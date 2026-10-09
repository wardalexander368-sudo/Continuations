import sys, os, json, pandas as pd, numpy as np
D, W = sys.argv[1], sys.argv[2]
c = pd.read_csv(os.path.join(W, 'carry_daily.csv'), index_col=0, parse_dates=True)
f = pd.read_csv(os.path.join(W, 'daily_funding.csv'), index_col=0, parse_dates=True); f.index = f.index.tz_localize(None).normalize()
cap = 1 + 1/3
def bci(x, B=30, seed=0):
    x = np.asarray(x); n = len(x); rng = np.random.default_rng(seed)
    bs = [x[np.concatenate([np.arange(s, s+B) % n for s in rng.integers(0, n, n//B+1)])[:n]].mean()*36500 for _ in range(3000)]
    return np.percentile(bs, [5, 95])
for lb in (7, 30):
    c[f'tr{lb}'] = f['hyperliquid'].rolling(lb).mean().reindex(c.index) * 36500
def rule(sub, thr, lb, cost_bps=10):
    on = (sub[f'tr{lb}'].shift(1) > thr).astype(int); sw = on.diff().abs().fillna(on.iloc[0])
    r = np.where(on == 1, sub['carry_hl'] / cap, sub['usdc']) - sw * cost_bps / 2 / 1e4
    return pd.Series(r - sub['usdc'].values, index=sub.index)
train = c[c.index < '2025-07-01']; test = c[c.index >= '2025-07-01']
grid = [(thr, lb) for thr in (-1e9, 0, 5, 10, 15, 20) for lb in (7, 30)]
tr_res = {g: rule(train, *g).mean()*36500 for g in grid}
best = max(tr_res, key=tr_res.get)
print('LST carry regime rule: train (2023-10..2025-06) excess APR by (thr, lookback):', {k: round(v, 2) for k, v in tr_res.items()})
te = rule(test, *best)
print(f'chosen on train {best}: test (2025-07..2026-10) excess APR {te.mean()*36500:.2f} CI {bci(te).round(2)}; always-on test {rule(test, -1e9, 7).mean()*36500:.2f}; n={len(te)}')
for g in grid: print('   test', g, round(rule(test, *g).mean()*36500, 2))
# Hedged JLP halves + CI
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
    res.append((d, x['JLP'] - b @ x[['SOL','ETH','BTC']].values, sum(b[k]*fund[cc].get(d, 0) for k, cc in enumerate(('SOL','ETH','BTC'))), b.sum()))
H = pd.DataFrame(res, columns=['d', 'hedged', 'fund', 'bsum']).set_index('d')
H['ex'] = (H.hedged + H.fund) / (1 + H.bsum/3) - c['usdc'].reindex(H.index).ffill()
# fixed-weight hedge alternative (pool target weights SOL .47 ETH .08 BTC .13) - no estimation
H['fixed'] = R['JLP'].reindex(H.index) - (0.47*R['SOL'] + 0.08*R['ETH'] + 0.13*R['BTC']).reindex(H.index)
n = len(H); h1, h2 = H.iloc[:int(n*0.6)], H.iloc[int(n*0.6):]
print(f'\nHedged JLP excess over USDC per capital: all {H.ex.mean()*36500:.1f} CI {bci(H.ex, 20).round(1)} n={n}; first 60% {h1.ex.mean()*36500:.1f} ({h1.index.min().date()}..{h1.index.max().date()}); last 40% {h2.ex.mean()*36500:.1f} CI {bci(h2.ex, 20).round(1)}')
print(f'Fixed target-weight hedge (no funding), hedged price APR: all {H.fixed.mean()*36500:.1f}, first 60% {h1.fixed.mean()*36500:.1f}, last 40% {h2.fixed.mean()*36500:.1f}; daily std {H.fixed.std()*100:.2f}%')
print('Mean hedge funding received on JLP hedge (APR on JLP notional): %.2f' % (H.fund.mean()*36500))
