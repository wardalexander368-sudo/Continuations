"""Train the global model and measure it honestly on tokens launched after the training data."""

from __future__ import annotations

import math
import time
from typing import Callable

import numpy as np

from .data.dataset import Dataset, TokenData, _hash_unit
from .model import Forecaster
from .model.engine import FEATURES
from .model.volatility import TRADE_DOMAINS
from .model.global_model import (
    EDGES,
    N_CLASSES,
    GlobalModel,
    batch_cdf,
    batch_quantile,
)
from .scoreboard import Tally

# Candle-only data (e.g. GeckoTerminal OHLCV) has no trade counts, wallets or creator.
# High/low-based inputs are left out: live candle-only tokens are built from 3s DexScreener
# price polls, whose ranges are about half the true OHLC ranges the model would train on.
OHLCV_FEATURES = (
    "r1", "r2", "r3", "r1_raw", "mom5", "mom15", "log_sigma", "vol_ratio",
    "body", "ema_dev", "ema_trend", "drawdown", "rise",
    "log_volume", "volume_z", "flat_streak", "idle", "age", "n_candles",
)  # fmt: skip


def _softmax(raw: np.ndarray, temperature: float) -> np.ndarray:
    z = raw / temperature
    z = z - z.max(axis=1, keepdims=True)
    p = np.exp(z)
    return p / p.sum(axis=1, keepdims=True)


def _nll(raw: np.ndarray, labels: np.ndarray, weights: np.ndarray, temperature: float) -> float:
    p = _softmax(raw, temperature)[np.arange(len(labels)), labels]
    return float(-(weights * np.log(np.maximum(p, 1e-12))).sum() / weights.sum())


def fit_temperature(raw: np.ndarray, labels: np.ndarray, weights: np.ndarray) -> float:
    """Temperature T minimizing validation log loss of softmax(raw / T) (golden-section search)."""
    lo, hi = math.log(0.5), math.log(4.0)
    g = (math.sqrt(5) - 1) / 2
    a, b = hi - g * (hi - lo), lo + g * (hi - lo)
    fa, fb = _nll(raw, labels, weights, math.exp(a)), _nll(raw, labels, weights, math.exp(b))
    for _ in range(30):
        if fa < fb:
            hi, b, fb = b, a, fa
            a = hi - g * (hi - lo)
            fa = _nll(raw, labels, weights, math.exp(a))
        else:
            lo, a, fa = a, b, fb
            b = lo + g * (hi - lo)
            fb = _nll(raw, labels, weights, math.exp(b))
    return math.exp((lo + hi) / 2)


def train_global(
    ds: Dataset,
    *,
    rounds: int = 3000,
    early_stopping: int = 100,
    learning_rate: float = 0.05,
    num_leaves: int = 63,
    min_data_in_leaf: int = 100,
    threads: int = 0,
    log: Callable[[str], None] = print,
) -> GlobalModel:
    import lightgbm as lgb

    train, valid, _ = ds.split()
    if train.sum() < 100 or valid.sum() < 20:
        raise ValueError(f"not enough data to train: {train.sum()} train / {valid.sum()} validation rows")
    features = list(FEATURES) if ds.domain in TRADE_DOMAINS else list(OHLCV_FEATURES)
    cols = [FEATURES.index(name) for name in features]
    X_train, X_valid = ds.X[train][:, cols], ds.X[valid][:, cols]
    params = {
        "objective": "multiclass",
        "num_class": N_CLASSES,
        "learning_rate": learning_rate,
        "num_leaves": num_leaves,
        "min_data_in_leaf": min_data_in_leaf,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 1.0,
        "num_threads": threads,
        "verbose": -1,
        "seed": 7,
    }
    dtrain = lgb.Dataset(X_train, ds.label[train], weight=ds.weight[train], feature_name=features, free_raw_data=False)
    dvalid = lgb.Dataset(X_valid, ds.label[valid], weight=ds.weight[valid], reference=dtrain)
    started = time.time()
    booster = lgb.train(
        params,
        dtrain,
        num_boost_round=rounds,
        valid_sets=[dvalid],
        valid_names=["valid"],
        callbacks=[
            lgb.early_stopping(early_stopping, verbose=False),
            lgb.log_evaluation(period=100) if log is print else lgb.record_evaluation({}),
        ],
    )
    raw_valid = np.asarray(booster.predict(X_valid, raw_score=True, num_iteration=booster.best_iteration))
    temperature = fit_temperature(raw_valid.reshape(len(X_valid), N_CLASSES), ds.label[valid], ds.weight[valid])

    moved_z = ds.z[train & (ds.label > 0)]
    low, high = moved_z[moved_z < EDGES[0]], moved_z[moved_z > EDGES[-1]]
    meta = {
        "domain": ds.domain,
        "timeframe": ds.timeframe,
        "features": features,
        "edges": EDGES.tolist(),
        "temperature": temperature,
        "tail_low": float(np.mean(EDGES[0] - low)) if len(low) else 1.0,
        "tail_high": float(np.mean(high - EDGES[-1])) if len(high) else 1.0,
        "nowcast": bool(ds.domain in TRADE_DOMAINS and (ds.f > 0).any()),
        "best_iteration": int(booster.best_iteration or booster.current_iteration()),
        "train_rows": int(train.sum()),
        "valid_rows": int(valid.sum()),
        "tokens": len(ds.tokens),
        "simulated": ds.simulated,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "train_seconds": round(time.time() - started, 1),
    }
    model = GlobalModel(booster, meta)
    meta["median_shrink"] = fit_median_shrink(model, ds, valid)
    log(f"trained {meta['best_iteration']} rounds in {meta['train_seconds']}s, temperature {temperature:.3f}")
    return model


def fit_median_shrink(model: GlobalModel, ds: Dataset, mask: np.ndarray) -> list[list[float]]:
    """[[f, s], ...]: how far to move the point forecast from the price now toward the model's
    median, per fraction of the candle elapsed, chosen to minimize absolute error on `mask` (validation).

    Late in a candle the median's small, mostly downward shifts lost to the current price on
    held-out launches, while early on the full median helped; the fitted factor falls with f.
    """
    if not mask.any():
        return []
    probs = model.predict_proba(ds.X[mask])
    tl, th = model.meta.get("tail_low", 1.0), model.meta.get("tail_high", 1.0)
    f, x0, sigma, ref, close, w = ds.f[mask], ds.x0[mask], ds.sigma[mask], ds.ref[mask], ds.close[mask], ds.weight[mask]
    q = batch_quantile(probs, 0.5, tl, th) * np.sqrt(1.0 - f)
    grid = np.linspace(0.0, 1.0, 11)
    out = []
    for frac in sorted(set(f.tolist())):
        m = f == frac
        target = np.log(close[m] / ref[m]) / sigma[m] - x0[m]  # the remaining move, in sigma units
        errors = [float((np.abs(target - s * q[m]) * sigma[m] * w[m]).sum()) for s in grid]
        out.append([frac, float(grid[int(np.argmin(errors))])])
    return out


def evaluate_rows(
    model: GlobalModel, ds: Dataset, mask: np.ndarray, coverage: float = 0.8, baselines: dict[float, np.ndarray] | None = None
) -> list[dict]:
    """Global-model metrics on the masked rows, per fraction of the candle elapsed."""
    probs = model.predict_proba(ds.X[mask])
    tl, th = model.meta.get("tail_low", 1.0), model.meta.get("tail_high", 1.0)
    f, x0, sigma, ref = ds.f[mask], ds.x0[mask], ds.sigma[mask], ds.ref[mask]
    price_now, close, w, labels = ds.price_now[mask], ds.close[mask], ds.weight[mask], ds.label[mask]
    scale = np.sqrt(1.0 - f)
    alpha = 1.0 - coverage

    q_mid, q_low, q_high = (batch_quantile(probs, q, tl, th) for q in (0.5, alpha / 2, 1 - alpha / 2))
    q_mid = q_mid * np.array([model.median_shrink(v) for v in f])

    def price_at(qz: np.ndarray) -> np.ndarray:
        return ref * np.exp(sigma * (x0 + scale * qz))

    pred, low, high = price_at(q_mid), price_at(q_low), price_at(q_high)
    # Probability the model itself puts inside the band. The no-move mass makes it exceed
    # `coverage` whenever "no further trade" alone is likelier than `coverage`.
    band_mass = batch_cdf(probs, q_high, tl, th) - batch_cdf(probs, q_low - 1e-9, tl, th)
    below = batch_cdf(probs, -x0 / np.maximum(scale, 1e-9), tl, th)
    p_up = 1.0 - below
    p_flat = np.where(x0 == 0, probs[:, 0], 0.0)
    p_down = 1.0 - p_up - p_flat
    P = np.stack([p_up, p_down, p_flat], axis=1)
    call = P.argmax(axis=1)
    actual = np.where(close > ref, 0, np.where(close < ref, 1, 2))
    err = np.abs(np.log(close / pred))
    naive = np.abs(np.log(close / price_now))
    in_band = (close >= low * (1 - 1e-9)) & (close <= high * (1 + 1e-9))
    ll = -np.log(np.maximum(probs[np.arange(len(labels)), labels], 1e-12))

    out = []
    for frac in sorted(set(f.tolist())):
        m = f == frac
        wm = w[m]
        avg = lambda v: float((v[m] * wm).sum() / wm.sum())  # noqa: E731
        mae, naive_mae = avg(err), avg(naive)
        row = {
            "f": frac,
            "rows": int(m.sum()),
            "hit_rate": avg((call == actual).astype(float)),
            "avg_confidence": avg(P.max(axis=1)),
            "band_coverage": avg(in_band.astype(float)),
            "band_stated": avg(band_mass),
            "band_width_pct": 100 * avg(np.log(high / low)),
            "mae_pct": 100 * mae,
            "naive_mae_pct": 100 * naive_mae,
            "edge": 1.0 - mae / naive_mae if naive_mae > 0 else None,
            "log_loss": avg(ll),
        }
        if baselines is not None and frac in baselines:
            # Against the label frequencies at this same point of the candle, so knowing f earns nothing.
            base_ll = -np.log(np.maximum(baselines[frac][labels], 1e-12))
            row["info_gain_bits"] = (avg(base_ll) - row["log_loss"]) / math.log(2)
        out.append(row)
    return out


def replay(tokens: list[TokenData], timeframe: int, domain: str, model: GlobalModel | None, coverage: float = 0.8) -> dict[str, Tally]:
    """Run the live forecaster candle by candle.

    Tallies cover all candles, and candles predicted while the token was
    trading (the previous candle had trades), a condition known at prediction
    time, unlike filtering on the outcome.
    """
    all_, trading = Tally(), Tally()
    for token in tokens:
        known_creator = domain == "trades" and _hash_unit(token.mint, "creator") >= 0.3
        launched = token.created if token.launch_known and _hash_unit(token.mint, "launch") >= 0.15 else None
        fc = Forecaster(timeframe, coverage, model=model, domain=domain, launched_at=launched, creator_known=known_creator)
        prev_active = False
        for i, candle in enumerate(token.candles):
            # Live order: a candle's trades reach the wallet tracker before the candle closes.
            for tick, _ in token.ticks.get(candle.start, ()):
                fc.on_tick(tick)
            outcome = fc.observe(candle)
            if outcome is not None and i >= token.first_target:  # PumpSwap tokens: score only after graduation
                all_.add(outcome)
                if prev_active:
                    trading.add(outcome)
            prev_active = candle.active
    return {"all": all_, "trading": trading}


def evaluate(model: GlobalModel, ds: Dataset, *, replay_tokens: int = 300, log: Callable[[str], None] = print) -> dict:
    train, valid, test = ds.split()
    baselines = {}
    for frac in sorted(set(ds.f.tolist())):
        m = train & (ds.f == frac)
        counts = np.bincount(ds.label[m], weights=ds.weight[m], minlength=N_CLASSES) + 0.5
        baselines[frac] = counts / counts.sum()
    captures = [t.capture for t in ds.tokens if t.capture is not None]
    report = {
        "model": model.meta,
        "test_rows": int(test.sum()),
        "data_capture": {
            "tokens_measured": len(captures),
            "median": float(np.median(captures)) if captures else None,
            "mean": float(np.mean(captures)) if captures else None,
            "note": "share of recorded trades whose predecessor was also recorded (1.0 = complete stream)",
        },
        "test_by_fraction": evaluate_rows(model, ds, test, baselines=baselines),
    }
    test_tokens = sorted({int(i) for i in ds.token[test]})
    sample = [ds.tokens[i] for i in test_tokens[:replay_tokens]]
    log(f"replaying the live forecaster on {len(sample)} test tokens…")
    online = replay(sample, ds.timeframe, ds.domain, None)
    blended = replay(sample, ds.timeframe, ds.domain, model)
    report["live_at_open"] = {
        "tokens": len(sample),
        "online_only": {k: v.to_dict() for k, v in online.items()},
        "global_plus_online": {k: v.to_dict() for k, v in blended.items()},
    }
    importance = model.booster.feature_importance("gain")
    names = model.meta["features"]
    order = np.argsort(importance)[::-1]
    total = importance.sum() or 1.0
    report["feature_importance"] = {names[i]: round(float(importance[i] / total), 4) for i in order[:20]}
    return report


def test_log_loss(model: GlobalModel, ds: Dataset) -> float:
    """Weighted log loss on the test split (latest launches): lower is better."""
    _, _, test = ds.split()
    probs = model.predict_proba(ds.X[test])
    labels, w = ds.label[test], ds.weight[test]
    return float(-(w * np.log(np.maximum(probs[np.arange(len(labels)), labels], 1e-12))).sum() / w.sum())
