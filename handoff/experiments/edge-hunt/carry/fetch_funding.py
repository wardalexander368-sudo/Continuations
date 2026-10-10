"""Fetch full SOL perp funding histories from free public APIs into data/<venue>.csv (time_ms, rate_per_interval, interval_h)."""
import sys, json, time, csv, requests, os
OUT = sys.argv[1]
S = requests.Session()
NOW = int(time.time()*1000)

def save(name, rows):
    rows = sorted(set(rows))
    with open(os.path.join(OUT, name + '.csv'), 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['t_ms', 'rate', 'interval_h']); w.writerows(rows)
    if rows:
        print(f"{name}: {len(rows)} rows {time.strftime('%Y-%m-%d', time.gmtime(rows[0][0]/1000))} .. {time.strftime('%Y-%m-%d %H:%M', time.gmtime(rows[-1][0]/1000))}", flush=True)
    else:
        print(name, 'EMPTY', flush=True)

def hyperliquid():
    rows, start = [], 0
    while True:
        r = S.post('https://api.hyperliquid.xyz/info', json={'type': 'fundingHistory', 'coin': 'SOL', 'startTime': start}, timeout=30).json()
        if not r: break
        rows += [(int(x['time']), float(x['fundingRate']), 1) for x in r]
        start = int(r[-1]['time']) + 1
        if start > NOW - 3600*1000: break
        time.sleep(0.3)
    save('hyperliquid', rows)

def bitmex():
    rows, start = [], 0
    while True:
        r = S.get('https://www.bitmex.com/api/v1/funding', params={'symbol': 'SOLUSDT', 'count': 500, 'start': start, 'reverse': 'false'}, timeout=30).json()
        if not r: break
        for x in r:
            t = int(time.mktime(time.strptime(x['timestamp'][:19], '%Y-%m-%dT%H:%M:%S')) - time.timezone) * 1000
            rows.append((t, float(x['fundingRate']), 8))
        start += len(r)
        if len(r) < 500: break
        time.sleep(1.2)
    save('bitmex', rows)

def okx():
    rows, after = [], None
    for _ in range(200):
        p = {'instId': 'SOL-USDT-SWAP', 'limit': 100}
        if after: p['after'] = after
        r = S.get('https://www.okx.com/api/v5/public/funding-rate-history', params=p, timeout=30).json()['data']
        if not r: break
        rows += [(int(x['fundingTime']), float(x['realizedRate'] or x['fundingRate']), 8) for x in r]
        after = r[-1]['fundingTime']
        time.sleep(0.25)
    save('okx', rows)

def mexc():
    rows, page = [], 1
    while True:
        r = S.get('https://contract.mexc.com/api/v1/contract/funding_rate/history', params={'symbol': 'SOL_USDT', 'page_num': page, 'page_size': 100}, timeout=30).json()['data']
        rows += [(int(x['settleTime']), float(x['fundingRate']), int(x.get('collectCycle', 8))) for x in r['resultList']]
        if page >= r['totalPage']: break
        page += 1; time.sleep(0.2)
    save('mexc', rows)

def gate():
    rows, to = [], None
    for _ in range(100):
        p = {'contract': 'SOL_USDT', 'limit': 1000}
        if to: p['to'] = to
        r = S.get('https://api.gateio.ws/api/v4/futures/usdt/funding_rate', params=p, timeout=30).json()
        if not r: break
        new = [(int(x['t'])*1000, float(x['r']), 8) for x in r]
        if rows and min(new)[0] >= min(rows)[0]: break
        rows += new
        to = min(x['t'] for x in r) - 1
        time.sleep(0.3)
    save('gate', rows)

def dydx():
    rows, before = [], None
    for _ in range(200):
        p = {'limit': 100}
        if before: p['effectiveBeforeOrAt'] = before
        r = S.get('https://indexer.dydx.trade/v4/historicalFunding/SOL-USD', params=p, timeout=30).json()['historicalFunding']
        if not r: break
        for x in r:
            t = int(time.mktime(time.strptime(x['effectiveAt'][:19], '%Y-%m-%dT%H:%M:%S')) - time.timezone) * 1000
            rows.append((t, float(x['rate']), 1))
        before = r[-1]['effectiveAt'].replace('00.', '00.') 
        # step back one ms
        last = min(rows)[0] - 1000
        before = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(last/1000))
        if len(r) < 100: break
        time.sleep(0.15)
    save('dydx', rows)

def deribit():
    rows, end = [], NOW
    for _ in range(200):
        st = end - 30*86400*1000
        r = S.get('https://www.deribit.com/api/v2/public/get_funding_rate_history', params={'instrument_name': 'SOL_USDC-PERPETUAL', 'start_timestamp': st, 'end_timestamp': end}, timeout=30).json().get('result', [])
        if not r: break
        rows += [(int(x['timestamp']), float(x['interest_1h']), 1) for x in r]
        end = st
        time.sleep(0.2)
    save('deribit', rows)

def kucoin():
    rows, to = [], NOW
    for _ in range(100):
        fr = to - 100*8*3600*1000
        r = S.get('https://api-futures.kucoin.com/api/v1/contract/funding-rates', params={'symbol': 'SOLUSDTM', 'from': fr, 'to': to}, timeout=30).json().get('data', [])
        if not r: break
        rows += [(int(x['timepoint']), float(x['fundingRate']), 8) for x in r]
        to = fr
        time.sleep(0.3)
    save('kucoin', rows)

def bitget():
    rows, page = [], 1
    for page in range(1, 200):
        r = S.get('https://api.bitget.com/api/v2/mix/market/history-fund-rate', params={'symbol': 'SOLUSDT', 'productType': 'usdt-futures', 'pageSize': 100, 'pageNo': page}, timeout=30).json().get('data', [])
        if not r: break
        rows += [(int(x['fundingTime']), float(x['fundingRate']), 8) for x in r]
        time.sleep(0.2)
    save('bitget', rows)

for f in sys.argv[2:]:
    try: globals()[f]()
    except Exception as e: print(f, 'ERROR', repr(e)[:300], flush=True)
