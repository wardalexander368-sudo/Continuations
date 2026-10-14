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


def test_exit_waits_for_its_candle_and_an_unavailable_pair_does_not_raise(tmp_path):
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


def observation_fixture(rows, *, coins=("BTC", "ETH"), done=None, get=None):
    from tartar.autotrade.core import Context
    from tartar.autotrade.observation_coverage import _hour
    from tartar.autotrade.strategies.coinbase_pattern import day

    signal = H0 + 200
    start = day(signal)
    data = {"done_hour": _hour(start) - 1 if done is None else done}
    strategy = CoinbasePattern("us_capit_fast", {"_get": get or (lambda ctx, coin, t0, t1: [r for r in rows if t0 <= r[0] < t1]),
        "rule": "capit", "coins": list(coins), "start": start, "end": "2100-01-01", "delay_bars": 1})
    return strategy, Context((signal + 1) * 3600 + 1260, [], data, {})


def test_complete_quiet_inputs_are_observed_without_signal():
    from tartar.autotrade import observation_coverage as oc

    strategy, ctx = observation_fixture(bars(260, 10000))
    assert strategy.step(ctx) == []
    c = ctx.state["coverage"]
    assert set(r["state"] for r in c["receipts"].values()) == {"observed-no-signal"}
    assert not c["pending"] and oc.summarize(c, ctx.now)["complete"]


@pytest.mark.parametrize("missing, reason", ((H0 + 100, "missing-signal-lookback"), (H0 + 201, "missing-entry-candle")))
def test_each_coin_retains_missing_lookback_or_entry_without_hiding_the_other(missing, reason):
    rows = bars(260, 200)
    deleted = missing * 3600 if reason == "missing-signal-lookback" else missing * 3600

    def get(ctx, coin, t0, t1):
        return [r for r in rows if t0 <= r[0] < t1 and not (coin == "BTC" and r[0] == deleted)]

    strategy, ctx = observation_fixture(rows, done=H0 + 199, get=get)
    assert [it.meta["key"] for it in strategy.step(ctx) if it.kind == "open"] == [f"ETH:{H0 + 200}"]
    c = ctx.state["coverage"]
    gap = c["receipts"][f"BTC:{H0 + 200}"]
    assert gap["state"] == "incomplete" and gap["reason"] == reason
    assert c["receipts"][f"ETH:{H0 + 200}"]["state"] == "signal-intent"
    assert ctx.state["done_hour"] == H0 + 200


def test_gap_recovery_is_persisted_annotation_without_retrospective_intents():
    from tartar.autotrade import observation_coverage as oc

    rows = bars(260, 200)
    missing = True

    def get(ctx, coin, t0, t1):
        return [] if coin == "BTC" and missing else [r for r in rows if t0 <= r[0] < t1]

    strategy, ctx = observation_fixture(rows, done=H0 + 199, get=get)
    assert [it.asset for it in strategy.step(ctx)] == ["ETH"]
    # A restart serializes the separate execution cursor and pending receipts.
    ctx.state = json.loads(json.dumps(ctx.state))
    original = dict(ctx.state["coverage"]["receipts"][f"BTC:{H0 + 200}"])
    missing = False
    assert strategy.step(ctx) == []  # same execution cursor, restored source
    gap = ctx.state["coverage"]["receipts"][f"BTC:{H0 + 200}"]
    assert all(gap[k] == v for k, v in original.items())
    assert gap["recovery"] == {"observed_at": int(ctx.now), "signal": True, "execution": "annotation-only"}
    assert ctx.state["done_hour"] == H0 + 200 and not ctx.state["coverage"]["pending"]
    before = json.dumps(ctx.state, sort_keys=True)
    assert strategy.step(ctx) == [] and json.dumps(ctx.state, sort_keys=True) == before
    summary = oc.summarize(ctx.state["coverage"], ctx.now)
    assert summary["incomplete_coin_hours"] == summary["late_recovered_coin_hours"] == 1
    assert not summary["complete"]


def test_http_404_and_successful_empty_body_have_distinct_receipts(monkeypatch):
    from tartar.autotrade.strategies import coinbase_pattern as cp

    class Response:
        def __init__(self, code):
            self.status_code = code

        def json(self):
            return []

    class Http:
        def __init__(self, code):
            self.code = code

        def get(self, *args, **kwargs):
            return Response(self.code)

    monkeypatch.setattr(cp.time, "sleep", lambda _: None)
    for code, reason in ((404, "http-unavailable"), (200, "empty-response")):
        strategy, ctx = observation_fixture([], coins=("BTC",), done=H0 + 199)
        strategy.get = strategy._get
        ctx.http = Http(code)
        assert strategy.step(ctx) == []
        receipt = ctx.state["coverage"]["receipts"][f"BTC:{H0 + 200}"]
        assert receipt["state"] == "incomplete" and receipt["reason"] == reason
        assert receipt["source"]["http_status"] == code
        assert "delist" not in json.dumps(receipt)


def test_legacy_cursor_is_historically_unknown_and_pruning_retains_the_denominator(monkeypatch):
    from tartar.autotrade import observation_coverage as oc

    strategy, ctx = observation_fixture(bars(260, 10000), done=H0 + 199)
    strategy.step(ctx)
    c = ctx.state["coverage"]
    assert c["legacy_unknown"]["coin_hours"] > 0 and not oc.summarize(c, ctx.now)["complete"]

    strategy, ctx = observation_fixture([], get=lambda *args: [])
    monkeypatch.setattr(oc, "DETAIL_LIMIT", 3)
    strategy.step(ctx)
    c = ctx.state["coverage"]
    summary = oc.summarize(c, ctx.now)
    assert len(c["receipts"]) == 3
    assert c["archived"]["unresolved"] > 0
    assert summary["unresolved_coin_hours"] == summary["expected_coin_hours"] == c["counts"]["incomplete"]
    assert not summary["complete"]


def test_a_fetch_exception_is_isolated_to_its_coin():
    rows = bars(260, 200)

    def get(ctx, coin, t0, t1):
        if coin == "BTC":
            raise TimeoutError("synthetic")
        return [r for r in rows if t0 <= r[0] < t1]

    strategy, ctx = observation_fixture(rows, done=H0 + 199, get=get)
    assert [it.asset for it in strategy.step(ctx)] == ["ETH"]
    assert ctx.state["coverage"]["receipts"][f"BTC:{H0 + 200}"]["reason"] == "fetch-error:TimeoutError"


def test_busy_receipt_is_explicit_and_does_not_claim_a_signal_or_missing_input():
    from types import SimpleNamespace

    strategy, ctx = observation_fixture([], coins=("BTC",), done=H0 + 199)
    ctx.positions = [SimpleNamespace(id="already-open", asset="BTC",
        meta={"signal_hour": H0 + 199, "exit_t": ctx.now + 24 * 3600})]
    assert strategy.step(ctx) == []
    receipt = ctx.state["coverage"]["receipts"][f"BTC:{H0 + 200}"]
    assert receipt["state"] == "busy" and receipt["reason"] == "position-overlap"
    assert not ctx.state["coverage"]["pending"]


def test_volspike_requires_finite_volume_history():
    rows = bars(260, 10000)
    rows[100 * 4][5] = float("nan")
    strategy, ctx = observation_fixture(rows, coins=("BTC",), done=H0 + 199)
    strategy = CoinbasePattern(strategy.name, {**strategy.cfg, "rule": "volspike"})
    assert strategy.step(ctx) == []
    assert ctx.state["coverage"]["receipts"][f"BTC:{H0 + 200}"]["reason"] == "missing-signal-volume"


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
