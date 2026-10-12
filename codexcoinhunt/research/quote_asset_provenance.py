#!/usr/bin/env python3
"""Offline exact-asset routing and capital-role audit; no orders or keys."""
import argparse
import base64
import collections
import hashlib
import json
from pathlib import Path
from buyer_enrichment import account_keys, enriched_events
from buyer_funding_audit import program_id, token_identities, SYSTEM
from buyer_probe import b58, utc, WSOL, PUMP_AMM
from buyer_trade_history import is_signer

TOKEN = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
USDC = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
USDT = 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB'
ASSETS = {USDC:'USDC',USDT:'USDT',WSOL:'WSOL'}
POOL_DISC = hashlib.sha256(b'account:Pool').digest()[:8]


def execution_instructions(tx):
    """Interleave each outer instruction and its CPI group in execution order."""
    keys=account_keys(tx)
    groups=collections.defaultdict(list)
    for group in (tx.get('meta') or {}).get('innerInstructions') or []:
        groups[group.get('index')]+=group.get('instructions') or []
    for outer, ix in enumerate(tx.get('transaction',{}).get('message',{}).get('instructions') or []):
        parent=program_id(ix,keys)
        yield f'outer:{outer}',ix,[]
        stack={1:parent}
        for inner, child in enumerate(groups[outer]):
            depth=child.get('stackHeight')
            if not isinstance(depth,int) or depth<2:
                yield f'inner:{outer}:{inner}',child,None
                stack={1:parent}
                continue
            stack={level:pid for level,pid in stack.items() if level<depth}
            ancestors=[stack[level] for level in sorted(stack)] if sorted(stack)==list(range(1,depth)) else None
            yield f'inner:{outer}:{inner}',child,ancestors
            stack[depth]=program_id(child,keys)


def raw_amount(value):
    if isinstance(value,str) and value.isdigit():return int(value)
    if isinstance(value,int) and not isinstance(value,bool) and value>=0:return value
    return None


def owned_changes(tx,user):
    meta=tx.get('meta') or {}; by_mint=collections.defaultdict(lambda:{'pre':0,'post':0,'decimals':set()})
    issues=[]
    for stage,field in [('pre','preTokenBalances'),('post','postTokenBalances')]:
        for balance in meta.get(field) or []:
            if balance.get('owner')!=user:continue
            amount=raw_amount((balance.get('uiTokenAmount') or {}).get('amount'))
            decimals=(balance.get('uiTokenAmount') or {}).get('decimals')
            if amount is None or not isinstance(decimals,int):
                issues.append({'reason':'missing_raw_amount_or_decimals','account_index':balance.get('accountIndex')});continue
            row=by_mint[balance.get('mint')];row[stage]+=amount;row['decimals'].add(decimals)
    rows=[]
    for mint,values in sorted(by_mint.items()):
        if len(values['decimals'])!=1:
            issues.append({'reason':'conflicting_decimals','mint':mint});continue
        rows.append({'mint':mint,'asset_label':ASSETS.get(mint),'decimals':next(iter(values['decimals'])),
                     'pre_raw':str(values['pre']),'post_raw':str(values['post']),
                     'net_delta_raw':str(values['post']-values['pre']),
                     'ultimate_funding_or_usd_value_verified':False})
    return rows,issues


def token_transfer(ix,keys,identities):
    if program_id(ix,keys)!=TOKEN:return None,'not_legacy_token_program'
    parsed=ix.get('parsed') or {};info=parsed.get('info') or {};kind=parsed.get('type')
    if kind not in ('transfer','transferChecked'):return None,'not_token_transfer'
    source,destination=info.get('source'),info.get('destination')
    s=identities.get(source) or {};d=identities.get(destination) or {}
    mints={x for x in [s.get('mint'),d.get('mint'),info.get('mint')] if x is not None}
    if s.get('identity_conflict') or d.get('identity_conflict') or len(mints)!=1 or next(iter(mints))!=WSOL:
        return None,'unverified_or_conflicting_legacy_wsol_mint'
    if kind=='transferChecked' and (info.get('tokenAmount') or {}).get('decimals')!=9:
        return None,'wrong_wsol_decimals'
    amount=raw_amount(info.get('amount') if kind=='transfer' else (info.get('tokenAmount') or {}).get('amount'))
    if amount is None:return None,'invalid_raw_token_amount'
    if not s.get('owner') or not d.get('owner'):return None,'unverified_token_owner'
    return {'source_account':source,'destination_account':destination,'source_token_owner':s['owner'],
            'destination_token_owner':d['owner'],'mint':WSOL,'amount_raw':str(amount),
            'transfer_authority':info.get('authority'),'initial_funder_verified':False},None


def audit_buy(response,event):
    params=(response.get('request') or {}).get('params') or []
    base={'user':event['user'],'signature':event['signature'],'pool':event['pool'],'mint':event['mint']}
    if len(params)<2 or params[0]!=event['signature'] or params[1].get('commitment')!='finalized':
        return {'status':'unverified_signature_or_finality',**base}
    tx=(response.get('body') or {}).get('result')
    if not isinstance(tx,dict) or tx.get('meta') is None:return {'status':'missing_body_or_metadata',**base}
    meta=tx['meta']
    if meta.get('err') is not None or any(' failed:' in l for l in meta.get('logMessages') or []):
        return {'status':'failed_or_caught_inner_failure','historical_transaction_fee_lamports':meta.get('fee'),**base}
    decoded,_=enriched_events(tx,event['signature'],event['pool'],event['mint'],response['received_at_utc'])
    matching=[e for e in decoded if e['side']=='B' and e['user']==event['user']
              and e['reconciliation']['verified'] and e['quote_token_account']==event['quote_token_account']]
    if not matching or not is_signer(tx,event['user']):return {'status':'exact_authorized_buy_not_verified',**base}
    keys=account_keys(tx);identities=token_identities(tx);q=event['quote_token_account'];q_identity=identities.get(q) or {}
    if q_identity.get('mint')!=WSOL or q_identity.get('owner')!=event['user']:
        return {'status':'exact_quote_mint_owner_not_verified',**base}
    incoming=[];outgoing=[];native=[];closures=[];issues=[]
    sequence=list(execution_instructions(tx))
    for order,(path,ix,ancestors) in enumerate(sequence):
        parsed=ix.get('parsed') or {};info=parsed.get('info') or {}
        referenced=[keys[index] if isinstance(index,int) and 0<=index<len(keys) else index for index in ix.get('accounts') or []]
        if program_id(ix,keys)==TOKEN and not parsed and q in referenced:
            issues.append({'path':path,'reason':'unparsed_token_instruction_referencing_quote_account'})
        if q in (info.get('source'),info.get('destination')) and program_id(ix,keys)==TOKEN and parsed.get('type') in ('transfer','transferChecked'):
            transfer,reason=token_transfer(ix,keys,identities)
            if transfer is None:issues.append({'path':path,'reason':reason});continue
            transfer.update(instruction_path=path,execution_order=order,ancestor_program_ids=ancestors)
            if transfer['destination_account']==q:incoming.append(transfer)
            if transfer['source_account']==q:outgoing.append(transfer)
        if program_id(ix,keys)==SYSTEM and parsed.get('type') in ('createAccount','transfer') and q in (info.get('newAccount'),info.get('destination')):
            amount=raw_amount(info.get('lamports'))
            native.append({'instruction_path':path,'source':info.get('source'),'lamports_including_possible_storage_deposit':str(amount) if amount is not None else None,
                           'type':parsed['type'],'source_is_user':info.get('source')==event['user'],'quote_token_amount_from_native_verified':False})
        if program_id(ix,keys)==TOKEN and parsed.get('type')=='closeAccount' and info.get('account')==q:
            closures.append({'instruction_path':path,'destination':info.get('destination'),'close_authority':info.get('owner') or info.get('authority'),
                             'initial_funder_verified':False})
    changes,change_issues=owned_changes(tx,event['user']);issues+=change_issues
    disposals=[c for c in changes if int(c['net_delta_raw'])<0 and c['mint'] not in (event['mint'],WSOL)]
    classes=('stablecoin_disposal_with_routed_wsol' if incoming and any(c['asset_label'] in ('USDC','USDT') for c in disposals) else
             'other_mint_disposal_with_routed_wsol' if incoming and disposals else
             'native_sol_quote_account_input' if native and not incoming else
             'unclassified_quote_capital')
    total_in=sum(int(t['amount_raw']) for t in incoming);total_out=sum(int(t['amount_raw']) for t in outgoing)
    token_net=int(next((c['net_delta_raw'] for c in changes if c['mint']==event['mint']),'0'))
    return {'status':'exact_buy_and_quote_route_audited',**base,'available_at_utc':response['received_at_utc'],
            'quote_account':q,'quote_identity':q_identity,'fee_payer':keys[0],
            'user_is_fee_payer':keys[0]==event['user'],'fee_payer_is_user_owner_proof':False,
            'historical_transaction_fee_lamports':meta.get('fee'),'event_reported_quote_raw':event['user_quote_raw'],
            'verified_quote_transfer_in_raw':str(total_in),'verified_quote_transfer_out_raw':str(total_out),
            'event_quote_matches_whole_account_outflow':total_out==int(event['user_quote_raw']) if not issues else None,
            'event_vs_outflow_difference_raw':str(total_out-int(event['user_quote_raw'])) if not issues else None,
            'quote_transfer_in':incoming,'quote_transfer_out':outgoing,'native_account_inputs':native,
            'quote_account_closures':closures,'owned_asset_changes':changes,'other_asset_disposals':disposals,
            'mechanism_class':classes,'target_net_inventory_delta_raw':str(token_net),'flow_attribution_issues':issues,
            'new_external_funding_from_route_credit_verified':False,'initial_funding_root_verified':False,
            'independent_buyer_certified':False,'historical_entry_eligibility_promoted':False,
            'realized_profit_usd_verified':False,'complete_cost_reconciliation':False,
            'note':'Exact token movements and disposal coexist in this transaction. Route credit, native wallet balance and event notional do not establish ultimate funding, a common human owner or recoverable USD profit.'}


def current_accounts(response):
    params=(response.get('request') or {}).get('params') or []
    if len(params)<2 or params[1].get('commitment')!='finalized':return []
    result=(response.get('body') or {}).get('result') or {};values=result.get('value') or []
    rows=[]
    for address,value in zip(params[0],values):
        row={'address':address,'available_at_utc':response['received_at_utc'],'context_slot':(result.get('context') or {}).get('slot'),
             'historical_owner_role_verified':False}
        if value is None:row['status']='missing_current_account';rows.append(row);continue
        raw=base64.b64decode(value['data'][0]);row.update(status='current_account_decoded',owner_program=value['owner'],bytes=len(raw),executable=value.get('executable'))
        if value['owner']==TOKEN and len(raw)==165 and raw[108] in (1,2):
            row.update(mint=b58(raw[:32]),token_owner=b58(raw[32:64]),amount_raw=str(int.from_bytes(raw[64:72],'little')))
        if value['owner']==PUMP_AMM and len(raw)>=203 and raw[:8]==POOL_DISC:
            row.update(pool_base_mint=b58(raw[43:75]),pool_quote_mint=b58(raw[75:107]),
                       pool_base_vault=b58(raw[139:171]),pool_quote_vault=b58(raw[171:203]))
        rows.append(row)
    return rows


def related_roles(audits,states):
    state={r['address']:r for r in states};source_users=collections.defaultdict(set);payer_users=collections.defaultdict(set)
    source_owner={}
    for a in audits:
        if a['status']!='exact_buy_and_quote_route_audited':continue
        payer_users[a['fee_payer']].add(a['user'])
        for transfer in a['quote_transfer_in']:
            source_users[transfer['source_account']].add(a['user']);source_owner[transfer['source_account']]=transfer['source_token_owner']
    rows=[]
    for source,users in sorted(source_users.items()):
        owner=source_owner[source];now=state.get(owner) or {}
        program=now.get('owner_program');controlled=bool(program and program not in (SYSTEM,TOKEN) and now.get('bytes',0)>0 and not now.get('executable'))
        rows.append({'kind':'shared_or_distinct_quote_route_source','source_account':source,'source_token_owner':owner,
                     'buyers':sorted(users),'owner_current_program':program,'current_program_owned_data_account':controlled,
                     'current_role_available_at_utc':now.get('available_at_utc'),'historical_service_role_verified':False,
                     'classify_as_same_person_or_initial_funder':False})
    for payer,users in sorted(payer_users.items()):
        if len(users)>1:rows.append({'kind':'shared_fee_payer','fee_payer':payer,'buyers':sorted(users),
                                    'same_owner_or_shared_initial_funder_verified':False})
    return rows


def run(root,data,output):
    plan=json.loads((data/'plan.json').read_text());output.mkdir(parents=True,exist_ok=False)
    records={}
    for name in ['data/buyer_probe_20261012/rpc.jsonl','data/buyer_probe_20261012/wallet_rpc.jsonl']:
        for line in (root/name).read_text().splitlines():
            r=json.loads(line)
            if r['request']['method']=='getTransaction' and isinstance(r.get('body',{}).get('result'),dict):records[r['request']['params'][0]]=r
    original=[json.loads(l) for l in (root/'data/buyer_probe_20261012/events.jsonl').read_text().splitlines()]
    audits=[audit_buy(records[e['signature']],e) for e in original if e['side']=='B']
    new=[json.loads(l) for l in (data/'rpc.jsonl').read_text().splitlines()] if (data/'rpc.jsonl').exists() else []
    states=[row for r in new for row in current_accounts(r) if r['request']['method']=='getMultipleAccounts']
    result={'id':plan['id'],'completed_at_utc':utc(),'same_five_buys_reaudited_not_new_market_observations':True,
            'new_read_only_account_response_count':len(new),'current_accounts_decoded':len(states),
            'buy_transactions_audited':len(audits),'mechanism_counts':dict(collections.Counter(a.get('mechanism_class',a['status']) for a in audits)),
            'event_quote_outflow_disagreements':sum(a.get('event_quote_matches_whole_account_outflow') is False for a in audits),
            'role_relations':related_roles(audits,states),'strategy_closed_positions_added':0,
            'matched_net_account_comparisons_added':0,'recoverable_usd_profit_outcomes_added':0,
            'independent_clusters_verified':0,'initial_funding_roots_verified':0,
            'opportunity_frequency_or_calendar_timeout_estimate':None,
            'limits':['Current state cannot be inserted into original historical eligibility.',
                      'Stablecoin disposal is not proven fresh fiat inflow; other-token disposal is not proven profitable rotation.',
                      'Shared fee payers or routing vaults do not certify a common owner.',
                      'Transfer totals are exact account movements, not independently reconciled USD fills or all execution costs.',
                      'Original sample, missing social/US/exit/funding/conversion proof and unmatched controls remain explicit.']}
    (output/'buy_route_audits.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in audits))
    (output/'current_account_roles.json').write_text(json.dumps(states,indent=2)+'\n')
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=Path('.'))
    parser.add_argument('--data',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.root,args.data,args.output)
