"""Next-candle close forecaster: point prediction, prediction band and direction odds."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..candles import Candle, Tick
from ..scam import WalletTracker
from .engine import FeatureEngine
from .ensemble import Ensemble, default_ensemble
from .features import build_features
from .global_model import BinnedDistribution, GlobalModel
from .predictive import DirectionCalibrator, Mixture, ResidualDistribution, logit, sigmoid
from .volatility import TRADE_DOMAINS, ActivityEstimator, trades_flat_priors

LAST_TRAINED_FRACTION = 0.95  # latest point in a candle the global model is trained on (dataset.FRACTIONS)


@dataclass(frozen=True)
class Forecast:
    """A prediction of a candle's closing price.

    Direction (up/down/flat) is measured against `ref_price`, the previous
    candle's close. `elapsed` is how far into the target candle the forecast was
    made: 0 for the forecast locked in at the candle's open, approaching 1 as the
    live estimate is refreshed toward the close.
    """

    target_start: int
    timeframe: int
    made_at: float
    elapsed: float
    ref_price: float
    last_price: float
    price: float
    low: float
    high: float
    coverage: float
    p_up: float
    p_down: float
    p_flat: float
    sigma: float
    signal: float
    # Probability the forecast itself puts inside [low, high]. Usually above `coverage`:
    # when "no further trade" alone is likelier than `coverage`, the band is just the
    # current price and covers that whole point mass.
    band_mass: float | None = None

    @property
    def target_end(self) -> int:
        return self.target_start + self.timeframe

    @property
    def direction(self) -> str:
        return max((("up", self.p_up), ("down", self.p_down), ("flat", self.p_flat)), key=lambda kv: kv[1])[0]

    @property
    def confidence(self) -> float:
        """Probability the predicted direction is right."""
        return max(self.p_up, self.p_down, self.p_flat)

    @property
    def change(self) -> float:
        return self.price / self.ref_price - 1.0

    def to_dict(self) -> dict:
        return {
            "candle_start": self.target_start,
            "candle_end": self.target_end,
            "made_at": round(self.made_at, 3),
            "elapsed": round(self.elapsed, 4),
            "prev_close": self.ref_price,
            "price_now": self.last_price,
            "predicted_close": self.price,
            "change_pct": round(100 * self.change, 4),
            "direction": self.direction,
            "confidence": round(self.confidence, 4),
            "p_up": round(self.p_up, 4),
            "p_down": round(self.p_down, 4),
            "p_flat": round(self.p_flat, 4),
            "band": {
                "coverage": self.coverage,
                "stated": None if self.band_mass is None else round(self.band_mass, 4),
                "low": self.low,
                "high": self.high,
            },
            "volatility_pct": round(100 * self.sigma, 4),
            "signal_sigma": round(self.signal, 4),
        }


@dataclass(frozen=True)
class Outcome:
    """How a locked-in forecast fared once its candle closed."""

    forecast: Forecast
    actual: float

    @property
    def actual_direction(self) -> str:
        ref = self.forecast.ref_price
        if self.actual > ref:
            return "up"
        return "down" if self.actual < ref else "flat"

    @property
    def hit(self) -> bool:
        return self.forecast.direction == self.actual_direction

    @property
    def in_band(self) -> bool:
        return self.forecast.low * (1 - 1e-9) <= self.actual <= self.forecast.high * (1 + 1e-9)

    @property
    def error(self) -> float:
        """Absolute log error of the predicted close (~ fractional error)."""
        return abs(math.log(self.actual / self.forecast.price))

    @property
    def naive_error(self) -> float:
        """Error of the naive 'close = previous close' prediction."""
        return abs(math.log(self.actual / self.forecast.ref_price))

    def to_dict(self) -> dict:
        f = self.forecast
        return {
            "candle_start": f.target_start,
            "predicted_close": f.price,
            "actual_close": self.actual,
            "prev_close": f.ref_price,
            "error_pct": round(100 * (self.actual / f.price - 1.0), 4),
            "direction": f.direction,
            "confidence": round(f.confidence, 4),
            "actual_direction": self.actual_direction,
            "hit": self.hit,
            "in_band": self.in_band,
            "band": {"coverage": f.coverage, "low": f.low, "high": f.high},
        }


class Forecaster:
    """Learns online from each closed candle and predicts the next close.

    Two predictive distributions are combined:

    * global model (optional): a gradient-boosted distribution trained offline
      across many tokens (see `tartar train`), conditioned on order flow,
      wallets, creator activity, lifecycle and the forming candle so far
    * online model, learned on this token only:
      - volatility: EWMA of range + close-to-close variance
      - signal: ensemble of online experts (random walk, drift, momentum, order
        flow), weighted by how well each has done on this token, then scaled
        by a reliability slope fitted on realized moves
      - uncertainty: empirical distribution of this token's own forecast errors
      - flat odds: chance that nothing trades, pinning the close to the last price

    They are mixed with a weight that follows each one's discounted log score
    on this token, so whichever predicts this token better takes over. The band
    width is tuned online (adaptive conformal inference) to cover the close
    `coverage` of the time, and up/down odds are recalibrated against realized
    directions so stated confidence matches the observed hit rate.
    """

    def __init__(
        self,
        timeframe: int,
        coverage: float = 0.8,
        aci_rate: float = 0.02,
        ensemble: Ensemble | None = None,
        *,
        model: GlobalModel | None = None,
        domain: str = "ohlcv",
        launched_at: float | None = None,
        creator_known: bool = False,
        model_prior: float = 0.95,
    ):
        if not 0.5 <= coverage < 1.0:
            raise ValueError("coverage must be in [0.5, 1)")
        self.timeframe = timeframe
        self.coverage = coverage
        self.engine = FeatureEngine(timeframe, launched_at, creator_known, domain=domain)
        self.wallets = WalletTracker(launched_at)
        if domain in TRADE_DOMAINS:
            # Recorded pump.fun launches: a flat candle follows a traded one 37-61% of the time and a
            # flat one 94-98% of the time, depending on the candle length (similar at every age).
            # Graduated PumpSwap pools trade more steadily: 13-15% and 75-90%.
            after_trade, after_flat = trades_flat_priors(timeframe, domain)
            self.activity = ActivityEstimator(prior_flat=after_trade, prior_flat_after_flat=after_flat, prior_weight=4.0)
        else:  # aggregated candles of established pools are rarely flat
            self.activity = ActivityEstimator()
        self.ensemble = ensemble or default_ensemble()
        self.residuals = ResidualDistribution()
        self.calibrator = DirectionCalibrator()
        self.model = model if model is not None and model.compatible(timeframe, domain) else None
        self.locked: Forecast | None = None
        self._aci_rate = aci_rate
        self._alpha = 1.0 - coverage
        self._x = None
        self._preds = None
        self._raw_signal = 0.0
        self._raw_log_odds = 0.0
        # Discounted moments for the reliability slope of the raw ensemble signal.
        self._sxy = 0.0
        self._sxx = 0.0
        self._nrel = 0.0
        # Global-vs-online mixing: prior log-odds plus discounted log-score difference.
        self._prior_logit = logit(model_prior)
        self._score_diff = 0.0
        self._global: BinnedDistribution | None = None
        self._online_mass = 0.0

    @property
    def history(self):
        return self.engine.history

    @property
    def vol(self):
        return self.engine.vol

    @property
    def reliability(self) -> float:
        """Least-squares slope of realized move on the raw signal, shrunk toward 0 while unproven.

        The shrinkage counts candles (10 pseudo-candles at slope 0), and the slope never
        exceeds 1, so a signal fades in only as it earns it and is never amplified.
        """
        if self._sxx <= 0:
            return 0.0
        return min(1.0, max(0.0, self._sxy / self._sxx * self._nrel / (self._nrel + 10.0)))

    @property
    def global_weight(self) -> float:
        return sigmoid(self._prior_logit + self._score_diff) if self.model is not None else 0.0

    def describe(self) -> dict[str, float]:
        """Current weight of each component of the prediction."""
        w = self.global_weight
        weights = {name: (1.0 - w) * v for name, v in self.ensemble.describe().items()}
        if self.model is not None:
            weights = {"global model": w, **weights}
        return weights

    def on_tick(self, tick: Tick) -> None:
        """Every trade, after any candle it closed has been observed (keeps wallet state causal)."""
        self.wallets.update(tick)

    def observe(self, candle: Candle) -> Outcome | None:
        """Ingest a closed candle; score and learn from the forecast made for it."""
        outcome = None
        if self.locked is not None and candle.start == self.locked.target_start:
            outcome = Outcome(self.locked, candle.close)
            self._learn(outcome)
        self.engine.update(candle)
        self.activity.update(candle)
        self.locked = self._lock()
        return outcome

    def nowcast(self, current: Candle | None, now: float) -> Forecast | None:
        """Live estimate of the forming candle's close, given its trading so far."""
        if current is None:
            return None
        f = self.locked
        elapsed = min(max((now - current.start) / self.timeframe, 0.0), 1.0)
        if f is None:
            # No closed candle yet (brand-new token): anchor on this candle's open.
            sigma = self.engine.sigma
            return self._predict(current.start, current.open, current.close, elapsed, current.active, sigma, 0.0, now, trades=current.trades)[0]
        if current.start != f.target_start:
            return f
        gdist, g_mass = self._global, None
        if self.model is not None and self.model.nowcast:
            gdist = self.model.distribution(self.engine.features(current, now, self.wallets.snapshot()))
            g_mass = gdist.p_still
        return self._predict(
            f.target_start, f.ref_price, current.close, elapsed, current.active, f.sigma, f.signal, now, gdist, g_mass,
            trades=current.trades,
        )[0]

    def _learn(self, outcome: Outcome) -> None:
        f = outcome.forecast
        r = math.log(outcome.actual / f.ref_price)
        z = r / f.sigma
        if self._global is not None:
            self._score_diff = 0.98 * self._score_diff + self._log_score_diff(z, f.signal)
        self.ensemble.update(self._x, z, self._preds)
        clipped = min(max(z, -3.0), 3.0)
        self._sxy = 0.995 * self._sxy + self._raw_signal * clipped
        self._sxx = 0.995 * self._sxx + self._raw_signal**2
        self._nrel = 0.995 * self._nrel + 1.0
        if r != 0.0:
            self.residuals.add(z - f.signal)
            self.calibrator.update(self._raw_log_odds, r > 0)
        flat = outcome.actual == f.ref_price
        if flat and f.low <= f.ref_price <= f.high:
            return  # the band could not have missed: no evidence about its width
        miss = 0.0 if outcome.in_band else 1.0
        target = 1.0 - self.coverage
        if not flat:  # the flat share is covered for free, so moves may be missed more often
            target = min(target / max(1.0 - f.p_flat, 1e-9), 1.0)
        self._alpha = min(0.95, max(0.002, self._alpha + self._aci_rate * (target - miss)))

    def _log_score_diff(self, z: float, signal: float) -> float:
        """log p_global(outcome) - log p_online(outcome) for the forecast locked at the open."""
        g, m = self._global, self._online_mass
        if z == 0.0:
            diff = math.log(max(g.p_still, 1e-9)) - math.log(max(m, 1e-9))
        else:
            p_global = (1.0 - g.p_still) * g.cont_pdf(z)
            p_online = (1.0 - m) * self.residuals.pdf(z - signal)
            diff = math.log(max(p_global, 1e-12)) - math.log(max(p_online, 1e-12))
        return min(max(diff, -5.0), 5.0)

    def _lock(self) -> Forecast:
        history = self.engine.history
        last = history[-1]
        sigma = self.engine.sigma
        self._x = build_features(history, sigma)
        self._raw_signal, self._preds = self.ensemble.predict(self._x)
        signal = self._raw_signal * self.reliability
        self._global = self.model.distribution(self.engine.features(risk=self.wallets.snapshot())) if self.model is not None else None
        self._online_mass = self.activity.no_trade_prob(1.0, False)
        start = last.start + self.timeframe
        g_mass = self._global.p_still if self._global is not None else None
        forecast, q_raw = self._predict(start, last.close, last.close, 0.0, False, sigma, signal, float(start), self._global, g_mass)
        self._raw_log_odds = logit(q_raw)
        return forecast

    def _predict(
        self,
        target_start: int,
        ref: float,
        price: float,
        elapsed: float,
        active: bool,
        sigma: float,
        signal: float,
        made_at: float,
        gdist: BinnedDistribution | None = None,
        g_mass: float | None = None,
        trades: int | None = None,
    ) -> tuple[Forecast, float]:
        """Forecast plus the uncalibrated P(up | price moves)."""
        remaining = 1.0 - elapsed
        x0 = math.log(price / ref) / sigma
        scale = math.sqrt(remaining)
        center = x0 + signal * remaining
        online_mass = self.activity.no_trade_prob(remaining, active, trades or 1)
        if g_mass is not None and elapsed > LAST_TRAINED_FRACTION:
            # Beyond the last trained snapshot, the chance of another move shrinks with the time left.
            g_mass = g_mass ** (remaining / (1.0 - LAST_TRAINED_FRACTION))
        if remaining <= 1e-9:
            online_mass, g_mass = 1.0, (None if g_mass is None else 1.0)  # no time left: the close is the price now

        def online_cdf(x: np.ndarray) -> np.ndarray:
            return self.residuals.cdf_many(x - center, scale)

        w = self.global_weight if gdist is not None else 0.0
        if w > 0:
            global_mass = online_mass if g_mass is None else g_mass
            mass = w * global_mass + (1.0 - w) * online_mass

            def cont_cdf(x: np.ndarray) -> np.ndarray:
                g = gdist.cont_cdf((x - x0) / scale) if scale > 1e-6 else (x >= x0).astype(float)
                total = w * (1.0 - global_mass) * g + (1.0 - w) * (1.0 - online_mass) * online_cdf(x)
                return total / max(1.0 - mass, 1e-12)
        else:
            mass, cont_cdf = online_mass, online_cdf

        mix = Mixture(cont_cdf, mass, x0)
        alpha = self._alpha
        q_low, q_mid, q_high = mix.quantiles((alpha / 2, 0.5, 1 - alpha / 2))
        if w > 0:  # point forecast: keep only the share of the median's move that held up on validation
            q_mid = x0 + (1.0 - w + w * self.model.median_shrink(elapsed)) * (q_mid - x0)
        cont_low, cont_high = cont_cdf(np.array([q_low, q_high]))
        band_mass = (1.0 - mass) * float(cont_high - cont_low) + (mass if q_low <= x0 <= q_high else 0.0)

        q_raw = 1.0 - float(cont_cdf(np.array([0.0]))[0])
        q_up = self.calibrator.apply(q_raw, weight=remaining)
        p_up, p_down, p_flat = (1.0 - mass) * q_up, (1.0 - mass) * (1.0 - q_up), 0.0
        if x0 > 0:
            p_up += mass
        elif x0 < 0:
            p_down += mass
        else:
            p_flat = mass

        forecast = Forecast(
            target_start=target_start,
            timeframe=self.timeframe,
            made_at=made_at,
            elapsed=elapsed,
            ref_price=ref,
            last_price=price,
            price=ref * math.exp(sigma * q_mid),
            low=ref * math.exp(sigma * q_low),
            high=ref * math.exp(sigma * q_high),
            coverage=self.coverage,
            p_up=p_up,
            p_down=p_down,
            p_flat=p_flat,
            sigma=sigma,
            signal=signal,
            band_mass=band_mass,
        )
        return forecast, q_raw
