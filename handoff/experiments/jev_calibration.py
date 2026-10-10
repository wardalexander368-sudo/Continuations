import sys, json, numpy as np
sys.path.insert(0, '.')
from tartar.data.dataset import load_trade_tokens
from tartar.decide import launch_states
from tartar.profit import Costs, Exit, curves_for, label_round_trips
from tartar.jev import LAUNCH, QUESTIONS
QUESTION_VERSION = LAUNCH.version
tokens = load_trade_tokens('data/raw', 60); curves = curves_for(tokens)
states = launch_states(tokens, curves, 20.0)
ans = {}
for line in open('data/jev-answers.jsonl'):
    r = json.loads(line)
    if r['version'] == QUESTION_VERSION: ans[r['mint']] = r['answers']
y = label_round_trips(curves, np.array([s['token'] for s in states]), np.array([s['decide_at'] for s in states]), Costs(), Exit(180))
ok = ~np.isnan(y)
print(f'launches with outcome: {ok.sum()}, base mean {np.nanmean(y):+.3f}, P(net>0) {np.mean(y[ok]>0):.3f}')
for q in QUESTIONS:
    p = np.array([ans[s['mint']][q] for s in states])
    print(f'--- {q}: mean answer {p[ok].mean():.3f}')
    edges = np.unique(np.quantile(p[ok], [0, .2, .4, .6, .8, 1]))
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = ok & (p >= lo) & ((p < hi) | (hi == edges[-1]))
        if m.sum(): print(f'   {lo:.2f}-{hi:.2f}: n={m.sum():4d}  P(net>0) {np.mean(y[m]>0):.3f}  mean net {y[m].mean():+.3f}  median {np.median(y[m]):+.3f}')
