"""The adopted US live rule's gate and cost checks (live_gate.py), offline."""

import json

from tartar.autotrade import live_gate as lg

DAY = 86400.0
T0 = 1_790_000_000.0  # 2026-09-21


def trip(pos, day, sym="BTC/USD", cost=0.004, net=0.02, strategy="us_capit_fast", gap=10.0):
    at = T0 + day * DAY
    return [{"event": "buy", "at": at, "paper_at": at, "strategy": strategy, "position": pos, "symbol": sym},
            {"event": "sell", "at": at + DAY, "strategy": strategy, "position": pos, "symbol": sym,
             "measured_side_cost": cost, "alpaca_net_return": net, "entry_gap_bps": gap, "exit_gap_bps": -gap}]


def rows_for(n_days, per_day, **kw):
    out = []
    for d in range(n_days):
        for k in range(per_day):
            out += trip(f"p{d}-{k}", d, sym=["BTC/USD", "ETH/USD", "SOL/USD"][k % 3], **kw)
    return out


def test_gate_counts_days_not_trades():
    g = lg.gate(rows_for(2, 5))
    assert (g["crash_days"], g["trades"], g["met"]) == (2, 10, False)
    assert "2/3 crash days" in g["unmet"][0]


def test_gate_met_on_paper_side():
    g = lg.gate(rows_for(3, 3))
    assert g["met"] and g["unmet"] == []
    assert abs(g["mean_net"] - 0.02) < 1e-12


def test_gate_ignores_other_strategies():
    assert lg.gate(rows_for(3, 3, strategy="us_volspike"))["trades"] == 0


def test_gate_fails_on_mean_cost_and_gap():
    assert any("mean net" in u for u in lg.gate(rows_for(3, 3, net=-0.05))["unmet"])
    assert any("median cost" in u for u in lg.gate(rows_for(3, 3, cost=0.0055))["unmet"])
    assert any("bp from the paper" in u for u in lg.gate(rows_for(3, 3, gap=60))["unmet"])


def test_coin_screen_needs_three_fills():
    rows = trip("a", 0, "LTC/USD", cost=0.0058) + trip("b", 1, "LTC/USD", cost=0.0056)
    assert lg.coin_screen(lg.round_trips(rows))["LTC/USD"]["ok"] is None
    rows += trip("c", 2, "LTC/USD", cost=0.0057)
    assert lg.coin_screen(lg.round_trips(rows))["LTC/USD"]["ok"] is False


def write(tmp_path, rows):
    (tmp_path / "alpaca_fills.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_health_levels(tmp_path):
    assert lg.health_items(tmp_path)[0]["level"] == "green"  # no fills yet
    write(tmp_path, rows_for(1, 4, cost=0.007))
    assert lg.health_items(tmp_path)[0]["level"] == "green"  # 4 round trips: not judged yet
    write(tmp_path, rows_for(1, 5, cost=0.0055))
    assert lg.health_items(tmp_path)[0]["level"] == "yellow"
    write(tmp_path, rows_for(1, 5, cost=0.0065))
    assert lg.health_items(tmp_path)[0]["level"] == "red"


def test_report_line(tmp_path):
    lines = lg.report_lines(tmp_path)
    assert "0/3 crash days" in lines[1] and "Nothing trades live" in lines[1]
    write(tmp_path, rows_for(3, 3))
    lines = lg.report_lines(tmp_path)
    assert "Paper side met" in lines[1] and "AJ's go" in lines[1]
    assert lines[2].startswith("Coin cost screen")


def test_damaged_fills_never_raise(tmp_path):
    (tmp_path / "alpaca_fills.jsonl").write_text('{"event": "sell"\nnot json\n[1, 2]\n')
    assert lg.health_items(tmp_path)[0]["check"] == "Alpaca paper cost"
    assert "Live rule gate" in lg.report_lines(tmp_path)[1]
    write(tmp_path, [{"event": "sell", "measured_side_cost": "x", "position": "p", "strategy": "us_capit_fast", "at": T0}])
    assert lg.health_items(tmp_path)[0]["level"] in ("green", "yellow")
    assert "Live rule gate" in lg.report_lines(tmp_path)[1]


def test_random_entry_control_line():
    assert "no priced us_capit trades yet" in lg.control_line(None)
    st = {"strategies": {"us_capit": {"verdict": {"stats": {"excess": 0.031, "excess_lo": -0.01, "excess_hi": 0.07, "excess_n": 9}}}}}
    assert "+3.10%/trade [-1.00, +7.00] over 9 paper trades" in lg.control_line(st)
