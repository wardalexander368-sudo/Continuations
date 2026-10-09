"""Per-candle volatility and trading-activity estimates."""

from __future__ import annotations

import math

from ..candles import Candle

_PARKINSON = 1.0 / (4.0 * math.log(2.0))


# Data domains read trade by trade: "trades" (pump.fun bonding curves) and "pumpswap" (a graduated
# token's PumpSwap pool). Anything else is aggregated candles ("ohlcv").
TRADE_DOMAINS = ("trades", "pumpswap")


def prior_sigma(timeframe: int, domain: str = "ohlcv") -> float:
    """Prior per-candle log-volatility of a candle that trades.

    Aggregated OHLCV of an established pool: ~3% per minute, scaled by sqrt(time).
    A pump.fun launch watched trade by trade moves far more: one trade on a thin
    curve shifts the price by percents, and recorded launches show a typical
    ~0.28 per traded candle at both 15 s and 60 s, growing only slowly beyond.
    """
    if domain in TRADE_DOMAINS:
        return min(0.25 * max(timeframe / 60.0, 1.0) ** 0.25, 1.5)
    return min(0.03 * math.sqrt(timeframe / 60.0), 1.5)


class VolatilityEstimator:
    """EWMA of per-candle log-return variance.

    Blends the close-to-close return with the Parkinson high/low range estimate,
    which is far more efficient when only a handful of candles exist. Starts from
    a prior that carries `prior_weight` candles' worth of evidence.

    Only candles that traded update it: a candle where nothing traded has no
    range and no return, and counting it as zero variance would shrink the
    scale of the next real move (whether anything trades is modelled separately).
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
        if not candle.active:
            return
        sample = _PARKINSON * math.log(candle.high / candle.low) ** 2
        if prev_close:
            sample = 0.5 * sample + 0.5 * math.log(candle.close / prev_close) ** 2
        if self.count >= 5:  # outlier cap, once the estimate rests on more than the prior
            sample = min(sample, 36.0 * max(self._var, self._floor**2))
        self._weight = self._weight * self._decay + 1.0
        self._var += (sample - self._var) / self._weight
        self.count += 1


# P(flat | previous candle traded), P(flat | previous candle flat) by candle length, measured on
# recorded pump.fun launches (training split, 5,790 launches, 2026-10-09).
_TRADES_FLAT_PRIORS = ((15, 0.372, 0.980), (30, 0.422, 0.974), (60, 0.487, 0.965), (300, 0.610, 0.943))


def trades_flat_priors(timeframe: int) -> tuple[float, float]:
    """Starting flat odds for a pump.fun launch watched trade by trade, interpolated in log time."""
    x = math.log(max(timeframe, 1))
    xs = [math.log(tf) for tf, _, _ in _TRADES_FLAT_PRIORS]

    def interp(values: list[float]) -> float:
        if x <= xs[0]:
            return values[0]
        if x >= xs[-1]:
            return values[-1]
        i = next(k for k in range(1, len(xs)) if x <= xs[k])
        w = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
        return values[i - 1] + w * (values[i] - values[i - 1])

    return interp([a for _, a, _ in _TRADES_FLAT_PRIORS]), interp([b for _, _, b in _TRADES_FLAT_PRIORS])


class ActivityEstimator:
    """How likely the price is to stay exactly where it is (nothing else trades).

    Young tokens alternate between quiet spells and bursts, so whether a candle
    trades at all depends on whether the last one did: the chance of a flat
    candle is tracked separately after a flat candle and after a traded one
    (a two-state Markov chain). Within a candle that trades, arrivals are
    bursty too, so the trade rate is gamma-distributed around its mean (counts
    are negative binomial, dispersion fitted from the observed count variance)
    rather than a fixed Poisson rate. Without trade counts it falls back on the
    flat-candle odds alone.
    """

    def __init__(
        self,
        halflife: float = 25.0,
        prior_flat: float = 0.03,
        prior_weight: float = 4.0,
        prior_flat_after_flat: float | None = None,
    ):
        self._decay = 0.5 ** (1.0 / halflife)
        # P(flat | previous candle traded), P(flat | previous candle flat), each with its evidence weight.
        after_flat = prior_flat if prior_flat_after_flat is None else prior_flat_after_flat
        self._flat = {True: prior_flat, False: after_flat}
        self._flat_weight = {False: prior_weight, True: prior_weight}
        self._last_active: bool | None = None
        self._rate = 0.0
        self._sq = 0.0
        self._rate_weight = 0.0
        self.counted = 0

    @property
    def flat_rate(self) -> float:
        """Chance that the next candle is flat, given how the last one went."""
        if self._last_active is None:
            return 0.5 * (self._flat[False] + self._flat[True])
        return self._flat[self._last_active]

    def update(self, candle: Candle) -> None:
        if self._last_active is not None:
            key = self._last_active
            self._flat_weight[key] = self._flat_weight[key] * self._decay + 1.0
            self._flat[key] += ((0.0 if candle.active else 1.0) - self._flat[key]) / self._flat_weight[key]
        self._last_active = candle.active
        if candle.trades:
            self._rate_weight = self._rate_weight * self._decay + 1.0
            self._rate += (candle.trades - self._rate) / self._rate_weight
            self._sq += (candle.trades**2 - self._sq) / self._rate_weight
            self.counted += 1

    def _gamma(self) -> tuple[float, float]:
        """Shape k and rate b of the gamma-distributed trade rate (per candle) of a candle that trades."""
        m = self._rate
        var = self._sq - m * m
        k = min(max(m * m / (var - m), 0.05), 1e6) if var > m else 1e6
        return k, k / m

    def no_trade_prob(self, remaining: float, active_so_far: bool, trades_so_far: int = 1) -> float:
        """Probability that nothing trades in the remaining fraction of the candle."""
        remaining = min(max(remaining, 0.0), 1.0)
        p_open = self.flat_rate
        if self.counted >= 5:
            k, b = self._gamma()
            elapsed = 1.0 - remaining

            def quiet(t0: float, t: float, shape: float = k) -> float:
                # P(no trade in the next t | none in the first t0), integrated over the rate.
                return math.exp(-shape * math.log1p(t / (b + t0)))

            if active_so_far:  # n trades seen so far: rate posterior is gamma(k + n, b + elapsed)
                return quiet(elapsed, remaining, k + max(trades_so_far, 1))
            quiet_full = quiet(0.0, 1.0)
            asleep = min(max((p_open - quiet_full) / (1.0 - quiet_full), 0.0), 1.0) if quiet_full < 1 else 0.0
            if asleep > 0.0:  # no trades so far this candle makes "asleep" more likely
                asleep = asleep / (asleep + (1.0 - asleep) * quiet(0.0, elapsed))
            return asleep + (1.0 - asleep) * quiet(elapsed, remaining)
        if active_so_far:
            return 0.0 if remaining > 0 else 1.0
        return p_open**remaining
