#!/usr/bin/env python3
"""Collect the frozen bounded public transaction plan. No orders or credentials."""
import argparse
import json
from pathlib import Path
import time
from buyer_probe import rpc, utc


def collect(directory):
    plan = json.loads((directory / 'plan.json').read_text())
    raw = directory / 'rpc.jsonl'
    if raw.exists(): raise ValueError('preserve existing evidence; choose a new collection directory')
    requested = [s for row in plan['selection'] for s in row['selected'] if s['existing_body_path'] is None]
    if len(requested) > plan['maximum_new_body_reads']: raise ValueError('collection exceeds frozen request bound')
    failures = 0
    for index, selected in enumerate(requested):
        time.sleep(2.5)
        response = rpc('https://api.mainnet-beta.solana.com', 'getTransaction',
                       [selected['signature'], {'commitment': 'finalized', 'encoding': 'jsonParsed',
                                                'maxSupportedTransactionVersion': 1}], raw)
        complete = isinstance(response.get('body', {}).get('result'), dict)
        failures = 0 if complete else failures + 1
        if index % 5 == 0 or failures:
            print(json.dumps({'requested':index+1,'planned':len(requested),'receipt_at_utc':utc(),
                              'body_available':complete,'consecutive_errors':failures}),flush=True)
        if failures >= 3: break
    print(json.dumps({'finished_at_utc':utc(),'requests_written':sum(1 for _ in raw.open()) if raw.exists() else 0,
                      'complete_bodies_are_not_trade_or_funding_proof':True}),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    collect(parser.parse_args().directory)
