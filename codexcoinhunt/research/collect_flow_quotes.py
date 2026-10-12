#!/usr/bin/env python3
"""Bounded unauthenticated historical Alpaca quote pages; no trade execution."""
import argparse
import datetime as dt
import gzip
import json
import pathlib
import urllib.parse
from collect_orderbook import get_record


def collect(output,max_pages):
    output.mkdir(parents=True,exist_ok=False)
    completion=[]
    for start,end in [('2026-10-09','2026-10-10'),('2026-10-10','2026-10-11')]:
        for symbol in ['DOGE/USD','BONK/USD','WIF/USD','PEPE/USD']:
            token=None;pages=0;count=0;status='complete'
            # An hour after midnight is needed to observe exits from late comparison signals.
            params={'symbols':symbol,'start':start+'T00:00:00Z','end':end+'T01:01:00Z','limit':10000,'sort':'asc'}
            for page in range(max_pages):
                query=dict(params)
                if token:query['page_token']=token
                url='https://data.alpaca.markets/v1beta3/crypto/us/quotes?'+urllib.parse.urlencode(query)
                record=get_record(url,page,'historical_quotes')
                record.update(symbol=symbol,date_partition=start)
                fname=f'{start}_{symbol.replace("/","_")}_{page:03d}.json.gz'
                with gzip.open(output/fname,'wt') as handle:json.dump(record,handle)
                pages+=1
                if record.get('http_status')!=200:status='http_error';break
                body=record.get('body',{});count+=len(body.get('quotes',{}).get(symbol,[]));token=body.get('next_page_token')
                if not token:break
            if token:status='page_limit_or_incomplete'
            row={'date':start,'symbol':symbol,'pages':pages,'quote_rows':count,'status':status,'next_page_token':token}
            completion.append(row);print(json.dumps(row),flush=True)
    (output/'summary.json').write_text(json.dumps({'completed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'public Alpaca us quote endpoint','streams':completion},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--max-pages',type=int,default=20);a=p.parse_args()
    if not 1<=a.max_pages<=30:p.error('page bound 1–30 required')
    collect(a.output,a.max_pages)
