"""Regression tests for the 2026-10-10 correctness audit (STATUS log, code audit thread)."""

import importlib.util
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tartar.autotrade.strategies.xs_momentum import XSMomentum, close_ts


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, Path("handoff/experiments") / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def hourly_payments(t0, t1, rate_at):
    """Hyperliquid-style funding rows: one per hour, stamped a few ms after the hour."""
    out, h = [], int(t0 // 3600) * 3600
    while h <= t1 + 3600:
        out.append({"time": h * 1000 + 37, "fundingRate": str(rate_at(h))})
        h += 3600
    return out


def test_xs_scorer_charges_funding_over_the_hold_not_a_day_early():
    xs = load_script("xs_momentum_forward")
    m = date(2026, 10, 12)  # signal Monday
    hours = list(xs.hold_hours(m))
    wed = datetime(2026, 10, 14, tzinfo=timezone.utc).timestamp()
    assert len(hours) == 168
    assert hours[0] * 3600 == wed + 3600  # first payment after entry at Tuesday's close (Wed 00:00)
    assert hours[-1] * 3600 == wed + 7 * 86400  # last: the payment at the next Tuesday's close


def test_xs_agent_funding_is_the_hours_after_entry_through_exit():
    t0 = close_ts(date(2026, 10, 13))
    t1 = close_ts(date(2026, 10, 20))
    rows = hourly_payments(t0 - 86400, t1 + 86400, lambda h: 1.0 if t0 < h <= t1 else 1000.0)

    def post(ctx, body):
        assert body["type"] == "fundingHistory"
        return [r for r in rows if body["startTime"] <= r["time"] <= body["endTime"]]

    strat = XSMomentum("xs", {"_post": post})
    assert strat.funding(None, "BTC", t0, t1) == pytest.approx(168.0)


def test_pumpflow_scorer_funding_window_matches():
    pf = load_script("pumpflow_paper")
    a = {"t": "2026-10-11T03:20:00Z", "mid": 1.0, "position": 1}
    b = {"t": "2026-10-12T03:20:00Z", "mid": 1.0, "position": 1}
    t0 = pf.ts(a["t"])
    fund = {t0 - 1: 9.0, t0 + 1: 0.001, pf.ts(b["t"]): 0.002, pf.ts(b["t"]) + 1: 9.0}
    ((net, hold, p),) = pf.trades([a, b], fund)
    assert net == pytest.approx(-0.003 - 1e-3)  # long pays 0.1% + 0.2% funding, plus the entry side's cost


def test_dip_agent_scores_trades_with_the_registered_net_formula():
    import numpy as np

    from tartar.autotrade.core import Trade
    from tartar.autotrade.strategies.dip import DipStrategy

    strat = DipStrategy("dip", {})
    spec = json.loads(Path("handoff/preregistration/dip-rolling/SPEC.json").read_text())["costs"]
    fee, size, network = spec["fee_per_side"], spec["size_usd"], spec["network_usd_per_tx"]
    entry, exit_, impact = 0.002, 0.00226, 0.004
    t = Trade("x", "dip", "P", 1, size, entry, 0, exit_, 1, 0, 0, 0, meta={"impact_assumed": impact})
    official = (exit_ / entry) * (1 - fee) ** 2 * (1 - impact) ** 2 - 1 - 2 * network / size  # established_prereg_eval.net
    assert strat.spec_net(t) == pytest.approx(official)
    # the baseline uses the same formula: one entry bar, flat except the exit
    from tartar.autotrade.core import CostModel

    strat.rule = {**strat.rule, "hold_bars": 1}
    o = np.array([entry, entry, entry]); c = np.array([entry, exit_, exit_]); tt = np.array([0, 300, 600])
    b = strat.baseline(tt, o, c, 0, 600, CostModel(fee=fee, impact=impact, fixed_usd=network))
    assert b == pytest.approx(official)


def test_health_flags_an_agent_that_stopped_running_inside_a_live_job(tmp_path):
    from tartar.autotrade import health

    now = 1_800_000_000.0
    (tmp_path / "state.json").write_text(json.dumps({"last_run": {"at": now - 3 * 3600}}))  # hourly runs
    items = {i["check"]: i["level"] for i in health.check_agent(tmp_path, now)}
    assert items.get("Agent: last run") == "red"
    (tmp_path / "state.json").write_text(json.dumps({"last_run": {"at": now - 65 * 60}}))
    assert "Agent: last run" not in {i["check"] for i in health.check_agent(tmp_path, now)}


def test_configured_risk_caps_admit_a_full_xs_book_and_signal_age_fits_observed_lag(tmp_path):
    """A full xs-momentum book (two quintiles of ~200 eligible perps) next to the dip cohorts must not
    hit the paper caps, or registered legs would be dropped; spot signals arrive 5-21 minutes old."""
    from tartar.autotrade.core import Intent, Position
    from tartar.autotrade.risk import Risk

    cfg = json.loads((Path(__file__).resolve().parents[1] / "autotrade/config.json").read_text())

    class L:
        state = {"daily": {}}

    risk = Risk(cfg, tmp_path, L())
    pos = [Position(str(i), "xs_momentum", f"C{i}", 1, 1000 / 40, 1.0, 0.0, 0.0) for i in range(79)]
    pos += [Position(f"d{i}", "dip", f"M{i}", 1, 200, 1.0, 0.0, 0.0) for i in range(40)]
    leg = Intent("open", "xs_momentum", 0.0, 1.0, asset="C80", notional_usd=1000 / 40)
    assert risk.allow_open(leg, pos) is None
    assert cfg["live"]["max_signal_age_s"] >= 1300
