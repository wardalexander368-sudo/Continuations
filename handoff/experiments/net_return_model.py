import pickle, sys, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')
from tartar.profit import Costs, Exit, Curve, run_policy, summarize, label_round_trips
from tartar.model.engine import FEATURES
from tartar.model.global_model import find_model, EDGES
ds = pickle.load(open(sys.argv[1],'rb'))
curves = [Curve([t for g in tok.ticks.values() for t, _ in g]) for tok in ds.tokens]
tr, va, te = ds.split()
costs = Costs()
def show(name, trades):
    s = summarize(trades, costs)
    print(f'  {name:48s} n={s.trades:5d} tok={s.tokens:4d} mean {100*s.mean_ret:+6.2f}% [{100*s.ci_low:+6.2f},{100*s.ci_high:+6.2f}] P>0 {s.p_positive:.2f} win {100*s.win_rate:4.1f}% total {s.total_sol:+7.3f} SOL')
    return s
# v1 model expected-return score
m = find_model('trades', 60)
def exp_ratio(probs, s, tl=1.0, th=1.0):
    a = np.concatenate([[-np.inf], EDGES]); b = np.concatenate([EDGES, [np.inf]])
    out = probs[:,0].copy()
    for k in range(len(a)):
        p = probs[:,1+k]
        if k == 0: e = np.exp(s*b[k]) / (1 + s*tl)
        elif k == len(a)-1: e = np.exp(s*a[k]) / np.maximum(1 - s*th, 0.05)
        else: e = (np.exp(s*b[k]) - np.exp(s*a[k])) / (s*(b[k]-a[k]))
        out += p*e
    return out - 1
probs = m.predict_proba(ds.X)
er_v1 = exp_ratio(probs, ds.sigma*np.sqrt(1-ds.f), m.meta.get('tail_low',1), m.meta.get('tail_high',1))
p_up_v1 = 1 - probs[:,0] - (probs[:,1:13].sum(1))  # mass of z>0 bins
rules = [Exit(30), Exit(60), Exit(180), Exit(180, 0.5, 0.2), Exit(600, 1.0, 0.3)]
def pick_threshold(score, mask, rule, qs=(0.5,0.8,0.9,0.95,0.98,0.99,0.995)):
    best = None
    for q in qs:
        thr = np.quantile(score[mask], q)
        trades = run_policy(curves, ds.token[mask], ds.time[mask], score[mask] > thr, costs, rule)
        s = summarize(trades, costs, boot=200)
        if s.trades >= 30 and (best is None or s.total_sol > best[1]):
            best = (thr, s.total_sol, q)
    return best
for rule in rules:
    print(f'=== exit: {rule.label()}')
    y = label_round_trips(curves, ds.token, ds.time, costs, rule)
    ok = ~np.isnan(y)
    yc = np.clip(y, -1, 2)
    print(f'  label mean: train {np.nanmean(y[tr]):+.4f} valid {np.nanmean(y[va]):+.4f} test {np.nanmean(y[te]):+.4f}; P(net>0) train {np.mean(y[tr&ok]>0):.3f}')
    scores = {'v1 expected return': er_v1, 'v1 P(up)': p_up_v1}
    for obj in ('huber', 'binary'):
        a = tr & ok
        target = yc[a] if obj == 'huber' else (y[a] > 0).astype(int)
        params = dict(objective=obj, learning_rate=0.03, num_leaves=15, min_data_in_leaf=200, feature_fraction=0.8,
                      bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=1)
        if obj == 'huber': params['alpha'] = 0.2
        dtr = lgb.Dataset(ds.X[a], target, weight=ds.weight[a], feature_name=list(FEATURES))
        b = va & ok
        dva = lgb.Dataset(ds.X[b], yc[b] if obj == 'huber' else (y[b] > 0).astype(int), weight=ds.weight[b], reference=dtr)
        booster = lgb.train(params, dtr, 2000, valid_sets=[dva], callbacks=[lgb.early_stopping(100, verbose=False)])
        scores[f'net model ({obj}, {booster.best_iteration} rounds)'] = booster.predict(ds.X, num_iteration=booster.best_iteration)
    for name, score in scores.items():
        best = pick_threshold(score, va, rule)
        if best is None:
            print(f'  {name}: no threshold with 30+ validation trades'); continue
        thr, _, q = best
        print(f' {name}: threshold at validation quantile {q}')
        show('valid (threshold chosen here)', run_policy(curves, ds.token[va], ds.time[va], score[va] > thr, costs, rule))
        show('TEST', run_policy(curves, ds.token[te], ds.time[te], score[te] > thr, costs, rule))
