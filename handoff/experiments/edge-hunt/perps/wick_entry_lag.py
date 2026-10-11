"""Wick-bounce entry-lag cost (drags review 2026-10-11): signals from Binance 1h klines with the registered
rule (6-sigma wick, 168 h sigma, 4 h hold, one position per coin), entry and exit priced from 5-minute bars
at 0..60 min after the hour, 8.5 bps per side.  python3 handoff/experiments/edge-hunt/perps/wick_entry_lag.py [cache_dir]"""
import json, sys, time, concurrent.futures as cf
from pathlib import Path
import httpx, numpy as np
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "data/wick-entry-lag"); OUT.mkdir(parents=True, exist_ok=True)
API = "https://data-api.binance.vision/api/v3/klines"
COINS = ["ADA","APT","ARB","AVAX","BCH","BNB","BTC","DOGE","DOT","ETH","INJ","LINK","LTC","NEAR","OP","SEI","SOL","SUI","TIA","XRP"]
START = int(time.mktime(time.strptime("2022-12-20", "%Y-%m-%d"))) * 1000
END = int(time.mktime(time.strptime("2026-10-01", "%Y-%m-%d"))) * 1000
cli = httpx.Client(timeout=30)
def kl(sym, iv, start, end, limit=1000):
    out = []
    while start < end:
        for a in range(5):
            try:
                r = cli.get(API, params={"symbol": sym + "USDT", "interval": iv, "startTime": start, "endTime": end, "limit": limit}); r.raise_for_status(); break
            except Exception:
                time.sleep(2 * (a + 1))
        rows = r.json()
        if not rows: break
        out += rows; start = rows[-1][0] + 1
        if len(rows) < limit: break
    return out
def hourly(c):
    f = OUT / f"{c}-1h.json"
    if not f.exists(): f.write_text(json.dumps(kl(c, "1h", START, END)))
    return c, json.loads(f.read_text())
with cf.ThreadPoolExecutor(6) as ex: H = dict(ex.map(hourly, COINS))
sigs = []
for c, rows in H.items():
    t = np.array([r[0] // 3600000 for r in rows]); o, hi, lo, cl = (np.array([float(r[k]) for r in rows]) for k in (1, 2, 3, 4))
    busy = -1
    for i in range(169, len(t) - 5):
        if t[i] - t[i - 168] != 168 or t[i + 4] - t[i] != 4: continue
        R = cl[i - 168:i] / cl[i - 169:i - 1] - 1; s = R.std()
        lw = (min(o[i], cl[i]) - lo[i]) / o[i] >= 6 * s; uw = (hi[i] - max(o[i], cl[i])) / o[i] >= 6 * s
        if lw == uw or i < busy: continue
        sigs.append((c, int(t[i]), 1 if lw else -1, float(cl[i]), float(cl[i + 4]))); busy = i + 4
print(len(sigs), "signals")
LAGS = [0, 5, 10, 15, 20, 25, 30, 45, 60]
def five(sig):
    c, h, side, c0, c4 = sig
    f = OUT / f"{c}-{h}-5m.json"
    if not f.exists():
        a = (h + 1) * 3600000; f.write_text(json.dumps(kl(c, "5m", a, a + 6 * 3600000, 100)))
    rows = {r[0]: float(r[1]) for r in json.loads(f.read_text())}
    a = (h + 1) * 3600000; b = (h + 5) * 3600000
    res = {}
    for L in LAGS:
        pe, px = rows.get(a + L * 60000), rows.get(b + L * 60000)
        if pe and px: res[L] = side * (px / pe - 1) - 0.0017
    res["reg"] = side * (c4 / c0 - 1) - 0.0017
    res["entry_only20"] = (side * (c4 / rows[a + 1200000] - 1) - 0.0017) if rows.get(a + 1200000) else None
    return h, res
with cf.ThreadPoolExecutor(6) as ex: rs = list(ex.map(five, sigs))
def show(sel, name):
    print(name, len(sel))
    for L in ["reg"] + LAGS + ["entry_only20"]:
        x = np.array([r[L] for _, r in sel if r.get(L) is not None]) * 1e4
        print(f"  lag {L}: mean {x.mean():+.0f} bp  median {np.median(x):+.0f}  n {len(x)}")
show(rs, "all 2023-01..2026-09")
show([r for r in rs if r[0] * 3600 >= time.mktime(time.strptime("2025-01-01", "%Y-%m-%d"))], "test 2025-01..2026-09")
rng = np.random.default_rng(1)
for L in (10, 20):
    d = np.array([r[L] - r[0] for _, r in rs]) * 1e4
    bs = [rng.choice(d, len(d)).mean() for _ in range(5000)]
    print(f"lag {L} minus lag 0: {d.mean():+.0f} bp, 90% CI [{np.percentile(bs,5):+.0f}, {np.percentile(bs,95):+.0f}]")
