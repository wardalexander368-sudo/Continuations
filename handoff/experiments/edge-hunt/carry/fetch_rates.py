import sys, json, time, requests, datetime as dt, csv, os
OUT = sys.argv[1]; S = requests.Session()
M = '7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF'
RES = {'SOL': 'd4A2prbA2whesmvHaL88BH6Ewn5N4bTSU2Ze8P6Bc4Q', 'USDC': 'D6q6wuQSrifJKZYpR1M8R4YawnLDtDsMmWM1NbBmgJ59', 'JITOSOL': 'EVbyPKrHG6WBfm4dLxLMJpUDY43cCAcHSpV3KYjKsktW'}
def kamino(sym, rid):
    rows = []; s = dt.datetime(2023, 9, 1)
    end = dt.datetime(2026, 10, 9)
    while s < end:
        e = min(s + dt.timedelta(days=90), end)
        r = S.get(f'https://api.kamino.finance/kamino-market/{M}/reserves/{rid}/metrics/history', params={'env': 'mainnet-beta', 'start': s.strftime('%Y-%m-%dT00:00Z'), 'end': e.strftime('%Y-%m-%dT00:00Z'), 'frequency': 'day'}, timeout=60)
        if r.status_code == 200:
            for h in r.json().get('history', []):
                m = h['metrics']
                rows.append((h['timestamp'][:10], m.get('borrowInterestAPY'), m.get('supplyInterestAPY'), m.get('utilizationRatio'), m.get('assetPriceUSD')))
        else:
            print(sym, s, r.status_code, r.text[:100])
        s = e; time.sleep(0.5)
    with open(os.path.join(OUT, f'kamino_{sym}.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['date', 'borrow_apy', 'supply_apy', 'util', 'px']); w.writerows(rows)
    print(f'kamino {sym}: {len(rows)} rows {rows[0][0] if rows else None}..{rows[-1][0] if rows else None}', flush=True)
def jito():
    r = S.post('https://kobe.mainnet.jito.network/api/v1/stake_pool_stats', json={'bucket_type': 'Daily', 'range_filter': {'start': '2022-11-01T00:00:00Z', 'end': '2026-10-09T23:00:00Z'}, 'sort_by': {'field': 'BlockTime', 'order': 'Asc'}}, timeout=60).json()
    rows = [(a['date'][:10], a['data']) for a in r['apy']]
    with open(os.path.join(OUT, 'jito_apy.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['date', 'apy']); w.writerows(rows)
    print(f'jito apy: {len(rows)} rows {rows[0][0]}..{rows[-1][0]}', flush=True)
def coinbase():
    rows = []; end = int(time.time())
    for _ in range(8):
        st = end - 300*86400
        r = S.get('https://api.exchange.coinbase.com/products/SOL-USD/candles', params={'granularity': 86400, 'start': dt.datetime.utcfromtimestamp(st).isoformat(), 'end': dt.datetime.utcfromtimestamp(end).isoformat()}, timeout=30).json()
        rows += [(dt.datetime.utcfromtimestamp(x[0]).strftime('%Y-%m-%d'), x[4]) for x in r]
        end = st; time.sleep(0.4)
    rows = sorted(set(rows))
    with open(os.path.join(OUT, 'px_sol.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['date', 'close']); w.writerows(rows)
    print(f'coinbase SOL: {len(rows)} rows {rows[0][0]}..{rows[-1][0]}', flush=True)
for a in sys.argv[2:]:
    try:
        if a == 'kamino':
            for k, v in RES.items(): kamino(k, v)
        else: globals()[a]()
    except Exception as e: print(a, 'ERROR', repr(e)[:300])
