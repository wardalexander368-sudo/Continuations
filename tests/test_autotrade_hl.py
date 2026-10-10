"""The live gate and the Hyperliquid order sender, offline (fake exchange). The testnet run is
tests/test_hl_testnet.py."""

import json

import pytest

pytest.importorskip("eth_account")
pytest.importorskip("msgpack")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_typed_data  # noqa: E402
from eth_utils import keccak  # noqa: E402

import msgpack  # noqa: E402

from tartar.autotrade import broker as broker_mod  # noqa: E402
from tartar.autotrade import gate  # noqa: E402
from tartar.autotrade.broker import LiveBroker  # noqa: E402
from tartar.autotrade.core import CostModel, Intent  # noqa: E402
from tartar.autotrade.hl_exchange import (HyperliquidExchange, LivePerpExecutor, float_to_wire, l1_typed_data,  # noqa: E402
                                          make_live_perp_executor, round_px)
from tartar.autotrade.ledger import Ledger  # noqa: E402
from tartar.autotrade.perps import select_perp_route  # noqa: E402

KEY = "0x" + "11" * 32
ACCOUNT = "0x" + "ab" * 20
CFG = {"mode": "live", "live_approved_on": "2026-10-10", "live": {"perps": {"network": "testnet"}}}
ENV = {"TARTAR_LIVE_APPROVED": "2026-10-10", "HYPERLIQUID_AGENT_KEY": KEY, "HYPERLIQUID_ACCOUNT": ACCOUNT}
NOW = 100_000.0


def test_gate_needs_mode_approval_keys_and_no_kill(tmp_path):
    keys = ("HYPERLIQUID_AGENT_KEY", "HYPERLIQUID_ACCOUNT")
    assert gate.live_reason(CFG, ENV, keys, tmp_path) is None
    assert "not 'live'" in gate.live_reason({**CFG, "mode": "dry_live"}, ENV, keys)
    assert "not approved" in gate.live_reason(CFG, {**ENV, "TARTAR_LIVE_APPROVED": "2026-10-09"}, keys)
    assert "not approved" in gate.live_reason({**CFG, "live_approved_on": None}, ENV, keys)
    assert gate.live_reason(CFG, {k: v for k, v in ENV.items() if k != "HYPERLIQUID_ACCOUNT"}, keys) == "missing HYPERLIQUID_ACCOUNT"
    (tmp_path / "HALT_LIVE").write_text("stop")
    assert gate.live_reason(CFG, ENV, keys, tmp_path).startswith("live kill switch")
    assert gate.live_reason(CFG, {**ENV, "TARTAR_LIVE_KILL": "1"}, keys).startswith("live kill switch")
    with pytest.raises(gate.LiveNotAllowed):
        gate.require_live({**CFG, "mode": "dry_live"}, ENV, keys)


def test_perp_route_live_only_past_the_gate():
    assert select_perp_route("live", ENV, CFG) == "live"
    assert select_perp_route("live", {**ENV, "TARTAR_LIVE_APPROVED": ""}, CFG) is None
    assert select_perp_route("live", {"TARTAR_LIVE_APPROVED": "2026-10-10"}, CFG) is None
    assert select_perp_route("dry_live", ENV, CFG) == "dry"
    with pytest.raises(gate.LiveNotAllowed):
        make_live_perp_executor({**CFG, "live_approved_on": None}, {}, ENV)


def test_wire_formats():
    assert float_to_wire(0.0012) == "0.0012" and float_to_wire(100.0) == "100" and float_to_wire(1.5e-5) == "0.000015"
    assert round_px(82665.432, 5) == 82665.0 and round_px(123456.7, 5) == 123457.0
    assert round_px(0.0053621, 0) == 0.005362 and round_px(109.6851, 2) == 109.69


def test_signature_recovers_the_agent_address():
    ex = HyperliquidExchange(KEY, network="testnet", clock=lambda: NOW)
    action = {"type": "order", "orders": [{"a": 0, "b": True, "p": "110", "s": "0.1", "r": False, "t": {"limit": {"tif": "Ioc"}}}], "grouping": "na"}
    sig = ex.sign(action, 123)
    h = keccak(msgpack.packb(action) + (123).to_bytes(8, "big") + b"\x00")
    msg = encode_typed_data(full_message=l1_typed_data(h, False))
    assert Account.recover_message(msg, vrs=(sig["v"], sig["r"], sig["s"])) == Account.from_key(KEY).address
    assert ex.nonce() < ex.nonce()  # strictly increasing within one millisecond


class FakeInfo:
    def __init__(self):
        self.calls = []

    def post(self, body):
        self.calls.append(body)
        if body["type"] == "meta":
            return {"universe": [{"name": "BTC", "szDecimals": 5}, {"name": "SOL", "szDecimals": 2}]}
        if body["type"] == "userFills":
            return [{"oid": 7, "fee": "0.0049"}]
        raise AssertionError(body)

    def book(self, coin):
        return [{"px": "109.99", "sz": "100"}], [{"px": "110.01", "sz": "100"}]

    def sz_decimals(self, coin):
        return 2

    def funding_rate_sum(self, coin, t0, t1):
        return 0.0


class FakeExchange:
    url, network = "https://api.hyperliquid-testnet.xyz", "testnet"

    def __init__(self, resp):
        self.resp, self.sent = resp, []

    def ioc(self, asset, is_buy, px, sz, reduce_only):
        self.sent.append((asset, is_buy, px, sz, reduce_only))
        return self.resp


FILLED = {"status": "ok", "response": {"type": "order", "data": {"statuses": [{"filled": {"totalSz": "0.10", "avgPx": "109.98", "oid": 7}}]}}}


def test_open_short_and_reduce_only_close():
    ex = FakeExchange(FILLED)
    lx = LivePerpExecutor(ex, ACCOUNT, info=FakeInfo(), clock=lambda: NOW)
    f = lx.open("SOL", -1, 12.0)
    assert ex.sent[0] == (1, False, 108.9, 0.1, False)  # 1% through the mid, size floored to 0.01
    assert f.ok and f.px == 109.98 and f.sz == 0.1 and f.fee_usd == pytest.approx(0.0049) and not f.dry
    c = lx.close("SOL", -1, 0.1)
    assert ex.sent[1] == (1, True, 111.1, 0.1, True) and c.ok


def test_errors_and_minimum_are_failed_legs():
    err = {"status": "ok", "response": {"type": "order", "data": {"statuses": [{"error": "Insufficient margin to place order."}]}}}
    lx = LivePerpExecutor(FakeExchange(err), ACCOUNT, info=FakeInfo(), clock=lambda: NOW)
    f = lx.open("SOL", 1, 12.0)
    assert not f.ok and "Insufficient margin" in f.error
    ex = FakeExchange(FILLED)
    small = LivePerpExecutor(ex, ACCOUNT, info=FakeInfo(), clock=lambda: NOW).open("SOL", 1, 8.0)
    assert not small.ok and "minimum" in small.error and not ex.sent
    top = LivePerpExecutor(FakeExchange({"status": "err", "response": "User or API Wallet 0x1 does not exist."}), ACCOUNT, info=FakeInfo())
    assert "does not exist" in top.open("SOL", 1, 12.0).error


def test_guard_stops_opens_under_kill_switch_but_closes_still_flatten(tmp_path):
    ex = FakeExchange(FILLED)
    guard = lambda leg: gate.require_live(CFG, ENV, ("HYPERLIQUID_AGENT_KEY",), tmp_path if leg == "open" else None)  # noqa: E731
    lx = LivePerpExecutor(ex, ACCOUNT, info=FakeInfo(), guard=guard, clock=lambda: NOW)
    (tmp_path / "HALT_LIVE").write_text("stop")
    assert "kill switch" in lx.open("SOL", 1, 12.0).error and not ex.sent
    assert lx.close("SOL", 1, 0.1).ok and ex.sent[0][4] is True


def intent(meta):
    return Intent("open", "s", NOW - 60, 110.0, "t", asset="SOL", side=-1, notional_usd=200.0, cost=CostModel(fee=0.001),
                  meta={"venue": "hyperliquid", "key": "SOL", **meta})


def test_broker_uses_the_live_route_and_keeps_basket_hedges_on_paper(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text(json.dumps(CFG))
    led = Ledger(tmp_path)
    led.strategy("s")["status"] = "promoted"
    lx = LivePerpExecutor(FakeExchange(FILLED), ACCOUNT, info=FakeInfo(), clock=lambda: NOW)
    monkeypatch.setattr(broker_mod, "make_perp_executor", lambda *a, **k: lx)
    b = LiveBroker(CFG, ledger=led, root=tmp_path, env=ENV, now=NOW)  # no Solana key: perps alone are enough
    assert b.route is None and b.perp_route == "live" and b.mode == "live"
    pos, row = b.open(intent({}))
    assert pos.meta["live"]["route"] == "live" and not pos.meta["live"]["dry"] and pos.mode == "live"
    pos2, row2 = b.open(intent({"basket": "jlp", "twin_usd": 50}))
    assert "basket leg" in row2["live"]["skipped"]
    sol = Intent("open", "s", NOW - 60, 1.0, "t", asset="X", side=1, notional_usd=100.0, meta={"mint": "M"})
    _, row3 = b.open(sol)
    assert "no Solana route key" in row3["live"]["skipped"]
