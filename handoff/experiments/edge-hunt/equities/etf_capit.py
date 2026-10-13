"""US ETF capitulation bounce: does buying a liquid US ETF after a crash-sized daily drop on heavy volume pay
after Alpaca's equity costs (no commission; ~5 bp/side spread and slippage)?

Asked by AJ 2026-10-13 ("approved for all", after handoff/reviews/perfect-system-2026-10-13.md gap 1). Same shape as
the crypto CAPIT study (edge-hunt §K) on daily bars, which suit the hourly runner (an order before the next open).

Pre-specified before any result was seen:
* Universe: 28 liquid US-listed ETFs (index, sector, industry, country); ETFs, not stocks, so today's survivors
  don't bias the sample.
* Signal on day t's close: return_t / stdev(returns t-60..t-1) <= -Z AND volume_t >= V x median(volume t-20..t-1).
* Trade: buy at day t+1's open, sell at day t+H's close (H trading days after the signal), 5 bp/side.
* Family: Z in {2, 2.5, 3} x V in {1.5, 2} x H in {1, 3, 5} = 18 rules. The rule is picked on TRAIN only.
* Splits by signal date (bars are fetched from 2003 so the 60-day stdev is warm by 2005): train 2005-01-01..2016-12-31, validation 2017..2021, test 2022-01-01..end.
* Control: the same ETF entered at every day within +-60 trading days of the signal, same hold and cost (exact
  mean); excess = trade - control. CIs: 90% bootstrap over signal DAYS (crash days hit many ETFs at once).
* Pass (for paper registration): picked rule's excess and net both > 0 on validation AND test, test excess CI lower > 0.

    python3 etf_capit.py DATA_DIR      # fetches Yahoo daily bars into DATA_DIR once, then reports
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ETFS = ["SPY", "QQQ", "IWM", "DIA", "MDY", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "SMH",
        "XBI", "KRE", "XHB", "XRT", "ITB", "GDX", "EEM", "EFA", "FXI", "EWJ", "EWZ", "IYR", "IBB"]
COST = 0.0005
SPLITS = [("train", "2005-01-01", "2016-12-31"), ("validation", "2017-01-01", "2021-12-31"), ("test", "2022-01-01", "2100-01-01")]
GRID = [(z, v, h) for z in (2.0, 2.5, 3.0) for v in (1.5, 2.0) for h in (1, 3, 5)]
CONTROL = 60


def fetch(sym: str, d: Path) -> dict:
    f = d / f"{sym}.json"
    if not f.exists():
        import httpx

        r = httpx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                      params={"period1": 1041379200, "period2": int(time.time()), "interval": "1d", "events": "div,split"},
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        q, adj = res["indicators"]["quote"][0], res["indicators"]["adjclose"][0]["adjclose"]
        rows = [(t, o, c, a, v) for t, o, c, a, v in zip(res["timestamp"], q["open"], q["close"], adj, q["volume"])
                if None not in (o, c, a, v) and o > 0 and c > 0 and v > 0]
        f.write_text(json.dumps(rows))
        time.sleep(0.5)
    rows = json.loads(f.read_text())
    t, o, c, a, v = (np.array(x, dtype=float) for x in zip(*rows))
    k = a / c  # dividend/split adjustment, applied to the open too
    days = np.array([time.strftime("%Y-%m-%d", time.gmtime(x)) for x in t])
    return {"day": days, "open": o * k, "close": a, "vol": v}


def trades(s: dict, z: float, v: float, h: int) -> list[tuple[str, float, float]]:
    c, o, vol, day = s["close"], s["open"], s["vol"], s["day"]
    r = np.r_[np.nan, c[1:] / c[:-1] - 1]
    out = []
    n = len(c)
    hold = lambda i: (c[i + h] / o[i + 1]) * (1 - COST) ** 2 - 1  # noqa: E731  buy t+1 open, sell t+h close
    for t in range(61, n - h):
        sd = np.nanstd(r[t - 60:t], ddof=1)
        if not (sd > 0 and r[t] / sd <= -z and vol[t] >= v * np.median(vol[t - 20:t])):
            continue
        lo, hi = max(1, t - CONTROL), min(n - h - 1, t + CONTROL)
        ctrl = np.mean([hold(i) for i in range(lo, hi + 1)])
        out.append((day[t], hold(t), hold(t) - ctrl))
    return out


def summarize(rows, B: int = 5000) -> dict:
    if not rows:
        return {"n": 0}
    days = sorted({d for d, _, _ in rows})
    by = {d: [] for d in days}
    for d, net, ex in rows:
        by[d].append((net, ex))
    rng = np.random.default_rng(1)
    pick = rng.integers(0, len(days), (B, len(days)))
    out = {"n": len(rows), "days": len(days)}
    for j, k in ((0, "net"), (1, "excess")):
        tot = np.array([sum(x[j] for x in by[d]) for d in days])
        cnt = np.array([len(by[d]) for d in days])
        boot = tot[pick].sum(1) / cnt[pick].sum(1)
        out[k] = float(tot.sum() / cnt.sum())
        out[k + "_ci"] = [float(np.percentile(boot, 5)), float(np.percentile(boot, 95))]
    return out


def main(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    data = {s: fetch(s, d) for s in ETFS}
    res = {}
    for z, v, h in GRID:
        rows = [x for s in ETFS for x in trades(data[s], z, v, h)]
        res[(z, v, h)] = {name: summarize([x for x in rows if a <= x[0] <= b]) for name, a, b in SPLITS}
    best = max(GRID, key=lambda g: res[g]["train"].get("excess", -9) if res[g]["train"]["n"] >= 30 else -9)
    pct = lambda x: f"{100 * x:+.2f}%"  # noqa: E731
    print(f"{len(ETFS)} ETFs, {min(s['day'][0] for s in data.values())}..{max(s['day'][-1] for s in data.values())}, cost {COST:.2%}/side")
    print("rule (Z, V, H) | split | trades/days | net [90% CI] | excess over random [90% CI]")
    for g in GRID:
        for name, _, _ in SPLITS:
            r = res[g][name]
            if r["n"]:
                print(f"{g}{' <- picked on train' if g == best and name == 'train' else ''} | {name} | {r['n']}/{r['days']} | "
                      f"{pct(r['net'])} [{pct(r['net_ci'][0])}, {pct(r['net_ci'][1])}] | "
                      f"{pct(r['excess'])} [{pct(r['excess_ci'][0])}, {pct(r['excess_ci'][1])}]")
    v, t = res[best]["validation"], res[best]["test"]
    ok = all(x.get("n") and x["net"] > 0 and x["excess"] > 0 for x in (v, t)) and t["excess_ci"][0] > 0
    print(f"PICKED {best}: {'PASS' if ok else 'FAIL'} (needs net and excess > 0 on validation and test, test excess CI lower > 0)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
