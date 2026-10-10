"""Execution check on the real route: for each fresh paper entry on a Solana token, ask Jupiter's
Swap API (the route chosen in profitability §3.19) for a quote of the same USD size, and record the
measured price impact and route beside the paper fill. The fill itself is unchanged (the registered
cost model decides it); the check shows whether that cost model is realistic at our size.

Jupiter's ``priceImpactPct`` is not usable as impact: it is measured against a reference price and
already reads 0.7-2.6% for a $1 order on the cohort pools (checked 2026-10-09). So the impact is
measured as the shortfall of the full-size quote against a $1 probe quote of the same token:
``1 - (out_N / N) / (out_1 / 1)``. Jupiter's own figure is kept as ``jup_reported_impact_pct``."""

from __future__ import annotations

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
JUP = "https://lite-api.jup.ag/swap/v1/quote"
PROBE_USD = 1.0


def quote_check(intent, now: float, http=None, max_age: float = 3900.0) -> dict | None:
    """{"jup_impact_measured_pct", "jup_reported_impact_pct", "jup_route", "jup_out", "jup_at"} for a
    fresh open on a Solana mint, else None."""
    mint = intent.meta.get("mint")
    if intent.kind != "open" or not mint or now - intent.at > max_age:
        return None
    import httpx

    client = http or httpx.Client(timeout=15)

    def quote(usd: float) -> dict:
        return client.get(JUP, params={"inputMint": USDC, "outputMint": mint, "amount": int(usd * 1e6),
                                       "slippageBps": 300}).json()

    try:
        q, probe = quote(intent.notional_usd), quote(PROBE_USD)
        if "outAmount" not in q or "outAmount" not in probe:
            bad = q if "outAmount" not in q else probe
            return {"jup_error": str(bad.get("error") or bad)[:200], "jup_at": now}
        per_usd, per_usd_probe = int(q["outAmount"]) / intent.notional_usd, int(probe["outAmount"]) / PROBE_USD
        return {"jup_impact_measured_pct": 100 * (1 - per_usd / per_usd_probe),
                "jup_reported_impact_pct": float(q.get("priceImpactPct") or 0.0) * 100,
                "jup_route": [p["swapInfo"].get("label") for p in q.get("routePlan", [])],
                "jup_out": q.get("outAmount"), "jup_at": now}
    except Exception as exc:  # noqa: BLE001 - a failed check never blocks a paper fill
        return {"jup_error": f"{type(exc).__name__}: {exc}"[:200], "jup_at": now}
