"""Training pipeline: raw logs, dataset building, global model, and train/serve parity."""

import asyncio
import gzip
import json
import math
import random

import numpy as np
import pytest
from websockets.asyncio.server import serve

from tartar.candles import Candle, CandleBook
from tartar.cli import main
from tartar.data.collect import collect_ohlcv
from tartar.data.dataset import _hash_unit, build_dataset, is_late_join, late_join_view, load_ohlcv_tokens, load_trade_tokens
from tartar.data.rawlog import RawWriter, raw_files, read_events
from tartar.data.recorder import Recorder
from tartar.data.simulate import simulate_raw
from tartar.model import Forecaster
from tartar.model.engine import FEATURES, PARTIAL_FEATURES, FeatureEngine
from tartar.model.global_model import (
    N_CLASSES,
    BinnedDistribution,
    GlobalModel,
    batch_cdf,
    batch_quantile,
    find_model,
    z_to_class,
)
from tartar.model.predictive import Mixture
from tartar.model.volatility import ActivityEstimator
from tartar.train import evaluate, train_global

from conftest import gecko_pool, gecko_tokens


@pytest.fixture(scope="module")
def sim_tokens(tmp_path_factory):
    directory = tmp_path_factory.mktemp("sim")
    simulate_raw(directory, 60, seed=5)
    return load_trade_tokens(directory, 60)


@pytest.fixture(scope="module")
def sim_dataset(sim_tokens):
    return build_dataset(sim_tokens, 60, "trades")


@pytest.fixture(scope="module")
def tiny_model(sim_dataset):
    return train_global(sim_dataset, rounds=25, early_stopping=10, num_leaves=15, min_data_in_leaf=20, log=lambda m: None)


def test_simulated_tokens_follow_the_bonding_curve(sim_tokens):
    token = max(sim_tokens, key=lambda t: len(t.ticks))
    ticks = [tick for group in token.ticks.values() for tick, _ in group]
    assert ticks[0].creator and ticks[0].buys == 1
    for tick in ticks:
        # pump.fun spot price is vSol / vTokens with vSol * vTokens fixed
        assert tick.price == pytest.approx(tick.liquidity**2 / (30.0 * 1_073_000_000.0), rel=1e-9)
    assert all(t.simulated for t in sim_tokens)


def test_dataset_rows_and_time_split(sim_dataset):
    ds = sim_dataset
    assert ds.X.shape == (len(ds), len(FEATURES))
    assert set(np.unique(ds.f)) == {0.0, 0.2, 0.4, 0.6, 0.8, 0.95}
    still = ds.label == 0
    assert np.all(ds.z[still] == 0) and np.all(ds.close[still] == ds.price_now[still])
    assert np.all(ds.label == z_to_class(ds.z, ~still))
    train, valid, test = ds.split()
    assert not (train & valid).any() and not (train & test).any() and (train | valid | test).all()
    created = np.array([t.created for t in ds.tokens])
    assert created[ds.token[train]].max() <= created[ds.token[test]].min()
    assert ds.simulated


def test_train_serve_parity(sim_tokens, sim_dataset):
    """Features computed live (candle book + engine, as the agent does) equal the training rows."""
    index, token = max(((i, t) for i, t in enumerate(sim_tokens) if not is_late_join(t)), key=lambda it: len(it[1].ticks))
    rows = np.flatnonzero(sim_dataset.token == index)
    expected = {(round(float(sim_dataset.f[r]), 2), int(round(float(sim_dataset.ref[r]) * 1e15))): sim_dataset.X[r] for r in rows}
    known_creator = _hash_unit(token.mint, "creator") >= 0.3
    launched = token.created if _hash_unit(token.mint, "launch") >= 0.15 else None
    engine = FeatureEngine(60, launched, known_creator)
    book = CandleBook(60, grace=0.0)
    ticks = sorted((tick for group in token.ticks.values() for tick, _ in group), key=lambda t: t.ts)
    checked, i = 0, 0
    for candle in token.candles[1:20]:
        for f in (0.0, 0.2, 0.4, 0.6, 0.8, 0.95):
            cutoff = candle.start + f * 60
            while i < len(ticks) and ticks[i].ts < cutoff:
                for closed in book.add_tick(ticks[i]):
                    engine.update(closed)
                i += 1
            for closed in book.advance(cutoff):
                engine.update(closed)
            if engine.count == 0:
                continue
            live = engine.features(book.view() if f > 0 else None, cutoff)
            key = (f, int(round(engine.history[-1].close * 1e15)))
            if key in expected:
                np.testing.assert_allclose(live.astype(np.float32), expected[key], rtol=1e-5, atol=1e-6, equal_nan=True)
                checked += 1
    assert checked >= 30


def test_late_join_rows_look_like_a_mid_life_watch(sim_tokens, sim_dataset):
    late = [(i, t) for i, t in enumerate(sim_tokens) if is_late_join(t)]
    assert late
    index, token = late[0]
    candles, ticks, k = late_join_view(token, 60)
    assert [c.start for c in candles] == [c.start for c in token.candles]
    assert all(c.trades is None for c in candles[:k]) and all(c.trades is not None for c in candles[k:])
    assert [c.close for c in candles] == [c.close for c in token.candles]
    rows = sim_dataset.X[sim_dataset.token == index]
    names = list(FEATURES)
    assert len(rows) and np.all(rows[:, names.index("creator_known")] == 0)
    wallets_seen = sum(c.new_traders for c in candles)
    assert wallets_seen <= sum(c.new_traders for c in token.candles)


def test_engine_partial_features_and_unknowns():
    engine = FeatureEngine(60, launched_at=None, creator_known=False)
    for i in range(5):
        engine.update(Candle(i * 60, 1.0, 1.1, 0.9, 1.0 + 0.01 * i, volume=2, trades=3, buys=2, sells=1, traders=2, new_traders=1, liquidity=40))
    x = engine.features()
    names = dict(zip(FEATURES, x))
    assert names["f"] == 0 and names["x0"] == 0
    assert math.isnan(names["creator_sell"]) and math.isnan(names["age"])
    assert names["curve_progress"] == pytest.approx((40 - 30) / 85)
    partial = Candle(300, 1.04, 1.2, 1.04, 1.15, volume=1, trades=4, buy_volume=1)
    x = dict(zip(FEATURES, engine.features(partial, 330)))
    assert x["f"] == 0.5 and x["x0"] == pytest.approx(math.log(1.15 / 1.04) / engine.sigma)
    assert x["p_flow_imb"] == 1.0 and x["p_trades"] == pytest.approx(math.log(5))
    assert len(PARTIAL_FEATURES) == 9


def test_vectorized_distribution_matches_scalar():
    rng = np.random.default_rng(0)
    for _ in range(50):
        p = rng.dirichlet(np.ones(N_CLASSES) * rng.uniform(0.2, 3))
        dist = BinnedDistribution(float(p[0]), p[1:], 0.8, 1.3)
        mix = Mixture(dist.cont_cdf, dist.p_still, 0.0)
        for c in rng.normal(0, 3, 4):
            assert batch_cdf(p[None], np.array([c]), 0.8, 1.3)[0] == pytest.approx(float(mix.cdf(np.array([c]))[0]), abs=1e-9)
        for q in (0.05, 0.5, 0.95):
            assert batch_quantile(p[None], q, 0.8, 1.3)[0] == pytest.approx(float(mix.quantiles([q])[0]), abs=1e-6)
        z = rng.normal(0, 2)
        h = 1e-5
        numeric = (dist.cont_cdf(np.array([z + h]))[0] - dist.cont_cdf(np.array([z - h]))[0]) / (2 * h)
        assert dist.cont_pdf(z) == pytest.approx(numeric, rel=1e-3, abs=1e-6)


def test_global_model_save_load_and_blend(tiny_model, sim_dataset, sim_tokens, tmp_path):
    path = tiny_model.save(tmp_path / "trades-60s")
    model = GlobalModel.load(path)
    probs = model.predict_proba(sim_dataset.X[:10])
    assert probs.shape == (10, N_CLASSES) and np.allclose(probs.sum(axis=1), 1)
    np.testing.assert_allclose(probs, tiny_model.predict_proba(sim_dataset.X[:10]), rtol=1e-6)
    assert find_model("trades", 60, tmp_path) is None  # simulated models stay out of live use
    assert find_model("trades", 60, tmp_path, allow_simulated=True) is not None
    assert find_model("ohlcv", 60, tmp_path, allow_simulated=True) is None

    fc = Forecaster(60, model=model, domain="trades", launched_at=sim_tokens[0].created, creator_known=True)
    assert Forecaster(60, model=model, domain="ohlcv").model is None  # wrong domain
    token = max(sim_tokens, key=lambda t: len(t.ticks))
    for candle in token.candles[:30]:
        fc.observe(candle)
        f = fc.locked
        assert f.low <= f.price <= f.high
        assert f.p_up + f.p_down + f.p_flat == pytest.approx(1.0)
    assert 0 < fc.global_weight < 1 and "global model" in fc.describe()
    current = Candle(fc.locked.target_start, fc.locked.ref_price, fc.locked.ref_price * 1.05, fc.locked.ref_price, fc.locked.ref_price * 1.05, volume=1, trades=3)
    live = fc.nowcast(current, fc.locked.target_start + 59.9)
    assert live.direction == "up" and live.confidence > 0.9


def test_evaluate_report(tiny_model, sim_dataset):
    report = evaluate(tiny_model, sim_dataset, replay_tokens=3, log=lambda m: None)
    fractions = [row["f"] for row in report["test_by_fraction"]]
    assert fractions == [0.0, 0.2, 0.4, 0.6, 0.8, 0.95]
    for row in report["test_by_fraction"]:
        assert 0 <= row["hit_rate"] <= 1 and 0 <= row["band_coverage"] <= 1
    live = report["live_at_open"]
    assert live["online_only"]["all"]["n"] == live["global_plus_online"]["all"]["n"] > 0
    assert report["feature_importance"]


def test_activity_zero_inflated():
    sleepy, busy = ActivityEstimator(), ActivityEstimator()
    for i in range(60):
        sleepy.update(Candle(i * 60, 1, 1, 1, 1, volume=1, trades=4) if i % 3 == 0 else Candle.flat(i * 60, 1))
        busy.update(Candle(i * 60, 1, 1, 1, 1, volume=1, trades=50))
    assert 0.5 < sleepy.no_trade_prob(1.0, False) < 0.8
    assert sleepy.no_trade_prob(0.5, False) > sleepy.no_trade_prob(1.0, False)
    assert sleepy.no_trade_prob(0.5, True) < 0.2
    assert busy.no_trade_prob(1.0, False) < 0.01 and busy.no_trade_prob(0.05, True) < 0.1


def test_raw_writer_rotates_and_compresses(tmp_path):
    now = [1_760_000_000.0]
    writer = RawWriter(tmp_path, clock=lambda: now[0])
    writer.write({"e": "session", "t": now[0], "state": "connected"})
    now[0] += 3600
    writer.write({"e": "session", "t": now[0], "state": "stopped"})
    writer.close()
    files = raw_files(tmp_path)
    assert len(files) == 2 and all(f.suffix == ".gz" for f in files)
    with gzip.open(files[0], "rt") as fh:
        assert json.loads(fh.readline())["state"] == "connected"
    assert [e["state"] for e in read_events(files)] == ["connected", "stopped"]


async def test_recorder_against_local_pumpportal(tmp_path):
    received = []
    mints = ["MintAAAApump", "MintBBBBpump"]

    def msg(kind, mint, trader, vsol):
        return {"txType": kind, "mint": mint, "traderPublicKey": trader, "solAmount": 0.5, "tokenAmount": 1e6, "vSolInBondingCurve": vsol, "vTokensInBondingCurve": 32_190_000_000 / vsol, "name": "A", "symbol": "A"}

    async def handler(ws):
        async for raw in ws:
            request = json.loads(raw)
            received.append(request)
            if request["method"] == "subscribeNewToken":
                for mint in mints:
                    await ws.send(json.dumps(msg("create", mint, "dev" + mint, 30.5)))
            elif request["method"] == "subscribeTokenTrade":
                for mint in request["keys"]:
                    if mint == mints[0]:
                        await ws.send(json.dumps(msg("buy", mint, "w1", 31.0)))
                        await ws.send(json.dumps(msg("sell", mint, "w1", 30.8)))
                await ws.send(json.dumps({"txType": "buy", "mint": "UntrackedMint", "traderPublicKey": "x", "solAmount": 1, "tokenAmount": 1}))

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        recorder = Recorder(tmp_path, url=f"ws://127.0.0.1:{port}", api_key="", idle_minutes=0.01, housekeeping=0.05)
        stats = await asyncio.wait_for(recorder.run(duration=1.5), timeout=10)

    assert stats.total_tokens == 2 and stats.trades == 2
    methods = [r["method"] for r in received]
    assert methods[:2] == ["subscribeNewToken", "subscribeMigration"]
    assert {"method": "subscribeTokenTrade", "keys": mints} in received
    assert any(r["method"] == "unsubscribeTokenTrade" for r in received)
    events = list(read_events(raw_files(tmp_path)))
    kinds = [e["e"] for e in events]
    assert kinds.count("create") == 2 and kinds.count("trade") == 2 and kinds.count("track") == 2
    assert "untrack" in kinds and kinds[-1] == "session" and events[-1]["state"] == "stopped"
    assert all(e.get("mint") != "UntrackedMint" for e in events)


async def test_collect_ohlcv_and_ohlcv_dataset(make_apis, tmp_path):
    mint = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
    rng = random.Random(0)
    price, rows = 1.0, []
    for i in range(80):
        nxt = price * math.exp(rng.gauss(0, 0.02))
        rows.append([1_760_000_000 + 60 * i, price, max(price, nxt) * 1.01, min(price, nxt) * 0.99, nxt, 100 + i])
        price = nxt
    routes = {
        "/api/v2/networks/solana/new_pools": {"data": [gecko_pool("POOLX", mint)], "included": gecko_tokens((mint, "MEME", "Meme"))},
        "/api/v2/networks/solana/pools/POOLX/ohlcv/minute": {"data": {"attributes": {"ohlcv_list": rows[::-1]}}},
    }
    gecko, _, _ = make_apis(routes)
    written = await collect_ohlcv(tmp_path, 60, pages=1, gecko=gecko)
    assert written == 1 and (tmp_path / f"{mint}.json").exists()
    tokens = load_ohlcv_tokens(tmp_path, 60)
    assert len(tokens) == 1 and len(tokens[0].candles) == 80
    ds = build_dataset(tokens, 60, "ohlcv")
    assert len(ds) == 79 and set(ds.f) == {0.0}


def test_cli_simulate_and_train(tmp_path):
    raw, models = tmp_path / "raw", tmp_path / "models"
    assert main(["simulate", "--tokens", "40", "--out", str(raw), "--seed", "2"]) == 0
    assert main(["train", "--raw", str(raw), "--rounds", "15", "--replay-tokens", "2", "--out", str(models)]) == 0
    assert (models / "trades-60s.txt").exists() and (models / "trades-60s.report.json").exists()
    meta = json.loads((models / "trades-60s.json").read_text())
    assert meta["simulated"] and meta["nowcast"] and meta["domain"] == "trades"
    with pytest.raises(SystemExit):  # simulated data never lands in the default model directory
        main(["train", "--raw", str(raw), "--rounds", "5"])
