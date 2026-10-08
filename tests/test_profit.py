"""Cost-aware trade simulation on recorded bonding curves."""

import numpy as np
import pytest

from tartar.candles import Tick
from tartar.data.dataset import build_dataset, load_trade_tokens
from tartar.data.simulate import simulate_raw
from tartar.profit import Costs, Curve, Exit, buy_tokens, curves_for, profit_report, round_trip, run_policy, sell_sol, summarize
from tartar.train import train_global

VTOK0 = 1_073_000_000.0


def tick(ts: float, vsol: float) -> Tick:
    """A trade leaving the standard curve at `vsol` virtual SOL."""
    vtok = 30.0 * VTOK0 / vsol
    return Tick(ts, vsol / vtok, virtual_sol=vsol, liquidity=vsol - 30.0)


def test_curve_round_trip_costs():
    vsol, vtok = 40.0, 30.0 * VTOK0 / 40.0
    tokens = buy_tokens(vsol, vtok, 1.0, 0.0)
    assert tokens == pytest.approx(vtok * 1.0 / (vsol + 1.0))
    # selling straight back into the same reserves loses only the price impact paid twice
    back = sell_sol(vsol, vtok, tokens, 0.0)
    assert 0.94 < back < 1.0
    # fees cost about one fee per side
    with_fees = sell_sol(vsol, vtok, buy_tokens(vsol, vtok, 1.0, 0.01), 0.01)
    assert with_fees == pytest.approx(back * 0.99 * 0.99, rel=2e-3)


def test_round_trip_uses_latency_and_horizon():
    curve = Curve([tick(0.0, 30.0), tick(0.5, 40.0), tick(5.0, 60.0), tick(20.0, 50.0)])
    costs = Costs(size_sol=0.01, fee=0.0, network_sol=0.0, latency=1.0)
    trade = round_trip(curve, 0.0, costs, Exit(horizon=10.0))
    assert trade.entry_price == pytest.approx(curve.price[1])  # filled after the 0.5 s trade, not at the decision
    assert trade.exit_price == pytest.approx(curve.price[2])  # the state at entry + 10 s
    assert trade.pnl_sol > 0 and trade.reason == "horizon" and not trade.censored
    assert round_trip(curve, -5.0, costs, Exit(10.0)) is None  # nothing had traded yet
    late = round_trip(curve, 19.0, costs, Exit(60.0))
    assert late.censored and late.exit_price == pytest.approx(curve.price[-1])


def test_take_profit_and_stop_loss():
    up = Curve([tick(0.0, 30.0), tick(2.0, 45.0), tick(3.0, 30.0)])
    costs = Costs(size_sol=0.01, fee=0.0, network_sol=0.0, latency=0.5)
    trade = round_trip(up, 0.0, costs, Exit(60.0, take_profit=0.5))
    assert trade.reason == "take_profit" and trade.exit == pytest.approx(2.5)
    down = Curve([tick(0.0, 40.0), tick(2.0, 30.0), tick(3.0, 60.0)])
    trade = round_trip(down, 0.0, costs, Exit(60.0, stop_loss=0.2))
    assert trade.reason == "stop_loss" and trade.pnl_sol < 0


def test_one_position_per_token_and_summary():
    curves = [Curve([tick(0.0, 30.0), tick(30.0, 35.0), tick(90.0, 33.0)]), Curve([tick(0.0, 30.0), tick(10.0, 28.0)])]
    token = np.array([0, 0, 0, 1])
    time = np.array([0.0, 20.0, 70.0, 0.0])
    costs = Costs(size_sol=0.1, fee=0.0125, network_sol=0.0002, latency=1.0)
    trades = run_policy(curves, token, time, np.ones(4, bool), costs, Exit(60.0))
    assert [(t.token, t.decided) for t in trades] == [(0, 0.0), (0, 70.0), (1, 0.0)]  # 20 s falls inside the first position
    s = summarize(trades, costs, boot=200)
    assert s.trades == 3 and s.tokens == 2
    assert s.total_sol == pytest.approx(sum(t.pnl_sol for t in trades))
    assert s.ci_low <= s.mean_ret <= s.ci_high


def test_profit_report_on_simulated_launches(tmp_path):
    simulate_raw(tmp_path, 60, seed=3)
    tokens = load_trade_tokens(tmp_path, 60)
    ds = build_dataset(tokens, 60, "trades")
    assert len(ds.time) == len(ds) and np.all(ds.time >= np.array([tokens[k].created for k in ds.token]))
    assert len(curves_for(tokens)) == len(tokens)
    model = train_global(ds, rounds=10, early_stopping=5, num_leaves=7, min_data_in_leaf=20, log=lambda m: None)
    rows = profit_report(ds, Costs(), model)
    assert {r["split"] for r in rows} == {"valid", "test"}
    assert any(r["strategy"].startswith("buy every launch") and r["trades"] > 0 for r in rows)
    for r in rows:
        assert r["trades"] == 0 or -1.0 <= r["mean_ret"]
