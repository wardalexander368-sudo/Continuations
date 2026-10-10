"""Independent pre-live audit of the perps momentum strategies (paper only, no orders, reads public data).

    python3 handoff/experiments/momentum_audit.py panel      # fetch daily closes (cache in data/momentum-audit/)
    python3 handoff/experiments/momentum_audit.py backtests  # base, survivorship, stale exits, cost sensitivity
    python3 handoff/experiments/momentum_audit.py timing     # entry/exit 1 h after the daily close (hourly candles)
    python3 handoff/experiments/momentum_audit.py books      # current picks walked through live L2 books
    python3 handoff/experiments/momentum_audit.py funding    # cached daily funding vs the API, sampled coin-weeks

Rules audited (the agent's own backtest, tartar/autotrade/search.py, on the agent's own data):
  xs_momentum   14-day return, quintiles, Monday signal, enter 1 day later   (pre-registered)
  vol_momentum  14-day return / volatility, quintiles, Monday, lag 1         (pre-registered)
  cand          21-day vol-scaled, deciles, Monday, lag 2                    (search winner, paper from 10-19)
Nothing here edits autotrade/; findings go to the board for the autotrade owner.
"""
import argparse
import csv
import json
import pickle
import statistics
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, ".")
from tartar.autotrade import hl_data  # noqa: E402
from tartar.autotrade.search import COST, Panel, backtest  # noqa: E402
from tartar.autotrade.strategies.xs_momentum import MIN_HIST, MIN_VOL, rank_signal  # noqa: E402

OUT = Path("data/momentum-audit")
HL = "https://api.hyperliquid.xyz/info"
RULES = {
    "xs_momentum": {"lookback": 14, "quant": 5, "scaled": False, "signal_weekday": 0, "lag_days": 1, "leg_usd": 1000},
    "vol_momentum": {"lookback": 14, "quant": 5, "scaled": True, "signal_weekday": 0, "lag_days": 1, "leg_usd": 1000},
    "cand": {"lookback": 21, "quant": 10, "scaled": True, "signal_weekday": 0, "lag_days": 2, "leg_usd": 500},
}
HOLD = 26  # the search's holdout weeks

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=("panel", "backtests", "timing", "books", "funding", "robust"))
ap.add_argument("--scale", type=float, default=1.0, help="books: multiply each rule's leg size")
args = ap.parse_args()
http = httpx.Client(timeout=60)


def post(body):
    return hl_data.post(http, body)


def load_panel():
    d = pickle.loads((OUT / "panel.pkl").read_bytes())
    F = hl_data.load_funding(Path("autotrade/search/funding_daily.csv"))
    return d, Panel(d["days"], d["coins"], d["C"], d["V"], F)


def stats(s, hold=False):
    r = np.array([v for _, v in s][-HOLD:] if hold else [v for _, v in s])
    return 100 * r.mean(), 100 * r.std(ddof=1) / len(r) ** 0.5, len(r)


def fmt(s):
    m, se, n = stats(s)
    hm, hse, hn = stats(s, True)
    return f"all {m:+.2f}%/wk (SE {se:.2f}, n={n}); last {hn} wk {hm:+.2f}% (SE {hse:.2f})"


def panel():
    OUT.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date()
    days, coins, C, V, live = hl_data.load_daily(http, today)
    meta = post({"type": "meta"})["universe"]
    delisted = sorted(u["name"] for u in meta if u.get("isDelisted"))
    (OUT / "panel.pkl").write_bytes(pickle.dumps({"days": days, "coins": coins, "C": C, "V": V, "delisted": delisted}))
    print(f"{len(coins)} coins, {len(days)} days to {days[-1]}, {len(delisted)} delisted")


def picks(P, p, i):
    L, Q = p["lookback"], p["quant"]
    e = i + p["lag_days"]
    sig = rank_signal(P.C, i, L, p["scaled"])
    ok = P.base_ok(i) & ~np.isnan(P.C[i - L]) & ~np.isnan(P.C[e]) & np.isfinite(sig)
    ids = np.where(ok)[0]
    if len(ids) < 15:
        return None, None
    order = ids[np.argsort(sig[ids])]
    q = len(order) // Q
    return order[-q:], order[:q]


def backtests():
    d, P = load_panel()
    delisted = set(d["delisted"])
    print("== Base (the search's own backtest, 20 bps/side + funding) ==")
    base = {}
    for k, p in RULES.items():
        base[k] = backtest(P, p)
        print(f"  {k:<13} {fmt(base[k])}")

    print("== Survivorship: delisted coins dropped from the panel (if results rose, delisted coins were hurting; the base keeps them) ==")
    keep = [j for j, c in enumerate(P.coins) if c not in delisted]
    P2 = Panel(P.days, [P.coins[j] for j in keep], P.C[:, keep], P.V[:, keep], hl_data.load_funding(Path("autotrade/search/funding_daily.csv")))
    for k, p in RULES.items():
        print(f"  {k:<13} {fmt(backtest(P2, p))}")

    print("== Delisted coins actually traded, and exits on a forward-filled (stale) close ==")
    col = {c: j for j, c in enumerate(P.coins)}
    for k, p in RULES.items():
        n_leg = n_del = n_stale = n_stale_live = 0
        for i, day in enumerate(P.days):
            if day.weekday() != p["signal_weekday"] or day < date(2023, 7, 3) or i < max(MIN_HIST, 30, p["lookback"]):
                continue
            e, x = i + p["lag_days"], i + p["lag_days"] + 7
            if x >= len(P.days):
                break
            lo, sh = picks(P, p, i)
            if lo is None:
                continue
            for j in list(lo) + list(sh):
                n_leg += 1
                if P.coins[j] in delisted:
                    n_del += 1
                if np.isnan(P.C[x, j]):
                    n_stale += 1
                    if P.coins[j] not in delisted:
                        n_stale_live += 1
        print(f"  {k:<13} {n_leg} coin-legs; on coins now delisted {n_del}; exit on a stale close {n_stale} (on live coins {n_stale_live})")

    print("== Cost sensitivity (per side, per unit turnover) ==")
    for k, p in RULES.items():
        row = []
        for c in (0.0005, 0.001, 0.002, 0.004, 0.006):
            row.append(f"{1e4 * c:.0f} bps {stats(backtest(P, p, cost=c), True)[0]:+.2f}")
        print(f"  {k:<13} last {HOLD} wk: " + ", ".join(row))

    print("== Funding: without it, and with missing-funding coins (JELLY, PONS, USELESS) ==")
    for k, p in RULES.items():
        nf = backtest(P, p, funding=False)
        print(f"  {k:<13} no funding: {fmt(nf)}")
    json.dump({k: [(d0.isoformat(), v) for d0, v in s] for k, s in base.items()}, (OUT / "base.json").open("w"))


def hourly(coin, t0, t1):
    rows = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h", "startTime": t0, "endTime": t1}}) or []
    return {int(x["t"]) // 1000: (float(x["o"]), float(x["c"])) for x in rows}


def timing():
    """Re-price every leg's entry and exit at the close of the hour AFTER the daily close (what an hourly
    agent run can really get), for the weeks the hourly candles cover; compare with the base."""
    d, P = load_panel()
    end = datetime.now(timezone.utc)
    t1 = int(end.timestamp() * 1000)
    t0 = t1 - 4990 * 3600_000  # Hyperliquid serves the last 5000 candles
    first_day = (datetime.fromtimestamp(t0 / 1000, timezone.utc) + timedelta(days=2)).date()
    cache = OUT / "hourly.pkl"
    H = pickle.loads(cache.read_bytes()) if cache.exists() else {}
    need = set()
    for k, p in RULES.items():
        for i, day in enumerate(P.days):
            if day.weekday() != p["signal_weekday"] or day < first_day:
                continue
            if i + p["lag_days"] + 7 >= len(P.days):
                break
            lo, sh = picks(P, p, i)
            if lo is not None:
                need |= {P.coins[j] for j in list(lo) + list(sh)}
    for c in sorted(need - set(H)):
        H[c] = hourly(c, t0, t1)
        time.sleep(0.15)
    cache.write_bytes(pickle.dumps(H))
    print(f"hourly candles for {len(need)} coins from {first_day}")
    for lag_h in (1, 2):
        print(f"== Entry and exit {lag_h} h after the daily close vs at the close (same weeks, 20 bps, funding as base) ==")
        for k, p in RULES.items():
            a, b = [], []
            prev_a, prev_b = {}, {}
            for i, day in enumerate(P.days):
                if day.weekday() != p["signal_weekday"] or day < first_day:
                    continue
                e, x = i + p["lag_days"], i + p["lag_days"] + 7
                if x >= len(P.days):
                    break
                lo, sh = picks(P, p, i)
                if lo is None:
                    continue
                q = len(lo)
                te = int(datetime.combine(P.days[e] + timedelta(days=1), datetime.min.time(), timezone.utc).timestamp())
                tx = int(datetime.combine(P.days[x] + timedelta(days=1), datetime.min.time(), timezone.utc).timestamp())
                fund = P.fund_cum[x] - P.fund_cum[e]
                ra, rb, okall = 0.0, 0.0, True
                for j, s in [(j, 1) for j in lo] + [(j, -1) for j in sh]:
                    h = H.get(P.coins[j], {})
                    he, hx = h.get(te + (lag_h - 1) * 3600), h.get(tx + (lag_h - 1) * 3600)
                    if not he or not hx or np.isnan(P.C[x, j]):
                        okall = False
                        break
                    ra += s * (P.C[x, j] / P.C[e, j] - 1) - s * fund[j]
                    rb += s * (hx[1] / he[1] - 1) - s * fund[j]
                if not okall:
                    continue
                w = {**{int(j): 1 / q for j in lo}, **{int(j): -1 / q for j in sh}}
                turn = sum(abs(w.get(m, 0) - prev_a.get(m, 0)) for m in set(w) | set(prev_a)) / 2
                prev_a = w
                a.append(ra / q - 2 * COST * turn)
                b.append(rb / q - 2 * COST * turn)
            if a:
                diff = np.array(b) - np.array(a)
                print(f"  {k:<13} {len(a)} weeks: at close {100 * np.mean(a):+.2f}%/wk, +{lag_h} h {100 * np.mean(b):+.2f}%/wk, "
                      f"difference {100 * diff.mean():+.2f} (SE {100 * diff.std(ddof=1) / len(diff) ** 0.5:.2f})")


def books():
    """Walk each rule's current picks (latest signal Monday) through the live L2 book at its real leg size."""
    d, P = load_panel()
    i = max(k for k, day in enumerate(P.days) if day.weekday() == 0 and k + 2 < len(P.days))
    print(f"signal day {P.days[i]}; taker fee 4.5 bps (base tier) added to the book walk")
    for k, p in RULES.items():
        p2 = dict(p, lag_days=0)  # entry-close filter: use the signal day itself (later closes may not exist yet)
        lo, sh = picks(P, p2, i)
        q = len(lo)
        per_coin = args.scale * p["leg_usd"] / q
        costs = []
        for j, s in [(j, 1) for j in lo] + [(j, -1) for j in sh]:
            c = P.coins[j]
            bids, asks = post({"type": "l2Book", "coin": c})["levels"]
            mid = (float(bids[0]["px"]) + float(asks[0]["px"])) / 2
            book = asks if s > 0 else bids
            need, got_usd, got_sz = per_coin, 0.0, 0.0
            for lvl in book:
                px, sz = float(lvl["px"]), float(lvl["sz"])
                take = min(sz, (need - got_usd) / px)
                got_sz += take
                got_usd += take * px
                if got_usd >= need - 1e-9:
                    break
            avg = got_usd / got_sz if got_sz else float("nan")
            slip = s * (avg / mid - 1)
            costs.append((c, s, 1e4 * slip + 4.5, got_usd >= need - 1e-6))
            time.sleep(0.1)
        v = [x[2] for x in costs]
        worst = sorted(costs, key=lambda x: -x[2])[:3]
        print(f"  {k:<13} {2 * q} coins at ${per_coin:,.0f} each: cost per side median {statistics.median(v):.1f} bps, "
              f"mean {statistics.mean(v):.1f}, max {max(v):.1f}; worst {[(c, round(b, 1)) for c, _, b, _ in worst]}"
              f"{'' if all(x[3] for x in costs) else '; SOME BOOKS TOO THIN'}")


def funding():
    """Spot-check the cached daily funding sums against fresh hourly funding history."""
    F = hl_data.load_funding(Path("autotrade/search/funding_daily.csv"))
    rng = np.random.default_rng(7)
    coins = [c for c in F if F[c]]
    diffs = []
    for c in rng.choice(coins, 12, replace=False):
        days = sorted(F[c])
        d0 = date.fromisoformat(days[int(rng.integers(len(days) // 2, len(days) - 8))])
        t0 = int(datetime.combine(d0, datetime.min.time(), timezone.utc).timestamp() * 1000)
        part = post({"type": "fundingHistory", "coin": c, "startTime": t0, "endTime": t0 + 8 * 86400_000}) or []
        hourly = {x["time"] // 3600_000: float(x["fundingRate"]) for x in part}
        for k in range(7):
            day = d0 + timedelta(days=k)
            h0 = t0 // 3600_000 + 24 * k
            api = sum(hourly.get(h, 0.0) for h in range(h0 + 1, h0 + 25))
            diffs.append(abs(api - F[c].get(day.isoformat(), 0.0)))
        time.sleep(0.2)
    print(f"{len(diffs)} coin-days: max |cache - API| {max(diffs):.2e}, mean {statistics.mean(diffs):.2e}")


def robust():
    """Do a few coin-weeks or weeks carry the result? Leg returns capped at +-50% / +-25%, the median week,
    and the mean without the best 5 weeks (same legs, costs and funding as the base)."""
    d, P = load_panel()
    for k, p in RULES.items():
        base = {d0: v for d0, v in backtest(P, p)}
        out = {50: [], 25: []}
        for i, day in enumerate(P.days):
            if day not in base:
                continue
            e, x = i + p["lag_days"], i + p["lag_days"] + 7
            lo, sh = picks(P, p, i)
            ret = P.Cf[x] / P.C[e] - 1
            for cap in out:
                rc = np.clip(ret, -cap / 100, cap / 100)
                adj = (np.mean(rc[lo]) - np.mean(ret[lo])) + (-np.mean(rc[sh]) + np.mean(ret[sh]))
                out[cap].append(base[day] + adj)
        v = np.array(list(base.values()))
        top5 = np.sort(v)[-5:]
        print(f"  {k:<13} base {100 * v.mean():+.2f}%/wk, median week {100 * np.median(v):+.2f}%, without best 5 weeks "
              f"{100 * np.sort(v)[:-5].mean():+.2f}% (best 5: {', '.join(f'{100 * t:+.0f}%' for t in top5)}); "
              f"legs capped +-50% {100 * np.mean(out[50]):+.2f}, +-25% {100 * np.mean(out[25]):+.2f}")


{"panel": panel, "backtests": backtests, "timing": timing, "books": books, "funding": funding, "robust": robust}[args.mode]()
