"""Per-candle volatility and trading-activity estimates."""

from __future__ import annotations

import math

from ..candles import Candle

_PARKINSON = 1.0 / (4.0 * math.log(2.0))


def prior_sigma(timeframe: int) -> float:
    """Prior per-candle log-volatility for a young Solana token: ~3% per minute, scaled by sqrt(time)."""
    return min(0.03 * math.sqrt(timeframe / 60.0), 1.5)


class VolatilityEstimator:
    """EWMA of per-candle log-return variance.

    Blends the close-to-close return with the Parkinson high/low range estimate,
    which is far more efficient when only a handful of candles exist. Starts from
    a prior that carries `prior_weight` candles' worth of evidence.
    """

    def __init__(self, prior: float, halflife: float = 20.0, prior_weight: float = 3.0, floor: float = 1e-4):
        self._decay = 0.5 ** (1.0 / halflife)
        self._var = prior * prior
        self._weight = prior_weight
        self._floor = floor
        self.count = 0

    @property
    def sigma(self) -> float:
        return max(math.sqrt(self._var), self._floor)

    def update(self, prev_close: float | None, candle: Candle) -> None:
        sample = _PARKINSON * math.log(candle.high / candle.low) ** 2
        if prev_close:
            sample = 0.5 * sample + 0.5 * math.log(candle.close / prev_close) ** 2
        sample = min(sample, 36.0 * max(self._var, self._floor**2))
        self._weight = self._weight * self._decay + 1.0
        self._var += (sample - self._var) / self._weight
        self.count += 1


class ActivityEstimator:
    """How likely the price is to stay exactly where it is (nothing else trades).

    Young tokens alternate between quiet spells and bursts, so arrivals are
    modelled as zero-inflated Poisson: a candle is "asleep" (no trades) with
    probability pi, otherwise trades arrive at rate lambda (the mean count in
    candles that did trade). Without trade counts it falls back on the observed
    share of candles in which nothing traded.
    """

    def __init__(self, halflife: float = 30.0, prior_flat: float = 0.03, prior_weight: float = 4.0):
        self._decay = 0.5 ** (1.0 / halflife)
        self._flat = prior_flat
        self._flat_weight = prior_weight
        self._rate = 0.0
        self._rate_weight = 0.0
        self.counted = 0

    @property
    def flat_rate(self) -> float:
        return self._flat

    def update(self, candle: Candle) -> None:
        self._flat_weight = self._flat_weight * self._decay + 1.0
        self._flat += ((0.0 if candle.active else 1.0) - self._flat) / self._flat_weight
        if candle.trades:
            self._rate_weight = self._rate_weight * self._decay + 1.0
            self._rate += (candle.trades - self._rate) / self._rate_weight
            self.counted += 1

    def no_trade_prob(self, remaining: float, active_so_far: bool) -> float:
        """Probability that nothing trades in the remaining fraction of the candle."""
        remaining = min(max(remaining, 0.0), 1.0)
        if self.counted >= 5:
            lam = self._rate
            quiet_full = math.exp(-lam)
            asleep = min(max((self._flat - quiet_full) / (1.0 - quiet_full), 0.0), 1.0) if quiet_full < 1 else 0.0
            if active_so_far or asleep == 0.0:
                asleep_now = 0.0
            else:  # no trades so far this candle makes "asleep" more likely
                asleep_now = asleep / (asleep + (1.0 - asleep) * math.exp(-lam * (1.0 - remaining)))
            return asleep_now + (1.0 - asleep_now) * math.exp(-lam * remaining)
        if active_so_far:
            return 0.0 if remaining > 0 else 1.0
        return self._flat**remaining
