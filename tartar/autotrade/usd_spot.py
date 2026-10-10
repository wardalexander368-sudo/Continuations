"""USD-denominated spot twins on Solana: buy a token with USDC and sell it back to USDC through Jupiter.

Used for legs whose paper position is in USD and must stay in proportion to other legs, such as the hedged
JLP basket's JLP leg (its perp hedges are sized in USD on Hyperliquid). Intents with
``meta["venue"] == "jupiter_usd"`` and a ``mint`` get this twin.

* ``dry`` (mode ``dry_live``): the fill is Jupiter's quote at that moment (USDC -> token, token -> USDC), less a
  network fee in USD per leg. Nothing is signed or sent; no key.
* ``jupiter`` (mode ``live`` with ``TARTAR_WALLET_KEY``): the same Jupiter Swap API path as the SOL twins
  (``execution.py``: ``check_tx`` before signing, the shared live gate re-checked right before each send,
  confirmed / failed / unknown outcomes), paying and receiving USDC held in that wallet. The fill is read
  from the confirmed transaction (USDC and token balance changes).

Restart safety is the SOL twins' (``safety.py``): the broker records each leg in ``pending.json`` before
sending, and the startup reconcile counts these twins' tokens in the same wallet. The dry route moves the
token in the simulated wallet (``dry_wallet.json``) so that reconcile covers it too.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .execution import SOL, USDC, Chain, Quotes, check_tx, send_signed

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
    unknown: bool = False  # sent, but whether it landed is not known: treat as possibly filled
    signature: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class DryUsdSpotExecutor:
    name = "dry"

    def __init__(self, quotes: Quotes | None = None, clock=time.time):
        self.quotes = quotes or Quotes()
        self.clock = clock
        self.path = None

    def attach(self, path) -> None:
        """Move bought and sold tokens in the dry route's simulated wallet (``dry_wallet.json``)."""
        from pathlib import Path

        self.path = Path(path)

    def _move(self, mint: str, raw: int) -> None:
        if self.path:
            sim_wallet_move(self.path, mint, raw)

    def buy(self, mint: str, usd: float) -> UsdFill:
        try:
            q = self.quotes.quote(USDC, mint, int(round(usd * 1e6)))
        except Exception as exc:  # noqa: BLE001
            return UsdFill("dry", "buy", mint, False, at=self.clock(), dry=True, error=f"{type(exc).__name__}: {exc}"[:200])
        self._move(mint, int(q["outAmount"]))
        return UsdFill("dry", "buy", mint, True, usd=usd + NETWORK_FEE_USD, token_raw=int(q["outAmount"]), fee_usd=NETWORK_FEE_USD,
                       price_impact_pct=float(q.get("priceImpactPct") or 0) * 100, at=self.clock(), dry=True)

    def sell(self, mint: str, token_raw: int) -> UsdFill:
        try:
            q = self.quotes.quote(mint, USDC, token_raw)
        except Exception as exc:  # noqa: BLE001
            return UsdFill("dry", "sell", mint, False, at=self.clock(), dry=True, error=f"{type(exc).__name__}: {exc}"[:200])
        self._move(mint, -token_raw)
        return UsdFill("dry", "sell", mint, True, usd=int(q["outAmount"]) / 1e6 - NETWORK_FEE_USD, token_raw=token_raw,
                       fee_usd=NETWORK_FEE_USD, price_impact_pct=float(q.get("priceImpactPct") or 0) * 100, at=self.clock(), dry=True)


def sim_wallet_move(path, mint: str, raw: int) -> None:
    """Add ``raw`` of ``mint`` to the simulated wallet file (the dry SOL route's format; SOL untouched)."""
    import json

    w = json.loads(path.read_text()) if path.exists() else {"sol": 0.05, "tokens": {}}
    left = int(w["tokens"].get(mint, 0)) + int(raw)
    if left > 0:
        w["tokens"][mint] = left
    else:
        w["tokens"].pop(mint, None)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(w, indent=1, sort_keys=True))
    tmp.replace(path)


class LiveUsdSpotExecutor:
    """USDC <-> token on Jupiter, signed with ``TARTAR_WALLET_KEY``. ``guard`` is the shared live gate."""

    name = "jupiter"

    def __init__(self, secret: str | None = None, quotes: Quotes | None = None, chain: Chain | None = None,
                 priority_sol: float = 0.00002, clock=time.time):
        import os

        from solders.keypair import Keypair

        secret = secret or os.environ.get("TARTAR_WALLET_KEY")
        if not secret:
            raise RuntimeError("TARTAR_WALLET_KEY is not set")
        self.keypair = Keypair.from_base58_string(secret.strip())
        self.wallet = str(self.keypair.pubkey())
        self.quotes, self.chain = quotes or Quotes(), chain or Chain()
        self.priority_sol, self.clock = priority_sol, clock
        self.guard = None

    def holdings(self, mints) -> dict[str, int]:
        return {m: self.chain.held(self.wallet, m)[0] for m in mints}

    def _swap(self, leg: str, mint: str, amount: int) -> UsdFill:
        pair = (USDC, mint) if leg == "buy" else (mint, USDC)
        at = self.clock()
        try:
            q = self.quotes.quote(*pair, amount)
            raw, last_valid = self.quotes.swap(q, self.wallet, self.priority_sol)
            check_tx(raw, self.wallet)
        except Exception as exc:  # noqa: BLE001 - nothing was sent
            return UsdFill(self.name, leg, mint, False, at=at, error=f"{type(exc).__name__}: {exc}"[:300])
        f = send_signed(self.chain, self.keypair, self.name, leg, mint, raw, self.wallet, int(q["outAmount"]), last_valid,
                        guard=self.guard, counter=USDC)
        if not f.ok:
            return UsdFill(self.name, leg, mint, False, at=at, unknown=f.unknown, signature=f.signature, error=f.error,
                           extra={"quote_out": int(q["outAmount"])})
        usdc = f.extra["counter_change"]
        try:
            fee_usd = f.fee_sol * int(self.quotes.quote(SOL, USDC, 10**9)["outAmount"]) / 1e6
        except Exception:  # noqa: BLE001
            fee_usd = NETWORK_FEE_USD
        usd = (-usdc / 1e6 + fee_usd) if leg == "buy" else (usdc / 1e6 - fee_usd)
        return UsdFill(self.name, leg, mint, True, usd=usd, token_raw=f.token_raw, fee_usd=fee_usd,
                       price_impact_pct=float(q.get("priceImpactPct") or 0) * 100, at=at, signature=f.signature,
                       extra={"fee_sol": f.fee_sol, "rent_sol": f.rent_sol, "quote_out": int(q["outAmount"])})

    def buy(self, mint: str, usd: float) -> UsdFill:
        return self._swap("buy", mint, int(round(usd * 1e6)))

    def sell(self, mint: str, token_raw: int) -> UsdFill:
        return self._swap("sell", mint, int(token_raw))


def make_usd_spot_executor(route: str, env=None, priority_sol: float = 0.00002):
    if route == "dry":
        return DryUsdSpotExecutor()
    if route == "jupiter":
        import os

        env = os.environ if env is None else env
        return LiveUsdSpotExecutor(secret=env.get("TARTAR_WALLET_KEY"), priority_sol=priority_sol)
    raise ValueError(f"USD spot route {route!r} is not built")
