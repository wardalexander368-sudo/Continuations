#!/usr/bin/env python3
"""Offline native-payment, account-close and prior-participation evidence audit.

No amount, missing link or source label certifies an independent person. The
module neither signs nor sends transactions and does not manufacture fills.
"""
import argparse
import collections
import json
from pathlib import Path
from buyer_enrichment import account_keys, enriched_events
from buyer_trade_history import is_signer
from buyer_probe import utc, WSOL

SYSTEM = '11111111111111111111111111111111'
TOKENS = {'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',
          'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'}


def instructions(tx):
    message = tx.get('transaction', {}).get('message', {})
    for index, ix in enumerate(message.get('instructions') or []):
        yield 'outer:' + str(index), ix
    for group in (tx.get('meta') or {}).get('innerInstructions') or []:
        for index, ix in enumerate(group.get('instructions') or []):
            yield f"inner:{group.get('index')}:{index}", ix


def program_id(ix, keys):
    if ix.get('programId') is not None: return ix['programId']
    index = ix.get('programIdIndex')
    return keys[index] if isinstance(index, int) and 0 <= index < len(keys) else None


def balance_change(tx, wallet):
    keys = account_keys(tx)
    try: index = keys.index(wallet)
    except ValueError: return None
    meta = tx.get('meta') or {}
    before, after = meta.get('preBalances') or [], meta.get('postBalances') or []
    if index >= len(before) or index >= len(after): return None
    return {'before_lamports':before[index], 'after_lamports':after[index],
            'net_change_lamports':after[index] - before[index],
            'wallet_fee_payer':index == 0, 'transaction_fee_lamports':meta.get('fee'),
            'external_funding_attribution_verified':False}


def token_identities(tx):
    """Include transient initialized-and-closed accounts absent from balances.

    Conflicting identity evidence remains unknown. An instruction alias alone
    cannot establish Token Program execution or a native source wallet.
    """
    keys = account_keys(tx); meta = tx.get('meta') or {}
    evidence = collections.defaultdict(list)
    for kind in ('preTokenBalances','postTokenBalances'):
        for balance in meta.get(kind) or []:
            index = balance.get('accountIndex')
            if isinstance(index,int) and 0 <= index < len(keys):
                evidence[keys[index]].append({'mint':balance.get('mint'),'owner':balance.get('owner'),
                                               'path':kind + ':' + str(index)})
    for path, ix in instructions(tx):
        parsed = ix.get('parsed') or {}; info = parsed.get('info') or {}
        if program_id(ix,keys) in TOKENS and parsed.get('type') in ('initializeAccount','initializeAccount2','initializeAccount3'):
            if info.get('account') in keys:
                evidence[info['account']].append({'mint':info.get('mint'),'owner':info.get('owner'),'path':path})
    result = {}
    for account, items in evidence.items():
        mints = {row['mint'] for row in items if row.get('mint') is not None}
        owners = {row['owner'] for row in items if row.get('owner') is not None}
        conflict = len(mints) > 1 or len(owners) > 1
        result[account] = {'mint':next(iter(mints)) if len(mints)==1 and not conflict else None,
                           'owner':next(iter(owners)) if len(owners)==1 and not conflict else None,
                           'identity_conflict':conflict,'evidence_paths':[row['path'] for row in items]}
    return result


def audit_transaction(response, profile, plan):
    request = response.get('request') or {}
    params = request.get('params') or []
    issue = {'signature':params[0] if params else None,'wallet':profile['wallet']}
    if request.get('method') != 'getTransaction' or len(params) < 2 or params[1].get('commitment') != 'finalized':
        return {'status':'unverified_finality', **issue}
    tx = (response.get('body') or {}).get('result')
    if not isinstance(tx, dict): return {'status':'missing_body', **issue}
    meta = tx.get('meta')
    if meta is None: return {'status':'missing_metadata', **issue}
    if meta.get('err') is not None:
        return {'status':'failed_transaction_no_payment_or_swap_proof',
                'transaction_fee_lamports':meta.get('fee'), **issue}
    block_time = tx.get('blockTime')
    if not isinstance(block_time, int) or not profile['start_unix_time'] <= block_time < profile['cutoff_unix_time']:
        return {'status':'outside_verified_prior_window', **issue}
    if any(' failed:' in line for line in meta.get('logMessages') or []):
        return {'status':'caught_inner_failure_requires_rollback_alignment', **issue}
    wallet = profile['wallet']; keys = account_keys(tx)
    token_accounts = token_identities(tx)
    prior_inventory = []
    for balance in (meta.get('preTokenBalances') or []) + (meta.get('postTokenBalances') or []):
        index = balance.get('accountIndex')
        if balance.get('owner') == wallet and balance.get('mint') == plan['mint']:
            raw = (balance.get('uiTokenAmount') or {}).get('amount')
            if isinstance(raw, str) and raw.isdigit() and int(raw) > 0:
                prior_inventory.append({'account_index':index,'mint':plan['mint'],
                                        'raw_amount':raw,'kind':'positive_prior_exact_owned_inventory'})
    payments = []; closes = []; unknown_instructions = []
    seen_paths = set()
    for path, ix in instructions(tx):
        if path in seen_paths:
            unknown_instructions.append({'path':path,'reason':'duplicated_instruction_path'})
            continue
        seen_paths.add(path)
        parsed = ix.get('parsed') or {}; info = parsed.get('info') or {}
        program = program_id(ix, keys); kind = parsed.get('type')
        if program == SYSTEM and kind in ('transfer', 'transferWithSeed') and info.get('destination') == wallet:
            source = info.get('source'); amount = info.get('lamports')
            if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
                unknown_instructions.append({'path':path,'reason':'invalid_lamport_amount'}); continue
            reason = ('self_transfer' if source == wallet else
                      'token_account_source_not_external_wallet' if source in token_accounts else
                      'seed_transfer_authority_requires_derivation' if kind != 'transfer' else
                      'source_not_transaction_signer' if not is_signer(tx, source) else
                      'below_frozen_materiality' if amount < profile['materiality_lamports'] else
                      'material_authorized_native_receipt_candidate')
            payments.append({'instruction_path':path,'source':source,'destination':wallet,
                             'lamports':amount,'instruction_type':kind,'source_is_transaction_signer':is_signer(tx,source),
                             'materiality_lamports':profile['materiality_lamports'],'classification':reason,
                             'material_direct_receipt_candidate':reason == 'material_authorized_native_receipt_candidate',
                             'first_funding_root_verified':False,'retained_external_funding_verified':False,
                             'service_status':'unknown','independent_person_verified':False})
        elif program in TOKENS and kind == 'closeAccount' and info.get('destination') == wallet:
            source = info.get('account'); balance = token_accounts.get(source) or {}
            closes.append({'instruction_path':path,'source_account':source,'destination':wallet,
                           'source_token_owner':balance.get('owner'),'source_mint':balance.get('mint'),
                           'close_authority':info.get('owner') or info.get('authority'),
                           'classification':('token_account_close_identity_unknown' if not balance.get('mint') or not balance.get('owner') else
                                             'wrapped_SOL_release' if balance.get('mint') == WSOL else 'token_storage_deposit_release'),
                           'source_owner_proof_available':bool(balance.get('owner')),
                           'identity_evidence_paths':balance.get('evidence_paths') or [],
                           'independent_funder_verified':False,
                           'note':'Account closure can return own/recycled capital; token account address is not a distinct external funder.'})
        elif ix.get('program') == 'system' and program != SYSTEM and info.get('destination') == wallet:
            unknown_instructions.append({'path':path,'reason':'parsed_program_alias_does_not_verify_program_id'})
    events, event_errors = enriched_events(tx, params[0], plan['pool'], plan['mint'], response['received_at_utc'])
    target_events = [event for event in events if event['user'] == wallet
                     and event['reconciliation']['verified'] and is_signer(tx,wallet)
                     and profile['start_unix_time'] <= event['event_unix_time'] < profile['cutoff_unix_time']
                     and int(event['base_amount_raw']) > 0 and int(event['user_quote_raw']) > 0]
    return {'status':'successful_finalized_body','wallet':wallet,'signature':params[0],
            'block_time':block_time,'available_at_utc':response['received_at_utc'],
            'native_balance':balance_change(tx,wallet),'incoming_system_payments':payments,
            'token_account_closures':closes,'prior_target_swap_events':target_events,
            'prior_target_inventory':prior_inventory,'event_decode_issues':event_errors,
            'unknown_instructions':unknown_instructions,'initial_funding_or_independence_verified':False}


def source_relations(audits, plan, service_registry=None):
    registry = service_registry or {}; sources = collections.defaultdict(set)
    for audit in audits:
        for payment in audit.get('incoming_system_payments') or []:
            if payment['material_direct_receipt_candidate']:
                sources[payment['source']].add(audit['wallet'])
    rows = []
    buyers = {row['wallet'] for row in plan['selection']}
    for source, destinations in sorted(sources.items()):
        label = registry.get(source) or {}
        service_verified = label.get('category') == 'service' and bool(label.get('source_url')) and bool(label.get('available_at_utc'))
        relation = ('verified_service_excluded_from_common_owner_grouping' if service_verified else
                    'payment_from_historical_event_creator_fee_role' if source == plan['historical_event_coin_creator'] else
                    'payment_from_another_sampled_buyer' if source in buyers else
                    'shared_unknown_source_candidate' if len(destinations) > 1 else
                    'distinct_unknown_source_not_independence_proof')
        rows.append({'source':source,'destination_buyers':sorted(destinations),'service_status':'verified_service' if service_verified else 'unknown',
                     'service_evidence':label if service_verified else None,'relation':relation,
                     'same_owner_cluster_verified':False,'independent_clusters_verified':0})
    return rows


def load_records(root, plan, new_raw):
    records = {}
    paths = [root / path for path in plan['saved_raw_sources']] + [new_raw]
    for path in paths:
        if not path.exists(): continue
        for line in path.read_text().splitlines():
            if not line.strip(): continue
            response = json.loads(line); request = response.get('request') or {}
            if request.get('method') != 'getTransaction': continue
            signature = request['params'][0]
            old = records.get(signature)
            new_valid = isinstance((response.get('body') or {}).get('result'),dict)
            if old is None or (new_valid and not isinstance((old.get('body') or {}).get('result'),dict)):
                records[signature] = response
    return records


def run(root, directory, output):
    plan = json.loads((directory / 'plan.json').read_text())
    output.mkdir(parents=True,exist_ok=False)
    records = load_records(root,plan,directory / 'rpc.jsonl')
    audits = []; rows = []
    for profile in plan['selection']:
        own = []
        for selected in profile['selected']:
            response = records.get(selected['signature']) or {'request':{'method':'getTransaction','params':[selected['signature'],{'commitment':'finalized'}]}}
            audit = audit_transaction(response,profile,plan)
            audits.append(audit); own.append(audit)
        successes = [a for a in own if a['status'] == 'successful_finalized_body']
        # A positive balance could be an unsolicited transfer or airdrop. It
        # alone does not establish an earlier authorized buying decision.
        participation = [a for a in successes if a['prior_target_swap_events']]
        payments = [p for a in successes for p in a['incoming_system_payments']]
        rows.append({'wallet':profile['wallet'],'reported_window_signatures':profile['window_signatures_reported'],
                     'reported_failed_signatures':profile['failed_signatures_reported'],
                     'selected_signatures':len(own),'successful_finalized_bodies':len(successes),
                     'selected_all_reported_window_signatures':profile['selected_all_reported_window_signatures'],
                     'older_saved_page_precedes_window':profile['oldest_saved_page_precedes_window'],
                     'all_selected_bodies_available':all(a['status'] not in ('missing_body','missing_metadata') for a in own),
                     'incoming_native_payment_instructions':len(payments),
                     'material_direct_native_receipt_candidates':sum(p['material_direct_receipt_candidate'] for p in payments),
                     'closed_token_accounts_crediting_wallet':sum(len(a['token_account_closures']) for a in successes),
                     'prior_target_swap_event_count':sum(len(a['prior_target_swap_events']) for a in successes),
                     'prior_positive_target_inventory_bodies':sum(bool(a['prior_target_inventory']) for a in successes),
                     'new_to_mint_falsified':bool(participation),'new_to_mint_verified':False,
                     'participation_evidence_signatures':[a['signature'] for a in participation],
                     'native_funding_provenance_coverage':None,'initial_funding_root_verified':False,
                     'independent_buyer_verified':False,'historical_entry_eligibility_promoted':False})
    new_responses = [json.loads(line) for line in (directory / 'rpc.jsonl').read_text().splitlines()] if (directory / 'rpc.jsonl').exists() else []
    result = {'id':plan['id'],'completed_at_utc':utc(),'status':'bounded native-payment and prior-participation audit; no account returns or independent-human certification',
              'plan_frozen_at_utc':plan['frozen_at_utc'],'raw_new_rpc_responses':len(new_responses),
              'new_body_response_errors':sum(not isinstance((r.get('body') or {}).get('result'),dict) for r in new_responses),
              'receipt_first_utc':min((r['received_at_utc'] for r in new_responses),default=None),
              'receipt_last_utc':max((r['received_at_utc'] for r in new_responses),default=None),
              'selected_signature_wallet_pairs':len(audits),'rows':rows,'source_relations':source_relations(audits,plan),
              'new_to_mint_falsified_users':sum(row['new_to_mint_falsified'] for row in rows),
              'independent_clusters_verified':0,'initial_funding_roots_verified':0,
              'verified_strategy_entries_added':0,'costed_net_account_outcomes_added':0,
              'matched_random_attention_momentum_return_comparisons_added':0,
              'opportunity_frequency_and_calendar_campaign_timeouts':None,
              'limits':['Signature references are not payments or trades. Failures remain failures and retain recorded network fees.',
                        'Only one wallet has all reported 24-hour signatures selected; public pagination does not certify complete archival history.',
                        'A material signed payment is not necessarily retained or initial funding, nor an independent owner.',
                        'Token account closure may release wrapped SOL or storage deposits; neither creates a separate funding person.',
                        'Native-only analysis misses prior capital, token transfers, other programs and longer histories.',
                        'An earlier authorized exact trade disproves first-time entry. Positive inventory alone may be unsolicited; bounded absence proves neither first-time entry nor independence.',
                        'Post-event receipt times cannot qualify earlier entries. No attention/exit/fill/US eligibility evidence supplied.']}
    (output / 'transaction_audits.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in audits))
    (output / 'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('limits','rows')},indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('.'));parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.root,args.data,args.output)
