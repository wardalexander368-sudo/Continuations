"""USD-denominated spot twins on Solana: buy a token with USDC and sell it back to USDC through Jupiter.

Used for legs whose paper position is in USD and must stay in proportion to other legs, such as the hedged
JLP basket's JLP leg (its perp hedges are sized in USD on Hyperliquid). Intents with
``meta["venue"] == "jupiter_usd"`` and a ``mint`` get this twin.

* ``dry`` (mode ``dry_live``): the fill is Jupiter's quote at that moment (USDC -> token, token -> USDC), less a
  network fee in USD per leg. Nothing is signed or sent; no key.
* live: **not built.** It would be Jupiter's Swap API signed with ``TARTAR_WALLET_KEY`` (as the SOL twins),
  with USDC held in that wallet.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .execution import USDC, Quotes

NETWORK_FEE_USD = 0.003  # base fee + priority per transaction, about 0.000025 SOL


def is_usd_spot(meta: dict) -> bool:
    return meta.get("venue") == "jupiter_usd"


@dataclass
class UsdFill:
    route: str
    leg: str  # "buy" | "sell"
    mint: str
    ok: bool
    usd: float = 0.0          # USDC spent (buy) or received (sell), network fee included
    token_raw: int = 0
    fee_usd: float = 0.0
    price_impact_pct: float | None = None
    at: float = 0.0
    dry: bool = False
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class DryUsdSpotExecutor:
    name = "dry"

    def __init__(self, quotes: Quotes | None = None, clock=time.time):
        self.quotes = quotes or Quotes()
        self.clock = clock

    def buy(self, mint: str, usd: float) -> UsdFill:
        try:
            q = self.quotes.quote(USDC, mint, int(round(usd * 1e6)))
        except Exception as exc:  # noqa: BLE001
            return UsdFill("dry", "buy", mint, False, at=self.clock(), dry=True, error=f"{type(exc).__name__}: {exc}"[:200])
        return UsdFill("dry", "buy", mint, True, usd=usd + NETWORK_FEE_USD, token_raw=int(q["outAmount"]), fee_usd=NETWORK_FEE_USD,
                       price_impact_pct=float(q.get("priceImpactPct") or 0) * 100, at=self.clock(), dry=True)

    def sell(self, mint: str, token_raw: int) -> UsdFill:
        try:
            q = self.quotes.quote(mint, USDC, token_raw)
        except Exception as exc:  # noqa: BLE001
            return UsdFill("dry", "sell", mint, False, at=self.clock(), dry=True, error=f"{type(exc).__name__}: {exc}"[:200])
        return UsdFill("dry", "sell", mint, True, usd=int(q["outAmount"]) / 1e6 - NETWORK_FEE_USD, token_raw=token_raw,
                       fee_usd=NETWORK_FEE_USD, price_impact_pct=float(q.get("priceImpactPct") or 0) * 100, at=self.clock(), dry=True)


def make_usd_spot_executor(route: str):
    if route == "dry":
        return DryUsdSpotExecutor()
    raise ValueError(f"USD spot route {route!r} is not built")
