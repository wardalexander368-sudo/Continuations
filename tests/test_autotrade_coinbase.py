import json

import pytest

from tartar.autotrade.ledger import Ledger
from tartar.autotrade.runner import run_once
from tartar.autotrade.strategies.coinbase_pattern import CoinbasePattern

H0 = 500_000  # an hour index


def bars(n_hours, crash_at):
    """15-minute bars, gently oscillating; a -40% crash through the hour ``crash_at``, flat after."""
    import numpy as np

    noise = np.random.default_rng(0).normal(0, 0.002, n_hours * 4)
    rows = []
    for k in range(n_hours * 4):
        h = k // 4
        base = 100 * (1 + noise[k])
        px = base if h < crash_at else 60.0 if h == crash_at else 63.0
        rows.append([(H0 * 4 + k) * 900, px, px, px, px, 1.0])
    return rows


def test_capit_buys_30_min_after_the_crash_hour_and_sells_24_h_later(tmp_path):
    rows = bars(260, 200)

    def get(ctx, coin, t0, t1):
        return [r for r in rows if t0 <= r[0] < t1]

    (tmp_path / "config.json").write_text(json.dumps({"mode": "dry_live", "strategies": {"c": {"kind": "coinbase_pattern"}}}))
    s = CoinbasePattern("c", {"_get": get, "rule": "capit", "coins": ["BTC"], "start": "2000-01-01", "end": "2100-01-01",
                              "venue_costs": {"alpaca": 0.0039}})
    for h in range(H0 + 190, H0 + 240):
        run_once(tmp_path, now=h * 3600 + 1200, strategies={"c": s})
    (t,) = Ledger(tmp_path).trades()
    assert t.entry_at == (H0 + 201) * 3600 + 1800 and t.entry_price == pytest.approx(63.0)
    assert t.exit_at == t.entry_at + 24 * 3600 and t.meta["venue"] == "coinbase" and t.mode == "paper"
    assert t.net_return == pytest.approx((1 - 0.0062) ** 2 - 1, abs=1e-3)
    assert s.evaluate([t], t.exit_at, {}).decision == "pending"
    v = s.evaluate([t, t], t.exit_at, {})
    assert v.stats["mean_net_alpaca"] == pytest.approx(-2 * 0.0039, abs=1e-6) and "at alpaca" in v.reason
