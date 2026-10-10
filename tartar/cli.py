"""Command line: tartar watch | new | backtest | demo | resolve | record | collect | simulate | train | profit | decide | fast | review."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from contextlib import aclosing
from datetime import datetime, timezone
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

from . import __version__
from .agent import CandleAgent, FeedEnded, Sink
from .backtest import backtest
from .candles import Tick, format_timeframe, load_csv, parse_timeframe
from .clock import SimClock
from .dashboard import Dashboard
from .feeds.geckoterminal import GeckoTerminal
from .feeds.http import ApiError
from .feeds.pumpchain import stream_program_events
from .feeds.pumpportal import stream_new_tokens
from .scam import CreatorIndex, assess, static_checks, static_checks_many
from .screen import next_clean_launch
from .feeds.synthetic import SimulatedToken, SyntheticFeed
from .model.global_model import MODEL_DIR, GlobalModel, find_model, model_dir, model_name
from .market import SOURCES, Market, MarketInfo, MarketNotFound, launch_market, open_market, short
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
    p.add_argument("--model-dir", help=f"where trained global models live (default {MODEL_DIR})")
    p.add_argument("--no-model", action="store_true", help="ignore trained global models; online model only")


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
    watch.add_argument("--screen", type=float, default=20.0, help="--next-launch: seconds to observe each launch before choosing (default 20)")
    watch.add_argument("--min-buyers", type=int, default=3, help="--next-launch: buyers besides the creator needed during screening")
    watch.add_argument("--allow-risky", action="store_true", help="--next-launch: don't skip launches flagged danger/scam")
    watch.add_argument("--no-scam-check", action="store_true", help="skip the RugCheck/mint checks (behavioural flags still shown)")
    watch.add_argument("--creators", default="data/raw", help="recorded raw logs used for creator history (default data/raw, if present)")
    _add_output_args(watch)
    watch.set_defaults(func=cmd_watch)

    new = sub.add_parser("new", help="list newly launched Solana tokens")
    new.add_argument("--source", choices=("gecko", "pumpportal"), default="gecko", help="gecko: newest pools; pumpportal: live pump.fun launches")
    new.add_argument("--limit", type=int, default=20)
    new.add_argument("--safe", action="store_true", help="gecko: run scam checks and hide tokens flagged danger/scam")
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

    scan = sub.add_parser("scan", help="scam check a token: mint, RugCheck, creator history and recorded trading")
    scan.add_argument("address")
    scan.add_argument("--creators", default="data/raw", help="recorded raw logs for creator history and trading (default data/raw)")
    scan.set_defaults(func=cmd_scan)

    resolve = sub.add_parser("resolve", help="show which pool, source and history 'watch' would use")
    resolve.add_argument("address")
    resolve.add_argument("-t", "--timeframe", default="1m")
    resolve.add_argument("--source", choices=SOURCES, default="auto")
    resolve.set_defaults(func=cmd_resolve)

    record = sub.add_parser("record", help="record every new pump.fun launch and its trades (training data)")
    record.add_argument("--out", default="data/raw", help="directory for raw logs (default data/raw)")
    record.add_argument("--hours", type=float, help="stop after this many hours (default: until Ctrl+C)")
    record.add_argument("--track-minutes", type=float, default=60.0, help="record each token for this long (default 60)")
    record.add_argument("--idle-minutes", type=float, default=10.0, help="stop recording a token after this long without trades")
    record.add_argument("--max-tokens", type=int, default=3000, help="most tokens tracked at once")
    record.add_argument("--pumpswap-hours", type=float, default=0.0, help="also record each graduated token's PumpSwap pool for this long (chain source; default off)")
    record.add_argument("--revive-hours", type=float, default=0.0, help="keep idle or aged tokens dormant until this long after launch and record them again when they trade (chain source; default off)")
    record.add_argument("--dormant", help="JSON file of dormant tokens: read at start if present, written every 10 min and at the end (with --revive-hours)")
    record.add_argument(
        "--source",
        choices=("chain", "pumpportal"),
        default="chain",
        help="chain: Solana RPC logs (free, default); pumpportal: needs PUMPPORTAL_API_KEY funded with SOL",
    )
    record.set_defaults(func=cmd_record)

    collect = sub.add_parser("collect", help="download OHLCV histories of new Solana pools (training data)")
    collect.add_argument("--out", default="data/ohlcv", help="directory (default data/ohlcv; a subfolder per timeframe)")
    collect.add_argument("-t", "--timeframe", default="1m")
    collect.add_argument("--pages", type=int, default=10, help="pages of 20 new pools (default 10)")
    collect.add_argument("--interval", type=float, default=6.5, help="seconds between API requests (default 6.5)")
    collect.set_defaults(func=cmd_collect)

    simulate = sub.add_parser("simulate", help="write simulated pump.fun launches in the recorder's format")
    simulate.add_argument("--out", default="data/sim")
    simulate.add_argument("--tokens", type=int, default=500)
    simulate.add_argument("--seed", type=int, default=0)
    simulate.set_defaults(func=cmd_simulate)

    train = sub.add_parser("train", help="train and evaluate the global model on recorded data")
    data = train.add_mutually_exclusive_group(required=True)
    data.add_argument("--raw", help="raw trade logs from `tartar record` (or `tartar simulate`); comma-separate one directory per recorder")
    data.add_argument("--ohlcv", help="OHLCV files from `tartar collect` (the timeframe's subfolder)")
    train.add_argument("-t", "--timeframe", default="1m")
    train.add_argument("--out", help=f"model directory (default {MODEL_DIR}, where `watch` looks)")
    train.add_argument("--rounds", type=int, default=3000, help="max boosting rounds (early stopping decides)")
    train.add_argument("--num-leaves", type=int, default=63, help="LightGBM leaves per tree (default 63)")
    train.add_argument("--min-leaf", type=int, default=100, help="LightGBM min rows per leaf (default 100)")
    train.add_argument("--replay-tokens", type=int, default=300, help="test tokens to replay through the live forecaster")
    train.add_argument("--force", action="store_true", help="replace the installed model even if it scores better")
    train.add_argument(
        "--pumpswap", action="store_true",
        help="train the model for graduated tokens on their PumpSwap pools (`watch` switches to it at graduation); "
        "needs recordings made with --pumpswap-hours",
    )  # fmt: skip
    train.add_argument(
        "--rug", action="store_true",
        help="train P(rug) instead: the chance a launch collapses (-80%%, not graduated) within 30 min, judged 20 s "
        "after launch; `watch --next-launch` shows it beside the risk level (needs --raw)",
    )  # fmt: skip
    train.set_defaults(func=cmd_train)

    profit = sub.add_parser("profit", help="net SOL of trading strategies on recorded launches, after fees, slippage and latency")
    profit.add_argument("--raw", default="data/raw", help="raw trade logs from `tartar record` (default data/raw)")
    profit.add_argument("-t", "--timeframe", default="1m")
    profit.add_argument("--size", type=float, default=0.1, help="SOL per entry (default 0.1)")
    profit.add_argument("--fee", type=float, default=1.25, help="bonding-curve fee per side, in %% (default 1.25)")
    profit.add_argument("--network", type=float, default=0.0002, help="SOL per transaction, base + priority fee (default 0.0002)")
    profit.add_argument("--latency", type=float, default=1.0, help="seconds from decision to execution (default 1.0)")
    profit.add_argument("--json", help="also write the results to this file")
    profit.set_defaults(func=cmd_profit)

    decide = sub.add_parser("decide", help="buy-or-skip scorers for new launches (rules, LightGBM, TypeSafe Jev), judged by net SOL")
    decide.add_argument("--raw", default="data/raw", help="raw trade logs from `tartar record` (default data/raw)")
    decide.add_argument("--seconds", type=float, default=20.0, help="decide this long after a launch is seen (default 20)")
    decide.add_argument("--hold", type=float, default=180.0, help="seconds to hold (default 180)")
    decide.add_argument("--take-profit", type=float, help="sell once up this many %%")
    decide.add_argument("--stop-loss", type=float, help="sell once down this many %%")
    decide.add_argument("--latency", type=float, default=1.0, help="seconds from decision to execution (default 1.0)")
    decide.add_argument("--fee", type=float, default=1.25, help="bonding-curve fee per side, in %% (default 1.25)")
    decide.add_argument("--jev", action="store_true", help="also ask TypeSafe Jev about every validation/test (and training) launch")
    decide.add_argument("--jev-cache", default="data/jev-answers.jsonl", help="where Jev's answers are cached by mint")
    decide.set_defaults(func=cmd_decide)

    fast = sub.add_parser("fast", help="the fast loop: screen each new launch, ask the scorer (rules or Jev), paper-trade it")
    fast.add_argument("--policy", default="data/policy.json", help="policy file, reloaded when it changes (created with defaults if missing)")
    fast.add_argument("--journal", default="data/journal", help="directory for the decision journal")
    fast.add_argument("--replay", help="run over recorded raw logs instead of the live chain")
    fast.add_argument("--out", default="data/raw", help="live: also record raw logs here (default data/raw)")
    fast.add_argument("--hours", type=float, help="live: stop after this many hours")
    fast.add_argument("--pumpswap-hours", type=float, default=0.0, help="live: also record each graduated token's PumpSwap pool for this long (default off)")
    fast.set_defaults(func=cmd_fast)

    rv = sub.add_parser("review", help="the slow loop's input: the fast loop's results and what every screened launch would have earned")
    rv.add_argument("--journal", default="data/journal", help="fast-loop journal directory")
    rv.add_argument("--raw", default="data/raw", help="raw logs covering the same period, for counterfactual outcomes")
    rv.add_argument("--hours", type=float, help="only the last N hours of the journal")
    rv.add_argument("--markdown", help="write the review as Markdown to this file")
    rv.add_argument("--json", help="write the full review as JSON to this file")
    rv.set_defaults(func=cmd_review)

    learn = sub.add_parser("learn", help="record continuously and retrain the global model on a schedule")
    learn.add_argument("--out", default="data/raw", help="directory for raw logs (default data/raw)")
    learn.add_argument("-t", "--timeframe", default="1m")
    learn.add_argument("--first-train-hours", type=float, default=3.0, help="hours of recording before the first training")
    learn.add_argument("--retrain-hours", type=float, default=6.0, help="hours between retrainings")
    learn.add_argument("--model-dir", help=f"where to install models (default {MODEL_DIR})")
    learn.set_defaults(func=cmd_learn)
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


def _load_model(market: Market, args, timeframe: int) -> GlobalModel | None:
    if args.no_model:
        return None
    model = find_model(market.info.domain, timeframe, args.model_dir, allow_simulated=market.info.source == "simulated")
    if model is None:
        market.info.notes.append(
            f"no trained global model for {market.info.domain} data at {format_timeframe(timeframe)} "
            "(see `tartar record` / `tartar train`); using the per-token online model only"
        )
    else:
        meta = model.meta
        market.info.notes.append(
            f"global model {model_name(model.domain, model.timeframe)}: trained on {meta.get('tokens', '?')} tokens, {meta.get('trained_at', '?')}"
        )
    return model


def _creator_index(path: str | None) -> CreatorIndex | None:
    if not path or not Path(path).exists():
        return None
    return CreatorIndex.from_raw(path)


async def _run_agent(market: Market, args, timeframe: int, creators: CreatorIndex | None = None, p_rug: float | None = None) -> None:
    console = Console()
    model = _load_model(market, args, timeframe)
    sinks, interval = _make_sinks(args, console)
    simulated = market.info.source == "simulated"
    if creators is None and not simulated:
        creators = _creator_index(getattr(args, "creators", None))
    agent = CandleAgent(
        market,
        timeframe,
        coverage=args.band,
        sinks=sinks,
        update_interval=interval,
        model=model,
        scam_checks=not simulated and not getattr(args, "no_scam_check", False),
        creators=creators,
        after_graduation=None if args.no_model or simulated else lambda: find_model("pumpswap", timeframe, args.model_dir),
        p_rug=p_rug,
    )
    try:
        await agent.run(max_candles=args.candles)
    except FeedEnded:
        Console(stderr=True).print(f"The feed ended: {agent.status_message}")
    finally:
        await market.aclose()
        for sink in sinks:
            if isinstance(sink, JsonLines) and sink.stream is not sys.stdout:
                sink.stream.close()


async def cmd_watch(args) -> int:
    timeframe = parse_timeframe(args.timeframe)
    if args.next_launch:
        err = Console(stderr=True)
        creators = _creator_index(args.creators) or CreatorIndex()
        err.print(
            f"Waiting for the next pump.fun launch that passes scam screening "
            f"({args.screen:g}s observation, ≥{args.min_buyers} buyers{', risky allowed' if args.allow_risky else ''})…"
        )

        from .rug import find_rug_model

        rug_model = None if args.no_model else find_rug_model(args.model_dir)
        if rug_model is not None and abs(rug_model.meta.get("screen", 20.0) - args.screen) > 1e-9:
            err.print(f"[dim]P(rug) was trained on launches judged at +{rug_model.meta.get('screen', 20.0):g}s; at +{args.screen:g}s treat it as rough[/dim]")

        def show(verdict) -> None:
            c = verdict.candidate.create
            mark = "[green]✓[/green]" if verdict.passed else "[dim]✗[/dim]"
            p_rug = f"P(rug) {verdict.p_rug:4.0%}  " if verdict.p_rug is not None else ""
            err.print(f"{mark} {c.symbol[:12]:<12} {c.mint[:6]}…  {p_rug}{verdict.reason}", highlight=False)

        stream = stream_program_events()
        verdict = await next_clean_launch(
            stream, screen_seconds=args.screen, min_buyers=args.min_buyers, allow_risky=args.allow_risky, creators=creators, on_verdict=show,
            rug_model=rug_model,
        )  # fmt: skip
        c = verdict.candidate.create
        err.print(f"Watching [bold]{c.symbol}[/bold] {c.name} {c.mint}")
        market = launch_market(
            c.mint,
            symbol=c.symbol,
            name=c.name,
            creator=c.creator,
            launched_at=verdict.candidate.seen_at,
            uri=c.uri,
            initial=verdict.candidate.ticks,
            stream=stream,
        )
        await _run_agent(market, args, timeframe, creators, p_rug=verdict.p_rug)
        return 0
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
    token = SimulatedToken(clock.now(), history_minutes=args.history * timeframe / 60, seed=args.seed)
    history = token.history(timeframe, clock.now())

    async def load_history():
        return history

    info = MarketInfo(
        address=token.mint,
        symbol=token.symbol,
        name="simulated pump.fun token",
        quote="SOL",
        source="simulated",
        dex="pumpfun",
        notes=[f"simulated bonding-curve trades at {args.speed:g}x speed, not real market data"],
        launched_at=token.created,
        creator=token.creator,
    )
    await _run_agent(Market(info, SyntheticFeed(token, clock), load_history, clock), args, timeframe)
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
    pools = pools[: args.limit]
    risks = {}
    if args.safe:
        console.print(f"scam-checking {len(pools)} tokens…")
        creators = _creator_index("data/raw")
        statics = await static_checks_many([p.base_token for p in pools])
        risks = {mint: assess(None, static, creators, mint=mint) for mint, static in statics.items()}
    table = Table(title="Newest Solana pools (GeckoTerminal)", box=box.SIMPLE_HEAD)
    cols = ("age", "symbol", "name", "token mint", "dex", "liquidity", "24h vol") + (("risk",) if args.safe else ())
    for col in cols:
        table.add_column(col, justify="right" if col in ("age", "liquidity", "24h vol") else "left", no_wrap=col == "token mint")
    hidden = 0
    for pool in pools:
        risk = risks.get(pool.base_token)
        if risk is not None and risk.is_scam_or_danger:
            hidden += 1
            continue
        row = [_age(pool.created_at), pool.base_symbol, pool.base_name[:24], pool.base_token, pool.dex, _usd(pool.reserve_usd), _usd(pool.volume_24h_usd)]
        if args.safe:
            row.append(f"{risk.level}: {risk.summary(2)}" if risk else "—")
        table.add_row(*row)
    console.print(table)
    if hidden:
        console.print(f"hid {hidden} token(s) flagged danger or scam")
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


async def cmd_record(args) -> int:
    from .data.recorder import ChainRecorder, Recorder

    console = Console()
    if args.source == "chain":
        dormant = {}
        if args.dormant and Path(args.dormant).exists():
            dormant = {m: (float(v[0]), str(v[1])) for m, v in json.loads(Path(args.dormant).read_text()).items()}
        recorder = ChainRecorder(
            args.out, track_minutes=args.track_minutes, idle_minutes=args.idle_minutes, max_tokens=args.max_tokens,
            pumpswap_hours=args.pumpswap_hours, revive_hours=args.revive_hours, dormant=dormant,
        )  # fmt: skip
        if args.revive_hours > 0:
            console.print(f"revival on: {len(recorder.dormant)} dormant tokens carried over, kept {args.revive_hours:g} h after launch")
        recorder.on_status = lambda message: console.print(f"{datetime.now():%H:%M:%S}  ! {message}")
    else:
        recorder = Recorder(args.out, track_minutes=args.track_minutes, idle_minutes=args.idle_minutes, max_tokens=args.max_tokens)
    console.print(f"Recording pump.fun launches and trades to {args.out} (Ctrl+C to stop)…")

    saved = [time.time()]

    def save_dormant() -> None:
        if args.dormant and getattr(recorder, "revive_seconds", 0) > 0:
            tmp = Path(args.dormant + ".tmp")
            tmp.write_text(json.dumps(recorder.dormant_state()))
            tmp.replace(args.dormant)
            saved[0] = time.time()

    def report(stats) -> None:
        if time.time() - saved[0] >= 600:
            save_dormant()
        state = "connected" if stats.connected else "reconnecting"
        pools = f" · {len(recorder.pools)} PumpSwap pools, {recorder.swaps} swaps" if getattr(recorder, "pumpswap_seconds", 0) else ""
        console.print(f"{datetime.now():%H:%M:%S}  {state} · {stats.tracked} tokens tracked · {stats.total_tokens} launches · {stats.trades} trades{pools}")

    try:
        stats = await recorder.run(None if args.hours is None else args.hours * 3600, on_stats=report)
    finally:
        save_dormant()
    report(stats)
    return 0


async def cmd_collect(args) -> int:
    from .data.collect import collect_ohlcv

    timeframe = parse_timeframe(args.timeframe)
    out = f"{args.out}/{format_timeframe(timeframe)}"
    console = Console()
    written = await collect_ohlcv(out, timeframe, pages=args.pages, interval=args.interval, progress=console.print)
    console.print(f"saved {written} token histories to {out}")
    return 0


async def cmd_simulate(args) -> int:
    from .data.simulate import simulate_raw

    path = simulate_raw(args.out, args.tokens, seed=args.seed)
    Console().print(f"wrote {path} (simulated data: useful for testing the pipeline, not for real accuracy)")
    return 0


def _metric(v, pct: bool = False, signed: bool = False) -> str:
    if v is None:
        return "—"
    if signed:
        return f"{100 * v:+.1f}%"
    return f"{100 * v:.1f}%" if pct else f"{v:.2f}"


async def cmd_train(args) -> int:
    import json
    from pathlib import Path

    from .data.dataset import build_dataset, load_ohlcv_tokens, load_pumpswap_tokens, load_trade_tokens
    import numpy as np

    from .train import evaluate, test_log_loss, train_global

    if args.rug:
        return _train_rug(args)
    timeframe = parse_timeframe(args.timeframe)
    console = Console()
    if args.pumpswap and not args.raw:
        raise SystemExit("--pumpswap needs --raw (recordings made with --pumpswap-hours)")
    domain = "pumpswap" if args.pumpswap else "trades" if args.raw else "ohlcv"
    console.print(f"loading {domain} data…")
    if domain == "pumpswap":
        tokens = load_pumpswap_tokens(args.raw, timeframe)
    else:
        tokens = load_trade_tokens(args.raw, timeframe) if args.raw else load_ohlcv_tokens(args.ohlcv, timeframe)
    if len(tokens) < 20:
        raise SystemExit(f"only {len(tokens)} usable tokens; record more data first")
    ds = build_dataset(tokens, timeframe, domain)
    console.print(f"{len(tokens)} tokens → {len(ds)} rows")
    captures = [t.capture for t in tokens if t.capture is not None]
    if captures and float(np.median(captures)) < 0.9:
        console.print(
            f"[yellow]data capture: a median {float(np.median(captures)):.0%} of each token's trades were recorded "
            "(the free public RPC drops notifications; set SOLANA_RPC_WS to a private endpoint for complete data)[/yellow]"
        )
    if len(tokens) < 500:
        console.print("[yellow]fewer than 500 tokens: expect noisy estimates; keep recording for a better model[/yellow]")
    if ds.simulated and args.out is None:
        raise SystemExit("this is simulated data; pass --out DIR so the model is not used for real tokens")

    model = train_global(ds, rounds=args.rounds, num_leaves=args.num_leaves, min_data_in_leaf=args.min_leaf, log=console.print)
    report = evaluate(model, ds, replay_tokens=args.replay_tokens, log=console.print)
    target = model_dir(args.out) / model_name(domain, timeframe)
    report["test_log_loss"] = new_loss = test_log_loss(model, ds)
    if target.with_suffix(".txt").exists() and not args.force:
        try:
            old_loss = test_log_loss(GlobalModel.load(target), ds)
        except Exception:  # unreadable or incompatible: replace it
            old_loss = None
        if old_loss is not None and old_loss <= new_loss:
            console.print(
                f"[yellow]kept the installed model: it scores better on these test tokens "
                f"(log loss {old_loss:.4f} vs {new_loss:.4f}); use --force to replace it[/yellow]"
            )
            return 0
        if old_loss is not None:
            console.print(f"new model beats the installed one (log loss {new_loss:.4f} vs {old_loss:.4f})")
    path = model.save(target)
    path.with_suffix(".report.json").write_text(json.dumps(report, indent=2))

    table = Table(title=f"Test set: {report['test_rows']} rows from the latest-launched tokens", box=box.SIMPLE_HEAD)
    for col in ("candle elapsed", "hit", "stated", "80% band", "band states", "band width", "error", "naive", "edge", "info gain"):
        table.add_column(col, justify="right")
    for row in report["test_by_fraction"]:
        table.add_row(
            f"{row['f']:.0%}",
            _metric(row["hit_rate"], pct=True),
            _metric(row["avg_confidence"], pct=True),
            _metric(row["band_coverage"], pct=True),
            _metric(row.get("band_stated"), pct=True),
            f"{row['band_width_pct']:.2f}%",
            f"{row['mae_pct']:.2f}%",
            f"{row['naive_mae_pct']:.2f}%",
            _metric(row["edge"], signed=True),
            f"{row.get('info_gain_bits', 0):.3f} bits",
        )
    console.print(table)
    live = report["live_at_open"]
    cmp = Table(title=f"Live forecaster replayed on {live['tokens']} test tokens (forecasts locked at candle open)", box=box.SIMPLE_HEAD)
    for col in ("", "candles", "hit", "stated", "80% band", "band states", "edge vs naive"):
        cmp.add_column(col, justify="right")
    for name, key in (("online only", "online_only"), ("global + online", "global_plus_online")):
        for subset in ("all", "trading"):
            t = live[key][subset]
            cmp.add_row(
                f"{name} · {subset}", str(t["n"]), _metric(t["hit_rate"], pct=True), _metric(t["avg_confidence"], pct=True),
                _metric(t["band_coverage"], pct=True), _metric(t.get("band_stated"), pct=True), _metric(t["edge"], signed=True),
            )  # fmt: skip
    console.print(cmp)
    console.print(
        "[dim]'band states' is the probability the forecasts put inside their 80% bands: when 'no further trade' alone "
        "is likelier than 80%, the band is the current price and covers that whole mass, so compare coverage with it.[/dim]"
    )
    top = ", ".join(f"{k} {v:.0%}" for k, v in list(report["feature_importance"].items())[:10])
    console.print(f"top features: {top}")
    console.print(f"saved {path} (+ .json metadata, .report.json)")
    return 0


def _train_rug(args) -> int:
    import json

    from .rug import RugModel, labelled_states, rug_model_name, rug_report, train_rug

    console = Console()
    if not args.raw:
        raise SystemExit("--rug needs --raw (recordings from `tartar record`)")
    console.print("replaying launches (screen every launch at +20 s, outcome 30 min later)…")
    rows = labelled_states(args.raw)
    if len(rows) < 200:
        raise SystemExit(f"only {len(rows)} launches with a recorded outcome; record more data first")
    if any(r["simulated"] for r in rows) and args.out is None:
        raise SystemExit("this is simulated data; pass --out DIR so the model is not used for real tokens")
    model, report = train_rug(rows, log=console.print)
    target = model_dir(args.out) / rug_model_name()
    new_loss = report["test"]["log_loss"]
    if target.with_suffix(".txt").exists() and not args.force:
        try:
            old_loss = rug_report(RugModel.load(target), rows)["test"]["log_loss"]
        except Exception:  # unreadable or incompatible: replace it
            old_loss = None
        if old_loss is not None and old_loss <= new_loss:
            console.print(f"[yellow]kept the installed P(rug) model: it scores better on these test launches (log loss {old_loss:.4f} vs {new_loss:.4f}); use --force to replace it[/yellow]")
            return 0
        if old_loss is not None:
            console.print(f"new P(rug) model beats the installed one (log loss {new_loss:.4f} vs {old_loss:.4f})")
    path = model.save(target)
    path.with_suffix(".report.json").write_text(json.dumps(report, indent=2))
    t = report["test"]
    n = report["launches"]
    console.print(
        f"test: {n['test']} latest launches (train {n['train']}, validation {n['valid']}), rug rate {100 * report['base_rate']['test']:.1f}%\n"
        f"  AUC {t['auc']:.3f} (risk level alone {t['auc_risk_level']:.3f}); log loss {t['log_loss']:.4f} "
        f"(uncalibrated {t['log_loss_uncalibrated']:.4f}, base rate {t['log_loss_base_rate']:.4f}); Brier {t['brier']:.4f}"
    )
    console.print("  by decile of P(rug), predicted → observed: " + ", ".join(f"{100 * d['predicted']:.0f}→{100 * d['observed']:.0f}%" for d in t["deciles"]))
    console.print("  by risk level: " + ", ".join(f"{k} {100 * v['share']:.0f}% of launches, rug {100 * v['rug_rate']:.1f}%" for k, v in t["by_level"].items()))
    console.print("  top features: " + ", ".join(f"{k} {v:.0%}" for k, v in list(report["feature_gain"].items())[:6]))
    console.print(f"saved {path} (+ .json metadata, .report.json)")
    return 0


async def cmd_profit(args) -> int:
    import json

    from .data.dataset import build_dataset, load_trade_tokens
    from .profit import Costs, profit_report

    timeframe = parse_timeframe(args.timeframe)
    console = Console()
    costs = Costs(size_sol=args.size, fee=args.fee / 100, network_sol=args.network, latency=args.latency)
    console.print("loading trade data…")
    tokens = load_trade_tokens(args.raw, timeframe)
    if len(tokens) < 20:
        raise SystemExit(f"only {len(tokens)} usable tokens; record more data first")
    ds = build_dataset(tokens, timeframe, "trades")
    model = find_model("trades", timeframe, allow_simulated=ds.simulated)
    rows = profit_report(ds, costs, model)
    title = (
        f"Net results per trade: {args.size:g} SOL, fee {args.fee:g}%/side, {args.network:g} SOL/tx, "
        f"{args.latency:g}s latency ({len(tokens)} launches; validation = earlier, test = latest)"
    )
    table = Table(title=title, box=box.SIMPLE_HEAD)
    for col in ("strategy", "exit", "split", "trades", "mean", "90% CI (by token)", "win", "total SOL"):
        table.add_column(col, justify="left" if col in ("strategy", "exit") else "right", no_wrap=True)
    for r in rows:
        ci = f"{100 * r['ci_low']:+.1f}% … {100 * r['ci_high']:+.1f}%" if r["trades"] else "—"
        table.add_row(
            r["strategy"], r["exit"], r["split"], str(r["trades"]),
            _metric(r["mean_ret"], signed=True) if r["trades"] else "—", ci,
            _metric(r["win_rate"], pct=True) if r["trades"] else "—", f"{r['total_sol']:+.3f}",
        )  # fmt: skip
    console.print(table)
    if any(r["split"] == "test" and r["trades"] and r["ci_low"] > 0 for r in rows):
        console.print("a strategy's whole 90% interval is above zero on the test launches; confirm on new recordings before trusting it")
    else:
        console.print("[yellow]no strategy is reliably profitable on the test launches at these costs[/yellow]")
    if args.json:
        Path(args.json).write_text(json.dumps({"costs": costs.__dict__, "results": rows}, indent=2))
    return 0


async def cmd_decide(args) -> int:
    import numpy as np

    from .data.dataset import load_trade_tokens
    from .decide import FlagScorer, FunctionScorer, LightGBMScorer, evaluate, launch_states
    from .profit import Costs, Exit, curves_for, label_round_trips

    console = Console()
    costs = Costs(fee=args.fee / 100, latency=args.latency)
    rule = Exit(
        args.hold,
        None if args.take_profit is None else args.take_profit / 100,
        None if args.stop_loss is None else args.stop_loss / 100,
    )
    console.print("loading trade data…")
    tokens = load_trade_tokens(args.raw, 60)
    if len(tokens) < 50:
        raise SystemExit(f"only {len(tokens)} usable tokens; record more data first")
    curves = curves_for(tokens)
    states = launch_states(tokens, curves, args.seconds)
    n = len(states)
    split = np.where(np.arange(n) < 0.7 * n, 0, np.where(np.arange(n) < 0.85 * n, 1, 2))  # states are in launch order
    token = np.array([s["token"] for s in states])
    when = np.array([s["decide_at"] for s in states])
    labels = label_round_trips(curves, token, when, costs, rule)
    train = [s for s, p in zip(states, split) if p == 0]
    valid = [s for s, p in zip(states, split) if p == 1]
    scorers = [
        FunctionScorer("buy every launch", lambda s: 1.0),
        FunctionScorer("pass the --next-launch screen", lambda s: float(s["buyers"] >= 3 and not s["avoid"])),
        FlagScorer(train, labels[split == 0]),
        LightGBMScorer(train, labels[split == 0], valid, labels[split == 1]),
    ]
    jev = None
    if args.jev:
        from .jev import FEATURES as JEV_FEATURES
        from .jev import JevClient, JevScorer

        jev = JevClient(cache=args.jev_cache)
        console.print(f"asking Jev about {len(states)} launches (cached in {args.jev_cache})…")
        jev.ask_many(states)
        scorers.append(JevScorer(jev))
        scorers.append(
            LightGBMScorer(train, labels[split == 0], valid, labels[split == 1], extra=jev.features, extra_names=JEV_FEATURES, name="lightgbm + jev judgments")
        )
    else:
        console.print("[dim]add --jev to include TypeSafe Jev[/dim]")
    table = Table(
        title=f"Buy {args.seconds:g}s after launch, {rule.label()}, fee {args.fee:g}%/side, {args.latency:g}s latency: "
        f"{int((split == 1).sum())} validation / {int((split == 2).sum())} test launches",
        box=box.SIMPLE_HEAD,
    )
    for col in ("scorer", "kept", "valid mean", "test trades", "test mean", "test 90% CI", "test SOL"):
        table.add_column(col, justify="left" if col == "scorer" else "right", no_wrap=True)
    for scorer in scorers:
        r = evaluate(scorer, states, split, curves, costs, rule)
        if r["threshold"] is None:
            table.add_row(scorer.name, "—", "—", "0", "—", "—", "—")
            continue
        v, t = r["valid"], r["test"]
        table.add_row(
            scorer.name, f"{100 * r['kept_share_valid']:.0f}%", _metric(v["mean_ret"], signed=True), str(t["trades"]),
            _metric(t["mean_ret"], signed=True) if t["trades"] else "—",
            f"{100 * t['ci_low']:+.1f}% … {100 * t['ci_high']:+.1f}%" if t["trades"] else "—", f"{t['total_sol']:+.3f}",
        )  # fmt: skip
    console.print(table)
    console.print(f"flags that lost on train launches: {', '.join(scorers[2].bad) or 'none'}")
    if jev is not None:
        console.print(f"Jev: {jev.latency_summary() or 'all answers from cache'}")
        top = ", ".join(f"{k} {v:.0%}" for k, v in list(scorers[-1].importance().items())[:8])
        console.print(f"lightgbm + jev judgments, top features: {top}")
    return 0


async def cmd_fast(args) -> int:
    from .fastloop import FastLoop, InlineDecider, Journal, PolicyFile, ThreadDecider, jev_factory_from_env, replay, shadow_factory
    from .scam import CreatorIndex

    console = Console()
    policy = PolicyFile(args.policy)
    p = policy.policy
    jev = jev_factory_from_env(p.scorer_timeout)
    console.print(
        f"policy {args.policy}: scorer {p.scorer}, screen {p.screen_seconds:g}s, threshold {p.threshold:g}, "
        f"skip flags {', '.join(p.skip_flags) or 'none'}, {p.exit_rule().label()}, paper size {p.size_sol:g} SOL"
    )
    if args.replay:
        loop = FastLoop(
            policy, Journal(args.journal), jev_factory=jev, decider_factory=lambda scorer: InlineDecider(scorer), shadow_factory=shadow_factory(threaded=False)
        )
        summary = replay(args.replay, loop)
    else:
        from .data.recorder import ChainRecorder

        creators = CreatorIndex.from_raw(args.out)
        loop = FastLoop(
            policy, Journal(args.journal), jev_factory=jev, decider_factory=lambda scorer: ThreadDecider(scorer), creators=creators, shadow_factory=shadow_factory()
        )
        recorder = ChainRecorder(args.out, track_minutes=90, idle_minutes=20, pumpswap_hours=args.pumpswap_hours)
        recorder.on_event = loop.on_event
        recorder.on_status = lambda message: console.print(f"[yellow]{message}[/yellow]")
        loop.start(time.time())

        async def tick() -> None:
            while True:
                await asyncio.sleep(0.25)
                loop.advance(time.time())

        import signal

        ticker = asyncio.create_task(tick())
        running = asyncio.create_task(recorder.run(None if args.hours is None else args.hours * 3600))
        # SIGTERM ends the run cleanly: positions are closed and a summary is journaled.
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, running.cancel)
        try:
            await running
        except asyncio.CancelledError:
            pass
        finally:
            ticker.cancel()
            summary = loop.finish(time.time())
    mean = summary["mean_ret"]
    console.print(
        f"launches {summary['launches']}, screened {summary['screened']}, skipped {summary['skipped']}, asked {summary['asked']}, "
        f"paper buys {summary['buys']}, scorer errors {summary['errors']}, Jev shadow answers {summary.get('shadow', 0)}; "
        f"closed trades {summary['trades']}, "
        f"net {summary['pnl_sol']:+.3f} SOL" + (f" ({100 * mean:+.2f}% per trade)" if mean is not None else "")
    )
    console.print(f"journal in {args.journal}; review it with `tartar review`")
    return 0


async def cmd_review(args) -> int:
    import json

    from .review import load_journal, review, to_markdown

    since = None if args.hours is None else time.time() - args.hours * 3600
    records = load_journal(args.journal, since=since)
    if not records:
        raise SystemExit(f"no journal records in {args.journal}")
    raw = args.raw if args.raw and Path(args.raw).exists() else None
    result = review(records, raw)
    text = to_markdown(result)
    print(text)
    if args.markdown:
        Path(args.markdown).write_text(text)
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, default=str))
    return 0


async def cmd_learn(args) -> int:
    """Record without pause; retrain in a separate process so recording never stalls."""
    from .data.recorder import ChainRecorder

    console = Console()
    recorder = ChainRecorder(args.out, max_tokens=3000)
    record_task = asyncio.create_task(recorder.run(on_stats=lambda st: console.print(
        f"{datetime.now():%H:%M:%S}  recording · {st.tracked} tracked · {st.total_tokens} launches · {st.trades} trades"
    )))
    console.print(f"Learning: recording to {args.out}; first training in {args.first_train_hours:g}h, then every {args.retrain_hours:g}h.")
    wait = args.first_train_hours * 3600
    try:
        while True:
            done, _ = await asyncio.wait({record_task}, timeout=wait)
            if done:
                record_task.result()
                return 1
            cmd = [sys.executable, "-m", "tartar", "train", "--raw", args.out, "-t", args.timeframe]
            if args.model_dir:
                cmd += ["--out", args.model_dir]
            console.print(f"{datetime.now():%H:%M:%S}  retraining…")
            proc = await asyncio.create_subprocess_exec(*cmd)
            await proc.wait()
            console.print(f"{datetime.now():%H:%M:%S}  training finished (exit {proc.returncode})")
            wait = args.retrain_hours * 3600
    finally:
        record_task.cancel()
        await asyncio.gather(record_task, return_exceptions=True)


async def cmd_scan(args) -> int:
    """Everything known about a token's scam risk, without watching it."""
    from .data.dataset import load_trade_tokens
    from .scam import WalletTracker

    console = Console()
    mint = args.address.strip()
    console.print(f"Scanning {mint}…")
    static = await static_checks(mint)
    creators = _creator_index(args.creators)
    tracker = None
    creator = name = symbol = uri = ""
    if creators is not None and mint in creators.mint_creator:
        creator = creators.mint_creator[mint]
        for token in load_trade_tokens(args.creators, 60):
            if token.mint == mint:
                tracker = WalletTracker(token.created)
                for tick in sorted((t for group in token.ticks.values() for t, _ in group), key=lambda t: t.ts):
                    tracker.update(tick)
                break
    rc = static.rugcheck or {}
    meta = (rc.get("tokenMeta") or {})
    name, symbol = meta.get("name") or "", meta.get("symbol") or ""
    uri = meta.get("uri") or ""
    report = assess(tracker, static, creators, mint=mint, creator=creator or rc.get("creator"), name=name, symbol=symbol, uri=uri)
    style = {"ok": "green", "caution": "yellow", "danger": "red", "scam": "bold red", "unknown": "dim"}[report.level]
    console.print(f"[{style}]{report.level.upper()}[/{style}]  {symbol} {name}")
    for f in report.flags:
        console.print(f"  [{'red' if f.severity != 'caution' else 'yellow'}]{f.severity:>7}[/] {f.message}")
    if not report.flags:
        console.print("  no red flags found")
    facts = []
    if static.token_program:
        facts.append(f"mint authority {'set' if static.mint_authority else 'revoked'}, freeze authority {'set' if static.freeze_authority else 'revoked'}")
    if rc:
        facts.append(f"RugCheck score {rc.get('score_normalised')}, holders {rc.get('totalHolders')}, insiders {rc.get('graphInsidersDetected') or 0}")
    if tracker is not None:
        facts.append(f"recorded: {tracker.trades} trades, {tracker.holders} holders")
    for fact in facts:
        console.print(f"  [dim]{fact}[/dim]")
    for error in static.errors:
        console.print(f"  [yellow]note: {error}[/yellow]")
    return 0 if report.level not in ("danger", "scam") else 3
