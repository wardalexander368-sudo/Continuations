"""Execution check on the real route: for each fresh paper entry on a Solana token, ask Jupiter's
Swap API (the route chosen in profitability §3.19) for a quote of the same USD size, and record the
quoted price impact and route beside the paper fill. The fill itself is unchanged (the registered
cost model decides it); the check shows whether that cost model is realistic at our size."""

from __future__ import annotations

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
JUP = "https://lite-api.jup.ag/swap/v1/quote"


def quote_check(intent, now: float, http=None, max_age: float = 3900.0) -> dict | None:
    """{"jup_impact_pct", "jup_route", "jup_out", "jup_at"} for a fresh open on a Solana mint, else None."""
    mint = intent.meta.get("mint")
    if intent.kind != "open" or not mint or now - intent.at > max_age:
        return None
    import httpx

    client = http or httpx.Client(timeout=15)
    try:
        r = client.get(JUP, params={"inputMint": USDC, "outputMint": mint, "amount": int(intent.notional_usd * 1e6),
                                     "slippageBps": 300})
        q = r.json()
        if "outAmount" not in q:
            return {"jup_error": str(q.get("error") or q)[:200], "jup_at": now}
        return {"jup_impact_pct": float(q.get("priceImpactPct") or 0.0) * 100,
                "jup_route": [p["swapInfo"].get("label") for p in q.get("routePlan", [])],
                "jup_out": q.get("outAmount"), "jup_at": now}
    except Exception as exc:  # noqa: BLE001 - a failed check never blocks a paper fill
        return {"jup_error": f"{type(exc).__name__}: {exc}"[:200], "jup_at": now}
