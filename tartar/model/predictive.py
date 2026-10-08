"""Predictive distribution of the next close, in units of per-candle volatility."""

from __future__ import annotations

import math
from collections import deque
from typing import Callable, Sequence

import numpy as np

_LAPLACE_B = 1.0 / math.sqrt(2.0)  # unit-variance Laplace scale


def laplace_cdf(t: float) -> float:
    if t < 0:
        return 0.5 * math.exp(t / _LAPLACE_B)
    return 1.0 - 0.5 * math.exp(-t / _LAPLACE_B)


class ResidualDistribution:
    """Distribution of forecast errors (normalized), learned online.

    Kernel-smoothed empirical CDF of past residuals, shrunk toward a fat-tailed,
    unit-variance Laplace prior while there are only a few of them. Because it is
    built from this token's own realized errors, stated probabilities track how
    the model has actually been doing.
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
        prior = np.where(u < 0, 0.5 * np.exp(np.minimum(u, 0) / _LAPLACE_B), 1.0 - 0.5 * np.exp(-np.maximum(u, 0) / _LAPLACE_B))
        n = len(self._res)
        if n == 0:
            return prior
        if self._arr is None:
            self._arr = np.fromiter(self._res, float, n)
        empirical = np.mean(0.5 * (1.0 + np.tanh(0.5 * (u[:, None] - self._arr[None, :]) / self._h)), axis=1)
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
        lo = np.full(ps.shape, -64.0)
        hi = np.full(ps.shape, 64.0)
        for _ in range(48):
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

    Fits a slope `a` in p = sigmoid(a * logit(q)) by discounted least squares
    on the linearized model y - 1/2 ~ a * logit(q) / 4, shrunk toward a = 1 with
    `prior_count` pseudo-observations. If stated odds carry no information about
    what actually happens, `a` falls toward 0 and confidence toward 50%.
    """

    def __init__(self, prior_count: float = 50.0, discount: float = 0.995):
        self._k = prior_count
        self._discount = discount
        self._sly = 0.0
        self._sll = 0.0
        self._n = 0.0

    @property
    def slope(self) -> float:
        if self._n == 0 or self._sll == 0:
            return 1.0
        prior = self._k * self._sll / self._n
        return min(2.0, max(0.0, (4.0 * self._sly + prior) / (self._sll + prior)))

    def update(self, log_odds: float, up: bool) -> None:
        log_odds = min(max(log_odds, -3.0), 3.0)
        d = self._discount
        self._sly = d * self._sly + log_odds * ((1.0 if up else 0.0) - 0.5)
        self._sll = d * self._sll + log_odds * log_odds
        self._n = d * self._n + 1.0

    def apply(self, q: float, weight: float = 1.0) -> float:
        """Calibrated P(up | price moves); `weight` in [0, 1] phases the correction in."""
        a = 1.0 + (self.slope - 1.0) * weight
        return sigmoid(a * logit(q))
