"""Command line: tartar watch | new | backtest | demo | resolve | record | collect | simulate | train."""

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
from .agent import CandleAgent, FeedEnded, Sink
from .backtest import backtest
from .candles import Tick, format_timeframe, load_csv, parse_timeframe
from .clock import SimClock
from .dashboard import Dashboard
from .feeds.geckoterminal import GeckoTerminal
from .feeds.http import ApiError
from .feeds.pumpchain import ChainCreate, ChainTrade, create_to_message, stream_program_events
from .feeds.pumpportal import stream_new_tokens, tick_from_message
from .feeds.synthetic import SimulatedToken, SyntheticFeed
from .model.global_model import MODEL_DIR, GlobalModel, find_model, model_name
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

    record = sub.add_parser("record", help="record every new pump.fun launch and its trades (training data)")
    record.add_argument("--out", default="data/raw", help="directory for raw logs (default data/raw)")
    record.add_argument("--hours", type=float, help="stop after this many hours (default: until Ctrl+C)")
    record.add_argument("--track-minutes", type=float, default=60.0, help="record each token for this long (default 60)")
    record.add_argument("--idle-minutes", type=float, default=10.0, help="stop recording a token after this long without trades")
    record.add_argument("--max-tokens", type=int, default=3000, help="most tokens tracked at once")
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
    data.add_argument("--raw", help="raw trade logs from `tartar record` (or `tartar simulate`)")
    data.add_argument("--ohlcv", help="OHLCV files from `tartar collect` (the timeframe's subfolder)")
    train.add_argument("-t", "--timeframe", default="1m")
    train.add_argument("--out", help=f"model directory (default {MODEL_DIR}, where `watch` looks)")
    train.add_argument("--rounds", type=int, default=3000, help="max boosting rounds (early stopping decides)")
    train.add_argument("--replay-tokens", type=int, default=300, help="test tokens to replay through the live forecaster")
    train.add_argument("--force", action="store_true", help="replace the installed model even if it scores better")
    train.set_defaults(func=cmd_train)

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


async def _run_agent(market: Market, args, timeframe: int) -> None:
    console = Console()
    model = _load_model(market, args, timeframe)
    sinks, interval = _make_sinks(args, console)
    agent = CandleAgent(market, timeframe, coverage=args.band, sinks=sinks, update_interval=interval, model=model)
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
        err.print("Waiting for the next pump.fun launch on-chain…")
        stream = stream_program_events()
        create = first = None
        async for item in stream:
            if isinstance(item, tuple):
                events = item[2]
                create = next((e for e in events if isinstance(e, ChainCreate)), None)
                if create is not None:
                    first = next((e for e in events if isinstance(e, ChainTrade) and e.mint == create.mint), None)
                    break
        err.print(f"New launch: [bold]{create.symbol}[/bold] {create.name} {create.mint}")
        launched = time.time()
        initial = []
        if first is not None:
            initial.append(tick_from_message(create_to_message(create, first), launched, create.creator))
        market = launch_market(
            create.mint, symbol=create.symbol, name=create.name, creator=create.creator, launched_at=launched, initial=initial, stream=stream
        )
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
    try:
        await _run_agent(Market(info, SyntheticFeed(token, clock), load_history, clock), args, timeframe)
    except FeedEnded:
        Console(stderr=True).print("The simulated token stopped trading (died or graduated). Run the demo again for another.")
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


async def cmd_record(args) -> int:
    from .data.recorder import ChainRecorder, Recorder

    console = Console()
    kind = ChainRecorder if args.source == "chain" else Recorder
    recorder = kind(args.out, track_minutes=args.track_minutes, idle_minutes=args.idle_minutes, max_tokens=args.max_tokens)
    console.print(f"Recording pump.fun launches and trades to {args.out} (Ctrl+C to stop)…")

    def report(stats) -> None:
        state = "connected" if stats.connected else "reconnecting"
        console.print(f"{datetime.now():%H:%M:%S}  {state} · {stats.tracked} tokens tracked · {stats.total_tokens} launches · {stats.trades} trades")

    stats = await recorder.run(None if args.hours is None else args.hours * 3600, on_stats=report)
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

    from .data.dataset import build_dataset, load_ohlcv_tokens, load_trade_tokens
    from .train import evaluate, test_log_loss, train_global

    timeframe = parse_timeframe(args.timeframe)
    console = Console()
    domain = "trades" if args.raw else "ohlcv"
    console.print(f"loading {domain} data…")
    tokens = load_trade_tokens(args.raw, timeframe) if args.raw else load_ohlcv_tokens(args.ohlcv, timeframe)
    if len(tokens) < 20:
        raise SystemExit(f"only {len(tokens)} usable tokens; record more data first")
    ds = build_dataset(tokens, timeframe, domain)
    console.print(f"{len(tokens)} tokens → {len(ds)} rows")
    if len(tokens) < 500:
        console.print("[yellow]fewer than 500 tokens: expect noisy estimates; keep recording for a better model[/yellow]")
    if ds.simulated and args.out is None:
        raise SystemExit("this is simulated data; pass --out DIR so the model is not used for real tokens")

    model = train_global(ds, rounds=args.rounds, log=console.print)
    report = evaluate(model, ds, replay_tokens=args.replay_tokens, log=console.print)
    out_dir = Path(args.out) if args.out else MODEL_DIR
    target = out_dir / model_name(domain, timeframe)
    report["test_log_loss"] = new_loss = test_log_loss(model, ds)
    if target.with_suffix(".txt").exists() and not args.force:
        try:
            old_loss = test_log_loss(GlobalModel.load(target), ds)
        except (ValueError, OSError):
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
    for col in ("candle elapsed", "hit", "stated", "80% band", "band width", "error", "naive", "edge", "info gain"):
        table.add_column(col, justify="right")
    for row in report["test_by_fraction"]:
        table.add_row(
            f"{row['f']:.0%}",
            _metric(row["hit_rate"], pct=True),
            _metric(row["avg_confidence"], pct=True),
            _metric(row["band_coverage"], pct=True),
            f"{row['band_width_pct']:.2f}%",
            f"{row['mae_pct']:.2f}%",
            f"{row['naive_mae_pct']:.2f}%",
            _metric(row["edge"], signed=True),
            f"{row.get('info_gain_bits', 0):.3f} bits",
        )
    console.print(table)
    live = report["live_at_open"]
    cmp = Table(title=f"Live forecaster replayed on {live['tokens']} test tokens (forecasts locked at candle open)", box=box.SIMPLE_HEAD)
    for col in ("", "candles", "hit", "stated", "80% band", "edge vs naive"):
        cmp.add_column(col, justify="right")
    for name, key in (("online only", "online_only"), ("global + online", "global_plus_online")):
        for subset in ("all", "trading"):
            t = live[key][subset]
            cmp.add_row(f"{name} · {subset}", str(t["n"]), _metric(t["hit_rate"], pct=True), _metric(t["avg_confidence"], pct=True), _metric(t["band_coverage"], pct=True), _metric(t["edge"], signed=True))
    console.print(cmp)
    top = ", ".join(f"{k} {v:.0%}" for k, v in list(report["feature_importance"].items())[:10])
    console.print(f"top features: {top}")
    console.print(f"saved {path} (+ .json metadata, .report.json)")
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
