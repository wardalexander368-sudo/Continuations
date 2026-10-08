"""Resolve a token mint or pool address into a live feed plus warm-up history."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .candles import Candle, format_timeframe
from .clock import Clock
from .feeds.base import LiveFeed
from .feeds.dexscreener import DexPair, DexScreener, DexScreenerFeed
from .feeds.geckoterminal import TIMEFRAMES as GECKO_TIMEFRAMES
from .feeds.geckoterminal import GeckoPool, GeckoTerminal, GeckoTerminalFeed
from .feeds.http import ApiError
from .feeds.pumpportal import PumpPortalFeed

WSOL = "So11111111111111111111111111111111111111112"
_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
SOURCES = ("auto", "pumpportal", "dexscreener", "gecko")


def short(address: str) -> str:
    return address if len(address) <= 12 else f"{address[:4]}…{address[-4:]}"


@dataclass
class MarketInfo:
    address: str  # token mint
    symbol: str
    name: str
    quote: str  # unit prices are quoted in
    source: str  # live data source
    pool: str | None = None
    dex: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class Market:
    info: MarketInfo
    feed: LiveFeed
    history: Callable[[], Awaitable[list[Candle]]] | None = None
    clock: Clock = field(default_factory=Clock)
    closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def aclose(self) -> None:
        for close in self.closers:
            await close()


class MarketNotFound(Exception):
    pass


async def _safe(coro, notes: list[str], label: str):
    try:
        return await coro
    except ApiError as exc:
        notes.append(f"{label} lookup failed: {exc}")
        return [], False


async def open_market(
    address: str,
    timeframe: int,
    source: str = "auto",
    *,
    history_limit: int = 500,
    poll: float | None = None,
    grace: float | None = None,
    gecko: GeckoTerminal | None = None,
    dex: DexScreener | None = None,
    clock: Clock | None = None,
) -> Market:
    """Look the address up on GeckoTerminal and DexScreener and pick a live source.

    auto: pump.fun tokens still on the bonding curve stream from PumpPortal
    (every trade, real time); other tokens poll DexScreener prices every few
    seconds; GeckoTerminal OHLCV polling is the fallback. Warm-up history comes
    from GeckoTerminal whenever it has the pool at this timeframe.
    """
    if source not in SOURCES:
        raise ValueError(f"source must be one of {', '.join(SOURCES)}")
    address = address.strip()
    if not _ADDRESS_RE.match(address):
        raise ValueError(f"{address!r} is not a Solana address (expected 32-44 base58 characters)")
    gecko = gecko or GeckoTerminal()
    dex = dex or DexScreener()
    try:
        return await _resolve(address, timeframe, source, history_limit, poll, grace, gecko, dex, clock or Clock())
    except BaseException:
        await gecko.aclose()
        await dex.aclose()
        raise


async def _resolve(
    address: str,
    timeframe: int,
    source: str,
    history_limit: int,
    poll: float | None,
    grace: float | None,
    gecko: GeckoTerminal,
    dex: DexScreener,
    clock: Clock,
) -> Market:
    notes: list[str] = []

    (pools, gecko_token), (pairs, dex_token) = await asyncio.gather(
        _safe(gecko.lookup(address), notes, "GeckoTerminal"), _safe(dex.lookup(address), notes, "DexScreener")
    )

    if gecko_token or dex_token:
        mint = address
    elif pairs:
        mint = pairs[0].base_address
    elif pools:
        mint = pools[0].base_token
    else:
        mint = address

    pairs = [p for p in pairs if p.base_address == mint and (p.price_usd or p.price_native)]
    pools = [p for p in pools if mint in (p.base_token, p.quote_token)]
    pair: DexPair | None = max(pairs, key=lambda p: p.liquidity_usd) if pairs else None
    pool: GeckoPool | None = max(pools, key=lambda p: p.reserve_usd) if pools else None
    if not dex_token and pairs:
        pair = next((p for p in pairs if p.address == address), pair)
    if not gecko_token and pools:
        pool = next((p for p in pools if p.address == address), pool)

    pump = mint.endswith("pump")
    if source == "auto":
        if pump and (pair is None or pair.dex == "pumpfun"):
            source = "pumpportal"
        elif pair is not None:
            source = "dexscreener"
        elif pool is not None:
            source = "gecko"
        elif any("lookup failed" in note for note in notes):
            raise MarketNotFound(f"could not look up {address}: " + "; ".join(notes))
        else:
            raise MarketNotFound(
                f"{address} was not found on DexScreener or GeckoTerminal, and is not a pump.fun mint. "
                "Check the address, or force a source with --source."
            )

    symbol = (pair.base_symbol if pair else "") or (pool.base_symbol if pool and pool.base_token == mint else "")
    name = (pair.base_name if pair else "") or (pool.base_name if pool and pool.base_token == mint else "")
    quote = "SOL" if source == "pumpportal" else "USD"

    if source == "pumpportal":
        feed: LiveFeed = PumpPortalFeed(mint, clock=clock)
        if not pump:
            notes.append("mint does not end in 'pump'; PumpPortal may not carry its trades")
    elif source == "dexscreener":
        if pair is None:
            raise MarketNotFound(f"DexScreener has no Solana pair for {address}")
        feed = DexScreenerFeed(dex, pair.address, quote=quote, poll_interval=poll or 3.0, clock=clock)
    else:
        if pool is None:
            raise MarketNotFound(f"GeckoTerminal has no pool for {address}")
        token = mint if mint in (pool.base_token, pool.quote_token) else "base"
        feed = GeckoTerminalFeed(
            gecko, pool.address, timeframe, token=token, poll_interval=poll, grace=grace or 45.0, clock=clock
        )
        notes.append("GeckoTerminal candles can lag up to ~1 minute; 5m+ timeframes suit this source best")
    if grace is not None:
        feed.close_grace = grace

    history = None
    if pool is not None and timeframe in GECKO_TIMEFRAMES:
        other = pool.quote_token if pool.base_token == mint else pool.base_token
        currency = "token" if quote == "SOL" else "usd"
        if currency == "token" and other != WSOL:
            notes.append("no warm-up history: GeckoTerminal's pool is not SOL-quoted")
        else:
            token = mint if mint in (pool.base_token, pool.quote_token) else "base"
            limit = min(history_limit, 1000)
            pool_address = pool.address

            async def history() -> list[Candle]:
                return await gecko.ohlcv(pool_address, timeframe, token=token, currency=currency, limit=limit)

    elif pool is None:
        notes.append("no warm-up history: GeckoTerminal has not indexed this token yet (starting cold)")
    else:
        notes.append(f"no warm-up history: GeckoTerminal has no {format_timeframe(timeframe)} candles")

    info = MarketInfo(
        address=mint,
        symbol=symbol or short(mint),
        name=name,
        quote=quote,
        source=feed.name,
        pool=(pair.address if source == "dexscreener" and pair else pool.address if pool else None),
        dex=(pair.dex if pair else pool.dex if pool else ("pumpfun" if pump else None)),
        notes=notes,
    )
    return Market(info, feed, history, clock, closers=[gecko.aclose, dex.aclose])


def pumpportal_market(mint: str, *, symbol: str = "", name: str = "", initial=(), api_key: str | None = None) -> Market:
    """A market for a token too new to be indexed anywhere: live PumpPortal trades only."""
    clock = Clock()
    feed = PumpPortalFeed(mint, clock=clock, initial=initial, api_key=api_key)
    info = MarketInfo(address=mint, symbol=symbol or short(mint), name=name, quote="SOL", source=feed.name, dex="pumpfun")
    return Market(info, feed, None, clock)
