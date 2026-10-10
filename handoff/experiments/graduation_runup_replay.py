"""Graduation run-up rules judged by the fast loop itself, replayed over the full raw stream.

    python3 handoff/experiments/graduation_runup_replay.py [dirs...]

Why not graduation_runup.py: that script reads curves from `load_trade_tokens`, whose token
windows end at the first recording interruption. A token that graduates ends its window at
graduation (short, rarely cut); a token that rugs keeps its window open until it has been idle
for 20 minutes (long, often cut). Skipping cut windows therefore skips losers more than winners.
Here every signal is traded through `FastLoop` on the raw stream (which keeps recording across
short disconnects), and a signal is excluded only if the *recorder* was down during its
holding period (a gap of more than 30 s in the event stream, or the end of the recording):
a rule that depends on the recorder alone, never on the token.

Haircut: exits after the curve completed are sold on PumpSwap (not recorded); they are valued at
the final curve price less the haircut, recomputed for 0%, 10% and 25%.
"""
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

DIRS = sys.argv[1:] or ["handoff/data/raw", "handoff/data/raw-slots", "handoff/data/raw-slots-processed"]
RULES = [(50.0, 80.0), (60.0, 80.0), (70.0, 80.0), (75.0, 80.0)]
HOLD = 1800.0


def downtime(directory: str) -> tuple[list[tuple[float, float]], float]:
    ts = sorted(e["t"] for e in read_events(raw_files(directory)))
    gaps = [(a, b) for a, b in zip(ts, ts[1:]) if b - a > 30.0]
    return gaps, ts[-1]


def run(directory: str, enter: float, exit_: float, latency: float) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        p = asdict(Policy())
        p.update(
            runup_enter_sol=enter, runup_exit_sol=exit_, runup_hold_seconds=HOLD, graduation_haircut=0.0, exec_latency=latency,
            min_buyers=1000, max_open=100, max_entries_per_hour=1000, daily_loss_limit_sol=100.0,
        )  # fmt: skip
        Path(tmp, "policy.json").write_text(json.dumps(p))
        loop = FastLoop(PolicyFile(Path(tmp, "policy.json")), Journal(Path(tmp, "j")))
        replay(directory, loop)
        records = load_journal(Path(tmp, "j"))
    gaps, end = downtime(directory)
    size, network = p["size_sol"], p["network_sol"]
    exits = {r["mint"]: r for r in records if r["e"] == "exit" and r.get("kind") == "runup"}
    cancels = {r["mint"]: r for r in records if r["e"] == "cancel" and r.get("kind") == "runup"}
    out = []
    for r in (r for r in records if r["e"] == "runup" and "skip" not in r):
        t0, t1 = r["t"], r["t"] + latency + HOLD + 5.0
        if t1 > end or any(a < t1 and b > t0 for a, b in gaps):
            continue  # the recorder was down during the trade: outcome unknown (decided by the recorder alone)
        m = r["mint"]
        if m in exits:
            x = exits[m]
            out.append({"mint": m, "t": t0, "reason": x["reason"], "proceeds": x["pnl_sol"] + size + 2 * network, "size": size, "network": network})
        elif m in cancels:
            out.append({"mint": m, "t": t0, "reason": "missed", "proceeds": None, "size": size, "network": network})
    return out


def ret(row: dict, haircut: float) -> float:
    if row["proceeds"] is None:
        return -row["network"] / row["size"]  # the buy failed: one wasted transaction
    proceeds = row["proceeds"] * ((1.0 - haircut) if row["reason"] == "after_graduation" else 1.0)
    return (proceeds - row["size"] - 2 * row["network"]) / row["size"]


rng = np.random.default_rng(0)
print(f"directories: {DIRS}; hold limit {HOLD / 60:.0f} min; per signal (a missed buy costs one transaction)\n")
for latency in (1.0, 3.0):
    for enter, exit_ in RULES:
        rows, seen = [], set()
        for d in DIRS:
            for row in run(d, enter, exit_, latency):
                if row["mint"] not in seen:
                    seen.add(row["mint"])
                    rows.append(row)
        rows.sort(key=lambda r: r["t"])
        reasons = {}
        for r in rows:
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
        line = f"latency {latency:g}s  {enter:g} -> {exit_:g} SOL  n={len(rows):3d}"
        for haircut in (0.0, 0.10, 0.25):
            v = np.array([ret(r, haircut) for r in rows])
            boots = v[rng.integers(0, len(v), (2000, len(v)))].mean(axis=1)
            lo, hi = np.quantile(boots, [0.05, 0.95])
            half = len(v) // 2
            line += f" | cut {haircut:.0%}: {100 * v.mean():+6.2f}% [{100 * lo:+6.1f},{100 * hi:+6.1f}] halves {100 * v[:half].mean():+5.1f}/{100 * v[half:].mean():+5.1f}"
        print(line + f"  {reasons}")
    print()
