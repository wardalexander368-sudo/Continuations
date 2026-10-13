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


def test_exit_waits_for_its_candle_and_a_delisted_pair_does_not_raise(tmp_path):
    rows = bars(260, 200)
    cut = (H0 + 225) * 3600  # Coinbase stops publishing after this (the exit candle comes later)

    def get(ctx, coin, t0, t1):
        return [r for r in rows if t0 <= r[0] < min(t1, cut)]

    (tmp_path / "config.json").write_text(json.dumps({"mode": "paper", "strategies": {"c": {"kind": "coinbase_pattern"}}}))
    s = CoinbasePattern("c", {"_get": get, "rule": "capit", "coins": ["BTC"], "start": "2000-01-01", "end": "2100-01-01"})
    for h in range(H0 + 190, H0 + 232):
        run_once(tmp_path, now=h * 3600 + 1200, strategies={"c": s})
    assert not Ledger(tmp_path).trades() and len(Ledger(tmp_path).positions) == 1  # waits, no stale exit
    cut = 10**12
    run_once(tmp_path, now=(H0 + 232) * 3600 + 1200, strategies={"c": s})
    (t,) = Ledger(tmp_path).trades()
    assert t.exit_at == t.entry_at + 24 * 3600

    class R:
        status_code = 404

    class H:
        def get(self, *a, **k):
            return R()

    from tartar.autotrade.core import Context

    gone = CoinbasePattern("g", {"rule": "capit", "coins": ["GONE"]})
    assert gone._get(Context(0, [], {}, {}, H()), "GONE", 0, 900 * 10) == []


def test_delay_bars_1_books_the_entry_at_the_first_run_after_the_signal(tmp_path):
    rows = bars(260, 200)

    def get(ctx, coin, t0, t1):
        return [r for r in rows if t0 <= r[0] < t1]

    (tmp_path / "config.json").write_text(json.dumps({"mode": "dry_live", "strategies": {"c": {"kind": "coinbase_pattern"}}}))
    s = CoinbasePattern("c", {"_get": get, "rule": "capit", "coins": ["BTC"], "start": "2000-01-01", "end": "2100-01-01",
                              "delay_bars": 1})
    run_once(tmp_path, now=(H0 + 190) * 3600 + 1200, strategies={"c": s})
    run_once(tmp_path, now=(H0 + 201) * 3600 + 1260, strategies={"c": s})  # the run at :21 right after the signal hour
    (p,) = Ledger(tmp_path).positions
    assert p.entry_at == (H0 + 201) * 3600 + 900
    for h in range(H0 + 202, H0 + 240):
        run_once(tmp_path, now=h * 3600 + 1260, strategies={"c": s})
    (t,) = Ledger(tmp_path).trades()
    assert t.exit_at == t.entry_at + 24 * 3600 and s.describe()["entry"].startswith("15 min")


def test_a_shadow_line_trades_on_paper_with_its_shadow_flag(tmp_path):
    rows = bars(260, 200)

    def get(ctx, coin, t0, t1):
        return [r for r in rows if t0 <= r[0] < t1]

    (tmp_path / "config.json").write_text(json.dumps({"mode": "dry_live", "strategies": {"c~wide": {"kind": "coinbase_pattern"}}}))
    s = CoinbasePattern("c~wide", {"_get": get, "rule": "capit", "coins": ["AAVE"], "start": "2000-01-01", "end": "2100-01-01",
                                   "shadow": True})
    for h in range(H0 + 190, H0 + 240):
        run_once(tmp_path, now=h * 3600 + 1200, strategies={"c~wide": s})
    (t,) = Ledger(tmp_path).trades()
    assert t.meta["shadow"] is True and t.mode == "paper" and "live" not in t.meta


def test_random_entry_control_is_priced_after_its_window_and_reported_as_excess(tmp_path):
    from tartar.autotrade.strategies.coinbase_pattern import CONTROL

    rows = bars(1000, 500)

    def get(ctx, coin, t0, t1):
        return [r for r in rows if t0 <= r[0] < t1]

    (tmp_path / "config.json").write_text(json.dumps({"mode": "paper", "strategies": {"c": {"kind": "coinbase_pattern"}}}))
    s = CoinbasePattern("c", {"_get": get, "rule": "capit", "coins": ["BTC"], "start": "2000-01-01", "end": "2100-01-01"})
    for h in range(H0 + 490, H0 + 530):
        run_once(tmp_path, now=h * 3600 + 1200, strategies={"c": s})
    data = Ledger(tmp_path).strategy("c")["data"]
    key = f"BTC:{H0 + 500}"
    assert data["control_due"] == {key: ["BTC", H0 + 500]} and "controls" not in data  # window still open
    run_once(tmp_path, now=(H0 + 500 + CONTROL + 26) * 3600 + 1200, strategies={"c": s})
    data = Ledger(tmp_path).strategy("c")["data"]
    assert key not in data["control_due"] and data["controls"][key] < -0.005  # entries just before the crash lost ~37%
    t = next(t for t in Ledger(tmp_path).trades() if t.meta["key"] == key)
    v = s.evaluate([t, t], t.exit_at, data)
    assert v.decision == "pending" and v.stats["excess_n"] == 2
    assert v.stats["excess"] == pytest.approx(t.exit_price / t.entry_price - 1 - data["controls"][key])
    assert "excess over random entries" in v.reason
    assert "excess" not in s.evaluate([t, t], t.exit_at, {}).stats  # no control yet: nothing claimed


def test_cde_book_snapshot_rides_on_fresh_entries_and_exits(tmp_path):
    from tartar.autotrade import cde_book

    rows = bars(260, 200)

    def get(ctx, coin, t0, t1):
        return [r for r in rows if t0 <= r[0] < t1]

    class R:
        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    class Http:
        def get(self, url, params=None):
            if url.endswith("/products"):
                return R({"products": [{"product_id": "BIP-20DEC30-CDE",
                                        "future_product_details": {"contract_root_unit": "BTC", "contract_size": "0.01"}}]})
            return R({"pricebook": {"bids": [{"price": "99.9", "size": "4"}], "asks": [{"price": "100.1", "size": "5"}]}})

    cde_book._PRODUCTS.clear()
    (tmp_path / "config.json").write_text(json.dumps({"mode": "paper", "strategies": {"c": {"kind": "coinbase_pattern"}}}))
    s = CoinbasePattern("c", {"_get": get, "_cde_http": Http(), "cde_book": True, "rule": "capit", "coins": ["BTC"],
                              "start": "2000-01-01", "end": "2100-01-01"})
    for h in range(H0 + 190, H0 + 240):
        run_once(tmp_path, now=h * 3600 + 1200, strategies={"c": s})
    (t,) = Ledger(tmp_path).trades()
    assert t.meta["cde_entry"]["half_spread_bps"] == 10.0 and t.meta["cde_entry"]["contract_usd"] == 1.0
    assert t.meta["cde_exit"]["product"] == "BIP-20DEC30-CDE"
    v = s.evaluate([t, t], t.exit_at, {})
    assert v.stats["cde_sides"] == 4 and "perp half-spread at our fills median 10.0 bp" in v.reason

    class Broken:
        def get(self, *a, **k):
            raise RuntimeError("down")

    cde_book._PRODUCTS.clear()
    assert cde_book.snapshot(Broken(), "BTC") is None  # never raises
