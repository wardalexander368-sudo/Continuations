"""The live path of tartar/autotrade, offline: route choice, live twins, limits, kill switches, fill log."""

import json

import pytest

from tartar.autotrade import broker as broker_mod
from tartar.autotrade.broker import LiveBroker, preflight
from tartar.autotrade.core import CostModel, Intent, Verdict
from tartar.autotrade.execution import Fill, select_route
from tartar.autotrade.ledger import Ledger
from tartar.autotrade.runner import run_once

NOW = 100_000.0


class FakeExec:
    """Buys 1000 raw tokens per 0.01 SOL; sells return ``sell_ratio`` of the SOL put in."""

    name = "fake"

    def __init__(self, balance=0.05, sell_ratio=1.0, fail_sell=False):
        self.balance, self.sell_ratio, self.fail_sell = balance, sell_ratio, fail_sell
        self.buys, self.sells, self.wallet = [], [], "W"

    def balance_sol(self):
        return self.balance

    def sol_usd(self):
        return 100.0

    def buy(self, mint, sol):
        self.buys.append((mint, sol))
        self.balance -= sol
        return Fill(self.name, "buy", mint, True, sol=sol, token_raw=int(sol * 1e5), quote_out=int(sol * 1e5))

    def sell(self, mint, raw):
        self.sells.append((mint, raw))
        if self.fail_sell:
            return Fill(self.name, "sell", mint, False, error="boom")
        sol = raw / 1e5 * self.sell_ratio
        self.balance += sol
        return Fill(self.name, "sell", mint, True, sol=sol, token_raw=raw, quote_out=int(sol * 1e9))


class Strat:
    def __init__(self, script, name="s"):
        self.name, self.prereg, self.script = name, "test", list(script)

    def step(self, ctx):
        return self.script.pop(0) if self.script else []

    def marks(self, ctx):
        return {}

    def evaluate(self, trades, now, state):
        return Verdict("pending", len(trades), {}, "test")


def opener(key="a", mint="M1", at=NOW - 60, name="s", **meta):
    return Intent("open", name, at, 1.0, "test", asset=mint, notional_usd=100.0, cost=CostModel(fee=0.01),
                  meta={"key": key, "mint": mint, **meta})


def closer(key="a", price=1.0, at=NOW, name="s"):
    return Intent("close", name, at, price, "test", cost=CostModel(fee=0.01), meta={"key": key})


@pytest.fixture
def fake(monkeypatch):
    ex = FakeExec()
    monkeypatch.setattr(broker_mod, "make_executor", lambda route, cfg, env=None: ex)
    for k in ("TARTAR_WALLET_KEY", "PUMPPORTAL_API_KEY", "TARTAR_LIVE_APPROVED", "TARTAR_LIVE_KILL"):
        monkeypatch.delenv(k, raising=False)
    return ex


def setup(tmp_path, mode="dry_live", status="promoted", live=None, **cfg):
    (tmp_path / "config.json").write_text(json.dumps({"mode": mode, "strategies": {}, "live": live or {}, **cfg}))
    led = Ledger(tmp_path)
    led.strategy("s")["status"] = status
    led.save()
    return tmp_path


def run(root, script, now=NOW, name="s"):
    return run_once(root, now=now, strategies={name: Strat(script, name)})


def fills(root):
    p = root / "fills.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_route_prefers_jupiter_then_lightning():
    assert select_route({}, {"TARTAR_WALLET_KEY": "k", "PUMPPORTAL_API_KEY": "p"}) == "jupiter"
    assert select_route({}, {"PUMPPORTAL_API_KEY": "p"}) == "lightning"
    assert select_route({"route": "lightning"}, {"TARTAR_WALLET_KEY": "k"}) is None
    assert select_route({}, {}) is None
    assert select_route({"route": "dry"}, {}) == "dry"


def test_promoted_strategy_gets_a_twin_and_its_fill_is_compared(tmp_path, fake):
    root = setup(tmp_path)
    run(root, [[opener()]])
    (pos,) = Ledger(root).positions
    assert pos.meta["live"]["sol_in"] == pytest.approx(0.01) and pos.mode == "dry_live"
    fake.sell_ratio = 0.98
    run(root, [[closer(price=1.05)]], now=NOW + 10)
    (trade,) = Ledger(root).trades()
    cmp = trade.meta["live"]
    assert cmp["live_net_return_sol"] == pytest.approx(-0.02)
    assert cmp["paper_net_return"] == pytest.approx(0.05 - 0.02)
    assert cmp["live_minus_paper"] == pytest.approx(-0.02 - 0.03)
    assert [r["event"] for r in fills(root)] == ["buy", "sell"]
    assert "## Live twins" in (root / "REPORT.md").read_text()


def test_paper_status_and_shadows_get_no_twin(tmp_path, fake):
    root = setup(tmp_path, status="paper")
    run(root, [[opener(), opener("b", "M2", shadow=True)]])
    assert not fake.buys and len(Ledger(root).positions) == 2


def test_live_mode_needs_matching_approval_and_a_key(tmp_path, fake, monkeypatch):
    root = setup(tmp_path, mode="live", live_approved_on="2026-10-10")
    run(root, [[opener()]])
    assert not fake.buys and "live_refused" in (root / "journal.jsonl").read_text()
    monkeypatch.setenv("TARTAR_LIVE_APPROVED", "2026-10-10")
    run(root, [[opener("b", "M2")]], now=NOW + 1)
    assert not fake.buys  # still no route key
    monkeypatch.setenv("PUMPPORTAL_API_KEY", "x")  # Jupiter is off under us_only
    run(root, [[opener("c", "M3")]], now=NOW + 2)
    assert fake.buys == [("M3", 0.01)]
    assert [p.mode for p in Ledger(root).positions] == ["paper", "paper", "live"]


def test_sizing_respects_budget_reserve_and_min(tmp_path, fake):
    root = setup(tmp_path, live={"budget_sol": 0.025, "max_trade_sol": 0.01})
    run(root, [[opener("a", "M1"), opener("b", "M2"), opener("c", "M3")]])
    assert [s for _, s in fake.buys] == pytest.approx([0.01, 0.01, 0.005])  # the third gets what the budget leaves
    run(root, [[opener("d", "M4")]], now=NOW + 1)  # budget used up
    assert len(fake.buys) == 3 and "< min" in fills(root)[-1]["reason"]


def test_low_wallet_balance_skips(tmp_path, fake):
    root = setup(tmp_path)
    fake.balance = 0.011  # 0.001 free after the 0.01 reserve
    run(root, [[opener()]])
    assert not fake.buys and "free 0.0010" in fills(root)[-1]["reason"]


def test_one_twin_per_mint_and_stale_or_mintless_signals_skip(tmp_path, fake):
    root = setup(tmp_path)
    run(root, [[opener("a", "M1"), opener("b", "M1"), opener("c", "M2", at=NOW - 5000)]])
    i = Intent("open", "s", NOW, 1.0, "perp", asset="BTC", notional_usd=100.0, meta={"key": "d"})
    run(root, [[i]], now=NOW + 1)
    assert fake.buys == [("M1", 0.01)]
    reasons = [r["reason"] for r in fills(root) if r["event"] == "skip"]
    assert any("already holds" in r for r in reasons) and any("old" in r for r in reasons) and any("mint" in r for r in reasons)


def test_halt_live_stops_entries_but_exits_still_sell(tmp_path, fake):
    root = setup(tmp_path)
    run(root, [[opener()]])
    (root / "HALT_LIVE").write_text("test")
    run(root, [[opener("b", "M2"), closer()]], now=NOW + 1)
    assert fake.buys == [("M1", 0.01)] and len(fake.sells) == 1
    assert len(Ledger(root).positions) == 1  # paper keeps trading


def test_env_kill_switch(tmp_path, fake, monkeypatch):
    root = setup(tmp_path)
    monkeypatch.setenv("TARTAR_LIVE_KILL", "1")
    run(root, [[opener()]])
    assert not fake.buys


def test_big_live_loss_halts_the_strategy_live(tmp_path, fake):
    root = setup(tmp_path, live={"daily_loss_cap_sol": 1.0})
    run(root, [[opener()]])
    fake.sell_ratio = 0.6
    run(root, [[closer(), opener("b", "M2", at=NOW + 1)]], now=NOW + 1)
    st = Ledger(root).state["live"]
    assert st["strategies"]["s"]["halted"] and len(fake.buys) == 1


def test_daily_live_loss_cap_halts_all_live_entries(tmp_path, fake):
    root = setup(tmp_path, live={"daily_loss_cap_sol": 0.001})
    run(root, [[opener()]])
    fake.sell_ratio = 0.85
    run(root, [[closer()]], now=NOW + 1)
    assert "live daily loss" in Ledger(root).state["live"]["halted"]


def test_fills_worse_than_paper_three_times_halt(tmp_path, fake):
    root = setup(tmp_path, live={"daily_loss_cap_sol": 1.0})
    fake.sell_ratio = 0.94  # live -6% against paper -2% (fees): 4 points worse each time
    for k in range(3):
        run(root, [[opener(str(k), f"M{k}", at=NOW + 10 * k - 1)]], now=NOW + 10 * k)
        run(root, [[closer(str(k), at=NOW + 10 * k + 5)]], now=NOW + 10 * k + 5)
    assert "worse than paper" in (Ledger(root).state["live"]["strategies"]["s"]["halted"] or "")


def test_failed_sell_keeps_an_orphan_and_halts(tmp_path, fake):
    root = setup(tmp_path)
    run(root, [[opener()]])
    fake.fail_sell = True
    run(root, [[closer()]], now=NOW + 1)
    st = Ledger(root).state["live"]
    assert st["orphans"][0]["mint"] == "M1" and st["strategies"]["s"]["halted"]


def test_demoted_strategy_twin_still_exits_live(tmp_path, fake):
    root = setup(tmp_path)
    run(root, [[opener()]])
    led = Ledger(root)
    led.strategy("s")["status"] = "demoted"
    led.save()
    run(root, [[closer()]], now=NOW + 1)
    assert len(fake.sells) == 1


def test_exit_with_no_live_route_records_an_orphan(tmp_path, fake):
    root = setup(tmp_path)
    run(root, [[opener()]])
    cfg = json.loads((root / "config.json").read_text())
    cfg["mode"] = "paper"
    (root / "config.json").write_text(json.dumps(cfg))
    run(root, [[closer()]], now=NOW + 1)
    assert not fake.sells and Ledger(root).state["live"]["orphans"][0]["mint"] == "M1"


def test_preflight(tmp_path, fake, monkeypatch):
    root = setup(tmp_path, mode="live", live_approved_on="2026-10-10")
    out = preflight(json.loads((root / "config.json").read_text()), Ledger(root), root)
    assert not out["ready"] and any("approved" in p or "match" in p for p in out["problems"])
    monkeypatch.setenv("TARTAR_LIVE_APPROVED", "2026-10-10")
    monkeypatch.setenv("TARTAR_WALLET_KEY", "x")
    out = preflight(json.loads((root / "config.json").read_text()), Ledger(root), root)
    assert out["ready"] and out["route"] == "jupiter" and out["balance_sol"] == pytest.approx(0.05)


def test_live_broker_refuses_paper_mode():
    with pytest.raises(broker_mod.LiveNotAllowed):
        LiveBroker({"mode": "paper"})


def test_dry_executor_charges_the_network_fee():
    from tartar.autotrade.execution import DryExecutor

    class Q:
        def quote(self, i, o, amount):
            return {"outAmount": str(amount * 2 if o != "So11111111111111111111111111111111111111112" else amount // 2)}

    ex = DryExecutor(quotes=Q(), balance_sol=0.05, priority_sol=0.00002)
    b = ex.buy("M", 0.01)
    s = ex.sell("M", b.token_raw)
    assert b.token_raw == 2 * 10**7 and b.sol == pytest.approx(0.010025)
    assert s.sol == pytest.approx(0.01 - 0.000025) and ex.balance_sol() == pytest.approx(0.05 - 0.00005)
