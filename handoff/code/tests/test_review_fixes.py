"""Regression tests for defects found in the accuracy review."""

import asyncio
import math

import numpy as np
import pytest

from tartar.candles import Candle, Tick
from tartar.data.dataset import _hash_unit, build_dataset, load_trade_tokens
from tartar.data.rawlog import RawWriter
from tartar.feeds.base import LiveFeed, Status
from tartar.feeds.pumpchain import ChainComplete, ChainTrade, PumpChainFeed, capture_rate
from tartar.feeds.pumpswap import canonical_pool
from tartar.market import Market, MarketInfo, open_market
from tartar.model import Forecaster
from tartar.model.global_model import GlobalModel, find_model
from tartar.model.predictive import Mixture, ResidualDistribution

from conftest import PUMP_MINT, dex_pair, gecko_pool, gecko_tokens

T0 = 1_760_000_000.0


def test_quantiles_follow_a_huge_move():
    res = ResidualDistribution()
    x0 = -300.0  # a rug: price 300 sigmas below the previous close mid-candle
    mix = Mixture(lambda x: res.cdf_many(x - x0, 0.3), mass=0.2, x0=x0)
    lo, mid, hi = mix.quantiles([0.1, 0.5, 0.9])
    assert lo < mid < hi and abs(mid - x0) < 1.0 and lo < x0 < hi


def test_no_time_left_means_no_move():
    fc = Forecaster(60)
    for i in range(10):
        fc.observe(Candle(i * 60, 1.0, 1.02, 0.98, 1.0 + 0.001 * i, volume=1, trades=5))
    ref = fc.locked.ref_price
    quiet = Candle.flat(fc.locked.target_start, ref, 0)
    end = fc.nowcast(quiet, fc.locked.target_start + 60)
    assert end.p_flat == pytest.approx(1.0) and end.direction == "flat"
    assert end.low == end.price == end.high == pytest.approx(ref)


def _raw(directory, events):
    writer = RawWriter(directory, clock=lambda: T0)
    for event in events:
        writer.write(event)
    writer.close()


def _create(mint, t):
    return {"e": "create", "t": t, "mint": mint, "creator": "dev", "name": "A", "symbol": "A", "sol": 1.0, "tok": 3e7, "vsol": 31.0, "vtok": 1.038e9, "rsol": 1.0}


def _trade(mint, t, vsol):
    return {"e": "trade", "t": t, "mint": mint, "side": "b", "trader": f"w{t}", "sol": 0.1, "tok": 3e6, "vsol": vsol, "vtok": 32.19e9 / vsol, "rsol": vsol - 30}


def test_unclean_restart_cuts_the_data(tmp_path):
    events = [{"e": "session", "t": T0, "state": "connected"}, _create("M1", T0 + 1), {"e": "track", "t": T0 + 1, "mint": "M1"}]
    events += [_trade("M1", T0 + 2 + 5 * i, 31.0 + 0.1 * (i + 1)) for i in range(120)]  # 10 minutes of trading
    # The recorder is killed (no "stopped"); two hours later a new session starts.
    events += [{"e": "session", "t": T0 + 7800, "state": "connected"}, {"e": "session", "t": T0 + 8400, "state": "stopped"}]
    _raw(tmp_path, events)
    (token,) = load_trade_tokens(tmp_path, 60)
    assert token.candles[-1].start < T0 + 700  # ends where the data ends, not after a 2h fake quiet spell
    assert sum(not c.active for c in token.candles) <= 1


def test_launches_without_track_are_skipped(tmp_path):
    events = [{"e": "session", "t": T0, "state": "connected"}, _create("M2", T0 + 1)]
    events += [_trade("M2", T0 + 2 + 5 * i, 31.0 + 0.1 * (i + 1)) for i in range(40)]
    events += [{"e": "session", "t": T0 + 600, "state": "stopped"}]
    _raw(tmp_path, events)
    assert load_trade_tokens(tmp_path, 60) == []


def test_capture_rate_is_order_insensitive():
    trades = [(0.1, True, 1.0 + 0.1 * i, 31.0 + 0.1 * i) for i in range(1, 11)]
    assert capture_rate(trades[::-1]) == pytest.approx(0.9)  # only the first trade's predecessor is unseen
    assert capture_rate(trades[::2]) == pytest.approx(0.0)  # every other trade missing


class ScriptFeed(LiveFeed):
    name = "script"

    def __init__(self, clock, script):
        self.clock, self.script = clock, script

    async def events(self):
        for at, event in self.script:
            await self.clock.sleep(at - self.clock.now())
            yield event
        while True:
            await self.clock.sleep(3600)


async def test_outage_candles_are_not_scored():
    from tartar.agent import CandleAgent
    from tartar.clock import SimClock

    clock = SimClock(start=T0, speed=600)
    script = [(T0 + 5 + 10 * i, Tick(T0 + 5 + 10 * i, 1.0 + 0.001 * i, volume=1, buys=1, trader=f"w{i}")) for i in range(18)]
    script += [(T0 + 185, Status("down", "warn", kind="disconnected")), (T0 + 400, Status("up", kind="connected"))]
    script += [(T0 + 425 + 10 * i, Tick(T0 + 425 + 10 * i, 1.1, volume=1, buys=1, trader=f"v{i}")) for i in range(20)]
    agent = CandleAgent(Market(MarketInfo("M", "M", "", "SOL", "script"), ScriptFeed(clock, script), None, clock), 60, update_interval=0.02, scam_checks=False)
    board = await asyncio.wait_for(agent.run(max_candles=10), timeout=20)
    assert agent.unobserved >= 4  # 180..420 overlap the outage
    assert board.live.n + agent.unobserved <= agent.live_candles
    assert board.live.n >= 1  # scoring resumes after the resync
    assert agent.forecaster.engine.count >= 7  # resync replayed the candle history


async def test_graduation_ends_the_chain_feed():
    async def stream():
        yield T0, "s1", [ChainTrade(PUMP_MINT, 0.1, 3e6, True, "w", int(T0), 40.0, 8e8, "dev", 10.0)]
        yield T0 + 1, "s2", [ChainComplete(PUMP_MINT)]
        yield T0 + 2, "s3", [ChainTrade(PUMP_MINT, 0.1, 3e6, True, "x", int(T0), 41.0, 7.8e8, "dev", 11.0)]

    events = [e async for e in PumpChainFeed(PUMP_MINT, stream=stream(), follow=lambda mint, creator: None).events()]
    assert isinstance(events[0], Tick) and events[-1].kind == "graduated" and len(events) == 2


async def test_graduated_pump_token_is_not_put_on_the_curve_feed(make_apis):
    routes = {
        f"/api/v2/networks/solana/tokens/{PUMP_MINT}/pools": {"data": [gecko_pool("SWAP", PUMP_MINT, dex="pumpswap")], "included": gecko_tokens((PUMP_MINT, "M", "M"))},
        f"/tokens/v1/solana/{PUMP_MINT}": 429,
        f"/latest/dex/tokens/{PUMP_MINT}": 429,
    }
    gecko, dex, _ = make_apis(routes)
    market = await open_market(PUMP_MINT, 300, gecko=gecko, dex=dex)
    assert market.info.source == "pumpswap" and market.info.pool == canonical_pool(PUMP_MINT)
    gecko, dex, _ = make_apis({f"/tokens/v1/solana/{PUMP_MINT}": [dex_pair("SWAPPAIR", PUMP_MINT, dex="pumpswap")]})
    market = await open_market(PUMP_MINT, 60, gecko=gecko, dex=dex)
    assert market.info.source == "pumpswap" and market.info.quote == "SOL"
    gecko, dex, _ = make_apis({f"/tokens/v1/solana/{PUMP_MINT}": [dex_pair("RAYPAIR", PUMP_MINT, dex="raydium")]})
    market = await open_market(PUMP_MINT, 60, gecko=gecko, dex=dex)
    assert market.info.source == "dexscreener"  # migrated before PumpSwap existed: no canonical pool


def test_replay_feeds_wallets_like_training(sim_tokens_small):
    tokens, ds = sim_tokens_small
    index, token = max(enumerate(tokens), key=lambda it: len(it[1].ticks))
    known_creator = _hash_unit(token.mint, "creator") >= 0.3
    launched = token.created if _hash_unit(token.mint, "launch") >= 0.15 else None
    from tartar.data.dataset import is_late_join

    if is_late_join(token):
        pytest.skip("busiest token uses the late-join view")
    fc = Forecaster(60, domain="trades", launched_at=launched, creator_known=known_creator)
    rows = {round(float(ds.ref[r]) * 1e15): ds.X[r] for r in np.flatnonzero((ds.token == index) & (ds.f == 0))}
    checked = 0
    for candle in token.candles[:15]:
        for tick, _ in token.ticks.get(candle.start, ()):
            fc.on_tick(tick)
        fc.observe(candle)
        key = round(candle.close * 1e15)
        if key in rows:
            live = fc.engine.features(risk=fc.wallets.snapshot())
            np.testing.assert_allclose(live.astype(np.float32), rows[key], rtol=1e-5, atol=1e-6, equal_nan=True)
            checked += 1
    assert checked >= 5


@pytest.fixture(scope="module")
def sim_tokens_small(tmp_path_factory):
    from tartar.data.simulate import simulate_raw

    directory = tmp_path_factory.mktemp("sim_small")
    simulate_raw(directory, 30, seed=9)
    tokens = load_trade_tokens(directory, 60)
    return tokens, build_dataset(tokens, 60, "trades")


def test_truncated_model_file_is_rejected(sim_tokens_small, tmp_path):
    from tartar.train import train_global

    _, ds = sim_tokens_small
    model = train_global(ds, rounds=5, early_stopping=3, num_leaves=7, min_data_in_leaf=10, log=lambda m: None)
    path = model.save(tmp_path / "trades-60s")
    assert not list(tmp_path.glob("*.tmp"))
    assert find_model("trades", 60, tmp_path, allow_simulated=True) is not None
    path.write_bytes(path.read_bytes()[: len(path.read_bytes()) // 2])  # a half-written file
    with pytest.raises(ValueError):
        GlobalModel.load(path)
    assert find_model("trades", 60, tmp_path, allow_simulated=True) is None


def test_flat_candles_do_not_shrink_volatility():
    from tartar.model.volatility import VolatilityEstimator, prior_sigma

    est = VolatilityEstimator(prior_sigma(60, "trades"))
    for i in range(10):
        est.update(1.0, Candle(i * 60, 1.0, 1.3, 0.8, 1.2, volume=1, trades=3))
    before = est.sigma
    for i in range(10, 60):
        est.update(1.2, Candle.flat(i * 60, 1.2))
    assert est.sigma == before and est.count == 10
    assert prior_sigma(60, "trades") > 5 * prior_sigma(60, "ohlcv")


def test_first_moves_are_not_capped_against_the_prior():
    from tartar.model.volatility import VolatilityEstimator

    est = VolatilityEstimator(0.03)
    est.update(1.0, Candle(0, 1.0, 2.0, 1.0, 2.0, volume=1, trades=3))  # a launch doubling in a minute
    assert est.sigma > 0.2  # capped at 36x the prior variance it would stay under 0.1


def test_activity_follows_the_last_candle():
    from tartar.model.volatility import ActivityEstimator

    act = ActivityEstimator(prior_flat=0.5, prior_weight=1.5)
    for i in range(78):  # bursts: three trading candles, then three quiet ones
        act.update(Candle(i * 60, 1, 1, 1, 1, volume=1, trades=5) if i % 6 < 3 else Candle.flat(i * 60, 1))
    assert act.flat_rate > 0.55  # ended on a quiet candle: quiet spells persist (2/3)
    act.update(Candle(78 * 60, 1, 1, 1, 1, volume=1, trades=5))
    assert act.flat_rate < 0.45  # after a trading candle, trading persists (1/3 flat)


def test_bursty_trades_leave_more_quiet_time():
    from tartar.model.volatility import ActivityEstimator

    steady, bursty = ActivityEstimator(), ActivityEstimator()
    for i in range(60):
        steady.update(Candle(i * 60, 1, 1, 1, 1, volume=1, trades=10))
        bursty.update(Candle(i * 60, 1, 1, 1, 1, volume=1, trades=1 if i % 2 else 19))  # same mean, overdispersed
    assert bursty.no_trade_prob(0.5, True, 1) > 5 * steady.no_trade_prob(0.5, True, 1)
    assert bursty.no_trade_prob(0.5, True, 30) < bursty.no_trade_prob(0.5, True, 1)  # a busy start predicts more


def test_band_control_ignores_flat_closes_it_covered():
    fc = Forecaster(60, domain="trades")
    for i in range(10):
        fc.observe(Candle(i * 60, 1.0, 1.02, 0.98, 1.0 + 0.001 * i, volume=1, trades=5))
    alpha = fc._alpha
    for i in range(10, 40):  # the token goes quiet: every close equals the reference price
        price = fc.locked.ref_price
        assert fc.locked.low <= price <= fc.locked.high
        fc.observe(Candle.flat(i * 60, price))
    assert fc._alpha == alpha


def test_band_states_its_own_probability():
    fc = Forecaster(60, domain="trades")
    for i in range(30):  # a token that trades every other candle
        fc.observe(Candle(i * 60, 1.0, 1.02, 0.98, 1.0 + 0.002 * (i % 3), volume=1, trades=4) if i % 2 else Candle.flat(i * 60, fc.history[-1].close if fc.history else 1.0))
    f = fc.locked
    assert f.band_mass is not None and f.band_mass >= f.coverage - 0.02
    if f.p_flat >= f.coverage:  # the no-move mass alone exceeds 80%: the band is the price itself
        assert f.low == f.high == f.ref_price and f.band_mass == pytest.approx(f.p_flat)
    from tartar.scoreboard import Tally

    t = Tally()
    t.add(fc.observe(Candle.flat(f.target_start, f.ref_price)))
    assert t.to_dict()["band_stated"] == pytest.approx(f.band_mass, abs=1e-4)


def test_flat_priors_follow_the_candle_length():
    from tartar.model.volatility import trades_flat_priors

    short, minute, five = trades_flat_priors(15), trades_flat_priors(60), trades_flat_priors(300)
    assert short[0] < minute[0] < five[0] and short[1] > minute[1] > five[1]
    assert trades_flat_priors(5) == short and trades_flat_priors(3600) == five  # held flat outside the measured range
    assert Forecaster(30, domain="trades").activity.flat_rate == pytest.approx(sum(trades_flat_priors(30)) / 2)



async def test_graduated_token_continues_on_its_pumpswap_pool():
    import json
    from pathlib import Path

    from tartar.feeds.pumpswap import PumpSwapFeed, swap_events_from_logs

    data = Path(__file__).parent / "data"
    buy_tx = json.loads((data / "pumpswap_buy.json").read_text())
    mint = buy_tx["mint"]

    async def curve():
        yield T0, "s1", [ChainTrade(mint, 0.1, 3e6, True, "w", int(T0), 80.0, 4e8, "dev", 50.0)]
        yield T0 + 1, "s2", [ChainComplete(mint)]
        yield T0 + 2, "s3", [ChainTrade(mint, 0.1, 3e6, True, "x", int(T0), 81.0, 3.9e8, "dev", 51.0)]  # never read

    async def pool():
        yield T0 + 3, "p1", swap_events_from_logs(buy_tx["logs"]), 9

    feed = PumpChainFeed(mint, stream=curve(), follow=lambda m, creator: PumpSwapFeed(m, creator=creator, stream=pool()))
    events = [e async for e in feed.events()]
    assert [type(e).__name__ for e in events] == ["Tick", "Status", "Tick"]
    assert events[1].kind == "graduated" and "PumpSwap pool FEmnAsVE" in events[1].message
    assert events[2].price == pytest.approx(137.474161536 / 128879639.516385)
    quoted = PumpChainFeed(mint, stream=_once(ChainComplete(mint, "USDCmint")), follow=lambda m, c: pytest.fail("quote-paired pools are not followed"))
    assert [e.kind for e in [e async for e in quoted.events()]] == ["graduated"]


async def _once(event):
    yield T0, "s", [event]


async def test_agent_drops_the_curve_model_after_graduation(sim_tokens_small, tmp_path):
    from tartar.agent import CandleAgent
    from tartar.clock import SimClock
    from tartar.train import train_global

    _, ds = sim_tokens_small
    model = train_global(ds, rounds=5, early_stopping=3, num_leaves=7, min_data_in_leaf=10, log=lambda m: None)
    clock = SimClock(start=T0, speed=600)
    script = [(T0 + 5 + 10 * i, Tick(T0 + 5 + 10 * i, 1.0 + 0.001 * i, volume=1, buys=1, trader=f"w{i}")) for i in range(18)]
    script += [(T0 + 185, Status("token graduated: following its PumpSwap pool P", "warn", kind="graduated"))]
    script += [(T0 + 190 + 10 * i, Tick(T0 + 190 + 10 * i, 1.2 + 0.001 * i, volume=1, buys=1, trader=f"v{i}")) for i in range(20)]
    info = MarketInfo("M", "M", "", "SOL", "solana-rpc")
    agent = CandleAgent(Market(info, ScriptFeed(clock, script), None, clock), 60, model=model, update_interval=0.02, scam_checks=False)
    await asyncio.wait_for(agent.run(max_candles=6), timeout=20)
    assert agent.forecaster.model is None and agent.live_candles >= 5
