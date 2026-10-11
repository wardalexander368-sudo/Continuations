"""Do the two registered US-spot patterns hold on US coins outside the study's 11? (overall review, 2026-10-11)

Lightweight check: Coinbase HOURLY candles 2023-01..2026-10 (not the study's 15-minute ones), so entry is the
close of the hour after the signal (60 min; the study used 30, the agent's next run gets ~90) and exit H hours
later. Signals are the agent's own (tartar.autotrade.strategies.coinbase_pattern.signals, fixed constants).
Cost 0.39%/side (Alpaca). The study's 11 coins are run the same way as the calibration line.
Mean net per trade, 90% bootstrap CI over entry days (seed 1), and excess over buying every hour.

    python handoff/experiments/edge-hunt/patterns/wide_coins.py CACHE_DIR
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from tartar.autotrade.strategies.coinbase_pattern import COINS, RULES, signals  # noqa: E402

EXTRA = ["AAVE", "UNI", "SHIB", "CRV", "GRT", "XTZ", "BAT", "SUSHI", "YFI", "PEPE"]  # on Coinbase USD and Alpaca
T0, T1 = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp()) // 3600, int(datetime(2026, 10, 10, tzinfo=timezone.utc).timestamp()) // 3600
COST = 0.0039


def fetch(coin, cache: Path):
    f = cache / f"{coin}.json"
    if f.exists():
        return json.loads(f.read_text())
    out, h, http = {}, T0, httpx.Client(timeout=30)
    while h < T1:
        e = min(h + 300, T1)
        for i in range(6):
            r = http.get(f"https://api.exchange.coinbase.com/products/{coin}-USD/candles", params={
                "granularity": 3600, "start": datetime.fromtimestamp(h * 3600, timezone.utc).isoformat(),
                "end": datetime.fromtimestamp((e - 1) * 3600, timezone.utc).isoformat()})
            if r.status_code == 200:
                for ts, lo, hi, op, cl, v in r.json():
                    out[str(ts // 3600)] = [cl, v]
                break
            if r.status_code == 404:
                h = T1
                break
            time.sleep(2 * (i + 1))
        h = e
        time.sleep(0.12)
    f.write_text(json.dumps(out))
    return out


def trades(coin, cache):
    d = fetch(coin, cache)
    n = T1 - T0
    C, V = np.full(n, np.nan), np.zeros(n)
    for k, (c, v) in d.items():
        i = int(k) - T0
        if 0 <= i < n:
            C[i], V[i] = c, v
    out = {}
    for rule in RULES:
        H = RULES[rule]["hold"]
        sig = signals(rule, C, V)
        fwd = np.full(n, np.nan)
        fwd[:n - 1 - H] = C[1 + H:] / C[1:n - H] - 1  # buy close h+1, sell close h+1+H
        base = np.nanmean(fwd)
        rows, busy = [], -1
        for h in np.where(sig)[0]:
            if h < busy or np.isnan(fwd[h]):
                continue
            rows.append((datetime.fromtimestamp((T0 + h) * 3600, timezone.utc).date().isoformat(), fwd[h] - 2 * COST, fwd[h] - base))
            busy = h + H + 1
        out[rule] = rows
    return out


def summary(rows):
    if len(rows) < 2:
        return f"{len(rows)} trades"
    by = {}
    for d, r, x in rows:
        by.setdefault(d, []).append((r, x))
    keys = list(by)
    s = np.array([sum(r for r, _ in by[k]) for k in keys])
    sx = np.array([sum(x for _, x in by[k]) for k in keys])
    c = np.array([len(by[k]) for k in keys])
    pick = np.random.default_rng(1).integers(0, len(keys), (10000, len(keys)))
    lo, hi = np.percentile(s[pick].sum(1) / c[pick].sum(1), [5, 95])
    xl, xh = np.percentile(sx[pick].sum(1) / c[pick].sum(1), [5, 95])
    m, mx = np.mean([r for _, r, _ in rows]), np.mean([x for _, _, x in rows])
    return (f"{len(rows)} trades on {len(keys)} days: net {m*100:+.2f}% [{lo*100:+.2f}, {hi*100:+.2f}], "
            f"excess over every-hour buying {mx*100:+.2f}% [{xl*100:+.2f}, {xh*100:+.2f}]")


if __name__ == "__main__":
    cache = Path(sys.argv[1])
    cache.mkdir(parents=True, exist_ok=True)
    res = {c: trades(c, cache) for c in COINS + EXTRA}
    for label, group in (("study 11 coins (calibration)", COINS), ("10 extra US coins (out of sample)", EXTRA)):
        print(f"\n## {label}")
        for rule in RULES:
            rows = [r for c in group for r in res[c][rule]]
            print(f"{rule}: {summary(rows)}")
            for yr in ("2023", "2024", "2025", "2026"):
                print(f"  {yr}: {summary([r for r in rows if r[0].startswith(yr)])}")
    print("\nper extra coin (capit / volspike trades):", {c: (len(res[c]['capit']), len(res[c]['volspike'])) for c in EXTRA})
