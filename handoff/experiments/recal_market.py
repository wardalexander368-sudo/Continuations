"""Market-wide recalibration of the predictor-strategy signal (2026-10-09, retrain thread).

    python3 handoff/experiments/recal_market.py prepare OUT.npz --tf 300 DIR [DIR...]
    python3 handoff/experiments/recal_market.py study OUT.npz [--split UNIX]

Why: on unseen hours the curve forecasts swing between over- and underconfident with the hour,
following market-wide drift a single-token watcher can't see (predictor doc 8.4.1, 8.2.2e). This
asks whether a calibration layer fitted on *recently resolved decisions across all tokens*
corrects that, and whether it helps the predictor-strategy rule (p_clear: P(candle clears a 3.5%
round trip)) after real costs.

`prepare` builds the predictor-strategy decision rows (`predictor_strategy.load` / `signals`,
the installed model) and, for each row, its outcome y = close / price_now - 1 > 3.5%, and its net
trade return at two cost levels (`profit.run_policy`): curve fees 1.25%/side via Jupiter or our own
instructions (profitability §3.19), and Lightning (+1%/side, 1.4 s landing, the real fills).

`study` fits, at each decision time t, a logistic correction logit p' = a + b * logit p on rows
that resolved before t (decision + timeframe + latency <= t) within the last W minutes, with a
ridge prior toward (a, b) = (0, 1) worth K pseudo-rows. Variants: intercept only / intercept and
slope, W in {30, 60, 120} min. Selection on the earlier hours (before --split), confirmation after.
The trading rule picks its threshold on the selection hours' top quantiles, as `explore` does.
"""

from __future__ import annotations

import argparse
import datetime
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

HURDLE = 0.035


def prepare(out: str, dirs: list[str], tf: int) -> None:
    from predictor_strategy import load, signals  # noqa: E402

    from tartar.model.global_model import find_model
    from tartar.profit import Costs, Exit, round_trip
    from tartar.rug import SCREEN

    tokens, ds, curves, prug, created = load(dirs, tf)
    sig = signals(find_model("trades", tf), ds)
    age = ds.time - created[ds.token]
    keep = (age >= SCREEN) & ~np.isnan(prug[ds.token])
    idx = np.flatnonzero(keep)
    print(f"{len(tokens)} launches, {len(ds)} open rows, {len(idx)} decisions (age >= {SCREEN:g}s with P(rug))", flush=True)
    nets = {}
    for name, costs in (("jup", Costs()), ("ltn", Costs(fee=0.0125 + 0.01, latency=1.4))):
        net = np.full(len(idx), np.nan)
        # one decision at a time: the per-token one-position rule is applied later, per rule
        for j, n in enumerate(idx):
            tr = round_trip(curves[int(ds.token[n])], float(ds.time[n]), costs, Exit(tf - costs.latency))
            if tr is not None and not tr.cut:
                net[j] = tr.pnl_sol / costs.size_sol
        nets[name] = net
        print(f"  {name}: {np.isfinite(net).sum()} decisions with a trade return", flush=True)
    y = (ds.close[idx] / ds.price_now[idx] - 1.0) > HURDLE
    np.savez_compressed(out, t=ds.time[idx], tf=tf, token=ds.token[idx], p_clear=sig["p_clear"][idx], p_up=sig["p_up"][idx],
                        er=sig["er_trim"][idx], prug=prug[ds.token[idx]], created=created[ds.token[idx]], y=y, **nets)


def lg(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def sg(x):
    return 1.0 / (1.0 + np.exp(-x))


def recalibrate(t, p, y, tf, window_min, slope, k=200.0, latency=1.0, step=60.0):
    """p' for every row from rows resolved before it, refitted once per `step` seconds of decision time."""
    L = lg(p)
    resolved = t + tf + latency
    order = np.argsort(resolved)
    rs, Lr, yr = resolved[order], L[order], y[order].astype(float)
    out = np.empty_like(p)
    ab = np.array([0.0, 1.0])
    bucket = np.floor(t / step)
    for b in np.unique(bucket):
        rows = bucket == b
        now = b * step
        lo, hi = np.searchsorted(rs, now - 60.0 * window_min), np.searchsorted(rs, now)
        if hi - lo >= 20:
            x, yy = Lr[lo:hi], yr[lo:hi]
            ab = np.array([0.0, 1.0])
            for _ in range(8):  # Newton steps on the penalized log-likelihood
                q = sg(ab[0] + ab[1] * x)
                g = np.array([np.sum(yy - q), np.sum((yy - q) * x)]) - k * (ab - [0.0, 1.0])
                w = q * (1 - q)
                H = np.array([[np.sum(w), np.sum(w * x)], [np.sum(w * x), np.sum(w * x * x)]]) + k * np.eye(2)
                if not slope:
                    g[1], H[0, 1], H[1, 0], H[1, 1] = 0.0, 0.0, 0.0, 1.0
                ab = ab + np.linalg.solve(H, g)
        else:
            ab = np.array([0.0, 1.0])
        out[rows] = sg(ab[0] + ab[1] * L[rows])
    return out


def logloss(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def take_one_per_token(t, token, tf, mask):
    """One position per token at a time (the strategy's rule): skip a decision while the token's last one is open."""
    busy: dict[int, float] = {}
    keep = np.zeros(len(t), bool)
    for i in np.flatnonzero(mask)[np.argsort(t[mask], kind="stable")]:
        if t[i] >= busy.get(int(token[i]), -1e18):
            keep[i] = True
            busy[int(token[i])] = t[i] + tf
    return keep


def summary(net, token):
    ok = np.isfinite(net)
    net, token = net[ok], token[ok]
    if len(net) == 0:
        return "n=0"
    rng = np.random.default_rng(1)
    toks = np.unique(token)
    by = {u: net[token == u] for u in toks}
    means = []
    for _ in range(2000):  # bootstrap by token
        pick = rng.choice(toks, len(toks))
        v = np.concatenate([by[u] for u in pick])
        means.append(v.mean())
    lo, hi = np.quantile(means, [0.05, 0.95])
    return f"n={len(net):>5} tok={len(toks):>4} mean {100 * net.mean():+6.2f}% [{100 * lo:+6.2f}, {100 * hi:+6.2f}]"


def study(path: str, split: float | None) -> None:
    d = np.load(path)
    t, tf, p, y, token, prug = d["t"], float(d["tf"]), d["p_clear"], d["y"].astype(float), d["token"], d["prug"]
    if split is None:
        split = float(np.quantile(d["created"], 0.6))
    sel, chk = d["created"] < split, d["created"] >= split
    hrs = lambda m: f"{datetime.datetime.fromtimestamp(t[m].min(), datetime.UTC):%H:%M}-{datetime.datetime.fromtimestamp(t[m].max(), datetime.UTC):%H:%M}"
    print(f"tf {tf:g}s: {len(t)} decisions; selection {sel.sum()} ({hrs(sel)}), confirmation {chk.sum()} ({hrs(chk)}); "
          f"clear rate {y.mean():.3f}, mean p_clear {p.mean():.3f}")  # fmt: skip
    hour = np.floor(t / 3600)
    print("  by hour: observed clear rate vs mean p_clear")
    for h in np.unique(hour):
        m = hour == h
        print(f"    {datetime.datetime.fromtimestamp(h * 3600, datetime.UTC):%H}  n {m.sum():>6}  {y[m].mean():.3f} vs {p[m].mean():.3f}")
    variants = {"raw": p}
    for slope in (False, True):
        for w in (30, 60, 120):
            variants[f"{'a+b' if slope else 'a'} W{w}"] = recalibrate(t, p, y, tf, w, slope)
    print("\n  calibration of p_clear (log loss; mean predicted vs observed), selection / confirmation")
    for name, q in variants.items():
        print(f"    {name:<10} {logloss(q[sel], y[sel]):.4f} ({q[sel].mean():.3f} vs {y[sel].mean():.3f})  /  "
              f"{logloss(q[chk], y[chk]):.4f} ({q[chk].mean():.3f} vs {y[chk].mean():.3f})")  # fmt: skip
    for cost in ("jup", "ltn"):
        net = d[cost]
        print(f"\n  trading at {'Jupiter / own instructions (curve fees 1.25%/side)' if cost == 'jup' else 'Lightning (+1%/side, 1.4 s)'}: "
              "threshold = a top quantile of the selection hours' score, P(rug) cap")  # fmt: skip
        every = take_one_per_token(t, token, tf, chk)
        print(f"    every decision (confirmation)            {summary(net[every], token[every])}")
        for name, q in variants.items():
            for qq in (0.9, 0.98, 0.995):
                thr = float(np.quantile(q[sel], qq))
                for cap in (1.0, 0.3):
                    for part, pm in (("sel", sel), ("chk", chk)):
                        take = take_one_per_token(t, token, tf, pm & (q > thr) & (prug < cap))
                        print(f"    {name:<10} top {100 * (1 - qq):>4.1f}% P(rug)<{cap:<3g} {part}  {summary(net[take], token[take])}")


def regime(path: str, split: float | None = None, window_min: float = 60.0) -> None:
    """Market-regime gate: trade only when the market's recent realized clear rate (rows resolved in
    the last `window_min` minutes, all tokens) is above a quantile of the selection hours'."""
    d = np.load(path)
    t, tf, p, y, token, prug = d["t"], float(d["tf"]), d["p_clear"], d["y"].astype(float), d["token"], d["prug"]
    split = float(np.quantile(d["created"], 0.6)) if split is None else split
    sel, chk = d["created"] < split, d["created"] >= split
    resolved = t + tf + 1.0
    order = np.argsort(resolved)
    rs, ys = resolved[order], np.concatenate([[0.0], np.cumsum(y[order])])
    lo, hi = np.searchsorted(rs, t - 60 * window_min), np.searchsorted(rs, t)
    rate = np.where(hi - lo >= 20, (ys[hi] - ys[lo]) / np.maximum(hi - lo, 1), np.nan)
    print(f"tf {tf:g}s, W{window_min:g}: recent clear rate quantiles (selection) {np.nanquantile(rate[sel], [0.25, 0.5, 0.75]).round(3)}")
    for cost in ("jup", "ltn"):
        net = d[cost]
        print(f"  {cost}")
        for gq in (0.0, 0.5, 0.75):
            g = rate > (np.nanquantile(rate[sel], gq) if gq else -1)
            for qq in (0.0, 0.9, 0.98):
                thr = float(np.quantile(p[sel], qq)) if qq else -1
                for part, pm in (("sel", sel), ("chk", chk)):
                    take = take_one_per_token(t, token, tf, pm & g & (p > thr) & (prug < 0.3))
                    print(f"    gate>{gq:<4g} p_clear top {100 * (1 - qq):>5.1f}% P(rug)<0.3 {part}  {summary(net[take], token[take])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "study", "regime"])
    ap.add_argument("out")
    ap.add_argument("dirs", nargs="*")
    ap.add_argument("--tf", type=int, default=300)
    ap.add_argument("--split", type=float, default=None)
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(a.out, a.dirs, a.tf)
    elif a.cmd == "regime":
        regime(a.out, a.split)
    else:
        study(a.out, a.split)
