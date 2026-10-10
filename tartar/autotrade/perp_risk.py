"""Risk controls for the perps strategies (weekly long-short books on Hyperliquid), applied to the paper book
every run, so live twins, which exit with their paper legs, inherit them. Scored on the search's 146-week
backtest by handoff/experiments/perps_risk_controls.py (results in handoff/autotrade.md):

* **Weekly loss limit** (``weekly_stop_frac``, default 0.12): when a strategy's P&L for its current week
  (closed legs of that week plus open legs at their marks) falls below ``-weekly_stop_frac`` x its side
  notional (``leg_usd``), every open leg closes at its mark (20 bps per side, funding carried) and the
  strategy sits out until its next weekly rebalance. In the backtest a 12% stop kept the mean weekly
  return (candidate +2.92% vs +2.83%, vol-momentum +1.31% vs +1.42%, xs +1.10% vs +1.03%) and cut the
  worst week from -36/-24/-31% to -25/-22/-18%.
* **Account drawdown stop** (``account_drawdown_stop_frac``, default 0.35): when the registered (non-shadow)
  perps strategies' combined P&L falls more than that fraction of their combined side notional below its
  peak, the agent writes the kill switch file ``HALT`` (new entries stop everywhere; exits still run) and
  logs a halt, which fails the Action so the owner is emailed.

Inverse-volatility sizing was scored too and cost return on every rule, so legs stay equal weight.
"""

from __future__ import annotations

from .core import Context, CostModel, Intent

DEFAULTS = {"weekly_stop_frac": 0.12, "account_drawdown_stop_frac": 0.35, "exit_cost": 0.002}


def is_perp_book(pos) -> bool:
    return pos.meta.get("venue") == "hyperliquid" and "week" in pos.meta and "leg_usd" in pos.meta


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


def account_drawdown(ledger, config: dict, root, now: float, cfg: dict) -> str | None:
    """Write HALT when the registered perps book's drawdown passes the limit; returns the reason if it fired now."""
    lim = {**DEFAULTS, **cfg}
    names = [n for n, s in config.get("strategies", {}).items()
             if s.get("kind") == "xs_momentum" and s.get("enabled", True) and not s.get("shadow")]
    capital = sum(float(config["strategies"][n].get("leg_usd", 100.0)) for n in names)
    if not names or capital <= 0:
        return None
    equity = sum(t.pnl_usd for n in names for t in ledger.trades(n)) + \
        sum(p.unrealized() for p in ledger.positions if p.strategy in names)
    st = ledger.state.setdefault("perp_risk", {})
    st["peak"] = max(st.get("peak", 0.0), equity)
    st["equity"] = equity
    dd = st["peak"] - equity
    st["drawdown_frac"] = dd / capital
    halt = root / "HALT"
    if dd > lim["account_drawdown_stop_frac"] * capital and not halt.exists():
        reason = (f"perps account drawdown {dd:.2f} USD > {lim['account_drawdown_stop_frac']:.0%} of {capital:.0f} USD "
                  f"(peak {st['peak']:+.2f}, now {equity:+.2f})")
        halt.write_text(reason + "\n")
        ledger.change({"t": now, "kind": "halt", "scope": "agent", "reason": reason})
        return reason
    return None
