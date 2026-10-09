"""The JLP paper test's accounting (handoff/experiments/jlp_paper.py)."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("jlp_paper", Path(__file__).parents[1] / "handoff/experiments/jlp_paper.py")
jp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jp)

DELTA = {"SOL": 0.0187, "ETH": 0.000144, "BTC": 0.000007}   # tokens per JLP (~0.44 / 0.08 / 0.12 of $4.65)


def snap(ts, nav, px, delta=DELTA, spread=0.0, buy=0.0, sell=0.0):
    hl = {a: {"mark": p, "oracle": p, "funding": 0.0, "bid": p * (1 - spread), "ask": p * (1 + spread)} for a, p in px.items()}
    return {"t": jp.utc(ts), "ts": ts, "jlp": {"price": nav, "delta": dict(delta)}, "hl": hl,
            "quote": {"buy_bps": buy, "sell_bps": sell}}


def market(px_by_hour, funding=0.0):
    """px_by_hour: list of (ts, {coin: (open, high, close)})"""
    out = {}
    for a in jp.MAINT:
        candles = [(t, p[a][0], p[a][1], p[a][2]) for t, p in px_by_hour]
        out[a] = (candles, [(t, funding) for t, _ in px_by_hour])
    return out


PX = {"SOL": 110.0, "ETH": 2480.0, "BTC": 82500.0}
BENCH = [(0, 1.0), (10**10, 1.0)]


def flat_market(t0, hours, px=PX, funding=0.0):
    return market([(t0 + 3600 * h, {a: (p, p, p) for a, p in px.items()}) for h in range(hours)], funding)


def test_custody_delta_reads_jupiter_units():
    c = {"aumTokenAmount": "3939177765378536", "aumTokenAmountFormatted": "3939177.77", "owned": "3939177765378536",
         "locked": "474289251899780", "globalShortSizes": "14644402116059", "globalShortAveragePrice": "110673520"}
    d = jp.custody_delta(c, 192535221.0)
    held = (3939177.765378536 - 474289.25189978) / 192535221.0
    assert d == pytest.approx(held + 14644402.116059 / 110.67352 / 192535221.0)


def test_flat_prices_cost_only_the_entry_spread():
    t0 = 1_800_000_000
    snaps = [snap(t0 + 4 * 3600 * k, 4.65, PX, spread=1e-4) for k in range(5)]
    rows, liq = jp.replay(snaps, flat_market(t0, 24), BENCH)
    assert liq is None
    hedge = sum(DELTA[a] * PX[a] for a in PX) / 4.65
    jlp_usd = jp.CAPITAL / (1 + hedge / jp.LEVERAGE)
    cost = jlp_usd / 4.65 * sum(DELTA[a] * PX[a] for a in PX) * (jp.TAKER + 1e-4)
    assert rows[-1]["equity"] == pytest.approx(jp.CAPITAL - cost, rel=1e-9)
    assert rows[0]["margin"] == pytest.approx(rows[0]["notional"] / jp.LEVERAGE, rel=0.01)
    assert [r["event"] for r in rows[1:]] == [""] * 4


def test_hedge_cancels_a_price_move_and_funding_is_received():
    t0 = 1_800_000_000
    up = {a: p * 1.10 for a, p in PX.items()}
    nav_up = 4.65 * (1 + 0.10 * sum(DELTA[a] * PX[a] for a in PX) / 4.65)   # JLP gains its delta's share
    snaps = [snap(t0, 4.65, PX), snap(t0 + 3600, nav_up, up)]
    rate = 1e-5
    m = market([(t0, {a: (p, p, p) for a, p in PX.items()}), (t0 + 3600, {a: (up[a], up[a], up[a]) for a in PX})], rate)
    rows, liq = jp.replay(snaps, m, BENCH)
    shorts = {a: DELTA[a] * rows[0]["jlp"] / 4.65 for a in PX}
    funding = sum(shorts[a] * up[a] * rate for a in PX)   # one funding print inside (t0, t0+3600]
    entry = sum(shorts[a] * PX[a] for a in PX) * jp.TAKER
    assert rows[1]["equity"] == pytest.approx(jp.CAPITAL - entry + funding, rel=1e-9)
    assert "rebalance" not in rows[1]["event"]


def test_a_spike_through_maintenance_liquidates():
    t0 = 1_800_000_000
    spike = {a: (p, p * 1.6, p) for a, p in PX.items()}   # +60% intra-hour on a 3x short
    m = market([(t0 + 3600, spike), (t0 + 7200, {a: (p, p, p) for a, p in PX.items()})])
    rows, liq = jp.replay([snap(t0, 4.65, PX), snap(t0 + 3 * 3600, 4.65, PX)], m, BENCH)
    assert liq == jp.utc(t0 + 3 * 3600)
    assert rows[-1]["event"] == "liquidated"


def test_margin_top_up_sells_jlp():
    t0 = 1_800_000_000
    up = {a: p * 1.25 for a, p in PX.items()}             # shorts lose 25% of notional: below notional / 5
    nav_up = 4.65 * (1 + 0.25 * sum(DELTA[a] * PX[a] for a in PX) / 4.65)
    m = market([(t0, {a: (p, p, p) for a, p in PX.items()}), (t0 + 3600, {a: (up[a], up[a], up[a]) for a in PX})])
    rows, liq = jp.replay([snap(t0, 4.65, PX), snap(t0 + 3600, nav_up, up, sell=20)], m, BENCH)
    assert liq is None
    assert "topup" in rows[1]["event"]
    assert rows[1]["margin"] == pytest.approx(rows[1]["notional"] / jp.LEVERAGE)


def test_daily_excess_and_block_ci():
    rows = [{"t": jp.utc(1_800_000_000 + 86400 * d), "equity": 100 * 1.001 ** d, "bench": 1.0005 ** d} for d in range(30)]
    x = jp.daily_excess(rows)
    assert len(x) == 29
    assert x == pytest.approx(np.full(29, 0.001 - 0.0005))
    lo, hi = jp.block_ci(x)
    assert lo <= x.mean() <= hi
