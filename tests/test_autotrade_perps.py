"""Hyperliquid perp twins (tartar/autotrade/perps.py + LiveBroker), offline with a fake order book."""

import json

import pytest

from tartar.autotrade import broker as broker_mod
from tartar.autotrade.broker import LiveBroker, preflight
from tartar.autotrade.core import CostModel, Intent, Verdict
from tartar.autotrade.ledger import Ledger
from tartar.autotrade.perps import DryPerpExecutor, select_perp_route, walk
from tartar.autotrade.runner import run_once

NOW = 100_000.0


class FakeInfo:
    """A book around ``mid`` with 10 bps spread, 1,000 units per level; funding ``rate`` per call."""

    def __init__(self, mid=2.0, rate=0.0):
        self.mid, self.rate = mid, rate

    def book(self, coin):
        bids = [{"px": str(self.mid * (1 - 0.0005 - i * 0.001)), "sz": "1000"} for i in range(5)]
        asks = [{"px": str(self.mid * (1 + 0.0005 + i * 0.001)), "sz": "1000"} for i in range(5)]
        return bids, asks

    def sz_decimals(self, coin):
        return 1

    def funding_rate_sum(self, coin, t0, t1):
        return self.rate


class Strat:
    def __init__(self, script, name="s"):
        self.name, self.prereg, self.script = name, "test", list(script)

    def step(self, ctx):
        return self.script.pop(0) if self.script else []

    def marks(self, ctx):
        return {}

    def evaluate(self, trades, now, state):
        return Verdict("pending", len(trades), {}, "test")


def opener(coin="PUMP", side=-1, at=NOW - 60, price=2.0, key=None):
    return Intent("open", "s", at, price, "test", asset=coin, side=side, notional_usd=200.0, cost=CostModel(fee=0.002),
                  meta={"venue": "hyperliquid", "key": key or coin})


def closer(coin="PUMP", price=2.0, at=NOW, kept=False):
    return Intent("close", "s", at, price, "weekly rebalance" + (" (kept)" if kept else ""),
                  cost=CostModel(fee=0.0 if kept else 0.002), meta={"key": coin, "kept": kept})


@pytest.fixture
def info(monkeypatch):
    inf = FakeInfo()
    monkeypatch.setattr(broker_mod, "make_perp_executor", lambda route, cfg, env=None, *a: DryPerpExecutor(inf, clock=lambda: NOW))
    monkeypatch.setattr(broker_mod, "make_executor", lambda route, cfg, env=None: None)
    monkeypatch.delenv("TARTAR_LIVE_KILL", raising=False)
    return inf


def setup(tmp_path, mode="dry_live", status="paper", perps=None):
    (tmp_path / "config.json").write_text(json.dumps({"mode": mode, "strategies": {}, "live": {"perps": perps or {}}}))
    led = Ledger(tmp_path)
    led.strategy("s")["status"] = status
    led.save()
    return tmp_path


def run(root, script, now=NOW):
    return run_once(root, now=now, strategies={"s": Strat(script)})


def fills(root):
    p = root / "fills.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_walk_takes_levels_in_order():
    lv = [{"px": "1.0", "sz": "2"}, {"px": "2.0", "sz": "2"}]
    assert walk(lv, sz=3) == pytest.approx((4 / 3, 3))
    assert walk(lv, usd=4.0) == pytest.approx((4 / 3, 3))
    with pytest.raises(ValueError):
        walk(lv, sz=5)


def test_route_is_dry_only():
    assert select_perp_route("dry_live") == "dry"
    assert select_perp_route("live") is None and select_perp_route("paper") is None


def test_dry_twin_opens_on_the_book_and_compares_at_close(tmp_path, info):
    root = setup(tmp_path)  # paper status: dry_all mirrors it anyway
    run(root, [[opener()]])
    (pos,) = Ledger(root).positions
    tw = pos.meta["live"]
    assert tw["venue"] == "hyperliquid" and tw["side"] == -1 and tw["dry"]
    assert tw["px_in"] == pytest.approx(2.0 * 0.9995)  # sold into the bid
    assert 10 <= tw["notional_in"] <= 12
    info.mid, info.rate = 1.9, 0.001  # price fell 5%, shorts receive 0.1% funding
    run(root, [[closer(price=1.9)]], now=NOW + 10)
    (trade,) = Ledger(root).trades()
    cmp = trade.meta["live"]
    expect = (tw["sz"] * (tw["px_in"] - 1.9 * 1.0005) - tw["fee_in"] - tw["sz"] * 1.9 * 1.0005 * 0.00045
              + tw["notional_in"] * 0.001) / tw["notional_in"]
    assert cmp["live_net_return_usd"] == pytest.approx(expect)
    assert cmp["paper_net_return"] == pytest.approx(0.05 - 0.004)
    assert [r["event"] for r in fills(root)] == ["perp_open", "perp_close"]
    assert "Perp twins closed" in (root / "REPORT.md").read_text()


def test_kept_leg_rolls_without_trading(tmp_path, info):
    root = setup(tmp_path)
    run(root, [[opener()]])
    info.mid = 1.8
    run(root, [[closer(price=1.8, kept=True), opener(price=1.8, at=NOW)]], now=NOW + 10)
    led = Ledger(root)
    (pos,) = led.positions
    assert pos.meta["live"]["px_in"] == pytest.approx(1.8) and pos.meta["live"]["fee_in"] == 0.0
    assert [r["event"] for r in fills(root)] == ["perp_open", "perp_roll_out", "perp_roll_in"]
    assert not led.state["live"]["perp_handover"]


def test_budget_minimum_and_kill_switch(tmp_path, info):
    root = setup(tmp_path, perps={"budget_usd": 20, "max_leg_usd": 12})
    run(root, [[opener("A", key="A"), opener("B", key="B")]])
    led = Ledger(root)
    assert sum(1 for p in led.positions if p.meta.get("live")) == 1
    assert any("< min $10" in r.get("reason", "") for r in fills(root))
    (root / "HALT_LIVE").write_text("stop")
    run(root, [[opener("C", key="C")]], now=NOW + 1)
    assert fills(root)[-1]["reason"].startswith("live kill switch")


def test_promoted_only_when_dry_all_is_off(tmp_path, info):
    root = setup(tmp_path, perps={"dry_all": False})
    run(root, [[opener()]])
    assert not Ledger(root).positions[0].meta.get("live")


def test_live_mode_without_hyperliquid_keys_has_no_perp_route(tmp_path, info, monkeypatch):
    root = setup(tmp_path, mode="live", status="promoted")
    cfg = {"mode": "live", "live_approved_on": "2026-10-10", "live": {}, "us_only": False}
    monkeypatch.setattr(broker_mod, "select_route", lambda cfg, env=None: "jupiter")
    b = LiveBroker(cfg, ledger=Ledger(root), root=root, env={"TARTAR_LIVE_APPROVED": "2026-10-10"}, now=NOW)
    pos, row = b.open(opener())
    assert "HYPERLIQUID_AGENT_KEY" in row["live"]["skipped"]
    pf = preflight(cfg, Ledger(root), root, env={})
    assert pf["perps"]["route"] is None and pf["perps"]["keys"] == {"HYPERLIQUID_AGENT_KEY": False, "HYPERLIQUID_ACCOUNT": False}


def book_leg(coin, side, usd=50.0, week="2026-10-12"):
    return Intent("open", "s", NOW - 60, 2.0, "test", asset=coin, side=side, notional_usd=usd, cost=CostModel(fee=0.002),
                  meta={"venue": "hyperliquid", "key": coin, "week": week, "leg_usd": 100.0, "label": coin})


def test_book_week_twins_are_sized_from_paper_and_dollar_neutral(tmp_path, info):
    root = setup(tmp_path)
    run(root, [[book_leg("A", 1), book_leg("B", 1), book_leg("C", -1), book_leg("D", -1)]])
    tw = [p.meta["live"] for p in Ledger(root).positions]
    assert len(tw) == 4
    long_usd = sum(t["notional_in"] for t in tw if t["side"] > 0)
    short_usd = sum(t["notional_in"] for t in tw if t["side"] < 0)
    assert long_usd == pytest.approx(50.0, rel=0.05) and short_usd == pytest.approx(50.0, rel=0.05)  # 0.5 x $50 per leg


def test_book_week_below_the_venue_minimum_stays_on_paper_whole(tmp_path, info):
    root = setup(tmp_path)
    run(root, [[book_leg("A", 1, usd=50), book_leg("B", 1, usd=15), book_leg("C", -1, usd=65)]])  # B: $7.50 twin
    assert not any(p.meta.get("live") for p in Ledger(root).positions)
    (skip,) = [r for r in fills(root) if r["event"] == "book_skip"]
    assert "all or nothing" in skip["reason"] and "B twin" in skip["reason"]


def test_unbalanced_or_over_budget_book_stays_on_paper(tmp_path, info):
    root = setup(tmp_path)
    run(root, [[book_leg("A", 1), book_leg("B", 1), book_leg("C", -1)]])  # $50 long vs $25 short
    assert not any(p.meta.get("live") for p in Ledger(root).positions)
    (tmp_path / "b").mkdir()
    root2 = setup(tmp_path / "b", perps={"book_budget_usd": 60})
    run(root2, [[book_leg("A", 1, usd=80), book_leg("C", -1, usd=80)]])
    assert "budget" in [r for r in fills(root2) if r["event"] == "book_skip"][0]["reason"]


def test_failed_book_leg_unwinds_the_weeks_other_twins(tmp_path, info):
    real = info.book
    info.book = lambda coin: (_ for _ in ()).throw(RuntimeError("no book")) if coin == "C" else real(coin)
    root = setup(tmp_path)
    run(root, [[book_leg("A", 1), book_leg("B", -1), book_leg("C", -1), book_leg("D", 1)]])
    assert not any(p.meta.get("live") for p in Ledger(root).positions)  # A and B unwound, D never sent
    ev = [r["event"] for r in fills(root)]
    assert ev.count("book_unwind") == 2 and ev.count("perp_open") == 3
    assert not Ledger(root).state["live"]["orphans"]


def test_us_only_blocks_hyperliquid_and_jupiter_in_live_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(broker_mod, "make_executor", lambda route, cfg, env=None: None)
    monkeypatch.setattr(broker_mod, "approval_reason", lambda config, env: None)
    monkeypatch.setattr(broker_mod, "select_perp_route", lambda mode, env=None, config=None: "live")
    env = {"HYPERLIQUID_AGENT_KEY": "k", "HYPERLIQUID_ACCOUNT": "a", "TARTAR_WALLET_KEY": "w", "PUMPPORTAL_API_KEY": "p"}
    b = LiveBroker({"mode": "live", "strategies": {}}, root=tmp_path, env=env)
    assert b.perp_route is None and b.route == "lightning" and b.usd_route is None
    assert b.us_blocked == ["Hyperliquid", "Jupiter"]
    b = LiveBroker({"mode": "live", "strategies": {}, "us_only": False}, root=tmp_path, env=env)
    assert b.perp_route == "live" and b.route == "jupiter"
