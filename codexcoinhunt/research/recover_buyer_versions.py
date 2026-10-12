#!/usr/bin/env python3
"""Recover only explicit v1 read failures; retain original evidence and summaries."""
import argparse
import collections
import json
import pathlib
import time
from buyer_probe import rpc, swap_events, utc


def recover(folder):
    summary_path=folder/'summary.json'
    initial=json.loads(summary_path.read_text())
    preserved=folder/'summary_initial_v0.json'
    if preserved.exists(): raise ValueError('recovery already performed; do not re-query unchanged input')
    preserved.write_text(json.dumps(initial,indent=2)+'\n')
    events=[json.loads(x) for x in (folder/'events.jsonl').read_text().splitlines() if x.strip()]
    outcomes=initial['outcomes']
    raw_path=folder/'rpc.jsonl'
    evidence=[json.loads(x) for x in raw_path.read_text().splitlines()]
    recovered=0
    versions=collections.Counter()
    for record in evidence:
        if record['request']['method']=='getTransaction' and isinstance(record.get('body',{}).get('result'),dict):
            versions[str(record['body']['result'].get('version'))]+=1
    for outcome in outcomes:
        if outcome.get('rpc_error',{}).get('code')!=-32015: continue
        time.sleep(2.5)
        signature=outcome['signature']
        response=rpc(evidence[0]['url'],'getTransaction',[signature,{'commitment':'finalized','encoding':'jsonParsed','maxSupportedTransactionVersion':1}],raw_path)
        tx=response.get('body',{}).get('result')
        outcome['original_status']=outcome['status']
        outcome['retried_at_utc']=response['received_at_utc']
        if not tx:
            outcome['retry_status']='unavailable';outcome['retry_rpc_error']=response.get('body',{}).get('error');continue
        versions[str(tx.get('version'))]+=1
        tx['_target_mint']=initial['plan']['mint']
        decoded,errors=swap_events(tx,signature,initial['plan']['pool'])
        for e in decoded:e.update(mint=initial['plan']['mint'],available_at_utc=response['received_at_utc'],finalized=True)
        events+=decoded
        outcome.update(status='decoded' if decoded else 'no_matching_swap_event',retry_status='recovered',events=len(decoded),parse_errors=errors)
        recovered+=1
    unique={e['event_id']:e for e in events};events=list(unique.values())
    buys=[e for e in events if e['side']=='B'];sells=[e for e in events if e['side']=='S']
    by_user=collections.Counter()
    for e in buys:by_user[e['user']]+=int(e['user_quote_raw'])
    initial.update(completed_at_utc=utc(),explicit_version_failures_recovered=recovered,transaction_versions=dict(versions),
        decoded_swap_events=len(events),buy_events=len(buys),sell_events=len(sells),unique_buy_event_users=len(by_user),
        buy_quote_lamports=sum(int(e['user_quote_raw']) for e in buys),sell_user_receipts_lamports=sum(int(e['user_quote_raw']) for e in sells),
        largest_buyer_notional_fraction=max(by_user.values())/sum(by_user.values()) if by_user else None,
        initial_v0_result='summary_initial_v0.json; version failure correction is implementation development, not a later outcome-selection filter')
    summary_path.write_text(json.dumps(initial,indent=2)+'\n')
    (folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    print(json.dumps({k:v for k,v in initial.items() if k!='outcomes'},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=pathlib.Path);a=p.parse_args();recover(a.folder)
