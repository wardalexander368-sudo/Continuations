import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from tartar.autotrade import lifecycle
from tartar.autotrade.core import CostModel, Intent, Trade, Verdict
from tartar.autotrade.ledger import Ledger
from tartar.autotrade.runner import run_once
from tartar.autotrade.strategies.dip import DipStrategy
from tartar.autotrade.strategies.xs_momentum import XSMomentum, close_ts


class Fake:
    """A strategy driven by a script of intents per run."""

    def __init__(self, name="fake", script=None, verdict=None, fail=False):
        self.name, self.prereg = name, "test"
        self.script = list(script or [])
        self.verdict = verdict or Verdict("pending", 0, {}, "test")
        self.fail = fail

    def step(self, ctx):
        if self.fail:
            raise RuntimeError("boom")
        return self.script.pop(0) if self.script else []

    def marks(self, ctx):
        return {p.id: (p.entry_price * 1.1, ctx.now) for p in ctx.positions}

    def evaluate(self, trades, now, state):
        return self.verdict


def setup(tmp_path, cfg=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "config.json").write_text(json.dumps({"mode": "paper", "strategies": {}, **(cfg or {})}))
    return tmp_path


def opener(key="a", notional=100.0, price=1.0, at=1000.0, cost=None):
    return Intent("open", "fake", at, price, "test", asset="X", side=1, notional_usd=notional,
                  cost=cost or CostModel(fee=0.01, fixed_usd=0.1), meta={"key": key})


def closer(key="a", price=1.2, at=2000.0, cost=None):
    return Intent("close", "fake", at, price, "test", cost=cost or CostModel(fee=0.01, fixed_usd=0.1), meta={"key": key})


def test_paper_round_trip_accounting(tmp_path):
    root = setup(tmp_path)
    s = run_once(root, now=3000, strategies={"fake": Fake(script=[[opener(), closer()]])})
    assert s["opened"] == 1 and s["closed"] == 1
    (trade,) = Ledger(root).trades()
    # gross +20, costs 2 * (1.0 + 0.1)
    assert trade.pnl_usd == pytest.approx(20 - 2.2)
    assert trade.net_return == pytest.approx(0.178)
    assert (root / "REPORT.md").exists() and (root / "journal.jsonl").exists()


def test_open_position_is_marked_and_persisted(tmp_path):
    root = setup(tmp_path)
    run_once(root, now=3000, strategies={"fake": Fake(script=[[opener()]])})
    led = Ledger(root)
    (pos,) = led.positions
    assert pos.mark_price == pytest.approx(1.1)
    run_once(root, now=4000, strategies={"fake": Fake(script=[[closer()]])})
    assert not Ledger(root).positions and len(Ledger(root).trades()) == 1


def test_risk_caps_and_kill_switch(tmp_path):
    root = setup(tmp_path, {"risk": {"max_position_usd": 50}})
    s = run_once(root, now=3000, strategies={"fake": Fake(script=[[opener(notional=100)]])})
    assert s["rejected"] == 1 and not Ledger(root).positions
    root2 = setup(tmp_path / "b")
    run_once(root2, now=3000, strategies={"fake": Fake(script=[[opener()]])})
    (root2 / "HALT").write_text("test halt")
    s = run_once(root2, now=4000, strategies={"fake": Fake(script=[[opener(key="b"), closer()]])})
    assert s["rejected"] == 1 and s["closed"] == 1  # exits still run under the kill switch
    assert "test halt" in (root2 / "REPORT.md").read_text()


def test_daily_loss_cap_halts_agent(tmp_path):
    root = setup(tmp_path, {"risk": {"daily_loss_cap_usd": 10}})
    s = run_once(root, now=3000, strategies={"fake": Fake(script=[[opener(), closer(price=0.5)]])})
    assert s["halted"] and "daily loss cap" in s["halted"]
    s = run_once(root, now=3100, strategies={"fake": Fake(script=[[opener(key="c")]])})
    assert s["rejected"] == 1
    assert any(c["kind"] == "halt" for c in Ledger(root).changes())


def test_errors_halt_strategy_after_limit(tmp_path):
    root = setup(tmp_path)
    for t in range(3):
        run_once(root, now=3000 + t, strategies={"fake": Fake(fail=True)})
    assert Ledger(root).strategy("fake")["status"] == "halted"
    from tartar.autotrade.__main__ import main
    main(["resume", "fake", "--root", str(root)])
    assert Ledger(root).strategy("fake")["status"] == "paper"


def test_live_mode_without_approval_stays_on_paper(tmp_path, monkeypatch):
    monkeypatch.delenv("TARTAR_LIVE_APPROVED", raising=False)
    root = setup(tmp_path, {"mode": "live"})
    led = Ledger(root)
    led.strategy("fake")["status"] = "promoted"
    led.save()
    run_once(root, now=3000, strategies={"fake": Fake(script=[[opener()]])})
    led = Ledger(root)
    assert led.positions[0].mode == "paper"
    assert "live_refused" in (root / "journal.jsonl").read_text()


def trades(rets, t0=0.0):
    return [Trade(str(i), "fake", "X", 1, 100, 1, t0 + i, 1, t0 + i + 1, 0, 100 * r, r) for i, r in enumerate(rets)]


def test_lifecycle_moves():
    rec = {}
    assert lifecycle.decide("paper", Verdict("pass", 5, {}, "ok"), [], rec, {})[0] == "promoted"
    assert lifecycle.decide("paper", Verdict("fail", 5, {}, "bad"), [], rec, {})[0] == "retired"
    assert lifecycle.decide("paper", Verdict("pending", 5, {}, ""), [], rec, {}) is None
    bad = trades([-0.05 + 0.001 * (i % 3) for i in range(30)])
    assert lifecycle.decide("promoted", Verdict("pending", 30, {}, ""), bad, {"since": 0}, {})[0] == "demoted"
    good = trades([0.05 + 0.001 * (i % 3) for i in range(30)])
    assert lifecycle.decide("demoted", Verdict("pass", 30, {}, ""), good, {"since": 0}, {})[0] == "promoted"
    assert lifecycle.decide("demoted", Verdict("pending", 61, {}, ""), trades([0.0] * 61), {"since": 0}, {})[0] == "retired"


def test_review_logs_and_resizes(tmp_path):
    root = setup(tmp_path)
    run_once(root, now=3000, strategies={"fake": Fake(verdict=Verdict("pass", 9, {"m": 1}, "criteria met"))})
    led = Ledger(root)
    assert led.strategy("fake")["status"] == "promoted"
    (row,) = led.changes()
    assert row["from"] == "paper" and row["to"] == "promoted" and row["reason"].startswith("registered criteria met")


def write_dip_prereg(root: Path, liquidity=100_000.0):
    d = root / "prereg"
    d.mkdir()
    (d / "SPEC.json").write_text(json.dumps({
        "rule": {"lookback_bars": 12, "drop": 0.05, "hold_bars": 48, "bar_seconds": 300},
        "costs": {"fee_per_side": 0.005, "size_usd": 200, "network_usd_per_tx": 0.05},
        "evaluation": {}}))
    (d / "cohort-1.json").write_text(json.dumps({"registered_at": "2026-10-01T00:00:00Z", "pools": [
        {"pool": "P1", "token": "T1", "name": "ONE / SOL", "liquidity_usd": liquidity}]}))
    return d


def test_dip_trades_forward_only_and_holds_48_bars(tmp_path):
    prereg = write_dip_prereg(tmp_path)
    t0 = 1_800_000_000 - 1_800_000_000 % 300
    closes = [1.0] * 200
    data = {"rows": None}

    def bars(n):
        return [[t0 + 300 * i, closes[i], closes[i], closes[i], closes[i], 1.0] for i in range(n)]

    strat = DipStrategy("dip", {"prereg": str(prereg), "_fetch": lambda ctx, pool: data["rows"]})
    root = setup(tmp_path / "agent")
    # run 1 sees 20 bars: cursor only, no back-filled trades
    data["rows"] = bars(20)
    s = run_once(root, now=t0 + 300 * 20, strategies={"dip": strat})
    assert s["opened"] == 0
    # a 10% drop at bar 30; run 2 sees through bar 40
    for i in range(30, 200):
        closes[i] = 0.9
    data["rows"] = bars(41)
    s = run_once(root, now=t0 + 300 * 41, strategies={"dip": strat})
    assert s["opened"] == 1
    (pos,) = Ledger(root).positions
    assert pos.entry_at == t0 + 300 * 31 and pos.entry_price == pytest.approx(0.9)
    assert pos.meta["exit_t"] == t0 + 300 * (30 + 48)
    # run 3 sees the exit bar
    data["rows"] = bars(120)
    s = run_once(root, now=t0 + 300 * 120, strategies={"dip": strat})
    assert s["closed"] == 1 and s.get("opened", 0) == 0  # still busy until the exit, no re-entry on flat prices
    (trade,) = Ledger(root).trades()
    assert trade.exit_at == t0 + 300 * 79
    side_cost = 200 * (0.005 + 200 / 50_000) + 0.05  # registered fee, impact at liquidity/2, network
    assert trade.pnl_usd == pytest.approx(-2 * side_cost)  # flat price: the round trip costs both sides
    assert "baseline" in trade.meta


def test_dip_evaluate_pending_then_scored():
    strat = DipStrategy.__new__(DipStrategy)
    strat.rule = {"hold_bars": 48}
    rng = np.random.default_rng(0)
    tr = []
    for i in range(210):
        r = 0.02 + 0.01 * rng.standard_normal()
        tr.append(Trade(str(i), "dip", f"P{i % 7}", 1, 200, 1, i * 60, 1, i * 60 + 1, 0, 200 * r, r,
                        meta={"pool": f"P{i % 7}", "baseline": -0.01}))
    v = strat.evaluate(tr[:50], 50 * 60, {})
    assert v.decision == "pending"
    v = strat.evaluate(tr, 210 * 60, {})
    assert v.decision == "pass" and v.stats["excess"] > 0


def fake_hyperliquid(n_coins=30, start=date(2026, 7, 1), end=date(2026, 10, 25)):
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    rng = np.random.default_rng(3)
    drift = np.linspace(-0.01, 0.01, n_coins)
    prices = {f"C{j}": 100 * np.exp(np.cumsum(drift[j] + 0.0 * rng.standard_normal(len(days)))) for j in range(n_coins)}

    def post(ctx, body):
        if body["type"] == "meta":
            return {"universe": [{"name": c} for c in prices]}
        if body["type"] == "candleSnapshot":
            c = body["req"]["coin"]
            out = []
            for i, d in enumerate(days):
                t = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)
                if body["req"]["startTime"] <= t < body["req"]["endTime"]:
                    out.append({"t": t, "c": str(prices[c][i]), "v": "1e6"})
            return out
        if body["type"] == "fundingHistory":
            return []
        if body["type"] == "allMids":
            return {c: str(p[-1]) for c, p in prices.items()}
        raise ValueError(body)

    return post


def test_xs_momentum_books_weekly_legs(tmp_path):
    strat = XSMomentum("xs", {"leg_usd": 1000, "_post": fake_hyperliquid()})
    root = setup(tmp_path, {"risk": {"max_gross_usd": 1e9}})
    tue = date(2026, 10, 13)
    s = run_once(root, now=close_ts(tue) - 3600, strategies={"xs": strat})
    assert s.get("opened", 0) == 0  # Tuesday's close not final yet
    s = run_once(root, now=close_ts(tue) + 3600, strategies={"xs": strat})
    led = Ledger(root)
    longs = [p for p in led.positions if p.side > 0]
    shorts = [p for p in led.positions if p.side < 0]
    assert len(longs) == len(shorts) == 6  # 30 coins, quintiles
    assert {p.asset for p in longs} == {f"C{j}" for j in range(24, 30)}  # strongest 14-day returns
    assert sum(p.notional_usd for p in longs) == pytest.approx(1000)
    s = run_once(root, now=close_ts(tue) + 7200, strategies={"xs": strat})
    assert s.get("opened", 0) == 0  # booked once per week
    s = run_once(root, now=close_ts(tue + timedelta(days=7)) + 3600, strategies={"xs": strat})
    led = Ledger(root)
    assert len(led.trades()) == 12 and len(led.positions) == 12
    kept = [t for t in led.trades() if t.reason.endswith("(kept)") and t.cost_usd == pytest.approx(0.002 * t.notional_usd)]
    assert len(kept) == 12  # same ranking: every leg kept, no turnover cost
    v = strat.evaluate(led.trades(), close_ts(tue + timedelta(days=7)) + 3600, {})
    assert v.decision == "pending" and v.n == 1


def test_new_halts_reported_and_equity_logged(tmp_path):
    root = setup(tmp_path)
    s = None
    for t in range(3):
        s = run_once(root, now=3000 + t, strategies={"fake": Fake(fail=True)})
    assert s["new_halts"] and s["new_halts"][0]["scope"] == "fake"
    s = run_once(root, now=4000, strategies={"fake": Fake(fail=True)})
    assert not s["new_halts"]  # already halted: not reported again
    assert len((root / "equity.jsonl").read_text().splitlines()) == 4


def test_alt_cost_reported_beside_registered():
    from tartar.autotrade.broker import PaperBroker

    b = PaperBroker()
    o = opener(cost=CostModel(fee=0.005))
    o.meta["alt_cost"] = {"fee": 0.0125, "impact": 0.0, "fixed_usd": 0.0}
    pos, _ = b.open(o)
    trade, _ = b.close(pos, closer(price=1.0, cost=CostModel(fee=0.005)))
    assert trade.net_return == pytest.approx(-0.01)
    assert trade.meta["alt_net_return"] == pytest.approx(-0.025)
