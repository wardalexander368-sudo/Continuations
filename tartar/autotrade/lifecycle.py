"""Self-improvement: score each strategy's paper trades against its pre-registered rule and move it
between statuses. Every move is logged in changes.jsonl with the numbers behind it.

Statuses:
* ``paper``: collecting paper trades under its registered rule (every strategy starts here).
* ``promoted``: its registered success criteria are met on the agent's own paper trades. It keeps
  trading on paper at full size; it is the only status eligible for live trading, which still
  needs the user's explicit approval (broker.py).
* ``demoted``: was promoted, then its recent trades turned bad (rolling window below zero with the
  CI under zero, or a drawdown past the limit). Trades on paper at ``demoted_size_factor``.
* ``retired``: its registered criteria failed (or can no longer pass), or it stayed demoted too
  long. Takes no new entries; open positions still close on schedule.
* ``halted``: stopped by the risk layer (repeated errors); ``resume`` puts it back.

Rules (thresholds in config ``lifecycle``):
  paper    -> promoted  verdict "pass"
  paper    -> retired   verdict "fail"
  promoted -> demoted   verdict "fail", or rolling window CI upper < 0, or drawdown > max_drawdown_pct
  demoted  -> promoted  verdict "pass" and rolling window CI lower > 0
  demoted  -> retired   verdict "fail", or demoted for more than retire_after_demoted_trades trades

Weekly long-short books (trades carrying ``week`` and ``leg_usd``: the momentum strategies) are judged per
week, not per leg: a week's return is its legs' P&L over the side budget ``leg_usd``. Legs of one week are one
bet, so a per-leg rolling CI overstates the evidence, and a drawdown measured against one leg's notional
(1/4 to 1/15 of the side) would demote a promoted book on an ordinary bad week. Book thresholds:
``book_rolling_weeks`` (13), ``book_max_drawdown`` (0.35 of the side budget, as the account stop in
perp_risk.py) and ``retire_after_demoted_weeks`` (26).
"""

from __future__ import annotations

from .core import Trade, Verdict, bootstrap_ci

DEFAULTS = {
    "rolling_window": 30,
    "max_drawdown_pct": 0.25,  # of cumulative notional traded in the window's average position
    "demoted_size_factor": 0.5,
    "retire_after_demoted_trades": 60,
    "book_rolling_weeks": 13,
    "book_max_drawdown": 0.35,
    "retire_after_demoted_weeks": 26,
}


class WeekUnit:
    """One week of a long-short book as a pseudo-trade: return and P&L per unit of side budget."""

    def __init__(self, week: str, ret: float, exit_at: float):
        self.week, self.net_return, self.pnl_usd, self.exit_at, self.notional_usd = week, ret, ret, exit_at, 1.0


def book_units(trades: list[Trade]) -> list[WeekUnit] | None:
    """Weekly units if every trade is a weekly book leg, else None."""
    if not trades or not all(t.meta.get("week") and t.meta.get("leg_usd") for t in trades):
        return None
    by: dict[str, list[Trade]] = {}
    for t in trades:
        by.setdefault(t.meta["week"], []).append(t)
    return [WeekUnit(w, sum(t.pnl_usd / float(t.meta["leg_usd"]) for t in ts), max(t.exit_at for t in ts))
            for w, ts in sorted(by.items())]


def rolling(trades: list[Trade], k: int) -> dict:
    recent = sorted(trades, key=lambda t: t.exit_at)[-k:]
    if len(recent) < k:
        return {"n": len(recent), "complete": False}
    m, lo, hi = bootstrap_ci([t.net_return for t in recent])
    return {"n": len(recent), "complete": True, "mean": m, "lo": lo, "hi": hi}


def drawdown_pct(trades: list[Trade]) -> float:
    """Peak-to-trough drop of cumulative PnL, as a fraction of the average position size."""
    if not trades:
        return 0.0
    ts = sorted(trades, key=lambda t: t.exit_at)
    avg = sum(t.notional_usd for t in ts) / len(ts)
    peak = cum = worst = 0.0
    for t in ts:
        cum += t.pnl_usd
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return worst / avg if avg else 0.0


def decide(status: str, verdict: Verdict, trades: list[Trade], rec: dict, cfg: dict) -> tuple[str, str] | None:
    """(new status, reason) or None to keep the current one."""
    c = {**DEFAULTS, **cfg}
    units = book_units(trades)
    if units is not None:  # a weekly book: judge weeks, with the book thresholds
        trades = units
        c = {**c, "rolling_window": c["book_rolling_weeks"], "max_drawdown_pct": c["book_max_drawdown"],
             "retire_after_demoted_trades": c["retire_after_demoted_weeks"]}
    what = "weeks" if units is not None else "trades"
    if status == "paper":
        if verdict.decision == "pass":
            return "promoted", f"registered criteria met: {verdict.reason}"
        if verdict.decision == "fail":
            return "retired", f"registered criteria failed: {verdict.reason}"
    elif status == "promoted":
        if verdict.decision == "fail":
            return "demoted", f"registered criteria no longer met: {verdict.reason}"
        since = [t for t in trades if t.exit_at >= rec.get("since", 0)]
        win_since = rolling(since, c["rolling_window"])
        if win_since.get("complete") and win_since["hi"] < 0:
            return "demoted", f"last {win_since['n']} {what} mean {100 * win_since['mean']:+.2f}% with 90% CI upper {100 * win_since['hi']:+.2f}% < 0"
        dd = drawdown_pct(since)
        if dd > c["max_drawdown_pct"]:
            return "demoted", (f"drawdown {100 * dd:.1f}% of {'the side budget' if units is not None else 'average position'} "
                               f"> {100 * c['max_drawdown_pct']:.0f}%")
    elif status == "demoted":
        if verdict.decision == "fail":
            return "retired", f"registered criteria failed: {verdict.reason}"
        since = [t for t in trades if t.exit_at >= rec.get("since", 0)]
        win_since = rolling(since, c["rolling_window"])
        if verdict.decision == "pass" and win_since.get("complete") and win_since["lo"] > 0:
            return "promoted", f"recovered: last {win_since['n']} {what} mean {100 * win_since['mean']:+.2f}%, CI lower {100 * win_since['lo']:+.2f}% > 0"
        if len(since) > c["retire_after_demoted_trades"]:
            return "retired", f"demoted for {len(since)} {what} without recovering"
    return None


def review(ledger, strategies: dict, now: float, cfg: dict) -> list[dict]:
    """Score every strategy and apply status changes. Returns the change rows (also logged)."""
    c = {**DEFAULTS, **cfg}
    rows = []
    for name, strat in strategies.items():
        rec = ledger.strategy(name)
        trades = ledger.trades(name)
        try:
            verdict = strat.evaluate(trades, now, rec["data"])
        except Exception as exc:  # a broken scorer must not move a strategy
            verdict = Verdict("pending", len(trades), {}, f"scorer error: {exc!r}"[:300])
        rec["verdict"] = {"decision": verdict.decision, "n": verdict.n, "reason": verdict.reason,
                          "stats": verdict.stats, "at": now}
        if rec["status"] in ("halted", "retired"):
            continue
        move = decide(rec["status"], verdict, trades, rec, c)
        if move:
            new, reason = move
            row = {"t": now, "kind": "status", "scope": name, "from": rec["status"], "to": new, "reason": reason,
                   "n": verdict.n, "stats": verdict.stats}
            rec["status"], rec["since"] = new, now
            rec["size_factor"] = c["demoted_size_factor"] if new == "demoted" else 1.0
            ledger.change(row)
            rows.append(row)
    return rows
