"""DexScreener public API: token/pair lookup and a polling price feed.

Free, no key, ~300 requests/minute on these endpoints. DexScreener has no
candle endpoint, so the feed polls the pair's price every few seconds and the
candle book assembles candles from those observations. Volume and buy/sell
counts are taken from changes in the rolling 24h totals, which is exact for
tokens younger than a day and approximate after that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

from ..candles import Tick
from ..clock import Clock
from .base import Event, LiveFeed, Status
from .http import ApiError, JsonClient, NotFound

BASE_URL = "https://api.dexscreener.com"


@dataclass(frozen=True)
class DexPair:
    chain: str
    dex: str
    address: str
    base_address: str
    base_symbol: str
    base_name: str
    quote_address: str
    quote_symbol: str
    price_native: float | None
    price_usd: float | None
    liquidity_usd: float = 0.0
    volume_h24: float = 0.0
    buys_h24: int = 0
    sells_h24: int = 0
    created_ms: int | None = None
    url: str = ""


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_pair(item: Any) -> DexPair | None:
    if not isinstance(item, dict) or not item.get("pairAddress"):
        return None
    base = item.get("baseToken") or {}
    quote = item.get("quoteToken") or {}
    txns = (item.get("txns") or {}).get("h24") or {}
    created = item.get("pairCreatedAt")
    return DexPair(
        chain=str(item.get("chainId") or ""),
        dex=str(item.get("dexId") or ""),
        address=str(item["pairAddress"]),
        base_address=str(base.get("address") or ""),
        base_symbol=str(base.get("symbol") or ""),
        base_name=str(base.get("name") or ""),
        quote_address=str(quote.get("address") or ""),
        quote_symbol=str(quote.get("symbol") or ""),
        price_native=_float(item.get("priceNative")),
        price_usd=_float(item.get("priceUsd")),
        liquidity_usd=_float((item.get("liquidity") or {}).get("usd")) or 0.0,
        volume_h24=_float((item.get("volume") or {}).get("h24")) or 0.0,
        buys_h24=_int(txns.get("buys")),
        sells_h24=_int(txns.get("sells")),
        created_ms=_int(created) or None,
        url=str(item.get("url") or ""),
    )


def parse_pairs(payload: Any) -> list[DexPair]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("pairs") or ([payload["pair"]] if payload.get("pair") else [])
    else:
        items = []
    return [p for p in (parse_pair(item) for item in items) if p is not None]


class DexScreener:
    def __init__(self, client: JsonClient | None = None, chain: str = "solana"):
        self.http = client or JsonClient(BASE_URL, min_interval=0.25)
        self.chain = chain

    async def token_pairs(self, token: str) -> list[DexPair]:
        try:
            pairs = parse_pairs(await self.http.get(f"tokens/v1/{self.chain}/{token}"))
        except NotFound:
            pairs = parse_pairs(await self.http.get(f"latest/dex/tokens/{token}"))
        return [p for p in pairs if p.chain == self.chain]

    async def pair(self, address: str) -> DexPair | None:
        pairs = parse_pairs(await self.http.get(f"latest/dex/pairs/{self.chain}/{address}"))
        return pairs[0] if pairs else None

    async def lookup(self, address: str) -> tuple[list[DexPair], bool]:
        """Pairs trading `address` as a token, else the pair with that address.

        Returns (pairs, address_is_token).
        """
        try:
            pairs = await self.token_pairs(address)
            if pairs:
                return pairs, True
        except NotFound:
            pass
        try:
            pair = await self.pair(address)
        except NotFound:
            return [], False
        return ([pair] if pair else []), False

    async def aclose(self) -> None:
        await self.http.aclose()


class DexScreenerFeed(LiveFeed):
    """Polls one pair's price and turns each change into a tick."""

    name = "dexscreener"

    def __init__(self, api: DexScreener, pair: str, *, quote: str = "USD", poll_interval: float = 3.0, clock: Clock | None = None):
        self.api = api
        self.pair = pair
        self.quote = quote
        self.poll_interval = poll_interval
        self.close_grace = poll_interval + 1.0
        self.clock = clock or Clock()

    def _price(self, pair: DexPair) -> float | None:
        price = pair.price_usd if self.quote == "USD" else pair.price_native
        return price if price and price > 0 else None

    async def events(self) -> AsyncIterator[Event]:
        prev: DexPair | None = None
        failures = 0
        while True:
            try:
                pair = await self.api.pair(self.pair)
                failures = 0
            except ApiError as exc:
                pair = None
                failures += 1
                yield Status(f"DexScreener poll failed ({failures}x): {exc}", "warn")
            price = self._price(pair) if pair else None
            if pair is not None and price is not None:
                if prev is None:
                    # Baseline observation: sets the price without counting as a trade.
                    yield Tick(self.clock.now(), price, trades=0)
                else:
                    tick = self._diff(prev, pair, price)
                    if tick is not None:
                        yield tick
                prev = pair
            await self.clock.sleep(self.poll_interval * (1 if failures < 3 else 3))

    def _diff(self, prev: DexPair, pair: DexPair, price: float) -> Tick | None:
        buys = max(0, pair.buys_h24 - prev.buys_h24)
        sells = max(0, pair.sells_h24 - prev.sells_h24)
        volume = max(0.0, pair.volume_h24 - prev.volume_h24)
        moved = price != self._price(prev)
        if not (moved or buys or sells or volume > 0):
            return None
        share = buys / (buys + sells) if buys + sells else 0.5
        return Tick(
            self.clock.now(),
            price,
            volume=volume,
            buy_volume=volume * share,
            sell_volume=volume * (1.0 - share),
            trades=max(buys + sells, 1),
            buys=buys,
            sells=sells,
        )
