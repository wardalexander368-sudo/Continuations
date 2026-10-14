"""The adopted US live rule's gate and cost checks (live_gate.py), offline."""

import json

import pytest

from tartar.autotrade import live_gate as lg
from tartar.autotrade import observation_coverage as oc

DAY = 86400.0
T0 = 1_791_800_000.0  # 2026-10-12 10:13 UTC, inside the forward window
NOW = T0 + 4 * DAY


def complete_state():
    from tartar.autotrade.strategies.coinbase_pattern import COINS

    data = {}
    start_h = lg.WINDOW_START // 3600
    c = oc.initialize(data, done=start_h - 1, now=int(NOW), coins=COINS,
                      start="2026-10-12", end="2027-10-11", delay=1, rule="capit")
    through = (int(NOW) - 60 - 900) // 3600 - 1
    for h in range(start_h, through + 1):
        for coin in COINS:
            oc.record(c, coin, h, "observed-no-signal", int(NOW))
    oc.finish(c, through)
    return {"strategies": {lg.GATE_STRATEGY: {"data": data}}, "last_run": {"at": NOW},
            "alpaca": {"reconcile": {"checked_at": NOW, "ok": True, "unconfirmed": [], "mismatches": [], "stuck_orders": []}}}


def measured_gate(rows):
    return lg.gate(rows, complete_state(), NOW)


def trip(pos, day, sym="BTC/USD", cost=0.004, net=0.02, strategy="us_capit_fast", gap=10.0):
    at = T0 + day * DAY
    completion = {"order_status": "filled", "requested_qty": 1.0, "filled_qty": 1.0, "fill_completion": "complete-requested-fill"}
    return [{"event": "buy", "at": at, "paper_at": at, "strategy": strategy, "position": pos, "symbol": sym, **completion},
            {"event": "sell", "at": at + DAY, "strategy": strategy, "position": pos, "symbol": sym,
             "measured_side_cost": cost, "alpaca_net_return": net, "entry_gap_bps": gap, "exit_gap_bps": -gap, **completion}]


def rows_for(n_days, per_day, **kw):
    out = []
    for d in range(n_days):
        for k in range(per_day):
            out += trip(f"p{d}-{k}", d, sym=["BTC/USD", "ETH/USD", "SOL/USD"][k % 3], **kw)
    return out


def test_gate_counts_days_not_trades():
    g = measured_gate(rows_for(2, 5))
    assert (g["crash_days"], g["trades"], g["met"]) == (2, 10, False)
    assert "2/3 crash days" in g["unmet"][0]


def test_gate_met_on_paper_side():
    g = measured_gate(rows_for(3, 3))
    assert g["met"] and g["unmet"] == []
    assert abs(g["mean_net"] - 0.02) < 1e-12


def test_gate_ignores_other_strategies():
    assert measured_gate(rows_for(3, 3, strategy="us_volspike"))["trades"] == 0


def test_gate_fails_on_mean_cost_and_gap():
    assert any("mean net" in u for u in measured_gate(rows_for(3, 3, net=-0.05))["unmet"])
    assert any("median cost" in u for u in measured_gate(rows_for(3, 3, cost=0.0055))["unmet"])
    assert any("bp from the paper" in u for u in measured_gate(rows_for(3, 3, gap=60))["unmet"])


def test_coin_screen_needs_three_fills():
    rows = trip("a", 0, "LTC/USD", cost=0.0058) + trip("b", 1, "LTC/USD", cost=0.0056)
    assert lg.coin_screen(lg.round_trips(rows))["LTC/USD"]["ok"] is None
    rows += trip("c", 2, "LTC/USD", cost=0.0057)
    assert lg.coin_screen(lg.round_trips(rows))["LTC/USD"]["ok"] is False


def write(tmp_path, rows):
    (tmp_path / "alpaca_fills.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_health_levels(tmp_path):
    assert lg.health_items(tmp_path)[0]["level"] == "yellow"  # cost is unmeasured
    assert lg.health_items(tmp_path)[0]["paper_cost_evidence"] == "unmeasured"
    write(tmp_path, rows_for(1, 4, cost=0.007))
    assert lg.health_items(tmp_path)[0]["level"] == "yellow"  # 4 round trips: insufficient evidence
    write(tmp_path, rows_for(1, 5, cost=0.0055))
    assert lg.health_items(tmp_path)[0]["level"] == "yellow"
    write(tmp_path, rows_for(1, 5, cost=0.0065))
    assert lg.health_items(tmp_path)[0]["level"] == "red"


def test_report_line(tmp_path):
    lines = lg.report_lines(tmp_path, complete_state(), NOW)
    assert "0/3 crash days" in lines[1] and "Nothing trades live" in lines[1]
    write(tmp_path, rows_for(3, 3))
    lines = lg.report_lines(tmp_path, complete_state(), NOW)
    assert "Paper side met" in lines[1] and "AJ's go" in lines[1]
    assert lines[2].startswith("Coin cost screen")
    assert any("paper-fill-proxy" in line and "actual commission unverified" in line for line in lines)


def test_damaged_fills_never_raise(tmp_path):
    (tmp_path / "alpaca_fills.jsonl").write_text('{"event": "sell"\nnot json\n[1, 2]\n')
    assert lg.health_items(tmp_path)[0]["check"] == "Alpaca paper cost"
    assert "Live rule gate" in lg.report_lines(tmp_path)[1]
    write(tmp_path, [{"event": "sell", "measured_side_cost": "x", "position": "p", "strategy": "us_capit_fast", "at": T0}])
    assert lg.health_items(tmp_path)[0]["level"] == "yellow"
    assert "Live rule gate" in lg.report_lines(tmp_path)[1]


def test_random_entry_control_line():
    assert "no priced us_capit trades yet" in lg.control_line(None)
    st = {"strategies": {"us_capit": {"verdict": {"stats": {"excess": 0.031, "excess_lo": -0.01, "excess_hi": 0.07, "excess_n": 9}}}}}
    assert "+3.10%/trade [-1.00, +7.00] over 9 paper trades" in lg.control_line(st)


def test_gate_rejects_bad_inputs():
    """Codex review 2026-10-13: each of these used to report the paper side as met."""
    import copy
    three = [r for d in range(3) for r in trip(f"p{d}", d)]
    dup = three + [copy.deepcopy(r) for r in three if r["event"] == "sell"] * 2
    orphans = [r for r in rows_for(3, 3) if r["event"] == "sell"]
    old = [dict(r, at=r["at"] - 30 * DAY, paper_at=r.get("paper_at", r["at"]) - 30 * DAY) for r in rows_for(3, 3)]
    nan = [dict(r, **{k: float("nan") for k in lg.NUMERIC}) if r["event"] == "sell" else r for r in rows_for(3, 3)]
    missing = [{k: v for k, v in r.items() if k not in ("entry_gap_bps", "exit_gap_bps")} for r in rows_for(3, 3)]
    for rows in (dup, orphans, old, nan, missing):
        g = measured_gate(rows)
        assert not g["met"] and g["rejected"], g
    assert measured_gate(dup)["trades"] == 3


def test_gate_requires_fresh_and_well_formed_fast_line_observation_coverage():
    rows = rows_for(3, 3)
    assert measured_gate(rows)["met"]
    assert not lg.gate(rows, None, NOW)["met"]
    state = complete_state()
    coverage = state["strategies"][lg.GATE_STRATEGY]["data"]["coverage"]
    g = lg.gate(rows, state, NOW + 3 * 3600)
    assert not g["met"] and g["coverage"]["status"] == "stale"
    coverage["counts"]["observed-no-signal"] -= 1
    assert lg.gate(rows, state, NOW)["coverage"]["status"] == "malformed"
    coverage["counts"]["observed-no-signal"] += 1
    coverage["receipts"] = ["not a receipt object"]
    assert lg.gate(rows, state, NOW)["coverage"]["status"] == "malformed"

    wrong_rule = complete_state()
    wrong_rule["strategies"][lg.GATE_STRATEGY]["data"]["coverage"]["rule"] = "volspike"
    g = lg.gate(rows, wrong_rule, NOW)
    assert not g["met"] and "does not match" in g["coverage"]["detail"]


def test_original_gap_still_blocks_gate_after_data_is_recovered():
    state = complete_state()
    c = state["strategies"][lg.GATE_STRATEGY]["data"]["coverage"]
    key = next(iter(c["receipts"]))
    receipt = c["receipts"][key]
    receipt.update(state="incomplete", reason="missing-entry-candle")
    c["counts"]["observed-no-signal"] -= 1
    c["counts"]["incomplete"] += 1
    c["pending"][key] = receipt["hour"]
    oc.recovered(c, receipt["coin"], receipt["hour"], int(NOW), signal=True)
    g = lg.gate(rows_for(3, 3), state, NOW)
    assert not g["met"] and g["coverage"]["late_recovered_coin_hours"] == 1


def test_malformed_lines_and_unmeasured_sells_are_surfaced_and_block_gate(tmp_path):
    rows = rows_for(3, 3)
    write(tmp_path, rows)
    with (tmp_path / "alpaca_fills.jsonl").open("a") as f:
        f.write('not json\n[1, 2]\n')
    g = lg.gate(lg._rows(tmp_path), complete_state(), NOW)
    assert not g["met"] and {r["why"] for r in g["rejected"]} == {"malformed JSON", "non-object JSON"}
    assert lg.health_items(tmp_path)[0]["level"] == "yellow"
    unmeasured = [{k: v for k, v in row.items() if k != "measured_side_cost"} for row in trip("unmeasured", 0)]
    g = measured_gate(rows + unmeasured)
    assert not g["met"] and g["rejected"] == [{"position": "unmeasured", "why": "unmeasured sell"}]


def test_fill_ignores_non_finite_price():
    from tartar.autotrade.alpaca import _fill
    assert _fill({"status": "filled", "filled_qty": "1", "filled_avg_price": "NaN"}) is None
    assert _fill({"status": "filled", "filled_qty": "1", "filled_avg_price": "100"}) == (1.0, 100.0)


@pytest.mark.parametrize("side, changes, expected", (
    ("sell", {"symbol": "ETH/USD"}, "buy/sell symbol mismatch"),
    ("buy", {"symbol": None}, "missing or invalid symbol"),
    ("sell", {"at": T0 - 1800}, "sell precedes buy"),
    ("buy", {"at": float("nan")}, "missing or non-finite event time"),
    ("sell", {"at": float("inf")}, "missing or non-finite event time"),
    ("sell", {"at": True}, "missing or non-finite event time"),
    ("buy", {"paper_at": None}, "missing or non-finite event time"),
    ("buy", {"paper_at": float("nan")}, "missing or non-finite event time"),
    ("buy", {"paper_at": 0}, "entered before the window"),
    ("buy", {"paper_at": T0 + 60}, "paper event time contradicts execution"),
    ("sell", {"paper_at": T0 - 60}, "paper event time contradicts execution"),
    ("sell", {"paper_at": T0 + DAY + 60}, "paper event time contradicts execution"),
))
def test_round_trip_rejects_asset_and_clock_identity_defects(side, changes, expected):
    bad = trip("bad", 0)
    next(row for row in bad if row["event"] == side).update(changes)
    rejected = []
    assert lg.round_trips(bad, rejected=rejected) == []
    assert rejected == [{"position": "bad", "why": expected}]
    g = measured_gate(rows_for(3, 3) + bad)
    assert not g["met"] and g["trades"] == 9 and g["rejected"][0]["why"] == expected


def test_round_trip_requires_actual_clocks_and_accepts_legacy_paper_clock_fallback():
    rows = trip("p", 0)
    del rows[1]["at"]
    rejected = []
    assert lg.round_trips(rows, rejected=rejected) == []
    assert rejected[0]["why"] == "missing or non-finite event time"

    rows = trip("p", 0)
    del rows[0]["paper_at"]  # legacy rows have only the actual buy clock
    rows[1]["at"] = rows[0]["at"]  # same-run buy/close is chronologically valid
    assert len(lg.round_trips(list(reversed(rows)))) == 1


def test_unknown_fill_events_are_rejected_and_failure_information_is_allowed():
    rows = rows_for(3, 3)
    information = [{"event": "error", "at": T0, "error": "synthetic failure"},
                   {"event": "skip", "at": T0, "reason": "synthetic spread screen"}]
    assert measured_gate(rows + information)["met"]
    bad = {"event": "selll", "position": "typo", "strategy": lg.GATE_STRATEGY}
    g = measured_gate(rows + information + [bad])
    assert not g["met"] and g["trades"] == 9
    assert g["rejected"] == [{"position": "typo", "why": "unexpected fill event", "event": "selll"}]


@pytest.mark.parametrize("side, changes, reason", (
    ("buy", {"order_status": "partially_filled"}, "buy partial or unfilled"),
    ("sell", {"order_status": "canceled"}, "sell partial or unfilled"),
    ("buy", {"filled_qty": 0.5}, "buy filled quantity differs from request"),
    ("sell", {"filled_qty": 0.5}, "sell filled quantity differs from request"),
    ("sell", {"filled_qty": 1.1}, "sell filled quantity differs from request"),
    ("sell", {"requested_qty": None}, "sell completion unknown"),
    ("buy", {"fill_completion": "unknown"}, "buy completion unknown"),
    ("sell", {"filled_qty": float("nan")}, "sell completion unknown"),
))
def test_partial_or_unproven_requested_fills_cannot_count_as_round_trips(side, changes, reason):
    rows = trip("partial", 0)
    next(r for r in rows if r["event"] == side).update(changes)
    g = measured_gate(rows_for(3, 3) + rows)
    assert not g["met"] and g["trades"] == 9
    assert g["rejected"] == [{"position": "partial", "why": reason}]


def test_legacy_missing_completion_proof_is_unknown_not_assumed_filled():
    rows = [{k: v for k, v in r.items() if k not in ("order_status", "requested_qty", "filled_qty", "fill_completion")}
            for r in trip("legacy", 0)]
    rejected = []
    assert lg.round_trips(rows, rejected=rejected) == []
    assert rejected == [{"position": "legacy", "why": "buy completion unknown"}]


def test_a_partial_buy_without_a_sell_is_visible_and_blocks_readiness():
    buy = trip("still-partial", 0)[0]
    buy.update(order_status="partially_filled", fill_completion="partial-or-unfilled", filled_qty=0.5)
    g = measured_gate(rows_for(3, 3) + [buy])
    assert not g["met"] and g["trades"] == 9
    assert g["rejected"] == [{"position": "still-partial", "why": "buy partial or unfilled"}]


@pytest.mark.parametrize("changes, status", (
    ({"ok": None}, "unknown"),
    ({"checked_at": float("nan")}, "unknown"),
    ({"checked_at": NOW + 1}, "unknown"),
    ({"checked_at": NOW - lg.RECON_MAX_AGE - 1}, "stale"),
    ({"unconfirmed": ["BTCUSD"]}, "unmatched"),
    ({"mismatches": [{"symbol": "BTCUSD", "held_qty": 1}]}, "unmatched"),
    ({"stuck_orders": [{"symbol": "BTCUSD"}]}, "unmatched"),
    ({"unconfirmed": None}, "unknown"),
))
def test_readiness_requires_fresh_complete_existing_account_reconciliation(changes, status):
    state = complete_state()
    state["alpaca"]["reconcile"].update(changes)
    g = lg.gate(rows_for(3, 3), state, NOW)
    assert not g["met"] and g["terminal_inventory"]["status"] == status
    assert any("Terminal paper inventory" in item for item in g["unmet"])


def test_missing_reconciliation_keeps_terminal_inventory_unknown():
    state = complete_state()
    del state["alpaca"]
    g = lg.gate(rows_for(3, 3), state, NOW)
    assert not g["met"] and g["terminal_inventory"]["status"] == "unknown"


def test_terminal_reconciliation_must_follow_latest_trade_observation():
    state = complete_state()
    state["alpaca"]["reconcile"]["checked_at"] = NOW - 1800
    rows = rows_for(3, 3)
    rows[-1]["at"] = NOW
    g = lg.gate(rows, state, NOW)
    assert not g["met"] and "predates" in g["terminal_inventory"]["detail"]
