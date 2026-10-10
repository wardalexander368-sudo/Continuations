"""Spot-perp funding carry on Hyperliquid (edge hunt E3): fetch the data.

Universe: Hyperliquid spot pairs quoted in USDC with at least $1M of spot volume in the last day (2026-10-10),
whose base token maps to a Hyperliquid perp (UBTC -> BTC, UETH -> ETH, USOL -> SOL, UZEC -> ZEC, UPUMP -> PUMP,
UENA -> ENA, HYPE, PURR). For each: hourly candles of the spot pair and the perp since START, hourly funding,
and today's books (cost per side at $1,000: fee + half spread + impact).

    python3 handoff/experiments/edge-hunt/spotcarry/fetch.py   -> handoff/data/edge-hunt/spotcarry/
"""
import gzip
import json
import time
from pathlib import Path

import httpx

U = "https://api.hyperliquid.xyz/info"
OUT = Path("handoff/data/edge-hunt/spotcarry")
START = 1773532800000  # 2026-03-15 00:00 UTC (hourly candles reach back 5,000 hours)
MIN_SPOT_VLM = 1e6
ALIAS = {"UBTC": "BTC", "UETH": "ETH", "USOL": "SOL", "UZEC": "ZEC", "UPUMP": "PUMP", "UENA": "ENA", "UFART": "FARTCOIN",
         "HPENGU": "PENGU", "UBONK": "kBONK"}
SPOT_TAKER, PERP_TAKER, PROBE_USD = 7e-4, 4.5e-4, 1000.0
c = httpx.Client(timeout=60)


def post(body):
    for i in range(6):
        r = c.post(U, json=body)
        if r.status_code == 200:
            return r.json()
        time.sleep(5 * (i + 1))
    r.raise_for_status()


def side_cost(levels, usd, mid):
    got, cost = 0.0, 0.0
    for lv in levels:
        px, sz = float(lv["px"]), float(lv["sz"])
        take = min(sz, (usd - got) / px)
        got += take * px
        cost += take * abs(px - mid)
        if got >= usd - 1e-9:
            return cost / usd
    return None  # book thinner than the probe


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sm, ctx = post({"type": "spotMetaAndAssetCtxs"})
    perps = {u["name"] for u in post({"type": "meta"})["universe"]}
    toks = {t["index"]: t["name"] for t in sm["tokens"]}
    cx = {x["coin"]: x for x in ctx}
    pairs = []
    for u in sm["universe"]:
        base, quote = toks[u["tokens"][0]], toks[u["tokens"][1]]
        perp = ALIAS.get(base, base)
        if quote == "USDC" and perp in perps and float(cx.get(u["name"], {}).get("dayNtlVlm") or 0) >= MIN_SPOT_VLM:
            pairs.append({"spot": u["name"], "base": base, "perp": perp, "spot_vlm": float(cx[u["name"]]["dayNtlVlm"])})
    now = int(time.time() * 1000)
    for p in pairs:
        for key, coin in (("spot", p["spot"]), ("perp", p["perp"])):
            rows = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h", "startTime": START, "endTime": now}}) or []
            p[f"{key}_candles"] = [[r["t"], float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"])] for r in rows]
            book = post({"type": "l2Book", "coin": coin})["levels"]
            mid = (float(book[0][0]["px"]) + float(book[1][0]["px"])) / 2
            buy, sell = side_cost(book[1], PROBE_USD, mid), side_cost(book[0], PROBE_USD, mid)
            fee = SPOT_TAKER if key == "spot" else PERP_TAKER
            p[f"{key}_cost_side"] = None if buy is None or sell is None else fee + max(buy, sell)
            time.sleep(1)
        f, s = {}, START
        while s < now:
            part = post({"type": "fundingHistory", "coin": p["perp"], "startTime": s, "endTime": now}) or []
            f.update({x["time"]: float(x["fundingRate"]) for x in part})
            if len(part) < 500:
                break
            s = part[-1]["time"] + 1
            time.sleep(0.5)
        p["funding"] = sorted(f.items())
        print(p["spot"], p["base"], p["perp"], len(p["spot_candles"]), len(p["perp_candles"]), len(p["funding"]),
              p["spot_cost_side"], p["perp_cost_side"], flush=True)
    (OUT / "data.json.gz").write_bytes(gzip.compress(json.dumps({"fetched": now, "pairs": pairs}).encode()))


if __name__ == "__main__":
    main()
