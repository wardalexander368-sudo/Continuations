#!/usr/bin/env python3
"""Read only the frozen eight-signature participation plan; no paid services."""
import argparse
import json
from pathlib import Path
import time
from buyer_probe import rpc, utc


def collect(directory):
    plan=json.loads((directory/'participation_plan.json').read_text())
    raw=directory/'participation_rpc.jsonl'
    if raw.exists():raise ValueError('preserve existing raw evidence')
    if len(plan['selected'])>8:raise ValueError('frozen body bound exceeded')
    errors=0
    for index,row in enumerate(plan['selected']):
        time.sleep(2.5)
        response=rpc('https://api.mainnet-beta.solana.com','getTransaction',
                     [row['signature'],{'commitment':'finalized','encoding':'jsonParsed','maxSupportedTransactionVersion':1}],raw)
        good=isinstance(response.get('body',{}).get('result'),dict)
        errors=0 if good else errors+1
        print(json.dumps({'requested':index+1,'planned':len(plan['selected']),'receipt':utc(),'body_available':good}),flush=True)
        if errors>=3:break


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    collect(parser.parse_args().directory)
