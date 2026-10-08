"""Text and JSON outputs, plus shared formatting helpers."""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime
from typing import IO

from .agent import Sink, View
from .candles import Candle, format_timeframe
from .market import MarketInfo, short
from .model import Forecast, Outcome
from .scoreboard import Scoreboard, Tally

_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
ARROWS = {"up": "▲", "down": "▼", "flat": "▬"}
COIN_FLIP_PCT = 52  # calls shown at or below this confidence are flagged as coin flips


def fmt_price(price: float | None, digits: int = 4) -> str:
    """Compact price; tiny memecoin prices use DexScreener-style zero counts (0.0₅4521)."""
    if price is None or not math.isfinite(price):
        return "—"
    if price <= 0:
        return "0"
    if price >= 1000:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:.4f}"
    zeros = -math.floor(math.log10(price)) - 1
    if zeros < 4:
        return f"{price:.{zeros + digits}f}"
    mantissa = round(price * 10 ** (zeros + digits))
    if mantissa >= 10**digits:
        zeros -= 1
        mantissa = round(mantissa / 10)
    return f"0.0{str(zeros).translate(_SUBSCRIPT)}{mantissa}"


def fmt_pct(x: float | None, digits: int = 2) -> str:
    return "—" if x is None else f"{100 * x:+.{digits}f}%"


def fmt_prob(p: float | None) -> str:
    return "—" if p is None else f"{100 * p:.0f}%"


def is_coin_flip(f: Forecast) -> bool:
    return f.direction != "flat" and int(f"{100 * f.confidence:.0f}") <= COIN_FLIP_PCT


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds >= 3600:
        return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60}:{seconds % 60:02d}"


def fmt_time(ts: float, timeframe: int) -> str:
    fmt = "%H:%M:%S" if timeframe < 60 else "%H:%M" if timeframe < 86400 else "%Y-%m-%d"
    return datetime.fromtimestamp(ts).strftime(fmt)


def call_text(f: Forecast) -> str:
    """'UP 61%', or flags a call that is little better than a coin flip."""
    text = f"{f.direction.upper()} {fmt_prob(f.confidence)}"
    if is_coin_flip(f):
        text += " (≈ coin flip)"
    return text


def describe_forecast(f: Forecast, quote: str) -> str:
    return (
        f"{fmt_price(f.price)} {quote} ({fmt_pct(f.change)}) {ARROWS[f.direction]} {call_text(f)}"
        f" · {f.coverage:.0%} band {fmt_price(f.low)}–{fmt_price(f.high)}"
    )


def tally_line(t: Tally) -> str:
    if not t.n:
        return "no scored predictions yet"
    return (
        f"n={t.n} · direction hit {fmt_prob(t.hit_rate)} (stated {fmt_prob(t.avg_confidence)})"
        f" · band coverage {fmt_prob(t.coverage)} · error {100 * t.mae:.2f}% vs naive {100 * t.naive_mae:.2f}%"
        f" (edge {fmt_pct(t.edge, 1)})"
    )


def summary_lines(board: Scoreboard) -> list[str]:
    lines = []
    if board.history.n:
        lines.append(f"history warm-up: {tally_line(board.history)}")
    lines.append(f"live:            {tally_line(board.live)}")
    return lines


class PlainPrinter(Sink):
    """Human-readable log lines: one per closed candle, plus periodic live updates."""

    def __init__(self, stream: IO[str] | None = None, every: float = 10.0):
        self.stream = stream or sys.stdout
        self.every = every
        self._last = 0.0
        self._quote = ""
        self._tf = 60

    def _print(self, text: str) -> None:
        print(text, file=self.stream, flush=True)

    def start(self, info: MarketInfo, timeframe: int) -> None:
        self._quote, self._tf = info.quote, timeframe
        name = f" ({info.name})" if info.name else ""
        self._print(
            f"Watching {info.symbol}{name} {short(info.address)} via {info.source} · "
            f"{format_timeframe(timeframe)} candles · prices in {info.quote}"
        )
        for note in info.notes:
            self._print(f"  note: {note}")

    def warmed_up(self, candles: int, board: Scoreboard) -> None:
        self._print(f"Warm-up on {candles} historical candles: {tally_line(board.history)}")

    def candle_closed(self, candle: Candle, outcome: Outcome | None, next_forecast: Forecast | None) -> None:
        line = f"[{fmt_time(candle.start, self._tf)}] closed {fmt_price(candle.close)} {self._quote}"
        if outcome is not None:
            f = outcome.forecast
            verdict = "HIT" if outcome.hit else "MISS"
            band = "in band" if outcome.in_band else "outside band"
            line += f" | predicted {fmt_price(f.price)} {ARROWS[f.direction]} {call_text(f)} → {verdict}, {band}"
        self._print(line)
        if next_forecast is not None:
            self._print(f"  next [{fmt_time(next_forecast.target_start, self._tf)}] {describe_forecast(next_forecast, self._quote)}")

    def update(self, view: View) -> None:
        if view.live is None or time.monotonic() - self._last < self.every:
            return
        self._last = time.monotonic()
        f = view.live
        left = fmt_duration(f.target_end - view.now)
        self._print(
            f"  live [{fmt_time(f.target_start, self._tf)}, {left} left] now {fmt_price(f.last_price)} → "
            f"close {describe_forecast(f, self._quote)}"
        )

    def status(self, message: str, level: str) -> None:
        self._print(f"  {'!' if level != 'info' else '·'} {message}")

    def stop(self, board: Scoreboard) -> None:
        for line in summary_lines(board):
            self._print(line)


class JsonLines(Sink):
    """Machine-readable event stream, one JSON object per line."""

    def __init__(self, stream: IO[str] | None = None, every: float = 1.0):
        self.stream = stream or sys.stdout
        self.every = every
        self._last = 0.0

    def _write(self, obj: dict) -> None:
        self.stream.write(json.dumps(obj) + "\n")
        self.stream.flush()

    def start(self, info: MarketInfo, timeframe: int) -> None:
        self._write(
            {
                "type": "start",
                "token": info.address,
                "symbol": info.symbol,
                "name": info.name,
                "quote": info.quote,
                "source": info.source,
                "pool": info.pool,
                "dex": info.dex,
                "timeframe": timeframe,
                "notes": info.notes,
            }
        )

    def warmed_up(self, candles: int, board: Scoreboard) -> None:
        self._write({"type": "warmup", "candles": candles, "track_record": board.history.to_dict()})

    def candle_closed(self, candle: Candle, outcome: Outcome | None, next_forecast: Forecast | None) -> None:
        self._write(
            {
                "type": "candle",
                "start": candle.start,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "trades": candle.trades,
            }
        )
        if outcome is not None:
            self._write({"type": "result", **outcome.to_dict()})
        if next_forecast is not None:
            self._write({"type": "forecast", **next_forecast.to_dict()})

    def update(self, view: View) -> None:
        if view.live is None or time.monotonic() - self._last < self.every:
            return
        self._last = time.monotonic()
        self._write({"type": "prediction", "ts": round(view.now, 3), **view.live.to_dict()})

    def status(self, message: str, level: str) -> None:
        self._write({"type": "status", "level": level, "message": message})

    def stop(self, board: Scoreboard) -> None:
        self._write({"type": "summary", "live": board.live.to_dict(), "history": board.history.to_dict()})
