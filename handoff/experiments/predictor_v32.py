"""Predictor v3.2 study: v3.1's recipe on every curve recording, including the hours v3.1 never saw.

    python3 handoff/experiments/predictor_v32.py SECONDS OUT_DIR 1,0.25,0

Recordings: v3.1's (`raw`, `raw-slots`, `raw-slots-processed`, `raw-pumpswap`, `raw-eager`,
`raw-clever` 06-11) plus `raw-clever` 12-15, `raw-clever2`, `raw-v3` and `raw-pred` (one directory
per recorder; duplicate launches keep the longest copy). As in v3.1 (predictor doc 8.2.2d), the old
recorder's (`handoff/data/raw`) training rows are weighted by w and w is chosen on validation log
loss; validation and test hold no old rows. 31 leaves / 2,000 rows per leaf. Test = the latest 15%
of launches, which neither the installed v3.1 nor any candidate trained on. Prints validation and
test metrics for the installed model and each w; saves OUT_DIR/w<w>/ and OUT_DIR/v32-<seconds>s.json.
"""
import sys, json, numpy as np
sys.path.insert(0, ".")
from tartar.data.dataset import build_dataset, load_trade_tokens
from tartar.model.global_model import GlobalModel
from tartar.train import evaluate, test_log_loss, train_global
tf = int(sys.argv[1]); out_dir = sys.argv[2]; weights = [float(x) for x in sys.argv[3].split(",")]
OTHERS = ["handoff/data/raw-slots", "handoff/data/raw-slots-processed", "handoff/data/raw-pumpswap", "handoff/data/raw-eager",
          "handoff/data/raw-clever", "handoff/data/raw-clever2", "handoff/data/raw-v3", "handoff/data/raw-pred"]
ds = build_dataset(load_trade_tokens(",".join(["handoff/data/raw"] + OTHERS), tf), tf, "trades")
old = {t.mint for t in load_trade_tokens("handoff/data/raw", tf)} - {t.mint for d in OTHERS for t in load_trade_tokens(d, tf)}
is_old = np.array([t.mint in old for t in ds.tokens])[ds.token]
tr, va, te = ds.split()
created = np.array([t.created for t in ds.tokens])[ds.token]
print(f"{len(ds.tokens)} tokens, {len(ds)} rows; old-recorder share: train {is_old[tr].mean():.2f} valid {is_old[va].mean():.2f} test {is_old[te].mean():.2f}; "
      f"test launches from {np.min(created[te]):.0f}", flush=True)
w0 = ds.weight.copy()

def report(name, m):
    r = evaluate(m, ds, replay_tokens=300, log=lambda *a: None)
    live = r["live_at_open"]["global_plus_online"]; f0 = r["test_by_fraction"][0]
    pv = m.predict_proba(ds.X[va])
    valid_ll = float(-(ds.weight[va] * np.log(np.maximum(pv[np.arange(va.sum()), ds.label[va]], 1e-12))).sum() / ds.weight[va].sum())
    res = {"valid_ll": round(valid_ll, 4), "test_ll": round(test_log_loss(m, ds), 4), "open hit/stated": (round(f0["hit_rate"], 3), round(f0["avg_confidence"], 3)), "edge_open": round(f0["edge"], 4),
           "live all/trading": (live["all"]["edge"], live["trading"]["edge"]), "trading hit/stated": (live["trading"]["hit_rate"], live["trading"]["avg_confidence"]),
           "temperature": round(m.meta["temperature"], 3), "iters": m.meta["best_iteration"]}
    print(name, res, flush=True)
    return res

out = {"tokens": len(ds.tokens), "rows": len(ds), "installed v3.1": report("installed v3.1", GlobalModel.load(f"tartar/models/trades-{tf}s.txt"))}
for w in weights:
    ds.weight = np.where(tr & is_old, w0 * w, w0)
    m = train_global(ds, num_leaves=31, min_data_in_leaf=2000, log=lambda *a: None)
    ds.weight = w0
    m.meta["old_recorder_weight"] = w
    m.meta["note"] = "v3.2 study (handoff/experiments/predictor_v32.py)"
    out[f"old rows x{w:g}"] = report(f"old rows x{w:g}", m)
    m.save(f"{out_dir}/w{w:g}/trades-{tf}s")
json.dump(out, open(f"{out_dir}/v32-{tf}s.json", "w"), indent=1)
