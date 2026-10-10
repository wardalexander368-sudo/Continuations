import sys, pandas as pd, numpy as np, glob, os
D = sys.argv[1]
ser = {}
for f in sorted(glob.glob(os.path.join(D, '*.csv'))):
    n = os.path.basename(f)[:-4]
    if n.startswith('llama') or n.startswith('px'): continue
    d = pd.read_csv(f)
    d['t'] = pd.to_datetime(d.t_ms, unit='ms', utc=True)
    d = d.drop_duplicates('t').set_index('t').sort_index()
    # per-day sum of funding (fraction of notional received by a short)
    daily = d['rate'].resample('1D').sum(min_count=1)
    ser[n] = daily
df = pd.DataFrame(ser)
df = df[df.index < '2026-10-09']
print('Annualized mean funding received by a SHORT (% APR), by calendar year; n days')
yr = df.groupby(df.index.year)
tab = (yr.mean()*365*100).round(1)
cnt = yr.count()
print(tab.to_string())
print(cnt.to_string())
print('\nLast 90 days APR:'); print((df[df.index >= df.index.max()-pd.Timedelta(days=90)].mean()*365*100).round(2).to_string())
print('\nLast 30 days APR:'); print((df[df.index >= df.index.max()-pd.Timedelta(days=30)].mean()*365*100).round(2).to_string())
# fraction of days negative
print('\nFraction of days with negative funding (short pays):'); print((df<0).sum().div(df.notna().sum()).round(3).to_string())
df.to_csv(os.path.join(sys.argv[2], 'daily_funding.csv'))
