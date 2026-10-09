"""pump.fun log decoding: event attribution to the emitting program, and slot numbers."""

import asyncio
import base64
import json
import struct
from pathlib import Path

import pytest

from tartar.data.dataset import load_trade_tokens
from tartar.data.rawlog import event_from_message
from tartar.feeds import pumpchain
from tartar.feeds.pumpchain import PUMP_PROGRAM, TRADE, ChainCreate, ChainTrade, events_from_logs, stream_item

DATA = Path(__file__).parent / "data"
T0 = 1_760_000_000.0


def trade_payload(mint: bytes, sol: int, vsol: int, buy: bool = True) -> str:
    body = mint + struct.pack("<QQ", sol, 3_000_000_000_000) + bytes([buy]) + b"u" * 32 + struct.pack("<qQQ", 1_760_000_000, vsol, 1_000_000_000_000_000)
    body += struct.pack("<QQ", vsol - 30_000_000_000, 700_000_000_000_000) + b"f" * 32 + struct.pack("<QQ", 95, sol * 95 // 10_000) + b"c" * 32
    return "Program data: " + base64.b64encode(TRADE + body).decode()


def test_events_only_count_inside_the_pump_frame():
    other = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
    logs = [
        f"Program {other} invoke [1]",
        trade_payload(b"x" * 32, 5_000_000_000, 40_000_000_000),  # another program's "TradeEvent"
        f"Program {PUMP_PROGRAM} invoke [2]",
        "Program log: Instruction: Buy",
        trade_payload(b"m" * 32, 100_000_000, 35_000_000_000),
        f"Program {PUMP_PROGRAM} consumed 40000 of 200000 compute units",
        f"Program {PUMP_PROGRAM} success",
        trade_payload(b"y" * 32, 7_000_000_000, 41_000_000_000),  # back in the other program's frame
        f"Program {other} success",
    ]
    (event,) = events_from_logs(logs)
    assert isinstance(event, ChainTrade) and event.sol == pytest.approx(0.1) and event.vsol == pytest.approx(35.0)
    assert len(events_from_logs([trade_payload(b"m" * 32, 100_000_000, 35_000_000_000)])) == 1  # no frames: accepted


def test_real_routed_sell_decodes():
    tx = json.loads((DATA / "pump_sell_via_jupiter.json").read_text())
    (event,) = events_from_logs(tx["logs"])
    assert isinstance(event, ChainTrade) and not event.is_buy
    assert event.sol == pytest.approx(0.003548345) and event.vsol == pytest.approx(57.013273292) and event.real_sol == pytest.approx(27.013273292)


def test_stream_items_with_and_without_slot():
    assert stream_item((T0, "sig", [], 123)) == (T0, "sig", [], 123)
    assert stream_item((T0, "sig", [])) == (T0, "sig", [], None)
    assert event_from_message({"txType": "buy", "mint": "M", "solAmount": 1, "tokenAmount": 2, "vSolInBondingCurve": 31, "vTokensInBondingCurve": 1e9, "slot": 77}, T0)["slot"] == 77
    assert "slot" not in event_from_message({"txType": "buy", "mint": "M", "solAmount": 1, "tokenAmount": 2, "vSolInBondingCurve": 31, "vTokensInBondingCurve": 1e9}, T0)
    assert event_from_message({"txType": "migrate", "mint": "M", "slot": 9}, T0) == {"e": "migrate", "t": T0, "mint": "M", "slot": 9}


async def test_chain_recorder_writes_slots(tmp_path, monkeypatch):
    from tartar.data.recorder import ChainRecorder
    from tartar.feeds.base import Status

    def trade(user, sol, vsol):
        return ChainTrade("MintS", sol, sol * 3e7, True, user, int(T0), vsol, 32.19e9 / vsol, "dev", vsol - 30)

    now = [T0]

    async def fake_stream(urls=None):
        yield Status("connected", kind="connected")
        yield T0, "s1", [ChainCreate("MintS", "S", "S", "dev", None), trade("dev", 1.0, 31.0)], 1000
        for i in range(30):
            now[0] = T0 + 5 + 5 * i
            yield now[0], f"t{i}", [trade(f"w{i}", 0.1, 31.0 + 0.1 * (i + 1))], 1010 + 12 * i
        now[0] = T0 + 200
        yield now[0], "old", [trade("v", 0.1, 34.2)]  # a stream without slots still works
        await asyncio.sleep(3600)

    monkeypatch.setattr(pumpchain, "stream_program_events", fake_stream)
    recorder = ChainRecorder(tmp_path, clock=lambda: now[0], track_minutes=60, idle_minutes=30)
    await recorder.run(duration=0.5)
    from tartar.data.rawlog import raw_files, read_events

    events = list(read_events(raw_files(tmp_path)))
    create = next(e for e in events if e["e"] == "create")
    trades = [e for e in events if e["e"] == "trade"]
    assert create["slot"] == 1000 and trades[0]["slot"] == 1010 and "slot" not in trades[-1]
    (token,) = load_trade_tokens(tmp_path, 60)
    slots = [tick.slot for group in token.ticks.values() for tick, _ in group]
    assert slots[0] == 1000 and 1010 in slots


def test_curves_quoted_in_other_tokens_decode_with_their_quote():
    (trade,) = events_from_logs(json.loads((DATA / "pump_trade_quoted.json").read_text())["logs"])
    assert trade.quote_mint == "WXMRyRZhsa19ety5erZhHg4N3xj3EVN92u94422teJp" and trade.sol == 0 and trade.price == 0
    assert trade.quote_amount == 232_421_770_913 and trade.vquote > 0 and trade.tokens == pytest.approx(5590780.730242)
    (create,) = events_from_logs(json.loads((DATA / "pump_create_quoted.json").read_text())["logs"])
    assert isinstance(create, ChainCreate) and create.quote_mint.endswith("pump")
    (sol_trade,) = events_from_logs(json.loads((DATA / "pump_sell_via_jupiter.json").read_text())["logs"])
    assert sol_trade.quote_mint == "" and sol_trade.price > 0


async def test_quoted_launches_are_recorded_but_kept_out_of_sol_data(tmp_path, monkeypatch):
    from tartar.data.recorder import ChainRecorder
    from tartar.data.rawlog import raw_files, read_events
    from tartar.feeds.base import Status

    now = [T0]

    def sol_trade(user, sol, vsol):
        return ChainTrade("MintS", sol, sol * 3e7, True, user, int(T0), vsol, 32.19e9 / vsol, "dev", vsol - 30)

    def quoted(user, amount, vq):
        return ChainTrade("MintQ", 0.0, 1e6, True, user, int(T0), 0.0, 1e9 - vq, "dev2", None, "USDCmint", amount, vq, vq - 4_292_000_000)

    async def fake_stream(urls=None):
        yield Status("connected", kind="connected")
        yield T0, "a", [ChainCreate("MintS", "S", "S", "dev", None), sol_trade("dev", 1.0, 31.0)], 1
        yield T0, "b", [ChainCreate("MintQ", "Q", "Q", "dev2", None, quote_mint="USDCmint"), quoted("dev2", 50_000_000, 4_342_000_000)], 1
        for i in range(60):
            now[0] = T0 + 5 + 5 * i
            yield now[0], f"s{i}", [sol_trade(f"w{i}", 0.1, 31.0 + 0.1 * (i + 1)), quoted(f"q{i}", 1_000_000, 4_343_000_000 + i)], 2 + i
        await asyncio.sleep(3600)

    monkeypatch.setattr(pumpchain, "stream_program_events", fake_stream)
    await ChainRecorder(tmp_path, clock=lambda: now[0], track_minutes=60, idle_minutes=30).run(duration=0.5)
    events = list(read_events(raw_files(tmp_path)))
    q_create = next(e for e in events if e["e"] == "create" and e["mint"] == "MintQ")
    q_trades = [e for e in events if e["e"] == "trade" and e["mint"] == "MintQ"]
    assert q_create["quote"] == "USDCmint" and q_create.get("vsol") is None
    assert len(q_trades) == 61 and q_trades[0]["qamt"] == 50_000_000 and q_trades[0].get("vsol") is None
    assert [t.mint for t in load_trade_tokens(tmp_path, 60)] == ["MintS"]


async def test_screener_skips_quoted_launches():
    from tartar.screen import next_clean_launch

    verdicts = []

    async def stream():
        yield T0, "q", [ChainCreate("MintQ", "Q", "Q", "dev", None, quote_mint="USDCmint")], 1

    with pytest.raises(ConnectionError):  # the stream ends without a SOL launch passing
        await next_clean_launch(stream(), screen_seconds=20, min_buyers=3, on_verdict=verdicts.append, clock=lambda: T0)
    (verdict,) = verdicts
    assert verdict.candidate.create.mint == "MintQ" and "not SOL" in verdict.reason and not verdict.passed
