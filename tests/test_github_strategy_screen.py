"""Offline budget, causality, evidence and input-integrity checks for the screen."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from handoff.experiments import github_strategy_screen as screen


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def setup(tmp_path):
    root = tmp_path.resolve()
    sources, cache = root / "sources", root / "cache"
    sources.mkdir()
    cache.mkdir()
    # The pinned file is deliberately executable-looking. It must remain inert.
    method = b"raise RuntimeError('external strategy code must never execute')\n"
    license_body = b"MIT license test fixture; attestation only\n"
    (sources / "method.py").write_bytes(method)
    (sources / "LICENSE").write_bytes(license_body)
    (cache / "BTC.json").write_text(json.dumps({str(h): [10, 1] for h in range(5)}))
    spec = {
        "schema_version": 1, "candidate_id": "fixture-balanced",
        "source": {"repo_url": "https://github.com/example/rebalancer", "commit": "a" * 40,
                   "files": [{"path": "method.py", "sha256": sha(method)}],
                   "license_spdx": "MIT", "license_file": "LICENSE", "license_sha256": sha(license_body)},
        "review": {"reviewer": "offline test", "transcription_checked": True, "license_checked": True,
                   "closed_lane_checked": True, "mechanism_note": "Market-rebalance adaptation; no external execution."},
        "method": {"adapter": screen.ADAPTER, "weights": {"BTC": 0.5}, "interval_bars": 1, "drift_band": 0},
        "protocol": {"capital_usd": 1000, "side_cost_bps": 39, "stress_side_cost_bps": 78,
                     "start_hour": 0, "end_hour": 4, "evidence_class": "explored-history",
                     "planned_at": "2024-01-01T00:00:00Z"},
    }
    spec_path = root / "spec.json"
    spec_path.write_text(json.dumps(spec))
    return root, sources, cache, spec_path, spec


def run_fixture(setup, spec=None):
    root, sources, cache, spec_path, original = setup
    spec_path.write_text(json.dumps(original if spec is None else spec))
    return screen.run(spec_path, cache, sources, root / "attempt")


def model(prices, weights=None, interval=1, cost=0, band=0):
    method = {"adapter": screen.ADAPTER, "weights": weights or {"BTC": 0.5},
              "interval_bars": interval, "drift_band": band}
    hours = sorted(next(iter(prices.values())))
    protocol = {"capital_usd": 1000, "start_hour": hours[0], "end_hour": hours[-1]}
    return method, protocol, cost


def test_constant_prices_have_only_initial_and_terminal_fee_decay():
    prices = {"BTC": {h: 10.0 for h in range(10)}}
    method, protocol, cost = model(prices, {"BTC": 1}, cost=100)
    result, rows, trades = screen.simulate(prices, method, protocol, cost, "strategy")
    assert result["final_cash_usd"] == pytest.approx(1000 * 0.99 / 1.01)
    assert result["modeled_cost_usd"] == pytest.approx(1000 - result["final_cash_usd"])
    assert [t["side"] for t in trades] == ["BUY", "SELL"]
    assert [t["hour"] for t in trades] == [1, 9]
    assert result["max_drawdown_fraction"] == pytest.approx(1 - 0.99 / 1.01)
    assert rows[0]["equity_usd"] == 1000


def test_matched_controls_share_initial_and_terminal_costs_and_inventory():
    prices = {"BTC": {h: 10.0 for h in range(5)}}
    method, protocol, cost = model(prices, cost=39)
    strategy, _, st = screen.simulate(prices, method, protocol, cost, "strategy")
    hold, _, ht = screen.simulate(prices, method, protocol, cost, "buy_and_hold")
    cash, cash_rows, ct = screen.simulate(prices, method, protocol, cost, "cash")
    assert st == ht
    for field in ("initial_capital_usd", "final_cash_usd", "net_usd", "max_drawdown_fraction", "modeled_cost_usd"):
        assert strategy[field] == pytest.approx(hold[field])
    assert strategy["terminal_inventory_usd"] == hold["terminal_inventory_usd"] == 0
    assert cash["net_usd"] == cash["modeled_cost_usd"] == 0
    assert ct == []
    assert all(r["cash_usd"] == 1000 for r in cash_rows)


def test_direction_and_share_quantity_fixed_before_next_hour_price():
    prices = {"BTC": {0: 10, 1: 10, 2: 20, 3: 5, 4: 10}}
    method, protocol, cost = model(prices, interval=2)
    _, rows, trades = screen.simulate(prices, method, protocol, cost, "strategy")
    future = copy.deepcopy(prices)
    future["BTC"][3] = 100
    _, other_rows, other_trades = screen.simulate(future, method, protocol, cost, "strategy")
    first = [t for t in trades if t["signal_hour"] == 2 and t["reason"] == "target_rebalance"]
    second = [t for t in other_trades if t["signal_hour"] == 2 and t["reason"] == "target_rebalance"]
    assert len(first) == len(second) == 1
    assert first[0]["side"] == second[0]["side"] == "SELL"
    assert first[0]["share_quantity"] == second[0]["share_quantity"] == pytest.approx(12.5)
    assert first[0]["hour"] == first[0]["signal_hour"] + 1
    assert rows[:3] == other_rows[:3]
    assert rows[2]["signal_for_next_hour"] is True


def test_initial_order_sizing_is_causal_and_buy_budget_caps_without_borrow():
    prices = {"BTC": {0: 10, 1: 1000, 2: 2, 3: 10}}
    method, protocol, cost = model(prices, cost=200)
    _, rows, trades = screen.simulate(prices, method, protocol, cost, "strategy")
    initial = trades[0]
    assert initial["signal_hour"] == 0 and initial["hour"] == 1
    assert initial["share_quantity"] == pytest.approx(1000 / (1000 * 1.02))
    assert all(r["cash_usd"] >= 0 for r in rows)
    assert all(q >= 0 for row in rows for q in row["shares"].values())


def test_sell_before_buy_and_total_fee_equals_each_traded_notional_once():
    prices = {"AAA": {0: 10, 1: 10, 2: 50, 3: 50, 4: 50},
              "BBB": {0: 10, 1: 10, 2: 5, 3: 5, 4: 5}}
    method, protocol, cost = model(prices, {"AAA": 0.5, "BBB": 0.5}, interval=2, cost=50)
    result, rows, trades = screen.simulate(prices, method, protocol, cost, "strategy")
    rebalance = [t for t in trades if t["signal_hour"] == 2 and t["reason"] == "target_rebalance"]
    assert [t["side"] for t in rebalance] == ["SELL", "BUY"]
    assert result["modeled_cost_usd"] == pytest.approx(sum(t["notional_usd"] * 0.005 for t in trades))
    assert all(r["cash_usd"] >= 0 for r in rows)
    assert all(q == 0 for q in rows[-1]["shares"].values())
    assert result["final_cash_usd"] == rows[-1]["equity_usd"]


def test_drift_gate_uses_signal_close_and_terminal_day_skips_rebalance():
    prices = {"BTC": {0: 10, 1: 10, 2: 11, 3: 11, 4: 11}}
    method, protocol, cost = model(prices, interval=1, band=0.1)
    _, rows, trades = screen.simulate(prices, method, protocol, cost, "strategy")
    assert rows[0]["signal_for_next_hour"] is True
    assert not any(r["signal_for_next_hour"] for r in rows[1:])
    assert not any(t["hour"] == 4 and t["reason"] != "terminal_liquidation" for t in trades)
    assert all(t["hour"] == t["signal_hour"] + 1 for t in trades)


def test_success_is_explored_history_with_no_profit_or_promotion_claim(setup):
    result = run_fixture(setup)
    assert result["status"] == "FAIL_SCREEN"
    assert result["evidence_class"] == "explored-history"
    assert result["validated_profitability"] is result["promotion_authorized"] is False
    assert set(result["scenarios"]) == {"base", "stress"}
    root = setup[0] / "attempt"
    receipt = json.loads((root / "verified-inputs.json").read_text())
    assert receipt["source"]["commit"] == "a" * 40
    assert receipt["input_hashes"]["cache_sha256"]["BTC.json"] == sha((setup[2] / "BTC.json").read_bytes())
    assert receipt["code_sha256"] == sha(Path(screen.__file__).read_bytes())
    for name in ("base", "stress"):
        assert (root / f"equity-{name}.csv").is_file()
        scenario = result["scenarios"][name]
        assert scenario["strategy_minus_buy_and_hold_usd"] == pytest.approx(0)
        assert scenario["accounts"]["strategy"]["net_usd"] < 0


def test_receipts_are_durable_before_simulation_and_runtime_failure_is_retained(setup, monkeypatch):
    def fail(*args, **kwargs):
        root = setup[0] / "attempt"
        assert (root / "attempt.json").exists()
        assert (root / "verified-inputs.json").exists()
        events = [json.loads(r) for r in (root / "attempt-events.jsonl").read_text().splitlines()]
        assert events[-1]["phase"] == "INPUTS_VERIFIED_BEFORE_OUTCOMES"
        assert all(e["outcomes_available"] is False for e in events)
        raise RuntimeError("injected after durable protocol receipt")
    monkeypatch.setattr(screen, "simulate", fail)
    result = run_fixture(setup)
    assert result["status"] == "INCOMPLETE"
    assert result["error_code"] == "RuntimeError"
    assert (setup[0] / "attempt" / "result.json").exists()


@pytest.mark.parametrize("field", ["transcription_checked", "license_checked", "closed_lane_checked"])
def test_missing_review_bit_blocks_before_results(setup, field):
    spec = copy.deepcopy(setup[-1])
    spec["review"][field] = False
    result = run_fixture(setup, spec)
    assert result["status"] == "BLOCKED" and result["error_code"] == "REVIEW_REQUIRED"
    assert not (setup[0] / "attempt" / "equity-base.csv").exists()


@pytest.mark.parametrize("location,value,code", [
    (("source", "license_spdx"), "GPL-3.0", "UNSUPPORTED_LICENSE"),
    (("method", "adapter"), "exec_external_bot", "UNSUPPORTED_ADAPTER"),
    (("protocol", "evidence_class"), "untouched-holdout", "INVALID_EVIDENCE_CLASS"),
    (("protocol", "capital_usd"), True, "INVALID_SPEC"),
    (("protocol", "capital_usd"), 0, "INVALID_SPEC"),
    (("protocol", "side_cost_bps"), -1, "INVALID_SPEC"),
    (("protocol", "stress_side_cost_bps"), 10, "INVALID_SPEC"),
    (("protocol", "start_hour"), 0.0, "INVALID_SPEC"),
    (("protocol", "planned_at"), "2024-01-01T00:00:00", "INVALID_SPEC"),
    (("method", "interval_bars"), 0, "INVALID_SPEC"),
    (("method", "weights"), {"BTC": 0.7, "ETH": 0.4}, "INVALID_SPEC"),
    (("method", "weights"), {"../BTC": 0.5}, "INVALID_SPEC"),
    (("source", "commit"), "shortsha", "INVALID_SPEC"),
])
def test_strict_spec_invalid_fields_block(setup, location, value, code):
    spec = copy.deepcopy(setup[-1])
    spec[location[0]][location[1]] = value
    result = run_fixture(setup, spec)
    assert result["status"] == "BLOCKED"
    assert result["error_code"] == code


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_protocol_fields_block(setup, value):
    spec = copy.deepcopy(setup[-1])
    spec["protocol"]["capital_usd"] = value
    result = run_fixture(setup, spec)
    assert result["status"] == "BLOCKED" and result["error_code"] == "INVALID_JSON"


def test_source_hash_mismatch_is_blocked_without_importing_external_code(setup):
    (setup[1] / "method.py").write_text("raise Exception('malicious modified payload')")
    result = run_fixture(setup)
    assert result["status"] == "BLOCKED" and result["error_code"] == "SOURCE_HASH_MISMATCH"


@pytest.mark.parametrize("path", ["../method.py", "/method.py", "a/../method.py", "a\\method.py", "a//method.py"])
def test_source_traversal_is_blocked(setup, path):
    spec = copy.deepcopy(setup[-1])
    spec["source"]["files"][0]["path"] = path
    result = run_fixture(setup, spec)
    assert result["status"] == "BLOCKED" and result["error_code"] == "UNSAFE_PATH"


def test_source_symlink_is_blocked(setup):
    source = setup[1] / "method.py"
    original = source.read_bytes()
    source.unlink()
    (setup[0] / "other.py").write_bytes(original)
    source.symlink_to(setup[0] / "other.py")
    result = run_fixture(setup)
    assert result["status"] == "BLOCKED" and result["error_code"] == "UNSAFE_PATH"


def test_source_symlink_ancestor_is_blocked(setup):
    root, sources, cache, spec_path, _ = setup
    link = root / "source-link"
    link.symlink_to(root, target_is_directory=True)
    result = screen.run_screen(spec_path, cache, link / "sources", root / "attempt")
    assert result["status"] == "BLOCKED" and result["error_code"] == "UNSAFE_PATH"


def test_missing_price_or_chronological_gap_blocks_without_imputation(setup):
    (setup[2] / "BTC.json").write_text(json.dumps({str(h): [10, 1] for h in (0, 1, 3, 4)}))
    result = run_fixture(setup)
    assert result["status"] == "BLOCKED" and result["error_code"] == "MISSING_PRICE_COVERAGE"
    assert "first [2]" in result["detail"]


@pytest.mark.parametrize("row", [[0, 1], [-2, 1], [10, -1], [10, True], [float("inf"), 1], [10]])
def test_invalid_price_and_volume_block(setup, row):
    (setup[2] / "BTC.json").write_text(json.dumps({str(h): row for h in range(5)}))
    result = run_fixture(setup)
    assert result["status"] == "BLOCKED"


def test_duplicate_cache_hour_blocks(setup):
    (setup[2] / "BTC.json").write_text('{"0": [10, 1], "0": [11, 1]}')
    result = run_fixture(setup)
    assert result["status"] == "BLOCKED" and result["error_code"] == "INVALID_JSON"


def test_noncanonical_epoch_hour_and_missing_selected_asset_block(setup):
    (setup[2] / "BTC.json").write_text('{"00": [10, 1]}')
    result = run_fixture(setup)
    assert result["status"] == "BLOCKED" and result["error_code"] == "INVALID_CACHE"


def test_unknown_spec_field_blocks(setup):
    spec = copy.deepcopy(setup[-1])
    spec["method"]["optimize"] = True
    result = run_fixture(setup, spec)
    assert result["status"] == "BLOCKED" and result["error_code"] == "INVALID_SPEC"


def test_invalid_direct_simulation_cost_is_rejected_without_clamping():
    prices = {"BTC": {h: 10.0 for h in range(5)}}
    method, protocol, _ = model(prices)
    with pytest.raises(screen.ScreenBlocked, match="permitted range"):
        screen.simulate(prices, method, protocol, -1, "strategy")


def test_existing_attempt_never_overwritten(setup):
    run_fixture(setup)
    original = (setup[0] / "attempt" / "attempt-events.jsonl").read_bytes()
    with pytest.raises(FileExistsError):
        screen.run(setup[3], setup[2], setup[1], setup[0] / "attempt")
    assert (setup[0] / "attempt" / "attempt-events.jsonl").read_bytes() == original


def test_positive_base_and_stress_remain_review_only(setup):
    (setup[2] / "BTC.json").write_text(json.dumps({str(h): [p, 1] for h, p in enumerate([10, 10, 20, 20, 10])}))
    spec = copy.deepcopy(setup[-1])
    spec["method"]["interval_bars"] = 2
    result = run_fixture(setup, spec)
    assert result["status"] == "REVIEW_ONLY"
    assert result["validated_profitability"] is result["promotion_authorized"] is False
    assert all(s["strategy_minus_buy_and_hold_usd"] > 0 and s["strategy_minus_cash_usd"] > 0
               for s in result["scenarios"].values())
