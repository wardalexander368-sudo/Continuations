"""Predictive distribution of the next close, in units of per-candle volatility."""

from __future__ import annotations

import math
from collections import deque
from typing import Callable, Sequence

import numpy as np

_ERFC = np.frompyfunc(math.erfc, 1, 1)


def _normal_cdf(u: np.ndarray) -> np.ndarray:
    return 0.5 * _ERFC(-u / math.sqrt(2.0)).astype(float)


class ResidualDistribution:
    """Distribution of forecast errors (normalized), learned online.

    Kernel-smoothed empirical CDF of past residuals, shrunk toward a unit normal
    prior while there are only a few of them. Because it is built from this
    token's own realized errors, stated probabilities track how the model has
    actually been doing. The prior has no cusp at zero (a Laplace prior turned a
    0.18-sigma shift into 61% odds), and the location of a few residuals is
    partly reflected about zero until there are enough of them, so a chance
    sign imbalance does not read as direction.
    """

    def __init__(self, window: int = 400, prior_strength: float = 20.0, bandwidth: float = 0.15, cap: float = 12.0):
        self._res: deque[float] = deque(maxlen=window)
        self._arr: np.ndarray | None = None
        self._k = prior_strength
        self._h = bandwidth
        self._cap = cap

    def __len__(self) -> int:
        return len(self._res)

    def add(self, error: float) -> None:
        self._res.append(min(max(error, -self._cap), self._cap))
        self._arr = None

    def cdf(self, t: float, scale: float = 1.0) -> float:
        """P(scale * error <= t)."""
        return float(self.cdf_many(np.array([t]), scale)[0])

    def cdf_many(self, t: np.ndarray, scale: float = 1.0) -> np.ndarray:
        if scale < 1e-6:
            return (t >= 0).astype(float)
        u = t / scale
        prior = _normal_cdf(u)
        n = len(self._res)
        if n == 0:
            return prior
        if self._arr is None:
            self._arr = np.fromiter(self._res, float, n)
        both = np.concatenate([u, -u])
        smooth = np.mean(0.5 * (1.0 + np.tanh(0.5 * (both[:, None] - self._arr[None, :]) / self._h)), axis=1)
        empirical, mirrored = smooth[: len(u)], 1.0 - smooth[len(u) :]
        ws = self._k / (n + self._k)
        empirical = ws * 0.5 * (empirical + mirrored) + (1.0 - ws) * empirical
        w = n / (n + self._k)
        return w * empirical + (1.0 - w) * prior

    def pdf(self, t: float) -> float:
        """Density of the error at t (unit scale)."""
        prior = math.exp(-0.5 * t * t) / math.sqrt(2.0 * math.pi)
        n = len(self._res)
        if n == 0:
            return prior
        if self._arr is None:
            self._arr = np.fromiter(self._res, float, n)
        dens = np.mean(0.25 / np.cosh(0.5 * (np.array([[t], [-t]]) - self._arr[None, :]) / self._h) ** 2, axis=1) / self._h
        ws = self._k / (n + self._k)
        empirical = float(ws * 0.5 * (dens[0] + dens[1]) + (1.0 - ws) * dens[0])
        w = n / (n + self._k)
        return w * empirical + (1.0 - w) * prior


class Mixture:
    """A point mass at `x0` (price does not move again) plus a continuous part.

    `cont_cdf` maps an array of points to the continuous part's CDF values.
    """

    def __init__(self, cont_cdf: Callable[[np.ndarray], np.ndarray], mass: float, x0: float):
        self._cont = cont_cdf
        self.mass = mass
        self.x0 = x0

    def cdf(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        return (1.0 - self.mass) * self._cont(x) + np.where(x >= self.x0, self.mass, 0.0)

    def quantiles(self, ps: Sequence[float]) -> np.ndarray:
        ps = np.asarray(ps, dtype=float)
        # Bracket around the current price (x0 can be hundreds of sigmas away after a rug
        # or a pump within the candle), widening until every quantile is inside.
        lo = np.full(ps.shape, self.x0 - 64.0)
        hi = np.full(ps.shape, self.x0 + 64.0)
        for step in range(12):
            low_out = self.cdf(lo) >= ps
            high_out = self.cdf(hi) < ps
            if not (low_out.any() or high_out.any()):
                break
            lo = np.where(low_out, lo - 128.0 * 2**step, lo)
            hi = np.where(high_out, hi + 128.0 * 2**step, hi)
        for _ in range(64):
            mid = 0.5 * (lo + hi)
            below = self.cdf(mid) < ps
            lo = np.where(below, mid, lo)
            hi = np.where(below, hi, mid)
        left = (1.0 - self.mass) * float(self._cont(np.array([self.x0]))[0])
        in_jump = (ps > left) & (ps <= left + self.mass)
        return np.where(in_jump, self.x0, hi)


def logit(p: float) -> float:
    p = min(max(p, 1e-9), 1.0 - 1e-9)
    return math.log(p / (1.0 - p))


def sigmoid(x: float) -> float:
    return 0.5 * (1.0 + math.tanh(0.5 * x))


class DirectionCalibrator:
    """Recalibrates 'up vs down' odds against realized moves.

    Fits a slope `a` in p = sigmoid(a * logit(q)) by discounted logistic
    regression (a few Newton steps from the last fit), shrunk toward a = 1 by
    `prior_count` pseudo-observations. If stated odds carry no information about
    what actually happens, `a` falls toward 0 and confidence toward 50%; on
    calibrated odds it stays at 1 (a least-squares fit on the linearized model
    settled near 0.83). It only ever tempers: a few lucky outcomes on near-50%
    odds would otherwise inflate the slope early in a token's life.
    """

    def __init__(self, prior_count: float = 50.0, discount: float = 0.995, window: int = 1000):
        self._k = prior_count
        self._discount = discount
        self._obs: deque[tuple[float, float]] = deque(maxlen=window)
        self._a = 1.0

    @property
    def slope(self) -> float:
        return self._a

    def update(self, log_odds: float, up: bool) -> None:
        self._obs.append((min(max(log_odds, -3.0), 3.0), 1.0 if up else 0.0))
        L, Y = np.array(self._obs).T
        W = self._discount ** np.arange(len(L) - 1, -1, -1)
        m = max(float(np.sum(W * L * L) / np.sum(W)), 1e-2)
        h0 = self._k * m / 4.0  # Fisher information of the pseudo-observations at a = 1
        a = self._a
        for _ in range(3):
            p = 0.5 * (1.0 + np.tanh(0.5 * a * L))
            g = float(np.sum(W * (Y - p) * L)) - h0 * (a - 1.0)
            h = float(np.sum(W * p * (1.0 - p) * L * L)) + h0
            a += g / h
        self._a = min(1.0, max(0.0, a))

    def apply(self, q: float, weight: float = 1.0) -> float:
        """Calibrated P(up | price moves); `weight` in [0, 1] phases the correction in."""
        a = 1.0 + (self.slope - 1.0) * weight
        return sigmoid(a * logit(q))
