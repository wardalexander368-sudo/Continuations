"""Secondary lines for the US-patterns forward test at the venue costs a US person actually pays
(`handoff/preregistration/us-patterns/ADDENDUM-2026-10-11-venue-costs.md`). Informative only: the
registered result is still `pattern_forward.py CACHE --final` at 0.62% per side.

    python3 handoff/experiments/edge-hunt/patterns/pattern_forward_costs.py CACHE_DIR [--from 2026-10-12 --to 2027-10-11] [--no-fetch]

Same rules, same trades and the same 90% bootstrap over entry days as pattern_forward.py, computed
gross and then net of each per-side cost below.
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
COSTS = {  # per side, fixed 2026-10-11 before the window opened
    "Coinbase taker (0.90% fee since 2026-09-16 + ~1 bp half spread)": 0.0091,
    "Coinbase maker (0.50%, assumes every resting order fills)": 0.0050,
    "Alpaca taker (0.25% + 14 bp mean half spread on the 11 coins, measured 2026-10-11)": 0.0039,
}
cache = sys.argv[1]
a = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "2026-10-12"
b = sys.argv[sys.argv.index("--to") + 1] if "--to" in sys.argv else "2027-10-11"
if "--no-fetch" not in sys.argv:
    fetch_from = (dt.date.fromisoformat(a) - dt.timedelta(days=30)).isoformat()
    subprocess.run([sys.executable, str(HERE / "fetch_coinbase.py"), cache, "--from", fetch_from], check=True)

sys.argv = [sys.argv[0], cache, "--cost", "0", "--delay-bars", "2"]
sys.path.insert(0, str(HERE))
import numpy as np  # noqa: E402
import patterns as P  # noqa: E402

P.SPLITS["fwd"] = (a, b)
for name, fn, hold in (("CAPIT Z=4 H=24", P.capit(4), 24), ("VOLSPIKE K=10 H=72", P.volspike(10), 72)):
    tr = P.split(P.run(fn, hold), "fwd")
    if len(tr) < 2:
        print(f"{name}: {len(tr)} trades in {a}..{b}")
        continue
    by = defaultdict(list)
    for d, r in tr:
        by[d].append(r)
    k = list(by); s = np.array([sum(by[x]) for x in k]); n = np.array([len(by[x]) for x in k])
    pick = np.random.default_rng(1).integers(0, len(k), (10000, len(k)))
    boot = s[pick].sum(1) / n[pick].sum(1)
    m = float(np.mean([r for _, r in tr]))
    lo, hi = np.percentile(boot, [5, 95])
    print(f"{name}: {len(tr)} trades on {len(k)} days, gross {m * 100:+.2f}%/trade [{lo * 100:+.2f}, {hi * 100:+.2f}]")
    for label, c in COSTS.items():  # a fixed cost per trade shifts the mean and the CI alike
        print(f"  {label}: {(m - 2 * c) * 100:+.2f}% [{(lo - 2 * c) * 100:+.2f}, {(hi - 2 * c) * 100:+.2f}]")
