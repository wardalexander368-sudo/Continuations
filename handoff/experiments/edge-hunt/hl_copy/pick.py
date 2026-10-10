"""E2 selection on period A only (handoff/preregistration/hl-copy/SPEC.md).

    python3 handoff/experiments/edge-hunt/hl_copy/pick.py rank      # portfolio rules 1-4 -> ranking.json
    python3 handoff/experiments/edge-hunt/hl_copy/pick.py final     # + followability (needs fills) -> selection.json

`rank` prints the addresses whose fills `final` needs (fetch them with fetch.py fills ...).
"""
import gzip
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

CACHE = Path("data/hl-copy")
OUT = Path("handoff/data/edge-hunt/hl-copy")
A0 = datetime(2026, 5, 1, tzinfo=timezone.utc).timestamp() * 1000
A1 = datetime(2026, 8, 20, tzinfo=timezone.utc).timestamp() * 1000
FILLS_FROM = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp() * 1000
WEEK = 7 * 86400 * 1000
AV_MIN, AV_MAX, MIN_WEEKS, N_SEL, N_PLACEBO, MAX_FILLS = 1e4, 5e7, 10, 20, 60, 3000


def interp(series, t):
    xs = np.array([p[0] for p in series], dtype=float)
    ys = np.array([float(p[1]) for p in series])
    if len(xs) == 0 or t < xs[0] or t > xs[-1]:
        return None
    return float(np.interp(t, xs, ys))


def stats(addr):
    p = CACHE / "portfolio" / f"{addr}.json.gz"
    if not p.exists():
        return None
    d = dict(json.loads(gzip.decompress(p.read_bytes())))
    av, pnl = d["allTime"]["accountValueHistory"], d["perpAllTime"]["pnlHistory"]
    grid = np.arange(A0, A1 + 1, WEEK)  # 17 points, 16 weeks
    avs = [interp(av, t) for t in grid]
    pns = [interp(pnl, t) for t in grid]
    if None in avs or None in pns:
        return {"addr": addr, "ok": False, "why": "history doesn't cover A"}
    avs, pns = np.array(avs), np.array(pns)
    dp = np.diff(pns)
    out = {"addr": addr, "av_a0": avs[0], "pnl_a": float(pns[-1] - pns[0]), "weeks_active": int((np.abs(dp) > 1e-6).sum())}
    if not (AV_MIN <= avs[0] <= AV_MAX):
        return {**out, "ok": False, "why": "account value at A start outside $10k-$50M"}
    if out["weeks_active"] < MIN_WEEKS:
        return {**out, "ok": False, "why": "fewer than 10 active weeks"}
    base = np.maximum(avs[:-1], 1.0)
    r = dp / base
    out.update(ok=True, sharpe=float(r.mean() / r.std()) if r.std() > 0 else 0.0, ret_mean=float(r.mean()))
    return out


def followable(addr):
    p = CACHE / "fills" / f"{addr}.json.gz"
    if not p.exists():
        return None
    fills = [f for f in json.loads(gzip.decompress(p.read_bytes())) if FILLS_FROM <= f["time"] < A1]
    perp = [f for f in fills if not f["coin"].startswith("@") and ":" not in f["coin"] and f["coin"] != "PURR/USDC"]
    return len(fills) <= MAX_FILLS and len(perp) >= 1, len(fills)


def rank():
    pool = json.loads((OUT / "pool.json").read_text())["pool"]
    rows = [s for s in (stats(a) for a in pool) if s]
    elig = [r for r in rows if r["ok"]]
    ranked = sorted((r for r in elig if r["pnl_a"] > 0), key=lambda r: -r["sharpe"])
    why = {}
    for r in rows:
        if not r["ok"]:
            why[r["why"]] = why.get(r["why"], 0) + 1
    placebo_cand = random.Random(20261011).sample(sorted(r["addr"] for r in elig), min(150, len(elig)))
    (OUT / "ranking.json").write_text(json.dumps({"have": len(rows), "eligible_1_2": len(elig), "excluded": why,
                                                  "ranked": ranked, "placebo_candidates": placebo_cand}, indent=0))
    print(f"{len(rows)} portfolios, {len(elig)} pass rules 1-2, {len(ranked)} with P&L > 0 in A; excluded {why}")
    need = [r["addr"] for r in ranked[:80]] + placebo_cand
    print(" ".join(dict.fromkeys(need)))


def final():
    rk = json.loads((OUT / "ranking.json").read_text())
    sel, skipped = [], []
    for r in rk["ranked"]:
        f = followable(r["addr"])
        if f is None:
            raise SystemExit(f"fills missing for {r['addr']}")
        if f[0]:
            sel.append({**r, "fills_jun_a1": f[1]})
        else:
            skipped.append({"addr": r["addr"], "fills_jun_a1": f[1]})
        if len(sel) == N_SEL:
            break
    plac = []
    for a in rk["placebo_candidates"]:
        f = followable(a)
        if f and f[0]:
            plac.append(a)
        if len(plac) == N_PLACEBO:
            break
    (OUT / "selection.json").write_text(json.dumps({"selected": sel, "skipped_unfollowable": skipped, "placebo": plac}, indent=0))
    print(f"selected {len(sel)} (skipped {len(skipped)} as unfollowable), placebo {len(plac)}")


if __name__ == "__main__":
    {"rank": rank, "final": final}[sys.argv[1]]()
