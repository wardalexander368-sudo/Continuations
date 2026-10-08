"""Next-candle close forecaster: point prediction, prediction band and direction odds."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from ..candles import Candle
from .ensemble import Ensemble, default_ensemble
from .features import build_features
from .predictive import DirectionCalibrator, Mixture, ResidualDistribution, logit
from .volatility import ActivityEstimator, VolatilityEstimator, prior_sigma


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
            "band": {"coverage": self.coverage, "low": self.low, "high": self.high},
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

    * volatility: EWMA of range + close-to-close variance (scale of everything)
    * signal: ensemble of online experts (random walk, drift, momentum, order
      flow), weighted by how well each has done on this token, then scaled by a
      reliability slope fitted on realized moves (noise-only signals fade to 0)
    * uncertainty: empirical distribution of this token's own forecast errors,
      with a prediction band whose width is tuned online (adaptive conformal
      inference) so that it covers the close `coverage` of the time
    * direction odds: P(up/down) from that distribution, recalibrated against
      realized directions so stated confidence matches the observed hit rate
    * flat odds: chance that nothing trades, which pins the close to the last price
    """

    def __init__(self, timeframe: int, coverage: float = 0.8, aci_rate: float = 0.02, ensemble: Ensemble | None = None):
        if not 0.5 <= coverage < 1.0:
            raise ValueError("coverage must be in [0.5, 1)")
        self.timeframe = timeframe
        self.coverage = coverage
        self.vol = VolatilityEstimator(prior_sigma(timeframe))
        self.activity = ActivityEstimator()
        self.ensemble = ensemble or default_ensemble()
        self.residuals = ResidualDistribution()
        self.calibrator = DirectionCalibrator()
        self.history: deque[Candle] = deque(maxlen=64)
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

    @property
    def reliability(self) -> float:
        """Least-squares slope of realized move on the raw signal, shrunk toward 1 when unproven."""
        prior = 0.5
        return min(1.5, max(0.0, (self._sxy + prior) / (self._sxx + prior)))

    def observe(self, candle: Candle) -> Outcome | None:
        """Ingest a closed candle; score and learn from the forecast made for it."""
        outcome = None
        if self.locked is not None and candle.start == self.locked.target_start:
            outcome = Outcome(self.locked, candle.close)
            self._learn(outcome)
        prev = self.history[-1].close if self.history else None
        self.vol.update(prev, candle)
        self.activity.update(candle)
        self.history.append(candle)
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
            sigma = self.vol.sigma
            return self._predict(current.start, current.open, current.close, elapsed, current.active, sigma, 0.0, now)
        if current.start != f.target_start:
            return f
        return self._predict(f.target_start, f.ref_price, current.close, elapsed, current.active, f.sigma, f.signal, now)

    def _learn(self, outcome: Outcome) -> None:
        f = outcome.forecast
        r = math.log(outcome.actual / f.ref_price)
        z = r / f.sigma
        self.ensemble.update(self._x, z, self._preds)
        clipped = min(max(z, -3.0), 3.0)
        self._sxy = 0.995 * self._sxy + self._raw_signal * clipped
        self._sxx = 0.995 * self._sxx + self._raw_signal**2
        if r != 0.0:
            self.residuals.add(z - f.signal)
            self.calibrator.update(self._raw_log_odds, r > 0)
        miss = 0.0 if outcome.in_band else 1.0
        self._alpha = min(0.95, max(0.002, self._alpha + self._aci_rate * ((1.0 - self.coverage) - miss)))

    def _lock(self) -> Forecast:
        last = self.history[-1]
        sigma = self.vol.sigma
        self._x = build_features(self.history, sigma)
        self._raw_signal, self._preds = self.ensemble.predict(self._x)
        signal = self._raw_signal * self.reliability
        self._raw_log_odds = logit(1.0 - self.residuals.cdf(-signal))
        start = last.start + self.timeframe
        return self._predict(start, last.close, last.close, 0.0, False, sigma, signal, float(start))

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
    ) -> Forecast:
        remaining = 1.0 - elapsed
        x0 = math.log(price / ref) / sigma
        mass = self.activity.no_trade_prob(remaining, active)
        scale = math.sqrt(remaining)
        center = x0 + signal * remaining
        mix = Mixture(lambda x: self.residuals.cdf_many(x - center, scale), mass, x0)
        alpha = self._alpha
        q_low, q_mid, q_high = mix.quantiles((alpha / 2, 0.5, 1 - alpha / 2))

        q_up = self.calibrator.apply(1.0 - self.residuals.cdf(-center, scale), weight=remaining)
        p_up, p_down, p_flat = (1.0 - mass) * q_up, (1.0 - mass) * (1.0 - q_up), 0.0
        if x0 > 0:
            p_up += mass
        elif x0 < 0:
            p_down += mass
        else:
            p_flat = mass

        return Forecast(
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
        )
