"""Coinbase US perps (-20DEC30-CDE): contract notional, spread, book depth and 24 h volume for the 23
cde-vol-momentum coins (gap review 2026-10-11). Public endpoints, no key.

    python3 handoff/experiments/cde_books.py
"""
import time
import httpx, json
c = httpx.Client(timeout=30)
p = c.get("https://api.coinbase.com/api/v3/brokerage/market/products", params={"product_type": "FUTURE", "limit": 1000}).json()["products"]
perp = {x["future_product_details"]["contract_root_unit"]: x for x in p if x["product_id"].endswith("20DEC30-CDE")}
COINS = "BTC ETH SOL XRP ADA AVAX LINK LTC DOT DOGE BCH NEAR SUI HYPE BNB AAVE ONDO XLM ENA HBAR PEPE SHIB ZEC".split()
rows = []
for k in COINS:
    x = perp.get(k)
    if not x:
        print(k, "no perp"); continue
    pid = x["product_id"]; size = float(x["future_product_details"]["contract_size"])
    time.sleep(0.5)
    b = c.get("https://api.coinbase.com/api/v3/brokerage/market/product_book", params={"product_id": pid, "limit": 50}).json()["pricebook"]
    bid, ask = float(b["bids"][0]["price"]), float(b["asks"][0]["price"])
    mid = (bid + ask) / 2
    notional = size * mid
    depth = sum(float(l["size"]) * size * float(l["price"]) for l in b["asks"])
    vol = float(x.get("volume_24h") or 0) * notional
    rows.append((k, pid, notional, 1e4 * (ask - bid) / mid, depth, vol))
    print(f"{k:5s} {pid:18s} contract ${notional:8.0f}  spread {1e4*(ask-bid)/mid:6.1f} bps  ask depth(50 lv) ${depth:10.0f}  24h vol ${vol:12.0f}")
pass
