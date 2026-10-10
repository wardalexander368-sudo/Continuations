"""Training rows from recorded trades (or OHLCV histories), built with the live feature code.

For every closed candle t of every token, rows describe the state when
predicting candle t+1's close: at its open (f = 0) and, for trade data, at
several points during it (f > 0, using only trades before that moment).
Targets: whether the price still moves before the close, and by how much,
z = ln(close / price now) / (sigma * sqrt(1 - f)).
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from ..candles import Candle, CandleBook, Tick, fill_gaps
from ..feeds.pumpchain import capture_rate
from ..feeds.pumpportal import VIRTUAL_SOL
from ..model.engine import FEATURES, FeatureEngine
from ..model.global_model import z_to_class
from ..model.volatility import TRADE_DOMAINS
from ..scam import WalletTracker
from .collect import load_ohlcv_file
from .rawlog import event_price, raw_files, read_events

FRACTIONS = (0.0, 0.2, 0.4, 0.6, 0.8, 0.95)


@dataclass
class TokenData:
    mint: str
    created: float
    creator: str
    candles: list[Candle] = field(default_factory=list)
    # ticks grouped by candle start (trade data only)
    ticks: dict[int, list[tuple[Tick, bool]]] = field(default_factory=dict)
    simulated: bool = False
    capture: float | None = None  # estimated share of the token's trades that were recorded
    end: float = 0.0  # when the token's recorded window ends
    name: str = ""
    symbol: str = ""
    uri: str = ""
    end_reason: str = ""  # idle (untracked after no trades), migrated, interrupted (recording cut), or another untrack reason
    first_target: int = 1  # first candle a training row may predict (PumpSwap tokens: the first after graduation)
    launch_known: bool = True  # False when the launch wasn't recorded (`created` is then only a stand-in)
    graduated: float | None = None  # PumpSwap tokens: when the curve completed (their rows start after it)


@dataclass
class Dataset:
    timeframe: int
    domain: str
    X: np.ndarray
    label: np.ndarray  # class: 0 = no further move, else 1 + bin of z
    z: np.ndarray  # remaining normalized move (0 when still)
    f: np.ndarray  # fraction of the candle elapsed
    x0: np.ndarray  # move so far vs previous close, in sigma units
    sigma: np.ndarray
    ref: np.ndarray  # previous close
    price_now: np.ndarray
    close: np.ndarray  # actual close
    weight: np.ndarray
    token: np.ndarray  # index into tokens
    tokens: list[TokenData]
    time: np.ndarray = field(default_factory=lambda: np.zeros(0))  # moment the row's prediction is made (unix s)
    simulated: bool = False

    def __len__(self) -> int:
        return len(self.label)

    def split(self, train: float = 0.7, valid: float = 0.15) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Row masks for train/valid/test, splitting tokens by launch time (graduation time for
        PumpSwap tokens, whose rows start then) with no look-ahead."""
        order = np.argsort([t.graduated if t.graduated is not None else t.created for t in self.tokens])
        n = len(order)
        part = np.empty(n, dtype=int)
        part[order] = np.where(np.arange(n) < train * n, 0, np.where(np.arange(n) < (train + valid) * n, 1, 2))
        rows = part[self.token]
        return rows == 0, rows == 1, rows == 2


def _hash_unit(text: str, salt: str) -> float:
    digest = hashlib.blake2b(f"{salt}:{text}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


def _real_sol(event: dict) -> float:
    if event.get("rsol") is not None:
        return max(event["rsol"], 0.0)
    vsol = event.get("vsol")
    return max(vsol - VIRTUAL_SOL, 0.0) if vsol else 0.0


def tick_from_event(event: dict, creator: str) -> Tick | None:
    """A recorded create (with the creator's first buy) or trade as a tick; None without a price."""
    price = event_price(event)
    if price is None:
        return None
    sol = event.get("sol") or 0.0
    buy = event["e"] == "create" or event.get("side") == "b"
    trader = event.get("creator") if event["e"] == "create" else event.get("trader") or ""
    return Tick(
        event["t"],
        price,
        volume=sol,
        buy_volume=sol if buy else 0.0,
        sell_volume=0.0 if buy else sol,
        buys=int(buy),
        sells=int(not buy),
        trader=trader,
        creator=bool(trader) and trader == creator,
        liquidity=_real_sol(event),
        tokens=event.get("tok") or 0.0,
        virtual_sol=event.get("vsol") or 0.0,
        slot=event.get("slot"),
    )


def load_trade_tokens(raw_dir: str | Path | Sequence[str | Path], timeframe: int, max_gap: float = 10.0, min_candles: int = 3) -> list[TokenData]:
    """Group recorded events by token and rebuild each token's candles over the
    window in which its trades were completely recorded.

    `raw_dir` may name several directories (a sequence, or comma-separated): one per
    recorder, since each directory is read as one recorder's timeline. A launch two
    recorders both caught keeps the copy with the most candles.

    Tokens with fewer than `min_candles` closed candles are dropped (training needs a few).
    Trading studies should pass `min_candles=0` (keep every token with a recorded trade): the
    default drops every token that graduates within ~2 minutes of launch, which is selection
    on the outcome.
    """
    dirs = [d for d in (raw_dir.split(",") if isinstance(raw_dir, str) else raw_dir if isinstance(raw_dir, (list, tuple)) else [raw_dir]) if str(d).strip()]
    if len(dirs) > 1:
        merged: dict[str, TokenData] = {}
        for d in dirs:
            for token in load_trade_tokens(str(d).strip(), timeframe, max_gap, min_candles):
                if token.mint not in merged or len(token.candles) > len(merged[token.mint].candles):
                    merged[token.mint] = token
        return sorted(merged.values(), key=lambda t: t.created)
    raw_dir = str(dirs[0]).strip() if dirs else raw_dir
    creates: dict[str, dict] = {}
    trades: dict[str, list[dict]] = defaultdict(list)
    untracked: dict[str, float] = {}
    untrack_reason: dict[str, str] = {}
    tracked: dict[str, float] = {}
    seen_trades: set[tuple] = set()
    events = sorted(read_events(raw_files(raw_dir)), key=lambda e: e["t"])
    interruptions, simulated = recorder_interruptions(events, max_gap)
    for event in events:
        kind = event["e"]
        if kind == "create":
            creates[event["mint"]] = event
        elif kind == "trade":
            # Post-trade reserves identify a trade; two overlapping recorders write it twice.
            ident = (event["mint"], event.get("side"), event.get("trader"), event.get("sol"), event.get("vsol"), event.get("rsol"))
            if ident not in seen_trades:
                seen_trades.add(ident)
                trades[event["mint"]].append(event)
        elif kind == "track":
            tracked.setdefault(event["mint"], event["t"])
        elif kind in ("untrack", "migrate"):
            mint = event["mint"]
            if event["t"] < untracked.get(mint, math.inf):
                untracked[mint] = event["t"]
                untrack_reason[mint] = "migrated" if kind == "migrate" else event.get("reason") or "idle"
    tokens = []
    for mint, create in creates.items():
        if create.get("quote"):
            continue  # priced in another token, not SOL
        start = create["t"]
        if mint not in tracked or tracked[mint] - start > 2.0:
            continue  # trades were not recorded from the launch on
        ends = [(t, "interrupted") for t in interruptions if t > start][:1]
        if mint in untracked:
            ends.append((untracked[mint], untrack_reason[mint]))
        if not ends:
            continue
        end, end_reason = min(ends)
        events = [create] + sorted((e for e in trades.get(mint, ()) if start <= e["t"] < end), key=lambda e: e["t"])
        token = TokenData(
            mint, start, create.get("creator") or "", end=end, end_reason=end_reason,
            name=create.get("name") or "", symbol=create.get("symbol") or "", uri=create.get("uri") or "",
        )  # fmt: skip
        token.capture = capture_rate(
            (e.get("sol") or 0.0, e["e"] == "create" or e.get("side") == "b", e.get("rsol"), e["vsol"]) for e in events if e.get("vsol")
        )
        book = CandleBook(timeframe, grace=0.0)
        for event in events:
            tick = tick_from_event(event, token.creator)
            if tick is None:
                continue
            new_trader = bool(tick.trader) and tick.trader not in book.wallets
            token.ticks.setdefault(book.period(tick.ts), []).append((tick, new_trader))
            token.candles += book.add_tick(tick)
        token.candles += book.advance(end)
        if len(token.candles) >= min_candles and (min_candles > 0 or token.ticks):
            token.simulated = simulated
            tokens.append(token)
    return tokens


def recorder_interruptions(events: list[dict], max_gap: float = 10.0) -> tuple[list[float], bool]:
    """When one recorder's stream stopped being complete (sorted times), and whether it is simulated.

    Events must be in time order. A reconnect within `max_gap` seconds only loses those seconds of
    trades, comparable to the stream's usual drop rate, so it is not an interruption.
    """
    interruptions: list[float] = []
    last_seen = 0.0
    simulated = False
    started = False
    down_since: float | None = None
    for event in events:
        if event["e"] == "session":
            state = event.get("state")
            if state == "stopped":
                interruptions.append(event["t"])
                down_since = None
            elif state == "disconnected":
                down_since = event["t"] if down_since is None else down_since
            elif state == "connected" and started:
                if down_since is None:
                    # Connected again without a recorded drop: the recorder was killed;
                    # cut where its data ends.
                    interruptions.append(last_seen)
                elif event["t"] - down_since > max_gap:
                    interruptions.append(down_since)
                down_since = None
            started = True
            simulated = simulated or bool(event.get("simulated"))
        last_seen = max(last_seen, event["t"])
    if down_since is not None:
        interruptions.append(down_since)
    interruptions.append(last_seen)  # a recording that was killed has no "stopped" event
    interruptions.sort()
    return interruptions, simulated


def swap_tick(event: dict, creator: str = "") -> Tick | None:
    """A recorded PumpSwap `swap` event as the tick `PumpSwapFeed` yields for it live."""
    tokens, sol = event.get("tok_after"), event.get("sol_after")
    if not tokens or not sol or tokens <= 0 or sol <= 0:
        return None
    paid = event.get("paid") or 0.0
    buy = event.get("side") == "b"
    trader = event.get("trader") or ""
    return Tick(
        event["t"], sol / tokens, volume=paid, buy_volume=paid if buy else 0.0, sell_volume=0.0 if buy else paid,
        buys=int(buy), sells=int(not buy), trader=trader, creator=bool(creator) and trader == creator,
        liquidity=sol, tokens=event.get("tok") or 0.0,
    )  # fmt: skip


def load_pumpswap_tokens(raw_dir: str | Path | Sequence[str | Path], timeframe: int, max_gap: float = 10.0, min_candles: int = 3) -> list[TokenData]:
    """Graduated pump.fun tokens on their PumpSwap pools (`tartar record --pumpswap-hours N`),
    seen the way `tartar watch` sees them after graduation.

    At graduation the agent restarts its forecaster like a mid-life join: the candles so far
    become history without trade detail, and trades (now PumpSwap swaps) are tracked from
    there. So each token here is its bonding-curve candles before the candle in which it
    graduated (when its launch was recorded completely up to graduation; else none), then
    candles built from every trade from that candle on: the curve's last trades and the swaps.
    Training rows predict only candles that start after graduation (`first_target`). A pool's
    window ends when the recorder stops watching it (idle or age) or the recording is cut.
    """
    dirs = [d for d in (raw_dir.split(",") if isinstance(raw_dir, str) else raw_dir if isinstance(raw_dir, (list, tuple)) else [raw_dir]) if str(d).strip()]
    if len(dirs) > 1:
        merged: dict[str, TokenData] = {}
        for d in dirs:
            for token in load_pumpswap_tokens(str(d).strip(), timeframe, max_gap, min_candles):
                if token.mint not in merged or len(token.candles) > len(merged[token.mint].candles):
                    merged[token.mint] = token
        return sorted(merged.values(), key=lambda t: t.graduated)
    raw_dir = str(dirs[0]).strip() if dirs else raw_dir
    events = sorted(read_events(raw_files(raw_dir)), key=lambda e: e["t"])
    interruptions, simulated = recorder_interruptions(events, max_gap)
    creates: dict[str, dict] = {}
    tracked: dict[str, float] = {}
    curve: dict[str, list[dict]] = defaultdict(list)
    graduations: dict[str, dict] = {}  # pool -> graduate event
    swaps: dict[str, list[dict]] = defaultdict(list)
    unwatched: dict[str, float] = {}
    untracked: dict[str, float] = {}  # curve recording stopped (idle or age) before it graduated?
    seen_swaps: set[tuple] = set()
    for event in events:
        kind = event["e"]
        if kind == "create":
            creates.setdefault(event["mint"], event)
        elif kind == "track":
            tracked.setdefault(event["mint"], event["t"])
        elif kind == "untrack" and event.get("reason") != "migrated":
            untracked.setdefault(event["mint"], event["t"])
        elif kind == "trade":
            curve[event["mint"]].append(event)
        elif kind == "graduate" and event.get("pool"):
            graduations.setdefault(event["pool"], event)
        elif kind == "swap":
            ident = (event.get("pool"), event.get("side"), event.get("trader"), event.get("tok"), event.get("sol_after"))
            if ident not in seen_swaps:
                seen_swaps.add(ident)
                swaps[event.get("pool")].append(event)
        elif kind == "unwatch":
            unwatched.setdefault(event.get("pool"), event["t"])

    tokens = []
    for pool, grad in graduations.items():
        mint, t_grad = grad["mint"], grad["t"]
        cut = next((t for t in interruptions if t > t_grad), math.inf)
        end, end_reason = min((cut, "interrupted"), (unwatched.get(pool, math.inf), "unwatched"))
        if not math.isfinite(end):
            continue
        create = creates.get(mint)
        launch_ok = (
            create is not None and not create.get("quote") and mint in tracked and tracked[mint] - create["t"] <= 2.0
            and not any(create["t"] < t <= t_grad for t in interruptions) and untracked.get(mint, math.inf) >= t_grad
        )  # fmt: skip
        creator = (create or {}).get("creator") or ""
        # One candle book for the token's whole life, as in the agent (its book outlives the
        # forecaster's restart): curve trades from the launch, then the pool's swaps.
        book = CandleBook(timeframe, grace=0.0)
        grad_period = book.period(t_grad)
        candles: list[Candle] = []
        if launch_ok:
            for event in sorted((e for e in [create] + curve.get(mint, []) if e["t"] < t_grad), key=lambda e: e["t"]):
                tick = tick_from_event(event, creator)
                if tick is not None:
                    candles += book.add_tick(tick)
        token = TokenData(
            mint, create["t"] if launch_ok else t_grad, creator, end=end, end_reason=end_reason,
            name=(create or {}).get("name") or "", symbol=(create or {}).get("symbol") or "", uri=(create or {}).get("uri") or "",
            launch_known=launch_ok, graduated=t_grad,
        )  # fmt: skip
        n_swaps = 0
        for event in swaps.get(pool, ()):
            if not t_grad <= event["t"] < end:
                continue
            tick = swap_tick(event, creator)
            if tick is None:
                continue
            n_swaps += 1
            # Only post-graduation trades reach the restarted forecaster's wallet tracker.
            new_trader = bool(tick.trader) and tick.trader not in book.wallets
            token.ticks.setdefault(book.period(tick.ts), []).append((tick, new_trader))
            candles += book.add_tick(tick)
        candles += book.advance(end)
        # What the restarted forecaster sees: candles before the graduation candle without trade detail.
        k = sum(1 for c in candles if c.start < grad_period)
        token.candles = [Candle(c.start, c.open, c.high, c.low, c.close, volume=c.volume, trades=None) for c in candles[:k]] + candles[k:]
        token.first_target = k + 1  # the first candle that starts after graduation
        if n_swaps and len(candles) - k > min_candles:
            token.simulated = simulated
            tokens.append(token)
    return sorted(tokens, key=lambda t: t.graduated)


def load_ohlcv_tokens(directory: str | Path, timeframe: int) -> list[TokenData]:
    tokens = []
    for path in sorted(Path(directory).glob("*.json")):
        record, candles = load_ohlcv_file(path)
        if int(record.get("timeframe", timeframe)) != timeframe:
            continue
        candles = fill_gaps(candles, timeframe)
        created = record.get("created_at") or (candles[0].start if candles else 0)
        if len(candles) >= 10:
            tokens.append(TokenData(record["token"], float(created), "", candles))
    return tokens


def is_late_join(token: TokenData, share: float = 0.3) -> bool:
    return len(token.candles) > 12 and _hash_unit(token.mint, "late") < share


def late_join_view(token: TokenData, timeframe: int) -> tuple[list[Candle], dict[int, list[tuple[Tick, bool]]], int]:
    """The token as seen by someone who starts watching it mid-life.

    Before a random candle k there is only candle data (what a GeckoTerminal
    warm-up provides); from k on, trades arrive and wallets are tracked from
    scratch, exactly as in a live candle book seeded with history.
    Returns (candles, ticks by candle start, k).
    """
    k = 3 + int(_hash_unit(token.mint, "late_at") * (len(token.candles) - 10))
    history = [Candle(c.start, c.open, c.high, c.low, c.close, volume=c.volume, trades=None) for c in token.candles[:k]]
    start = token.candles[k].start
    book = CandleBook(timeframe, grace=0.0)
    candles = book.add_snapshot(history)
    ticks: dict[int, list[tuple[Tick, bool]]] = {}
    for period in sorted(p for p in token.ticks if p >= start):
        for tick, _ in token.ticks[period]:
            new_trader = bool(tick.trader) and tick.trader not in book.wallets
            ticks.setdefault(period, []).append((tick, new_trader))
            candles += book.add_tick(tick)
    candles += book.advance(token.candles[-1].start + timeframe)
    return candles, ticks, k


def build_dataset(
    tokens: list[TokenData],
    timeframe: int,
    domain: str,
    *,
    fractions: tuple[float, ...] = FRACTIONS,
    mask_creator: float = 0.3,
    mask_launch: float = 0.15,
    late_join: float = 0.3,
    dead_keep: float = 0.1,
    progress: Callable[[int, int], None] = lambda done, total: None,
) -> Dataset:
    """Feature rows for every token.

    Live conditions are mimicked: creator identity and launch time are hidden
    for a random share of tokens, and for `late_join` of them the agent "starts
    watching" mid-life (see `late_join_view`). Long dead stretches (no trades
    for 5+ candles) are subsampled and up-weighted so they don't swamp the data.
    """
    if domain not in TRADE_DOMAINS:
        fractions = (0.0,)
    cols: dict[str, list] = defaultdict(list)
    xs: list[np.ndarray] = []
    for index, token in enumerate(tokens):
        known_creator = domain == "trades" and _hash_unit(token.mint, "creator") >= mask_creator
        known_launch = token.launch_known and _hash_unit(token.mint, "launch") >= mask_launch
        candles, tick_groups, first_target = token.candles, token.ticks, token.first_target
        if domain == "trades" and is_late_join(token, late_join):
            candles, tick_groups, first_target = late_join_view(token, timeframe)
            known_creator = False
        engine = FeatureEngine(timeframe, token.created if known_launch else None, known_creator, domain=domain)
        tracker = WalletTracker(token.created if known_launch else None)
        stream = sorted((tick for group in tick_groups.values() for tick, _ in group), key=lambda t: t.ts)
        pos = 0

        def advance(until: float) -> None:
            nonlocal pos
            while pos < len(stream) and stream[pos].ts < until:
                tracker.update(stream[pos])
                pos += 1

        for i, candle in enumerate(candles[:-1]):
            engine.update(candle)
            if i + 1 < first_target:
                continue
            nxt = candles[i + 1]
            weight = 1.0
            if not candle.active and not nxt.active and engine.flat_streak >= 5:
                if _hash_unit(f"{token.mint}:{i}", "dead") >= dead_keep:
                    continue
                weight = 1.0 / dead_keep
            ref, sigma = candle.close, engine.sigma
            ticks = tick_groups.get(nxt.start, [])
            for f in fractions:
                now = nxt.start + f * timeframe
                if f == 0:
                    partial, price = None, ref
                else:
                    partial = Candle.flat(nxt.start, ref, 0)
                    for tick, new_trader in ticks:
                        if tick.ts >= now:
                            break
                        partial.add(tick, new_trader)
                    price = partial.close
                moved = nxt.close != price
                z = math.log(nxt.close / price) / (sigma * math.sqrt(1.0 - f)) if moved else 0.0
                advance(now)
                xs.append(engine.features(partial, now, tracker.snapshot()))
                for key, value in (
                    ("z", z), ("moved", moved), ("f", f), ("x0", math.log(price / ref) / sigma), ("sigma", sigma),
                    ("ref", ref), ("price", price), ("close", nxt.close), ("weight", weight), ("token", index),
                    ("time", now),
                ):  # fmt: skip
                    cols[key].append(value)
        progress(index + 1, len(tokens))
    X = np.vstack(xs) if xs else np.zeros((0, len(FEATURES)))
    arr = {k: np.asarray(v) for k, v in cols.items()}
    if not xs:
        arr = {k: np.zeros(0) for k in ("z", "moved", "f", "x0", "sigma", "ref", "price", "close", "weight", "token", "time")}
    return Dataset(
        timeframe=timeframe,
        domain=domain,
        X=X.astype(np.float32),
        label=z_to_class(arr["z"], arr["moved"].astype(bool)).astype(np.int32),
        z=arr["z"],
        f=arr["f"],
        x0=arr["x0"],
        sigma=arr["sigma"],
        ref=arr["ref"],
        price_now=arr["price"],
        close=arr["close"],
        weight=arr["weight"],
        token=arr["token"].astype(int),
        tokens=tokens,
        time=arr["time"],
        simulated=any(t.simulated for t in tokens),
    )
