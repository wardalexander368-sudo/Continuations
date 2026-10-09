"""Daily candles for every Hyperliquid perp, delisted ones included (survivorship-light universe).

    python3 handoff/experiments/edge-hunt/crosssection/fetch_hl_daily.py [--out handoff/data/edge-hunt/hl-daily]

Writes one CSV per coin (day, open, high, low, close, volume in coins) and meta.json (universe with
isDelisted). Hyperliquid perps listed from 2023; 234 coins on 2026-10-09, 56 delisted.
"""
import argparse, csv, json, time
from pathlib import Path
import httpx

HL = "https://api.hyperliquid.xyz/info"
p = argparse.ArgumentParser(); p.add_argument("--out", default="handoff/data/edge-hunt/hl-daily"); a = p.parse_args()
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
c = httpx.Client(timeout=60)
def post(body):
    for i in range(6):
        r = c.post(HL, json=body)
        if r.status_code == 200: return r.json()
        time.sleep(2 * (i + 1))
    r.raise_for_status()
meta = post({"type": "meta"})
(out / "meta.json").write_text(json.dumps(meta["universe"], indent=1))
end = int(time.time() * 1000); n = 0
for u in meta["universe"]:
    rows = post({"type": "candleSnapshot", "req": {"coin": u["name"], "interval": "1d", "startTime": 1672531200000, "endTime": end}}) or []
    with (out / f"{u['name']}.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["day", "open", "high", "low", "close", "volume"])
        for x in rows:
            w.writerow([time.strftime("%Y-%m-%d", time.gmtime(x["t"] / 1000)), x["o"], x["h"], x["l"], x["c"], x["v"]])
    n += bool(rows); time.sleep(0.3)
print(f"{len(meta['universe'])} coins, {n} with candles -> {out}")
