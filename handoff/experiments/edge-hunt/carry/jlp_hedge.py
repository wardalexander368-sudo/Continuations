import sys, os, json, pandas as pd, numpy as np
D, W = sys.argv[1], sys.argv[2]
g = json.load(open(os.path.join(D, "gt_jlp_day.json")))
o = g['data']['attributes']['ohlcv_list']; meta = g['meta']
print('JLP pool base/quote:', meta.get('base', {}).get('symbol'), meta.get('quote', {}).get('symbol'), 'rows', len(o))
jlp = pd.Series({pd.Timestamp(x[0], unit='s').normalize(): x[4] for x in o}).sort_index()
cg = json.load(open(os.path.join(D, 'cg_jlp.json')))['prices']
cgs = pd.Series({pd.Timestamp(t, unit='ms').normalize(): p for t, p in cg}).sort_index()
both = pd.concat([jlp, cgs], axis=1).dropna(); print('GT vs CG JLP close, median abs diff %:', round(((both[0]/both[1]-1).abs().median()*100), 3), 'n', len(both))
px = {}
for a in ('ETH-USD', 'BTC-USD'):
    r = json.load(open(os.path.join(D, f'cb_{a}.json')))
    px[a[:3]] = pd.Series({pd.Timestamp(x[0], unit='s').normalize(): x[4] for x in r}).sort_index()
sol = pd.read_csv(os.path.join(D, 'px_sol.csv'), parse_dates=['date']).set_index('date')['close']
P = pd.DataFrame({'JLP': jlp, 'SOL': sol, 'ETH': px['ETH'], 'BTC': px['BTC']}).dropna()
R = np.log(P).diff().dropna()
print('days with all prices', len(R), R.index.min().date(), R.index.max().date())
# causal rolling 60d OLS betas, hedge next day
betas = []; res = []
for i in range(60, len(R)):
    w = R.iloc[i-60:i]; X = np.c_[np.ones(60), w[['SOL', 'ETH', 'BTC']].values]
    b = np.linalg.lstsq(X, w['JLP'].values, rcond=None)[0][1:]
    x = R.iloc[i]
    res.append((R.index[i], x['JLP'] - b @ x[['SOL', 'ETH', 'BTC']].values, *b))
H = pd.DataFrame(res, columns=['date', 'hedged', 'bSOL', 'bETH', 'bBTC']).set_index('date')
f = pd.read_csv(os.path.join(W, 'daily_funding.csv'), index_col=0, parse_dates=True); f.index = f.index.tz_localize(None).normalize()
# funding received on shorts: approximate ETH/BTC funding by SOL HL funding (not available here) -> report hedged-price return separately
H['fund_sol'] = H['bSOL'] * f['hyperliquid'].reindex(H.index).fillna(0)
print('mean betas SOL/ETH/BTC:', H[['bSOL', 'bETH', 'bBTC']].mean().round(3).to_dict())
yr = H.groupby(H.index.year)
print(pd.DataFrame({'hedged_price_APR': yr['hedged'].mean()*36500, 'raw_JLP_APR': R['JLP'].groupby(R.index.year).mean()*36500,
                    'sol_fund_on_hedge_APR': yr['fund_sol'].mean()*36500, 'hedged_daily_std_pct': yr['hedged'].std()*100, 'days': yr.size()}).round(2).to_string())
x = H['hedged'].values; n = len(x); rng = np.random.default_rng(1); B = 20
bs = [x[np.concatenate([np.arange(s, s+B) % n for s in rng.integers(0, n, n//B+1)])[:n]].mean()*36500 for _ in range(4000)]
print('hedged price return APR all: %.1f, 90%% CI %.1f..%.1f' % (x.mean()*36500, *np.percentile(bs, [5, 95])))
print('worst hedged day %.2f%% on %s; worst 30d sum %.2f%%' % (H.hedged.min()*100, H.hedged.idxmin().date(), H.hedged.rolling(30).sum().min()*100))
