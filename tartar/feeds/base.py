"""Live feed interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Union

from ..candles import Candle, Tick


@dataclass(frozen=True)
class Snapshot:
    """OHLCV candles from a polled source; the newest may still be forming."""

    candles: list[Candle]


@dataclass(frozen=True)
class Status:
    message: str
    level: str = "info"  # info | warn | error


Event = Union[Tick, Snapshot, Status]


class LiveFeed(ABC):
    name: str = "feed"
    # Seconds after a candle's end before the clock closes it (covers feed latency).
    close_grace: float = 2.0
    # Whether ticks carry real trade counts.
    counts_trades: bool = True

    @abstractmethod
    def events(self) -> AsyncIterator[Event]:
        """Yield ticks, snapshots and status messages until cancelled."""
