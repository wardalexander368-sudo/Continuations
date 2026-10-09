"""Longer holds (10-45 min) on screened launches, judged by the fast loop itself (queue item 3).

    python3 handoff/experiments/long_holds.py [--latency 1] DIR [DIR...]

Each policy below is replayed through `FastLoop` on the full raw stream of each directory (one
timeline each; profitability.md 3.10 lesson). A trade is excluded only if the *recorder* was down
during it (an event gap > 30 s, or the recording ended first). Holds end inside the recorder's
60-minute tracking window (screen + hold + latency < 60 min), so every exit price is recorded.
Positions still open when a token graduates are sold on its PumpSwap pool when the recording has
its swaps (`--pumpswap-hours`), else at the final curve price less the 10% haircut.

Grid: screen 20 / 120 / 600 s x hold 10 / 20 / 30 / 45 min x {the live skip flags; the same plus
at least 20 distinct buyers by the screen}. Launches are split by time: the rule with the best
mean net per trade on the first 60% (validation, at least 30 trades) is reported once on the
rest (test), with a 90% interval from a bootstrap over tokens.
"""
import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from tartar.data.rawlog import raw_files, read_events  # noqa: E402
from tartar.fastloop import FastLoop, Journal, Policy, PolicyFile, replay  # noqa: E402
from tartar.review import load_journal  # noqa: E402

SCREENS = (20.0, 120.0, 600.0)
HOLDS = (600.0, 1200.0, 1800.0, 2700.0)
FILTERS = {"flags": {}, "flags+20buyers": {"min_buyers": 20}}
MIN_TRADES = 30


def timeline(directory: str) -> tuple[list[tuple[float, float]], float, list[float]]:
    ts, creates = [], []
    for e in read_events(raw_files(directory)):
        ts.append(e["t"])
        if e["e"] == "create" and not e.get("quote"):
            creates.append(e["t"])
    ts.sort()
    return [(a, b) for a, b in zip(ts, ts[1:]) if b - a > 30.0], ts[-1], creates


def run(directory: str, screen: float, hold: float, extra: dict, latency: float, gaps, end) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        p = asdict(Policy())
        p.update(screen_seconds=screen, hold_seconds=hold, exec_latency=latency, shadow_jev=False, max_open=100, max_entries_per_hour=1000, daily_loss_limit_sol=100.0, **extra)
        Path(tmp, "policy.json").write_text(json.dumps(p))
        loop = FastLoop(PolicyFile(Path(tmp, "policy.json")), Journal(Path(tmp, "j")))
        replay(directory, loop)
        records = load_journal(Path(tmp, "j"))
    decided = {r["mint"]: r["t"] for r in records if r["e"] == "decision" and r.get("buy")}
    out = []
    for r in records:
        if r["e"] != "exit":
            continue
        t0 = decided[r["mint"]]
        t1 = t0 + latency + hold + 5.0
        if t1 > end or any(a < t1 and b > t0 for a, b in gaps):
            continue  # the recorder was down during the trade: outcome unknown
        out.append({"mint": r["mint"], "t": t0, "ret": r["ret"], "reason": r["reason"]})
    return out


def stats(rows, rng, boots=2000):
    if not rows:
        return None
    v = np.array([r["ret"] for r in rows])
    means = v[rng.integers(0, len(v), (boots, len(v)))].mean(axis=1)  # one trade per token: tokens = trades
    lo, hi = np.quantile(means, [0.05, 0.95])
    half = len(v) // 2
    return {"n": len(v), "mean": v.mean(), "lo": lo, "hi": hi, "median": float(np.median(v)), "win": float(np.mean(v > 0)), "halves": (v[:half].mean(), v[half:].mean())}


def fmt(s):
    if not s:
        return "no trades"
    return f"{s['n']:>4} trades  mean {100 * s['mean']:+6.2f}% [{100 * s['lo']:+6.2f}, {100 * s['hi']:+6.2f}]  median {100 * s['median']:+6.2f}%  win {100 * s['win']:4.1f}%  halves {100 * s['halves'][0]:+.1f}% / {100 * s['halves'][1]:+.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--latency", type=float, default=1.0)
    ap.add_argument("--split", type=float, default=0.6)
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    lines = {d: timeline(d) for d in a.dirs}
    creates = sorted(t for _, _, c in lines.values() for t in c)
    cut = creates[int(len(creates) * a.split)]
    print(f"{len(creates)} SOL launches in {len(a.dirs)} recording(s); validation = launches before the {a.split:.0%} time cut, test = after\n")
    results = {}
    for screen in SCREENS:
        for hold in HOLDS:
            for name, extra in FILTERS.items():
                rows = []
                for d, (gaps, end, _) in lines.items():
                    rows += run(d, screen, hold, extra, a.latency, gaps, end)
                rows.sort(key=lambda r: r["t"])
                results[(screen, hold, name)] = rows
    best = None
    print("VALIDATION:")
    for key, rows in results.items():
        s = stats([r for r in rows if r["t"] < cut], rng, boots=300)
        if s and s["n"] >= MIN_TRADES and (best is None or s["mean"] > best[1]["mean"]):
            best = (key, s)
        print(f"  screen {key[0]:>4.0f}s hold {key[1] / 60:>3.0f} min {key[2]:<15} {fmt(s)}")
    if best is None:
        print("no rule with enough validation trades")
        return
    key = best[0]
    test = [r for r in results[key] if r["t"] >= cut]
    reasons = {}
    for r in test:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    print(f"\nTEST, the rule chosen on validation (screen {key[0]:.0f} s, hold {key[1] / 60:.0f} min, {key[2]}):\n  {fmt(stats(test, rng))}  exits {reasons}")


if __name__ == "__main__":
    main()
