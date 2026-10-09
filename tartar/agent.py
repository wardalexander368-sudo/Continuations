"""The agent: watch a token's candles live, predict each close, and report as it goes."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from .candles import Candle, CandleBook, Tick
from .feeds.base import Snapshot, Status
from .market import Market, MarketInfo
from .model import Forecast, Forecaster, Outcome
from .model.global_model import GlobalModel
from .scam import CreatorIndex, ScamReport, StaticReport, assess, static_checks
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
    risk: ScamReport | None = None


class Sink:
    """Receives the agent's output. Override what you need."""

    def start(self, info: MarketInfo, timeframe: int) -> None: ...

    def warmed_up(self, candles: int, board: Scoreboard) -> None: ...

    def candle_closed(self, candle: Candle, outcome: Outcome | None, next_forecast: Forecast | None) -> None: ...

    def update(self, view: View) -> None: ...

    def status(self, message: str, level: str) -> None: ...

    def risk(self, report: ScamReport) -> None:
        """Called when the token's risk level or red flags change."""

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
        scam_checks: bool = True,
        creators: CreatorIndex | None = None,
        static_refresh: float = 600.0,
        after_graduation: Callable[[], GlobalModel | None] | None = None,
        p_rug: float | None = None,
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
        self.scam_checks = scam_checks
        self.creators = creators
        self.static: StaticReport | None = None
        self.static_refresh = static_refresh
        self.risk_report: ScamReport | None = None
        self.p_rug = p_rug  # P(rug) judged at the launch screen (rug.py), shown beside the risk level
        self._model = model
        self._domain = info.domain
        # At graduation the curve model no longer applies; this finds the PumpSwap model, if any.
        self.after_graduation = after_graduation
        self._coverage = coverage
        # Feed health: candles the feed did not fully see are never scored or learned from.
        self.outage_from: float | None = None  # feed currently down since this time
        self.max_gap = 10.0  # reconnects faster than this don't break observation
        self.observed_from: float | None = None  # first candle start fully seen after an outage
        self.unobserved = 0

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

    def assess_risk(self) -> ScamReport:
        info = self.market.info
        report = assess(
            self.forecaster.wallets,
            self.static,
            self.creators,
            mint=info.address,
            creator=info.creator,
            name=info.name,
            symbol=info.symbol,
            uri=info.uri,
        )
        report.p_rug = self.p_rug
        previous = self.risk_report
        if previous is None or previous.level != report.level or {f.code for f in previous.flags} != {f.code for f in report.flags}:
            self._emit("risk", report)
        self.risk_report = report
        return report

    async def _refresh_static(self) -> None:
        """Mint checks and RugCheck in the background; never blocks predictions."""
        while True:
            self.static = await static_checks(self.market.info.address)
            for error in self.static.errors:
                self._status(f"scam check: {error}", "warn")
            # New launches are often not on RugCheck yet: look again soon.
            await asyncio.sleep(self.static_refresh if self.static.rugcheck else min(60.0, self.static_refresh))

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
            risk=self.assess_risk(),
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
            self._feed_health(event)
        elif event is _END:
            raise FeedEnded("live feed ended")
        elif isinstance(event, Exception):
            raise event
        return []

    def _process(self, event) -> int:
        """Handle one feed event fully: close any candles it ends, then apply the trade."""
        closed = self._ingest(event)
        self._close_live(closed)
        if isinstance(event, Tick):
            self.forecaster.on_tick(event)
        return len(closed)

    def _feed_health(self, status: Status) -> None:
        now = self.clock.now()
        if status.kind == "graduated" and self._domain != "pumpswap":
            # The curve model knows bonding curves only. On PumpSwap, use the model trained on
            # graduated pools if there is one (it was trained on exactly this restart: history
            # without trade detail, wallets from scratch); else the online model carries on.
            had_model = self._model is not None
            self._model = self.after_graduation() if self.after_graduation is not None else None
            self._domain = "pumpswap"
            if self._model is not None:
                self._resync("graduated: PumpSwap model on; online model continues")
            elif had_model:
                self._resync("graduated: global model off (it covers bonding curves only); online model continues on PumpSwap")
        if status.kind == "disconnected" and self.outage_from is None:
            self.outage_from = now
        elif status.kind == "connected" and self.outage_from is not None:
            if now - self.outage_from > self.max_gap:
                # Data is complete again from the next candle boundary on.
                self.observed_from = self.book.period(now) + self.timeframe
            # A blip of a few seconds only loses those seconds' trades (as in training).
            self.outage_from = None

    def _seen(self, candle: Candle) -> bool:
        now = self.clock.now()
        if self.outage_from is not None and candle.start + self.timeframe > self.outage_from and now - self.outage_from > self.max_gap:
            return False
        return self.observed_from is None or candle.start >= self.observed_from

    def _resync(self, message: str = "feed back: resynced after an outage (candles it missed were not scored)") -> None:
        """After an outage, restart the forecaster the way a mid-life join starts: candle
        history without trade detail, wallet tracking from scratch (as in training)."""
        info = self.market.info
        self.forecaster = Forecaster(
            self.timeframe,
            self._coverage,
            model=self._model,
            domain=self._domain,
            launched_at=info.launched_at,
            creator_known=False,
        )
        for c in self.book.closed:
            self.forecaster.observe(Candle(c.start, c.open, c.high, c.low, c.close, volume=c.volume, trades=None))
        self._status(message)

    def _close_live(self, closed: list[Candle]) -> None:
        for candle in closed:
            self.live_candles += 1
            if not self._seen(candle):
                self.unobserved += 1
                if self.observed_from is not None and candle.start + self.timeframe == self.observed_from:
                    self._resync()
                self._emit("candle_closed", candle, None, None)
                continue
            outcome = self._observe(candle, live=True)
            self._emit("candle_closed", candle, outcome, self.forecaster.locked)

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
        tasks: list[asyncio.Task] = []
        try:
            if self.scam_checks:
                tasks.append(asyncio.create_task(self._refresh_static()))
            await self.warm_up()
            self._status(f"streaming from {self.market.feed.name}")
            tasks.append(asyncio.create_task(self._pump(queue)))
            next_update = 0.0
            while max_candles is None or self.live_candles < max_candles:
                closed = 0
                try:
                    event = await asyncio.wait_for(queue.get(), self._wait_time(next_update))
                    closed += self._process(event)
                    while not queue.empty():
                        closed += self._process(queue.get_nowait())
                except asyncio.TimeoutError:
                    pass
                timed_out = self.book.advance(self.clock.now())
                self._close_live(timed_out)
                if closed or timed_out or time.monotonic() >= next_update:
                    self._emit("update", self.view())
                    next_update = time.monotonic() + self.update_interval
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._emit("stop", self.board)
        return self.board
