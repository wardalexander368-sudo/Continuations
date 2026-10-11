"""Risk controls for the perps strategies (weekly long-short books on Hyperliquid), applied to the paper book
every run, so live twins, which exit with their paper legs, inherit them. Scored on the search's 146-week
backtest by handoff/experiments/perps_risk_controls.py (results in handoff/autotrade.md):

* **Weekly loss limit** (``weekly_stop_frac``, default 0.12): when a strategy's P&L for its current week
  (closed legs of that week plus open legs at their marks) falls below ``-weekly_stop_frac`` x its side
  notional (``leg_usd``), every open leg closes at its mark (20 bps per side, funding carried) and the
  strategy sits out until its next weekly rebalance. In the backtest a 12% stop kept the mean weekly
  return (candidate +2.92% vs +2.83%, vol-momentum +1.31% vs +1.42%, xs +1.10% vs +1.03%) and cut the
  worst week from -36/-24/-31% to -25/-22/-18%.
* **Book drawdown stop** (``account_drawdown_stop_frac``, default 0.35): when a book's registered (non-shadow)
  strategies' combined P&L falls more than that fraction of their combined side notional below its peak, that
  book stops taking new entries (``state.book_halts``; exits still run) and a halt is logged, which fails the
  Action so the owner is emailed. Only that book stops (2026-10-11: the Hyperliquid book is research, so its
  drawdown must not freeze the registered US tests, nor the reverse); ``resume book:hl`` / ``resume book:us``
  (or a bare ``resume``) clears it. The ``HALT`` file stays the manual, agent-wide kill switch.

* **Book volatility target** (``book_vol_target``, default 0.02): the registered perps strategies are one
  equal-weight book; once it has ``book_min_weeks`` (8) weekly returns, every new leg's size (and its
  ``leg_usd``) is multiplied by clip(target / std of the book's last 13 weekly returns, 0.5, 1.5), the
  book construction recommended by handoff/experiments/perps_book.py (worst week -18% vs -22%, max
  drawdown 24% vs 38%, at a lower mean). Scoring is per unit of ``leg_usd``, so verdicts don't change;
  a coin kept on the same side across a resize still pays no cost (the scale moves slowly).

**Two books** (2026-10-11, US-only rule): the Hyperliquid strategies (research only) and the Coinbase US-perp
strategies (``data: coinbase``, venue ``coinbase_perps``) are separate books. Each gets its own volatility
target and drawdown stop, so a US book's sizing never depends on Hyperliquid's weeks or the reverse; the
weekly loss limit applies to both (Coinbase legs carry no funding).

Inverse-volatility sizing was scored too and cost return on every rule, so legs stay equal weight.
"""

from __future__ import annotations

import numpy as np

from .core import Context, CostModel, Intent

DEFAULTS = {"weekly_stop_frac": 0.12, "account_drawdown_stop_frac": 0.35, "exit_cost": 0.002,
            "book_vol_target": 0.02, "book_window_weeks": 13, "book_min_weeks": 8, "book_scale_min": 0.5, "book_scale_max": 1.5}


BOOKS = ("hl", "us")
BOOK_VENUE = {"hl": "hyperliquid", "us": "coinbase_perps"}


def is_perp_book(pos) -> bool:
    return pos.meta.get("venue") in BOOK_VENUE.values() and "week" in pos.meta and "leg_usd" in pos.meta


def book_of(scfg: dict) -> str:
    return "us" if scfg.get("data") == "coinbase" else "hl"


def weekly_stops(ledger, strategies: dict, now: float, cfg: dict, http=None) -> list[Intent]:
    """Close intents for strategies past their weekly loss limit (state marks the week as stopped)."""
    lim = {**DEFAULTS, **cfg}
    out: list[Intent] = []
    by_strat: dict[str, list] = {}
    for p in ledger.positions:
        if is_perp_book(p):
            by_strat.setdefault(p.strategy, []).append(p)
    for name, pos in by_strat.items():
        week = max(p.meta["week"] for p in pos)
        leg_usd = float(pos[0].meta["leg_usd"])
        rec = ledger.strategy(name)
        if rec.get("stopped_week") == week:
            continue
        realized = sum(t.pnl_usd for t in ledger.trades(name) if t.meta.get("week") == week)
        open_now = [p for p in pos if p.meta["week"] == week]
        unreal = sum(p.unrealized() for p in open_now)
        if realized + unreal >= -lim["weekly_stop_frac"] * leg_usd:
            continue
        strat = strategies.get(name)
        for p in pos:
            if p.mark_price is None:
                continue
            carry = 0.0
            if hasattr(strat, "funding"):
                try:
                    ctx = Context(now, [], {}, {}, http)
                    carry = -p.side * strat.funding(ctx, p.asset, p.entry_at, now) * p.notional_usd
                except Exception:  # noqa: BLE001 - a funding lookup failure must not block the stop
                    carry = 0.0
            out.append(Intent("close", name, p.mark_at or now, p.mark_price,
                              f"weekly loss limit: week P&L {realized + unreal:+.2f} USD < -{lim['weekly_stop_frac']:.0%} of {leg_usd:.0f}",
                              position_id=p.id, cost=CostModel(fee=lim["exit_cost"]),
                              meta={"carry_usd": carry, "stop": "weekly_loss"}))
        rec["stopped_week"] = week
        ledger.change({"t": now, "kind": "pause", "scope": name,
                       "reason": f"weekly loss limit: week {week} P&L {realized + unreal:+.2f} USD on {leg_usd:.0f} per side; "
                                 "flat until the next rebalance", "week": week})
    return out


def book_names(config: dict, book: str = "hl") -> list[str]:
    return [n for n, s in config.get("strategies", {}).items()
            if s.get("kind") == "xs_momentum" and s.get("enabled", True) and not s.get("shadow") and book_of(s) == book]


def book_weeks(ledger, names: list[str]) -> list[float]:
    """The equal-weight book's weekly returns: each week, the mean of its strategies' returns per unit of leg_usd."""
    by_week: dict[str, dict[str, float]] = {}
    for n in names:
        for t in ledger.trades(n):
            w = t.meta.get("week")
            if w and t.meta.get("leg_usd"):
                d = by_week.setdefault(w, {})
                d[n] = d.get(n, 0.0) + t.pnl_usd / float(t.meta["leg_usd"])
    open_weeks = {p.meta.get("week") for p in ledger.positions if p.strategy in names}
    return [sum(d.values()) / len(d) for w, d in sorted(by_week.items()) if w not in open_weeks]


def book_scale(ledger, config: dict, cfg: dict, book: str = "hl") -> tuple[float, str]:
    """Size multiplier for new legs of a registered perps book, and a one-line reason."""
    lim = {**DEFAULTS, **cfg}
    x = book_weeks(ledger, book_names(config, book))
    if len(x) < lim["book_min_weeks"]:
        return 1.0, f"book vol target off until {lim['book_min_weeks']} weeks ({len(x)} so far)"
    vol = float(np.std(x[-int(lim["book_window_weeks"]):], ddof=1))
    k = float(np.clip(lim["book_vol_target"] / max(vol, 1e-4), lim["book_scale_min"], lim["book_scale_max"]))
    return k, f"book vol {100 * vol:.2f}%/week over {min(len(x), int(lim['book_window_weeks']))} weeks -> scale x{k:.2f}"


def account_drawdown(ledger, config: dict, root, now: float, cfg: dict, book: str = "hl") -> str | None:
    """Stop a registered perps book's new entries when its drawdown passes the limit; the reason if it fired now."""
    lim = {**DEFAULTS, **cfg}
    names = book_names(config, book)
    def deployed(n):  # the open book's leg_usd (vol-scaled), else the configured one
        legs = [float(p.meta["leg_usd"]) for p in ledger.positions if p.strategy == n and "leg_usd" in p.meta]
        return max(legs) if legs else float(config["strategies"][n].get("leg_usd", 100.0))

    capital = sum(deployed(n) for n in names)
    if not names or capital <= 0:
        return None
    equity = sum(t.pnl_usd for n in names for t in ledger.trades(n)) + \
        sum(p.unrealized() for p in ledger.positions if p.strategy in names)
    st = ledger.state.setdefault("perp_risk" if book == "hl" else f"perp_risk_{book}", {})
    st["peak"] = max(st.get("peak", 0.0), equity)
    st["equity"] = equity
    dd = st["peak"] - equity
    st["drawdown_frac"] = dd / capital
    halts = ledger.state.setdefault("book_halts", {})
    if dd > lim["account_drawdown_stop_frac"] * capital and not halts.get(book):
        reason = (f"{'US ' if book == 'us' else ''}perps account drawdown {dd:.2f} USD > {lim['account_drawdown_stop_frac']:.0%} of {capital:.0f} USD "
                  f"(peak {st['peak']:+.2f}, now {equity:+.2f})")
        halts[book] = reason
        ledger.change({"t": now, "kind": "halt", "scope": f"book:{book}", "reason": reason + "; this book takes no new entries until resumed"})
        return reason
    return None
