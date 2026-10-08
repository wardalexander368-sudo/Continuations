"""Candles, timeframes, and assembly of live candles from trades and OHLCV snapshots."""

from __future__ import annotations

import csv
import re
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Iterable

_TF_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$", re.IGNORECASE)
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_timeframe(text: str) -> int:
    """Parse '30s', '1m', '4h', '1d' into seconds."""
    match = _TF_RE.match(text)
    if not match:
        raise ValueError(f"invalid timeframe {text!r}; use e.g. 30s, 1m, 5m, 1h")
    seconds = int(match.group(1)) * _UNITS[match.group(2).lower()]
    if seconds < 5:
        raise ValueError("timeframe must be at least 5s")
    return seconds


def format_timeframe(seconds: int) -> str:
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds % size == 0:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


@dataclass(frozen=True)
class Tick:
    """One trade (or one observed price change) reported by a live feed."""

    ts: float
    price: float
    volume: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    trades: int = 1
    buys: int = 0
    sells: int = 0
    trader: str = ""
    creator: bool = False  # trade made by the token's creator (dev wallet)
    liquidity: float = 0.0  # quote reserve after the trade (pump.fun: virtual SOL in the curve)


@dataclass
class Candle:
    start: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    # None when the source does not report trade counts (e.g. REST OHLCV).
    trades: int | None = None
    buys: int = 0
    sells: int = 0
    traders: int = 0  # distinct wallets trading in this candle
    new_traders: int = 0  # wallets trading this token for the first time
    max_trade: float = 0.0
    creator_buy: float = 0.0
    creator_sell: float = 0.0
    liquidity: float = 0.0
    last_trade: float = 0.0  # timestamp of the candle's last trade (0 if unknown)
    _wallets: set = field(default_factory=set, init=False, repr=False, compare=False)

    @classmethod
    def flat(cls, start: int, price: float, trades: int | None = 0) -> Candle:
        """A candle in which nothing traded."""
        return cls(start, price, price, price, price, trades=trades)

    @property
    def active(self) -> bool:
        """Whether anything traded during this candle."""
        return bool(self.trades) or self.volume > 0

    def add(self, tick: Tick, new_trader: bool = False) -> None:
        if not self.active:
            self.open = self.high = self.low = tick.price
        self.high = max(self.high, tick.price)
        self.low = min(self.low, tick.price)
        self.close = tick.price
        self.volume += tick.volume
        self.buy_volume += tick.buy_volume
        self.sell_volume += tick.sell_volume
        self.trades = (self.trades or 0) + tick.trades
        self.buys += tick.buys
        self.sells += tick.sells
        if tick.trades:
            self.last_trade = tick.ts
        if tick.trades == 1:
            self.max_trade = max(self.max_trade, tick.volume)
        if tick.trader and tick.trader not in self._wallets:
            self._wallets.add(tick.trader)
            self.traders += 1
        self.new_traders += new_trader
        if tick.creator:
            self.creator_buy += tick.buy_volume
            self.creator_sell += tick.sell_volume
        if tick.liquidity:
            self.liquidity = tick.liquidity


class CandleBook:
    """Builds a gap-free candle series from live ticks and/or OHLCV snapshots.

    A candle is closed when data for a later period arrives, or once the clock
    passes its end by `grace` seconds (to allow for feed latency). Periods in
    which nothing traded become flat candles.
    """

    def __init__(self, timeframe: int, grace: float = 2.0, counts_trades: bool = True, max_history: int = 5000):
        self.timeframe = timeframe
        self.grace = grace
        self.counts_trades = counts_trades
        self.closed: deque[Candle] = deque(maxlen=max_history)
        self.current: Candle | None = None
        self.ticks = 0
        self.last_tick_at: float | None = None
        self.wallets: set[str] = set()  # every wallet seen trading this token

    def period(self, ts: float) -> int:
        return int(ts // self.timeframe) * self.timeframe

    def view(self) -> Candle | None:
        """The forming candle, or a flat placeholder when nothing has traded in it yet."""
        if self.current is not None:
            return self.current
        if not self.closed:
            return None
        last = self.closed[-1]
        return Candle.flat(last.start + self.timeframe, last.close, self._fill_trades)

    def deadline(self) -> float | None:
        """Clock time at which the forming candle will be closed if no newer data arrives."""
        view = self.view()
        return None if view is None else view.start + self.timeframe + self.grace

    def add_tick(self, tick: Tick) -> list[Candle]:
        start = self.period(tick.ts)
        closed: list[Candle] = []
        if self.current is not None:
            if start < self.current.start:
                return closed
            if start > self.current.start:
                closed += self._close_current()
        if self.current is None:
            if self.closed and start <= self.closed[-1].start:
                return closed
            closed += self._fill_until(start, self._fill_trades)
            self.current = Candle.flat(start, tick.price, 0)
        new_trader = bool(tick.trader) and tick.trader not in self.wallets
        if new_trader:
            self.wallets.add(tick.trader)
        self.current.add(tick, new_trader)
        self.ticks += 1
        self.last_tick_at = tick.ts
        return closed

    def add_snapshot(self, candles: Iterable[Candle]) -> list[Candle]:
        """Upsert OHLCV candles (e.g. from a REST poll). Revisions to closed candles are ignored."""
        closed: list[Candle] = []
        for candle in sorted(candles, key=lambda c: c.start):
            candle = replace(candle, start=self.period(candle.start))
            if self.closed and candle.start <= self.closed[-1].start:
                continue
            if self.current is not None:
                if candle.start < self.current.start:
                    continue
                if candle.start == self.current.start:
                    self.current = candle
                    continue
                closed += self._close_current()
            closed += self._fill_until(candle.start, None)
            self.current = candle
        return closed

    def advance(self, now: float) -> list[Candle]:
        """Close the forming candle, and any empty periods, once their time is up."""
        closed: list[Candle] = []
        if self.current is not None and now >= self.current.start + self.timeframe + self.grace:
            closed += self._close_current()
        if self.current is None and self.closed:
            closed += self._fill_until(self.period(now - self.grace), self._fill_trades)
        return closed

    @property
    def _fill_trades(self) -> int | None:
        return 0 if self.counts_trades else None

    def _close_current(self) -> list[Candle]:
        candle, self.current = self.current, None
        self.closed.append(candle)
        return [candle]

    def _fill_until(self, start: int, trades: int | None) -> list[Candle]:
        """Append flat candles for every empty period before `start`."""
        if not self.closed:
            return []
        last = self.closed[-1]
        nxt = last.start + self.timeframe
        limit = self.closed.maxlen or 5000
        if (start - nxt) // self.timeframe > limit:
            nxt = start - limit * self.timeframe
        filled = []
        while nxt < start:
            candle = Candle.flat(nxt, last.close, trades)
            self.closed.append(candle)
            filled.append(candle)
            nxt += self.timeframe
        return filled


def fill_gaps(candles: Iterable[Candle], timeframe: int) -> list[Candle]:
    """Sort, de-duplicate and gap-fill a historical candle series."""
    book = CandleBook(timeframe, counts_trades=False)
    closed = book.add_snapshot(candles)
    if book.current is not None:
        closed += book._close_current()
    return closed


def _parse_time(value: str) -> int:
    value = value.strip()
    try:
        ts = float(value)
    except ValueError:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    return int(ts / 1000 if ts > 1e12 else ts)


def load_csv(path: str | Path) -> list[Candle]:
    """Load candles from a CSV with timestamp/open/high/low/close[/volume] columns."""
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: empty CSV")
        fields = {name.strip().lower(): name for name in reader.fieldnames}
        time_key = next((fields[k] for k in ("timestamp", "time", "date", "start", "ts") if k in fields), None)
        missing = [k for k in ("open", "high", "low", "close") if k not in fields]
        if time_key is None or missing:
            raise ValueError(f"{path}: need timestamp, open, high, low, close columns")
        candles = []
        for row in reader:
            o, h, l, c = (float(row[fields[k]]) for k in ("open", "high", "low", "close"))
            if min(o, h, l, c) <= 0:
                continue
            volume = float(row[fields["volume"]]) if "volume" in fields and row[fields["volume"]] else 0.0
            candles.append(Candle(_parse_time(row[time_key]), o, max(h, o, c), min(l, o, c), c, volume=volume))
    return candles
