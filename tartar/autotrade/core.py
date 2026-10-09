"""Shared types: intents, positions, trades, cost models, and the Strategy interface."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Protocol


@dataclass
class CostModel:
    """Cost of one side of a trade, as a fraction of notional, plus a fixed USD amount per transaction.

    ``fee`` covers pool/venue fees and the route's own fee; ``impact`` the price impact at the
    position's size; ``fixed_usd`` network and priority fees."""

    fee: float = 0.0
    impact: float = 0.0
    fixed_usd: float = 0.0

    def side_cost(self, notional: float) -> float:
        """Total USD cost of one side at this notional."""
        return notional * (self.fee + self.impact) + self.fixed_usd


@dataclass
class Intent:
    """What a strategy wants done. Prices and times come from the market data the strategy read.

    kind "open": open a position in ``asset`` with ``side`` (+1 long, -1 short) and ``notional_usd``.
    kind "close": close ``position_id``.
    """

    kind: str
    strategy: str
    at: float  # unix time of the price used
    price: float  # reference price (USD per unit) before costs
    reason: str = ""
    asset: str = ""
    side: int = 1
    notional_usd: float = 0.0
    position_id: str = ""
    cost: CostModel = field(default_factory=CostModel)
    meta: dict[str, Any] = field(default_factory=dict)  # strategy-specific, copied to the position/trade


@dataclass
class Position:
    id: str
    strategy: str
    asset: str
    side: int
    notional_usd: float
    entry_price: float  # reference price at entry
    entry_at: float
    entry_cost_usd: float
    mode: str = "paper"
    mark_price: float | None = None
    mark_at: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new(intent: Intent, cost_usd: float, mode: str) -> "Position":
        return Position(id=uuid.uuid4().hex[:12], strategy=intent.strategy, asset=intent.asset, side=intent.side,
                        notional_usd=intent.notional_usd, entry_price=intent.price, entry_at=intent.at,
                        entry_cost_usd=cost_usd, mode=mode, meta=dict(intent.meta))

    def gross_pnl(self, price: float) -> float:
        return self.side * self.notional_usd * (price / self.entry_price - 1.0)

    def unrealized(self) -> float:
        if self.mark_price is None:
            return -self.entry_cost_usd
        return self.gross_pnl(self.mark_price) - self.entry_cost_usd

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Position":
        return Position(**d)


@dataclass
class Trade:
    """A closed position. ``net_return`` is net PnL over notional, after both sides' costs."""

    id: str
    strategy: str
    asset: str
    side: int
    notional_usd: float
    entry_price: float
    entry_at: float
    exit_price: float
    exit_at: float
    cost_usd: float
    pnl_usd: float
    net_return: float
    mode: str = "paper"
    reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Trade":
        return Trade(**d)


@dataclass
class Verdict:
    """A strategy's score against its pre-registered rule.

    decision: "pass" (the registered success criteria are met), "fail" (they can no longer be
    met, or the registered deadline passed without them), or "pending"."""

    decision: str
    n: int
    stats: dict[str, Any]
    reason: str


class Context:
    """What a strategy sees in one step: the time, its open positions and its private state."""

    def __init__(self, now: float, positions: list[Position], state: dict, config: dict, http=None):
        self.now = now
        self.positions = positions
        self.state = state  # persisted between runs (strategy-owned, JSON-serializable)
        self.config = config
        self.http = http


class Strategy(Protocol):
    """A strategy plugs into the agent by implementing these.

    ``step`` reads market data and returns intents; it must be idempotent across runs (keep a
    cursor in ``ctx.state`` so a bar is acted on once). ``marks`` returns current reference
    prices for open positions. ``evaluate`` scores closed trades against the strategy's
    pre-registered rule. ``prereg`` names the registration the rule comes from."""

    name: str
    prereg: str

    def step(self, ctx: Context) -> list[Intent]: ...

    def marks(self, ctx: Context) -> dict[str, tuple[float, float]]: ...  # position id -> (price, at)

    def evaluate(self, trades: list[Trade], now: float, state: dict) -> Verdict: ...


def bootstrap_ci(values: Iterable[float], groups: Iterable[Any] | None = None, n: int = 2000, seed: int = 0,
                 q: tuple[float, float] = (0.05, 0.95)) -> tuple[float, float, float]:
    """Mean and a bootstrap CI; resamples groups (e.g. pools) when given, else single values."""
    import numpy as np

    v = np.asarray(list(values), dtype=float)
    if not len(v):
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    if groups is None:
        boots = v[rng.integers(0, len(v), (n, len(v)))].mean(axis=1)
    else:
        g = np.asarray(list(groups))
        uniq, inv = np.unique(g, return_inverse=True)
        sums, cnts = np.bincount(inv, weights=v), np.bincount(inv)
        idx = rng.integers(0, len(uniq), (n, len(uniq)))
        boots = sums[idx].sum(axis=1) / np.maximum(cnts[idx].sum(axis=1), 1)
    lo, hi = np.quantile(boots, q)
    return float(v.mean()), float(lo), float(hi)
