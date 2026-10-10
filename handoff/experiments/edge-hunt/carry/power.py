import sys, os, json, pandas as pd, numpy as np
D, W = sys.argv[1], sys.argv[2]
c = pd.read_csv(os.path.join(W, 'carry_daily.csv'), index_col=0, parse_dates=True)
cap = 1 + 1/3
# Hedged JLP (CoinGecko 365d) rebuilt here
cg = json.load(open(os.path.join(D, 'cg_jlp.json')))['prices']
jlp = pd.Series({pd.Timestamp(t, unit='ms').normalize(): p for t, p in cg}).sort_index(); jlp = jlp[~jlp.index.duplicated(keep='last')]; jlp.index = jlp.index - pd.Timedelta(days=1)
px = {}
for a in ('ETH-USD', 'BTC-USD'):
    r = json.load(open(os.path.join(D, f'cb_{a}.json'))); s = pd.Series({pd.Timestamp(x[0], unit='s').normalize(): x[4] for x in r}).sort_index(); px[a[:3]] = s[~s.index.duplicated()]
sol = pd.read_csv(os.path.join(D, 'px_sol.csv'), parse_dates=['date']).set_index('date')['close']
P = pd.DataFrame({'JLP': jlp, 'SOL': sol, 'ETH': px['ETH'], 'BTC': px['BTC']}).dropna(); R = np.log(P).diff().dropna()
fund = {}
for cc, fn in (('SOL', 'hyperliquid.csv'), ('ETH', 'hl_ETH.csv'), ('BTC', 'hl_BTC.csv')):
    h = pd.read_csv(os.path.join(D, fn)); h['d'] = pd.to_datetime(h.t_ms, unit='ms').dt.normalize(); fund[cc] = h.groupby('d')['rate'].sum()
res = []
for i in range(60, len(R)):
    w = R.iloc[i-60:i]; X = np.c_[np.ones(60), w[['SOL','ETH','BTC']].values]; b = np.linalg.lstsq(X, w['JLP'].values, rcond=None)[0][1:]
    x = R.iloc[i]; d = R.index[i]
    res.append((d, x['JLP'] - b @ x[['SOL','ETH','BTC']].values + sum(b[k]*fund[cc].get(d, 0) for k, cc in enumerate(('SOL','ETH','BTC'))), b.sum()))
H = pd.DataFrame(res, columns=['d', 'total', 'bsum']).set_index('d')
H['cap'] = 1 + H.bsum / 3  # HL margin at 3x on hedge notional
H['usdc'] = c['usdc'].reindex(H.index).ffill()
H['excess'] = H.total / H.cap - H.usdc
print('Hedged JLP per capital: APR %.1f, USDC %.1f, excess %.1f (n=%d, %s..%s)' % (H.total.div(H.cap).mean()*36500, H.usdc.mean()*36500, H.excess.mean()*36500, len(H), H.index.min().date(), H.index.max().date()))
print('Hedged JLP daily excess std %.3f%%; lag-1 autocorr %.2f' % (H.excess.std()*100, H.excess.autocorr(1)))
for win in (30, 60, 90):
    rr = H.excess.rolling(win).mean()*36500
    print(f'  JLP {win}d windows: share excess>0 {(rr.dropna()>0).mean():.2f}; median {rr.median():.1f}; 10th pct {rr.quantile(.1):.1f}')
c['excess'] = c['carry_hl']/cap - c['usdc']
print('\nLST carry (JitoSOL + HL short, 3x) daily excess std %.3f%%, lag-1 autocorr %.2f' % (c.excess.std()*100, c.excess.autocorr(1)))
for per, sub in (('2025-01..', c[c.index >= '2025-01-01']), ('last 365d', c[c.index >= c.index.max() - pd.Timedelta(days=365)])):
    for win in (30, 60, 90):
        rr = sub.excess.rolling(win).mean()*36500
        print(f'  LST carry {per} {win}d windows: share excess>0 {(rr.dropna()>0).mean():.2f}; median {rr.median():.1f}; 10th pct {rr.quantile(.1):.1f}')
last = c[c.index >= c.index.max() - pd.Timedelta(days=90)]
print('LST carry last 90d: carry/capital APR %.1f, USDC %.1f, excess %.1f; last 30d excess %.1f' % (last.carry_hl.mean()/cap*36500, last.usdc.mean()*36500, last.excess.mean()*36500, c.excess.iloc[-30:].mean()*36500))
# conditional: does trailing-30d excess predict next-60d excess sign? (LST carry, full sample)
tr = c.excess.rolling(30).mean(); nx = c.excess[::-1].rolling(60).mean()[::-1].shift(-1)
d = pd.DataFrame({'tr': tr, 'nx': nx}).dropna().iloc[::30]
print('LST carry: P(next60 excess>0 | trailing30 excess>0) = %.2f (n=%d); unconditional %.2f' % ((d[d.tr > 0].nx > 0).mean(), (d.tr > 0).sum(), (d.nx > 0).mean()))
