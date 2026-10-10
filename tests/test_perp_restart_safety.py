"""Restart safety for Hyperliquid perp twins (safety.reconcile_perps + client order ids), in dry run: a run
is killed mid-order and the next run must neither lose the leg nor trade it twice, and any difference
between the account and the book stops perp entries. The dry perp route simulates the account on disk
(dry_perp_account.json)."""

import json

import pytest

from tartar.autotrade import broker as broker_mod
from tartar.autotrade.hl_exchange import LivePerpExecutor
from tartar.autotrade.ledger import Ledger
from tartar.autotrade.perps import DryPerpExecutor, cloid
from tartar.autotrade.runner import run_once

from test_autotrade_perps import NOW, FakeInfo, Strat, closer, opener, setup


class Killed(BaseException):
    """Stands in for SIGKILL / a lost runner."""


class KillableDryPerp(DryPerpExecutor):
    kill = None  # ("open" | "close", "before" | "after"), shared by every instance a run makes
    sent: list = []

    def open(self, coin, side, usd, cloid=None):
        return self._leg("open", lambda: super(KillableDryPerp, self).open(coin, side, usd, cloid=cloid), cloid)

    def close(self, coin, side, sz, cloid=None):
        return self._leg("close", lambda: super(KillableDryPerp, self).close(coin, side, sz, cloid=cloid), cloid)

    def _leg(self, leg, do, oid):
        if KillableDryPerp.kill == (leg, "before"):
            raise Killed
        f = do()
        KillableDryPerp.sent.append((leg, oid))
        if KillableDryPerp.kill == (leg, "after"):
            raise Killed
        return f


@pytest.fixture
def perp(monkeypatch):
    inf = FakeInfo()
    KillableDryPerp.kill, KillableDryPerp.sent = None, []
    monkeypatch.setattr(broker_mod, "make_perp_executor", lambda route, cfg, env=None, *a: KillableDryPerp(inf, clock=lambda: NOW))
    monkeypatch.setattr(broker_mod, "make_executor", lambda route, cfg, env=None: None)
    for k in ("TARTAR_LIVE_KILL", "GITHUB_RUN_ID"):
        monkeypatch.delenv(k, raising=False)
    return KillableDryPerp


def go(root, script, now):
    return run_once(root, now=now, strategies={"s": Strat(script)})


def account(root):
    return json.loads((root / "dry_perp_account.json").read_text())


def live(root):
    return json.loads((root / "state.json").read_text())["live"]


def twins(root):
    return [p.meta["live"] for p in Ledger(root).positions if p.meta.get("live")]


def test_killed_after_the_open_filled_next_run_adopts_it_and_does_not_trade_again(tmp_path, perp):
    root = setup(tmp_path)
    perp.kill = ("open", "after")
    with pytest.raises(Killed):
        go(root, [[opener()]], NOW)
    assert account(root)["positions"] == {"PUMP": -6.0} and len(perp.sent) == 1
    assert not Ledger(root).positions  # the book never saw it
    perp.kill = None
    s = go(root, [[opener()]], NOW + 300)  # re-emitted: same client order id
    assert len(perp.sent) == 1, "traded twice"
    (t,) = twins(root)
    assert t["sz"] == 6.0 and t["side"] == -1
    assert s["perp_reconcile"]["inflight"] == 1 and not s["new_halts"] and not live(root).get("perps_halted")
    assert not live(root)["perp_inflight"]
    rows = [json.loads(x) for x in (root / "fills.jsonl").read_text().splitlines()]
    assert rows[-1]["event"] == "perp_open_adopted"
    go(root, [[closer()]], NOW + 600)  # and exits normally
    assert account(root)["positions"] == {} and len(perp.sent) == 2


def test_killed_before_the_open_was_sent_next_run_opens_once(tmp_path, perp):
    root = setup(tmp_path)
    perp.kill = ("open", "before")
    with pytest.raises(Killed):
        go(root, [[opener()]], NOW)
    perp.kill = None
    s = go(root, [[opener()]], NOW + 300)
    assert len(perp.sent) == 1 and account(root)["positions"] == {"PUMP": -6.0}
    assert "perp_reconcile" not in s and not s["new_halts"]


def test_killed_after_the_close_filled_next_run_does_not_close_again(tmp_path, perp):
    root = setup(tmp_path)
    go(root, [[opener()]], NOW)
    perp.kill = ("close", "after")
    with pytest.raises(Killed):
        go(root, [[closer()]], NOW + 300)
    assert account(root)["positions"] == {}
    perp.kill = None
    s = go(root, [[closer()]], NOW + 600)
    assert [leg for leg, _ in perp.sent] == ["open", "close"], "closed twice"
    assert not s["new_halts"] and not Ledger(root).positions
    (trade,) = Ledger(root).trades()
    assert trade.meta["live"]["px_out"] > 0


def test_a_position_the_book_does_not_know_stops_perp_entries(tmp_path, perp):
    """A runner lost before it committed, or a hand trade: the account holds what no leg explains."""
    root = setup(tmp_path)
    go(root, [[opener()]], NOW)
    a = account(root)
    a["positions"]["ETH"] = 0.5
    (root / "dry_perp_account.json").write_text(json.dumps(a))
    s = go(root, [[opener("SOL", key="SOL")]], NOW + 300)
    assert s["perp_reconcile"]["mismatch"] == 1 and s["new_halts"]
    assert "ETH account 0.5 vs book 0" in live(root)["perps_halted"]
    assert len(perp.sent) == 1  # SOL was not opened
    go(root, [[closer()]], NOW + 600)  # closes still run (reduce-only)
    assert [leg for leg, _ in perp.sent] == ["open", "close"]


def test_an_unread_account_stops_perp_entries_not_paper(tmp_path, perp, monkeypatch):
    root = setup(tmp_path)
    monkeypatch.setattr(KillableDryPerp, "account", lambda self: (_ for _ in ()).throw(RuntimeError("api down")))
    s = go(root, [[opener()]], NOW)
    assert "perp reconcile failed" in live(root)["perps_halted"] and s["new_halts"]
    assert len(Ledger(root).positions) == 1 and not perp.sent


def test_a_fill_never_readopted_becomes_an_orphan(tmp_path, perp):
    root = setup(tmp_path)
    perp.kill = ("open", "after")
    with pytest.raises(Killed):
        go(root, [[opener()]], NOW)
    perp.kill = None
    go(root, [[]], NOW + 300)
    assert live(root)["perp_inflight"] and not live(root).get("perps_halted")
    s = go(root, [[]], NOW + 300 + 3601)
    assert not live(root)["perp_inflight"] and live(root)["orphans"][0]["coin"] == "PUMP" and s["new_halts"]
    s = go(root, [[]], NOW + 300 + 3602)  # the orphan is now counted as held: no further mismatch
    assert "perp_reconcile" not in s


def test_existing_dry_twins_seed_the_simulated_account(tmp_path, perp):
    root = setup(tmp_path)
    go(root, [[opener()]], NOW)
    (root / "dry_perp_account.json").unlink()  # as on main before this change: twins, no account file
    s = go(root, [[]], NOW + 300)
    assert account(root)["positions"] == {"PUMP": -6.0} and "perp_reconcile" not in s


def test_resume_live_perps_clears_the_perp_halt(tmp_path, perp):
    from tartar.autotrade.__main__ import main

    root = setup(tmp_path)
    led = Ledger(root)
    led.state.setdefault("live", {})["perps_halted"] = "x"
    led.save()
    main(["resume-live", "perps", "--root", str(root)])
    assert live(root)["perps_halted"] is None


# the live executor: client order ids on the wire, order lookup, account read

class HLInfo(FakeInfo):
    def __init__(self, status=None):
        super().__init__(mid=110.0)
        self.status, self.asked = status, []

    def post(self, body):
        self.asked.append(body)
        t = body["type"]
        if t == "meta":
            return {"universe": [{"name": "SOL", "szDecimals": 2}]}
        if t == "orderStatus":
            return self.status or {"status": "unknownOid"}
        if t == "userFills":
            return [{"oid": 7, "px": "109.9", "sz": "0.1", "fee": "0.005"}]
        if t == "clearinghouseState":
            return {"assetPositions": [{"position": {"coin": "SOL", "szi": "-0.1"}}, {"position": {"coin": "ETH", "szi": "0.0"}}]}
        if t == "openOrders":
            return []
        raise AssertionError(t)


class HLExchange:
    url, network = "https://api.hyperliquid-testnet.xyz", "testnet"

    def __init__(self):
        self.sent = []

    def ioc(self, asset, is_buy, px, sz, reduce_only, cloid=None):
        self.sent.append(cloid)
        return {"status": "ok", "response": {"data": {"statuses": [{"filled": {"totalSz": "0.1", "avgPx": "109.9", "oid": 7}}]}}}


def test_live_orders_carry_the_client_order_id_and_a_retry_finds_the_fill():
    ex = HLExchange()
    lx = LivePerpExecutor(ex, "0xacct", info=HLInfo(), clock=lambda: NOW)
    oid = cloid("perp_open|s|SOL|SOL|-1|99940")
    assert oid == cloid("perp_open|s|SOL|SOL|-1|99940") and len(oid) == 34
    assert lx.open("SOL", -1, 11.0, cloid=oid).ok and ex.sent == [oid]
    assert lx.find(oid) is None  # venue says unknown
    filled = {"status": "order", "order": {"status": "filled", "order": {"coin": "SOL", "side": "A", "origSz": "0.1", "sz": "0.0",
                                                                         "oid": 7, "cloid": oid}}}
    lx = LivePerpExecutor(ex, "0xacct", info=HLInfo(filled), clock=lambda: NOW)
    f = lx.find(oid)
    assert f.ok and f.side == -1 and f.sz == pytest.approx(0.1) and f.px == pytest.approx(109.9) and f.fee_usd == pytest.approx(0.005)
    missed = {"status": "order", "order": {"status": "canceled", "order": {"coin": "SOL", "side": "A", "origSz": "0.1", "sz": "0.1", "oid": 8}}}
    assert LivePerpExecutor(ex, "0xacct", info=HLInfo(missed)).find(oid) is None  # an IOC that missed: safe to resend
    assert lx.account() == {"positions": {"SOL": -0.1}, "open_orders": []}


def test_the_cloid_is_signed_into_the_order_wire():
    pytest.importorskip("eth_account")
    pytest.importorskip("msgpack")
    from tartar.autotrade.hl_exchange import HyperliquidExchange

    class H:
        def __init__(self):
            self.body = None

        def post(self, url, json):
            self.body = json

            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"status": "ok"}

            return R()

    h = H()
    ex = HyperliquidExchange("0x" + "11" * 32, network="testnet", http=h, clock=lambda: NOW)
    ex.ioc(0, True, 110.0, 0.1, False, cloid="0x" + "ab" * 16)
    order = h.body["action"]["orders"][0]
    assert list(order) == ["a", "b", "p", "s", "r", "t", "c"] and order["c"] == "0x" + "ab" * 16
