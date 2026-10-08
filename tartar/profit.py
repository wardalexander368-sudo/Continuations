"""What a trade would really have earned: round trips on the recorded bonding curves, after costs.

Prediction accuracy is not profit. A trade on a pump.fun bonding curve pays a
fee on both sides, moves the price against itself (the curve is the order
book), pays network fees, and executes a moment after the decision. This
module replays trades on the recorded curve states with all of that charged,
so a strategy is judged by the SOL it would have ended with.

Fills use the constant-product curve at the reserves of the last recorded
trade before the execution time. Our own trades do not change the recorded
path afterwards; entry and exit each pay their price impact on the market's
reserves, which slightly overstates the cost of a round trip (conservative).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .candles import Tick


@dataclass(frozen=True)
class Costs:
    size_sol: float = 0.1  # SOL spent on each entry
    fee: float = 0.0125  # bonding-curve fee per side (protocol + creator), as a fraction
    network_sol: float = 0.0002  # per transaction: base fee + priority fee
    latency: float = 1.0  # seconds from a decision to its execution on chain


@dataclass(frozen=True)
class Exit:
    horizon: float = 60.0  # seconds after entry at which the position is sold
    take_profit: float | None = None  # sell once the price is up this fraction from the fill
    stop_loss: float | None = None  # sell once the price is down this fraction from the fill

    def label(self) -> str:
        parts = [f"hold {self.horizon:g}s"]
        if self.take_profit is not None:
            parts.append(f"TP +{100 * self.take_profit:g}%")
        if self.stop_loss is not None:
            parts.append(f"SL -{100 * self.stop_loss:g}%")
        return ", ".join(parts)


def buy_tokens(vsol: float, vtok: float, sol: float, fee: float) -> float:
    """Tokens received for `sol` (fee taken from the input)."""
    sol_in = sol * (1.0 - fee)
    return vtok * sol_in / (vsol + sol_in)


def sell_sol(vsol: float, vtok: float, tokens: float, fee: float) -> float:
    """SOL received for selling `tokens` (fee taken from the output)."""
    return vsol * tokens / (vtok + tokens) * (1.0 - fee)


class Curve:
    """A token's recorded bonding-curve state over time.

    `known_until` is when the record stops being complete (the end of the
    token's recorded window); `cut` says the window ended because the
    recording itself stopped or dropped out, so nothing is known about the
    price afterwards. When it ended because the token went idle or migrated,
    the last recorded state is a fair stand-in for a while longer.
    """

    def __init__(self, ticks: list[Tick], known_until: float | None = None, cut: bool = False):
        ticks = sorted((t for t in ticks if t.virtual_sol > 0 and t.price > 0), key=lambda t: t.ts)
        self.times = np.array([t.ts for t in ticks])
        self.vsol = np.array([t.virtual_sol for t in ticks])
        self.price = np.array([t.price for t in ticks])
        self.known_until = known_until if known_until is not None else self.end
        self.cut = cut

    def __len__(self) -> int:
        return len(self.times)

    @property
    def end(self) -> float:
        return float(self.times[-1]) if len(self.times) else 0.0

    def index_at(self, t: float) -> int:
        """Index of the last trade at or before `t` (-1 if none)."""
        return int(np.searchsorted(self.times, t, side="right")) - 1

    def state(self, i: int) -> tuple[float, float]:
        vsol = float(self.vsol[i])
        return vsol, vsol / float(self.price[i])


@dataclass
class Trade:
    token: int
    decided: float
    entry: float
    exit: float
    entry_price: float
    exit_price: float
    pnl_sol: float
    reason: str  # horizon, take_profit, stop_loss
    censored: bool  # the exit fell after the token's recorded window ended
    cut: bool = False  # ... and that window ended because the recording was cut (outcome unknown)


def round_trip(curve: Curve, decided: float, costs: Costs, rule: Exit) -> Trade | None:
    """Buy at `decided` + latency, sell by the exit rule. None if nothing had traded yet."""
    t_in = decided + costs.latency
    i = curve.index_at(t_in)
    if i < 0:
        return None
    vsol, vtok = curve.state(i)
    tokens = buy_tokens(vsol, vtok, costs.size_sol, costs.fee)
    fill = costs.size_sol / tokens  # average price paid, fee included
    entry_price = float(curve.price[i])

    deadline = t_in + rule.horizon
    reason, t_exit_decision = "horizon", deadline
    if rule.take_profit is not None or rule.stop_loss is not None:
        j_end = curve.index_at(deadline)
        path = curve.price[i + 1 : j_end + 1] / fill
        hits = np.zeros(len(path), dtype=bool)
        if rule.take_profit is not None:
            hits |= path >= 1.0 + rule.take_profit
        if rule.stop_loss is not None:
            hits |= path <= 1.0 - rule.stop_loss
        if hits.any():
            k = int(hits.argmax())
            reason = "take_profit" if path[k] >= 1.0 else "stop_loss"
            t_exit_decision = float(curve.times[i + 1 + k])
    t_out = t_exit_decision if reason == "horizon" else t_exit_decision + costs.latency
    j = curve.index_at(t_out)
    vsol, vtok = curve.state(j)
    proceeds = sell_sol(vsol, vtok, tokens, costs.fee)
    pnl = proceeds - costs.size_sol - 2 * costs.network_sol
    return Trade(
        token=-1,
        decided=decided,
        entry=t_in,
        exit=t_out,
        entry_price=entry_price,
        exit_price=float(curve.price[j]),
        pnl_sol=pnl,
        reason=reason,
        censored=t_out > curve.known_until,
        cut=t_out > curve.known_until and curve.cut,
    )


def label_round_trips(curves: list[Curve], token: np.ndarray, time: np.ndarray, costs: Costs, rule: Exit) -> np.ndarray:
    """Net return (fraction of the stake) of a round trip decided at each (token, time).

    NaN where nothing had traded yet or the exit falls after a recording cut.
    """
    out = np.full(len(token), np.nan)
    for n, (k, t) in enumerate(zip(token, time)):
        trade = round_trip(curves[int(k)], float(t), costs, rule)
        if trade is not None and not trade.cut:
            out[n] = trade.pnl_sol / costs.size_sol
    return out


def run_policy(
    curves: list[Curve],
    token: np.ndarray,
    time: np.ndarray,
    take: np.ndarray,
    costs: Costs,
    rule: Exit,
    max_entries: int | None = None,
    keep_cut: bool = False,
) -> list[Trade]:
    """Trade every candidate decision with `take` set, holding at most one position per token.

    Candidates are processed in time order per token; a candidate that comes
    while a position on that token is open is skipped. `max_entries` caps the
    trades per token. Trades whose exit falls after a recording cut are
    dropped unless `keep_cut`: their outcome is unknown, and since a cut has
    nothing to do with the token, dropping them does not bias the result.
    """
    trades: list[Trade] = []
    busy_until: dict[int, float] = {}
    count: dict[int, int] = {}
    for n in np.lexsort((time, token)):
        if not take[n]:
            continue
        k, t = int(token[n]), float(time[n])
        if t < busy_until.get(k, -math.inf):
            continue
        if max_entries is not None and count.get(k, 0) >= max_entries:
            continue
        trade = round_trip(curves[k], t, costs, rule)
        if trade is None or (trade.cut and not keep_cut):
            continue
        trade.token = k
        trades.append(trade)
        busy_until[k] = trade.exit
        count[k] = count.get(k, 0) + 1
    return trades


@dataclass
class Summary:
    trades: int
    tokens: int
    total_sol: float
    mean_ret: float  # mean net return per trade, fraction of the stake
    median_ret: float
    win_rate: float
    ci_low: float  # 90% bootstrap interval of the mean return, resampling tokens
    ci_high: float
    p_positive: float  # share of bootstrap resamples with a positive mean
    censored: int
    reasons: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def summarize(trades: list[Trade], costs: Costs, boot: int = 2000, seed: int = 0) -> Summary:
    if not trades:
        return Summary(0, 0, 0.0, math.nan, math.nan, math.nan, math.nan, math.nan, math.nan, 0)
    rets = np.array([t.pnl_sol for t in trades]) / costs.size_sol
    toks = np.array([t.token for t in trades])
    uniq, inv = np.unique(toks, return_inverse=True)
    sums = np.bincount(inv, weights=rets)
    counts = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(uniq), size=(boot, len(uniq)))
    means = sums[pick].sum(axis=1) / counts[pick].sum(axis=1)
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t.reason] = reasons.get(t.reason, 0) + 1
    return Summary(
        trades=len(trades),
        tokens=len(uniq),
        total_sol=float(rets.sum() * costs.size_sol),
        mean_ret=float(rets.mean()),
        median_ret=float(np.median(rets)),
        win_rate=float((rets > 0).mean()),
        ci_low=float(np.quantile(means, 0.05)),
        ci_high=float(np.quantile(means, 0.95)),
        p_positive=float((means > 0).mean()),
        censored=sum(t.censored for t in trades),
        reasons=reasons,
    )


def curves_for(tokens) -> list[Curve]:
    """One curve per `TokenData` (trade data), in the same order."""
    return [
        Curve(
            [tick for group in token.ticks.values() for tick, _ in group],
            known_until=token.end or None,
            # After a migration the token trades elsewhere, so the last curve price stands in for the exit
            # (dropping those trades would remove the biggest winners). Any other end, such as the
            # recording stopping or the recorder's tracking limit, is unrelated to the token.
            cut=token.end_reason not in ("idle", "migrated"),
        )
        for token in tokens
    ]


def model_scores(model, ds) -> dict[str, np.ndarray]:
    """Per-row trading signals implied by a global model's predictive distribution.

    * expected return: E[close / price now] - 1, integrating the distribution
      (uniform within bins, exponential tails).
    * P(up): probability that the price rises from here by the close.
    """
    from .model.global_model import EDGES

    probs = model.predict_proba(ds.X)
    s = ds.sigma * np.sqrt(1.0 - ds.f)
    tl, th = model.meta.get("tail_low", 1.0), model.meta.get("tail_high", 1.0)
    lo = np.concatenate([[-np.inf], EDGES])
    hi = np.concatenate([EDGES, [np.inf]])
    ratio = probs[:, 0].copy()
    for k in range(len(lo)):
        if k == 0:
            e = np.exp(s * hi[k]) / (1.0 + s * tl)
        elif k == len(lo) - 1:
            e = np.exp(s * lo[k]) / np.maximum(1.0 - s * th, 0.05)  # the tail's mean is infinite past s * th = 1
        else:
            e = (np.exp(s * hi[k]) - np.exp(s * lo[k])) / (s * (hi[k] - lo[k]))
        ratio += probs[:, 1 + k] * e
    above = EDGES >= 0
    p_up = probs[:, 1:][:, np.concatenate([[False], above])].sum(axis=1)
    return {"expected return": ratio - 1.0, "P(up)": p_up}


def choose_threshold(score, curves, ds, mask, costs, rule, quantiles=(0.5, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995), min_trades=30):
    """The score threshold (a quantile on `mask` rows) that made the most SOL there, or None."""
    best = None
    for q in quantiles:
        thr = float(np.quantile(score[mask], q))
        s = summarize(run_policy(curves, ds.token[mask], ds.time[mask], score[mask] > thr, costs, rule), costs, boot=1)
        if s.trades >= min_trades and (best is None or s.total_sol > best[1]):
            best = (thr, s.total_sol, q)
    return None if best is None else (best[0], best[2])


def profit_report(ds, costs: Costs, model=None, holds=(30, 60, 180)) -> list[dict]:
    """Net results of standard strategies on the validation and test launches.

    Signal thresholds are chosen on validation launches only; test launches
    (the latest) are untouched until the final measurement.
    """
    curves = curves_for(ds.tokens)
    _, valid, test = ds.split()
    created = np.array([t.created for t in ds.tokens])
    rows = []

    def add(strategy: str, rule: Exit, split: str, trades: list[Trade], note: str = "") -> None:
        rows.append({"strategy": strategy, "exit": rule.label(), "split": split, "note": note, **summarize(trades, costs).to_dict()})

    for split, mask in (("valid", valid), ("test", test)):
        toks = np.unique(ds.token[mask])
        for hold in holds:
            rule = Exit(hold)
            add("buy every launch when seen", rule, split, run_policy(curves, toks, created[toks], np.ones(len(toks), bool), costs, rule))
    if model is not None:
        for name, score in model_scores(model, ds).items():
            for hold in (ds.timeframe,):
                rule = Exit(hold)
                pick = choose_threshold(score, curves, ds, valid, costs, rule)
                if pick is None:
                    continue
                thr, q = pick
                for split, mask in (("valid", valid), ("test", test)):
                    trades = run_policy(curves, ds.token[mask], ds.time[mask], score[mask] > thr, costs, rule)
                    add(f"model {name} > {thr:.3g}", rule, split, trades, f"top {100 * (1 - q):g}% on validation")
    return rows
