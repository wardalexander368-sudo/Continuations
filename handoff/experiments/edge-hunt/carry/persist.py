import sys, os, pandas as pd, numpy as np
W = sys.argv[1]
df = pd.read_csv(os.path.join(W, 'carry_daily.csv'), index_col=0, parse_dates=True)
f = pd.read_csv(os.path.join(W, 'daily_funding.csv'), index_col=0, parse_dates=True); f.index = f.index.tz_localize(None).normalize()
# HL hourly: share of hours at exactly the 0.00125% floor
h = pd.read_csv(os.path.join(sys.argv[2], 'hyperliquid.csv')); h['t'] = pd.to_datetime(h.t_ms, unit='ms')
h['yr'] = h.t.dt.year
print('HL share of hours with funding == 0.0000125 (interest floor):'); print(h.groupby('yr')['rate'].apply(lambda r: np.isclose(r, 1.25e-5, atol=1e-9).mean()).round(3).to_string())
print('HL share of hours with funding < 0:'); print(h.groupby('yr')['rate'].apply(lambda r: (r < 0).mean()).round(3).to_string())
# Persistence: trailing L-day mean vs next H-day mean (non-overlapping H blocks)
hl = f['hyperliquid'].dropna()
for L, H in ((7, 7), (7, 30), (30, 30)):
    tr = hl.rolling(L).mean(); nx = hl[::-1].rolling(H).mean()[::-1].shift(-1)
    d = pd.DataFrame({'tr': tr, 'nx': nx}).dropna().iloc[::H]
    print(f'HL trailing {L}d vs next {H}d (non-overlapping, n={len(d)}): corr {d.corr().iloc[0,1]:.2f}, slope {np.polyfit(d.tr, d.nx, 1)[0]:.2f}')
# Regime rule on carry: in carry when trailing-7d HL funding APR > thr, else USDC. costs 10 bps per switch round trip
x = df.copy(); cap = 1 + 1/3
x['tr7'] = f['hyperliquid'].rolling(7).mean().reindex(x.index) * 36500
def rule(thr, cost_bps=10):
    on = (x['tr7'].shift(1) > thr).astype(int)  # decide with data up to yesterday
    sw = on.diff().abs().fillna(on.iloc[0])
    r = np.where(on == 1, x['carry_hl'] / cap, x['usdc']) - sw * cost_bps / 2 / 1e4
    return pd.Series(r, index=x.index), on.mean(), sw.sum()
print('\nRegime rule (carry if trailing-7d HL funding APR > thr else Kamino USDC), APR by year; always-carry and always-USDC for reference')
rows = {}
for thr in (-1000, 0, 5, 10, 20):
    r, frac, nsw = rule(thr)
    rows[f'thr {thr}'] = list((r.groupby(r.index.year).mean()*36500).round(2)) + [round(frac, 2), int(nsw)]
rows['usdc'] = list((x['usdc'].groupby(x.index.year).mean()*36500).round(2)) + [0, 0]
print(pd.DataFrame(rows, index=[*sorted(set(x.index.year)), 'frac_on', 'switches']).T.to_string())
# Cross-venue dispersion: HL minus others (daily APR), means by year; persistence of spread
others = ['deribit', 'kucoin', 'gate', 'dydx', 'mexc', 'bitmex']
sp = pd.DataFrame({o: (f['hyperliquid'] - f[o]) * 36500 for o in others})
print('\nHL minus venue funding (APR pts), yearly mean:'); print(sp.groupby(sp.index.year).mean().round(1).to_string())
print('daily std of spread (APR pts):'); print(sp.std().round(1).to_string())
for o in ('deribit', 'kucoin', 'gate'):
    s = sp[o].dropna(); tr = s.rolling(7).mean(); nx = s[::-1].rolling(7).mean()[::-1].shift(-1)
    d = pd.DataFrame({'tr': tr, 'nx': nx}).dropna().iloc[::7]
    print(f'spread HL-{o}: trailing7 vs next7 corr {d.corr().iloc[0,1]:.2f}, n={len(d)}')
