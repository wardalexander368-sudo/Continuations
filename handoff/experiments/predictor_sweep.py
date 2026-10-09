"""Hyperparameter sweep for the global model (predictor doc, next step 4).

    python3 handoff/experiments/predictor_sweep.py RAW_DIRS [-t 1m] [--grid small|full]

Builds the dataset once (`tartar train`'s pipeline, same split: 70 / 15 / 15% of tokens by launch
time), trains one model per setting, and reports validation and test log loss (with each model's
own fitted temperature). Choose on validation; the test column is read once, for the chosen row
and the current default (num_leaves 63, min_data_in_leaf 100, learning_rate 0.05).
"""
import argparse
import itertools
import sys
import time

import numpy as np

sys.path.insert(0, ".")
from tartar.cli import parse_timeframe  # noqa: E402
from tartar.data.dataset import build_dataset, load_trade_tokens  # noqa: E402
from tartar.train import train_global  # noqa: E402


def log_loss(model, ds, mask):
    probs = model.predict_proba(ds.X[mask])
    labels, w = ds.label[mask], ds.weight[mask]
    return float(-(w * np.log(np.maximum(probs[np.arange(len(labels)), labels], 1e-12))).sum() / w.sum())


GRIDS = {
    "small": {"num_leaves": (15, 31, 63), "min_data_in_leaf": (100, 400, 1500), "learning_rate": (0.05,)},
    "full": {"num_leaves": (7, 15, 31, 63, 127), "min_data_in_leaf": (50, 100, 400, 1500, 4000), "learning_rate": (0.03, 0.05, 0.1)},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("-t", "--timeframe", default="1m")
    ap.add_argument("--grid", default="small", choices=sorted(GRIDS))
    a = ap.parse_args()
    tf = parse_timeframe(a.timeframe)
    started = time.time()
    tokens = load_trade_tokens(a.raw, tf)
    ds = build_dataset(tokens, tf, "trades")
    _, valid, test = ds.split()
    print(f"{len(tokens)} tokens, {len(ds)} rows (valid {valid.sum()}, test {test.sum()}); built in {time.time() - started:.0f}s", flush=True)
    grid = GRIDS[a.grid]
    rows = []
    for leaves, min_leaf, lr in itertools.product(grid["num_leaves"], grid["min_data_in_leaf"], grid["learning_rate"]):
        t0 = time.time()
        model = train_global(ds, num_leaves=leaves, min_data_in_leaf=min_leaf, learning_rate=lr, log=lambda _: None)
        v, te = log_loss(model, ds, valid), log_loss(model, ds, test)
        rows.append((v, te, leaves, min_leaf, lr, model.meta["best_iteration"]))
        print(f"leaves {leaves:>3}  min_leaf {min_leaf:>4}  lr {lr:.2f}: valid {v:.4f}  test {te:.4f}  rounds {model.meta['best_iteration']:>4}  ({time.time() - t0:.0f}s)", flush=True)
    best = min(rows)
    default = next((r for r in rows if r[2:5] == (63, 100, 0.05)), None)
    print(f"\nchosen on validation: leaves {best[2]}, min_leaf {best[3]}, lr {best[4]}: valid {best[0]:.4f}, TEST {best[1]:.4f}")
    if default:
        print(f"default (63, 100, 0.05): valid {default[0]:.4f}, TEST {default[1]:.4f}")


if __name__ == "__main__":
    main()
