"""Track record of locked-in forecasts: is the stated confidence honest?"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

from .model import Outcome


@dataclass
class Tally:
    n: int = 0
    hits: int = 0
    confidence: float = 0.0
    in_band: int = 0
    error: float = 0.0
    naive_error: float = 0.0

    @classmethod
    def of(cls, outcomes: Iterable[Outcome]) -> Tally:
        tally = cls()
        for outcome in outcomes:
            tally.add(outcome)
        return tally

    def add(self, outcome: Outcome) -> None:
        self.n += 1
        self.hits += outcome.hit
        self.confidence += outcome.forecast.confidence
        self.in_band += outcome.in_band
        self.error += outcome.error
        self.naive_error += outcome.naive_error

    @property
    def hit_rate(self) -> float | None:
        return self.hits / self.n if self.n else None

    @property
    def avg_confidence(self) -> float | None:
        return self.confidence / self.n if self.n else None

    @property
    def coverage(self) -> float | None:
        return self.in_band / self.n if self.n else None

    @property
    def mae(self) -> float | None:
        return self.error / self.n if self.n else None

    @property
    def naive_mae(self) -> float | None:
        return self.naive_error / self.n if self.n else None

    @property
    def edge(self) -> float | None:
        """Fractional reduction in error vs. predicting 'no change' (positive = better)."""
        if not self.n or self.naive_error <= 0:
            return None
        return 1.0 - self.error / self.naive_error

    def to_dict(self) -> dict:
        def r(v):
            return None if v is None else round(v, 4)

        return {
            "n": self.n,
            "hit_rate": r(self.hit_rate),
            "avg_confidence": r(self.avg_confidence),
            "band_coverage": r(self.coverage),
            "mae_pct": r(None if self.mae is None else 100 * self.mae),
            "naive_mae_pct": r(None if self.naive_mae is None else 100 * self.naive_mae),
            "edge": r(self.edge),
        }


@dataclass
class Bucket:
    low: float
    high: float
    n: int
    avg_confidence: float
    hit_rate: float


class Scoreboard:
    """Separate tallies for the history warm-up (walk-forward) and live predictions."""

    def __init__(self, window: int = 50, keep: int = 5000):
        self.history = Tally()
        self.live = Tally()
        self.recent: deque[Outcome] = deque(maxlen=window)
        self.outcomes: deque[Outcome] = deque(maxlen=keep)

    def record(self, outcome: Outcome, live: bool) -> None:
        (self.live if live else self.history).add(outcome)
        if live:
            self.recent.append(outcome)
        self.outcomes.append(outcome)

    def rolling(self) -> Tally:
        return Tally.of(self.recent)

    def calibration(self, edges: tuple[float, ...] = (0.0, 0.5, 0.55, 0.6, 0.7, 1.0)) -> list[Bucket]:
        """Realized hit rate grouped by stated confidence."""
        buckets = []
        for low, high in zip(edges, edges[1:]):
            inside = [o for o in self.outcomes if low <= o.forecast.confidence < high or (high == 1.0 and o.forecast.confidence == 1.0)]
            if inside:
                tally = Tally.of(inside)
                buckets.append(Bucket(low, high, tally.n, tally.avg_confidence, tally.hit_rate))
        return buckets
