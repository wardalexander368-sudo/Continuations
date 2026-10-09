"""Predictor v3.1 study: every recording; the old recorder's (handoff/data/raw) training rows at weight w.

    python3 handoff/experiments/predictor_old_weight.py SECONDS OUT_DIR 1,0.5,0.25,0.1,0

The old recorder followed dead tokens for longer (20-min idle cut), so its rows have a different
outcome mix at 5m (predictor doc 8.2.2c). Validation and test hold no old rows, so validation log
loss may choose w. Prints test metrics for the installed model and each w; saves OUT_DIR/w<w>/.
"""
import sys, json, numpy as np
sys.path.insert(0, ".")
from tartar.data.dataset import build_dataset, load_trade_tokens
from tartar.model.global_model import GlobalModel
from tartar.train import evaluate, test_log_loss, train_global
tf = int(sys.argv[1]); out_dir = sys.argv[2]; weights = [float(x) for x in sys.argv[3].split(",")]
OTHERS = ["handoff/data/raw-slots", "handoff/data/raw-slots-processed", "handoff/data/raw-pumpswap", "handoff/data/raw-eager", "handoff/data/raw-clever"]
ds = build_dataset(load_trade_tokens(",".join(["handoff/data/raw"] + OTHERS), tf), tf, "trades")
old = {t.mint for t in load_trade_tokens("handoff/data/raw", tf)} - {t.mint for d in OTHERS for t in load_trade_tokens(d, tf)}
is_old = np.array([t.mint in old for t in ds.tokens])[ds.token]
tr, va, te = ds.split()
print(f"{len(ds.tokens)} tokens, {len(ds)} rows; old-recorder share: train {is_old[tr].mean():.2f} valid {is_old[va].mean():.2f} test {is_old[te].mean():.2f}", flush=True)
w0 = ds.weight.copy()

def report(name, m):
    r = evaluate(m, ds, replay_tokens=300, log=lambda *a: None)
    live = r["live_at_open"]["global_plus_online"]; f0 = r["test_by_fraction"][0]
    res = {"test_ll": round(test_log_loss(m, ds), 4), "open hit/stated": (round(f0["hit_rate"], 3), round(f0["avg_confidence"], 3)), "edge_open": round(f0["edge"], 4),
           "live all/trading": (live["all"]["edge"], live["trading"]["edge"]), "trading hit/stated": (live["trading"]["hit_rate"], live["trading"]["avg_confidence"]),
           "temperature": round(m.meta["temperature"], 3), "iters": m.meta["best_iteration"]}
    print(name, res, flush=True)
    return res

out = {"installed v3": report("installed v3", GlobalModel.load(f"tartar/models/trades-{tf}s.txt"))}
for w in weights:
    ds.weight = np.where(tr & is_old, w0 * w, w0)
    m = train_global(ds, num_leaves=31, min_data_in_leaf=2000, log=lambda *a: None)
    ds.weight = w0
    out[f"old rows x{w:g}"] = report(f"old rows x{w:g}", m)
    m.save(f"{out_dir}/w{w:g}/trades-{tf}s")
json.dump(out, open(f"{out_dir}/v31-{tf}s.json", "w"), indent=1)
