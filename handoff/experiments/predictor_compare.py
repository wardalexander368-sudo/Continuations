"""The installed global model vs a candidate, scored on the candidate's own dataset (same test tokens).

    python3 handoff/experiments/predictor_compare.py TIMEFRAME CANDIDATE_DIR --raw DIR[,DIR...] [--installed DIR]

`tartar train`'s keep-better check compares test log loss only; this also replays the live
forecaster on 300 test tokens for both models, so point edges and calibration can be compared on
the same launches. Writes CANDIDATE_DIR/compare-<seconds>s.json.
"""
import argparse
import json
import sys

sys.path.insert(0, ".")
from tartar.candles import parse_timeframe  # noqa: E402
from tartar.data.dataset import build_dataset, load_trade_tokens  # noqa: E402
from tartar.model.global_model import GlobalModel, model_dir  # noqa: E402
from tartar.train import evaluate, test_log_loss  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("timeframe")
ap.add_argument("candidate")
ap.add_argument("--raw", required=True)
ap.add_argument("--installed", default=None)
a = ap.parse_args()
tf = parse_timeframe(a.timeframe)
ds = build_dataset(load_trade_tokens(a.raw, tf), tf, "trades")
out = {}
for name, path in (("installed", model_dir(a.installed) / f"trades-{tf}s"), ("candidate", f"{a.candidate}/trades-{tf}s")):
    m = GlobalModel.load(f"{path}.txt")
    r = evaluate(m, ds, replay_tokens=300, log=lambda *_: None)
    live = r["live_at_open"]["global_plus_online"]
    f0 = r["test_by_fraction"][0]
    out[name] = {
        "test_log_loss": test_log_loss(m, ds), "edge_open": f0["edge"], "hit_open": f0["hit_rate"], "stated_open": f0["avg_confidence"],
        "info_open": f0.get("info_gain_bits"), "live_all": live["all"]["edge"], "live_trading": live["trading"]["edge"],
        "live_trading_hit": live["trading"]["hit_rate"], "live_trading_stated": live["trading"]["avg_confidence"],
        "edge_by_f": [round(x["edge"], 4) for x in r["test_by_fraction"]],
    }  # fmt: skip
print(json.dumps(out, indent=1))
with open(f"{a.candidate}/compare-{tf}s.json", "w") as f:
    json.dump(out, f, indent=1)
