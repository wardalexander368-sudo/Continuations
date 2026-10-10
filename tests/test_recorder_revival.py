"""Recorder revival (`tartar record --revive-hours`): idle tokens stay dormant and are re-tracked when they trade."""

import asyncio

from tartar.data.dataset import load_trade_tokens
from tartar.data.rawlog import raw_files, read_events
from tartar.feeds import pumpchain
from tartar.feeds.base import Status
from tartar.feeds.pumpchain import ChainCreate, ChainTrade

T0 = 1_760_000_000.0


def trade(mint, user, sol, vsol):
    return ChainTrade(mint, sol, sol * 3e7, True, user, int(T0), vsol, 32.19e9 / vsol, "dev", vsol - 30)


async def record(tmp_path, monkeypatch, revive_hours, dormant=None):
    now = [T0]

    async def fake_stream(urls=None):
        yield Status("connected", kind="connected")
        yield T0, "c", [ChainCreate("MintR", "R", "R", "dev", None), trade("MintR", "dev", 1.0, 31.0)], 1
        for i in range(5):
            now[0] = T0 + 5 + 5 * i
            yield now[0], f"t{i}", [trade("MintR", f"w{i}", 0.1, 31.0 + 0.1 * (i + 1))], 2 + i
        now[0] = T0 + 900  # 15 quiet minutes: idle (10 min) untracks it
        yield now[0], "other", [trade("Other", "x", 0.1, 31.0)], 50
        now[0] = T0 + 3600  # an hour after launch it wakes up
        yield now[0], "wake", [trade("MintR", "late", 0.5, 32.0)], 60
        now[0] = T0 + 3605
        yield now[0], "wake2", [trade("MintR", "late2", 0.5, 32.5)], 61
        await asyncio.sleep(3600)

    monkeypatch.setattr(pumpchain, "stream_program_events", fake_stream)
    from tartar.data.recorder import ChainRecorder

    recorder = ChainRecorder(tmp_path, clock=lambda: now[0], track_minutes=120, idle_minutes=10, revive_hours=revive_hours, dormant=dormant)
    await recorder.run(duration=0.5)
    return recorder, list(read_events(raw_files(tmp_path)))


async def test_revival_off_drops_the_late_trades(tmp_path, monkeypatch):
    _, events = await record(tmp_path, monkeypatch, 0.0)
    assert [e["reason"] for e in events if e["e"] == "untrack"] == ["idle"]
    assert not [e for e in events if e["e"] == "trade" and e["t"] >= T0 + 3600]


async def test_revival_retracks_and_keeps_the_loader_unchanged(tmp_path, monkeypatch):
    recorder, events = await record(tmp_path, monkeypatch, 48.0)
    revived = [e for e in events if e["e"] == "track" and e.get("reason") == "revived"]
    assert len(revived) == 1 and revived[0]["created"] == T0 and revived[0]["creator"] == "dev" and revived[0]["t"] == T0 + 3600
    late = [e for e in events if e["e"] == "trade" and e["t"] >= T0 + 3600]
    assert [e["trader"] for e in late] == ["late", "late2"]
    # loaders end a token at its first untrack, as before: the revived trades don't leak into training
    (token,) = load_trade_tokens(tmp_path, 60, min_candles=0)
    assert token.end_reason == "idle" and token.end < T0 + 3600
    # the revived token is tracked now, so a later run would carry it over with its launch time
    assert recorder.dormant_state() == {"MintR": (T0, "dev")}


async def test_dormant_tokens_carry_over_between_runs(tmp_path, monkeypatch):
    # a token launched in an earlier run (no create in this run's files) is revived from the carried state
    _, events = await record(tmp_path, monkeypatch, 48.0, dormant={"Other": (T0 - 3600, "someone"), "Old": (T0 - 49 * 3600, "x")})
    other = [e for e in events if e["e"] == "track" and e["mint"] == "Other"]
    assert other and other[0]["reason"] == "revived" and other[0]["created"] == T0 - 3600
    assert [e["mint"] for e in events if e["e"] == "trade" and e["mint"] == "Other"] == ["Other"]
