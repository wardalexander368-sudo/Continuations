import math
import random

import numpy as np

from tartar.backtest import backtest
from tartar.candles import Candle
from tartar.model import Forecaster
from tartar.model.predictive import DirectionCalibrator, Mixture, ResidualDistribution


def make_series(n, phi=0.0, sigma=0.03, seed=0, trades=(5, 40)):
    rng = random.Random(seed)
    price, prev, out = 1e-6, 0.0, []
    for i in range(n):
        r = phi * prev + sigma * rng.gauss(0, 1)
        prev = r
        o, c = price, price * math.exp(r)
        h = max(o, c) * math.exp(abs(rng.gauss(0, sigma / 2)))
        l = min(o, c) * math.exp(-abs(rng.gauss(0, sigma / 2)))
        out.append(Candle(i * 60, o, h, l, c, volume=rng.random() * 10, trades=rng.randint(*trades)))
        price = c
    return out


def test_random_walk_confidence_is_honest():
    board = backtest(make_series(1500, seed=1), 60)
    t = board.history
    assert abs(t.coverage - 0.8) < 0.03
    assert abs(t.hit_rate - t.avg_confidence) < 0.04
    assert t.avg_confidence < 0.54  # no real signal -> no strong claims
    assert t.edge > -0.02


def test_finds_real_structure():
    t = backtest(make_series(1500, phi=0.3, seed=2), 60).history
    assert t.hit_rate > 0.56
    assert t.edge > 0.01
    assert abs(t.coverage - 0.8) < 0.03
    t = backtest(make_series(1500, phi=-0.3, seed=3), 60).history
    assert t.hit_rate > 0.56 and t.edge > 0.02


def test_dead_token_predicts_flat():
    candles = [Candle(0, 1.0, 1.0, 1.0, 1.0, volume=1, trades=1)]
    candles += [Candle.flat(60 * i, 1.0) for i in range(1, 60)]
    f = Forecaster(60)
    for c in candles:
        f.observe(c)
    locked = f.locked
    assert locked.direction == "flat" and locked.confidence > 0.9
    assert locked.price == locked.low == locked.high == 1.0


def test_forecast_shape_and_nowcast_convergence():
    f = Forecaster(60)
    for c in make_series(100, seed=4):
        f.observe(c)
    locked = f.locked
    assert locked.low <= locked.price <= locked.high
    assert math.isclose(locked.p_up + locked.p_down + locked.p_flat, 1.0)
    assert locked.elapsed == 0 and locked.target_start == 100 * 60

    ref = locked.ref_price
    current = Candle(locked.target_start, ref, ref * 1.10, ref, ref * 1.08, volume=1, trades=10)
    early = f.nowcast(current, locked.target_start + 6)
    late = f.nowcast(current, locked.target_start + 59.9)
    end = f.nowcast(current, locked.target_start + 60)
    assert early.p_up > locked.p_up
    assert late.p_up > early.p_up > 0.5
    assert (late.high - late.low) < (early.high - early.low)
    assert math.isclose(end.price, ref * 1.08) and math.isclose(end.low, end.high)
    assert end.direction == "up" and end.confidence > 0.999


def test_first_candle_without_history():
    f = Forecaster(60)
    assert f.locked is None
    current = Candle(0, 2.0, 2.2, 2.0, 2.1, volume=1, trades=3)
    live = f.nowcast(current, 30)
    assert live.ref_price == 2.0 and live.direction == "up"
    assert f.nowcast(None, 30) is None


def test_mixture_point_mass_quantile_is_exact():
    res = ResidualDistribution()
    mix = Mixture(lambda x: res.cdf_many(x - 0.3), mass=0.6, x0=-0.25)
    q = mix.quantiles([0.05, 0.5, 0.95])
    assert q[1] == -0.25
    assert q[0] < -0.25 < q[2]
    assert np.all(np.diff(q) >= 0)


def test_calibrator_fades_uninformative_odds():
    cal = DirectionCalibrator()
    rng = random.Random(0)
    for _ in range(2000):
        cal.update(0.2, rng.random() < 0.5)  # always claims 55% up, outcomes are coin flips
    assert cal.slope < 0.3
    assert abs(cal.apply(0.55) - 0.5) < 0.02
    informative = DirectionCalibrator()
    for _ in range(2000):
        q = rng.uniform(0.3, 0.7)
        informative.update(math.log(q / (1 - q)), rng.random() < q)
    assert 0.7 < informative.slope < 1.3


def test_volume_feature_ignores_other_source_units():
    from tartar.model.features import FEATURES, build_features

    history = [Candle(i * 60, 1, 1, 1, 1, volume=1e6) for i in range(10)]  # USD-scale, no trade counts
    live = [Candle(600 + i * 60, 1, 1, 1, 1, volume=5.0, trades=10) for i in range(5)]  # SOL-scale
    x = build_features(history + live, 0.03)
    assert abs(x[FEATURES.index("volume")]) < 1.0
