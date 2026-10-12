"""Walk-forward evaluation on historical candles."""

from __future__ import annotations

from typing import Iterable

from .candles import Candle, fill_gaps
from .model import Forecaster
from .scoreboard import Scoreboard


def backtest(candles: Iterable[Candle], timeframe: int, coverage: float = 0.8) -> Scoreboard:
    """Feed candles through a fresh forecaster one at a time, scoring each locked-in forecast.

    The model only ever sees candles before the one it predicts, exactly as it
    would live.
    """
    forecaster = Forecaster(timeframe, coverage)
    board = Scoreboard()
    for candle in fill_gaps(candles, timeframe):
        outcome = forecaster.observe(candle)
        if outcome is not None:
            board.record(outcome, live=False)
    return board
