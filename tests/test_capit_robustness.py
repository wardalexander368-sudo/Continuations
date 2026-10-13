import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

D = Path(__file__).resolve().parents[1] / "handoff/experiments/edge-hunt/patterns"
spec = importlib.util.spec_from_file_location("capit_robustness", D / "capit_robustness.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def trade(coin, hour, gross=0.1, episode=0, expected=0.0):
    return {"coin": coin, "signal_index": hour, "gross_return": gross,
            "episode_id": episode, "expected_control_gross": expected,
            "gross_excess": gross - expected}


def test_missing_endpoint_and_existing_busy_selection():
    close = np.array([100.0, 100, 110, 121, np.nan, 100, 0, np.inf])
    forward = m.forward_gross(close, hold=1)
    assert np.allclose(forward[:2], [0.1, 0.1])
    assert np.isnan(forward[2:]).all()  # never fill missing/zero/infinite endpoints
    # Next accepted signal may start at h+H+1, not h+H or the next calendar day.
    signal = np.ones(8, dtype=bool)
    gross = np.array([0.1, 0.2, 0.3, np.nan, 0.4, 0.5, 0.6, 0.7])
    assert m.accepted_hours(signal, gross, hold=2) == [0, 4, 7]


def test_full_episode_common_shift_intersection_and_subset_support():
    a = np.array([100.0, 100, np.nan, 100, 110, 154, 100, 100])
    b = np.array([100.0, 100, 100, 100, 100, 120, np.nan, 100])
    # A admits shifts 0,+1; B admits -1,0. Independent coin shifts would invent support.
    rows = [trade("A", 2), trade("B", 3, gross=0.2)]
    controlled, episodes = m.matched_controls({"A": a, "B": b}, rows, window=1, hold=1)
    assert episodes[0]["valid_shift_hours"] == [0]
    assert episodes[0]["support_count"] == 1
    assert np.allclose([r["expected_control_gross"] for r in controlled], [0.1, 0.2])
    subset = m.select_universe(controlled, ["A"])
    assert subset[0]["episode_id"] == 0
    assert np.isclose(subset[0]["expected_control_gross"], 0.1)
    standalone, _ = m.matched_controls({"A": a}, [rows[0]], window=1, hold=1)
    assert np.isclose(standalone[0]["expected_control_gross"], 0.25)


def test_shift_pool_includes_zero_and_other_actual_signals():
    close = np.array([100.0, 100, 100, 100, 200, 100, 100, 100])
    rows, episodes = m.matched_controls({"A": close}, [trade("A", 2, gross=1)], window=1, hold=1)
    assert episodes[0]["valid_shift_hours"] == [-1, 0, 1]
    assert np.isclose(rows[0]["expected_control_gross"], (0 + 1 - 0.5) / 3)
    # A negative return remains in the pool; no selecting favourable return magnitudes.


def test_global_episodes_connect_across_days_and_coins_then_keep_ids():
    raw = [trade("B", 144), trade("A", 0), trade("A", 72), trade("B", 217)]
    ordered = m.assign_episodes(raw, gap=72)
    assert [(r["signal_index"], r["episode_id"]) for r in ordered] == [(0, 0), (72, 0), (144, 0), (217, 1)]
    assert [r["episode_id"] for r in m.select_universe(ordered, ["B"])] == [0, 1]


def test_unequal_episode_sizes_use_trade_weighted_bootstrap():
    # Nineteen one-trade zero clusters, one 100-trade +100% cluster.
    values = [0.0] * 19 + [1.0] * 100
    labels = list(range(19)) + [19] * 100
    result = m.episode_bootstrap(values, labels, list(range(20)))
    assert np.isclose(result["mean"], 100 / 119)
    assert result["ci90"][0] == 0
    assert 0.8 < result["ci90"][1] < 1  # equal-weight clusters would instead give about 0.15
    assert result["defined_draws"] == 10000
    assert result["undefined_draws"] == 0


def test_empty_subset_episode_draws_are_reported_not_zero_or_redrawn():
    result = m.episode_bootstrap([0.7], [1], [0, 1])
    assert result["draws_generated"] == 10000
    assert 0 < result["undefined_draws"] < 10000
    assert result["defined_draws"] + result["undefined_draws"] == 10000
    assert np.allclose(result["ci90"], [0.7, 0.7])
    absent = m.episode_bootstrap([], [], [0, 1])
    assert absent["undefined_draws"] == 10000
    assert absent["mean"] is None and absent["ci90"] == [None, None]


def test_leave_one_entire_episode_out_and_cost_excess_cancellation():
    rows = [trade("A", 0, gross=-0.2, episode=0), trade("B", 1, gross=0.1, episode=0),
            trade("A", 80, gross=0.4, episode=1, expected=0.1)]
    a = m.summarize(rows, [0, 1, 2], "synthetic", 0.0039)
    b = m.summarize(rows, [0, 1, 2], "synthetic", 0.0050)
    loo = a["leave_one_episode_out"]
    assert [r["remaining_trades"] for r in loo] == [1, 2, 3]
    assert loo[0]["removed_trades"] == 2 and loo[2]["removed_trades"] == 0
    assert np.isclose(loo[0]["mean_model_net"], 0.4 - 0.0078)
    assert a["weakest_residual"]["mean_model_net"]["omitted_episode_id"] == 1
    assert np.isclose(a["mean_model_net"] - b["mean_model_net"], 0.0022)
    assert a["mean_excess"] == b["mean_excess"]
    assert a["excess_episode_bootstrap"] == b["excess_episode_bootstrap"]
    assert np.isclose(a["realized_model_net_usd"], 100 * (0.3 - 3 * 0.0078))


def test_actual_close_timestamp_concurrency_exits_before_entries():
    # h=0 position exits at close hour26; h=24 enters exactly there, so peak is one.
    assert m.peak_positions([trade("A", 0), trade("B", 24)]) == 1
    assert m.peak_positions([trade("A", 0), trade("B", 23)]) == 2
    assert m.peak_positions([]) == 0


def cache_fixture(tmp_path, full_universe=False):
    cache = tmp_path / "cache"
    cache.mkdir()
    manifest = {"status": "complete", "analysis_ready": True, "start_hour": m.T0,
                "end_hour_exclusive": m.T1, "coins": {}}
    for coin in m.COINS + (m.EXTRA if full_universe else []):
        raw = json.dumps({str(m.T0): [100.0, 10.0]}).encode()
        (cache / f"{coin}.json").write_bytes(raw)
        manifest["coins"][coin] = {"file": f"{coin}.json", "sha256": hashlib.sha256(raw).hexdigest(),
                                  "rows": 1, "missing_hours": m.T1 - m.T0 - 1,
                                  "planned_chunks": 1, "validated_chunks": 1}
    (cache / "manifest.json").write_text(json.dumps(manifest))
    return cache, manifest


def test_validated_cache_preserves_missing_prices_and_manifest_provenance(tmp_path):
    cache, _ = cache_fixture(tmp_path)
    provenance, series = m.load_cache(cache)
    close, volume = series[m.COINS[0]]
    assert close[0] == 100 and volume[0] == 10
    assert np.isnan(close[1:]).all()
    assert len(provenance["manifest_sha256"]) == 64


def test_original_21_cache_validated_but_fixed_11_analysis_only(tmp_path, monkeypatch):
    cache, _ = cache_fixture(tmp_path, full_universe=True)
    _, series = m.load_cache(cache)
    assert set(series) == set(m.COINS + m.EXTRA)
    calls = []

    def fixed_signals(rule, close, volume):
        calls.append(rule)
        signal = np.zeros(len(close), dtype=bool)
        signal[[0, 50]] = True
        return signal

    monkeypatch.setattr(m, "signals", fixed_signals)
    synthetic = {coin: (np.full(100, 100.0), np.full(100, 10.0)) for coin in m.COINS + m.EXTRA}
    result = m.analyze({}, synthetic)
    assert calls == ["capit"] * 11
    assert len(result["trades"]) == 22 and len(result["episodes"]) == 1
    assert len(result["summaries"]) == 4
    assert [s["trades"] for s in result["summaries"]] == [22, 22, 16, 16]
    assert result["trades"][0]["entry_close_hour"] == m.T0 + 2
    assert result["trades"][0]["exit_close_hour"] == m.T0 + 26


@pytest.mark.parametrize("close,volume", [(0, 10), (float("inf"), 10), (100, -1), (True, 10)])
def test_even_correct_hash_cannot_validate_bad_price_volume(tmp_path, close, volume):
    cache, manifest = cache_fixture(tmp_path)
    coin = m.COINS[0]
    raw = json.dumps({str(m.T0): [close, volume]}).encode()
    (cache / f"{coin}.json").write_bytes(raw)
    manifest["coins"][coin]["sha256"] = hashlib.sha256(raw).hexdigest()
    (cache / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="close/volume"):
        m.load_cache(cache)


@pytest.mark.parametrize("damage", ["incomplete", "not_ready", "partial_chunks", "wrong_window",
                                     "missing_coin", "hash", "rows", "missing_hours", "absent"])
def test_cache_damage_cli_fails_without_success_output(tmp_path, damage):
    cache, manifest = cache_fixture(tmp_path)
    coin = m.COINS[0]
    if damage == "incomplete":
        manifest["status"] = "partial"
    elif damage == "not_ready":
        manifest["analysis_ready"] = False
    elif damage == "partial_chunks":
        manifest["coins"][coin]["validated_chunks"] = 0
    elif damage == "wrong_window":
        manifest["start_hour"] += 1
    elif damage == "missing_coin":
        del manifest["coins"][coin]
    elif damage == "hash":
        (cache / f"{coin}.json").write_text("{}")
    elif damage in {"rows", "missing_hours"}:
        manifest["coins"][coin][damage] += 1
    else:
        (cache / f"{coin}.json").unlink()
    (cache / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / "result.json"
    assert m.main(["--cache", str(cache), "--output", str(output)]) != 0
    assert not output.exists()
    assert not (tmp_path / "result.json.tmp").exists()


def test_cli_never_writes_inside_readonly_cache(tmp_path):
    cache, _ = cache_fixture(tmp_path)
    output = cache / "result.json"
    assert m.main(["--cache", str(cache), "--output", str(output)]) != 0
    assert not output.exists()
