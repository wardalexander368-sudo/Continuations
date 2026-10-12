"""PumpSwap: pump.fun's AMM, where a token trades once its bonding curve completes.

Trades are Anchor events in the program's logs (`BuyEvent`, `SellEvent`; layouts
from pump.fun's public IDL, github.com/pump-fun/pump-public-docs idl/pump_amm.json,
checked against vault balances on mainnet transactions). Events name the pool, not
the mint. A graduated pump.fun token's canonical pool is derived offline
(`canonical_pool`): base = the token (6 decimals), quote = wrapped SOL.

The pool reserves in an event are PRE-trade. The price uses effective quote
reserves (vault + `virtual_quote_reserves`, a signed i128 that boosted pools carry):
after a buy, base - base_out and quote + quote_in_with_lp_fee; after a sell, base +
base_in and quote - quote_out_without_lp_fee. Those LP-inclusive amounts are the
liquidity that moves in every instruction variant (`quote_amount_in` and
`user_quote_amount_in` swap meaning between buy and buy_exact_quote_in).
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import AsyncIterator

from ..candles import Tick
from ..clock import Clock
from .base import Event, LiveFeed, Status
from .pumpchain import PUMP_PROGRAM, _disc, _Reader, b58decode, program_data, stream_item, stream_program_events

PUMP_AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL = "So11111111111111111111111111111111111111112"
BUY, SELL, CREATE_POOL = _disc("BuyEvent"), _disc("SellEvent"), _disc("CreatePoolEvent")


@dataclass(frozen=True)
class SwapTrade:
    pool: str
    is_buy: bool
    base: float  # tokens bought or sold
    quote: float  # quote (SOL in a WSOL pool) into or out of the pool, LP fee included
    user_quote: float  # what the trader paid (buy) or received (sell), every fee included
    user: str
    ts: int
    base_after: float  # pool token reserves after the trade
    quote_after: float  # effective quote reserves after the trade (vault + virtual)
    coin_creator: str = ""

    @property
    def price(self) -> float:
        """Quote per token after the trade."""
        return self.quote_after / self.base_after if self.base_after > 0 else 0.0


@dataclass(frozen=True)
class PoolCreated:
    pool: str
    base_mint: str
    quote_mint: str
    base_decimals: int
    quote_decimals: int
    creator: str


def _i128(r: _Reader) -> int:
    return int.from_bytes(r.take(16), "little", signed=True)


def decode_swap_event(data: bytes, base_decimals: int = 6, quote_decimals: int = 9) -> SwapTrade | PoolCreated | None:
    """Decode one PumpSwap event payload; None if not a trade or pool creation.

    Older, shorter layouts are accepted: trailing fields that are missing read as 0.
    """
    head = data[:8]
    bunit, qunit = 10.0**base_decimals, 10.0**quote_decimals
    try:
        if head in (BUY, SELL):
            buy = head == BUY
            r = _Reader(data)
            ts = r.i64()
            base_amount = r.u64()
            r.u64(), r.u64(), r.u64()  # max/min quote, the user's base and quote balances
            pool_base, pool_quote = r.u64(), r.u64()
            r.u64(), r.u64(), r.u64()  # quote in/out (meaning varies), lp fee bps, lp fee
            protocol_fee = (r.u64(), r.u64())[1]
            liquidity_quote = r.u64()  # quote_amount_in_with_lp_fee / quote_amount_out_without_lp_fee
            user_quote = r.u64()
            pool, user = r.key(), r.key()
            for _ in range(4):
                r.key()  # token accounts and the protocol fee recipient
            coin_creator, creator_fee, virtual_quote = "", 0, 0
            try:
                coin_creator = r.key()
                creator_fee = (r.u64(), r.u64())[1]
                if buy:
                    r.take(1)  # track_volume
                    r.u64(), r.u64(), r.u64(), r.i64(), r.u64()  # volume accumulators, last update, min base out
                    r.string()  # ix_name
                r.u64(), r.u64(), r.u64(), r.u64()  # cashback and buyback bps/amounts (buyback is part of the protocol fee)
                virtual_quote = _i128(r)
            except ValueError:
                pass  # an older layout without the later fields
            if pool_base <= 0:
                return None
            if buy:
                base_after, quote_after = pool_base - base_amount, pool_quote + virtual_quote + liquidity_quote
                paid = liquidity_quote + protocol_fee + creator_fee
            else:
                base_after, quote_after = pool_base + base_amount, pool_quote + virtual_quote - liquidity_quote
                paid = user_quote
            if base_after <= 0 or quote_after <= 0:
                return None
            return SwapTrade(
                pool, buy, base_amount / bunit, liquidity_quote / qunit, paid / qunit, user, ts,
                base_after / bunit, quote_after / qunit, coin_creator,
            )  # fmt: skip
        if head == CREATE_POOL:
            r = _Reader(data)
            r.i64(), r.take(2)  # timestamp, index
            creator, base_mint, quote_mint = r.key(), r.key(), r.key()
            base_dec, quote_dec = r.take(1)[0], r.take(1)[0]
            for _ in range(7):
                r.u64()
            r.take(1)  # pool bump
            return PoolCreated(r.key(), base_mint, quote_mint, base_dec, quote_dec, creator)
    except (ValueError, struct.error):
        return None
    return None


def swap_events_from_logs(logs: list[str]) -> list[SwapTrade | PoolCreated]:
    return [e for data in program_data(logs, PUMP_AMM) if (e := decode_swap_event(data)) is not None]


# ---------------------------------------------------------------- canonical pools

_P = 2**255 - 19
_D = -121665 * pow(121666, _P - 2, _P) % _P


def _on_curve(key: bytes) -> bool:
    """Whether 32 bytes decompress to an ed25519 point (program addresses must not)."""
    y = int.from_bytes(key, "little") & ((1 << 255) - 1)
    if y >= _P:
        return False
    y2 = y * y % _P
    x2 = (y2 - 1) * pow(_D * y2 + 1, _P - 2, _P) % _P
    if x2 == 0:
        return not key[31] >> 7  # x = 0 only with a clear sign bit
    return pow(x2, (_P - 1) // 2, _P) == 1


def find_program_address(seeds: list[bytes], program: str) -> str:
    program_id = b58decode(program)
    for bump in range(255, -1, -1):
        digest = hashlib.sha256(b"".join(seeds) + bytes([bump]) + program_id + b"ProgramDerivedAddress").digest()
        if not _on_curve(digest):
            from .pumpchain import b58encode

            return b58encode(digest)
    raise ValueError("no program address found")


def canonical_pool(mint: str) -> str:
    """The PumpSwap pool pump.fun creates when `mint`'s bonding curve completes (token/WSOL)."""
    raw_mint = b58decode(mint)
    authority = find_program_address([b"pool-authority", raw_mint], PUMP_PROGRAM)
    seeds = [b"pool", (0).to_bytes(2, "little"), b58decode(authority), raw_mint, b58decode(WSOL)]
    return find_program_address(seeds, PUMP_AMM)


# ---------------------------------------------------------------- live feed


class PumpSwapFeed(LiveFeed):
    """Every trade in one PumpSwap pool (a graduated pump.fun token), read from the chain."""

    name = "pumpswap"
    close_grace = 2.5

    def __init__(self, mint: str, pool: str | None = None, *, urls: tuple[str, ...] | None = None, clock: Clock | None = None, creator: str | None = None, stream=None):
        self.mint = mint
        self.pool = pool or canonical_pool(mint)
        self.urls = urls
        self.clock = clock or Clock()
        self.creator = creator
        self._stream = stream

    async def events(self) -> AsyncIterator[Event]:
        stream = self._stream or stream_program_events(self.urls, mentions=self.pool, decode=swap_events_from_logs)
        async for item in stream:
            if isinstance(item, Status):
                yield item
                continue
            _, _, events, _ = stream_item(item)
            for event in events:
                if isinstance(event, SwapTrade) and event.pool == self.pool:
                    if not self.creator and event.coin_creator:
                        self.creator = event.coin_creator
                    sol = event.user_quote
                    yield Tick(
                        self.clock.now(), event.price, volume=sol,
                        buy_volume=sol if event.is_buy else 0.0, sell_volume=0.0 if event.is_buy else sol,
                        buys=int(event.is_buy), sells=int(not event.is_buy), trader=event.user,
                        creator=bool(self.creator) and event.user == self.creator,
                        liquidity=event.quote_after, tokens=event.base,
                    )  # fmt: skip
