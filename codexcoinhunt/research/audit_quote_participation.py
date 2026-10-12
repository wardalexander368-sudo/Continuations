#!/usr/bin/env python3
"""Reproduce the frozen eight-body participation check without network access."""
import argparse
import collections
import json
from pathlib import Path
from buyer_funding_audit import audit_transaction
from buyer_probe import utc


def run(root,data,output):
    plan=json.loads((data/'participation_plan.json').read_text())
    original=json.loads((root/'data/buyer_funding_20261012/plan.json').read_text())
    profile=next(row for row in original['selection'] if row['wallet']==plan['wallet'])
    records=[json.loads(line) for line in (data/'participation_rpc.jsonl').read_text().splitlines() if line]
    allowed={row['signature'] for row in plan['selected']}
    if len(records)>8 or any(row['request']['params'][0] not in allowed for row in records):
        raise ValueError('raw responses exceed or disagree with the frozen selection')
    output.mkdir(parents=True,exist_ok=False)
    audits=[audit_transaction(row,profile,original) for row in records]
    summary={'id':plan['id'],'completed_at_utc':utc(),'wallet':plan['wallet'],'selected_body_requests':len(records),
             'successful_body_outcomes':dict(collections.Counter(row['status'] for row in audits)),
             'prior_target_swaps_verified':sum(len(row.get('prior_target_swap_events',[])) for row in audits),
             'new_to_mint_falsified':any(row.get('prior_target_swap_events') for row in audits),
             'new_to_mint_verified':False,'receipt_first_utc':min((row['received_at_utc'] for row in records),default=None),
             'receipt_last_utc':max((row['received_at_utc'] for row in records),default=None),
             'historical_eligibility_promoted':False,'frozen_plan':'data/quote_provenance_20261012/participation_plan.json'}
    (output/'transaction_audits.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in audits))
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=Path('.'))
    parser.add_argument('--data',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.root,args.data,args.output)
