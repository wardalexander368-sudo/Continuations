"""GeckoTerminal public API: pool lookup, OHLCV history, new pools, and a polling feed.

Free tier: ~30 requests/minute, no key. OHLCV supports 1m/5m/15m/1h/4h/12h/1d
candles and can lag real time by up to about a minute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

from ..candles import Candle
from ..clock import Clock
from .base import Event, LiveFeed, Snapshot, Status
from .http import ApiError, JsonClient, NotFound

BASE_URL = "https://api.geckoterminal.com/api/v2"
TIMEFRAMES: dict[int, tuple[str, int]] = {
    60: ("minute", 1),
    300: ("minute", 5),
    900: ("minute", 15),
    3600: ("hour", 1),
    14400: ("hour", 4),
    43200: ("hour", 12),
    86400: ("day", 1),
}


@dataclass(frozen=True)
class GeckoPool:
    address: str
    name: str
    dex: str
    base_token: str
    quote_token: str
    base_symbol: str = ""
    base_name: str = ""
    quote_symbol: str = ""
    reserve_usd: float = 0.0
    volume_24h_usd: float = 0.0
    created_at: str | None = None
    price_usd: float | None = None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rel_id(item: dict, key: str) -> str:
    data = ((item.get("relationships") or {}).get(key) or {}).get("data") or {}
    return str(data.get("id") or "")


def _strip_network(identifier: str) -> str:
    """'solana_<address>' -> '<address>' (Solana addresses never contain '_')."""
    return identifier.split("_", 1)[1] if "_" in identifier else identifier


def parse_pools(payload: Any) -> list[GeckoPool]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") or []
    if isinstance(data, dict):
        data = [data]
    included = {item.get("id"): item.get("attributes") or {} for item in payload.get("included") or [] if isinstance(item, dict)}
    pools = []
    for item in data:
        if not isinstance(item, dict):
            continue
        attrs = item.get("attributes") or {}
        address = attrs.get("address") or _strip_network(str(item.get("id", "")))
        base_id, quote_id = _rel_id(item, "base_token"), _rel_id(item, "quote_token")
        base, quote = included.get(base_id, {}), included.get(quote_id, {})
        name = str(attrs.get("name") or "")
        parts = [p.strip() for p in name.split("/")]
        pools.append(
            GeckoPool(
                address=address,
                name=name,
                dex=_strip_network(_rel_id(item, "dex")) or "",
                base_token=_strip_network(base_id),
                quote_token=_strip_network(quote_id),
                base_symbol=str(base.get("symbol") or (parts[0] if parts and parts[0] else "")),
                base_name=str(base.get("name") or ""),
                quote_symbol=str(quote.get("symbol") or (parts[1] if len(parts) > 1 else "")),
                reserve_usd=_float(attrs.get("reserve_in_usd")) or 0.0,
                volume_24h_usd=_float((attrs.get("volume_usd") or {}).get("h24")) or 0.0,
                created_at=attrs.get("pool_created_at"),
                price_usd=_float(attrs.get("base_token_price_usd")),
            )
        )
    return pools


def parse_ohlcv(payload: Any, timeframe: int) -> list[Candle]:
    try:
        rows = payload["data"]["attributes"]["ohlcv_list"]
    except (KeyError, TypeError):
        raise ApiError("unexpected OHLCV response shape") from None
    candles = []
    for row in rows or []:
        try:
            ts, o, h, l, c = (float(v) for v in row[:5])
            volume = float(row[5]) if len(row) > 5 and row[5] is not None else 0.0
        except (TypeError, ValueError):
            continue
        if min(o, h, l, c) <= 0:
            continue
        start = int(ts) // timeframe * timeframe
        candles.append(Candle(start, o, max(h, o, c), min(l, o, c), c, volume=volume, trades=None))
    candles.sort(key=lambda c: c.start)
    return candles


class GeckoTerminal:
    def __init__(self, client: JsonClient | None = None, network: str = "solana"):
        self.http = client or JsonClient(BASE_URL, min_interval=2.1)
        self.network = network

    async def token_pools(self, token: str) -> list[GeckoPool]:
        payload = await self.http.get(
            f"networks/{self.network}/tokens/{token}/pools", {"include": "base_token,quote_token,dex", "page": 1}
        )
        return sorted(parse_pools(payload), key=lambda p: p.reserve_usd, reverse=True)

    async def pool(self, address: str) -> GeckoPool | None:
        pools = parse_pools(
            await self.http.get(f"networks/{self.network}/pools/{address}", {"include": "base_token,quote_token,dex"})
        )
        return pools[0] if pools else None

    async def new_pools(self, page: int = 1) -> list[GeckoPool]:
        payload = await self.http.get(
            f"networks/{self.network}/new_pools", {"include": "base_token,quote_token,dex", "page": page}
        )
        return parse_pools(payload)

    async def ohlcv(
        self, pool: str, timeframe: int, *, token: str = "base", currency: str = "usd", limit: int = 100
    ) -> list[Candle]:
        if timeframe not in TIMEFRAMES:
            raise ApiError(f"GeckoTerminal has no {timeframe}s candles")
        unit, aggregate = TIMEFRAMES[timeframe]
        payload = await self.http.get(
            f"networks/{self.network}/pools/{pool}/ohlcv/{unit}",
            {"aggregate": aggregate, "limit": max(1, min(limit, 1000)), "currency": currency, "token": token},
        )
        return parse_ohlcv(payload, timeframe)

    async def lookup(self, address: str) -> tuple[list[GeckoPool], bool]:
        """Pools for `address` as a token mint, else the pool with that address.

        Returns (pools, address_is_token).
        """
        try:
            pools = await self.token_pools(address)
            if pools:
                return pools, True
        except NotFound:
            pass
        try:
            pool = await self.pool(address)
        except NotFound:
            return [], False
        return ([pool] if pool else []), False

    async def aclose(self) -> None:
        await self.http.aclose()


class GeckoTerminalFeed(LiveFeed):
    """Polls the latest few OHLCV candles of one pool."""

    name = "geckoterminal"
    counts_trades = False

    def __init__(
        self,
        api: GeckoTerminal,
        pool: str,
        timeframe: int,
        *,
        token: str = "base",
        currency: str = "usd",
        poll_interval: float | None = None,
        grace: float = 45.0,
        clock: Clock | None = None,
    ):
        if timeframe not in TIMEFRAMES:
            supported = ", ".join(f"{s // 60}m" if s < 3600 else f"{s // 3600}h" for s in TIMEFRAMES)
            raise ValueError(f"GeckoTerminal candles must be one of: {supported}")
        self.api = api
        self.pool = pool
        self.timeframe = timeframe
        self.token = token
        self.currency = currency
        self.poll_interval = poll_interval or max(6.0, min(30.0, timeframe / 6))
        self.close_grace = grace
        self.clock = clock or Clock()

    async def events(self) -> AsyncIterator[Event]:
        failures = 0
        while True:
            try:
                candles = await self.api.ohlcv(self.pool, self.timeframe, token=self.token, currency=self.currency, limit=3)
                failures = 0
                yield Snapshot(candles)
            except ApiError as exc:
                failures += 1
                yield Status(f"GeckoTerminal poll failed ({failures}x): {exc}", "warn")
            await self.clock.sleep(self.poll_interval * (1 if failures < 3 else 3))
