"""Edge hunt E1 data: pump.fun / PumpSwap daily fees and revenue (DefiLlama) and Hyperliquid daily
candles + hourly funding for the perps the flow might move. Writes handoff/data/edge-hunt/pumpflow/.

    python3 handoff/experiments/edge-hunt/pumpflow/fetch.py
"""
import json, time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

OUT = Path("handoff/data/edge-hunt/pumpflow")
HL = "https://api.hyperliquid.xyz/info"
COINS = ["PUMP", "SOL", "kBONK", "WIF", "POPCAT", "FARTCOIN", "kPEPE", "BTC"]
LLAMA = {f"{p}-{t}": f"https://api.llama.fi/summary/fees/{p}?dataType={t}"
         for p in ("pump.fun", "pumpswap") for t in ("dailyFees", "dailyRevenue")}


def post(c, body):
    for i in range(8):
        r = c.post(HL, json=body)
        if r.status_code == 200:
            return r.json()
        time.sleep(3 * (i + 1))
    r.raise_for_status()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    flow = {}
    with httpx.Client(timeout=60) as c:
        for k, url in LLAMA.items():
            for x in c.get(url).raise_for_status().json()["totalDataChart"]:
                d = datetime.fromtimestamp(x[0], timezone.utc).date().isoformat()
                flow.setdefault(d, {})[k] = x[1]
        (OUT / "flow.json").write_text(json.dumps(flow, sort_keys=True))
        start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        perps = {}
        for coin in COINS:
            candles, s = {}, start
            while True:
                part = post(c, {"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d", "startTime": s,
                                                                   "endTime": int(time.time() * 1000)}}) or []
                for x in part:
                    d = datetime.fromtimestamp(x["t"] / 1000, timezone.utc).date().isoformat()
                    candles[d] = {"o": float(x["o"]), "c": float(x["c"]), "v": float(x["v"]) * float(x["c"])}
                if len(part) < 500:
                    break
                s = part[-1]["t"] + 1
            fund, s = {}, start
            while True:
                part = post(c, {"type": "fundingHistory", "coin": coin, "startTime": s}) or []
                for x in part:
                    d = datetime.fromtimestamp(x["time"] / 1000, timezone.utc).date().isoformat()
                    fund[d] = fund.get(d, 0.0) + float(x["fundingRate"])
                if len(part) < 500:
                    break
                s = part[-1]["time"] + 1
                time.sleep(0.2)
            perps[coin] = {"candles": candles, "funding": fund}
            print(coin, len(candles), min(candles), len(fund))
        (OUT / "perps.json").write_text(json.dumps(perps, sort_keys=True))
    print("flow days", len(flow), min(flow), max(flow))


if __name__ == "__main__":
    main()
