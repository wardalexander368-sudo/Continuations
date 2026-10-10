"""Edge hunt I1 (edge-hunt.md): revival entries on the bonding curve. Dev launches only unless --test.

    python3 handoff/experiments/revival.py OUT.pkl [OUT.pkl ...]            # exit_study.py extract pickles
    python3 handoff/experiments/revival.py --test SPEC.json OUT.pkl ...     # a pre-registered rule, once

Signal: 30-110 min after a SOL launch's create (the recorder follows a token for 120 min), the first
trade at which the token had been quiet (<= 1 trade in the previous `quiet` minutes) and then at
least `k` distinct wallets other than the creator bought within 60 s. Optional: the launch's curve
had reached `X` real SOL at some earlier point (a token with a past). Buy 1 s later at 0.02 SOL,
1.25%/side; exit by take profit or max hold (exit_study.Window). Dev = created before 16:00 UTC
10-09; rules are chosen on dev's first 60% and checked on its last 40%.
"""
from __future__ import annotations

import itertools
import json
import sys

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "handoff/experiments")
from exit_study import TEST_FROM, fmt, stats  # noqa: E402
from who_trades import EXITS, FEE, LAT, LTN_FEE, LTN_LAT, load, trade  # noqa: E402


def signals(launches, quiet_min, k, X):
    out = []
    for n, L in enumerate(launches):
        a, who = L["path"], L["who"]
        t0, creator = L["created"], who[0]
        t = a[:, 0]
        rs = a[:, 1] - 30.0
        lo, hi = np.searchsorted(t, t0 + 1800), np.searchsorted(t, t0 + 6600)
        for j in range(lo, hi):
            if a[j, 3] <= 0:
                continue
            start = np.searchsorted(t, t[j] - 60)
            burst = {who[i] for i in range(start, j + 1) if a[i, 3] > 0 and who[i] != creator}
            if len(burst) < k:
                continue
            q0, q1 = np.searchsorted(t, t[start] - 60 * quiet_min), start
            if q1 - q0 > 1 or q0 == 0:
                continue
            if X and rs[:start].max(initial=0) < X:
                continue
            out.append((n, j, j))
            break
    return out


def explore(launches):
    dev = [L for L in launches if L["created"] < TEST_FROM]
    cut = dev[int(0.6 * len(dev))]["created"]
    print(f"{len(dev)} dev launches; choose < {cut:.0f}, check after", flush=True)
    rows = []
    for quiet, k, X in itertools.product((5, 10), (3, 6), (0, 20)):
        sig = signals(dev, quiet, k, X)
        early = np.array([dev[n]["created"] < cut for n, _, _ in sig], bool)
        print(f"\nquiet {quiet} min, >= {k} buyers in 60 s, earlier peak >= {X} SOL: {len(sig)} signals", flush=True)
        for r in EXITS:
            v = trade(dev, sig, r)
            a, b = v[early], v[~early]
            a, b = a[np.isfinite(a)], b[np.isfinite(b)]
            rows.append((f"q{quiet} k{k} X{X} TP{r['tp']} {r['hold']}s", a, b))
            print(f"  TP {r['tp']} hold {r['hold']:4d} choose {fmt(stats(a))}  |  check {fmt(stats(b))}", flush=True)
    ok = [r for r in rows if len(r[1]) >= 100]
    print("\nbest 6 on 'choose' (n >= 100), with their 'check':")
    for name, a, b in sorted(ok, key=lambda r: -r[1].mean())[:6]:
        print(f"  {name:<30} choose {fmt(stats(a))}  |  check {fmt(stats(b))}")


def test(spec_path, pkls):
    spec = json.load(open(spec_path))
    until = spec.get("test_until_unix", float("inf"))
    launches = [L for L in load(pkls) if spec["test_from_unix"] <= L["created"] < until]
    sig = signals(launches, spec["quiet_min"], spec["buyers"], spec["peak_real_sol"])
    rule = {"tp": spec["take_profit"], "hold": spec["max_hold_s"]}
    print(f"{len(launches)} test launches, {len(sig)} signals")
    for name, fee, lat in (("PRIMARY (curve fees 1.25%/side, 1 s)", FEE, LAT), ("secondary: Lightning (+1%/side, 1.4 s)", LTN_FEE, LTN_LAT)):
        v = trade(launches, sig, rule, fee, lat)
        print(f"  {name}: {fmt(stats(v[np.isfinite(v)]))}")


if __name__ == "__main__":
    if sys.argv[1] == "--test":
        test(sys.argv[2], sys.argv[3:])
    else:
        explore(load(sys.argv[1:]))
