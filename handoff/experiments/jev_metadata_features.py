"""Do Jev's judgments about launch metadata predict which launches beat costs?

Feature sets, each fed to the same LightGBM screen (train launches, early stopping on validation):
  A  numeric launch state (decide.NUMERIC)
  B  A + link features computed in code (metadata.LINK_FEATURES)
  C  B + Jev's metadata answers (jev.METADATA)
  D  A + Jev's metadata answers (no link features)
Reported: validation AUC (selection), test AUC with a launch bootstrap, and net P&L of the
validation-chosen threshold on test launches (decide.evaluate). Per-question Spearman uses
train + validation launches only.
"""
import json, sys
import numpy as np
sys.path.insert(0, '.')
from tartar.data.dataset import load_trade_tokens
from tartar.decide import NUMERIC, FunctionScorer, evaluate, launch_states, state_matrix
from tartar.jev import METADATA, JevClient
from tartar.metadata import LINK_FEATURES, fetch_metadata, link_features
from tartar.profit import Costs, Exit, curves_for, label_round_trips

tokens = load_trade_tokens('data/raw', 60)
curves = curves_for(tokens)
states = launch_states(tokens, curves, 20.0)
meta = fetch_metadata({t.mint: t.uri for t in tokens}, 'data/metadata.jsonl')
uri = {t.mint: t.uri for t in tokens}
for s in states:
    s['metadata'] = meta.get(s['mint'])
jev = JevClient(questions=METADATA, cache='data/jev-metadata.jsonl')
J = jev.features(states)
L = np.array([[link_features(s['metadata'], uri[s['mint']])[k] for k in LINK_FEATURES] for s in states])
N = state_matrix(states)
n = len(states)
split = np.where(np.arange(n) < 0.7 * n, 0, np.where(np.arange(n) < 0.85 * n, 1, 2))
sets = {
    'A numeric': (N, list(NUMERIC)),
    'B +links': (np.hstack([N, L]), list(NUMERIC) + list(LINK_FEATURES)),
    'C +links +jev': (np.hstack([N, L, J]), list(NUMERIC) + list(LINK_FEATURES) + [f'jev_{c}' for c in METADATA.features]),
    'D +jev': (np.hstack([N, J]), list(NUMERIC) + [f'jev_{c}' for c in METADATA.features]),
}


def auc(score, y):
    pos, neg = score[y], score[~y]
    if not len(pos) or not len(neg):
        return float('nan')
    ranks = np.argsort(np.argsort(np.concatenate([pos, neg]))) + 1
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def spearman(a, b):
    r = lambda v: np.argsort(np.argsort(v))  # noqa: E731
    return float(np.corrcoef(r(a), r(b))[0, 1])


import lightgbm as lgb

costs = Costs()
token = np.array([s['token'] for s in states])
when = np.array([s['decide_at'] for s in states])
for rule in (Exit(180), Exit(600, 1.0, 0.3)):
    y = label_round_trips(curves, token, when, costs, rule)
    ok = ~np.isnan(y)
    win = y > 0
    print(f'\n=== {rule.label()}: {ok.sum()} launches with outcomes, P(net>0) {win[ok].mean():.3f}')
    tv = ok & (split < 2)
    rows = sorted(((spearman(J[tv, i], y[tv]), c) for i, c in enumerate(METADATA.features)), reverse=True)
    print('  Jev answers, Spearman with net return (train+valid): ' + ', '.join(f'{c} {r:+.3f}' for r, c in rows))
    rows = sorted(((spearman(L[tv, i], y[tv]), c) for i, c in enumerate(LINK_FEATURES)), reverse=True)
    print('  link features, Spearman (train+valid):              ' + ', '.join(f'{c} {r:+.3f}' for r, c in rows))
    for name, (X, cols) in sets.items():
        params = dict(objective='binary', learning_rate=0.03, num_leaves=7, min_data_in_leaf=40, feature_fraction=0.8,
                      bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=1)
        a, b = ok & (split == 0), ok & (split == 1)
        dtr = lgb.Dataset(X[a], win[a].astype(int), feature_name=cols)
        dva = lgb.Dataset(X[b], win[b].astype(int), reference=dtr)
        booster = lgb.train(params, dtr, 2000, valid_sets=[dva], callbacks=[lgb.early_stopping(100, verbose=False)])
        p = booster.predict(X, num_iteration=booster.best_iteration)
        t = ok & (split == 2)
        rng = np.random.default_rng(0)
        idx = np.flatnonzero(t)
        boots = [auc(p[i], win[i]) for i in (rng.choice(idx, len(idx)) for _ in range(500))]
        lo, hi = np.nanquantile(boots, [0.05, 0.95])
        res = evaluate(FunctionScorer(name, lambda s, p=p: float(p[[st['mint'] for st in states].index(s['mint'])])), states, split, curves, costs, rule)
        tr = res.get('test') or {}
        gain = booster.feature_importance('gain'); top = np.argsort(gain)[::-1][:5]
        print(f'  {name:15s} rounds {booster.best_iteration:4d}  valid AUC {auc(p[b], win[b]):.3f}  test AUC {auc(p[t], win[t]):.3f} [{lo:.3f},{hi:.3f}]'
              + (f"  | buy top {100 * res['kept_share_valid']:.0f}%: test {tr['trades']} trades, mean {100 * tr['mean_ret']:+.2f}% [{100 * tr['ci_low']:+.1f},{100 * tr['ci_high']:+.1f}]" if res['threshold'] is not None and tr.get('trades') else '  | no threshold')
              + '  top: ' + ', '.join(cols[i] for i in top))
