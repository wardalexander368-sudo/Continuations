"""The PumpSwap global model: loading graduated tokens, train/serve parity, and the agent's switch."""

import asyncio
import json
import math
from pathlib import Path

import numpy as np
import pytest

from tartar.candles import Candle, CandleBook, Tick
from tartar.data.dataset import _hash_unit, build_dataset, load_pumpswap_tokens, load_trade_tokens, swap_tick, tick_from_event
from tartar.feeds.base import Status
from tartar.feeds.pumpswap import PumpSwapFeed, canonical_pool, swap_events_from_logs
from tartar.market import Market, MarketInfo
from tartar.model.engine import FEATURES, FeatureEngine
from tartar.scam import WalletTracker

T0 = 1_800_000_000.0  # a minute boundary
T_GRAD = T0 + 155.0
K = 30.0 * 1_073_000_000.0
DATA = Path(__file__).parent / "data"


def curve_events():
    out = [{"e": "create", "t": T0 + 1, "mint": "M", "creator": "dev", "name": "Moon", "symbol": "MOON", "uri": "", "sol": 1.0, "tok": 3.5e7, "vsol": 31.0, "vtok": K / 31.0, "rsol": 1.0}]
    for i in range(30):
        t = T0 + 2 + 5 * i
        vsol = 31.0 + 1.8 * (i + 1)
        trader = "dev" if i == 7 else f"w{i % 11}"
        out.append({"e": "trade", "t": t, "mint": "M", "side": "s" if i % 6 == 5 else "b", "trader": trader, "sol": 0.4, "tok": 1e6, "vsol": vsol, "vtok": K / vsol, "rsol": vsol - 30.0})
    return out


def swap_events(until=T0 + 900):
    out, tok, sol, i, t = [], 206.9e6, 85.0, 0, T_GRAD + 1
    rng = np.random.default_rng(3)
    while t < until:
        buy = rng.random() < 0.5
        amount = float(rng.uniform(0.05, 2.0))
        dtok = tok * amount / (sol + amount)
        tok, sol = (tok - dtok, sol + amount) if buy else (tok + dtok, max(sol - amount, 1.0))
        out.append({"e": "swap", "t": t, "mint": "M", "pool": "P", "side": "b" if buy else "s", "trader": f"s{i % 17}", "tok": dtok, "sol": amount, "paid": amount * 1.0125, "tok_after": tok, "sol_after": sol})
        t += float(rng.uniform(1.0, 9.0))
        i += 1
    return out


@pytest.fixture
def raw(tmp_path):
    events = [{"e": "session", "t": T0, "state": "connected"}, {"e": "track", "t": T0 + 1, "mint": "M"}] + curve_events()
    events += [{"e": "graduate", "t": T_GRAD, "mint": "M", "pool": "P"}, {"e": "migrate", "t": T_GRAD, "mint": "M"}]
    events += swap_events() + [{"e": "unwatch", "t": T0 + 950, "mint": "M", "pool": "P", "reason": "idle"}, {"e": "session", "t": T0 + 1000, "state": "stopped"}]
    events.sort(key=lambda e: e["t"])
    (tmp_path / "20270115-08.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    return tmp_path


def test_graduated_token_is_curve_history_then_pool_trades(raw):
    (token,) = load_pumpswap_tokens(raw, 60)
    assert token.launch_known and token.graduated == T_GRAD and token.created == T0 + 1
    k = token.first_target - 1
    assert k == 2  # candles at T0 and T0+60 closed before the graduation candle (T0+120)
    assert all(c.trades is None for c in token.candles[:k]) and all(c.trades is not None for c in token.candles[k:])
    assert token.candles[k].start == T0 + 120 and token.candles[k].trades > sum(1 for e in swap_events() if e["t"] < T0 + 180)  # curve + pool trades
    ticks = [t for group in token.ticks.values() for t, _ in group]
    assert ticks and min(t.ts for t in ticks) >= T_GRAD and all(t.liquidity > 50 for t in ticks)  # only pool trades reach the tracker
    assert token.end == T0 + 950 and token.end_reason == "unwatched"
    # the curve loader still sees the same launch, ending at migration
    (curve,) = load_trade_tokens(raw, 60, min_candles=0)
    assert curve.end == T_GRAD and curve.end_reason == "migrated"


def test_rows_start_after_graduation_without_creator(raw):
    tokens = load_pumpswap_tokens(raw, 60)
    ds = build_dataset(tokens, 60, "pumpswap")
    first = tokens[0].candles[tokens[0].first_target].start
    assert len(ds) and ds.time.min() >= first and sorted(set(np.round(ds.f, 2))) == [0.0, 0.2, 0.4, 0.6, 0.8, 0.95]
    assert np.all(ds.X[:, list(FEATURES).index("creator_known")] == 0)  # the agent restarts with the creator unknown


def test_train_serve_parity_after_graduation(raw):
    """Rows equal the features the agent computes after its graduation restart: closed candles
    as history without trade detail, then pool trades into the same candle book and a fresh
    wallet tracker."""
    (token,) = load_pumpswap_tokens(raw, 60)
    ds = build_dataset([token], 60, "pumpswap")
    expected = {(round(float(ds.f[r]), 2), int(round(float(ds.ref[r]) * 1e15))): ds.X[r] for r in range(len(ds))}
    launched = token.created if _hash_unit(token.mint, "launch") >= 0.15 else None
    book = CandleBook(60, grace=0.0)
    closed = []
    for event in curve_events():
        closed += book.add_tick(tick_from_event(event, "dev"))  # the curve model's era
    closed += book.advance(T_GRAD)
    engine = FeatureEngine(60, launched, False, domain="pumpswap")
    tracker = WalletTracker(launched)
    for c in closed:
        engine.update(Candle(c.start, c.open, c.high, c.low, c.close, volume=c.volume, trades=None))
    ticks = [swap_tick(e, "dev") for e in swap_events()]
    checked, i = 0, 0
    for candle in token.candles[token.first_target :]:
        for f in (0.0, 0.2, 0.4, 0.6, 0.8, 0.95):
            cutoff = candle.start + f * 60
            while i < len(ticks) and ticks[i].ts < cutoff:
                for c in book.add_tick(ticks[i]):
                    engine.update(c)
                tracker.update(ticks[i])
                i += 1
            for c in book.advance(cutoff):
                engine.update(c)
            live = engine.features(book.view() if f > 0 else None, cutoff, tracker.snapshot())
            key = (f, int(round(engine.history[-1].close * 1e15)))
            if key in expected:
                np.testing.assert_allclose(live.astype(np.float32), expected[key], rtol=1e-5, atol=1e-6, equal_nan=True)
                checked += 1
    assert checked >= 30


async def test_recorded_swaps_give_the_live_feed_ticks(tmp_path):
    """swap_tick on what the recorder writes equals PumpSwapFeed's tick for the same trade."""
    from tartar.data.recorder import ChainRecorder, _Pool

    tx = json.loads((DATA / "pumpswap_buy.json").read_text())
    (trade,) = [e for e in swap_events_from_logs(tx["logs"]) if hasattr(e, "is_buy")]

    async def stream():
        yield 1.0, "b", [trade], tx["slot"]

    (live,) = [t async for t in PumpSwapFeed(tx["mint"], pool=trade.pool, creator="dev", stream=stream()).events()]
    recorder = ChainRecorder(tmp_path, clock=lambda: 5.0, pumpswap_hours=1)
    written = []
    recorder._emit = written.append
    recorder.pools[trade.pool] = _Pool(tx["mint"], 0.0, 0.0)
    recorder._swap(trade, tx["slot"])
    replayed = swap_tick(written[0], "dev")
    for name in ("price", "volume", "buy_volume", "sell_volume", "buys", "sells", "trader", "creator", "liquidity", "tokens"):
        assert getattr(replayed, name) == pytest.approx(getattr(live, name)), name


async def test_agent_switches_to_the_pumpswap_model_at_graduation():
    from test_review_fixes import ScriptFeed
    from tartar.agent import CandleAgent
    from tartar.clock import SimClock
    from tartar.data.simulate import simulate_raw
    from tartar.train import train_global

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        simulate_raw(tmp, 30, seed=9)
        ds = build_dataset(load_trade_tokens(tmp, 60), 60, "trades")
    curve_model = train_global(ds, rounds=5, early_stopping=3, num_leaves=7, min_data_in_leaf=10, log=lambda m: None)
    pool_model = train_global(ds, rounds=5, early_stopping=3, num_leaves=7, min_data_in_leaf=10, log=lambda m: None)
    pool_model.meta["domain"] = "pumpswap"  # stands in for a model trained with `tartar train --pumpswap`
    clock = SimClock(start=T0, speed=600)
    script = [(T0 + 5 + 10 * i, Tick(T0 + 5 + 10 * i, 1.0 + 0.001 * i, volume=1, buys=1, trader=f"w{i}")) for i in range(18)]
    script += [(T0 + 185, Status("token graduated: following its PumpSwap pool P", "warn", kind="graduated"))]
    script += [(T0 + 190 + 10 * i, Tick(T0 + 190 + 10 * i, 1.2 + 0.001 * i, volume=1, buys=1, trader=f"v{i}", liquidity=90.0)) for i in range(20)]
    agent = CandleAgent(
        Market(MarketInfo("M", "M", "", "SOL", "solana-rpc"), ScriptFeed(clock, script), None, clock), 60,
        model=curve_model, update_interval=0.02, scam_checks=False, after_graduation=lambda: pool_model,
    )  # fmt: skip
    await asyncio.wait_for(agent.run(max_candles=6), timeout=20)
    assert agent.forecaster.model is pool_model and agent._domain == "pumpswap"
    assert agent.live_candles >= 5
