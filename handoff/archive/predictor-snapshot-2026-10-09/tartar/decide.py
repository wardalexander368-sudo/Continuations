"""Buy-or-skip decisions on new launches, from any scorer, judged by net SOL.

Each launch is described by what was knowable `seconds` after it appeared:
its first trades (wallet behaviour, flow, price move), the creator's record
from earlier launches only, and the risk flags. A scorer turns those states
into a probability that buying is worth it. `evaluate` picks the scorer's
threshold on validation launches and reports the net result on the latest
(test) launches with `profit.run_policy`, so every scorer is held to the same
standard: our own models, or an external decision API such as TypeSafe's Jev.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from .candles import Tick
from .profit import Costs, Curve, Exit, run_policy, summarize
from .scam import CreatorIndex, WalletTracker, assess

LEVEL_RANK = {"unknown": 0, "ok": 1, "caution": 2, "danger": 3, "scam": 4}
NUMERIC = (
    "buyers", "trades", "buy_sol", "sell_sol", "rise_pct", "raised_sol", "creator_sold_share",
    "creator_launches", "creator_rugs", "drawdown_pct", "top10_share", "holders", "creator_share",
    "sniper_share", "wash_share", "trades_per_wallet", "nonstandard_curve", "risk_rank",
)  # fmt: skip


@dataclass
class _Launch:
    mint: str
    created: float
    creator: str
    name: str
    symbol: str
    uri: str
    tracker: WalletTracker
    buyers: set = field(default_factory=set)
    buy_sol: float = 0.0
    sell_sol: float = 0.0
    trades: int = 0
    raised: float = 0.0
    first_price: float = 0.0
    last_price: float = 0.0
    peak: float = 0.0
    creator_bought: float = 0.0  # SOL
    creator_sold: float = 0.0  # SOL


class LaunchStateBuilder:
    """Launch states built from a stream of launches and trades, in time order.

    The same code serves the live fast loop and the offline evaluation
    (`launch_states` replays recorded tokens through it), so a decision is
    judged on exactly the state it would see live. Creator history only uses
    launches that were closed (their outcome known) before the moment of the
    decision.
    """

    def __init__(self, creators: CreatorIndex | None = None):
        self.index = creators or CreatorIndex()
        self.launches: dict[str, _Launch] = {}

    def create(self, mint: str, t: float, creator: str, name: str = "", symbol: str = "", uri: str = "") -> None:
        self.launches[mint] = _Launch(mint, t, creator, name, symbol, uri, WalletTracker(t))
        self.index.note_launch(creator, name, symbol, uri, mint)
        self.index.creators[creator].tokens[mint] = False  # rugged or not is known when it closes

    def tick(self, mint: str, tick: Tick) -> None:
        launch = self.launches.get(mint)
        if launch is None:
            return
        launch.tracker.update(tick)
        launch.trades += 1
        launch.raised = tick.liquidity
        launch.first_price = launch.first_price or tick.price
        launch.last_price = tick.price
        launch.peak = max(launch.peak, tick.price)
        if tick.creator:
            if tick.buys:
                launch.creator_bought += tick.volume
            else:
                launch.creator_sold += tick.volume
        else:
            launch.buy_sol += tick.buy_volume
            launch.sell_sol += tick.sell_volume
            if tick.buys and tick.trader:
                launch.buyers.add(tick.trader)

    def close(self, mint: str) -> None:
        """The launch is no longer followed: record whether it was rugged
        (creator sold half of what they bought and the price ended 80%+ below its peak)."""
        launch = self.launches.pop(mint, None)
        if launch is None:
            return
        rugged = (
            launch.creator_bought > 0
            and launch.creator_sold >= 0.5 * launch.creator_bought
            and launch.peak > 0
            and launch.last_price <= 0.2 * launch.peak
        )
        self.index.creators[launch.creator].tokens[mint] = rugged

    def state(self, mint: str, now: float) -> dict | None:
        launch = self.launches.get(mint)
        if launch is None:
            return None
        tracker = launch.tracker
        report = assess(tracker, None, self.index, mint=mint, creator=launch.creator, name=launch.name, symbol=launch.symbol, uri=launch.uri)
        record = self.index.creators.get(launch.creator)
        launches, rugs, _ = record.excluding(mint) if record else (0, 0, 0)
        snap = tracker.snapshot()
        sold, drawdown = tracker.creator_sold_share, tracker.drawdown
        return {
            "mint": mint,
            "decide_at": now,
            "name": launch.name,
            "symbol": launch.symbol,
            "seconds": now - launch.created,
            "buyers": len(launch.buyers),
            "trades": launch.trades,
            "buy_sol": launch.buy_sol,
            "sell_sol": launch.sell_sol,
            "rise_pct": 100 * (launch.last_price / launch.first_price - 1) if launch.first_price else math.nan,
            "raised_sol": launch.raised,
            "creator_sold_share": math.nan if sold is None else sold,
            "creator_launches": launches,
            "creator_rugs": rugs,
            "drawdown_pct": math.nan if drawdown is None else 100 * drawdown,
            "top10_share": snap["top10_share"],
            "holders": tracker.holders,
            "creator_share": snap["creator_share"],
            "sniper_share": snap["sniper_share"],
            "wash_share": snap["wash_share"],
            "trades_per_wallet": snap["trades_per_wallet"],
            "nonstandard_curve": snap["nonstandard_curve"],
            "risk": report.level,
            "risk_rank": LEVEL_RANK[report.level],
            "flags": sorted({f.code for f in report.flags}),
        }


def launch_states(tokens, curves: list[Curve], seconds: float = 20.0) -> list[dict]:
    """Each recorded launch's state `seconds` after it was seen, in launch order,
    built by replaying the recorded tokens through `LaunchStateBuilder`.

    Each token closes at the end of its recorded window (`TokenData.end`).
    """
    CREATE, TICK, DECIDE, CLOSE = range(4)  # order of simultaneous events
    events: list[tuple[float, int, int, object]] = []
    for k, token in enumerate(tokens):
        events.append((token.created, CREATE, k, None))
        for group in token.ticks.values():
            events.extend((tick.ts, TICK, k, tick) for tick, _ in group)
        events.append((token.created + seconds, DECIDE, k, None))
        end = token.end or (curves[k].end if len(curves[k]) else token.created)
        events.append((max(end, token.created + seconds), CLOSE, k, None))
    events.sort(key=lambda e: (e[0], e[1]))
    builder = LaunchStateBuilder()
    states = []
    for t, kind, k, payload in events:
        token = tokens[k]
        if kind == CREATE:
            builder.create(token.mint, t, token.creator, token.name, token.symbol, token.uri)
        elif kind == TICK:
            builder.tick(token.mint, payload)
        elif kind == DECIDE:
            state = builder.state(token.mint, t)
            state["token"] = k
            states.append(state)
        else:
            builder.close(token.mint)
    return states


def state_matrix(states: list[dict]) -> np.ndarray:
    return np.array([[float(s[c]) for c in NUMERIC] for s in states], dtype=float)


class Scorer(Protocol):
    name: str

    def score(self, states: list[dict]) -> np.ndarray:
        """Probability (or any monotone score) that buying each launch is worth it."""
        ...


class CachedScorer:
    """Remembers scores by mint in a JSON-lines file, so an API is asked about each launch once."""

    def __init__(self, inner: Scorer, path: str | Path):
        self.inner, self.path = inner, Path(path)
        self.name = inner.name
        self.cache: dict[str, float] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.cache[row["mint"]] = row["score"]

    def score(self, states: list[dict]) -> np.ndarray:
        missing = [s for s in states if s["mint"] not in self.cache]
        if missing:
            fresh = self.inner.score(missing)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as out:
                for s, value in zip(missing, fresh):
                    self.cache[s["mint"]] = float(value)
                    out.write(json.dumps({"mint": s["mint"], "score": float(value)}) + "\n")
        return np.array([self.cache[s["mint"]] for s in states])


class LightGBMScorer:
    """P(net > 0) from a small LightGBM classifier fitted on earlier launches' outcomes.

    `extra` adds feature columns computed from the states (e.g. Jev's judgments).
    """

    def __init__(
        self,
        train_states: list[dict],
        labels: np.ndarray,
        valid_states: list[dict],
        valid_labels: np.ndarray,
        seed: int = 1,
        extra: Callable[[list[dict]], np.ndarray] | None = None,
        extra_names: tuple[str, ...] = (),
        name: str = "lightgbm screen",
    ):
        import lightgbm as lgb

        self.name, self.extra = name, extra
        params = dict(
            objective="binary", learning_rate=0.03, num_leaves=7, min_data_in_leaf=40, feature_fraction=0.8,
            bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=seed,
        )  # fmt: skip
        ok, vok = ~np.isnan(labels), ~np.isnan(valid_labels)
        names = list(NUMERIC) + [f"extra_{n}" for n in extra_names]
        train = lgb.Dataset(self._matrix(train_states)[ok], (labels[ok] > 0).astype(int), feature_name=names)
        valid = lgb.Dataset(self._matrix(valid_states)[vok], (valid_labels[vok] > 0).astype(int), reference=train)
        self.booster = lgb.train(params, train, 2000, valid_sets=[valid], callbacks=[lgb.early_stopping(100, verbose=False)])

    def _matrix(self, states: list[dict]) -> np.ndarray:
        X = state_matrix(states)
        return X if self.extra is None else np.hstack([X, self.extra(states)])

    def score(self, states: list[dict]) -> np.ndarray:
        return self.booster.predict(self._matrix(states), num_iteration=self.booster.best_iteration)

    def importance(self) -> dict[str, float]:
        gain = self.booster.feature_importance("gain")
        total = gain.sum() or 1.0
        return {n: float(g / total) for n, g in sorted(zip(self.booster.feature_name(), gain), key=lambda x: -x[1])}


class FlagScorer:
    """Skip launches carrying any risk flag that went with worse trades on earlier launches.

    A flag counts as bad when, on the training launches, trades with it
    averaged at least `margin` (fraction of the stake) less than trades
    without it, over at least `min_count` trades each.
    """

    name = "skip flags that lost on train"

    def __init__(self, train_states: list[dict], labels: np.ndarray, margin: float = 0.02, min_count: int = 30):
        ok = ~np.isnan(labels)
        states = [s for s, keep in zip(train_states, ok) if keep]
        y = labels[ok]
        self.bad: list[str] = []
        for code in sorted({c for s in states for c in s["flags"]}):
            has = np.array([code in s["flags"] for s in states])
            if has.sum() >= min_count and (~has).sum() >= min_count and y[has].mean() <= y[~has].mean() - margin:
                self.bad.append(code)

    def score(self, states: list[dict]) -> np.ndarray:
        bad = set(self.bad)
        return np.array([0.0 if bad & set(s["flags"]) else 1.0 for s in states])


class FunctionScorer:
    """Wrap a plain function of one state (handy for rules and tests)."""

    def __init__(self, name: str, fn: Callable[[dict], float]):
        self.name, self.fn = name, fn

    def score(self, states: list[dict]) -> np.ndarray:
        return np.array([self.fn(s) for s in states], dtype=float)


def evaluate(
    scorer: Scorer,
    states: list[dict],
    split: np.ndarray,
    curves: list[Curve],
    costs: Costs,
    rule: Exit,
    quantiles=(0.0, 0.5, 0.7, 0.8, 0.9, 0.95),  # of validation scores, as candidate thresholds
    min_trades: int = 20,
) -> dict:
    """Buy launches scoring above a threshold chosen on validation (split 1); report validation and test (split 2)."""
    token = np.array([s["token"] for s in states])
    when = np.array([s["decide_at"] for s in states])
    scores = np.full(len(states), np.nan)
    for part in (1, 2):
        idx = np.flatnonzero(split == part)
        scores[idx] = scorer.score([states[i] for i in idx])

    def trades(part: int, threshold: float):
        sel = (split == part) & (scores >= threshold)
        return run_policy(curves, token[sel], when[sel], np.ones(sel.sum(), bool), costs, rule)

    valid_scores = scores[split == 1]
    candidates = {float(np.quantile(valid_scores, q)) for q in quantiles}
    distinct = np.unique(valid_scores)
    if len(distinct) <= 10:  # a rule: try each of its levels
        candidates |= {float(v) for v in distinct}
    best = None
    for thr in sorted(candidates):
        chosen = trades(1, thr)
        total = sum(t.pnl_sol for t in chosen)
        if len(chosen) >= min_trades and (best is None or total > best[1]):
            best = (thr, total)
    if best is None:
        return {"scorer": scorer.name, "exit": rule.label(), "threshold": None}
    thr = best[0]
    return {
        "scorer": scorer.name,
        "exit": rule.label(),
        "threshold": thr,
        "kept_share_valid": float((valid_scores >= thr).mean()),
        "valid": summarize(trades(1, thr), costs).to_dict(),
        "test": summarize(trades(2, thr), costs).to_dict(),
    }
