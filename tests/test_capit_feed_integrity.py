"""Diagnostic fidelity at the current CAPIT baseline, not a prescribed owner fix."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "handoff/experiments/capit_feed_integrity.py"
spec = importlib.util.spec_from_file_location("capit_feed_integrity", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def keys(step):
    return [i["key"] for i in step["open_intents"]]


@pytest.mark.parametrize("mode", ("transient_404", "transient_200_empty", "missing_entry_bar"))
def test_restored_data_is_not_reconsidered_after_the_shared_cursor_advances(mode):
    result = probe.scenario(mode)
    first, recovery, original = (result[k] for k in ("first", "recovery", "original_cursor_counterfactual"))
    assert keys(first) == [f"ETH:{probe.SIGNAL_HOUR}"]
    assert first["done_hour_before"] == probe.INITIAL_CURSOR
    assert first["done_hour_after"] == probe.SIGNAL_HOUR
    assert keys(recovery) == []
    assert recovery["done_hour_before"] == probe.SIGNAL_HOUR
    assert recovery["done_hour_after"] == probe.SIGNAL_HOUR + 1
    assert keys(original) == [f"BTC:{probe.SIGNAL_HOUR}", f"ETH:{probe.SIGNAL_HOUR}"]
    assert result["counterfactual_only_signal_keys"] == [f"BTC:{probe.SIGNAL_HOUR}"]
    assert recovery["source_mode"] == original["source_mode"] == "complete"
    assert original["done_hour_before"] == probe.INITIAL_CURSOR
    assert all(s["step_exception"] is None and s["other_intent_count"] == 0 for s in (first, recovery, original))


@pytest.mark.parametrize("mode, expected", (
    ("complete", [f"BTC:{probe.SIGNAL_HOUR}", f"ETH:{probe.SIGNAL_HOUR}"]),
    ("no_signal", []),
    ("intentional_unavailable", [f"ETH:{probe.SIGNAL_HOUR}"]),
))
def test_controls_do_not_label_quiet_or_persistently_unavailable_data_as_a_lost_signal(mode, expected):
    result = probe.scenario(mode)
    assert keys(result["first"]) == keys(result["original_cursor_counterfactual"]) == expected
    assert keys(result["recovery"]) == []
    assert result["counterfactual_only_signal_keys"] == []
    if mode == "intentional_unavailable":
        assert result["recovery"]["source_mode"] == "intentional_unavailable"
        assert all(r["status_code"] == 404 for s in (result["first"], result["recovery"])
                   for r in s["http_requests"] if r["coin"] == "BTC")


def test_source_codes_empty_bodies_and_one_missing_entry_bar_are_distinct():
    complete = probe.scenario("complete")["first"]
    missing = probe.scenario("missing_entry_bar")["first"]
    assert sum(r["wire_rows"] for r in complete["http_requests"] if r["coin"] == "BTC") - 1 == \
        sum(r["wire_rows"] for r in missing["http_requests"] if r["coin"] == "BTC")
    for mode, status in (("transient_404", 404), ("transient_200_empty", 200)):
        btc = [r for r in probe.scenario(mode)["first"]["http_requests"] if r["coin"] == "BTC"]
        assert btc and all(r["status_code"] == status and r["wire_rows"] == 0 for r in btc)
    assert all(r["status_code"] == 200 for r in missing["http_requests"])


def test_real_get_reorders_coinbase_wire_fields_and_retains_exact_ohlcv():
    start = probe.H0 * 3600
    end = start + 5 * probe.cp.G
    http = probe._Http("complete")
    ctx = probe.Context(end, [], {}, {}, http)
    with probe.patch.dict(probe.cp._CACHE, {}, clear=True), probe.patch.object(probe.cp.time, "sleep", lambda _: None):
        actual = probe._strategy()._get(ctx, "BTC", start, end)
    expected = [r for r in probe.bars(crash=True) if start <= r[0] < end]
    assert sorted(actual) == expected
    assert actual[0][1] != actual[0][2] != actual[0][3] != actual[0][4]
    assert len(http.requests) == 1


def test_probe_does_not_create_a_network_client_or_touch_the_bot_book(monkeypatch):
    import httpx

    def forbidden(*args, **kwargs):
        raise AssertionError("network or bot-book filesystem access")

    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "exists", forbidden)
    result = probe.run_probe()
    assert len(result["scenarios"]) == 6
    for scenario in result["scenarios"]:
        for field in ("first", "recovery", "original_cursor_counterfactual"):
            assert scenario[field]["check_agent_items"] == [{
                "check": "Agent", "level": "green",
                "detail": "no halts, no strategy errors, no orphans, no closed twins yet"}]
    assert result["has_named_capit_or_coinbase_coverage_input"] is False
    assert {i["name"] for i in result["health_input_inventory"]} == set(probe.health.INPUTS)


def test_cache_isolation_restores_prior_entries_and_sleep_even_on_error(monkeypatch):
    cache_before = dict(probe.cp._CACHE)
    sentinel = ("synthetic-sentinel", -1, -2)
    original_sleep = probe.cp.time.sleep
    try:
        probe.cp._CACHE[sentinel] = [[123]]
        saved = dict(probe.cp._CACHE)
        probe.scenario("complete")
        assert probe.cp._CACHE == saved
        assert probe.cp.time.sleep is original_sleep

        def fail(*args, **kwargs):
            raise RuntimeError("deliberate probe failure")

        monkeypatch.setattr(probe, "_step", fail)
        with pytest.raises(RuntimeError, match="deliberate probe failure"):
            probe.scenario("complete")
        assert probe.cp._CACHE == saved
        assert probe.cp.time.sleep is original_sleep
    finally:
        probe.cp._CACHE.clear()
        probe.cp._CACHE.update(cache_before)


def test_health_harness_detects_a_constructed_strategy_error():
    result = probe.run_probe()["health_error_detection_control"]
    assert result["constructed_strategy_errors"] == 1
    assert result["check_agent_items"] == [{
        "check": "Agent: strategy errors", "level": "yellow",
        "detail": "us_capit x1 (synthetic diagnostic error)"}]


def test_cli_is_deterministic_and_portable_without_data_fixtures(tmp_path):
    # Mirrors the important CI constraint: code is present; handoff/data is not.
    sparse = tmp_path / "sparse"
    script = sparse / "handoff/experiments/capit_feed_integrity.py"
    script.parent.mkdir(parents=True)
    shutil.copyfile(SCRIPT, script)
    shutil.copytree(REPO / "tartar", sparse / "tartar", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    assert not (sparse / "handoff/data").exists()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("PYTHONPATH", None)
    output = tmp_path / "probe.json"
    command = [sys.executable, str(script), "--output", str(output)]
    first = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    second = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout == output.read_text()
    assert json.loads(first.stdout) == probe.run_probe()
    assert not (sparse / "autotrade").exists()


@pytest.mark.parametrize("component", ("autotrade", "AUTOTRADE", "AutoTrade"))
def test_output_refuses_bot_book_case_aliases_before_any_write(tmp_path, monkeypatch, component):
    # The lowercase directory is real; the case alias resolves to it on this
    # Mac. The write interception makes the same regression meaningful on Linux.
    book = tmp_path / "autotrade"
    book.mkdir()
    attempted_writes = []

    def forbidden_write(path, *args, **kwargs):
        attempted_writes.append(str(path))
        raise AssertionError("output guard allowed a bot-book write attempt")

    monkeypatch.setattr(Path, "write_text", forbidden_write)
    with pytest.raises(SystemExit) as error:
        probe.main(["--output", str(tmp_path / component / "state.json")])
    assert error.value.code == 2
    assert attempted_writes == []
    assert not (book / "state.json").exists()


def test_cli_rejects_unknown_options():
    with pytest.raises(SystemExit) as error:
        probe.main(["--network"])
    assert error.value.code == 2


def test_unknown_scenario_does_not_silently_become_complete():
    with pytest.raises(ValueError, match="unknown diagnostic mode"):
        probe.scenario("typo")
