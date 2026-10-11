"""Forward scorer for the two pre-registered US-spot chart patterns
(`handoff/preregistration/us-patterns/SPEC.md`).

    python3 handoff/experiments/edge-hunt/patterns/pattern_forward.py CACHE_DIR [--from 2026-10-12 --to 2027-10-11] [--final]

Fetches Coinbase's public 15-minute candles (fetch_coinbase.py; Coinbase keeps the full history,
so nothing has to be recorded live) from 30 days before the window, then scores both rules with
`patterns.py`'s exact code: CAPIT Z=4 H=24 and VOLSPIKE K=10 H=72, entry and exit 30 minutes
after the hourly close, 0.62% per side. One line per rule; --final adds SUCCESS/FAIL.
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
cache = sys.argv[1]
a = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "2026-10-12"
b = sys.argv[sys.argv.index("--to") + 1] if "--to" in sys.argv else "2027-10-11"
final = "--final" in sys.argv
if "--no-fetch" not in sys.argv:
    fetch_from = (dt.date.fromisoformat(a) - dt.timedelta(days=30)).isoformat()
    subprocess.run([sys.executable, str(HERE / "fetch_coinbase.py"), cache, "--from", fetch_from], check=True)

sys.argv = [sys.argv[0], cache, "--cost", "0.0062", "--delay-bars", "2"]
sys.path.insert(0, str(HERE))
import numpy as np  # noqa: E402
import patterns as P  # noqa: E402

P.SPLITS["fwd"] = (a, b)
for name, fn, hold in (("CAPIT Z=4 H=24", P.capit(4), 24), ("VOLSPIKE K=10 H=72", P.volspike(10), 72)):
    tr = P.split(P.run(fn, hold), "fwd")
    if len(tr) < 2:
        print(f"{name}: {len(tr)} trades in {a}..{b}")
        continue
    from collections import defaultdict
    by = defaultdict(list)
    for d, r in tr:
        by[d].append(r)
    k = list(by); s = np.array([sum(by[x]) for x in k]); n = np.array([len(by[x]) for x in k])
    pick = np.random.default_rng(1).integers(0, len(k), (10000, len(k)))
    lo, hi = np.percentile(s[pick].sum(1) / n[pick].sum(1), [5, 95])
    m = float(np.mean([r for _, r in tr]))
    line = f"{name}: {len(tr)} trades on {len(k)} days, mean {m * 100:+.2f}%/trade after 0.62%/side, 90% CI [{lo * 100:+.2f}, {hi * 100:+.2f}]"
    if final:
        line += "  " + ("SUCCESS" if m > 0 and lo > 0 else "FAIL")
    print(line)
