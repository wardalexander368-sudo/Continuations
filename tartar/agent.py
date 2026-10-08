"""The agent: watch a token's candles live, predict each close, and report as it goes."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Sequence

from .candles import Candle, CandleBook, Tick
from .feeds.base import Snapshot, Status
from .market import Market, MarketInfo
from .model import Forecast, Forecaster, Outcome
from .model.global_model import GlobalModel
from .scoreboard import Scoreboard


@dataclass
class View:
    """Everything an output needs to render the current state."""

    info: MarketInfo
    timeframe: int
    now: float
    candles: Sequence[Candle]  # closed candles, oldest first
    current: Candle | None  # forming candle (placeholder if nothing traded yet)
    live: Forecast | None  # live estimate of the forming candle's close
    locked: Forecast | None  # the forecast locked in when the forming candle opened
    board: Scoreboard
    ticks: int
    last_tick_at: float | None
    status: str
    weights: dict[str, float]


class Sink:
    """Receives the agent's output. Override what you need."""

    def start(self, info: MarketInfo, timeframe: int) -> None: ...

    def warmed_up(self, candles: int, board: Scoreboard) -> None: ...

    def candle_closed(self, candle: Candle, outcome: Outcome | None, next_forecast: Forecast | None) -> None: ...

    def update(self, view: View) -> None: ...

    def status(self, message: str, level: str) -> None: ...

    def stop(self, board: Scoreboard) -> None: ...


class FeedEnded(Exception):
    pass


_END = object()


class CandleAgent:
    def __init__(
        self,
        market: Market,
        timeframe: int,
        *,
        coverage: float = 0.8,
        sinks: Sequence[Sink] = (),
        update_interval: float = 0.5,
        model: GlobalModel | None = None,
    ):
        self.market = market
        self.timeframe = timeframe
        self.clock = market.clock
        self.sinks = list(sinks)
        self.update_interval = update_interval
        self.book = CandleBook(timeframe, grace=market.feed.close_grace, counts_trades=market.feed.counts_trades)
        info = market.info
        self.forecaster = Forecaster(
            timeframe,
            coverage,
            model=model,
            domain=info.domain,
            launched_at=info.launched_at,
            creator_known=bool(info.creator),
        )
        self.board = Scoreboard()
        self.live_candles = 0
        self.status_message = "starting"

    def _emit(self, method: str, *args) -> None:
        for sink in self.sinks:
            getattr(sink, method)(*args)

    def _status(self, message: str, level: str = "info") -> None:
        self.status_message = message
        self._emit("status", message, level)

    async def warm_up(self) -> int:
        """Replay history through the model (walk-forward), so live predictions start informed."""
        if self.market.history is None:
            return 0
        self._status("loading history")
        try:
            candles = await self.market.history()
        except Exception as exc:  # history is optional; keep going without it
            self._status(f"history unavailable: {exc}", "warn")
            return 0
        closed = self.book.add_snapshot(candles) + self.book.advance(self.clock.now())
        for candle in closed:
            self._observe(candle, live=False)
        self._emit("warmed_up", len(closed), self.board)
        return len(closed)

    def _observe(self, candle: Candle, live: bool) -> Outcome | None:
        outcome = self.forecaster.observe(candle)
        if outcome is not None:
            self.board.record(outcome, live)
        return outcome

    def view(self) -> View:
        now = self.clock.now()
        current = self.book.view()
        return View(
            info=self.market.info,
            timeframe=self.timeframe,
            now=now,
            candles=self.book.closed,
            current=current,
            live=self.forecaster.nowcast(current, now),
            locked=self.forecaster.locked,
            board=self.board,
            ticks=self.book.ticks,
            last_tick_at=self.book.last_tick_at,
            status=self.status_message,
            weights=self.forecaster.describe(),
        )

    async def _pump(self, queue: asyncio.Queue) -> None:
        try:
            async for event in self.market.feed.events():
                await queue.put(event)
            await queue.put(_END)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # surfaced to run()
            await queue.put(exc)

    def _ingest(self, event) -> list[Candle]:
        if isinstance(event, Tick):
            return self.book.add_tick(event)
        if isinstance(event, Snapshot):
            return self.book.add_snapshot(event.candles)
        if isinstance(event, Status):
            self._status(event.message, event.level)
        elif event is _END:
            raise FeedEnded("live feed ended")
        elif isinstance(event, Exception):
            raise event
        return []

    def _wait_time(self, next_update: float) -> float:
        wait = next_update - time.monotonic()
        deadline = self.book.deadline()
        if deadline is not None:
            wait = min(wait, (deadline - self.clock.now()) / self.clock.speed)
        return min(max(wait, 0.01), self.update_interval)

    async def run(self, max_candles: int | None = None) -> Scoreboard:
        """Run until cancelled (or until `max_candles` live candles have closed)."""
        self._emit("start", self.market.info, self.timeframe)
        queue: asyncio.Queue = asyncio.Queue()
        pump = None
        try:
            await self.warm_up()
            self._status(f"streaming from {self.market.feed.name}")
            pump = asyncio.create_task(self._pump(queue))
            next_update = 0.0
            while max_candles is None or self.live_candles < max_candles:
                closed: list[Candle] = []
                try:
                    event = await asyncio.wait_for(queue.get(), self._wait_time(next_update))
                    closed += self._ingest(event)
                    while not queue.empty():
                        closed += self._ingest(queue.get_nowait())
                except asyncio.TimeoutError:
                    pass
                closed += self.book.advance(self.clock.now())
                for candle in closed:
                    outcome = self._observe(candle, live=True)
                    self.live_candles += 1
                    self._emit("candle_closed", candle, outcome, self.forecaster.locked)
                if closed or time.monotonic() >= next_update:
                    self._emit("update", self.view())
                    next_update = time.monotonic() + self.update_interval
        finally:
            if pump is not None:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
            self._emit("stop", self.board)
        return self.board
