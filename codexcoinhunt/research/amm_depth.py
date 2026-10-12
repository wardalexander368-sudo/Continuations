#!/usr/bin/env python3
"""Describe a PumpSwap constant-product curve; it is not a resting-order book."""
import argparse
import json
import math
import pathlib


def depth_bands(base, quote_vault, virtual_quote, fee_buckets, price_changes=(0.01, 0.05, 0.10)):
    if base <= 0 or quote_vault <= 0 or quote_vault + virtual_quote <= 0 or not 0 <= fee_buckets <= quote_vault:
        raise ValueError('invalid or unavailable reserve state')
    effective=quote_vault+virtual_quote
    real=quote_vault-fee_buckets
    rows=[]
    for change in price_changes:
        if not 0 < change < 1: raise ValueError('price change must be 0–1')
        # Pre-fee CP curve arithmetic. Fee-aware executable quotes remain the SDK's job.
        buy_quote=effective*(math.sqrt(1+change)-1)
        sell_base=base*(1/math.sqrt(1-change)-1)
        gross_sell_quote=effective*(1-math.sqrt(1-change))
        rows.append({'marginal_price_change_fraction':change,'buy_quote_before_fees_raw':buy_quote,
            'sell_base_before_fees_raw':sell_base,'gross_sell_quote_before_fees_raw':gross_sell_quote,
            'real_quote_capacity_raw':real,'gross_sell_exceeds_real_quote':gross_sell_quote>real})
    return rows


def from_probe(probe, output):
    source=json.loads(probe.read_text())
    results=[]
    for row in source['results']:
        state=row['pool_state']
        bands=depth_bands(int(state['base_reserve']),int(state['quote_vault']),int(state['virtual_quote_reserves']),int(state['protocol_fee_bucket'])+int(state['creator_fee_bucket']))
        results.append({'mint':row['mint'],'pool':row['pool_address'],'bands':bands})
    result={'status':'structural pre-fee AMM depth diagnostic, not bids/asks, not quote fills or new demand information',
        'source_quote_probe':str(probe),'source_completed_at_utc':source['completed_at_utc'],
        'findings':['a plain constant-product curve has no resting-order cancellation or queue imbalance',
            'curve depth is a deterministic function of already-observed reserves',
            'pool vault minus accrued fee buckets limits real quote recovery; effective pricing reserves are different',
            'do not apply this formula to Raydium CLMM total TVL or reinterpret it as human bid walls'],
        'results':results}
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'pools':len(results),'status':result['status']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('probe',type=pathlib.Path);p.add_argument('--output',type=pathlib.Path,required=True)
    a=p.parse_args();from_probe(a.probe,a.output)
