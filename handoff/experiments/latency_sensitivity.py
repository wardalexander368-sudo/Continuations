import pickle, sys, numpy as np
sys.path.insert(0, '.')
from tartar.profit import Costs, Exit, Curve, run_policy, summarize
ds = pickle.load(open(sys.argv[1],'rb'))
curves = [Curve([t for g in tok.ticks.values() for t, _ in g]) for tok in ds.tokens]
tr, va, te = ds.split()
created = np.array([t.created for t in ds.tokens])
toks = np.unique(ds.token[va | te])
print(f'{len(toks)} tokens (valid+test); snipe at launch receive time + delay, hold H')
print(f'{"latency":>8s} {"fee":>6s} {"hold":>5s}  mean     90% CI            win')
for lat in (0.0, 0.4, 1.0, 2.0):
    for fee in (0.0125, 0.005, 0.0):
        for h in (15, 30, 60):
            c = Costs(fee=fee, latency=lat)
            s = summarize(run_policy(curves, toks, created[toks], np.ones(len(toks), bool), c, Exit(h)), c, boot=1000)
            print(f'{lat:8.1f} {100*fee:5.2f}% {h:4d}s  {100*s.mean_ret:+6.2f}%  [{100*s.ci_low:+6.2f}, {100*s.ci_high:+6.2f}]  {100*s.win_rate:4.1f}%')
