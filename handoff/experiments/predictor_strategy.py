"""Can the installed candle predictor (v3.1) plus P(rug) be traded at real costs?

Every candle open of every recorded launch is a decision point (rows at elapsed
fraction 0, built the way the live agent sees a token: creator and launch time
known, no late join, no dead-row subsampling). At each open the installed global
model gives a distribution of the candle's close; signals derived from it:

* `p_clear`: P(close / price now - 1 > hurdle), the chance the candle alone clears
  a round trip's cost (hurdle 3.5%, profitability §3.1);
* `er_trim`: expected return with z clipped to the model's outer bin edges (the
  untrimmed mean is dominated by the fat upper tail, §3.2);
* `p_up`: P(close > price now).

A launch's P(rug) is the installed 20 s model on the launch's state 20 s after it
was seen (`decide.launch_states`), usable only by decisions at or after that moment.
Decisions earlier than `min_age` seconds after launch are excluded (launch entry is
another study's lane).

Trade: buy `size` SOL at decision + latency on the recorded curve, sell at the
candle's close (decision + timeframe), costs as `profit.Costs`. One position per
token at a time; exits after a recording cut are dropped (profit.run_policy).

    python3 handoff/experiments/predictor_strategy.py explore DIR [DIR...] --tf 60
    python3 handoff/experiments/predictor_strategy.py evaluate DIR [DIR...]   # the pre-registered rule, once
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tartar.data.dataset import build_dataset, load_trade_tokens  # noqa: E402
from tartar.decide import launch_states  # noqa: E402
from tartar.model.global_model import EDGES, find_model  # noqa: E402
from tartar.profit import Costs, Exit, curves_for, run_policy, summarize  # noqa: E402
from tartar.rug import SCREEN, find_rug_model  # noqa: E402

HURDLE = 0.035
PREREG = Path(__file__).resolve().parents[1] / "preregistration" / "predictor-strategy"


def signals(model, ds) -> dict[str, np.ndarray]:
    probs = model.predict_proba(ds.X)
    s = ds.sigma * np.sqrt(1.0 - ds.f)
    p_still, bins = probs[:, 0], probs[:, 1:]
    lo = np.concatenate([[EDGES[0] - 1.0], EDGES])
    hi = np.concatenate([EDGES, [EDGES[-1] + 1.0]])
    mid = (lo + hi) / 2.0
    # trimmed expected return: each bin at its midpoint, outer bins one unit beyond the last edge
    er = p_still + (bins * np.exp(s[:, None] * mid[None, :])).sum(axis=1) - 1.0
    p_up = bins[:, mid > 0].sum(axis=1)
    # P(z > z*), z* = log(1 + hurdle) / s, uniform within bins, exponential tails as in BinnedDistribution
    zstar = math.log1p(HURDLE) / s
    tail_high = model.meta.get("tail_high", 1.0)
    p_clear = np.zeros(len(s))
    for k in range(bins.shape[1]):
        if k == bins.shape[1] - 1:
            frac = np.where(zstar <= EDGES[-1], 1.0, np.exp(-(zstar - EDGES[-1]) / tail_high))
        elif k == 0:
            frac = (zstar < EDGES[0]).astype(float)
        else:
            a, b = EDGES[k - 1], EDGES[k]
            frac = np.clip((b - zstar) / (b - a), 0.0, 1.0)
        p_clear += bins[:, k] * frac
    return {"p_clear": p_clear, "er_trim": er, "p_up": p_up}


def load(dirs: list[str], tf: int):
    tokens = load_trade_tokens(dirs, tf, min_candles=0)
    ds = build_dataset(tokens, tf, "trades", fractions=(0.0,), mask_creator=0.0, mask_launch=0.0, late_join=0.0, dead_keep=1.0)
    curves = curves_for(tokens)
    rug = find_rug_model()
    states = launch_states(tokens, curves, SCREEN)
    prug = np.full(len(tokens), np.nan)
    if rug is not None and states:
        prug[[s["token"] for s in states]] = rug.predict_many(states)
    created = np.array([t.created for t in tokens])
    return tokens, ds, curves, prug, created


def trade(ds, curves, take, costs, tf):
    return run_policy(curves, ds.token[take], ds.time[take], np.ones(int(take.sum()), bool), costs, Exit(tf - costs.latency))


def row(name, trades, costs):
    s = summarize(trades, costs)
    return {"rule": name, "trades": s.trades, "tokens": s.tokens, "mean": s.mean_ret, "ci": (s.ci_low, s.ci_high), "win": s.win_rate, "sol": s.total_sol}


def show(r):
    if not r["trades"]:
        print(f"  {r['rule']:<48} no trades")
        return
    print(f"  {r['rule']:<48} n={r['trades']:>5} tok={r['tokens']:>4} mean {100 * r['mean']:+6.2f}% "
          f"[{100 * r['ci'][0]:+6.2f}, {100 * r['ci'][1]:+6.2f}] win {100 * r['win']:4.1f}% sol {r['sol']:+.3f}")  # fmt: skip


def explore(dirs, tf, min_age, part_split=0.6):
    costs = Costs()
    tokens, ds, curves, prug, created = load(dirs, tf)
    model = find_model("trades", tf)
    sig = signals(model, ds)
    age = ds.time - created[ds.token]
    pr = prug[ds.token]
    order = np.argsort(created)
    first = np.zeros(len(tokens), bool)
    first[order[: int(part_split * len(tokens))]] = True
    base = (age >= min_age) & ~np.isnan(pr)
    print(f"{len(tokens)} launches, {len(ds)} open rows, {int(base.sum())} at age >= {min_age:g}s with P(rug); tf {tf}s")
    for part, pm in (("choose (earlier 60%)", first[ds.token]), ("check (later 40%)", ~first[ds.token])):
        print(part)
        m = base & pm
        show(row("every open", trade(ds, curves, m, costs, tf), costs))
        for name, score in sig.items():
            for q in (0.9, 0.98, 0.995):
                thr = float(np.quantile(score[base & first[ds.token]], q))
                for rcap in (1.0, 0.3, 0.1):
                    take = m & (score > thr) & (pr < rcap)
                    show(row(f"{name} top {100 * (1 - q):g}% (>{thr:.3g}), P(rug)<{rcap:g}", trade(ds, curves, take, costs, tf), costs))


def evaluate(dirs, count_only=False):
    """The pre-registered test (SPEC.json), run once on launches created after registration."""
    import hashlib

    spec = json.loads((PREREG / "SPEC.json").read_text())
    for name, digest in spec["model_sha256"].items():
        got = hashlib.sha256((Path(__file__).resolve().parents[2] / "tartar" / "models" / name).read_bytes()).hexdigest()
        assert got == digest, f"{name} changed since registration"
    c = spec["costs"]
    costs = Costs(size_sol=c["size_sol"], fee=c["fee_per_side"], network_sol=c["network_sol"], latency=c["latency_s"])
    out = {"spec": spec["rules"], "results": []}
    for r in spec["rules"]:
        tf = r["timeframe_s"]
        tokens, ds, curves, prug, created = load(dirs, tf)
        sig = signals(find_model("trades", tf), ds)
        age = ds.time - created[ds.token]
        fresh = created[ds.token] >= spec["registered_at_unix"]
        take = fresh & (age >= spec["min_age_s"]) & (sig[r["signal"]] > r["threshold"]) & (prug[ds.token] < r["max_p_rug"])
        trades = trade(ds, curves, take, costs, tf)
        if count_only:
            print(f"{r['role']}: {len(trades)} trades on {int((created >= spec['registered_at_unix']).sum())} fresh launches")
            continue
        res = row(r["name"], trades, costs)
        res["launches"] = int((created >= spec["registered_at_unix"]).sum())
        res["role"] = r["role"]
        show(res)
        out["results"].append(res)
        # addendum 2026-10-09 19:55 UTC: the same decisions at measured real costs (Lightning 1%/side, ~1.4 s landing)
        real = Costs(size_sol=c["size_sol"], fee=c["fee_per_side"] + 0.01, network_sol=c["network_sol"], latency=1.4)
        res2 = row(r["name"] + " @ real costs", trade(ds, curves, take, real, tf), real)
        res2["role"] = r["role"] + " (addendum, not a criterion)"
        show(res2)
        out["results"].append(res2)
    if not count_only:
        print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["explore", "evaluate"])
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--tf", type=int, default=60)
    ap.add_argument("--min-age", type=float, default=SCREEN)
    ap.add_argument("--count-only", action="store_true")
    a = ap.parse_args()
    if a.cmd == "evaluate":
        evaluate(a.dirs, a.count_only)
    else:
        explore(a.dirs, a.tf, a.min_age)
