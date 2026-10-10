import sys, os, pandas as pd, numpy as np
W = sys.argv[1]
f = pd.read_csv(os.path.join(W, 'daily_funding.csv'), index_col=0, parse_dates=True); f.index = f.index.tz_localize(None).normalize()
f = f[f.index < '2026-10-09']
COST = 12e-4  # 4 perp fills x 3 bps per round trip (open+close both legs)
CAP = 2/3     # margin on both venues at 3x: 1/3 + 1/3 of notional
def run(other, thr, start, end, lb=14):
    s = (f['hyperliquid'] - f[other]).dropna()
    tr = s.rolling(lb).mean() * 36500
    wk = s.index[(s.index >= start) & (s.index < end)][::7]
    pnl = []; on_prev = 0; sgn_prev = 0
    for d0 in wk:
        t = tr.get(d0 - pd.Timedelta(days=1), np.nan)
        if np.isnan(t): continue
        sgn = 1 if t > thr else (-1 if t < -thr else 0)   # +1: short HL / long other
        seg = s[(s.index >= d0) & (s.index < d0 + pd.Timedelta(days=7))]
        r = sgn * seg.sum() - (COST if sgn != sgn_prev and sgn != 0 else 0) - (COST/2 if sgn_prev != 0 and sgn != sgn_prev else 0) * 0
        pnl.append(r); sgn_prev = sgn
    p = np.array(pnl)
    return p.sum() / (len(p) * 7) * 365 / CAP * 100 if len(p) else np.nan, (p != 0).mean() if len(p) else 0, len(p)
print('APR on capital (both venues margined at 3x), weekly rebalanced, trailing-14d spread rule')
for o in ('dydx', 'deribit', 'kucoin', 'gate', 'mexc'):
    rows = []
    for thr in (0, 5, 10, 20):
        tr_ = run(o, thr, '2023-01-01', '2025-07-01'); te = run(o, thr, '2025-07-01', '2026-10-09')
        rows.append((thr, round(tr_[0], 2), tr_[2], round(te[0], 2), te[2]))
    best = max(rows, key=lambda r: (r[1] if not np.isnan(r[1]) else -1e9))
    print(f'HL vs {o}: (thr, train APR, weeks, test APR, weeks) {rows}  -> chosen on train thr={best[0]}: test {best[3]}')
