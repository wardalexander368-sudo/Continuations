"""Simulated memecoin trades, for demos and tests without network access."""

from __future__ import annotations

import math
import random
from typing import AsyncIterator

from ..candles import Candle, CandleBook, Tick
from ..clock import Clock
from .base import Event, LiveFeed

# Log drift per minute in each market regime.
REGIMES = {"pump": 0.02, "chop": 0.0, "bleed": -0.012}


class MemecoinSimulator:
    """A rough stand-in for a young memecoin: bursty trades, trending regimes,
    volatility clustering and occasional jumps. Not real market data."""

    def __init__(self, seed: int | None = None, price: float = 3e-8, trades_per_min: float = 40.0, vol_per_min: float = 0.035):
        self.rng = random.Random(seed)
        self.log_price = math.log(price)
        self.trades_per_min = trades_per_min
        self.vol_per_min = vol_per_min
        self.regime = "chop"
        self._log_vol = 0.0

    @property
    def price(self) -> float:
        return math.exp(self.log_price)

    def step(self) -> tuple[float, Tick]:
        """Advance to the next trade. Returns (seconds elapsed, trade at t=0)."""
        rng = self.rng
        busy = 1.8 if self.regime == "pump" else 1.0
        dt = rng.expovariate(self.trades_per_min * busy * math.exp(self._log_vol) / 60.0)
        minutes = dt / 60.0
        if rng.random() < minutes / 12.0:
            self.regime = rng.choice(list(REGIMES))
        self._log_vol = self._log_vol * math.exp(-minutes / 8.0) + 0.25 * math.sqrt(minutes) * rng.gauss(0, 1)
        vol = self.vol_per_min * math.exp(self._log_vol)
        r = REGIMES[self.regime] * minutes + vol * math.sqrt(minutes) * rng.gauss(0, 1)
        if rng.random() < 0.002:
            r += rng.gauss(0, 0.08)
        self.log_price += r
        size = rng.lognormvariate(-1.0, 1.0)
        buy = r > 0 or (r == 0 and rng.random() < 0.5)
        return dt, Tick(0.0, self.price, volume=size, buy_volume=size if buy else 0.0, sell_volume=0.0 if buy else size)


def synthetic_history(sim: MemecoinSimulator, end: float, timeframe: int, candles: int) -> list[Candle]:
    """Run the simulator up to `end`; returns closed candles plus the one still forming."""
    book = CandleBook(timeframe)
    t = end - candles * timeframe
    while True:
        dt, tick = sim.step()
        if t + dt >= end:
            # Rewind isn't possible; the trade that would cross `end` is dropped.
            break
        t += dt
        book.add_tick(Tick(t, tick.price, tick.volume, tick.buy_volume, tick.sell_volume))
    book.advance(end)
    out = list(book.closed)
    if book.current is not None:
        out.append(book.current)
    return out


class SyntheticFeed(LiveFeed):
    name = "simulated"
    close_grace = 1.0

    def __init__(self, sim: MemecoinSimulator, clock: Clock):
        self.sim = sim
        self.clock = clock

    async def events(self) -> AsyncIterator[Event]:
        t = self.clock.now()
        while True:
            dt, tick = self.sim.step()
            t += dt
            await self.clock.sleep(t - self.clock.now())
            yield Tick(t, tick.price, tick.volume, tick.buy_volume, tick.sell_volume)
