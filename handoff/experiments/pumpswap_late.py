"""Edge hunt I2: graduated pools on PumpSwap *after their first hour* (pumpswap_study.py's families, later).

    python3 handoff/experiments/pumpswap_late.py DIR [DIR ...]

§3.16 closed the first hour after graduation on 264 pools (to 12:00 UTC 10-09). This asks the same
question 1-4 h after graduation, when the insiders' selling is over, on pools graduating after
12:00 UTC 10-09 that §3.16 never saw (`raw-clever` 12-15 via symlinks, `raw-clever2`, `raw-v3`, the
recorder Action's runs; one timeline per directory, a pool seen twice keeps the copy with more swaps).
Families as pumpswap_study.py (fills, PumpSwap fee tiers, recorder-gap exclusion), at 60/90/120/180
min; 0.02 SOL per entry. Pools by graduation time: rules chosen on the first 60%, checked on the rest.
"""
import sys

import numpy as np

sys.path.insert(0, "handoff/experiments")
import pumpswap_study as ps  # noqa: E402

FROM = 1791547200.0  # 2026-10-09 12:00 UTC
ps.GRID = ([("mom", {"at": a, "k": k}) for a in (3600, 5400, 7200, 10800) for k in (0.2, 0.5)]
           + [("dip", {"at": a, "k": k}) for a in (3600, 5400, 7200, 10800) for k in (0.3, 0.6)]
           + [("active", {"at": a, "n": n}) for a in (3600, 5400, 7200, 10800) for n in (10, 50)])  # fmt: skip
ps.HOLDS = (60, 300, 900, 3600)

best: dict[str, tuple] = {}
for d in sys.argv[1:]:
    pools, gaps, end = ps.load(d)
    for p in pools:
        if p.t_grad >= FROM and (p.pool not in best or len(p.ts) > len(best[p.pool][0].ts)):
            best[p.pool] = (p, gaps, end)
items = sorted(best.values(), key=lambda x: x[0].t_grad)
cut = int(0.6 * len(items))
print(f"{len(items)} pools graduating after 12:00 UTC 10-09; choose on the first {cut}, check on the rest")
rng = np.random.default_rng(0)
rows = {}
for n, (pool, gaps, end) in enumerate(items):
    for key, r in ps.run_rules([pool], gaps, end, 1.0, 0.02, 0.000011).items():
        rows.setdefault(key, []).extend((n, v) for _, v in r)
out = []
for key, r in rows.items():
    a = [(i, v) for i, v in r if i < cut]
    b = [(i, v) for i, v in r if i >= cut]
    sa, sb = ps.summarize(a, rng, 300), ps.summarize(b, rng, 300)
    out.append((key, sa, sb))
    print(f"  {key[0]:<6} {key[1]:<24} hold {key[2]:>4}s  choose {ps.fmt(sa)}\n{'':>46}check  {ps.fmt(sb)}")
ok = [o for o in out if o[1] and o[1]["n"] >= 20]
print("\nbest 6 on 'choose' (>= 20 trades):")
for key, sa, sb in sorted(ok, key=lambda o: -o[1]["mean"])[:6]:
    print(f"  {key[0]:<6} {key[1]:<24} hold {key[2]:>4}s  choose {ps.fmt(sa)}\n{'':>46}check  {ps.fmt(sb)}")
