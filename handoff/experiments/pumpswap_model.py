"""Train and judge the PumpSwap model (predictor doc §8.2.3) for several candle lengths in one pass.

    python3 handoff/experiments/pumpswap_model.py RAW_DIRS OUT [-t 15s,30s,1m,5m] [--grid small]

`tartar train --raw RAW_DIRS --pumpswap -t TF` does this for one length, but re-reads the raw logs
each time (~13 min for `raw-clever` alone). Here they are parsed once and shared by every length.
For each length:

1. build the dataset exactly as `tartar train --pumpswap` does (pools split 70 / 15 / 15% by
   graduation time);
2. sweep num_leaves x min_data_in_leaf and choose on **validation** log loss;
3. train the chosen setting and write `tartar train`'s full report next to the model in OUT
   (`evaluate`: test rows by candle fraction, and the live forecaster replayed on test pools with
   and without the model).

Nothing is installed. **Install rule, fixed before any result was read (2026-10-09 13:50 UTC):**
copy `OUT/pumpswap-<tf>s.{txt,json,report.json}` into `tartar/models/` only for a length where, on
the test pools' live replay, global + online beats online-only on edge for all candles and for
trading candles, its trading-candle calibration gap |hit - stated| is no more than 2 points worse
than online-only's, and the model's test rows carry positive information over the base rate at
the candle open.
"""
import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
import tartar.data.dataset as dataset  # noqa: E402
from tartar.candles import parse_timeframe  # noqa: E402
from tartar.model.global_model import model_name  # noqa: E402
from tartar.train import evaluate, test_log_loss, train_global  # noqa: E402

GRIDS = {
    "small": {"num_leaves": (15, 31, 63), "min_data_in_leaf": (100, 400, 1500)},
    "tiny": {"num_leaves": (31, 63), "min_data_in_leaf": (100, 1000)},
}

_cache: dict[tuple, list] = {}
_read_events = dataset.read_events


def cached_read_events(paths):
    """The loader reads every directory once per call; keep the parsed events for the next length."""
    key = tuple(sorted(str(p) for p in paths))
    if key not in _cache:
        _cache[key] = list(_read_events(paths))
    return iter(_cache[key])


dataset.read_events = cached_read_events


def log_loss(model, ds, mask):
    probs = model.predict_proba(ds.X[mask])
    labels, w = ds.label[mask], ds.weight[mask]
    return float(-(w * np.log(np.maximum(probs[np.arange(len(labels)), labels], 1e-12))).sum() / w.sum())


def verdict(report: dict) -> dict:
    live = report["live_at_open"]
    on, both = live["online_only"], live["global_plus_online"]
    gap = lambda t: abs(t["hit_rate"] - t["avg_confidence"])  # noqa: E731
    at_open = next(r for r in report["test_by_fraction"] if r["f"] == 0.0)
    checks = {
        "edge_all": both["all"]["edge"] > on["all"]["edge"],
        "edge_trading": both["trading"]["edge"] > on["trading"]["edge"],
        "calibration": gap(both["trading"]) <= gap(on["trading"]) + 0.02,
        "info_at_open": at_open.get("info_gain_bits", 0.0) > 0,
    }
    return {"install": all(checks.values()), "checks": checks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("out")
    ap.add_argument("-t", "--timeframes", default="15s,30s,1m,5m")
    ap.add_argument("--grid", default="small", choices=sorted(GRIDS))
    ap.add_argument("--replay-tokens", type=int, default=300)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for label in a.timeframes.split(","):
        tf = parse_timeframe(label)
        t0 = time.time()
        tokens = dataset.load_pumpswap_tokens(a.raw, tf)
        ds = dataset.build_dataset(tokens, tf, "pumpswap")
        train, valid, test = ds.split()
        print(f"\n=== {label}: {len(tokens)} pools, {len(ds)} rows (train {train.sum()}, valid {valid.sum()}, test {test.sum()}); "
              f"built in {time.time() - t0:.0f}s", flush=True)  # fmt: skip
        grid = GRIDS[a.grid]
        rows = []
        for leaves, min_leaf in itertools.product(grid["num_leaves"], grid["min_data_in_leaf"]):
            t1 = time.time()
            # The out-of-fold median shrink only moves the point forecast, not the log loss: skip it here.
            model = train_global(ds, num_leaves=leaves, min_data_in_leaf=min_leaf, shrink_folds=0, log=lambda _: None)
            v = log_loss(model, ds, valid)
            rows.append({"valid": v, "num_leaves": leaves, "min_leaf": min_leaf, "rounds": model.meta["best_iteration"]})
            print(f"  leaves {leaves:>3}  min_leaf {min_leaf:>4}: valid {v:.4f}  rounds {model.meta['best_iteration']:>4}  ({time.time() - t1:.0f}s)", flush=True)
        best = min(rows, key=lambda r: r["valid"])
        print(f"  chosen on validation: leaves {best['num_leaves']}, min_leaf {best['min_leaf']}", flush=True)
        model = train_global(ds, num_leaves=best["num_leaves"], min_data_in_leaf=best["min_leaf"], log=lambda _: None)
        report = evaluate(model, ds, replay_tokens=a.replay_tokens, log=lambda m: print("  " + m, flush=True))
        report["test_log_loss"] = test_log_loss(model, ds)
        report["sweep"] = rows
        report["verdict"] = verdict(report)
        path = model.save(out / model_name("pumpswap", tf))
        path.with_suffix(".report.json").write_text(json.dumps(report, indent=2))
        live = report["live_at_open"]
        for key in ("online_only", "global_plus_online"):
            for subset in ("all", "trading"):
                t = live[key][subset]
                print(f"  {key:>18} · {subset:<7} n {t['n']:>6}  hit {t['hit_rate']:.1%}  stated {t['avg_confidence']:.1%}  "
                      f"band {t['band_coverage']:.1%}  edge {t['edge']:+.1%}", flush=True)  # fmt: skip
        print(f"  test log loss {report['test_log_loss']:.4f}; verdict {report['verdict']}", flush=True)
        summary[label] = {"pools": len(tokens), "rows": len(ds), "chosen": best, "test_log_loss": report["test_log_loss"],
                          "live_at_open": live, "verdict": report["verdict"]}  # fmt: skip
        (out / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
