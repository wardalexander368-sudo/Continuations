"""Pick the next pump.fun launch worth watching, skipping likely scams and dead launches.

Every launch on the chain stream becomes a candidate. Its trades are followed
for `screen_seconds`; then it is judged on what happened in that window (sniped
supply, creator dumping, copycats, serial or rugging creators, too few real
buyers). The first candidate that passes is returned with all of its trades so
far, so the watch starts with complete candles.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

from .candles import Tick
from .feeds.base import Status
from .feeds.pumpchain import ChainCreate, ChainTrade, create_to_message, stream_item, trade_to_message
from .feeds.pumpportal import tick_from_message
from .scam import CreatorIndex, ScamReport, WalletTracker, assess


@dataclass
class Candidate:
    create: ChainCreate
    seen_at: float
    ticks: list[Tick] = field(default_factory=list)
    tracker: WalletTracker = field(init=False)
    buyers: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.tracker = WalletTracker(self.seen_at)

    def add(self, tick: Tick) -> None:
        self.ticks.append(tick)
        self.tracker.update(tick)
        if tick.buys and not tick.creator and tick.trader:
            self.buyers.add(tick.trader)


@dataclass
class Verdict:
    candidate: Candidate
    report: ScamReport
    passed: bool
    reason: str


def judge(candidate: Candidate, creators: CreatorIndex | None, *, min_buyers: int, allow_risky: bool) -> Verdict:
    c = candidate.create
    report = assess(candidate.tracker, None, creators, mint=c.mint, creator=c.creator, name=c.name, symbol=c.symbol, uri=c.uri)
    if len(candidate.buyers) < min_buyers:
        return Verdict(candidate, report, False, f"only {len(candidate.buyers)} buyer(s) besides the creator")
    if report.is_scam_or_danger and not allow_risky:
        return Verdict(candidate, report, False, f"{report.level}: {report.summary()}")
    return Verdict(candidate, report, True, report.summary())


async def next_clean_launch(
    stream: AsyncIterator,
    *,
    screen_seconds: float = 20.0,
    min_buyers: int = 3,
    allow_risky: bool = False,
    creators: CreatorIndex | None = None,
    on_verdict: Callable[[Verdict], None] = lambda verdict: None,
    clock: Callable[[], float] = time.time,
) -> Verdict:
    """Consume `stream` (from stream_program_events) until a launch passes screening."""
    candidates: dict[str, Candidate] = {}
    async for item in stream:
        if isinstance(item, Status):
            continue
        received, _, events, _ = stream_item(item)
        created = [e for e in events if isinstance(e, ChainCreate)]
        first_buys: dict[str, ChainTrade] = {}
        for event in events:
            if isinstance(event, ChainTrade) and any(c.mint == event.mint for c in created) and event.mint not in first_buys:
                first_buys[event.mint] = event
        for create in created:
            if creators is not None:
                creators.note_launch(create.creator, create.name, create.symbol, create.uri, create.mint)
            candidate = Candidate(create, received)
            first = first_buys.get(create.mint)
            if first is not None:
                candidate.add(tick_from_message(create_to_message(create, first), received, create.creator))
            candidates[create.mint] = candidate
        for event in events:
            if isinstance(event, ChainTrade) and event.mint in candidates and first_buys.get(event.mint) is not event:
                candidate = candidates[event.mint]
                tick = tick_from_message(trade_to_message(event), received, candidate.create.creator)
                if tick is not None:
                    candidate.add(tick)
        now = clock()
        for mint in [m for m, c in candidates.items() if now - c.seen_at >= screen_seconds]:
            verdict = judge(candidates.pop(mint), creators, min_buyers=min_buyers, allow_risky=allow_risky)
            on_verdict(verdict)
            if verdict.passed:
                return verdict
    raise ConnectionError("the chain stream ended before a launch passed screening")
