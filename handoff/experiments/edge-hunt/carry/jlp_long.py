import sys, os, json, pandas as pd, numpy as np
D = sys.argv[1]
px = json.load(open(os.path.join(D, 'llama_px.json')))
S = {}
for k, rows in px.items():
    s = pd.Series({pd.Timestamp(r['timestamp'], unit='s').normalize(): r['price'] for r in rows}).sort_index()
    S[k] = s[~s.index.duplicated(keep='last')]
P = pd.DataFrame(S).dropna()
# precision check: share of JLP prices with <=2 decimals
dec2 = P['JLP'].apply(lambda v: abs(v*100 - round(v*100)) < 1e-9)
print('JLP rows with <=2 decimals by year:', dec2.groupby(P.index.year).mean().round(2).to_dict())
R = np.log(P[['JLP', 'SOL', 'ETH', 'BTC']]).diff().dropna()
fund = {}
for c, fn in (('SOL', 'hyperliquid.csv'), ('ETH', 'hl_ETH.csv'), ('BTC', 'hl_BTC.csv')):
    h = pd.read_csv(os.path.join(D, fn)); h['d'] = pd.to_datetime(h.t_ms, unit='ms').dt.normalize(); fund[c] = h.groupby('d')['rate'].sum()
L = 60; res = []
for i in range(L, len(R)):
    w = R.iloc[i-L:i]; X = np.c_[np.ones(L), w[['SOL','ETH','BTC']].values]
    b = np.linalg.lstsq(X, w['JLP'].values, rcond=None)[0][1:]
    x = R.iloc[i]; d = R.index[i]
    fr = sum(b[k] * fund[c].get(d, np.nan) for k, c in enumerate(('SOL','ETH','BTC')))
    res.append((d, x['JLP'] - b @ x[['SOL','ETH','BTC']].values, fr, *b))
H = pd.DataFrame(res, columns=['d','hedged','fund','bS','bE','bB']).set_index('d')
H['total'] = H.hedged + H.fund.fillna(0)
q = H.groupby(H.index.to_period('Q'))
print(pd.DataFrame({'hedged_px_APR': q.hedged.mean()*36500, 'hedge_funding_APR': q.fund.mean()*36500, 'total_APR': q.total.mean()*36500,
                    'raw_JLP_APR': R['JLP'].groupby(R.index.to_period('Q')).mean().reindex(q.size().index)*36500,
                    'SOL_ret_APR': R['SOL'].groupby(R.index.to_period('Q')).mean().reindex(q.size().index)*36500,
                    'bSOL': q.bS.mean(), 'bBTC': q.bB.mean(), 'std_d%': q.hedged.std()*100, 'n': q.size()}).round(2).to_string())
for name, sub in (('all', H), ('2024', H[H.index.year == 2024]), ('2025', H[H.index.year == 2025]), ('2026', H[H.index.year == 2026])):
    x = sub.total.values; n = len(x); rng = np.random.default_rng(3); B = 20
    bs = [x[np.concatenate([np.arange(s, s+B) % n for s in rng.integers(0, n, n//B+1)])[:n]].mean()*36500 for _ in range(3000)]
    print(f'{name}: total hedged JLP APR {x.mean()*36500:.1f} [90% {np.percentile(bs,5):.1f}, {np.percentile(bs,95):.1f}] n={n}; worst day {x.min()*100:.2f}%; worst 30d {pd.Series(x).rolling(30).sum().min()*100:.2f}%')
# JitoSOL vs SOL realized yield (price ratio), incl. depeg
jr = np.log(P['JITOSOL'] / P['SOL'])
print('\nJitoSOL/SOL realized APR by year (price ratio, DefiLlama):', (jr.diff().groupby(P.index.year).mean()*36500).round(2).to_dict())
print('JitoSOL/SOL daily ratio-change std (bps):', round(jr.diff().std()*1e4, 1), ' worst day (bps):', round(jr.diff().min()*1e4, 1), jr.diff().idxmin().date())
H.to_csv('jlp_hedged_daily.csv')
