"""Holding and rebalance timing for the registered CDE vol-momentum rule (exploratory, research only).

    python3 handoff/experiments/edge-hunt/perps/cde_timing.py DAILY_DIR

DAILY_DIR as cde_forward.py writes it. The registered rule (preregistration/cde-vol-momentum/SPEC.md: D3,
quintile legs, signal Monday close, entered Tuesday close, 20 bps a side) is unchanged; this asks whether
the agent should hold its winners longer or trade on another day, on the same data and splits:

* Hold band ("keep winners"): a coin already held long stays long while it ranks in the top B of the
  universe (B = 30%, 40%, 50%) instead of dropping out the week it leaves the top 20%; shorts mirror it.
  New entries still come from the quintiles, and a leg keeps the registered size (equal weight, $1 a leg
  over however many coins it holds). Fewer trades, less cost; the risk is holding fading coins.
* Execution lag: entered at the signal day's close (lag 0) or 2 days later, against the registered 1.
* Signal day: the same rule on another weekday (each still entered a day later).

Each variant is scored as a paired weekly difference to the registered rule (same weeks), 4-week block
bootstrap 90% CI; selection on train, validation must agree, test read once, with a Bonferroni CI over
every variant tried. Today's coin list (look-ahead) and funding are as in the registration.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xs_coinbase as X  # noqa: E402  (loads DAILY_DIR)

COST = 0.0020


def run(band=0.2, lag=1, weekday=0):
    """Weekly long-short D3 book; returns [(signal day, net return)]. band=0.2, lag=1, weekday=0 is registered."""
    days = [i for i in range(60, len(X.days) - 8 - lag) if X.wd[i] == weekday]
    out, prev = [], {}
    for k, i in enumerate(days[:-1]):
        j = days[k + 1]
        sig = X.sig_vmom(i)
        ok = X.universe(i) & np.isfinite(sig)
        ids = np.where(ok)[0]
        if len(ids) < 10:
            prev = {}; continue
        o = ids[np.argsort(sig[ids])]; n = len(o); q = n // 5
        rank = {c: r for r, c in enumerate(o)}  # 0 = weakest
        m = max(q, int(band * n))  # band 0.2 keeps exactly the quintiles (registered)
        longs = set(o[-q:]) | {c for c, w in prev.items() if w > 0 and c in rank and rank[c] >= n - m}
        shorts = set(o[:q]) | {c for c, w in prev.items() if w < 0 and c in rank and rank[c] < m}
        w = {**{c: 1 / len(longs) for c in longs}, **{c: -1 / len(shorts) for c in shorts}}
        a, b = i + lag, j + lag
        r = sum(wt * (X.C[b, c] / X.C[a, c] - 1) for c, wt in w.items() if not np.isnan(X.C[b, c]) and not np.isnan(X.C[a, c]))
        turn = sum(abs(w.get(c, 0) - prev.get(c, 0)) for c in set(w) | set(prev)) / 2
        prev = w
        out.append((X.days[i], r - 2 * COST * turn, turn))
    return out


def boot(x, alpha=0.10, n=4000):
    x = np.asarray(x)
    if len(x) < 8:
        return np.nan, (np.nan, np.nan), len(x)
    rng = np.random.default_rng(1); B = 4
    bs = [x[np.concatenate([np.arange(s, s + B) % len(x) for s in rng.integers(0, len(x), len(x) // B + 1)])[: len(x)]].mean() for _ in range(n)]
    return float(x.mean()), tuple(np.percentile(bs, [100 * alpha / 2, 100 - 100 * alpha / 2])), len(x)


def fmt(t):
    m, ci, n = t
    return f"{m * 100:+.2f}% [{ci[0] * 100:+.2f},{ci[1] * 100:+.2f}] n{n}" if not np.isnan(m) else f"- n{n}"


def week_of(day):  # pair weeks across weekdays by ISO week
    import datetime as dt
    return dt.date.fromisoformat(day).isocalendar()[:2]


def split(rows, s):
    a, b = X.SPLITS[s]
    return [r for r in rows if a <= r[0] <= b]


if __name__ == "__main__":
    base = run()
    print(f"{len(X.coins)} coins; registered D3 long-short, 20 bp/side")
    print("  registered            " + "  ".join(f"{s} {fmt(boot([r[1] for r in split(base, s)]))}" for s in X.SPLITS) +
          f"  turnover/wk {np.mean([r[2] for r in base]):.2f}")
    variants = {f"hold band top/bottom {int(b * 100)}%": dict(band=b) for b in (0.3, 0.4, 0.5)}
    variants.update({f"entry lag {lag} day(s)": dict(lag=lag) for lag in (0, 2)})
    variants.update({f"signal on {d}": dict(weekday=k) for k, d in ((2, "Wednesday"), (4, "Friday"), (6, "Sunday"))})
    M = len(variants)
    bw = {week_of(d): r for d, r, _ in base}
    res = []
    for name, kw in variants.items():
        rows = run(**kw)
        diff = [(d, r - bw[week_of(d)]) for d, r, _ in rows if week_of(d) in bw]
        tr, va = boot([x for _, x in split(diff, "train")]), boot([x for _, x in split(diff, "val")])
        res.append((name, diff, tr, va))
        print(f"  {name:22s} diff train {fmt(tr)}  val {fmt(va)}  turnover/wk {np.mean([r[2] for r in rows]):.2f}  "
              f"(own net train {fmt(boot([r[1] for r in split(rows, 'train')]))})")
    name, diff, tr, va = max(res, key=lambda r: r[2][0] if not np.isnan(r[2][0]) else -9)
    print(f"variants tried: {M}")
    if tr[0] > 0 and va[0] > 0:
        te = [x for _, x in split(diff, "test")]
        print(f"-> chosen {name}: TEST diff {fmt(boot(te))}; Bonferroni {fmt(boot(te, alpha=0.10 / M, n=20000))}")
    else:
        print(f"-> chosen {name}: train <= 0 or validation disagrees; test not read")
