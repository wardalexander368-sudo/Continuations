"""Command line: tartar watch | new | backtest | demo | resolve."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from contextlib import aclosing
from datetime import datetime, timezone

from rich import box
from rich.console import Console
from rich.table import Table

from . import __version__
from .agent import CandleAgent, Sink
from .backtest import backtest
from .candles import Tick, format_timeframe, load_csv, parse_timeframe
from .clock import SimClock
from .dashboard import Dashboard
from .feeds.geckoterminal import GeckoTerminal
from .feeds.http import ApiError
from .feeds.pumpportal import stream_new_tokens
from .feeds.synthetic import MemecoinSimulator, SyntheticFeed, synthetic_history
from .market import SOURCES, Market, MarketInfo, MarketNotFound, open_market, pumpportal_market, short
from .output import JsonLines, PlainPrinter, fmt_pct, fmt_price, fmt_prob, summary_lines, tally_line


def _add_output_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-t", "--timeframe", default="1m", help="candle size, e.g. 15s, 30s, 1m, 5m, 1h (default 1m)")
    p.add_argument("--band", type=float, default=0.8, help="coverage of the prediction band (default 0.8)")
    p.add_argument(
        "-o",
        "--output",
        choices=("auto", "dashboard", "plain", "json"),
        default="auto",
        help="dashboard (full-screen), plain log lines, or JSON lines (default: dashboard on a terminal)",
    )
    p.add_argument("--every", type=float, help="seconds between live updates in plain/json output (default 10 / 1)")
    p.add_argument("--log", metavar="FILE", help="also append every event as JSON lines to FILE")
    p.add_argument("--candles", type=int, metavar="N", help="stop after N live candles have closed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tartar",
        description="Watch a Solana token's candles live and predict each candle's close, with confidence.",
    )
    parser.add_argument("--version", action="version", version=f"tartar {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    watch = sub.add_parser("watch", help="watch a token live and predict each candle's close")
    watch.add_argument("address", nargs="?", help="token mint (or pool/pair address)")
    watch.add_argument("--next-launch", action="store_true", help="wait for the next pump.fun launch and watch it")
    watch.add_argument("--source", choices=SOURCES, default="auto", help="live data source (default: auto)")
    watch.add_argument("--history", type=int, default=500, help="historical candles to warm up on (max 1000)")
    watch.add_argument("--poll", type=float, help="seconds between polls for polled sources")
    watch.add_argument("--grace", type=float, help="seconds after a candle ends before it is closed")
    _add_output_args(watch)
    watch.set_defaults(func=cmd_watch)

    new = sub.add_parser("new", help="list newly launched Solana tokens")
    new.add_argument("--source", choices=("gecko", "pumpportal"), default="gecko", help="gecko: newest pools; pumpportal: live pump.fun launches")
    new.add_argument("--limit", type=int, default=20)
    new.set_defaults(func=cmd_new)

    bt = sub.add_parser("backtest", help="walk-forward test of the model on a token's history")
    bt.add_argument("address", nargs="?", help="token mint (or pool/pair address)")
    bt.add_argument("--csv", help="use candles from a CSV (timestamp,open,high,low,close[,volume]) instead")
    bt.add_argument("-t", "--timeframe", default="1m")
    bt.add_argument("--limit", type=int, default=1000, help="candles to fetch (max 1000)")
    bt.add_argument("--band", type=float, default=0.8)
    bt.set_defaults(func=cmd_backtest)

    demo = sub.add_parser("demo", help="run the agent on a simulated memecoin (no network needed)")
    demo.add_argument("--speed", type=float, default=20.0, help="simulated seconds per real second (default 20)")
    demo.add_argument("--seed", type=int, help="random seed")
    demo.add_argument("--history", type=int, default=200, help="simulated warm-up candles")
    _add_output_args(demo)
    demo.set_defaults(func=cmd_demo)

    resolve = sub.add_parser("resolve", help="show which pool, source and history 'watch' would use")
    resolve.add_argument("address")
    resolve.add_argument("-t", "--timeframe", default="1m")
    resolve.add_argument("--source", choices=SOURCES, default="auto")
    resolve.set_defaults(func=cmd_resolve)
    return parser


def _make_sinks(args, console: Console) -> tuple[list[Sink], float]:
    mode = args.output
    if mode == "auto":
        mode = "dashboard" if sys.stdout.isatty() else "plain"
    if mode == "dashboard":
        sinks: list[Sink] = [_SummaryDashboard(console)]
        interval = 0.25
    elif mode == "plain":
        sinks = [PlainPrinter(every=args.every or 10.0)]
        interval = 0.5
    else:
        sinks = [JsonLines(every=args.every or 1.0)]
        interval = 0.5
    if args.log:
        sinks.append(JsonLines(open(args.log, "a", buffering=1), every=1.0))
    return sinks, interval


class _SummaryDashboard(Dashboard):
    """Dashboard that prints the track record after leaving full-screen mode."""

    def stop(self, board) -> None:
        super().stop(board)
        if self.info is not None:
            self.console.print(f"[bold]{self.info.symbol}[/bold] {short(self.info.address)}")
        for line in summary_lines(board):
            self.console.print(line)


async def _run_agent(market: Market, args, timeframe: int) -> None:
    console = Console()
    sinks, interval = _make_sinks(args, console)
    agent = CandleAgent(market, timeframe, coverage=args.band, sinks=sinks, update_interval=interval)
    try:
        await agent.run(max_candles=args.candles)
    finally:
        await market.aclose()
        for sink in sinks:
            if isinstance(sink, JsonLines) and sink.stream is not sys.stdout:
                sink.stream.close()


async def cmd_watch(args) -> int:
    timeframe = parse_timeframe(args.timeframe)
    if args.next_launch:
        err = Console(stderr=True)
        err.print("Waiting for the next pump.fun launch…")
        token = None
        async with aclosing(stream_new_tokens()) as launches:
            async for token in launches:
                break
        if token is None:
            raise SystemExit("PumpPortal closed the launch stream before a token appeared")
        err.print(f"New launch: [bold]{token.symbol}[/bold] {token.name} {token.mint}")
        initial = []
        if token.price:
            sol = token.initial_buy_sol or 0.0
            initial.append(Tick(time.time(), token.price, volume=sol, buy_volume=sol))
        market = pumpportal_market(token.mint, symbol=token.symbol, name=token.name, initial=initial)
    elif args.address:
        market = await open_market(
            args.address, timeframe, args.source, history_limit=args.history, poll=args.poll, grace=args.grace
        )
    else:
        raise SystemExit("watch: give a token address or --next-launch")
    await _run_agent(market, args, timeframe)
    return 0


async def cmd_demo(args) -> int:
    timeframe = parse_timeframe(args.timeframe)
    clock = SimClock(speed=args.speed)
    sim = MemecoinSimulator(seed=args.seed)
    history = synthetic_history(sim, clock.now(), timeframe, args.history)

    async def load_history():
        return history

    info = MarketInfo(
        address="DEMoSimuLated1111111111111111111111111pump",
        symbol="DEMO",
        name="simulated memecoin",
        quote="SOL",
        source="simulated",
        notes=[f"simulated trades at {args.speed:g}x speed, not real market data"],
    )
    await _run_agent(Market(info, SyntheticFeed(sim, clock), load_history, clock), args, timeframe)
    return 0


def _age(created_at: str | None) -> str:
    if not created_at:
        return "—"
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    minutes = int((datetime.now(timezone.utc) - created).total_seconds() // 60)
    return f"{minutes}m" if minutes < 120 else f"{minutes // 60}h"


def _usd(x: float) -> str:
    return f"${x / 1e6:.2f}M" if x >= 1e6 else f"${x / 1e3:.1f}k" if x >= 1e3 else f"${x:.0f}"


async def cmd_new(args) -> int:
    console = Console()
    if args.source == "pumpportal":
        console.print("Streaming new pump.fun launches (Ctrl+C to stop)…")
        count = 0
        async with aclosing(stream_new_tokens()) as launches:
            async for token in launches:
                mcap = f"{token.market_cap_sol:.1f} SOL mcap" if token.market_cap_sol else ""
                console.print(f"{datetime.now():%H:%M:%S}  [bold]{token.symbol:<10}[/bold] {token.name[:28]:<28}  {token.mint}  {mcap}")
                count += 1
                if count >= args.limit:
                    break
        return 0
    gecko = GeckoTerminal()
    try:
        pools = await gecko.new_pools()
    finally:
        await gecko.aclose()
    table = Table(title="Newest Solana pools (GeckoTerminal)", box=box.SIMPLE_HEAD)
    for col in ("age", "symbol", "name", "token mint", "dex", "liquidity", "24h vol"):
        table.add_column(col, justify="right" if col in ("age", "liquidity", "24h vol") else "left", no_wrap=col == "token mint")
    for pool in pools[: args.limit]:
        table.add_row(
            _age(pool.created_at), pool.base_symbol, pool.base_name[:24], pool.base_token, pool.dex, _usd(pool.reserve_usd), _usd(pool.volume_24h_usd)
        )
    console.print(table)
    console.print("Watch one with: [bold]tartar watch <token mint>[/bold]")
    return 0


async def cmd_backtest(args) -> int:
    timeframe = parse_timeframe(args.timeframe)
    console = Console()
    if args.csv:
        candles, label = load_csv(args.csv), args.csv
    elif args.address:
        market = await open_market(args.address, timeframe, history_limit=args.limit)
        try:
            if market.history is None:
                raise SystemExit("no history available for this token: " + "; ".join(market.info.notes))
            candles = await market.history()
        finally:
            await market.aclose()
        label = f"{market.info.symbol} {short(market.info.address)} ({market.info.quote})"
    else:
        raise SystemExit("backtest: give a token address or --csv FILE")
    board = backtest(candles, timeframe, args.band)
    tally = board.history
    console.print(f"[bold]Backtest[/bold] {label} · {len(candles)} {format_timeframe(timeframe)} candles")
    console.print(tally_line(tally))
    table = Table(title="Calibration: stated confidence vs. realized hit rate", box=box.SIMPLE_HEAD)
    for col in ("stated confidence", "predictions", "avg stated", "realized hit"):
        table.add_column(col, justify="right")
    for bucket in board.calibration():
        table.add_row(f"{bucket.low:.0%}–{bucket.high:.0%}", str(bucket.n), fmt_prob(bucket.avg_confidence), fmt_prob(bucket.hit_rate))
    console.print(table)
    if tally.n:
        verdict = "beats" if (tally.edge or 0) > 0 else "does not beat"
        console.print(f"Point forecast {verdict} 'next close = last close' on this history (edge {fmt_pct(tally.edge, 1)}).")
    return 0


async def cmd_resolve(args) -> int:
    timeframe = parse_timeframe(args.timeframe)
    console = Console()
    market = await open_market(args.address, timeframe, args.source)
    try:
        info = market.info
        console.print(f"token   {info.address}\nsymbol  {info.symbol} {info.name}\nsource  {info.source} (prices in {info.quote})")
        console.print(f"pool    {info.pool or '—'} ({info.dex or '?'})")
        for note in info.notes:
            console.print(f"note    {note}")
        if market.history is not None:
            candles = await market.history()
            if candles:
                last = candles[-1]
                console.print(
                    f"history {len(candles)} {format_timeframe(timeframe)} candles, last close {fmt_price(last.close)} {info.quote} "
                    f"at {datetime.fromtimestamp(last.start):%Y-%m-%d %H:%M}"
                )
            else:
                console.print("history none returned")
    finally:
        await market.aclose()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(args.func(args))
    except KeyboardInterrupt:
        return 130
    except (MarketNotFound, ApiError, ValueError) as exc:
        print(f"tartar: {exc}", file=sys.stderr)
        return 2
