import importlib.util
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

PATH = Path(__file__).resolve().parents[1] / 'handoff/experiments/edge-hunt/patterns/capit_account_controls.py'
spec = importlib.util.spec_from_file_location('capit_cash_controls', PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def row(i, coin='BTC', h=0, episode=0):
    return dict(cohort_id=i, coin=coin, signal_index=h, episode_id=episode)


def closes(n=100):
    return {c: np.full(n, 100.) for c in m.COINS}


def policy(**kw):
    return m.Policy(fee=0, budget=0, **kw)


def test_received_asset_fees_and_friction_reconcile_cash_once():
    c = closes(); c['BTC'][25] = 200
    p = m.Policy()
    a = m.account(c, [row(0)], {0: 0}, 1, p, trace=True)
    s, f = p.budget - p.fee, p.fee
    q = 100 / (100 * (1 + s)) * (1 - f)
    credit = q * 200 * (1 - s) * (1 - f)
    assert a['events'][0]['cash_usd'] == 1400
    assert a['events'][0]['quantity'] == pytest.approx(q)
    assert a['terminal_cash_usd'] == pytest.approx(1400 + credit)
    assert a['net_pnl_usd'] == pytest.approx(credit - 100)
    assert a['net_pnl_usd'] != pytest.approx(100 * (1 - 2 * p.budget))


def test_exits_release_cash_and_coin_before_tied_entry():
    a = m.account(closes(), [row(0), row(1, h=24)], {0: 0}, 1,
                  policy(cash=100, cap=100), trace=True)
    assert a['executed'] == 2 and not a['rejected']
    assert a['minimum_cash_usd'] == 0 and a['terminal_cash_usd'] == 100
    assert [e['event'] for e in a['events']] == ['entry', 'exit', 'entry', 'exit']


def test_busy_rejection_and_skipped_exit_do_not_create_cash():
    a = m.account(closes(), [row(0), row(1, h=1)], {0: 0}, 1, policy())
    assert a['executed'] == 1 and a['rejected'] == {'coin_busy': 1}
    assert a['terminal_cash_usd'] == 1500


@pytest.mark.parametrize('limits,reason', [({'cash': 150}, 'cash'), ({'cap': 100}, 'open_stake_cap')])
def test_caps_use_fixed_coin_priority_not_cohort_or_outcome(limits, reason):
    a = m.account(closes(), [row(0, 'ETH'), row(1, 'BTC')], {0: 0}, 1, policy(**limits), trace=True)
    assert a['executed'] == 1 and a['rejected'] == {reason: 1}
    assert a['events'][0]['event'] == 'entry' and a['events'][0]['cohort_id'] == 1
    assert a['minimum_cash_usd'] >= 0


def test_net_stop_after_exit_batch_can_overshoot_and_blocks_new_entries():
    c = closes(); c['BTC'][25] = 80; c['ETH'][25] = 50
    rows = [row(0), row(1, 'ETH'), row(2, 'DOGE', h=24)]
    a = m.account(c, rows, {0: 0}, 1, policy(loss_stop=50))
    assert a['net_pnl_usd'] == -70 and a['halt_reason'] == 'cumulative_net_loss'
    assert a['rejected'] == {'halted': 1}


def test_held_position_still_exits_after_halt():
    c = closes(); c['BTC'][25] = 40; c['ETH'][26] = 50
    a = m.account(c, [row(0), row(1, 'ETH', h=1), row(2, 'SOL', h=24)], {0: 0}, 1,
                  policy(loss_stop=50), trace=True)
    assert a['net_pnl_usd'] == -110 and a['executed'] == 2
    assert a['events'][-1]['event'] == 'exit' and a['events'][-1]['at_index'] == 26


def test_completed_signal_days_mean_stop_uses_only_closed_accepted_trades():
    c = closes(); c['BTC'][25] = 90; c['ETH'][49] = 90
    a = m.account(c, [row(0), row(1, 'ETH', h=24), row(2, 'SOL', h=48)], {0: 0}, 1,
                  policy(min_days=2, loss_stop=1000))
    assert a['executed'] == 2 and a['halt_index'] == 49
    assert a['halt_reason'] == 'mean_after_completed_days' and a['rejected'] == {'halted': 1}


def test_joint_episode_support_preserves_both_coin_offsets_and_delays():
    c = closes(60); c['BTC'][15] = np.nan; c['ETH'][16] = np.nan
    s = m.supports(c, [row(0, h=10), row(1, 'ETH', h=10)], window=5)
    assert s[0].tolist() == list(range(-5, 3))
    assert 0 in s[0]


def test_actual_missing_endpoint_is_non_evaluable_not_a_dropped_trade():
    c = closes(60); c['ETH'][36] = np.nan
    with pytest.raises(ValueError, match='zero shift unavailable'):
        m.supports(c, [row(0, h=10), row(1, 'ETH', h=10)], window=5)


def test_shared_sampling_is_deterministic_sorted_and_does_not_wrap_integer_shifts():
    s = {1: np.array([40000]), 0: np.array([-1, 0, 1])}
    e, a = m.sampled_shifts(s, draws=30)
    e2, b = m.sampled_shifts(dict(reversed(list(s.items()))), draws=30)
    assert e == e2 == [0, 1] and np.array_equal(a, b)
    assert set(a[:, 0]).issubset({-1, 0, 1}) and np.all(a[:, 1] == 40000)


@pytest.mark.parametrize('value', [np.nan, np.inf, 0, -1])
def test_invalid_execution_price_fails_instead_of_becoming_zero_return(value):
    c = closes(); c['BTC'][25] = value
    with pytest.raises(ValueError, match='execution price'):
        m.account(c, [row(0)], {0: 0}, 1)


@pytest.mark.parametrize('rows', [[row(0), row(0, 'ETH')], [row(0), row(1)], [row(True)]])
def test_duplicate_or_boolean_cohort_identity_rejected(rows):
    with pytest.raises(ValueError):
        m.account(closes(), rows, {0: 0}, 1)


@pytest.mark.parametrize('kw', [{'fee': True}, {'budget': np.nan}, {'cash': -1}, {'fee': .01, 'budget': .001}])
def test_invalid_account_policy_rejected(kw):
    with pytest.raises(ValueError):
        m.Policy(**kw)


@pytest.mark.parametrize('raw', ['{"fee":0.0025,"fee":0}', '{"x":NaN}', '{"x":Infinity}'])
def test_json_duplicate_or_nonstandard_values_rejected(tmp_path, raw):
    p = tmp_path / 'input.json'; p.write_text(raw)
    with pytest.raises(ValueError):
        m.read_json(p)


def test_all_cash_no_borrowing_when_stake_cannot_be_funded():
    a = m.account(closes(), [row(0)], {0: 0}, 1, policy(cash=50))
    assert a['executed'] == 0 and a['rejected'] == {'cash': 1}
    assert a['net_pnl_usd'] == 0 and a['mean_closed_net_return'] is None


def test_changed_protocol_cli_fails_before_loading_cache(tmp_path, monkeypatch, capsys):
    p = tmp_path / 'protocol.json'; p.write_text(json.dumps({'hold_hours': 23}))
    monkeypatch.setattr(sys, 'argv', ['tool', '--protocol', str(p), '--cache', str(tmp_path / 'none'),
                                    '--cohort', str(tmp_path / 'none2'), '--output', str(tmp_path / 'result')])
    assert m.main() == 2 and 'protocol bytes differ' in capsys.readouterr().err
    assert not (tmp_path / 'result').exists()


def test_changed_cohort_cli_fails_before_loading_cache(tmp_path, monkeypatch, capsys):
    # CI deliberately excludes handoff/data; isolate the cohort guard with local bytes.
    locked = tmp_path / 'protocol.json'; locked.write_bytes(b'{}\n')
    monkeypatch.setattr(m, 'LOCKED_PROTOCOL_SHA256', hashlib.sha256(locked.read_bytes()).hexdigest())
    cohort = tmp_path / 'cohort.json'; cohort.write_text('{"trades":[]}')
    monkeypatch.setattr(sys, 'argv', ['tool', '--protocol', str(locked), '--cache', str(tmp_path / 'none'),
                                    '--cohort', str(cohort), '--output', str(tmp_path / 'result')])
    assert m.main() == 2 and 'cohort bytes differ' in capsys.readouterr().err
    assert not (tmp_path / 'result').exists()


def test_signal_day_stop_uses_candle_start_utc_day_at_midnight_boundary():
    c = closes(); c['BTC'][48] = 90; c['ETH'][49] = 90
    # h23 and h24 are separate candle-start days; h23 becomes known at midnight.
    rows = [row(0, h=23), row(1, 'ETH', h=24), row(2, 'DOGE', h=49)]
    a = m.account(c, rows, {0: 0}, 1, policy(min_days=2, loss_stop=1000))
    assert a['executed'] == 2 and a['halt_index'] == 49
    assert a['halt_reason'] == 'mean_after_completed_days'
    assert a['rejected'] == {'halted': 1}
