#!/usr/bin/env python3
"""Read-only/offline buyer enrichment. No independence inferred from missing links."""
import argparse
import base64
import collections
import hashlib
import json
import pathlib
import re
import time
from buyer_probe import ALPHABET, BUY_DISC, SELL_DISC, PUMP_AMM, WSOL, b58, rpc, utc

EVENT_IX_TAG = bytes.fromhex('e445a52e51cb9a1d')


def unb58(text):
    number=0
    for char in text:
        if char not in ALPHABET:raise ValueError('invalid base58')
        number=number*58+ALPHABET.index(char)
    zeros=len(text)-len(text.lstrip('1'))
    return b'\0'*zeros+(number.to_bytes((number.bit_length()+7)//8,'big') if number else b'')


def account_keys(tx):
    message=tx.get('transaction',{}).get('message',{})
    raw=message.get('accountKeys',[])
    keys=[x.get('pubkey') if isinstance(x,dict) else x for x in raw]
    # jsonParsed accountKeys already contain resolved lookup accounts; json encoding does not.
    if not any(isinstance(x,dict) for x in raw):
        loaded=(tx.get('meta') or {}).get('loadedAddresses') or {}
        keys+=loaded.get('writable',[])+loaded.get('readonly',[])
    return keys


def event_payloads(tx):
    meta=tx.get('meta')
    if not meta or meta.get('err') is not None:return [],['failed or missing transaction metadata']
    records=[];errors=[];stack=[]
    for index,line in enumerate(meta.get('logMessages') or []):
        start=re.match(r'Program (\S+) invoke \[\d+\]',line)
        finish=re.match(r'Program (\S+) (success|failed:.*)$',line)
        if start:stack.append(start.group(1));continue
        if finish:
            if stack and stack[-1]==finish.group(1):stack.pop()
            else:stack=[]
            continue
        if line.startswith('Program data: ') and stack and stack[-1]==PUMP_AMM:
            try:records.append(('log',index,base64.b64decode(line[14:],validate=True)))
            except Exception as error:errors.append({'path':f'log:{index}','error':str(error)})
    keys=account_keys(tx)
    for outer in meta.get('innerInstructions') or []:
        for index,ix in enumerate(outer.get('instructions') or []):
            program=ix.get('programId')
            if program is None:
                pindex=ix.get('programIdIndex')
                if isinstance(pindex,int) and 0<=pindex<len(keys):program=keys[pindex]
            if program!=PUMP_AMM or 'data' not in ix:continue
            try:
                raw=unb58(ix['data'])
                if raw[:8]!=EVENT_IX_TAG:continue
                records.append(('cpi',f"{outer.get('index')}:{index}",raw[8:]))
            except Exception as error:errors.append({'path':f"cpi:{outer.get('index')}:{index}",'error':str(error)})
    return records,errors


def decode_prefix(raw,pool):
    if raw[:8] not in (BUY_DISC,SELL_DISC):return None
    if len(raw)<344:raise ValueError('truncated stable swap-event prefix')
    values=[int.from_bytes(raw[8+i*8:16+i*8],'little',signed=i==0) for i in range(14)]
    keys=[b58(raw[120+i*32:152+i*32]) for i in range(7)]
    if keys[0]!=pool:return None
    return {'pool':pool,'user':keys[1],'side':'B' if raw[:8]==BUY_DISC else 'S','event_unix_time':values[0],
        'base_amount_raw':str(values[1]),'user_quote_raw':str(values[13]),'curve_quote_raw':str(values[7]),
        'base_token_account':keys[2],'quote_token_account':keys[3],'coin_creator':keys[6],
        'pool_base_after_raw':str(values[5]),'pool_quote_after_raw':str(values[6])}


def token_reconciliation(tx,event,mint):
    """Check the event's exact token account and user against pre/post balances."""
    keys=account_keys(tx)
    try:index=keys.index(event['base_token_account'])
    except ValueError:return {'status':'unknown_event_account_not_in_transaction','verified':False}
    meta=tx.get('meta') or {}
    before=[x for x in meta.get('preTokenBalances') or [] if x.get('accountIndex')==index]
    after=[x for x in meta.get('postTokenBalances') or [] if x.get('accountIndex')==index]
    seen=before+after
    if not seen:return {'status':'unknown_token_balance_coverage','verified':False}
    if any(x.get('mint')!=mint or x.get('owner')!=event['user'] for x in seen):
        return {'status':'event_account_mint_or_owner_mismatch','verified':False}
    decimals={x.get('uiTokenAmount',{}).get('decimals') for x in seen}
    if len(decimals)!=1 or None in decimals:return {'status':'inconsistent_or_missing_decimals','verified':False}
    pre=int(before[0]['uiTokenAmount']['amount']) if before else 0
    post=int(after[0]['uiTokenAmount']['amount']) if after else 0
    delta=post-pre
    expected=int(event['base_amount_raw'])*(1 if event['side']=='B' else -1)
    return {'verified':True,'status':'exact_mint_and_event_owner_verified','decimals':next(iter(decimals)),
        'pre_balance_raw':str(pre),'post_balance_raw':str(post),'transaction_net_delta_raw':str(delta),
        'event_base_direction_matches_net':(delta>0 if event['side']=='B' else delta<0),
        'single_event_amount_matches_transaction_net':delta==expected,
        'net_caveat':'aggregate/roundtrip transfers can offset an event; zero prebalance does not establish first-ever mint participation'}


def enriched_events(tx,signature,pool,mint,available):
    payloads,errors=event_payloads(tx)
    counts=collections.defaultdict(lambda:collections.defaultdict(list));decoded={}
    for source,location,raw in payloads:
        try:
            event=decode_prefix(raw,pool)
            if event is None:continue
            # Match representations using the stable prefix, preserving occurrence counts.
            digest=hashlib.sha256(raw[:344]).hexdigest()
            counts[digest][source].append(str(location));decoded[digest]=event
        except Exception as error:errors.append({'source':source,'location':location,'error':str(error)})
    events=[]
    for digest,representations in counts.items():
        occurrences=max(len(paths) for paths in representations.values())
        for occurrence in range(occurrences):
            event=decoded[digest].copy()
            event.update(event_id=f'{signature}:event:{digest}:{occurrence}',signature=signature,mint=mint,
                available_at_utc=available,finalized=True,slot=tx.get('slot'),block_time=tx.get('blockTime'),
                evidence_paths={source:paths[occurrence] for source,paths in representations.items() if occurrence<len(paths)},
                reconciliation=token_reconciliation(tx,event,mint))
            events.append(event)
    return events,errors


def concentration(buys):
    notionals=collections.Counter()
    for event in buys:notionals[event['user']]+=int(event['user_quote_raw'])
    total=sum(notionals.values())
    hhi=sum((amount/total)**2 for amount in notionals.values()) if total else None
    return {'raw_event_users':len(notionals),'total_user_quote_raw':str(total),
        'largest_notional_share':max(notionals.values())/total if total else None,'notional_hhi':hhi,
        'notional_effective_user_count':1/hhi if hhi else None,
        'note':'notional diversity diagnostic, not a count of independent humans or a fitted trading threshold'}


def audit_saved(folder,output):
    output.mkdir(parents=True,exist_ok=False)
    plan=json.loads((folder/'plan.json').read_text());records=[json.loads(x) for x in (folder/'rpc.jsonl').read_text().splitlines()]
    latest={}
    for r in records:
        if r['request']['method']=='getTransaction' and isinstance(r.get('body',{}).get('result'),dict):latest[r['request']['params'][0]]=r
    events=[];outcomes=[]
    for signature,r in latest.items():
        found,errors=enriched_events(r['body']['result'],signature,plan['pool'],plan['mint'],r['received_at_utc'])
        events+=found;outcomes.append({'signature':signature,'events':len(found),'errors':errors})
    buys=[e for e in events if e['side']=='B'];old=[json.loads(x) for x in (folder/'events.jsonl').read_text().splitlines() if x]
    result={'status':'same fixed transactions re-audited; not a new market sample or return test',
        'completed_at_utc':utc(),'source_pool':plan['pool'],'mint':plan['mint'],'quote_mint':plan.get('quote_mint',WSOL),
        'retrieved_transactions':len(latest),'old_log_only_event_count':len(old),'complete_representation_event_count':len(events),
        'cpi_only_events_added':sum(set(e['evidence_paths'])=={'cpi'} for e in events),
        'dual_representation_events':sum(set(e['evidence_paths'])=={'log','cpi'} for e in events),
        'exact_event_account_mint_owner_verified':sum(e['reconciliation']['verified'] for e in events),
        'transaction_net_direction_matches':sum(e['reconciliation'].get('event_base_direction_matches_net',False) for e in events),
        'buy_concentration':concentration(buys),'outcomes':outcomes,
        'first_time_buyers_verified':None,'unrelated_clusters_verified':None,'strategy_eligible':False}
    (output/'events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in events))
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='outcomes'},indent=2))


def deep_history(folder,output,max_pages=5,page_size=100):
    output.mkdir(parents=True,exist_ok=False);events=[json.loads(x) for x in (folder/'events.jsonl').read_text().splitlines() if x]
    by_wallet=collections.defaultdict(list)
    for e in events:
        if e['side']=='B':by_wallet[e['user']].append(e)
    results=[];raw=output/'rpc.jsonl'
    for wallet,own in sorted(by_wallet.items()):
        cutoff=min(e['event_unix_time'] for e in own);collected={};before=None;history_exhausted=False;fetch_errors=[];receipts=[]
        for page in range(max_pages):
            args={'limit':page_size,'commitment':'finalized'}
            if before:args['before']=before
            time.sleep(1)
            response=rpc('https://api.mainnet-beta.solana.com','getSignaturesForAddress',[wallet,args],raw)
            receipts.append(response['received_at_utc']);rows=response.get('body',{}).get('result')
            if not isinstance(rows,list):fetch_errors.append(response.get('body',{}).get('error') or response.get('message'));break
            for s in rows:collected[s['signature']]=s
            if len(rows)<page_size:history_exhausted=True;break
            before=rows[-1]['signature']
            eligible=[s for s in collected.values() if s.get('err') is None and s.get('blockTime') is not None and s['blockTime']<cutoff]
            if len(eligible)>=10 and min(s['blockTime'] for s in eligible)<=cutoff-14*86400:break
        prior=sorted([s for s in collected.values() if s.get('err') is None and s.get('blockTime') is not None and s['blockTime']<cutoff],key=lambda s:s['blockTime'])
        age=(cutoff-prior[0]['blockTime'])/86400 if prior else None
        # Inspect a bounded spread of old prior activity; never call these first funding roots.
        indices=sorted({0,len(prior)//3,2*len(prior)//3,len(prior)-1}) if prior else []
        selected=[prior[i] for i in indices];other_mints=set();incoming=[];tx_errors=[]
        for row in selected:
            time.sleep(2.5)
            response=rpc('https://api.mainnet-beta.solana.com','getTransaction',[row['signature'],{'commitment':'finalized','encoding':'jsonParsed','maxSupportedTransactionVersion':1}],raw)
            receipts.append(response['received_at_utc']);tx=response.get('body',{}).get('result')
            if not tx:tx_errors.append(row['signature']);continue
            meta=tx.get('meta') or {}
            if meta.get('err') is not None:continue
            for balance in (meta.get('preTokenBalances') or [])+(meta.get('postTokenBalances') or []):
                if balance.get('owner')==wallet and balance.get('mint') not in (own[0]['mint'],WSOL):other_mints.add(balance['mint'])
            message=tx.get('transaction',{}).get('message',{})
            instructions=list(message.get('instructions') or [])
            for group in meta.get('innerInstructions') or []:instructions+=group.get('instructions') or []
            for ix in instructions:
                parsed=ix.get('parsed') or {};info=parsed.get('info') or {}
                if ix.get('program')=='system' and parsed.get('type') in ('transfer','transferWithSeed') and info.get('destination')==wallet and info.get('source')!=wallet:
                    incoming.append({'signature':row['signature'],'source':info.get('source'),'destination':wallet,'lamports':info.get('lamports'),'block_time':row['blockTime'],'available_at_utc':response['received_at_utc'],'kind':'observed_prior_incoming_transfer','first_funding_root':False,'source_service_status':'unknown'})
        results.append({'wallet':wallet,'mint':own[0]['mint'],'pages_queried':len([r for r in receipts])-len(selected),
            'prior_cutoff_unix_time':cutoff,'successful_prior_signatures_lower_bound':len(prior),'observed_prior_age_days_lower_bound':age,
            'at_least_14_days_verified':True if age is not None and age>=14 else None,'at_least_10_prior_transactions_verified':len(prior)>=10,
            'prior_other_mints_owned_or_touched_lower_bound':len(other_mints),'prior_other_mints':sorted(other_mints),
            'at_least_3_other_mints_balance_evidence':len(other_mints)>=3,'prior_other_mints_trade_count_verified':None,'inspected_prior_bodies':len(selected)-len(tx_errors),
            'incoming_transfer_evidence':incoming,'first_funding_root':None,'apparently_unrelated_buyer_cluster':None,'new_to_mint':None,
            'returned_history_page_exhausted':history_exhausted,'complete_archival_history_verified':False,
            'available_at_utc':max(receipts) if receipts else None,'signature_fetch_errors':fetch_errors,'transaction_fetch_errors':tx_errors})
    result={'status':'bounded historical activity and transfer evidence; no independence inferred','completed_at_utc':utc(),'wallet_count':len(results),
        'maturity_14d_verified':sum(r['at_least_14_days_verified'] is True for r in results),
        'at_least_3_other_mints_balance_evidence':sum(r['at_least_3_other_mints_balance_evidence'] for r in results),
        'wallets_traded_3_other_mints_verified':None,
        'first_funding_roots_verified':0,'unrelated_clusters_verified':0,'rows':results,
        'limits':['a common exchange/service funding source must not collapse unrelated buyers','distinct unlabelled funders do not prove independent buyers','post-event receipt times prevent retrospective eligibility promotion','four inspected bodies do not establish first-ever mint participation']}
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['audit','history']);p.add_argument('source',type=pathlib.Path);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--max-pages',type=int,default=5)
    a=p.parse_args()
    if not 1<=a.max_pages<=10:p.error('max pages must be 1–10')
    if a.mode=='audit':audit_saved(a.source,a.output)
    else:deep_history(a.source,a.output,a.max_pages)
