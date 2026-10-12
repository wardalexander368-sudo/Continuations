"""Wall-clock and simulated clocks, so the agent can run live or faster than real time."""

from __future__ import annotations

import asyncio
import time


class Clock:
    """Real time."""

    speed = 1.0

    def now(self) -> float:
        return time.time()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(0.0, seconds))


class SimClock(Clock):
    """Simulated time that runs `speed` times faster than real time."""

    def __init__(self, start: float | None = None, speed: float = 1.0):
        if speed <= 0:
            raise ValueError("speed must be positive")
        self.speed = speed
        self._start = time.time() if start is None else start
        self._t0 = time.monotonic()

    def now(self) -> float:
        return self._start + (time.monotonic() - self._t0) * self.speed

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(0.0, seconds) / self.speed)
