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


def test_several_recorder_directories_merge(tmp_path):
    from tartar.data.rawlog import RawWriter

    def write(directory, mint, offset):
        writer = RawWriter(directory, clock=lambda: T0 + offset)
        events = [{"e": "session", "t": T0 + offset, "state": "connected"}, {"e": "create", "t": T0 + offset + 1, "mint": mint, "creator": "dev", "name": "A", "symbol": "A", "sol": 1.0, "tok": 3e7, "vsol": 31.0, "vtok": 1.038e9, "rsol": 1.0}, {"e": "track", "t": T0 + offset + 1, "mint": mint}]
        events += [{"e": "trade", "t": T0 + offset + 2 + 5 * i, "mint": mint, "side": "b", "trader": f"w{i}", "sol": 0.1, "tok": 3e6, "vsol": 31.0 + 0.1 * (i + 1), "vtok": 32.19e9 / (31.0 + 0.1 * (i + 1)), "rsol": 1.0 + 0.1 * (i + 1)} for i in range(60)]
        events += [{"e": "session", "t": T0 + offset + 400, "state": "stopped"}]
        for e in events:
            writer.write(e)
        writer.close()

    write(tmp_path / "a", "MintA", 0)
    write(tmp_path / "b", "MintB", 7200)  # another recorder, another directory
    write(tmp_path / "b2", "MintA", 0)  # the same launch caught twice
    tokens = load_trade_tokens(f"{tmp_path / 'a'},{tmp_path / 'b'},{tmp_path / 'b2'}", 60)
    assert [t.mint for t in tokens] == ["MintA", "MintB"]
    assert [t.mint for t in load_trade_tokens([tmp_path / "a", tmp_path / "b"], 60)] == ["MintA", "MintB"]


async def test_recorder_follows_graduated_tokens_on_pumpswap(tmp_path, monkeypatch):
    from tartar.data.recorder import ChainRecorder
    from tartar.data.rawlog import raw_files, read_events
    from tartar.feeds.base import Status
    from tartar.feeds.pumpchain import ChainComplete
    from tartar.feeds.pumpswap import SwapTrade, canonical_pool

    buy_tx = json.loads((DATA / "pumpswap_buy.json").read_text())
    mint = buy_tx["mint"]
    pool = canonical_pool(mint)
    now = [T0]
    asked = []

    async def fake_stream(urls=None, extra=None):
        yield Status("connected", kind="connected")
        yield T0, "g", [ChainComplete(mint)], 500
        asked.append(dict(extra()))
        now[0] = T0 + 5
        yield now[0], "s1", [SwapTrade(pool, True, 1000.0, 0.01, 0.0101, "u1", int(T0), 9e8, 90.0, "dev")], 510
        yield now[0], "s2", [SwapTrade("OtherPool", True, 1.0, 0.01, 0.0101, "u2", int(T0), 9e8, 90.0)], 511
        now[0] = T0 + 3 * 3600  # past the recording window
        yield now[0], "s3", [ChainTrade("M", 0.1, 3e6, True, "w", int(T0), 31.0, 1.038e9, "dev", 1.0)], 600
        asked.append(dict(extra()))
        await asyncio.sleep(3600)

    monkeypatch.setattr(pumpchain, "stream_program_events", fake_stream)
    recorder = ChainRecorder(tmp_path, clock=lambda: now[0], pumpswap_hours=2, housekeeping=0)
    await recorder.run(duration=0.5)
    events = list(read_events(raw_files(tmp_path)))
    (grad,) = [e for e in events if e["e"] == "graduate"]
    swaps = [e for e in events if e["e"] == "swap"]
    assert grad == {"e": "graduate", "t": T0, "mint": mint, "pool": pool, "slot": 500}
    assert len(swaps) == 1 and swaps[0]["mint"] == mint and swaps[0]["sol_after"] / swaps[0]["tok_after"] == pytest.approx(1e-7)
    assert list(asked[0]) == [pool] and asked[1] == {}  # watched after graduation, dropped after the window
    assert any(e["e"] == "unwatch" and e["reason"] == "age" for e in events)


async def test_stream_watches_extra_accounts_on_one_connection(monkeypatch):
    import websockets

    pump_logs = json.loads((DATA / "pump_sell_via_jupiter.json").read_text())["logs"]
    swap_logs = json.loads((DATA / "pumpswap_buy.json").read_text())["logs"]
    seen = []

    async def server(ws):
        subs = {}
        async for raw in ws:
            msg = json.loads(raw)
            seen.append((msg["method"], msg["params"][0]))
            if msg["method"] == "logsSubscribe":
                sub = 100 + len(subs)
                subs[msg["params"][0]["mentions"][0]] = sub
                await ws.send(json.dumps({"jsonrpc": "2.0", "result": sub, "id": msg["id"]}))
                logs = pump_logs if sub == 100 else swap_logs
                note = {"jsonrpc": "2.0", "method": "logsNotification", "params": {"subscription": sub, "result": {"context": {"slot": 7}, "value": {"signature": f"s{sub}", "err": None, "logs": logs}}}}
                await ws.send(json.dumps(note))
            else:
                await ws.send(json.dumps({"jsonrpc": "2.0", "result": True, "id": msg["id"]}))

    from tartar.feeds.pumpswap import SwapTrade, swap_events_from_logs

    wanted = {"POOL": swap_events_from_logs}
    async with websockets.serve(server, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        got = []
        async for item in pumpchain.stream_program_events((f"ws://127.0.0.1:{port}",), extra=lambda: dict(wanted)):
            if isinstance(item, tuple):
                got.append(item)
                if len(got) == 2:
                    break
    kinds = sorted(type(e).__name__ for _, _, events, _ in got for e in events)
    assert kinds == ["ChainTrade", "SwapTrade"]  # each subscription decoded by its own decoder
    assert ("logsSubscribe", {"mentions": ["POOL"]}) in seen
