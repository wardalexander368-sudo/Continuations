"""PumpPortal real-time websocket: every trade on a pump.fun token, and new launches.

Free for pump.fun bonding-curve trades. Prices are in SOL. PumpPortal asks
clients to reuse a single connection; set PUMPPORTAL_API_KEY if your account
needs a key (e.g. for PumpSwap trades after a token graduates).
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterable

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from ..candles import Tick
from ..clock import Clock
from .base import Event, LiveFeed, Status

WS_URL = "wss://pumpportal.fun/api/data"
PUMP_TOTAL_SUPPLY = 1_000_000_000


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def message_price(msg: dict) -> float | None:
    """Spot price in SOL after the trade (bonding-curve reserves), else the fill price."""
    v_sol, v_tokens = _float(msg.get("vSolInBondingCurve")), _float(msg.get("vTokensInBondingCurve"))
    if v_sol and v_tokens and v_sol > 0 and v_tokens > 0:
        return v_sol / v_tokens
    sol, tokens = _float(msg.get("solAmount")), _float(msg.get("tokenAmount"))
    if sol and tokens and sol > 0 and tokens > 0:
        return sol / tokens
    mcap = _float(msg.get("marketCapSol"))
    if mcap and mcap > 0:
        return mcap / PUMP_TOTAL_SUPPLY
    return None


def tick_from_message(msg: dict, now: float) -> Tick | None:
    side = msg.get("txType")
    if side not in ("buy", "sell"):
        return None
    price = message_price(msg)
    if price is None:
        return None
    sol = _float(msg.get("solAmount")) or 0.0
    return Tick(
        now,
        price,
        volume=sol,
        buy_volume=sol if side == "buy" else 0.0,
        sell_volume=sol if side == "sell" else 0.0,
    )


@dataclass(frozen=True)
class NewToken:
    mint: str
    name: str
    symbol: str
    price: float | None
    market_cap_sol: float | None
    initial_buy_sol: float | None
    creator: str
    pool: str


def new_token_from_message(msg: dict) -> NewToken | None:
    if msg.get("txType") != "create" or not msg.get("mint"):
        return None
    return NewToken(
        mint=str(msg["mint"]),
        name=str(msg.get("name") or ""),
        symbol=str(msg.get("symbol") or ""),
        price=message_price(msg),
        market_cap_sol=_float(msg.get("marketCapSol")),
        initial_buy_sol=_float(msg.get("solAmount")),
        creator=str(msg.get("traderPublicKey") or ""),
        pool=str(msg.get("pool") or "pump"),
    )


def _url(url: str, api_key: str | None) -> str:
    key = api_key if api_key is not None else os.environ.get("PUMPPORTAL_API_KEY")
    return f"{url}?api-key={key}" if key else url


class PumpPortalFeed(LiveFeed):
    """Streams trades for one mint."""

    name = "pumpportal"
    close_grace = 1.5

    def __init__(
        self,
        mint: str,
        *,
        url: str = WS_URL,
        api_key: str | None = None,
        clock: Clock | None = None,
        initial: Iterable[Tick] = (),
        max_backoff: float = 30.0,
    ):
        self.mint = mint
        self.url = _url(url, api_key)
        self.clock = clock or Clock()
        self._initial = list(initial)
        self._max_backoff = max_backoff

    async def events(self) -> AsyncIterator[Event]:
        for tick in self._initial:
            yield tick
        backoff = 1.0
        while True:
            try:
                async with connect(self.url, open_timeout=15, ping_interval=20) as ws:
                    await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": [self.mint]}))
                    yield Status("connected to PumpPortal trade stream")
                    backoff = 1.0
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except ValueError:
                            continue
                        if not isinstance(msg, dict):
                            continue
                        if msg.get("mint") == self.mint:
                            tick = tick_from_message(msg, self.clock.now())
                            if tick is not None:
                                yield tick
                        elif msg.get("errors") or msg.get("error"):
                            yield Status(f"PumpPortal: {msg.get('errors') or msg.get('error')}", "warn")
                        elif msg.get("message"):
                            yield Status(f"PumpPortal: {msg['message']}")
            except (OSError, WebSocketException, asyncio.TimeoutError) as exc:
                yield Status(f"PumpPortal disconnected ({exc.__class__.__name__}: {exc}); retrying in {backoff:.0f}s", "warn")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self._max_backoff)


async def stream_new_tokens(url: str = WS_URL, api_key: str | None = None) -> AsyncIterator[NewToken]:
    """Yield pump.fun launches as they happen."""
    async with connect(_url(url, api_key), open_timeout=15, ping_interval=20) as ws:
        await ws.send(json.dumps({"method": "subscribeNewToken"}))
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            token = new_token_from_message(msg) if isinstance(msg, dict) else None
            if token is not None:
                yield token
