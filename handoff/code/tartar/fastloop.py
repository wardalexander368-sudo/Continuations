"""The fast loop: decide on every new launch within seconds, and paper-trade the decisions.

For each launch on the stream, the loop waits `screen_seconds`, builds the
launch's state (`decide.LaunchStateBuilder`, the same code the offline
evaluation uses), applies the policy's cheap skip rules, asks the scorer
(TypeSafe's Jev, or plain rules), and paper-trades a "buy": a simulated fill on
the live bonding-curve reserves after the execution latency, then an exit by
the policy's rule. Every screen, decision, fill and exit goes to a JSON-lines
journal.

The slow loop (Claude, on a schedule) reads the journal with `tartar review`
and changes the policy file. The fast loop reloads the policy when the file
changes. Positions keep the rule they were opened with.

Paper only: the policy refuses any mode other than "paper", and nothing here
can send a transaction.

Fills mirror `profit.round_trip` exactly (a test checks this): the state used
is the last trade at or before the fill time, so live paper results and the
offline backtest measure the same thing.
"""

from __future__ import annotations

import heapq
import json
import math
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .data.dataset import tick_from_event
from .decide import FunctionScorer, LaunchStateBuilder, Scorer
from .profit import Costs, Exit, buy_tokens, sell_sol
from .scam import CreatorIndex

# Hard bounds on every policy field. The slow loop may move values only inside these.
LIMITS = {
    "screen_seconds": (1.0, 600.0),
    "min_buyers": (0, 1000),
    "threshold": (0.0, 1.0),
    "hold_seconds": (1.0, 7200.0),
    "take_profit": (0.01, 20.0),
    "stop_loss": (0.01, 0.95),
    "size_sol": (0.001, 1.0),
    "fee": (0.0, 0.05),
    "network_sol": (0.0, 0.01),
    "exec_latency": (0.0, 30.0),
    "scorer_timeout": (0.05, 30.0),
    "max_open": (1, 100),
    "max_entries_per_hour": (1, 1000),
    "daily_loss_limit_sol": (0.0, 100.0),
}
SCORERS = ("rules", "jev")


class PolicyError(ValueError):
    pass


@dataclass
class Policy:
    version: int = 1
    mode: str = "paper"
    scorer: str = "rules"  # "rules": pass the skip rules = buy; "jev": ask TypeSafe Jev
    screen_seconds: float = 20.0
    min_buyers: int = 0
    skip_levels: list = field(default_factory=list)  # risk levels to skip, e.g. ["scam"]
    skip_flags: list = field(default_factory=lambda: ["concentrated", "sniped", "dev_bag"])
    threshold: float = 0.5  # buy when the scorer's probability is at least this
    hold_seconds: float = 180.0
    take_profit: float | None = None  # fraction, e.g. 1.0 = +100%
    stop_loss: float | None = None  # fraction, e.g. 0.3 = -30%
    size_sol: float = 0.1
    fee: float = 0.0125
    network_sol: float = 0.0002
    exec_latency: float = 1.0
    scorer_timeout: float = 2.0
    max_open: int = 10
    max_entries_per_hour: int = 60
    daily_loss_limit_sol: float = 1.0
    shadow_jev: bool = False  # ask Jev about every screened launch and journal its answers, without acting on them
    note: str = ""  # why the policy is what it is (written by whoever changed it)

    @classmethod
    def from_dict(cls, data: dict) -> Policy:
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise PolicyError(f"unknown policy fields: {', '.join(unknown)}")
        policy = cls(**data)
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.mode != "paper":
            raise PolicyError("only mode 'paper' exists: the fast loop never sends real transactions")
        if self.scorer not in SCORERS:
            raise PolicyError(f"scorer must be one of {SCORERS}")
        for name, (low, high) in LIMITS.items():
            value = getattr(self, name)
            if value is None and name in ("take_profit", "stop_loss"):
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not (low <= value <= high):
                raise PolicyError(f"{name} = {value!r} is outside [{low}, {high}]")
        if not isinstance(self.shadow_jev, bool):
            raise PolicyError("shadow_jev must be true or false")
        if not all(isinstance(x, str) for x in list(self.skip_flags) + list(self.skip_levels)):
            raise PolicyError("skip_flags and skip_levels must be lists of strings")

    def costs(self) -> Costs:
        return Costs(size_sol=self.size_sol, fee=self.fee, network_sol=self.network_sol, latency=self.exec_latency)

    def exit_rule(self) -> Exit:
        return Exit(self.hold_seconds, self.take_profit, self.stop_loss)

    def skip_reason(self, state: dict) -> str | None:
        if state["buyers"] < self.min_buyers:
            return f"{state['buyers']} buyers < {self.min_buyers}"
        if state["risk"] in self.skip_levels:
            return f"risk {state['risk']}"
        bad = sorted(set(self.skip_flags) & set(state["flags"]))
        if bad:
            return "flags " + ",".join(bad)
        return None


class PolicyFile:
    """A policy on disk, reloaded when the file changes. An invalid edit keeps the last good policy."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(asdict(Policy()), indent=2) + "\n")
        self.policy = Policy.from_dict(json.loads(self.path.read_text()))
        self._mtime = self.path.stat().st_mtime

    def reload(self) -> tuple[bool, str | None]:
        """(changed, error)."""
        try:
            mtime = self.path.stat().st_mtime
        except OSError as exc:
            return False, str(exc)
        if mtime == self._mtime:
            return False, None
        self._mtime = mtime
        try:
            self.policy = Policy.from_dict(json.loads(self.path.read_text()))
        except (ValueError, TypeError) as exc:
            return False, str(exc)
        return True, None


class Journal:
    """Append-only JSON lines, one file per UTC day."""

    def __init__(self, directory: str | Path, clock: Callable[[], float] = time.time):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._file = None
        self._day = None
        self.records = 0

    def write(self, record: dict) -> None:
        day = datetime.fromtimestamp(record.get("t", self.clock()), timezone.utc).strftime("%Y%m%d")
        if day != self._day:
            self.close()
            self._file = (self.dir / f"journal-{day}.jsonl").open("a", buffering=1)
            self._day = day
        self._file.write(json.dumps(record, default=_json_default) + "\n")
        self.records += 1

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


def _json_default(value):
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def _clean(state: dict) -> dict:
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in state.items()}


# ---------------------------------------------------------------- deciders


@dataclass
class Decision:
    mint: str
    screened_at: float
    decided_at: float
    score: float | None
    latency: float
    error: str | None = None


class InlineDecider:
    """Scores immediately (replays and the rules scorer). The decision lands at
    screen time + latency: `fixed_latency` if given, else the measured call time."""

    def __init__(self, scorer: Scorer, fixed_latency: float | None = None):
        self.scorer, self.fixed_latency = scorer, fixed_latency
        self._ready: list[Decision] = []

    def submit(self, mint: str, state: dict, now: float, timeout: float) -> None:
        started = time.perf_counter()
        score, error = None, None
        try:
            score = float(self.scorer.score([state])[0])
        except Exception as exc:  # a failing scorer means "skip", never a crash
            error = f"{type(exc).__name__}: {exc}"[:300]
        latency = self.fixed_latency if self.fixed_latency is not None else time.perf_counter() - started
        if latency > timeout:
            score, error = None, error or f"timeout ({latency:.2f}s > {timeout:g}s)"
        self._ready.append(Decision(mint, now, now + latency, score, latency, error))

    def poll(self, now: float) -> list[Decision]:
        due = [d for d in self._ready if d.decided_at <= now]
        self._ready = [d for d in self._ready if d.decided_at > now]
        return due


class ThreadDecider:
    """Scores in worker threads so the stream never waits on the scorer (live use)."""

    def __init__(self, scorer: Scorer, workers: int = 8, clock: Callable[[], float] = time.time):
        self.scorer, self.clock = scorer, clock
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self._pending: list[tuple[str, float, float, float, Future]] = []

    def submit(self, mint: str, state: dict, now: float, timeout: float) -> None:
        started = self.clock()
        future = self.pool.submit(lambda: (float(self.scorer.score([state])[0]), self.clock()))
        self._pending.append((mint, now, started, timeout, future))

    def poll(self, now: float) -> list[Decision]:
        out, keep = [], []
        wall = self.clock()
        for mint, screened, started, timeout, future in self._pending:
            if future.done():
                try:
                    score, finished = future.result()
                    error = None if finished - started <= timeout else f"timeout ({finished - started:.2f}s)"
                    out.append(Decision(mint, screened, finished, None if error else score, finished - started, error))
                except Exception as exc:
                    out.append(Decision(mint, screened, wall, None, wall - started, f"{type(exc).__name__}: {exc}"[:300]))
            elif wall - started > timeout:
                future.cancel()
                out.append(Decision(mint, screened, wall, None, wall - started, f"timeout ({timeout:g}s)"))
            else:
                keep.append((mint, screened, started, timeout, future))
        self._pending = keep
        return out

    def close(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)


class ShadowAsker:
    """Asks Jev every question about a launch and hands back the answers, to be
    journaled only. In `threaded` mode the calls run in worker threads (live)."""

    def __init__(self, client, threaded: bool = True, workers: int = 4, clock: Callable[[], float] = time.time):
        self.client, self.threaded, self.clock = client, threaded, clock
        self.pool = ThreadPoolExecutor(max_workers=workers) if threaded else None
        self._pending: list[tuple[str, float, float, object]] = []  # (mint, screened at, started, future or result)

    def _ask(self, state: dict):
        started = time.perf_counter()
        try:
            return self.client.ask(state), None, time.perf_counter() - started
        except Exception as exc:
            return None, f"{type(exc).__name__}: {exc}"[:300], time.perf_counter() - started

    def submit(self, mint: str, state: dict, now: float) -> None:
        if self.threaded:
            self._pending.append((mint, now, self.clock(), self.pool.submit(self._ask, state)))
        else:
            self._pending.append((mint, now, now, self._ask(state)))

    def poll(self) -> list[dict]:
        out, keep = [], []
        for mint, screened, started, item in self._pending:
            if isinstance(item, Future):
                if not item.done():
                    keep.append((mint, screened, started, item))
                    continue
                item = item.result()
            answers, error, latency = item
            record = {"e": "shadow", "t": screened, "mint": mint, "answers": answers, "latency_ms": round(1000 * latency, 1)}
            if error:
                record["error"] = error
            out.append(record)
        self._pending = keep
        return out

    def close(self) -> None:
        if self.pool is not None:
            self.pool.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------- paper broker


@dataclass
class Position:
    mint: str
    decided_at: float
    fill_at: float
    costs: Costs
    rule: Exit
    score: float | None
    tokens: float = 0.0
    fill: float = 0.0  # average price paid per token, fee included
    deadline: float = 0.0
    exit_at: float | None = None
    reason: str = "horizon"
    status: str = "pending"  # pending -> open -> closed (or cancelled)
    pnl_sol: float = 0.0


class PaperBroker:
    """Simulated fills on the streamed curve states, matching `profit.round_trip`."""

    def __init__(self, journal: Journal):
        self.journal = journal
        self.state: dict[str, tuple[float, float]] = {}  # mint -> (virtual SOL, price) after its last trade
        self.positions: dict[str, Position] = {}
        self.closed: list[Position] = []

    def open_count(self) -> int:
        return sum(1 for p in self.positions.values() if p.status in ("pending", "open"))

    def order(self, mint: str, decided_at: float, costs: Costs, rule: Exit, score: float | None) -> Position | None:
        if mint in self.positions:
            return None  # one position per token
        position = Position(mint, decided_at, decided_at + costs.latency, costs, rule, score)
        self.positions[mint] = position
        return position

    def advance(self, now: float) -> None:
        """Carry out fills and exits due before `now`, at each token's current state."""
        for position in list(self.positions.values()):
            if position.status == "pending" and position.fill_at < now:
                self._fill(position)
            if position.status == "open":
                due = position.exit_at if position.exit_at is not None else position.deadline
                if due < now:
                    self._exit(position, due)

    def on_trade(self, mint: str, t: float, vsol: float, price: float) -> None:
        self.advance(t)
        self.state[mint] = (vsol, price)
        position = self.positions.get(mint)
        if position is None or position.status != "open" or position.exit_at is not None or t > position.deadline:
            return
        ratio = price / position.fill
        rule = position.rule
        if (rule.take_profit is not None and ratio >= 1.0 + rule.take_profit) or (rule.stop_loss is not None and ratio <= 1.0 - rule.stop_loss):
            position.reason = "take_profit" if ratio >= 1.0 else "stop_loss"
            position.exit_at = t + position.costs.latency

    def close_all(self, now: float) -> None:
        self.advance(math.inf)

    def _fill(self, position: Position) -> None:
        state = self.state.get(position.mint)
        if state is None:
            position.status = "cancelled"
            self.positions.pop(position.mint)
            self.journal.write({"e": "cancel", "t": position.fill_at, "mint": position.mint, "reason": "nothing traded yet"})
            return
        vsol, price = state
        c = position.costs
        position.tokens = buy_tokens(vsol, vsol / price, c.size_sol, c.fee)
        position.fill = c.size_sol / position.tokens
        position.deadline = position.fill_at + position.rule.horizon
        position.status = "open"
        self.journal.write({"e": "fill", "t": position.fill_at, "mint": position.mint, "price": price, "avg_price": position.fill, "tokens": position.tokens, "size_sol": c.size_sol})

    def _exit(self, position: Position, at: float) -> None:
        vsol, price = self.state[position.mint]
        c = position.costs
        proceeds = sell_sol(vsol, vsol / price, position.tokens, c.fee)
        position.pnl_sol = proceeds - c.size_sol - 2 * c.network_sol
        position.status = "closed"
        self.positions.pop(position.mint)
        self.closed.append(position)
        self.journal.write({
            "e": "exit", "t": at, "mint": position.mint, "price": price, "reason": position.reason,
            "pnl_sol": position.pnl_sol, "ret": position.pnl_sol / c.size_sol, "held": at - position.fill_at,
        })  # fmt: skip


# ---------------------------------------------------------------- the loop


class FastLoop:
    """Consumes raw-format events (`tartar record`'s format) in time order."""

    def __init__(
        self,
        policy: PolicyFile | Policy,
        journal: Journal,
        *,
        jev_factory: Callable[[], Scorer] | None = None,
        decider_factory: Callable[[Scorer], object] | None = None,
        creators: CreatorIndex | None = None,
        reload_every: float = 5.0,
        shadow_factory: Callable[[], ShadowAsker] | None = None,
    ):
        self.policy_file = policy if isinstance(policy, PolicyFile) else None
        self.policy = policy.policy if isinstance(policy, PolicyFile) else policy
        self.journal = journal
        self.jev_factory = jev_factory
        self.decider_factory = decider_factory or (lambda scorer: InlineDecider(scorer, fixed_latency=0.0))
        self.builder = LaunchStateBuilder(creators)
        self.broker = PaperBroker(journal)
        self.creators_of: dict[str, str] = {}
        self._screens: list[tuple[float, str]] = []  # heap of (screen time, mint)
        self._entries: list[float] = []  # entry decision times, for the hourly cap
        self._day_pnl: dict[str, float] = {}
        self._last_reload = -math.inf
        self.reload_every = reload_every
        self.now = 0.0
        self.counts = {"launches": 0, "screened": 0, "skipped": 0, "asked": 0, "buys": 0, "errors": 0, "shadow": 0}
        self.shadow_factory = shadow_factory
        self.shadow: ShadowAsker | None = None
        self._set_scorer()
        self._set_shadow()

    def _set_scorer(self) -> None:
        if self.policy.scorer == "jev":
            if self.jev_factory is None:
                raise PolicyError("policy asks for the jev scorer but none is configured (set TYPESAFE_API_KEY)")
            scorer = self.jev_factory()
        else:
            scorer = FunctionScorer("rules", lambda state: 1.0)
        self.scorer_name = self.policy.scorer
        self.decider = self.decider_factory(scorer) if self.policy.scorer == "jev" else InlineDecider(scorer, fixed_latency=0.0)

    def _set_shadow(self) -> None:
        if self.policy.shadow_jev and self.shadow is None:
            if self.shadow_factory is None:
                raise PolicyError("policy asks for Jev shadow answers but no Jev client is configured")
            self.shadow = self.shadow_factory()

    def start(self, t: float) -> None:
        self.journal.write({"e": "start", "t": t, "policy": asdict(self.policy)})

    def on_event(self, event: dict) -> None:
        t = event.get("t", self.now)
        self.advance(t)
        kind, mint = event["e"], event.get("mint")
        if kind == "create":
            creator = event.get("creator") or ""
            self.creators_of[mint] = creator
            self.builder.create(mint, t, creator, event.get("name") or "", event.get("symbol") or "", event.get("uri") or "")
            heapq.heappush(self._screens, (t + self.policy.screen_seconds, mint))
            self.counts["launches"] += 1
            self._trade(mint, event)
        elif kind == "trade":
            self._trade(mint, event)
        elif kind == "untrack":
            self.builder.close(mint)

    def _trade(self, mint: str, event: dict) -> None:
        tick = tick_from_event(event, self.creators_of.get(mint, ""))
        if tick is None:
            return
        self.builder.tick(mint, tick)
        if tick.virtual_sol > 0:
            self.broker.on_trade(mint, tick.ts, tick.virtual_sol, tick.price)

    def advance(self, now: float) -> None:
        """Run everything due before `now` (call with the wall clock when the stream is quiet)."""
        self.now = max(self.now, now)
        if self.policy_file is not None and now - self._last_reload >= self.reload_every:
            self._last_reload = now
            self._reload(now)
        while self._screens and self._screens[0][0] < now:
            at, mint = heapq.heappop(self._screens)
            self._screen(mint, at)
        for decision in self.decider.poll(now):
            self._decide(decision)
        if self.shadow is not None:
            for record in self.shadow.poll():
                self.counts["shadow"] += 1
                self.journal.write(record)
        self.broker.advance(now)

    def _reload(self, now: float) -> None:
        changed, error = self.policy_file.reload()
        if error:
            self.journal.write({"e": "policy_error", "t": now, "error": error})
        if changed:
            old_scorer = self.policy.scorer
            self.policy = self.policy_file.policy
            try:
                if self.policy.scorer != old_scorer:
                    self._set_scorer()
                self._set_shadow()
            except PolicyError as exc:
                self.journal.write({"e": "policy_error", "t": now, "error": str(exc)})
            self.journal.write({"e": "policy", "t": now, "policy": asdict(self.policy)})

    def _screen(self, mint: str, at: float) -> None:
        state = self.builder.state(mint, at)
        if state is None:
            return  # closed before its screen time
        self.counts["screened"] += 1
        if self.shadow is not None and self.policy.shadow_jev:
            self.shadow.submit(mint, state, at)
        record = {"e": "screen", "t": at, "mint": mint, "state": _clean(state)}
        reason = self.policy.skip_reason(state)
        if reason is None:
            reason = self._cap_reason(at)
        if reason is not None:
            self.counts["skipped"] += 1
            record["skip"] = reason
            self.journal.write(record)
            return
        self.journal.write(record)
        self.counts["asked"] += 1
        self.decider.submit(mint, state, at, self.policy.scorer_timeout)

    def _cap_reason(self, now: float) -> str | None:
        p = self.policy
        if self.broker.open_count() >= p.max_open:
            return f"max_open {p.max_open}"
        self._entries = [t for t in self._entries if t > now - 3600]
        if len(self._entries) >= p.max_entries_per_hour:
            return f"max_entries_per_hour {p.max_entries_per_hour}"
        day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%d")
        realized = sum(pos.pnl_sol for pos in self.broker.closed if datetime.fromtimestamp(pos.fill_at, timezone.utc).strftime("%Y%m%d") == day)
        if realized <= -p.daily_loss_limit_sol:
            return f"daily loss {realized:.3f} SOL hit the limit"
        return None

    def _decide(self, d: Decision) -> None:
        p = self.policy
        buy = d.score is not None and d.score >= p.threshold
        record = {
            "e": "decision", "t": d.decided_at, "mint": d.mint, "screened_at": d.screened_at, "scorer": self.scorer_name,
            "score": d.score, "latency_ms": round(1000 * d.latency, 1), "threshold": p.threshold, "buy": buy,
        }  # fmt: skip
        if d.error:
            record["error"] = d.error
            self.counts["errors"] += 1
        self.journal.write(record)
        if buy and self.broker.order(d.mint, d.decided_at, p.costs(), p.exit_rule(), d.score) is not None:
            self.counts["buys"] += 1
            self._entries.append(d.decided_at)

    def finish(self, t: float) -> dict:
        """Close every position at its last known state and write a summary."""
        self.advance(t)
        self.broker.close_all(t)
        pnl = [p.pnl_sol for p in self.broker.closed]
        summary = {
            "e": "stop", "t": t, **self.counts, "trades": len(pnl), "pnl_sol": sum(pnl),
            "mean_ret": (sum(pnl) / len(pnl) / self.policy.size_sol) if pnl else None,
        }  # fmt: skip
        if self.shadow is not None:
            for record in self.shadow.poll():  # answers that came back; slower ones are dropped
                self.counts["shadow"] += 1
                self.journal.write(record)
            self.shadow.close()
        summary["shadow"] = self.counts["shadow"]
        self.journal.write(summary)
        self.journal.close()
        if isinstance(self.decider, ThreadDecider):
            self.decider.close()
        return summary


def replay(raw_dir: str | Path, loop: FastLoop) -> dict:
    """Run the fast loop over recorded raw logs, in time order (no waiting)."""
    from .data.rawlog import raw_files, read_events

    events = sorted(read_events(raw_files(raw_dir)), key=lambda e: e["t"])
    if not events:
        raise ValueError(f"no events in {raw_dir}")
    loop.start(events[0]["t"])
    for event in events:
        loop.on_event(event)
    return loop.finish(events[-1]["t"] + 1.0)


def jev_factory_from_env(policy_timeout: float = 2.0) -> Callable[[], Scorer]:
    """Jev's direct answer as the fast loop's scorer. Credentials come from
    `TYPESAFE_API_KEY` or, in a Claude cloud environment, from the proxy."""

    def make() -> Scorer:
        from .jev import JevClient, JevScorer

        return JevScorer(JevClient(timeout=policy_timeout, workers=1))

    return make


def shadow_factory(cache: str | Path = "data/jev-answers.jsonl", threaded: bool = True) -> Callable[[], ShadowAsker]:
    """Jev answering every question about every screened launch, for the journal only."""

    def make() -> ShadowAsker:
        from .jev import JevClient

        return ShadowAsker(JevClient(cache=cache, workers=1), threaded=threaded)

    return make
