import asyncio
import io
import json

import pytest

from tartar.agent import CandleAgent, FeedEnded, Sink
from tartar.candles import Candle, Tick
from tartar.clock import SimClock
from tartar.feeds.base import LiveFeed, Snapshot, Status
from tartar.feeds.synthetic import MemecoinSimulator, SyntheticFeed, synthetic_history
from tartar.market import Market, MarketInfo
from tartar.output import JsonLines, PlainPrinter

INFO = MarketInfo("MINTpump", "MEME", "Meme Coin", "SOL", "test")


class ScriptFeed(LiveFeed):
    """Replays (sim time, event) pairs, then optionally ends or fails."""

    name = "script"

    def __init__(self, clock, script, end=None, counts_trades=True, grace=1.0):
        self.clock, self.script, self.end = clock, script, end
        self.counts_trades = counts_trades
        self.close_grace = grace

    async def events(self):
        for at, event in self.script:
            await self.clock.sleep(at - self.clock.now())
            yield event
        if self.end == "fail":
            raise RuntimeError("socket exploded")
        if self.end == "stop":
            return
        while True:
            await self.clock.sleep(3600)


class Recorder(Sink):
    def __init__(self):
        self.calls = []

    def __getattribute__(self, name):
        if name in ("start", "warmed_up", "candle_closed", "update", "status", "stop"):
            return lambda *args: object.__getattribute__(self, "calls").append((name, args))
        return object.__getattribute__(self, name)


async def test_demo_agent_end_to_end_json_and_plain():
    clock = SimClock(start=1_700_000_000, speed=600)
    sim = MemecoinSimulator(seed=5)
    history = synthetic_history(sim, clock.now(), 60, 120)

    async def load():
        return history

    json_out, plain_out = io.StringIO(), io.StringIO()
    sinks = [JsonLines(json_out, every=0), PlainPrinter(plain_out, every=0)]
    agent = CandleAgent(Market(INFO, SyntheticFeed(sim, clock), load, clock), 60, sinks=sinks, update_interval=0.05)
    board = await asyncio.wait_for(agent.run(max_candles=3), timeout=20)

    assert board.history.n >= 115 and board.live.n == 3
    events = [json.loads(line) for line in json_out.getvalue().splitlines()]
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "summary"
    assert {"warmup", "candle", "result", "forecast", "prediction"} <= set(types)
    prediction = next(e for e in events if e["type"] == "prediction")
    assert prediction["band"]["low"] <= prediction["predicted_close"] <= prediction["band"]["high"]
    assert 0 <= prediction["confidence"] <= 1 and prediction["direction"] in ("up", "down", "flat")
    results = [e for e in events if e["type"] == "result"]
    forecasts = [e for e in events if e["type"] == "forecast"]
    assert results[1]["predicted_close"] == forecasts[0]["predicted_close"]  # locked forecast is what gets scored
    text = plain_out.getvalue()
    assert "Warm-up on" in text and "next [" in text and "live:" in text


async def test_snapshot_feed_closes_candles_and_scores():
    clock = SimClock(start=0, speed=600)
    script = [
        (1, Snapshot([Candle(0, 1.0, 1.1, 0.9, 1.05, volume=5)])),
        (61, Snapshot([Candle(0, 1.0, 1.1, 0.9, 1.06, volume=6), Candle(60, 1.06, 1.2, 1.0, 1.1, volume=3)])),
        (125, Snapshot([Candle(120, 1.1, 1.1, 1.0, 1.02, volume=3)])),
        (181, Status("still here")),
    ]
    feed = ScriptFeed(clock, script, end="stop", counts_trades=False, grace=10)
    recorder = Recorder()
    agent = CandleAgent(Market(INFO, feed, None, clock), 60, sinks=[recorder], update_interval=0.02)
    with pytest.raises(FeedEnded):
        await asyncio.wait_for(agent.run(), timeout=10)
    closed = [args[0] for name, args in recorder.calls if name == "candle_closed"]
    assert [c.start for c in closed] == [0, 60]
    assert closed[0].close == 1.06  # snapshot revision before close wins
    outcomes = [args[1] for name, args in recorder.calls if name == "candle_closed"]
    assert outcomes[0] is None and outcomes[1].actual == 1.1
    assert ("status", ("still here", "info")) in recorder.calls
    assert recorder.calls[-1][0] == "stop"


async def test_quiet_market_closes_flat_candles_by_clock():
    clock = SimClock(start=0, speed=300)
    feed = ScriptFeed(clock, [(1, Tick(1, 2.0)), (2, Tick(2, 2.2))])
    agent = CandleAgent(Market(INFO, feed, None, clock), 60, update_interval=0.02)
    board = await asyncio.wait_for(agent.run(max_candles=3), timeout=10)
    candles = list(agent.book.closed)
    assert [c.start for c in candles] == [0, 60, 120]
    assert not candles[1].active and candles[1].close == 2.2
    assert board.live.n == 2


async def test_feed_errors_propagate_and_sinks_stop():
    clock = SimClock(start=0, speed=100)
    recorder = Recorder()
    agent = CandleAgent(Market(INFO, ScriptFeed(clock, [(1, Tick(1, 1.0))], end="fail"), None, clock), 60, sinks=[recorder])
    with pytest.raises(RuntimeError, match="socket exploded"):
        await asyncio.wait_for(agent.run(), timeout=10)
    assert recorder.calls[-1][0] == "stop"


async def test_history_failure_is_not_fatal():
    clock = SimClock(start=0, speed=300)

    async def broken():
        raise ConnectionError("history down")

    recorder = Recorder()
    feed = ScriptFeed(clock, [(1, Tick(1, 1.0)), (61, Tick(61, 1.1))])
    agent = CandleAgent(Market(INFO, feed, broken, clock), 60, sinks=[recorder], update_interval=0.02)
    await asyncio.wait_for(agent.run(max_candles=1), timeout=10)
    assert any(name == "status" and "history unavailable" in args[0] for name, args in recorder.calls)
