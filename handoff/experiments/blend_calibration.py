"""Where does the curve blends' trading-candle underconfidence come from? (STATUS item (b), 2026-10-09)

    python3 handoff/experiments/blend_calibration.py RAW_DIRS [-t 1m] [--out FILE.jsonl]
    python3 handoff/experiments/blend_calibration.py --read FILE.jsonl

Replays the installed `trades-*` model through the live forecaster exactly as `train.replay`
does (same creator/launch masking), and for every forecast locked at a candle open records its
parts: the global model's no-trade mass, the online no-trade mass, the blend weight, the blended
no-trade mass (= p_flat at the open, where the price equals the reference), P(up | move) from
the global distribution, raw and calibrated, and the outcome. The report splits the stated
confidence vs hit rate on trading candles (the previous candle traded) into the flat-vs-move
call and the up/down call.

Pass directories holding only hours the model never saw (symlink the hourly files): tokens
whose launch is not in the files are skipped by the loader.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from tartar.candles import parse_timeframe  # noqa: E402
from tartar.data.dataset import _hash_unit, load_trade_tokens  # noqa: E402
from tartar.model.forecaster import Forecaster  # noqa: E402
from tartar.model.global_model import find_model  # noqa: E402


def records(raw: str, timeframe: int):
    model = find_model("trades", timeframe)
    tokens = load_trade_tokens(raw, timeframe)
    print(f"{len(tokens)} tokens", file=sys.stderr, flush=True)
    for token in tokens:
        known_creator = _hash_unit(token.mint, "creator") >= 0.3
        launched = token.created if token.launch_known and _hash_unit(token.mint, "launch") >= 0.15 else None
        fc = Forecaster(timeframe, 0.8, model=model, domain="trades", launched_at=launched, creator_known=known_creator)
        prev_active = False
        for i, candle in enumerate(token.candles):
            for tick, _ in token.ticks.get(candle.start, ()):
                fc.on_tick(tick)
            f = fc.locked
            parts = None
            if f is not None and f.target_start == candle.start:
                g = fc._global
                parts = {
                    "w": fc.global_weight,
                    "g_mass": None if g is None else float(g.p_still),
                    "o_mass": float(fc._online_mass),
                    "g_up": None if g is None else float(1.0 - g.cont_cdf(np.array([0.0]))[0]),
                    "q_raw": float(1.0 / (1.0 + np.exp(-fc._raw_log_odds))),
                }
            outcome = fc.observe(candle)
            if outcome is not None and parts is not None and i >= token.first_target:
                f = outcome.forecast
                yield {
                    "mint": token.mint, "t": candle.start, "i": i, "trading": prev_active,
                    "p_up": f.p_up, "p_down": f.p_down, "p_flat": f.p_flat, "call": f.direction,
                    "conf": f.confidence, "actual": outcome.actual_direction, "hit": outcome.hit, **parts,
                }  # fmt: skip
            prev_active = candle.active


def report(rows: list[dict]) -> None:
    tr = [r for r in rows if r["trading"]]
    print(f"candles {len(rows)}, trading {len(tr)}")
    for name, sub in (("all", rows), ("trading", tr)):
        hit = np.mean([r["hit"] for r in sub])
        conf = np.mean([r["conf"] for r in sub])
        print(f"  {name:<8} hit {hit:.1%}  stated {conf:.1%}  gap {hit - conf:+.1%}")
    print("\ntrading candles, by call:")
    for call in ("flat", "up", "down"):
        sub = [r for r in tr if r["call"] == call]
        if sub:
            print(f"  call {call:<5} n {len(sub):>6}  hit {np.mean([r['hit'] for r in sub]):.1%}  "
                  f"stated {np.mean([r['conf'] for r in sub]):.1%}")  # fmt: skip
    flat = np.array([r["actual"] == "flat" for r in tr])
    p_flat = np.array([r["p_flat"] for r in tr])
    print(f"\nflat on trading candles: observed {flat.mean():.1%}, blended p_flat {p_flat.mean():.1%}")
    gm = np.array([r["g_mass"] for r in tr if r["g_mass"] is not None])
    gm_flat = np.array([r["actual"] == "flat" for r in tr if r["g_mass"] is not None])
    om = np.array([r["o_mass"] for r in tr])
    print(f"  global mass {gm.mean():.1%} (observed {gm_flat.mean():.1%} on those), online mass {om.mean():.1%}, "
          f"weight {np.mean([r['w'] for r in tr]):.3f}")  # fmt: skip
    print("  p_flat bins: predicted -> observed (n)")
    edges = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    for lo, hi in zip(edges, edges[1:]):
        m = (p_flat >= lo) & (p_flat < hi)
        if m.sum() >= 30:
            print(f"    [{lo:.1f}, {hi:.1f}): {p_flat[m].mean():.3f} -> {flat[m].mean():.3f} ({m.sum()})")
    moved = [r for r in tr if r["actual"] != "flat"]
    q = np.array([r["p_up"] / max(r["p_up"] + r["p_down"], 1e-12) for r in moved])
    up = np.array([r["actual"] == "up" for r in moved])
    print(f"\ndirection on moved trading candles (n {len(moved)}): mean q_up {q.mean():.3f}, observed up {up.mean():.3f}")
    print(f"  right side of 50%: {np.mean((q > 0.5) == up):.1%}; stated max(q, 1-q) {np.mean(np.maximum(q, 1 - q)):.1%}")
    gq = np.array([r["g_up"] for r in moved if r["g_up"] is not None])
    gup = np.array([r["actual"] == "up" for r in moved if r["g_up"] is not None])
    print(f"  global P(up|move): right side {np.mean((gq > 0.5) == gup):.1%}, stated {np.mean(np.maximum(gq, 1 - gq)):.1%}")
    for lo, hi in zip([0, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7], [0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 1.01]):
        m = (q >= lo) & (q < hi)
        if m.sum() >= 30:
            print(f"    q_up [{lo:.2f}, {hi:.2f}): {q[m].mean():.3f} -> {up[m].mean():.3f} ({m.sum()})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", nargs="?")
    ap.add_argument("-t", "--timeframe", default="1m")
    ap.add_argument("--out")
    ap.add_argument("--read")
    a = ap.parse_args()
    if a.read:
        rows = [json.loads(line) for line in open(a.read)]
    else:
        rows = list(records(a.raw, parse_timeframe(a.timeframe)))
        if a.out:
            Path(a.out).write_text("".join(json.dumps(r) + "\n" for r in rows))
    report(rows)


if __name__ == "__main__":
    main()
