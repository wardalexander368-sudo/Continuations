#!/usr/bin/env python3
"""Bounded prior-swap evidence for fixed public event users. No orders or keys."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import time

from buyer_probe import rpc, utc, b58, BUY_DISC, SELL_DISC, WSOL
from buyer_enrichment import account_keys, decode_prefix, enriched_events, event_payloads


def saved_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def is_signer(tx, wallet):
    message = tx.get('transaction', {}).get('message', {})
    keys = message.get('accountKeys', [])
    if any(isinstance(key, dict) for key in keys):
        return any(key.get('pubkey') == wallet and key.get('signer') is True for key in keys if isinstance(key, dict))
    required = message.get('header', {}).get('numRequiredSignatures')
    return isinstance(required, int) and wallet in keys[:required]


def prior_swap_events(response, profiles):
    request = response.get('request', {})
    if request.get('method') != 'getTransaction': return [], []
    params = request.get('params', [])
    if len(params) < 2 or params[1].get('commitment') != 'finalized':
        return [], [{'reason':'unverified_finalized_request'}]
    tx = response.get('body', {}).get('result')
    if not isinstance(tx, dict): return [], [{'reason':'missing_body', 'signature':params[0]}]
    meta = tx.get('meta')
    if not meta or meta.get('err') is not None: return [], [{'reason':'failed_or_missing_metadata', 'signature':params[0]}]
    # A router can catch a CPI failure and finish the overall transaction.
    # Logs from rolled-back invocations are insufficient swap proof; exact
    # invocation rollback alignment remains a dependency for those bodies.
    if any(' failed:' in line for line in meta.get('logMessages') or []):
        return [], [{'reason':'failed_inner_invocation_requires_rollback_alignment','signature':params[0]}]
    keys = account_keys(tx)
    pools = set()
    issues = []
    for source, location, raw in event_payloads(tx)[0]:
        if raw[:8] not in (BUY_DISC, SELL_DISC): continue
        if len(raw) < 344:
            issues.append({'reason':'truncated_event', 'location':str(location)})
            continue
        event = decode_prefix(raw, b58(raw[120:152]))
        user = event['user']
        if user not in profiles: continue
        profile = profiles[user]
        if tx.get('blockTime') is None or tx['blockTime'] >= profile['prior_cutoff_unix_time']:
            issues.append({'reason':'not_verified_before_target_event', 'user':user})
            continue
        if not is_signer(tx, user):
            issues.append({'reason':'event_user_not_transaction_signer', 'user':user})
            continue
        try: account_index = keys.index(event['base_token_account'])
        except ValueError:
            issues.append({'reason':'event_account_missing', 'user':user})
            continue
        balances = [balance for balance in (meta.get('preTokenBalances') or []) + (meta.get('postTokenBalances') or []) if balance.get('accountIndex') == account_index]
        mints = {balance.get('mint') for balance in balances}
        owners = {balance.get('owner') for balance in balances}
        if len(mints) != 1 or None in mints or owners != {user}:
            issues.append({'reason':'exact_base_mint_owner_not_verified', 'user':user})
            continue
        mint = next(iter(mints))
        if mint in (profile['mint'], WSOL): continue
        if int(event['base_amount_raw']) <= 0 or int(event['user_quote_raw']) <= 0:
            issues.append({'reason':'nonpositive_swap_amounts', 'user':user})
            continue
        pools.add((event['pool'], mint, user))
    events = []
    for pool, mint, user in sorted(pools):
        decoded, errors = enriched_events(tx, params[0], pool, mint, response['received_at_utc'])
        issues.extend(errors)
        for event in decoded:
            if event['user'] != user or not event['reconciliation']['verified']: continue
            if int(event['base_amount_raw']) <= 0 or int(event['user_quote_raw']) <= 0: continue
            event.update(proof_grade='successful_finalized_pumpswap_event_exact_base_mint_owner_and_signer',
                         other_mint_trade_verified=True,
                         complete_wallet_trade_history=False,
                         event_user_is_transaction_signer=True,
                         prior_target_cutoff_unix_time=profiles[user]['prior_cutoff_unix_time'],
                         historical_entry_eligibility_promoted=False,
                         quote_asset_cash_reconciliation_complete=False,
                         note='An emitted successful swap verifies a trade, even if a later same-transaction swap/transfer offsets its net balance. No return or independent person inferred.')
            events.append(event)
    return events, issues


def fetch_plan(history, maximum):
    profiles = {row['wallet']:row for row in json.loads((history/'summary.json').read_text())['rows']}
    old = saved_rows(history/'rpc.jsonl')
    inspected = {row['request']['params'][0] for row in old if row['request']['method'] == 'getTransaction'}
    plans = []
    for wallet, profile in sorted(profiles.items()):
        signatures = {}
        for row in old:
            if row['request']['method'] != 'getSignaturesForAddress' or row['request']['params'][0] != wallet: continue
            for signature in row.get('body', {}).get('result') or []:
                if signature.get('err') is None and signature.get('blockTime') is not None and signature['blockTime'] < profile['prior_cutoff_unix_time'] and signature['signature'] not in inspected:
                    signatures[signature['signature']] = signature
        ordered = sorted(signatures.values(), key=lambda row:(row['blockTime'],row['signature']))
        indices = sorted({round(index*(len(ordered)-1)/max(1,maximum-1)) for index in range(min(maximum,len(ordered)))}) if ordered else []
        plans.append({'wallet':wallet,'successful_uninspected_prior_signatures_in_saved_pages':len(ordered),
                      'selected_signatures':[ordered[index] for index in indices],
                      'selection':'fixed evenly spaced chronological ranks among uninspected successful pre-event signatures; not chosen by outcome'})
    return profiles, plans


def run(history, output, maximum, collect, additional_rpc=None):
    output.mkdir(parents=True,exist_ok=False)
    profiles, plans = fetch_plan(history, maximum)
    plan = {'frozen_at_utc':utc(),'mode':'bounded_read_only' if collect else 'offline_reaudit',
            'source_rpc_sha256':hashlib.sha256((history/'rpc.jsonl').read_bytes()).hexdigest(),
            'maximum_new_transaction_bodies_per_user':maximum,'plans':plans,
            'history_is_complete':False,'market_outcomes_used_for_selection':False,'real_orders':0}
    if additional_rpc:
        plan.update(additional_rpc_source=str(additional_rpc),
                    additional_rpc_sha256=hashlib.sha256(additional_rpc.read_bytes()).hexdigest(),
                    original_collection_plan=str(additional_rpc.with_name('plan.json')),
                    new_network_requests=0)
    (output/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    raw = output/'rpc.jsonl'
    if collect:
        consecutive_errors = 0
        for wallet in plans:
            for selected in wallet['selected_signatures']:
                time.sleep(2.5)
                row = rpc('https://api.mainnet-beta.solana.com','getTransaction',[selected['signature'],{'commitment':'finalized','encoding':'jsonParsed','maxSupportedTransactionVersion':1}],raw)
                good = isinstance(row.get('body',{}).get('result'),dict)
                consecutive_errors = 0 if good else consecutive_errors + 1
                if consecutive_errors >= 3: break
            print(json.dumps({'wallet':wallet['wallet'],'last_receipt_utc':utc(),'consecutive_errors':consecutive_errors}),flush=True)
            if consecutive_errors >= 3: break
    added_rows = saved_rows(additional_rpc) if additional_rpc else saved_rows(raw) if raw.exists() else []
    rows = saved_rows(history/'rpc.jsonl') + added_rows
    events = {}; errors = []; body_count = 0
    for response in rows:
        if response['request']['method'] != 'getTransaction': continue
        body_count += int(isinstance(response.get('body',{}).get('result'),dict))
        decoded, issues = prior_swap_events(response, profiles)
        errors.append({'signature':response['request']['params'][0], 'issues':issues})
        for event in decoded: events.setdefault(event['event_id'],event)
    by_wallet = collections.defaultdict(list)
    for event in events.values(): by_wallet[event['user']].append(event)
    summaries = []
    for wallet, profile in sorted(profiles.items()):
        trades = by_wallet[wallet]; mints = sorted({event['mint'] for event in trades})
        summaries.append({'wallet':wallet,'target_mint':profile['mint'],'prior_cutoff_unix_time':profile['prior_cutoff_unix_time'],
                          'at_least_14_days_activity_verified':profile['at_least_14_days_verified'],
                          'other_mints_balance_evidence_lower_bound':profile['prior_other_mints_owned_or_touched_lower_bound'],
                          'verified_pumpswap_trade_events':len(trades),'verified_other_mints_traded_lower_bound':len(mints),'verified_other_mints':mints,
                          'at_least_3_other_mints_traded_verified':True if len(mints)>=3 else None,
                          'maturity_and_other_mint_activity_verified':profile['at_least_14_days_verified'] is True and len(mints)>=3,
                          'complete_trade_history':False,'independent_funding_cluster_verified':False,
                          'first_target_mint_participation_verified':False,
                          'trade_lower_bound_evidence_available_at_utc':max([event['available_at_utc'] for event in trades],default=profile['available_at_utc']),
                          'historical_entry_eligibility_promoted':False})
    result = {'completed_at_utc':utc(),'status':'partial prior swap proof; not a profitability test or independent-buyer proof',
              'additional_rpc_responses':len(added_rows),
              'new_network_requests_this_execution':0 if additional_rpc or not collect else len(added_rows),
              'transaction_bodies_inspected_including_prior':body_count,'deduplicated_trade_events':len(events),'rows':summaries,
              'wallets_traded_3_other_mints_verified':sum(row['at_least_3_other_mints_traded_verified'] is True for row in summaries),
              'wallets_maturity_and_other_mints_verified':sum(row['maturity_and_other_mint_activity_verified'] for row in summaries),
              'independent_clusters_verified':0,'strategy_entries_added':0,'costed_account_outcomes_added':0,
              'limits':['only successful PumpSwap events with exact event-user signer/base-account proof counted','other programs and proxy users remain unknown','a transaction referencing a wallet or old token balance alone is insufficient','representations are deduplicated; repeated same-mint trades are not different mints','profile receipt is later than original events and cannot backdate eligibility','no attention data, full buyer window or matched account outcomes']}
    (output/'events.jsonl').write_text(''.join(json.dumps(event)+'\n' for event in events.values()))
    (output/'transaction_issues.json').write_text(json.dumps(errors,indent=2)+'\n')
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items() if key not in ('rows','limits')},indent=2),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('history',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--maximum',type=int,default=8);parser.add_argument('--collect',action='store_true')
    parser.add_argument('--additional-rpc',type=Path,help='offline reuse of a previous collection; no new requests')
    args=parser.parse_args()
    if not 1<=args.maximum<=12:parser.error('maximum must be 1–12 bodies per user')
    if args.collect and args.additional_rpc:parser.error('choose collection or offline additional RPC, not both')
    run(args.history,args.output,args.maximum,args.collect,args.additional_rpc)
