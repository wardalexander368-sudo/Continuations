"""Forward scorer for `handoff/preregistration/cde-vol-momentum/SPEC.md`: D3 on Coinbase's US-perp coins.

    python3 handoff/experiments/edge-hunt/perps/cde_forward.py CACHE_DIR [--from 2026-10-12 --to 2027-10-11] [--final]

Downloads Coinbase Exchange daily candles for the 23 coins (public, full history, so nothing is
recorded live) into CACHE_DIR, then scores `xs_coinbase.py`'s exact rule: long-short quintiles of
14-day return / 14-day daily std among the coins with 60 days of history and 30-day median volume
>= $1M, signal Monday close, executed Tuesday close, 20 bps per side of turnover.
"""
from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

import numpy as np

COINS = ["BTC", "ETH", "SOL", "XRP", "ADA", "AVAX", "LINK", "LTC", "DOT", "DOGE", "BCH", "NEAR", "SUI", "HYPE",
         "BNB", "AAVE", "ONDO", "XLM", "ENA", "HBAR", "PEPE", "SHIB", "ZEC"]
cache = Path(sys.argv[1]); cache.mkdir(parents=True, exist_ok=True)
a = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "2026-10-12"
b = sys.argv[sys.argv.index("--to") + 1] if "--to" in sys.argv else "2027-10-11"
final = "--final" in sys.argv  # retain the CLI flag before xs_coinbase argument rewriting
if "--no-fetch" not in sys.argv:
    import httpx
    c = httpx.Client(timeout=30)
    for k in COINS:
        rows, t, now = {}, int(dt.datetime(2019, 1, 1, tzinfo=dt.timezone.utc).timestamp()), int(time.time())
        while t < now:
            t1 = min(t + 299 * 86400, now)
            for i in range(5):
                r = c.get(f"https://api.exchange.coinbase.com/products/{k}-USD/candles", params={"granularity": 86400,
                          "start": dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(), "end": dt.datetime.fromtimestamp(t1, dt.timezone.utc).isoformat()})
                if r.status_code in (200, 404):
                    break
                time.sleep(2 * (i + 1))
            if r.status_code == 200:
                for ts, lo, hi, op, cl, v in r.json():
                    rows[ts] = (cl, v * cl)
            elif r.status_code == 404:
                print(f"{k}: unavailable Coinbase candles {t}..{t1} (HTTP 404; coverage unknown)")
            else:
                r.raise_for_status()  # exhausted retries must not turn into an apparently valid cache
                raise RuntimeError(f"{k}: exhausted Coinbase candle retries {t}..{t1} (unexpected HTTP {r.status_code})")
            t = t1 + 86400
            time.sleep(0.2)
        (cache / f"{k}.csv").write_text("".join(f"{dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()},{rows[ts][0]},{rows[ts][1]}\n" for ts in sorted(rows)))
sys.argv = [sys.argv[0], str(cache)]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import xs_coinbase as X  # noqa: E402

rs = [x for x in X.run(X.sig_vmom, "ls", 0.0020) if a <= x[0] <= b]
x = np.array([r for _, r in rs])
if len(x) < 2:
    print(f"{a}..{b}: {len(x)} weeks"); sys.exit()
rng = np.random.default_rng(1); B = 4
bs = [x[np.concatenate([np.arange(s, s + B) % len(x) for s in rng.integers(0, len(x), len(x) // B + 1)])[: len(x)]].mean() for _ in range(10000)]
lo, hi = np.percentile(bs, [5, 95])
line = f"{a}..{b}: {len(x)} weeks, mean {x.mean() * 100:+.2f}%/week after 20 bp/side, 90% CI [{lo * 100:+.2f}, {hi * 100:+.2f}]"
if final:
    line += "  " + ("SUCCESS" if x.mean() > 0 and lo > 0 else "FAIL")
print(line)
