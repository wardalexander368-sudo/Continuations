"""Full-screen live terminal dashboard: candle chart, prediction, and track record."""

from __future__ import annotations

import math
from collections import deque
from typing import Sequence

from rich import box
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .agent import Sink, View
from .candles import Candle, format_timeframe
from .market import MarketInfo, short
from .model import Forecast
from .output import ARROWS, call_text, fmt_duration, fmt_pct, fmt_price, fmt_prob, fmt_time, is_coin_flip
from .scoreboard import Scoreboard

DIRECTION_STYLE = {"up": "bold green", "down": "bold red", "flat": "bold white"}
RISK_STYLE = {"ok": "bold black on green", "caution": "bold black on yellow", "danger": "bold white on red", "scam": "bold white on red blink"}
RISK_BORDER = {"caution": "yellow", "danger": "red", "scam": "red"}


def render_chart(
    candles: Sequence[Candle],
    current: Candle | None,
    forecast: Forecast | None,
    width: int,
    height: int,
    timeframe: int,
) -> list[Text]:
    """Candlesticks on a log price scale, with the predicted close (◆) and band (┊)."""
    axis_w = 12
    rows = max(height - 1, 4)
    plot_w = max(width - axis_w - 1, 8)
    slots = plot_w // 2
    n_hist = max(slots - (current is not None) - (forecast is not None), 0)
    series = (list(candles)[-n_hist:] if n_hist else []) + ([current] if current is not None else [])
    if not series:
        return [Text("waiting for the first trade…", style="dim")]

    lo = min(c.low for c in series)
    hi = max(c.high for c in series)
    if forecast is not None:
        lo, hi = min(lo, forecast.low), max(hi, forecast.high)
    y_lo, y_hi = math.log(lo), math.log(hi)
    if y_hi - y_lo < 1e-9:
        y_lo, y_hi = y_lo - 0.005, y_hi + 0.005
    pad = (y_hi - y_lo) * 0.04
    y_lo, y_hi = y_lo - pad, y_hi + pad

    def row(price: float) -> int:
        return min(rows - 1, max(0, round((y_hi - math.log(price)) / (y_hi - y_lo) * (rows - 1))))

    def price_at(r: int) -> float:
        return math.exp(y_hi - r / (rows - 1) * (y_hi - y_lo))

    grid: list[list[tuple[str, str]]] = [[(" ", "")] * plot_w for _ in range(rows)]
    last_row = row(series[-1].close)
    for col in range(plot_w):
        grid[last_row][col] = ("┄", "grey30")

    for i, c in enumerate(series):
        col = 2 * i
        forming = current is not None and i == len(series) - 1
        if not c.active:
            style = "grey50"
        elif c.close >= c.open:
            style = "bright_green" if forming else "green"
        else:
            style = "bright_red" if forming else "red"
        if forming:
            style = f"bold {style}"
        r_high, r_low, r_open, r_close = row(c.high), row(c.low), row(c.open), row(c.close)
        for r in range(r_high, r_low + 1):
            grid[r][col] = ("│", style)
        top, bottom = min(r_open, r_close), max(r_open, r_close)
        body = "█" if c.open != c.close else ("┼" if r_high != r_low else "─")
        for r in range(top, bottom + 1):
            grid[r][col] = (body, style)

    pred_row = None
    if forecast is not None and 2 * len(series) < plot_w:
        col = 2 * len(series)
        for r in range(row(forecast.high), row(forecast.low) + 1):
            grid[r][col] = ("┊", "yellow")
        pred_row = row(forecast.price)
        grid[pred_row][col] = ("◆", "bold yellow")

    labels: dict[int, tuple[str, str]] = {}
    for r in (0, rows // 4, rows // 2, 3 * rows // 4, rows - 1):
        labels[r] = (fmt_price(price_at(r)), "dim")
    for special, text, style in (
        (pred_row, f"◆{fmt_price(forecast.price) if forecast else ''}", "bold yellow"),
        (last_row, f"◀{fmt_price(series[-1].close)}", "bold reverse"),
    ):
        if special is None:
            continue
        for r in (special - 1, special + 1):
            if labels.get(r, ("", ""))[1] == "dim":
                labels.pop(r)
        labels[special] = (text, style)

    lines = []
    for r in range(rows):
        line = Text()
        run_char, run_style = "", None
        for ch, st in grid[r]:
            if st == run_style:
                run_char += ch
            else:
                if run_char:
                    line.append(run_char, run_style or "")
                run_char, run_style = ch, st
        line.append(run_char, run_style or "")
        label, label_style = labels.get(r, ("", ""))
        line.append(" " + label[: axis_w - 1], label_style)
        lines.append(line)

    axis = [" "] * plot_w
    for idx in (0, len(series) // 2, len(series) - 1):
        stamp = fmt_time(series[idx].start, timeframe)
        col = min(2 * idx, plot_w - len(stamp))
        if all(ch == " " for ch in axis[max(col - 1, 0) : col + len(stamp) + 1]):
            axis[col : col + len(stamp)] = list(stamp)
    lines.append(Text("".join(axis), style="dim"))
    return lines


class ChartView:
    def __init__(self, view: View):
        self.view = view

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        v = self.view
        lines = render_chart(v.candles, v.current, v.live, options.max_width, options.height or 20, v.timeframe)
        yield Text("\n").join(lines)


def _bar(fraction: float, width: int = 14) -> Text:
    filled = round(max(0.0, min(1.0, fraction)) * width)
    return Text("▰" * filled, style="yellow") + Text("▱" * (width - filled), style="grey35")


class Dashboard(Sink):
    def __init__(self, console: Console | None = None, recent: int = 7):
        self.console = console or Console()
        self.recent = recent
        self.messages: deque[tuple[str, str]] = deque(maxlen=2)
        self.info: MarketInfo | None = None
        self.timeframe = 60
        self.view: View | None = None
        self.warmup = 0
        self._live: Live | None = None

    # Sink interface -----------------------------------------------------------------------------

    def start(self, info: MarketInfo, timeframe: int) -> None:
        self.info, self.timeframe = info, timeframe
        for note in info.notes:
            self.messages.append((note, "info"))
        self._live = Live(console=self.console, screen=True, auto_refresh=False, redirect_stdout=False)
        self._live.start()
        self._refresh()

    def warmed_up(self, candles: int, board: Scoreboard) -> None:
        self.warmup = candles

    def update(self, view: View) -> None:
        self.view = view
        self._refresh()

    def status(self, message: str, level: str) -> None:
        self.messages.append((message, level))
        self._refresh()

    def stop(self, board: Scoreboard) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    # Rendering ----------------------------------------------------------------------------------

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self.render(), refresh=True)

    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(self._header(), name="header", size=4),
            Layout(name="body", ratio=1),
            Layout(self._footer(), name="footer", size=self.recent + 6),
        )
        tf = format_timeframe(self.timeframe)
        quote = self.info.quote if self.info else ""
        chart = ChartView(self.view) if self.view else Text("loading…", style="dim")
        layout["body"].split_row(
            Layout(Panel(chart, title=f"{tf} candles · {quote}", border_style="grey50"), name="chart", ratio=3),
            Layout(name="side", ratio=2, minimum_size=50),
        )
        layout["side"].split_column(Layout(self._prediction(), name="prediction", size=10), Layout(self._record(), name="record"))
        return layout

    def _header(self) -> Panel:
        info = self.info
        text = Text("TARTAR ", style="bold magenta")
        if info:
            text.append(f"▸ {info.symbol}", style="bold")
            if info.name:
                text.append(f" {info.name}")
            text.append(f"  {short(info.address)} · {info.source}", style="dim")
            if info.dex:
                text.append(f" · {info.dex}", style="dim")
        v = self.view
        if v is not None:
            age = f"{v.now - v.last_tick_at:.0f}s ago" if v.last_tick_at else "—"
            text.append(f"  ·  {v.ticks} trades seen, last {age}", style="dim")
        risk = v.risk if v is not None else None
        if risk is not None and risk.level != "unknown":
            text.append("\n")
            text.append(f" RISK {risk.level.upper()} ", style=RISK_STYLE[risk.level])
            text.append(f"  {risk.summary()}", style="dim" if risk.level == "ok" else "")
        return Panel(text, box=box.ROUNDED, border_style=RISK_BORDER.get(risk.level if risk else "", "magenta"))

    def _prediction(self) -> Panel:
        v = self.view
        title = "[b]Next close[/b]"
        if v is None or v.live is None:
            return Panel(Text("waiting for the first trade…", style="dim"), title=title, border_style="yellow")
        f, locked, quote = v.live, v.locked, v.info.quote
        grid = Table.grid(padding=(0, 1))
        grid.add_column(style="dim", justify="right", no_wrap=True)
        grid.add_column(no_wrap=True)
        grid.add_row("candle", Text(f"{fmt_time(f.target_start, v.timeframe)}  closes in {fmt_duration(f.target_end - v.now)} ") + _bar(f.elapsed))
        grid.add_row("price now", Text(f"{fmt_price(f.last_price)} {quote}  ") + Text(f"{fmt_pct(f.last_price / f.ref_price - 1)} vs prev close", style="dim"))
        grid.add_row(
            "predicted close",
            Text(f"{fmt_price(f.price)} {quote} ", style="bold") + Text(f"{ARROWS[f.direction]} {fmt_pct(f.change)}", style=DIRECTION_STYLE[f.direction]),
        )
        style = "dim" if is_coin_flip(f) else DIRECTION_STYLE[f.direction]
        grid.add_row(
            "confidence",
            Text(call_text(f), style=style) + Text(f"   ▲{fmt_prob(f.p_up)} ▼{fmt_prob(f.p_down)} ▬{fmt_prob(f.p_flat)}", style="dim"),
        )
        grid.add_row(f"{f.coverage:.0%} band", f"{fmt_price(f.low)} – {fmt_price(f.high)}")
        if locked is not None and locked.target_start == f.target_start:
            grid.add_row("locked at open", Text(f"{fmt_price(locked.price)} {ARROWS[locked.direction]} {call_text(locked)}", style="dim"))
        grid.add_row("volatility", Text(f"{100 * f.sigma:.2f}%/candle · signal {f.signal:+.2f}σ", style="dim"))
        return Panel(grid, title=title, border_style="yellow")

    def _record(self) -> Panel:
        v = self.view
        if v is None:
            return Panel("", title="Track record")
        board = v.board
        cols = [("last 50", board.rolling()), ("session", board.live), (f"history ({self.warmup})", board.history)]
        table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
        table.add_column("", style="dim", no_wrap=True)
        for name, _ in cols:
            table.add_column(name, justify="right", no_wrap=True)

        def row(label, fn):
            table.add_row(label, *(fn(t) if t.n else "—" for _, t in cols))

        row("predictions", lambda t: str(t.n))
        row("direction hit", lambda t: fmt_prob(t.hit_rate))
        row("stated conf.", lambda t: fmt_prob(t.avg_confidence))
        row(f"in {v.live.coverage:.0%} band" if v.live else "in band", lambda t: fmt_prob(t.coverage))
        row("avg error", lambda t: f"{100 * t.mae:.2f}%")
        row("naive error", lambda t: f"{100 * t.naive_mae:.2f}%")
        row("edge vs naive", lambda t: fmt_pct(t.edge, 1))
        mix = " · ".join(f"{name} {w:.0%}" for name, w in sorted(v.weights.items(), key=lambda kv: -kv[1]))
        return Panel(Group(table, Text(f"model mix: {mix}", style="dim")), title="[b]Track record[/b] (locked-at-open forecasts)", border_style="cyan")

    def _footer(self) -> Panel:
        table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
        for name, justify in (("candle", "left"), ("predicted", "right"), ("call", "left"), ("actual", "right"), ("error", "right"), ("result", "left")):
            table.add_column(name, justify=justify, no_wrap=True)
        v = self.view
        if v is not None:
            for o in list(v.board.recent)[-self.recent :][::-1]:
                f = o.forecast
                result = Text.assemble(
                    ("✓ direction" if o.hit else "✗ direction", "green" if o.hit else "red"),
                    ("  ● in band" if o.in_band else "  ○ outside band", "dim"),
                )
                table.add_row(
                    fmt_time(f.target_start, self.timeframe),
                    fmt_price(f.price),
                    Text(f"{ARROWS[f.direction]} {call_text(f)}", style=DIRECTION_STYLE[f.direction]),
                    fmt_price(o.actual),
                    f"{100 * (o.actual / f.price - 1):+.2f}%",
                    result,
                )
        status = Text()
        for message, level in self.messages:
            status.append(("! " if level != "info" else "· ") + message + "\n", style="yellow" if level != "info" else "dim")
        status.append("Ctrl+C to stop · predictions are statistical estimates, not financial advice", style="grey42")
        return Panel(Group(table, status), title="[b]Recent results[/b]", border_style="grey50")
