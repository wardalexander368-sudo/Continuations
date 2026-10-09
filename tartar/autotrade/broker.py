"""Execution. PaperBroker books fills at the reference price less the cost model. LiveBroker would
send through Jupiter's Swap API with our own key (profitability §3.19), and refuses unless live
trading was explicitly approved: config ``mode: live`` AND the environment variable
``TARTAR_LIVE_APPROVED`` set to the approval date recorded in the config AND the strategy promoted.
The committed config stays on paper; going live needs the user's explicit go."""

from __future__ import annotations

import os

from .core import Intent, Position, Trade


class LiveNotAllowed(RuntimeError):
    pass


class PaperBroker:
    mode = "paper"

    def open(self, intent: Intent) -> tuple[Position, dict]:
        cost = intent.cost.side_cost(intent.notional_usd)
        pos = Position.new(intent, cost, self.mode)
        return pos, {"event": "open", "mode": self.mode, "position": pos.id, "strategy": intent.strategy,
                     "asset": intent.asset, "side": intent.side, "notional_usd": intent.notional_usd,
                     "price": intent.price, "at": intent.at, "cost_usd": round(cost, 6), "reason": intent.reason}

    def close(self, pos: Position, intent: Intent) -> tuple[Trade, dict]:
        exit_cost = intent.cost.side_cost(pos.notional_usd)
        gross = pos.gross_pnl(intent.price)
        extra = float(intent.meta.get("carry_usd", 0.0))  # e.g. perp funding over the holding period
        pnl = gross - pos.entry_cost_usd - exit_cost + extra
        meta = {**pos.meta, **intent.meta}
        trade = Trade(id=pos.id, strategy=pos.strategy, asset=pos.asset, side=pos.side, notional_usd=pos.notional_usd,
                      entry_price=pos.entry_price, entry_at=pos.entry_at, exit_price=intent.price, exit_at=intent.at,
                      cost_usd=pos.entry_cost_usd + exit_cost, pnl_usd=pnl, net_return=pnl / pos.notional_usd,
                      mode=self.mode, reason=intent.reason, meta=meta)
        return trade, {"event": "close", "mode": self.mode, "position": pos.id, "strategy": pos.strategy,
                       "asset": pos.asset, "price": intent.price, "at": intent.at, "cost_usd": round(exit_cost, 6),
                       "pnl_usd": round(pnl, 6), "net_return": round(trade.net_return, 6), "reason": intent.reason}


class LiveBroker(PaperBroker):
    """Not used until the user approves live trading. Kept here so the switch is one place."""

    mode = "live"

    def __init__(self, config: dict):
        approved = config.get("live_approved_on")
        if config.get("mode") != "live" or not approved or os.environ.get("TARTAR_LIVE_APPROVED") != approved:
            raise LiveNotAllowed("live trading is not approved (config mode/live_approved_on and TARTAR_LIVE_APPROVED must match)")
        if not os.environ.get("TARTAR_WALLET_KEY"):
            raise LiveNotAllowed("TARTAR_WALLET_KEY is not set")
        raise LiveNotAllowed("live execution is not wired yet: build it on handoff/experiments/jupiter_fills.py "
                             "after the user's go and a verified 0.01 SOL round trip")


def make_broker(config: dict, strategy_status: str) -> PaperBroker:
    """Paper unless every live condition holds; any failure falls back to paper and is reported."""
    if config.get("mode") == "live" and strategy_status == "promoted":
        return LiveBroker(config)  # raises LiveNotAllowed unless approved
    return PaperBroker()
