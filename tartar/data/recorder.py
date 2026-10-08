"""Record every new pump.fun launch and its trades, for training.

`ChainRecorder` reads the chain through a Solana RPC websocket (free). `Recorder`
uses PumpPortal, whose per-token trade stream needs an API key funded with SOL.
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from ..feeds.pumpportal import WS_URL, _url
from .rawlog import RawWriter, event_from_message


@dataclass
class _Tracked:
    created: float
    last: float


@dataclass
class RecorderStats:
    tracked: int
    total_tokens: int
    events: int
    trades: int
    connected: bool


class Recorder:
    """Subscribes to new launches, then to each new token's trades for `track_minutes`
    (or until it goes quiet for `idle_minutes`), writing everything to raw log files."""

    def __init__(
        self,
        out_dir: str | Path,
        *,
        url: str = WS_URL,
        api_key: str | None = None,
        track_minutes: float = 60.0,
        idle_minutes: float = 10.0,
        max_tokens: int = 1500,
        clock: Callable[[], float] = time.time,
        housekeeping: float = 2.0,
    ):
        self.writer = RawWriter(out_dir, clock)
        self.url = _url(url, api_key)
        self.track_seconds = track_minutes * 60
        self.idle_seconds = idle_minutes * 60
        self.max_tokens = max_tokens
        self.clock = clock
        self.housekeeping = housekeeping
        self.tracked: dict[str, _Tracked] = {}
        self._pending: list[str] = []
        self.total_tokens = 0
        self.trades = 0
        self.connected = False

    def stats(self) -> RecorderStats:
        return RecorderStats(len(self.tracked), self.total_tokens, self.writer.events, self.trades, self.connected)

    def _session(self, state: str) -> None:
        self.connected = state == "connected"
        self.writer.write({"e": "session", "t": self.clock(), "state": state})

    def handle(self, msg: dict) -> None:
        now = self.clock()
        event = event_from_message(msg, now)
        if event is None:
            return
        mint = event["mint"]
        if event["e"] == "create":
            self.writer.write(event)
            self.total_tokens += 1
            if len(self.tracked) < self.max_tokens:
                self.tracked[mint] = _Tracked(now, now)
                self._pending.append(mint)
        elif mint in self.tracked:
            self.writer.write(event)
            if event["e"] == "trade":
                self.trades += 1
                self.tracked[mint].last = now
            else:  # migrated: bonding-curve trading is over
                self._untrack([mint], "migrated")

    def _untrack(self, mints: list[str], reason: str) -> list[str]:
        now = self.clock()
        for mint in mints:
            if self.tracked.pop(mint, None) is not None:
                self.writer.write({"e": "untrack", "t": now, "mint": mint, "reason": reason})
        return mints

    async def _maintain(self, ws) -> None:
        while True:
            await asyncio.sleep(self.housekeeping)
            now = self.clock()
            if self._pending:
                batch, self._pending = self._pending, []
                await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": batch}))
                for mint in batch:
                    self.writer.write({"e": "track", "t": now, "mint": mint})
            expired = [m for m, s in self.tracked.items() if now - s.created > self.track_seconds]
            idle = [m for m, s in self.tracked.items() if m not in expired and now - s.last > self.idle_seconds]
            done = self._untrack(expired, "age") + self._untrack(idle, "idle")
            if done:
                await ws.send(json.dumps({"method": "unsubscribeTokenTrade", "keys": done}))
            self.writer.flush()

    async def run(self, duration: float | None = None, on_stats: Callable[[RecorderStats], None] | None = None) -> RecorderStats:
        deadline = None if duration is None else self.clock() + duration
        backoff = 1.0
        try:
            while deadline is None or self.clock() < deadline:
                try:
                    async with connect(self.url, open_timeout=15, ping_interval=20, max_size=None) as ws:
                        self._session("connected")
                        backoff = 1.0
                        await ws.send(json.dumps({"method": "subscribeNewToken"}))
                        await ws.send(json.dumps({"method": "subscribeMigration"}))
                        # Trades during a disconnection were missed, so tracking starts over.
                        self._pending = list(self.tracked)
                        maintain = asyncio.create_task(self._maintain(ws))
                        reporter = asyncio.create_task(self._report(on_stats)) if on_stats else None
                        try:
                            await self._consume(ws, deadline)
                        finally:
                            for task in (maintain, reporter):
                                if task is not None:
                                    task.cancel()
                            await asyncio.gather(maintain, *([reporter] if reporter else []), return_exceptions=True)
                except (OSError, WebSocketException, asyncio.TimeoutError):
                    pass
                if self.connected:
                    self._session("disconnected")
                if deadline is not None and self.clock() >= deadline:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
        finally:
            self.writer.write({"e": "session", "t": self.clock(), "state": "stopped"})
            self.writer.close()
        return self.stats()

    async def _consume(self, ws, deadline: float | None) -> None:
        while deadline is None or self.clock() < deadline:
            timeout = None if deadline is None else max(deadline - self.clock(), 0.01)
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout)
            except asyncio.TimeoutError:
                return
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if isinstance(msg, dict):
                self.handle(msg)

    async def _report(self, on_stats: Callable[[RecorderStats], None]) -> None:
        while True:
            await asyncio.sleep(30)
            on_stats(self.stats())


class ChainRecorder(Recorder):
    """Records launches and trades straight from the chain (Solana RPC logs; free, no API key).

    The program-wide log stream carries every pump.fun trade, so tokens need no
    per-token subscription: a token is tracked from its creation for
    `track_minutes`, or until it goes quiet for `idle_minutes`.
    """

    def __init__(self, out_dir: str | Path, *, urls: tuple[str, ...] | None = None, **kwargs):
        kwargs.pop("url", None)
        kwargs.pop("api_key", None)
        super().__init__(out_dir, **kwargs)
        self.urls = urls

    async def run(self, duration: float | None = None, on_stats: Callable[[RecorderStats], None] | None = None) -> RecorderStats:
        try:
            if duration is None:
                await self._stream(on_stats)
            else:
                try:
                    await asyncio.wait_for(self._stream(on_stats), duration)
                except asyncio.TimeoutError:
                    pass
        finally:
            if self.connected:
                self._session("disconnected")
            self.writer.write({"e": "session", "t": self.clock(), "state": "stopped"})
            self.writer.close()
        return self.stats()

    async def _stream(self, on_stats: Callable[[RecorderStats], None] | None) -> None:
        from ..feeds.base import Status
        from ..feeds.pumpchain import ChainComplete, ChainCreate, ChainTrade, create_to_message, stream_program_events, trade_to_message

        last_housekeeping = last_report = self.clock()
        async with aclosing(stream_program_events(self.urls)) as stream:
            async for item in stream:
                now = self.clock()
                if isinstance(item, Status):
                    if item.level == "info":
                        if self.connected:
                            self._session("disconnected")
                        self._session("connected")
                    elif self.connected:
                        self._session("disconnected")
                    continue
                _, _, events = item
                created = {e.mint for e in events if isinstance(e, ChainCreate)}
                first_buys = {}
                for event in events:
                    if isinstance(event, ChainTrade) and event.mint in created and event.mint not in first_buys:
                        first_buys[event.mint] = event  # the creator's initial buy, folded into the create
                for event in events:
                    if isinstance(event, ChainCreate):
                        self.handle(create_to_message(event, first_buys.get(event.mint)))
                        if event.mint in self.tracked:
                            self.writer.write({"e": "track", "t": now, "mint": event.mint})
                    elif isinstance(event, ChainTrade):
                        if first_buys.get(event.mint) is not event:
                            self.handle(trade_to_message(event))
                    elif isinstance(event, ChainComplete):
                        self.handle({"txType": "migrate", "mint": event.mint})
                if now - last_housekeeping >= self.housekeeping:
                    last_housekeeping = now
                    expired = [m for m, s in self.tracked.items() if now - s.created > self.track_seconds]
                    idle = [m for m, s in self.tracked.items() if m not in expired and now - s.last > self.idle_seconds]
                    self._untrack(expired, "age")
                    self._untrack(idle, "idle")
                    self._pending.clear()  # nothing to subscribe to: the stream carries every token
                    self.writer.flush()
                if on_stats is not None and now - last_report >= 30:
                    last_report = now
                    on_stats(self.stats())
