import sys, os, pandas as pd, numpy as np
D, W = sys.argv[1], sys.argv[2]
f = pd.read_csv(os.path.join(W, 'daily_funding.csv'), index_col=0, parse_dates=True)
f.index = f.index.tz_localize(None).normalize()
jito = pd.read_csv(os.path.join(D, 'jito_apy.csv'), parse_dates=['date']).set_index('date')['apy']
k = {s: pd.read_csv(os.path.join(D, f'kamino_{s}.csv'), parse_dates=['date']).set_index('date') for s in ('SOL', 'USDC', 'JITOSOL')}
df = pd.DataFrame({'hl': f['hyperliquid'], 'deribit': f['deribit'], 'kucoin': f['kucoin'], 'gate': f['gate'],
                   'jito': jito.groupby(jito.index.normalize()).last(),
                   'usdc_sup': k['USDC']['supply_apy'], 'usdc_bor': k['USDC']['borrow_apy'],
                   'sol_bor': k['SOL']['borrow_apy'], 'sol_sup': k['SOL']['supply_apy']})
df = df[(df.index >= '2023-10-13') & (df.index < '2026-10-09')]
df['jito'] = df['jito'].ffill()
df = df.dropna(subset=['hl', 'jito', 'usdc_sup'])
print('days', len(df), df.index.min().date(), df.index.max().date())
# daily returns (fraction) per unit notional
for v in ('hl', 'deribit', 'kucoin', 'gate'):
    df[f'carry_{v}'] = df['jito'] / 365 + df[v]
df['usdc'] = df['usdc_sup'] / 365
LEV = 3.0  # HL short leverage -> extra margin 1/LEV of notional
cap = 1 + 1 / LEV
df['carry_hl_cap'] = df['carry_hl'] / cap
df['excess_hl_cap'] = df['carry_hl_cap'] - df['usdc']
def ann(s): return s.mean() * 365 * 100
g = df.groupby(df.index.year)
out = pd.DataFrame({'jito_apy': g['jito'].mean()*100, 'hl_fund': g['hl'].mean()*36500, 'deribit_fund': g['deribit'].mean()*36500,
                    'kucoin_fund': g['kucoin'].mean()*36500, 'usdc_sup': g['usdc_sup'].mean()*100, 'sol_borrow': g['sol_bor'].mean()*100,
                    'carry_hl_notional': g['carry_hl'].mean()*36500, 'carry_hl_per_capital(3x)': g['carry_hl_cap'].mean()*36500,
                    'excess_vs_usdc': g['excess_hl_cap'].mean()*36500, 'days': g.size()}).round(2)
print(out.to_string())
print('\nWhole period APR: carry_hl/capital %.2f  usdc %.2f  excess %.2f' % (ann(df.carry_hl_cap), ann(df.usdc), ann(df.excess_hl_cap)))
# block bootstrap 90% CI for excess (30-day blocks)
rng = np.random.default_rng(0); x = df['excess_hl_cap'].values; n = len(x); B = 30
bs = []
for _ in range(4000):
    idx = np.concatenate([np.arange(s, s + B) % n for s in rng.integers(0, n, n // B + 1)])[:n]
    bs.append(x[idx].mean() * 36500)
print('excess 90%% CI (30d block bootstrap): %.2f .. %.2f' % tuple(np.percentile(bs, [5, 95])))
# worst 30-day and 90-day windows of excess (APR)
r30 = df['excess_hl_cap'].rolling(30).mean() * 36500; r90 = df['excess_hl_cap'].rolling(90).mean() * 36500
print('worst 30d excess APR %.1f (%s); worst 90d %.1f (%s)' % (r30.min(), r30.idxmin().date(), r90.min(), r90.idxmin().date()))
print('share of 30d windows with excess<0: %.2f' % (r30.dropna() < 0).mean())
# LST loop spread: jito apy - kamino SOL borrow
df['loop_spread'] = df['jito'] - df['sol_bor']
print('\nLST loop spread (JitoSOL APY - Kamino SOL borrow APY), by year mean %, share of days > 0:')
print(pd.DataFrame({'mean': g['jito'].mean()*100 - g['sol_bor'].mean()*100, 'pos_days': df.groupby(df.index.year)['loop_spread'].apply(lambda s: (s > 0).mean())}).round(3).to_string())
df.to_csv(os.path.join(W, 'carry_daily.csv'))
