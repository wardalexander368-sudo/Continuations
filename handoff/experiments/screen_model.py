import pickle, sys, numpy as np, warnings, lightgbm as lgb
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')
from tartar.profit import Costs, Exit, curves_for, run_policy, summarize, label_round_trips
ds = pickle.load(open(sys.argv[1], 'rb'))
S = int(sys.argv[2])
d = pickle.load(open(f'/tmp/tartar-exp/screen_rows_{S}.pkl', 'rb'))
rows, when = d['rows'], d['when']
curves = curves_for(ds.tokens)
K = np.array([r['k'] for r in rows]); P = np.array([r['part'] for r in rows])
cols = ['buyers','trades','buy_sol','sell_sol','rise','creator_sold','launches','rugs','drawdown','top10_share','log_holders','creator_share','sniper_share','wash_share','trades_per_wallet','nonstandard_curve']
X = np.array([[r[c] for c in cols] for r in rows], dtype=float)
lvl = {'unknown':0,'ok':1,'caution':2,'danger':3,'scam':4}
X = np.column_stack([X, [lvl[r['level']] for r in rows]]); cols.append('level')
costs = Costs()
def fmt(s): return f"n={s.trades:4d} mean {100*s.mean_ret:+6.2f}% [{100*s.ci_low:+6.2f},{100*s.ci_high:+6.2f}] win {100*s.win_rate:4.1f}% total {s.total_sol:+6.3f}"
for rule in (Exit(60), Exit(180), Exit(600), Exit(600, 1.0, 0.3), Exit(1800, 2.0, 0.4)):
    y = label_round_trips(curves, K, when, costs, rule)
    ok = ~np.isnan(y)
    print(f'=== {rule.label()}: label mean train {np.nanmean(y[P==0]):+.3f}; P(net>0) {np.mean(y[(P==0)&ok]>0):.3f}')
    for obj in ('binary', 'huber'):
        a, b = (P==0)&ok, (P==1)&ok
        tgt = (lambda m: (y[m]>0).astype(int)) if obj=='binary' else (lambda m: np.clip(y[m], -1, 3))
        params = dict(objective=obj, learning_rate=0.03, num_leaves=7, min_data_in_leaf=40, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=1)
        dtr = lgb.Dataset(X[a], tgt(a), feature_name=cols); dva = lgb.Dataset(X[b], tgt(b), reference=dtr)
        bst = lgb.train(params, dtr, 2000, valid_sets=[dva], callbacks=[lgb.early_stopping(100, verbose=False)])
        score = bst.predict(X, num_iteration=bst.best_iteration)
        best = None
        for q in (0.5, 0.7, 0.8, 0.9, 0.95):
            thr = np.quantile(score[P==1], q); sel = (P==1) & (score > thr)
            s = summarize(run_policy(curves, K[sel], when[sel], np.ones(sel.sum(), bool), costs, rule), costs, boot=1)
            if s.trades >= 20 and (best is None or s.total_sol > best[1]): best = (thr, s.total_sol, q)
        if best is None: print(f'  {obj}: nothing'); continue
        thr, _, q = best
        for name, code in (('valid', 1), ('test', 2)):
            sel = (P==code) & (score > thr)
            print(f'  {obj:6s} ({bst.best_iteration:4d} rounds, top {100*(1-q):.0f}%) {name:5s}', fmt(summarize(run_policy(curves, K[sel], when[sel], np.ones(sel.sum(), bool), costs, rule), costs, boot=1000)))

# robustness of the last binary config (hold 1800s, TP 200%, SL 40%)
rule = Exit(1800, 2.0, 0.4)
y = label_round_trips(curves, K, when, costs, rule); ok = ~np.isnan(y)
a, b = (P==0)&ok, (P==1)&ok
for seed in range(1, 6):
    params = dict(objective='binary', learning_rate=0.03, num_leaves=7, min_data_in_leaf=40, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=seed)
    dtr = lgb.Dataset(X[a], (y[a]>0).astype(int), feature_name=cols); dva = lgb.Dataset(X[b], (y[b]>0).astype(int), reference=dtr)
    bst = lgb.train(params, dtr, 2000, valid_sets=[dva], callbacks=[lgb.early_stopping(100, verbose=False)])
    score = bst.predict(X, num_iteration=bst.best_iteration)
    thr = np.quantile(score[P==1], 0.9)
    for code in (1, 2):
        sel = (P==code) & (score > thr)
        trades = run_policy(curves, K[sel], when[sel], np.ones(sel.sum(), bool), costs, rule)
        pnl = np.sort([t.pnl_sol for t in trades])[::-1]
        s = summarize(trades, costs, boot=1000)
        print(f'seed {seed} {"valid" if code==1 else "test "} {fmt(s)} censored {s.censored} reasons {s.reasons} | total w/o top1 {pnl[1:].sum():+.3f} w/o top3 {pnl[3:].sum():+.3f}')

from tartar.data.rawlog import raw_files, read_events
why = {e['mint']: e.get('reason') for e in read_events(raw_files('data/raw')) if e['e'] == 'untrack'}
params = dict(objective='binary', learning_rate=0.03, num_leaves=7, min_data_in_leaf=40, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=1)
dtr = lgb.Dataset(X[a], (y[a]>0).astype(int), feature_name=cols); dva = lgb.Dataset(X[b], (y[b]>0).astype(int), reference=dtr)
bst = lgb.train(params, dtr, 2000, valid_sets=[dva], callbacks=[lgb.early_stopping(100, verbose=False)])
score = bst.predict(X, num_iteration=bst.best_iteration); thr = np.quantile(score[P==1], 0.9)
import collections
for code in (1, 2):
    sel = (P==code) & (score > thr)
    trades = run_policy(curves, K[sel], when[sel], np.ones(sel.sum(), bool), costs, rule)
    groups = collections.defaultdict(list)
    for t in trades:
        g = 'not censored' if not t.censored else f"censored: {why.get(ds.tokens[t.token].mint) or 'recording cut'}"
        groups[g].append(t)
    for g, ts in groups.items():
        print(f'{"valid" if code==1 else "test "} {g:28s} {fmt(summarize(ts, costs, boot=500))}')
    big = sorted(trades, key=lambda t: -t.pnl_sol)[:3]
    print('   top trades:', [(round(t.pnl_sol/costs.size_sol, 2), t.reason, t.censored, why.get(ds.tokens[t.token].mint)) for t in big])
imp = sorted(zip(bst.feature_importance('gain'), cols), reverse=True)[:8]
print('importance:', [(c, round(float(v)/sum(x for x,_ in imp),2)) for v, c in imp])
