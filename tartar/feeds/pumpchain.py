"""pump.fun events straight from the chain, via a Solana RPC websocket (free, no API key).

The pump.fun program logs an Anchor event for every create, trade and
completion (graduation). `logsSubscribe` on the program streams the logs of
every transaction that touches it; the events are decoded here from the
"Program data:" lines. Only the leading, long-stable fields of each event are
read, so fields the program appends later don't break decoding.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import bisect
import hashlib
import json
import os
import struct
import time
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Iterable, Iterator

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from ..candles import Tick
from ..clock import Clock
from .base import Event, LiveFeed, Status

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
# Only the official endpoint by default: publicnode's free websocket was seen silently
# delivering a partial stream (about 60% of trades), which would corrupt candles.
DEFAULT_RPC_WS = ("wss://api.mainnet-beta.solana.com",)
LAMPORTS = 1e9
TOKEN_UNITS = 1e6  # pump.fun tokens have 6 decimals

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _disc(name: str) -> bytes:
    return hashlib.sha256(f"event:{name}".encode()).digest()[:8]


TRADE, CREATE, COMPLETE = _disc("TradeEvent"), _disc("CreateEvent"), _disc("CompleteEvent")
SOL_QUOTE = "11111111111111111111111111111111"  # a curve's quote_mint when it trades against SOL


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + out


def b58decode(text: str, size: int = 32) -> bytes:
    n = 0
    for ch in text:
        n = n * 58 + _B58.index(ch)
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    raw = b"\0" * (len(text) - len(text.lstrip("1"))) + body
    if len(raw) != size:
        raise ValueError(f"not a {size}-byte base58 key: {text}")
    return raw


def rpc_urls() -> tuple[str, ...]:
    """RPC websocket endpoints: $SOLANA_RPC_WS (comma-separated) or the public defaults."""
    env = os.environ.get("SOLANA_RPC_WS")
    return tuple(u.strip() for u in env.split(",") if u.strip()) if env else DEFAULT_RPC_WS


@dataclass(frozen=True)
class ChainTrade:
    mint: str
    sol: float  # SOL
    tokens: float  # whole tokens
    is_buy: bool
    user: str
    block_time: int
    vsol: float  # virtual SOL reserves after the trade
    vtok: float  # virtual token reserves after the trade
    creator: str = ""
    real_sol: float | None = None  # SOL actually in the curve (progress toward graduation)
    # Curves quoted in another token (USDC, a tokenized stock, another pump coin...) report
    # zero SOL fields; their amounts are in raw base units of `quote_mint` (decimals are not
    # in the event). Empty for SOL curves.
    quote_mint: str = ""
    quote_amount: int = 0
    vquote: int = 0
    rquote: int = 0

    @property
    def price(self) -> float:
        """SOL per token (0 for a curve quoted in another token)."""
        return self.vsol / self.vtok if self.vtok else 0.0


@dataclass(frozen=True)
class ChainCreate:
    mint: str
    name: str
    symbol: str
    creator: str
    block_time: int | None
    uri: str = ""
    quote_mint: str = ""  # the token this curve is priced in; empty for SOL


@dataclass(frozen=True)
class ChainComplete:
    mint: str


class _Reader:
    def __init__(self, data: bytes, pos: int = 8):
        self.data, self.pos = data, pos

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise ValueError("event too short")
        chunk = self.data[self.pos : self.pos + n]
        self.pos += n
        return chunk

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.take(8))[0]

    def key(self) -> str:
        return b58encode(self.take(32))

    def string(self) -> str:
        n = struct.unpack("<I", self.take(4))[0]
        if n > 1000:
            raise ValueError("implausible string length")
        return self.take(n).decode("utf-8", "replace")


def decode_event(data: bytes) -> ChainTrade | ChainCreate | ChainComplete | None:
    """Decode one pump.fun event payload (discriminator + borsh body); None if not one we use."""
    head = data[:8]
    try:
        if head == TRADE:
            r = _Reader(data)
            mint, sol, tokens = r.key(), r.u64(), r.u64()
            is_buy = r.take(1) != b"\0"
            user, ts, vsol, vtok = r.key(), r.i64(), r.u64(), r.u64()
            creator, real_sol, quote = "", None, None
            try:  # fields were appended over time (pump.fun's public IDL): read while bytes remain
                real_sol = r.u64() / LAMPORTS
                r.u64(), r.key(), r.u64(), r.u64()  # real token reserves, fee recipient, fee bps, fee
                creator = r.key()
                r.u64(), r.u64(), r.take(1)  # creator fee bps, creator fee, track_volume
                r.u64(), r.u64(), r.u64(), r.i64()  # volume accumulator
                r.string(), r.take(1)  # ix_name, mayhem_mode
                r.u64(), r.u64(), r.u64(), r.u64()  # cashback and buyback (bps, amount)
                r.take(34 * struct.unpack("<I", r.take(4))[0])  # fee-sharing shareholders
                quote = (r.key(), r.u64(), r.u64(), r.u64())  # quote mint, amount, virtual and real reserves
            except ValueError:
                pass  # an older, shorter layout: SOL-quoted
            if quote is not None and quote[0] != SOL_QUOTE:
                if vtok <= 0 or quote[2] <= 0:
                    return None
                return ChainTrade(mint, 0.0, tokens / TOKEN_UNITS, is_buy, user, ts, 0.0, vtok / TOKEN_UNITS, creator, None, *quote)
            if vsol <= 0 or vtok <= 0:
                return None
            return ChainTrade(mint, sol / LAMPORTS, tokens / TOKEN_UNITS, is_buy, user, ts, vsol / LAMPORTS, vtok / TOKEN_UNITS, creator, real_sol)
        if head == CREATE:
            r = _Reader(data)
            name, symbol, uri = r.string(), r.string(), r.string()
            mint, _curve, user = r.key(), r.key(), r.key()
            creator, ts, quote_mint = user, None, ""
            try:
                creator, ts = r.key(), r.i64()
                r.u64(), r.u64(), r.u64(), r.u64(), r.key()  # starting reserves, supply, token program
                r.take(2)  # mayhem mode, cashback enabled
                quote_mint = r.key()
            except ValueError:
                pass  # an older, shorter layout: SOL-quoted
            return ChainCreate(mint, name, symbol, creator, ts, uri, "" if quote_mint == SOL_QUOTE else quote_mint)
        if head == COMPLETE:
            r = _Reader(data)
            r.key()  # user
            return ChainComplete(r.key())
    except (ValueError, struct.error):
        return None
    return None


def program_data(logs: Iterable[str], program: str) -> Iterator[bytes]:
    """Payloads of the `Program data` lines that `program` itself emitted.

    Only lines logged while `program` is the innermost running program count: routers
    and other launchpads in the same transaction emit their own Anchor events, whose
    discriminators depend only on the event name (another program's TradeEvent has
    pump.fun's). Logs without invoke lines are taken as the program's own.
    """
    frames: list[str] = []
    for line in logs:
        if not line.startswith("Program data: "):
            parts = line.split(" ", 3)
            if len(parts) >= 3 and parts[0] == "Program":
                if parts[2] == "invoke":
                    frames.append(parts[1])
                elif (parts[2] == "success" or parts[2].startswith("failed")) and frames and frames[-1] == parts[1]:
                    frames.pop()
            continue
        if frames and frames[-1] != program:
            continue
        try:
            yield base64.b64decode(line[14:], validate=True)
        except (binascii.Error, ValueError):
            continue


def events_from_logs(logs: Iterable[str], program: str = PUMP_PROGRAM) -> list[ChainTrade | ChainCreate | ChainComplete]:
    """pump.fun events in a transaction's logs (see `program_data`)."""
    return [event for data in program_data(logs, program) if (event := decode_event(data)) is not None]


def capture_rate(trades: Iterable[tuple[float, bool, float | None, float]]) -> float | None:
    """Share of a token's trades whose pre-trade curve reserves match some other recorded
    trade's post-trade reserves, i.e. whose predecessor was captured.

    Each item is (sol, is_buy, real_sol or None, virtual_sol). Order-insensitive:
    RPC notifications arrive out of execution order. On the free public RPC this is
    typically 0.6-0.75, and lower for busy tokens (the endpoint drops notifications).
    """
    rows = list(trades)
    if len(rows) < 2:
        return None
    posts = sorted(real if real is not None else virtual for _, _, real, virtual in rows)
    matched = 0
    for sol, buy, real, virtual in rows:
        after = real if real is not None else virtual
        before = after - sol if buy else after + sol
        i = bisect.bisect_left(posts, before - 1e-6)
        matched += i < len(posts) and abs(posts[i] - before) <= 1e-6
    return matched / len(rows)


def trade_to_message(trade: ChainTrade) -> dict:
    """The trade in PumpPortal's message shape, so the rest of the pipeline treats both alike.

    A trade on a curve quoted in another token has no SOL amounts; it carries `quote`,
    the raw quote amounts, and no SOL price, so SOL-based consumers skip it."""
    if trade.quote_mint:
        return {
            "mint": trade.mint, "traderPublicKey": trade.user, "txType": "buy" if trade.is_buy else "sell",
            "tokenAmount": trade.tokens, "vTokensInBondingCurve": trade.vtok, "creator": trade.creator, "pool": "pump",
            "quote": trade.quote_mint, "quoteAmount": trade.quote_amount, "vQuote": trade.vquote, "rQuote": trade.rquote,
        }  # fmt: skip
    return {
        "mint": trade.mint,
        "traderPublicKey": trade.user,
        "txType": "buy" if trade.is_buy else "sell",
        "solAmount": trade.sol,
        "tokenAmount": trade.tokens,
        "vSolInBondingCurve": trade.vsol,
        "vTokensInBondingCurve": trade.vtok,
        "realSolReserves": trade.real_sol,
        "creator": trade.creator,
        "pool": "pump",
    }


def create_to_message(create: ChainCreate, first_trade: ChainTrade | None = None) -> dict:
    msg = {"mint": create.mint, "traderPublicKey": create.creator, "txType": "create", "name": create.name, "symbol": create.symbol, "uri": create.uri, "pool": "pump"}
    if create.quote_mint:
        msg["quote"] = create.quote_mint
    if first_trade is not None and first_trade.mint == create.mint and not first_trade.quote_mint:
        msg.update(
            solAmount=first_trade.sol,
            tokenAmount=first_trade.tokens,
            vSolInBondingCurve=first_trade.vsol,
            vTokensInBondingCurve=first_trade.vtok,
            realSolReserves=first_trade.real_sol,
        )
    return msg


def stream_item(item: tuple) -> tuple[float, str, list, int | None]:
    """(receive time, signature, events, slot) from a stream item; slot is None if absent."""
    return item[0], item[1], item[2], (item[3] if len(item) > 3 else None)


async def stream_program_events(
    urls: tuple[str, ...] | None = None,
    *,
    commitment: str = "confirmed",
    max_backoff: float = 30.0,
    mentions: str = PUMP_PROGRAM,
    decode: Callable[[list[str]], list] = events_from_logs,
) -> AsyncIterator[tuple[float, str, list, int | None] | Status]:
    """Yield (receive time, signature, events, slot) for every successful pump.fun
    transaction, plus Status messages (kind connected/disconnected) on (re)connection.
    Consumers that predate the slot read the first three items (`stream_item`).
    `mentions` and `decode` select another account (e.g. one PumpSwap pool) and decoder.

    After a drop it reconnects to the same endpoint; it only moves to the next of
    `urls` after repeated failures to connect. Trades during a disconnection are
    lost, so consumers must treat that time as unobserved."""
    urls = urls or rpc_urls()
    index, failures, backoff = 0, 0, 1.0
    while True:
        url = urls[index % len(urls)]
        connected = False
        try:
            async with connect(url, open_timeout=15, ping_interval=None, max_size=None, max_queue=None) as ws:
                request = {"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe", "params": [{"mentions": [mentions]}, {"commitment": commitment}]}
                await ws.send(json.dumps(request))
                reply = json.loads(await asyncio.wait_for(ws.recv(), 15))
                if "error" in reply:
                    raise ConnectionError(f"logsSubscribe refused: {reply['error']}")
                connected = True
                failures, backoff = 0, 1.0
                yield Status(f"connected to {url}", kind="connected")
                while True:
                    raw = await asyncio.wait_for(ws.recv(), 60)  # pump.fun is never quiet for a minute
                    try:
                        result = json.loads(raw)["params"]["result"]
                        value = result["value"]
                    except (ValueError, KeyError, TypeError):
                        continue
                    if value.get("err") is not None:
                        continue  # failed transactions change nothing
                    events = decode(value.get("logs") or [])
                    if events:
                        slot = (result.get("context") or {}).get("slot")
                        yield time.time(), value.get("signature", ""), events, slot if isinstance(slot, int) else None
        except (OSError, WebSocketException, asyncio.TimeoutError, ConnectionError, ValueError) as exc:
            yield Status(f"{url} disconnected ({exc.__class__.__name__}: {str(exc)[:120]}); retrying in {backoff:.0f}s", "warn", kind="disconnected")
        if not connected:
            failures += 1
            if failures >= 3 and len(urls) > 1:
                index, failures = index + 1, 0
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)


class PumpChainFeed(LiveFeed):
    """Every trade of one pump.fun token, read from the chain."""

    name = "solana-rpc"
    close_grace = 2.5

    def __init__(
        self,
        mint: str,
        *,
        urls: tuple[str, ...] | None = None,
        clock: Clock | None = None,
        creator: str | None = None,
        initial: Iterable[Tick] = (),
        stream: AsyncIterator | None = None,
    ):
        self.mint = mint
        self.urls = urls
        self.clock = clock or Clock()
        self.creator = creator
        self._initial = list(initial)
        self._stream = stream  # an already-open program stream to continue (e.g. after spotting a launch)

    async def events(self) -> AsyncIterator[Event]:
        from .pumpportal import tick_from_message

        for tick in self._initial:
            yield tick
        async for item in self._stream or stream_program_events(self.urls):
            if isinstance(item, Status):
                yield item
                continue
            _, _, events, _ = stream_item(item)
            for event in events:
                if isinstance(event, ChainTrade) and event.mint == self.mint:
                    if not self.creator and event.creator:
                        self.creator = event.creator
                    tick = tick_from_message(trade_to_message(event), self.clock.now(), self.creator)
                    if tick is not None:
                        yield tick
                elif isinstance(event, ChainComplete) and event.mint == self.mint:
                    yield Status("token graduated: bonding-curve trading is over (it now trades on PumpSwap)", "warn", kind="graduated")
                    return
