"""Coinbase US perp (``-20DEC30-CDE``) top of book at the US-spot pattern trades' entries and exits (reporting only).

Coinbase Financial Markets' perps are US-tradable. ``us_capit`` pays ~0.39%/side on Alpaca spot; if the same coin's
perp is ~0.15%/side in crash hours, that is worth about half a point per trade. With ``cde_book: true`` in a
``coinbase_pattern`` strategy's config, each fresh entry and exit records the perp's best bid/ask, half-spread and
contract size in the trade meta (``cde_entry``, ``cde_exit``). Public endpoints, no key, no order; any failure just
leaves the snapshot out. Exchange fees are not included (half-spread only).
"""

from __future__ import annotations

import time

API = "https://api.coinbase.com/api/v3/brokerage/market"
_PRODUCTS: dict[str, tuple[str, float]] = {}  # coin -> (product id, contract size in coins), once per process


def _client(http):
    if http is not None:
        return http
    import httpx

    return httpx.Client(timeout=15)


def products(http) -> dict[str, tuple[str, float]]:
    if not _PRODUCTS:
        r = http.get(f"{API}/products", params={"product_type": "FUTURE", "limit": 1000})
        for x in r.json()["products"]:
            d = x.get("future_product_details") or {}
            if x["product_id"].endswith("20DEC30-CDE") and d.get("contract_root_unit"):
                _PRODUCTS[d["contract_root_unit"]] = (x["product_id"], float(d["contract_size"]))
    return _PRODUCTS


def snapshot(http, coin: str, now: float | None = None) -> dict | None:
    """The perp's top of book now, or None (no perp for the coin, or any error)."""
    try:
        http = _client(http)
        p = products(http).get(coin)
        if not p:
            return None
        b = http.get(f"{API}/product_book", params={"product_id": p[0], "limit": 1}).json()["pricebook"]
        bid, ask = float(b["bids"][0]["price"]), float(b["asks"][0]["price"])
        mid = (bid + ask) / 2
        return {"product": p[0], "at": time.time() if now is None else now, "bid": bid, "ask": ask,
                "half_spread_bps": round(1e4 * (ask - bid) / 2 / mid, 2), "contract_usd": round(p[1] * mid, 2),
                "bid_contracts": float(b["bids"][0]["size"]), "ask_contracts": float(b["asks"][0]["size"])}
    except Exception:  # noqa: BLE001 - a measurement, never a reason to stop the strategy
        return None
