"""Live feed replaying a simulated pump.fun token, for demos and tests without network access."""

from __future__ import annotations

import random
from typing import AsyncIterator, Iterator

from ..candles import Candle, CandleBook, Tick
from ..clock import Clock
from ..data.simulate import simulate_token
from ..feeds.pumpportal import tick_from_message
from .base import Event, LiveFeed


class SimulatedToken:
    """One simulated launch: its history before `now` and a live stream after it."""

    def __init__(self, now: float, history_minutes: float = 60.0, seed: int | None = None, lifetime_minutes: float = 720.0):
        rng = random.Random(seed)
        self.created = now - history_minutes * 60
        self._messages: Iterator[tuple[float, dict]] = simulate_token(rng, self.created, lifetime_minutes, lively=True)
        first_t, create = next(self._messages)
        self.mint = create["mint"]
        self.creator = create["traderPublicKey"]
        self.symbol = create["symbol"]
        self.name = create["name"]
        self._history: list[Tick] = [tick_from_message(create, first_t, self.creator)]
        self._next: tuple[float, dict] | None = None
        for t, msg in self._messages:
            if t >= now:
                self._next = (t, msg)
                break
            tick = tick_from_message(msg, t, self.creator)
            if tick is not None:
                self._history.append(tick)

    def history(self, timeframe: int, now: float) -> list[Candle]:
        book = CandleBook(timeframe, grace=0.0)
        for tick in self._history:
            book.add_tick(tick)
        book.advance(now)
        return list(book.closed) + ([book.current] if book.current is not None else [])

    def live(self) -> Iterator[Tick]:
        if self._next is not None:  # the trade that crossed `now`
            t, msg = self._next
            tick = tick_from_message(msg, t, self.creator)
            if tick is not None:
                yield tick
        for t, msg in self._messages:
            tick = tick_from_message(msg, t, self.creator)
            if tick is not None:
                yield tick


class SyntheticFeed(LiveFeed):
    name = "simulated"
    close_grace = 1.0

    def __init__(self, token: SimulatedToken, clock: Clock):
        self.token = token
        self.clock = clock

    async def events(self) -> AsyncIterator[Event]:
        for tick in self.token.live():
            await self.clock.sleep(tick.ts - self.clock.now())
            yield tick
