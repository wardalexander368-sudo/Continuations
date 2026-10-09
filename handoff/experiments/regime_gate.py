"""Does the recent market (other launches' outcomes, launch rate) say when to trade launches? (trading-skills audit)

    python3 handoff/experiments/regime_gate.py OUT.pkl [OUT.pkl ...]   # files from exit_study.py extract

For each screened launch, three causal features at its decision time: the mean net of buying every
launch at +20 s and holding 180 s over launches whose exit had happened in the last 30 min; the
share of those that were ever sellable above cost in that hold ("movers"); and the number of
launches in the last 10 min. The trade judged is the live skip flags with TP +100% / hold 180 s
(the exit rule exit_study picks for that filter). Gate threshold chosen on dev, reported on test.
"""
import sys

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "handoff/experiments")
from exit_study import FILTERS, TEST_FROM, Window, exit_time, fmt, load, stats  # noqa: E402

LAT = 1.0
launches = load(sys.argv[1:])
wins = [Window(L, 0.1, 0.0125, 0.0002, LAT) for L in launches]
rows = []
for L, w in zip(launches, wins):
    if w.tokens is None:
        continue
    base = w.exit_at(w.entry_t + 180, LAT, w.entry_t + 180)
    n = int(np.searchsorted(w.t, w.entry_t + 180, side="right"))
    mover = bool(((w.value[:n] - 0.1 - 0.0004) / 0.1 > 0).any())
    trade = w.exit_at(exit_time(w, {"hold": 180, "tp": 1.0}), LAT, w.entry_t + 180)
    rows.append({"t": L["t"], "created": L["created"], "done": w.entry_t + 180 + LAT, "base": base, "mover": mover, "trade": trade, "flags_ok": FILTERS["live skip flags"](L)})
rows.sort(key=lambda r: r["t"])
done = sorted((r["done"], r["base"], r["mover"]) for r in rows if r["base"] is not None)
dt = np.array([d[0] for d in done]); db = np.array([d[1] for d in done]); dm = np.array([d[2] for d in done], float)
ct = np.array([r["t"] for r in rows])
for r in rows:
    a, b = np.searchsorted(dt, r["t"] - 1800), np.searchsorted(dt, r["t"])
    r["recent_mean"] = db[a:b].mean() if b - a >= 30 else np.nan
    r["recent_movers"] = dm[a:b].mean() if b - a >= 30 else np.nan
    r["rate10"] = np.searchsorted(ct, r["t"]) - np.searchsorted(ct, r["t"] - 600)

for feat in ("recent_mean", "recent_movers", "rate10"):
    print(f"\n== {feat}")
    for pop in ("every launch", "live skip flags"):
        sel = [r for r in rows if r["trade"] is not None and not np.isnan(r[feat]) and (pop == "every launch" or r["flags_ok"])]
        dev = [r for r in sel if r["created"] < TEST_FROM]
        test = [r for r in sel if r["created"] >= TEST_FROM]
        x = np.array([r[feat] for r in dev]); y = np.array([r["trade"] for r in dev])
        qs = np.quantile(x, [0.2, 0.4, 0.6, 0.8])
        line = []
        for k in range(5):
            lo = -np.inf if k == 0 else qs[k - 1]; hi = np.inf if k == 4 else qs[k]
            m = (x > lo) & (x <= hi)
            line.append(f"{100 * y[m].mean():+.1f}")
        rho = np.corrcoef(np.argsort(np.argsort(x)), np.argsort(np.argsort(y)))[0, 1]
        print(f"  {pop:16s} dev quintiles (low→high) {' / '.join(line)}  spearman {rho:+.3f}")
        best = None
        for q in (0.5, 0.6, 0.7, 0.8, 0.9):
            for side in (1, -1):
                thr = np.quantile(x, q if side == 1 else 1 - q)
                m = x > thr if side == 1 else x <= thr
                if m.sum() >= 100 and (best is None or y[m].mean() > best[0]):
                    best = (y[m].mean(), thr, side, q)
        _, thr, side, q = best
        tx = np.array([r[feat] for r in test]); ty = np.array([r["trade"] for r in test])
        m = tx > thr if side == 1 else tx <= thr
        print(f"  {pop:16s} gate {'>' if side == 1 else '<='} {thr:.3g}: dev {fmt(stats(y[(x > thr) if side == 1 else (x <= thr)]))}")
        print(f"  {pop:16s}            test {fmt(stats(ty[m]))}   (ungated test {fmt(stats(ty))})")
