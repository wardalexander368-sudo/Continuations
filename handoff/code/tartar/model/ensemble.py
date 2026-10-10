"""Online experts predicting the next normalized return, mixed by recent performance."""

from __future__ import annotations

from typing import Protocol, Sequence

import numpy as np

from .features import FEATURES


class Expert(Protocol):
    name: str

    def predict(self, x: np.ndarray) -> float: ...

    def update(self, x: np.ndarray, z: float) -> None: ...


class RandomWalk:
    """No predictable move: the next close equals the last close (in the median)."""

    name = "random walk"

    def predict(self, x: np.ndarray) -> float:
        return 0.0

    def update(self, x: np.ndarray, z: float) -> None:
        pass


class Drift:
    """Persistent trend: recent average normalized return, shrunk toward zero."""

    name = "drift"

    def __init__(self, halflife: float = 15.0, shrink: float = 8.0):
        self._decay = 0.5 ** (1.0 / halflife)
        self._shrink = shrink
        self._mean = 0.0
        self._weight = 0.0

    def predict(self, x: np.ndarray) -> float:
        return self._mean * self._weight / (self._weight + self._shrink)

    def update(self, x: np.ndarray, z: float) -> None:
        self._weight = self._weight * self._decay + 1.0
        self._mean += (z - self._mean) / self._weight


class RidgeExpert:
    """Exponentially-weighted ridge regression on a subset of features (plus intercept)."""

    def __init__(self, name: str, features: Sequence[str], forget: float, ridge: float):
        self.name = name
        self._idx = np.array([FEATURES.index(f) for f in features])
        dim = len(self._idx) + 1
        self._forget = forget
        self._ridge = ridge * np.eye(dim)
        self._a = np.zeros((dim, dim))
        self._b = np.zeros(dim)
        self._w = np.zeros(dim)

    def _vec(self, x: np.ndarray) -> np.ndarray:
        return np.append(x[self._idx], 1.0)

    def predict(self, x: np.ndarray) -> float:
        return float(self._vec(x) @ self._w)

    def update(self, x: np.ndarray, z: float) -> None:
        v = self._vec(x)
        self._a = self._forget * self._a + np.outer(v, v)
        self._b = self._forget * self._b + v * z
        self._w = np.linalg.solve(self._a + self._ridge, self._b)


class Ensemble:
    """Exponentially weighted forecaster over experts, using discounted squared error.

    Starts out trusting the random walk and only shifts weight to another expert
    after it has actually beaten it on this token's recent candles.
    """

    def __init__(
        self,
        experts: Sequence[Expert],
        prior: Sequence[float] | None = None,
        eta: float = 0.5,
        forget: float = 0.99,
        clip: float = 3.0,
        limit: float = 1.0,
    ):
        self.experts = list(experts)
        prior = np.ones(len(self.experts)) if prior is None else np.asarray(prior, dtype=float)
        self._log_prior = np.log(prior / prior.sum())
        self._loss = np.zeros(len(self.experts))
        self._eta = eta
        self._forget = forget
        self._clip = clip
        self._limit = limit

    @property
    def weights(self) -> np.ndarray:
        logits = self._log_prior - self._eta * self._loss
        w = np.exp(logits - logits.max())
        return w / w.sum()

    def describe(self) -> dict[str, float]:
        return {e.name: float(w) for e, w in zip(self.experts, self.weights)}

    def predict(self, x: np.ndarray) -> tuple[float, np.ndarray]:
        preds = np.clip([e.predict(x) for e in self.experts], -self._limit, self._limit)
        return float(np.clip(self.weights @ preds, -self._limit, self._limit)), preds

    def update(self, x: np.ndarray, z: float, preds: np.ndarray) -> None:
        z = float(np.clip(z, -self._clip, self._clip))
        self._loss = self._forget * self._loss + (z - preds) ** 2
        for expert in self.experts:
            expert.update(x, z)


def default_ensemble() -> Ensemble:
    experts = [
        RandomWalk(),
        Drift(),
        RidgeExpert("momentum", ("ret1", "ret2", "ret3"), forget=0.97, ridge=20.0),
        RidgeExpert("order flow", ("ret1", "clv", "body", "range", "volume", "flow"), forget=0.985, ridge=30.0),
        RidgeExpert("full", FEATURES, forget=0.995, ridge=40.0),
    ]
    return Ensemble(experts, prior=[0.4, 0.15, 0.15, 0.15, 0.15])
