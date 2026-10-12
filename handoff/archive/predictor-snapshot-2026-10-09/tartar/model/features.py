"""Scale-free features describing the most recent candles."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from ..candles import Candle

FEATURES = (
    "ret1",  # last log return / sigma
    "ret2",
    "ret3",
    "clv",  # where the last close sits within its high/low range (-1..1)
    "body",  # last candle open->close / sigma
    "range",  # last candle high/low range / sigma, centred
    "volume",  # last volume vs recent volume (z-score of log volume)
    "flow",  # buy/sell volume imbalance (-1..1)
    "stretch",  # distance of close from its fast EMA / sigma
    "trend",  # fast EMA vs slow EMA / sigma
)


def _ema(values: Sequence[float], span: int) -> float:
    alpha = 2.0 / (span + 1.0)
    level = values[0]
    for v in values[1:]:
        level += alpha * (v - level)
    return level


def build_features(history: Sequence[Candle], sigma: float, window: int = 40) -> np.ndarray:
    x = np.zeros(len(FEATURES))
    recent = list(history)[-window:]
    n = len(recent)
    if n == 0:
        return x
    last = recent[-1]
    for k in range(3):
        if n >= k + 2:
            x[k] = math.log(recent[-1 - k].close / recent[-2 - k].close) / sigma
    spread = last.high - last.low
    if spread > 0:
        x[3] = ((last.close - last.low) - (last.high - last.close)) / spread
    x[4] = math.log(last.close / last.open) / sigma
    x[5] = math.log(last.high / last.low) / sigma - 1.5
    # Compare volume only with candles from the same kind of source (history and
    # live feeds can report volume in different units, e.g. USD vs SOL).
    same = [c.volume for c in recent if (c.trades is None) == (last.trades is None)]
    if len(same) >= 4 and any(v > 0 for v in same):
        logs = np.log1p(same)
        x[6] = (logs[-1] - logs[:-1].mean()) / (logs[:-1].std() + 0.5)
    flow = last.buy_volume + last.sell_volume
    if flow > 0:
        x[7] = (last.buy_volume - last.sell_volume) / flow
    if n >= 3:
        logs = [math.log(c.close) for c in recent]
        fast, slow = _ema(logs, 8), _ema(logs, 21)
        x[8] = (logs[-1] - fast) / sigma
        x[9] = (fast - slow) / sigma
    return np.clip(x, -4.0, 4.0)
