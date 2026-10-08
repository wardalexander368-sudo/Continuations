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
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from .profit import Costs, Curve, Exit, run_policy, summarize
from .scam import CreatorIndex, WalletTracker, assess

LEVEL_RANK = {"unknown": 0, "ok": 1, "caution": 2, "danger": 3, "scam": 4}
NUMERIC = (
    "buyers", "trades", "buy_sol", "sell_sol", "rise_pct", "raised_sol", "creator_sold_share",
    "creator_launches", "creator_rugs", "drawdown_pct", "top10_share", "holders", "creator_share",
    "sniper_share", "wash_share", "trades_per_wallet", "nonstandard_curve", "risk_rank",
)  # fmt: skip


def _rugged(curve: Curve, ticks) -> bool:
    """Creator sold at least half of what they bought and the price ended 80%+ below its peak."""
    if not len(curve):
        return False
    bought = sum(t.volume for t in ticks if t.creator and t.buys)
    sold = sum(t.volume for t in ticks if t.creator and t.sells)
    return bought > 0 and sold >= 0.5 * bought and curve.price[-1] <= 0.2 * curve.price.max()


def launch_states(tokens, curves: list[Curve], seconds: float = 20.0) -> list[dict]:
    """What each launch looked like `seconds` after it was seen, in launch order.

    Creator history only counts earlier launches whose outcome was already
    known (their recorded window ended at least 10 minutes before), so no
    state uses information from its own future.
    """
    index = CreatorIndex()
    pending: list[tuple[float, str, str, bool]] = []  # (known at, mint, creator, rugged)
    states = []
    for k in sorted(range(len(tokens)), key=lambda i: tokens[i].created):
        token, curve = tokens[k], curves[k]
        decide_at = token.created + seconds
        keep = []
        for known_at, mint, creator, rugged in pending:
            if known_at <= decide_at:
                index.creators[creator].tokens[mint] = rugged
            else:
                keep.append((known_at, mint, creator, rugged))
        pending = keep

        ticks = sorted((t for group in token.ticks.values() for t, _ in group), key=lambda t: t.ts)
        tracker = WalletTracker(token.created)
        buyers: set[str] = set()
        buy_sol = sell_sol = 0.0
        n = 0
        raised = 0.0
        for tick in ticks:
            if tick.ts > decide_at:
                break
            tracker.update(tick)
            n += 1
            raised = tick.liquidity
            if tick.buys and not tick.creator and tick.trader:
                buyers.add(tick.trader)
            if not tick.creator:
                buy_sol += tick.buy_volume
                sell_sol += tick.sell_volume
        report = assess(tracker, None, index, mint=token.mint, creator=token.creator, name=token.name, symbol=token.symbol, uri=token.uri)
        index.note_launch(token.creator, token.name, token.symbol, token.uri, token.mint)
        pending.append(((curve.end if len(curve) else token.created) + 600.0, token.mint, token.creator, _rugged(curve, ticks)))

        record = index.creators.get(token.creator)
        launches, rugs, _ = record.excluding(token.mint) if record else (0, 0, 0)
        i = curve.index_at(decide_at)
        snap = tracker.snapshot()
        sold = tracker.creator_sold_share
        drawdown = tracker.drawdown
        states.append(
            {
                "token": k,
                "mint": token.mint,
                "decide_at": decide_at,
                "name": token.name,
                "symbol": token.symbol,
                "seconds": seconds,
                "buyers": len(buyers),
                "trades": n,
                "buy_sol": buy_sol,
                "sell_sol": sell_sol,
                "rise_pct": 100 * (curve.price[i] / curve.price[0] - 1) if i >= 0 else math.nan,
                "raised_sol": raised,
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
        )
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
    """P(net > 0) from a small LightGBM classifier fitted on earlier launches' outcomes."""

    name = "lightgbm screen"

    def __init__(self, train_states: list[dict], labels: np.ndarray, valid_states: list[dict], valid_labels: np.ndarray, seed: int = 1):
        import lightgbm as lgb

        params = dict(
            objective="binary", learning_rate=0.03, num_leaves=7, min_data_in_leaf=40, feature_fraction=0.8,
            bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=seed,
        )  # fmt: skip
        ok, vok = ~np.isnan(labels), ~np.isnan(valid_labels)
        train = lgb.Dataset(state_matrix(train_states)[ok], (labels[ok] > 0).astype(int), feature_name=list(NUMERIC))
        valid = lgb.Dataset(state_matrix(valid_states)[vok], (valid_labels[vok] > 0).astype(int), reference=train)
        self.booster = lgb.train(params, train, 2000, valid_sets=[valid], callbacks=[lgb.early_stopping(100, verbose=False)])

    def score(self, states: list[dict]) -> np.ndarray:
        return self.booster.predict(state_matrix(states), num_iteration=self.booster.best_iteration)


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


def jev_scorer_from_env() -> Scorer | None:
    """TypeSafe Jev as a scorer, if `TYPESAFE_API_KEY` is set (see tartar/jev.py)."""
    if not os.environ.get("TYPESAFE_API_KEY"):
        return None
    from .jev import JevScorer

    return JevScorer(os.environ["TYPESAFE_API_KEY"])
