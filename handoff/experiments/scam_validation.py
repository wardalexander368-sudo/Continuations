"""How well do the scam filter's risk levels and flags predict a collapse? (predictor doc problem 6)

    python3 handoff/experiments/scam_validation.py DIR [DIR...] [--screen 20] [--horizon 1800]

Each launch is judged exactly as the fast loop and `watch --next-launch` judge it: its state
`--screen` seconds after launch (risk level, flags; creator history only from launches whose
outcome was known by then), from a fast-loop replay that screens every launch and buys none.
Outcome: the price `--horizon` seconds after the screen, read from the full raw stream, relative to
the price at the screen. A launch that graduated before the horizon counts as "graduated". After
the recorder stopped following an idle token the price is taken as unchanged. A launch is excluded
only when the recorder was down in between (event gap > 30 s, or recording end).

Labels: **rug** = the price fell 80% or more, **moon** = it doubled or graduated.
Then a P(rug) model (LightGBM on the screen state's numbers) is trained on the first 70% of
launches by time and checked on the rest: AUC and calibration by decile.
"""
import argparse
import bisect
import json
import sys
import tempfile
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from tartar.data.rawlog import raw_files, read_events  # noqa: E402
from tartar.decide import NUMERIC as STATE_FEATURES  # noqa: E402
from tartar.fastloop import FastLoop, Journal, Policy, PolicyFile, replay  # noqa: E402
from tartar.review import load_journal  # noqa: E402


def stream(directory):
    prices, migrated, times = defaultdict(lambda: ([], [])), {}, []
    for e in read_events(raw_files(directory)):
        times.append(e["t"])
        if e.get("quote"):
            continue
        if e["e"] in ("create", "trade") and e.get("vsol") and e.get("vtok"):
            ts, ps = prices[e["mint"]]
            ts.append(e["t"])
            ps.append(e["vsol"] / e["vtok"])
        elif e["e"] in ("migrate", "graduate"):
            migrated.setdefault(e["mint"], e["t"])
    times.sort()
    gaps = [(a, b) for a, b in zip(times, times[1:]) if b - a > 30.0]
    for ts, ps in prices.values():
        order = np.argsort(ts, kind="stable")
        ts[:], ps[:] = [ts[i] for i in order], [ps[i] for i in order]
    return prices, migrated, gaps, times[-1] if times else 0.0


def price_at(path, t):
    ts, ps = path
    i = bisect.bisect_right(ts, t) - 1
    return ps[i] if i >= 0 else None


def screens(directory, screen):
    with tempfile.TemporaryDirectory() as tmp:
        p = asdict(Policy())
        p.update(screen_seconds=screen, min_buyers=1000, skip_flags=[], shadow_jev=False)  # screen everything, buy nothing
        Path(tmp, "policy.json").write_text(json.dumps(p))
        loop = FastLoop(PolicyFile(Path(tmp, "policy.json")), Journal(Path(tmp, "j")))
        replay(directory, loop)
        return [r for r in load_journal(Path(tmp, "j")) if r["e"] == "screen"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--screen", type=float, default=20.0)
    ap.add_argument("--horizon", type=float, default=1800.0)
    a = ap.parse_args()
    rows, seen = [], set()
    for d in a.dirs:
        prices, migrated, gaps, end = stream(d)
        for r in screens(d, a.screen):
            mint, t0 = r["mint"], r["t"]
            if mint in seen or mint not in prices:
                continue
            t1 = t0 + a.horizon
            if t1 > end or any(x < t1 and y > t0 for x, y in gaps):
                continue
            seen.add(mint)
            p0, p1 = price_at(prices[mint], t0), price_at(prices[mint], t1)
            if not p0 or not p1:
                continue
            graduated = mint in migrated and migrated[mint] <= t1
            ratio = p1 / p0
            rows.append({"t": t0, "state": r["state"], "ratio": ratio, "rug": (not graduated) and ratio <= 0.2, "moon": graduated or ratio >= 2.0})
    rows.sort(key=lambda r: r["t"])
    n = len(rows)
    rug = np.array([r["rug"] for r in rows])
    moon = np.array([r["moon"] for r in rows])
    print(f"{n} launches judged at +{a.screen:.0f} s, outcome at +{a.horizon / 60:.0f} min: rug {100 * rug.mean():.1f}%, moon {100 * moon.mean():.1f}%, median price ratio {np.median([r['ratio'] for r in rows]):.2f}\n")

    def line(name, mask):
        k = int(mask.sum())
        if k == 0:
            return
        print(f"  {name:<18} n {k:>5} ({100 * k / n:4.1f}%)  P(rug) {100 * rug[mask].mean():5.1f}%  lift {rug[mask].mean() / rug.mean():4.2f}  recall {100 * (rug & mask).sum() / max(rug.sum(), 1):5.1f}%  P(moon) {100 * moon[mask].mean():5.1f}%")

    print("by risk level:")
    levels = np.array([r["state"].get("risk") for r in rows])
    for level in ("ok", "caution", "danger", "scam"):
        line(level, levels == level)
    print("by flag (a launch can carry several):")
    flags = sorted({f for r in rows for f in r["state"].get("flags", [])})
    for f in flags:
        line(f, np.array([f in r["state"].get("flags", []) for r in rows]))
    line("no flag", np.array([not r["state"].get("flags") for r in rows]))

    # P(rug) from the screen state's numbers, trained on earlier launches
    import lightgbm as lgb

    X = np.array([[np.nan if r["state"].get(k) is None else float(r["state"][k]) for k in STATE_FEATURES] for r in rows], dtype=float)
    cut = int(0.7 * n)
    params = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 50, "feature_fraction": 0.8, "verbose": -1, "seed": 7}
    inner = int(0.8 * cut)
    booster = lgb.train(params, lgb.Dataset(X[:inner], rug[:inner]), 2000, valid_sets=[lgb.Dataset(X[inner:cut], rug[inner:cut])], callbacks=[lgb.early_stopping(50, verbose=False)])
    p = booster.predict(X[cut:], num_iteration=booster.best_iteration)
    y = rug[cut:]
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    auc = (ranks[y].sum() - y.sum() * (y.sum() + 1) / 2) / max(y.sum() * (~y).sum(), 1)
    risk_rank = np.array([float(r["state"].get("risk_rank") or 0) for r in rows[cut:]])
    order = np.argsort(risk_rank, kind="stable")
    rr = np.empty(len(risk_rank))
    rr[order] = np.arange(1, len(risk_rank) + 1)
    auc_level = (rr[y].sum() - y.sum() * (y.sum() + 1) / 2) / max(y.sum() * (~y).sum(), 1)
    print(f"\nP(rug) model, test (last 30%, {len(y)} launches, base rate {100 * y.mean():.1f}%): AUC {auc:.3f} (the risk level alone: {auc_level:.3f})")
    print("  calibration by decile of predicted P(rug): predicted -> observed")
    for chunk in np.array_split(np.argsort(p), 10):
        print(f"    {100 * p[chunk].mean():5.1f}% -> {100 * y[chunk].mean():5.1f}%  (n {len(chunk)})")
    imp = booster.feature_importance("gain")
    top = np.argsort(imp)[::-1][:8]
    print("  top features: " + ", ".join(f"{STATE_FEATURES[i]} {imp[i] / imp.sum():.0%}" for i in top))


if __name__ == "__main__":
    main()
