"""Global model: a gradient-boosted distribution over the next close, trained across many tokens.

A single multiclass LightGBM model predicts, for the rest of the forming
candle, the probability that the price does not move again (class 0) and the
probability that the remaining move lands in each of 24 bins of normalized
return z = ln(close / price now) / (sigma * sqrt(1 - f)). That gives a full
predictive distribution: median, bands and direction odds all come from it.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .engine import FEATURES

# Bin edges in z units; the outer bins extend to +/- infinity with exponential tails.
EDGES = np.array(
    [-4.0, -3.0, -2.5, -2.0, -1.6, -1.3, -1.0, -0.75, -0.5, -0.3, -0.15, 0.0,
     0.15, 0.3, 0.5, 0.75, 1.0, 1.3, 1.6, 2.0, 2.5, 3.0, 4.0]
)  # fmt: skip
N_BINS = len(EDGES) + 1
N_CLASSES = N_BINS + 1  # class 0 = no further price change
MODEL_DIR = Path(__file__).resolve().parent.parent / "models"


def z_to_class(z: np.ndarray, moved: np.ndarray) -> np.ndarray:
    """Class labels: 0 for no move, else 1 + bin index of z."""
    return np.where(moved, 1 + np.searchsorted(EDGES, z, side="right"), 0)


@dataclass
class BinnedDistribution:
    """Distribution of z: point mass `p_still` at 0 plus binned continuous part."""

    p_still: float
    bins: np.ndarray  # probabilities of each bin (sum to 1 - p_still)
    tail_low: float = 1.0
    tail_high: float = 1.0
    _cum: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        moved = max(1.0 - self.p_still, 1e-12)
        self._cond = self.bins / moved  # conditional on moving
        self._cum = np.concatenate([[0.0], np.cumsum(self._cond)])

    def cont_cdf(self, z: np.ndarray) -> np.ndarray:
        """CDF of z given the price moves."""
        z = np.asarray(z, dtype=float)
        inner = np.interp(z, EDGES, self._cum[1:-1])
        low = self._cond[0] * np.exp(np.minimum(z - EDGES[0], 0.0) / self.tail_low)
        high = 1.0 - self._cond[-1] * np.exp(-np.maximum(z - EDGES[-1], 0.0) / self.tail_high)
        return np.clip(np.where(z < EDGES[0], low, np.where(z > EDGES[-1], high, inner)), 0.0, 1.0)

    def cont_pdf(self, z: float) -> float:
        if z < EDGES[0]:
            return self._cond[0] / self.tail_low * math.exp((z - EDGES[0]) / self.tail_low)
        if z > EDGES[-1]:
            return self._cond[-1] / self.tail_high * math.exp(-(z - EDGES[-1]) / self.tail_high)
        k = int(np.searchsorted(EDGES, z, side="right"))
        return self._cond[k] / (EDGES[k] - EDGES[k - 1])


@dataclass
class GlobalModel:
    booster: object  # lightgbm.Booster
    meta: dict

    @property
    def timeframe(self) -> int:
        return int(self.meta["timeframe"])

    @property
    def domain(self) -> str:
        """'trades' (trained on pump.fun trade streams, SOL prices) or 'ohlcv' (candles only)."""
        return self.meta["domain"]

    @property
    def nowcast(self) -> bool:
        """Whether the model was trained on intra-candle snapshots (f > 0)."""
        return bool(self.meta.get("nowcast"))

    def compatible(self, timeframe: int, domain: str) -> bool:
        return self.timeframe == timeframe and self.domain == domain

    def columns(self) -> list[int]:
        return [FEATURES.index(name) for name in self.meta["features"]]

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        X = np.atleast_2d(X)[:, self.columns()]
        raw = np.asarray(self.booster.predict(X, raw_score=True)).reshape(len(X), N_CLASSES)
        raw = raw / float(self.meta.get("temperature", 1.0))
        raw -= raw.max(axis=1, keepdims=True)
        p = np.exp(raw)
        return p / p.sum(axis=1, keepdims=True)

    def distribution(self, x: np.ndarray) -> BinnedDistribution:
        p = self.predict_proba(x)[0]
        return BinnedDistribution(float(p[0]), p[1:], self.meta.get("tail_low", 1.0), self.meta.get("tail_high", 1.0))

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(str(path.with_suffix(".txt")))
        path.with_suffix(".json").write_text(json.dumps(self.meta, indent=2))
        return path.with_suffix(".txt")

    @classmethod
    def load(cls, path: str | Path) -> GlobalModel:
        import lightgbm as lgb

        path = Path(path)
        meta = json.loads(path.with_suffix(".json").read_text())
        if meta.get("edges") != EDGES.tolist() or any(name not in FEATURES for name in meta["features"]):
            raise ValueError(f"{path}: model was trained with a different feature/bin layout")
        return cls(lgb.Booster(model_file=str(path.with_suffix(".txt"))), meta)


def model_name(domain: str, timeframe: int) -> str:
    return f"{domain}-{timeframe}s"


def find_model(domain: str, timeframe: int, directory: str | Path | None = None, allow_simulated: bool = False) -> GlobalModel | None:
    """Load the trained model for this domain/timeframe, if one exists and LightGBM is installed.

    Models trained on simulated data are only loaded when `allow_simulated` is set.
    """
    directory = Path(directory or os.environ.get("TARTAR_MODEL_DIR") or MODEL_DIR)
    path = directory / f"{model_name(domain, timeframe)}.txt"
    if not path.exists():
        return None
    try:
        model = GlobalModel.load(path)
    except ImportError:
        return None
    if model.meta.get("simulated") and not allow_simulated:
        return None
    return model


# Vectorized versions over many rows of class probabilities (used for training and evaluation).


def _edge_cdf(probs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """CDF of z at each edge (right limit, incl. the no-move mass at 0) and its left limit."""
    bins = probs[:, 1:]
    right = np.cumsum(bins, axis=1)[:, :-1] + probs[:, :1] * (EDGES >= 0)
    left = right - probs[:, :1] * (EDGES == 0)
    return right, left


def batch_cdf(probs: np.ndarray, c: np.ndarray, tail_low: float = 1.0, tail_high: float = 1.0) -> np.ndarray:
    """P(z <= c) per row."""
    c = np.asarray(c, dtype=float)
    right, _ = _edge_cdf(probs)
    rows = np.arange(len(probs))
    b_first, b_last = probs[:, 1], probs[:, -1]
    k = np.clip(np.searchsorted(EDGES, c, side="right"), 1, len(EDGES) - 1)
    inner = right[rows, k - 1] + probs[rows, 1 + k] * (c - EDGES[k - 1]) / (EDGES[k] - EDGES[k - 1])
    low = b_first * np.exp(np.minimum(c - EDGES[0], 0.0) / tail_low)
    high = 1.0 - b_last * np.exp(-np.maximum(c - EDGES[-1], 0.0) / tail_high)
    return np.where(c < EDGES[0], low, np.where(c >= EDGES[-1], high, inner))


def batch_quantile(probs: np.ndarray, p: float, tail_low: float = 1.0, tail_high: float = 1.0) -> np.ndarray:
    """Smallest z with P(z' <= z) >= p, per row."""
    right, left = _edge_cdf(probs)
    rows = np.arange(len(probs))
    reached = right >= p
    i = np.where(reached.any(axis=1), reached.argmax(axis=1), len(EDGES))
    out = np.empty(len(probs))
    b_first, b_last = np.maximum(probs[:, 1], 1e-12), np.maximum(probs[:, -1], 1e-12)
    low_tail = i == 0
    out[low_tail] = EDGES[0] + tail_low * np.log(np.minimum(p / b_first[low_tail], 1.0))
    high_tail = i == len(EDGES)
    out[high_tail] = EDGES[-1] - tail_high * np.log(np.maximum((1.0 - p) / b_last[high_tail], 1e-12))
    mid = ~(low_tail | high_tail)
    im, rm = i[mid], rows[mid]
    lo_val, hi_val = right[rm, im - 1], left[rm, im]
    jump = hi_val < p  # p falls inside the no-move mass at z = 0
    frac = np.where(hi_val > lo_val, (p - lo_val) / np.maximum(hi_val - lo_val, 1e-12), 1.0)
    out[mid] = np.where(jump, 0.0, EDGES[im - 1] + np.clip(frac, 0.0, 1.0) * (EDGES[im] - EDGES[im - 1]))
    return out
