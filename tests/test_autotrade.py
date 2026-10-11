import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from tartar.autotrade import lifecycle
from tartar.autotrade.broker import PaperBroker
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


def test_daily_loss_cap_stops_only_that_strategy_until_the_next_utc_day(tmp_path):
    root = setup(tmp_path, {"risk": {"daily_loss_cap_usd": 10}})
    s = run_once(root, now=3000, strategies={"fake": Fake(script=[[opener(), closer(price=0.5)]]), "other": Fake(script=[])})
    assert not s["halted"] and s["new_halts"] and "fake" in s["new_halts"][0]["reason"]
    o = opener(key="o")
    o.strategy = "other"
    other = Fake("other", script=[[o]])
    s = run_once(root, now=3100, strategies={"fake": Fake(script=[[opener(key="c")]]), "other": other})
    assert s["rejected"] == 1 and s["opened"] == 1  # fake stopped for the day, other trades on
    s = run_once(root, now=86400 + 3000, strategies={"fake": Fake(script=[[opener(key="d")]])})
    assert s["opened"] == 1  # a new UTC day clears it
    assert any(c["kind"] == "resume" and c["scope"] == "fake" for c in Ledger(root).changes())


def test_errors_halt_strategy_after_limit(tmp_path):
    root = setup(tmp_path)
    for t in range(3):
        run_once(root, now=3000 + t, strategies={"fake": Fake(fail=True)})
    assert Ledger(root).strategy("fake")["status"] == "halted"
    from tartar.autotrade.__main__ import main
    main(["resume", "fake", "--root", str(root)])
    assert Ledger(root).strategy("fake")["status"] == "paper"


def test_error_halt_retries_after_the_cool_down_and_resumes_on_a_clean_step(tmp_path):
    root = setup(tmp_path, {"risk": {"error_retry_hours": 6}})
    for t in range(3):
        run_once(root, now=3000 + t, strategies={"fake": Fake(fail=True)})
    assert Ledger(root).strategy("fake")["status"] == "halted"
    ok = Fake(script=[[opener()]])
    s = run_once(root, now=3000 + 3600, strategies={"fake": ok})
    assert s["opened"] == 0 and Ledger(root).strategy("fake")["status"] == "halted"  # still cooling down
    run_once(root, now=3005 + 6 * 3600, strategies={"fake": Fake(fail=True)})  # the retry fails: next one 6 h on
    assert Ledger(root).strategy("fake")["status"] == "halted"
    s = run_once(root, now=3000 + 9 * 3600, strategies={"fake": ok})
    assert s["opened"] == 0
    s = run_once(root, now=3010 + 12 * 3600, strategies={"fake": ok})
    rec = Ledger(root).strategy("fake")
    assert s["opened"] == 1 and rec["status"] == "paper" and "halted_by_errors_at" not in rec
    assert any(c["kind"] == "resume" and "retry" in c["reason"] for c in Ledger(root).changes())


def test_a_book_leg_may_exceed_the_position_cap_up_to_its_side_budget(tmp_path):
    root = setup(tmp_path, {"risk": {"max_position_usd": 250}})
    leg = opener(notional=1000 / 3)
    leg.meta.update(week="2026-10-12", leg_usd=1000)
    too_big = opener(key="b", notional=400)
    s = run_once(root, now=3000, strategies={"fake": Fake(script=[[leg, too_big]])})
    assert s["opened"] == 1 and s["rejected"] == 1


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
    (row,) = [c for c in led.changes() if c["kind"] == "status"]
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


def test_dip_fetch_budget_skips_then_rotates(tmp_path, monkeypatch):
    from tartar.autotrade.core import Context
    from tartar.autotrade.strategies import dip as dipmod

    prereg = write_dip_prereg(tmp_path)
    (prereg / "cohort-1.json").write_text(json.dumps({"registered_at": "2026-10-01T00:00:00Z", "pools": [
        {"pool": f"P{i}", "token": f"T{i}", "name": f"P{i} / SOL", "liquidity_usd": 1e5} for i in range(3)]}))
    clock = [0.0]
    monkeypatch.setattr(dipmod.time, "time", lambda: clock[0])
    t0 = 1_800_000_000 - 1_800_000_000 % 300
    fetched = []

    def fetch(ctx, pool):  # each request takes 100 s of the budget
        fetched.append(pool)
        clock[0] += 100
        return [[t0 + 300 * i, 1.0, 1.0, 1.0, 1.0, 1.0] for i in range(20)]

    strat = DipStrategy("dip", {"prereg": str(prereg), "_fetch": fetch, "fetch_budget_s": 150})
    state: dict = {}
    strat.step(Context(t0 + 6000, [], state, {}, None))
    assert fetched == ["P0", "P1"] and state["fetch_skipped"] == 1  # P2 skipped, not counted as a failure
    fetched.clear()
    strat.step(Context(t0 + 9600, [], state, {}, None))
    assert fetched == ["P2", "P0"] and state["fetch_skipped"] == 1  # the starved pool goes first next run


def test_dip_evaluate_pending_then_scored():
    strat = DipStrategy.__new__(DipStrategy)
    strat.rule = {"hold_bars": 48}
    strat.family_size = 1
    strat.costs, strat.size = {"fee_per_side": 0.005, "network_usd_per_tx": 0.05}, 200.0
    rng = np.random.default_rng(0)
    tr = []
    for i in range(210):
        r = 0.02 + 0.01 * rng.standard_normal()
        tr.append(Trade(str(i), "dip", f"P{i % 7}", 1, 200, 1, i * 60, 1 + r, i * 60 + 1, 0, 200 * r, r,
                        meta={"pool": f"P{i % 7}", "baseline": -0.01, "impact_assumed": 0.002}))
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


def test_variants_expand_register_and_stay_outside_caps(tmp_path):
    from tartar.autotrade.runner import expand_variants

    cfg = {"strategies": {"dip": {"kind": "dip", "size_usd": 200}},
           "variants": [{"base": "dip", "base_rule": {"drop": 0.05, "hold_bars": 48},
                         "grid": {"drop": [0.03, 0.05], "hold_bars": [24, 48]}}]}
    out = expand_variants(cfg)
    names = sorted(n for n in out if "~" in n)
    assert names == ["dip~drop=0.03~hold_bars=24", "dip~drop=0.03~hold_bars=48", "dip~drop=0.05~hold_bars=24"]
    v = out["dip~drop=0.03~hold_bars=24"]
    assert v["shadow"] and v["family_size"] == 4 and v["rule_overrides"] == {"drop": 0.03, "hold_bars": 24}
    # shadow intents bypass the agent-wide caps; registered once in changes.jsonl
    root = setup(tmp_path, {"risk": {"max_open_total": 0}})
    o = opener()
    o.meta["shadow"] = True
    s = run_once(root, now=3000, strategies={"fake": Fake(script=[[o]])})
    assert s["opened"] == 1
    run_once(root, now=4000, strategies={"fake": Fake()})
    assert [c["kind"] for c in Ledger(root).changes()].count("registered") == 1


def test_quote_check_records_beside_fill(monkeypatch):
    from tartar.autotrade import quotes

    class R:
        def __init__(self, amount):
            self.amount = amount

        def json(self):  # $1 probe gets 1000 out per USD; $200 gets 990 per USD (1% impact)
            per = 1000 if self.amount == 1_000_000 else 990
            return {"priceImpactPct": "0.02", "outAmount": str(int(per * self.amount / 1e6)),
                    "routePlan": [{"swapInfo": {"label": "Pump.fun Amm"}}]}

    class H:
        def get(self, url, params):
            assert params["amount"] in (200_000_000, 1_000_000)
            return R(params["amount"])

    o = opener(notional=200, at=1000)
    o.meta["mint"] = "M"
    out = quotes.quote_check(o, 1100, http=H())
    assert out["jup_impact_measured_pct"] == pytest.approx(1.0) and out["jup_reported_impact_pct"] == pytest.approx(2.0)
    assert out["jup_route"] == ["Pump.fun Amm"]
    assert quotes.quote_check(o, 1000 + 7200, http=H()) is None  # stale entry: no check


def test_quoted_net_return_uses_measured_impact():
    broker = PaperBroker()
    o = opener(notional=100, price=1.0)
    o.cost = CostModel(fee=0.01, impact=0.0, fixed_usd=0.0)
    o.meta["jup_impact_measured_pct"] = 2.0
    pos, _ = broker.open(o)
    trade, _ = broker.close(pos, Intent("close", "fake", 2000, 1.0, "t", position_id=pos.id, cost=o.cost))
    assert trade.net_return == pytest.approx(-0.02)
    assert trade.meta["quoted_net_return"] == pytest.approx(-0.06)


def test_dip_real_trading_execution_late_entry_and_route_fee(tmp_path):
    prereg = write_dip_prereg(tmp_path)
    t0 = 1_800_000_000 - 1_800_000_000 % 300
    closes = [1.0] * 200
    opens = [1.0] * 200
    data = {"rows": None}

    def bars(n):
        return [[t0 + 300 * i, opens[i], 1, 1, closes[i], 1.0] for i in range(n)]

    ex = {"entry": "next_bar_close", "route_fee_per_side": 0.01, "version": "2026-10-10-real-fills"}
    strat = DipStrategy("dip", {"prereg": str(prereg), "_fetch": lambda ctx, pool: data["rows"], "execution": ex})
    root = setup(tmp_path / "agent")
    data["rows"] = bars(20)
    run_once(root, now=t0 + 300 * 20, strategies={"dip": strat})
    for i in range(30, 200):
        closes[i] = opens[i] = 0.9
    closes[31] = 0.92  # bar t+1 rebounds before the real buy lands
    for i in range(32, 200):
        opens[i] = closes[i] = 0.92
    data["rows"] = bars(41)
    run_once(root, now=t0 + 300 * 41, strategies={"dip": strat})
    (pos,) = Ledger(root).positions
    assert pos.entry_at == t0 + 300 * 32 and pos.entry_price == pytest.approx(0.92)
    assert pos.meta["registered_entry_price"] == pytest.approx(0.9) and pos.meta["route_fee"] == 0.01
    changes = [c for c in Ledger(root).changes() if c["kind"] == "cost_update"]
    assert len(changes) == 1 and changes[0]["to"] == "2026-10-10-real-fills"
    data["rows"] = bars(120)
    run_once(root, now=t0 + 300 * 120, strategies={"dip": strat})
    (trade,) = Ledger(root).trades()
    side_cost = 200 * (0.015 + 200 / 50_000) + 0.05  # registered fee + 1% route, impact, network
    assert trade.pnl_usd == pytest.approx(-2 * side_cost)
    assert strat.registered_net(trade) > strat.spec_net(trade) + 0.03  # +2.2% rebound and 2 x 1% route fee
    assert len([c for c in Ledger(root).changes() if c["kind"] == "cost_update"]) == 1  # logged once


def test_dip_entry_delay_prices_inside_next_bar_and_replay_counts(tmp_path):
    prereg = write_dip_prereg(tmp_path)
    s = DipStrategy("dip", {"prereg": str(prereg), "_fetch": lambda ctx, pool: None,
                            "execution": {"entry": "delay", "entry_delay_s": 60, "version": "v"}})
    assert s.late_entry and s.delayed_px(1.0, 1.5) == pytest.approx(1.1)  # 60 s of a 300 s bar
    assert "60 s into bar t+1" in s.describe()["execution"]["entry"]
    # replay rows count toward the verdict, except ones the agent also traded
    rows = [{"name": f"P{i % 7}", "t": 1_800_000_000 + 3600 * i, "gross": -0.05} for i in range(30)]
    (tmp_path / "rep.json").write_text(json.dumps(rows))
    s = DipStrategy("dip", {"prereg": str(prereg), "_fetch": lambda ctx, pool: None, "replay": str(tmp_path / "rep.json")})
    s.pools = lambda: []
    mine = Trade("x", "dip", "addr", 1, 200, 1, 1_800_000_000, 1.0, 1_800_000_000 + 1, 0, 0, 0.0,
                 meta={"label": "P0", "signal_t": 1_800_000_100, "pool": "addr"})
    nets, _ = s.replay_nets([mine])
    assert len(nets) == 29 and all(x < -0.05 for x in nets)
    v = s.evaluate([mine], 1_800_000_000 + 86400 * 22, {})
    assert v.stats["n"] == 30 and v.stats["n_replay"] == 29 and v.decision == "fail"
    s2 = DipStrategy("dip", {"prereg": str(prereg), "_fetch": lambda ctx, pool: None, "replay": str(tmp_path / "rep.json"),
                             "rule_overrides": {"hold_bars": 24}})
    assert s2.replay_rows() == []  # variants don't borrow the registered rule's replay


def test_dip_schedule_entry_waits_for_the_next_hourly_run(tmp_path):
    prereg = write_dip_prereg(tmp_path)
    s = DipStrategy("dip", {"prereg": str(prereg), "_fetch": lambda ctx, pool: None,
                            "execution": {"entry": "schedule", "run_minute": 6, "run_lag_s": 60, "version": "v"}})
    t0 = 1_800_000_000 - 1_800_000_000 % 3600  # an hour boundary
    t = np.arange(t0, t0 + 3600 * 2, 300.0)
    o = np.arange(len(t), dtype=float)
    c = o + 0.5
    i = 3  # bar 00:15-00:20 -> next run 01:07, inside bar 01:05 (index 13), 2 of its 5 minutes
    assert s.entry(t, o, c, i) == (t0 + 3600 + 420, pytest.approx(13 + 0.5 * 0.4))
    assert s.entry(t[:13], o[:13], c[:13], i) is None  # not in the data yet
    assert "next hourly run, :07:00" in s.describe()["execution"]["entry"]


def test_weekly_books_are_judged_per_week_against_the_side_budget():
    from tartar.autotrade import lifecycle

    def leg(i, week, pnl, at):
        return Trade(str(i), "xs", "X", 1, 250, 1, at - 1, 1, at, 0, pnl, pnl / 250, meta={"week": week, "leg_usd": 1000.0})

    # four legs of one week losing $25 each: -10% of the side budget, an ordinary bad week, but 40% of one leg
    legs = [leg(f"{w}{k}", f"w{w}", (25 if w % 2 else -25), 100 * w + 10) for w in range(1, 7) for k in range(4)]
    units = lifecycle.book_units(legs)
    assert len(units) == 6 and units[1].net_return == pytest.approx(-0.10)
    rec = {"since": 0}
    assert lifecycle.decide("promoted", Verdict("pending", 6, {}, ""), legs, rec, {}) is None
    assert lifecycle.drawdown_pct(legs) > 0.25  # what the per-leg rule would have seen
    crash = legs + [leg(f"c{k}", "w7", -100, 710) for k in range(4)]  # -40% of the side in one week
    new, why = lifecycle.decide("promoted", Verdict("pending", 7, {}, ""), crash, rec, {})
    assert new == "demoted" and "side budget" in why
