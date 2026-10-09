"""One run of the agent: step every strategy, apply risk limits, fill on paper, mark, score, report."""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

from . import lifecycle
from .broker import LiveNotAllowed, PaperBroker, make_broker
from .core import Context, Intent
from .ledger import Ledger
from .risk import Risk

ROOT = Path("autotrade")


def load_config(root: Path) -> dict:
    path = root / "config.json"
    return json.loads(path.read_text()) if path.exists() else {"mode": "paper", "strategies": {}}


def expand_variants(config: dict) -> dict:
    """Config strategies plus shadow variants of a base rule (config "variants"): each grid point is its own
    paper strategy, registered (logged) the first time the agent runs it, scored with the CI widened for
    the number of variants in its family (Bonferroni), and kept out of the risk caps (research only)."""
    out = dict(config.get("strategies", {}))
    for fam in config.get("variants", []):
        base = out[fam["base"]]
        keys = sorted(fam["grid"])
        combos = [{}]
        for k in keys:
            combos = [{**c, k: v} for c in combos for v in fam["grid"][k]]
        combos = [c for c in combos if any(c[k] != fam.get("base_rule", {}).get(k) for k in keys)]  # not the registered rule
        k_family = len(combos) + 1
        for c in combos:
            name = fam["base"] + "~" + "~".join(f"{k}={c[k]}" for k in keys)
            out[name] = {**base, "rule_overrides": c, "shadow": True, "family_size": k_family,
                         "enabled": fam.get("enabled", True) and base.get("enabled", True)}
    return out


def build_strategies(config: dict) -> dict:
    from .strategies import REGISTRY

    out = {}
    for name, scfg in expand_variants(config).items():
        if not scfg.get("enabled", True):
            continue
        kind = scfg.get("kind", name)
        out[name] = REGISTRY[kind](name, scfg)
    return out


def _broker(config: dict, status: str, ledger: Ledger, name: str, now: float):
    try:
        return make_broker(config, status)
    except LiveNotAllowed as exc:
        ledger.journal({"event": "live_refused", "strategy": name, "at": now, "reason": str(exc)})
        return PaperBroker()


def run_once(root: Path = ROOT, now: float | None = None, strategies: dict | None = None, http=None) -> dict:
    now = time.time() if now is None else now
    root = Path(root)
    config = load_config(root)
    config["mode"] = config.get("mode", "paper")
    ledger = Ledger(root)
    risk = Risk(config, root, ledger)
    strategies = build_strategies(config) if strategies is None else strategies
    summary = {"at": now, "opened": 0, "closed": 0, "rejected": 0, "errors": {}}
    n_changes = len(ledger.changes())

    for name, strat in strategies.items():
        rec = ledger.strategy(name)
        if "registered_at" not in rec:  # the agent's own pre-registration: rule and criteria before any data
            rec["registered_at"] = now
            describe = getattr(strat, "describe", None)
            ledger.change({"t": now, "kind": "registered", "scope": name, "reason": "first run under this rule",
                           "rule": describe() if describe else {}, "prereg": getattr(strat, "prereg", "")})
        if rec["status"] == "halted":
            continue
        mine = [p for p in ledger.positions if p.strategy == name]
        ctx = Context(now, mine, rec["data"], config.get("strategies", {}).get(name, {}), http)
        try:
            intents = strat.step(ctx)
        except Exception as exc:  # noqa: BLE001 - a strategy failure must not stop the others
            err = f"{type(exc).__name__}: {exc}"
            summary["errors"][name] = err
            ledger.journal({"event": "error", "strategy": name, "at": now, "error": err,
                            "trace": traceback.format_exc()[-1500:]})
            risk.record_error(name, now, err)
            continue
        risk.record_ok(name)
        broker = _broker(config, rec["status"], ledger, name, now)
        for intent in sorted(intents, key=lambda i: (i.at, i.kind != "close")):
            summary_key = _apply(intent, rec, ledger, risk, broker, now)
            summary[summary_key] = summary.get(summary_key, 0) + 1
        ctx.positions = [p for p in ledger.positions if p.strategy == name]
        try:
            marks = strat.marks(ctx) if ctx.positions else {}
        except Exception as exc:  # noqa: BLE001 - a failed mark keeps the previous one
            marks = {}
            ledger.journal({"event": "mark_error", "strategy": name, "at": now, "error": f"{type(exc).__name__}: {exc}"})
        for pos in ctx.positions:
            if pos.id in marks:
                pos.mark_price, pos.mark_at = marks[pos.id]

    why = risk.kill_reason()
    if why and risk.limits.get("flatten_on_halt"):
        for pos in list(ledger.positions):
            if pos.mark_price is not None:
                intent = Intent("close", pos.strategy, pos.mark_at or now, pos.mark_price, reason=f"flatten: {why}",
                                position_id=pos.id)
                _apply(intent, ledger.strategy(pos.strategy), ledger, risk, PaperBroker(), now)
    risk.check_daily(now, ledger.positions)
    summary["changes"] = lifecycle.review(ledger, strategies, now, config.get("lifecycle", {}))
    summary["halted"] = risk.kill_reason()
    summary["new_halts"] = [c for c in ledger.changes()[n_changes:] if c.get("kind") == "halt"]
    ledger.state["last_run"] = {k: v for k, v in summary.items() if k != "changes"}
    ledger._append("equity.jsonl", {
        "t": now, "realized_usd": round(sum(t.pnl_usd for t in ledger.trades()), 4),
        "unrealized_usd": round(sum(p.unrealized() for p in ledger.positions), 4), "open": len(ledger.positions),
        "by_strategy": {n: round(sum(t.pnl_usd for t in ledger.trades(n)), 4) for n in strategies}})
    ledger.save()
    write_report(root, ledger, strategies, now, risk)
    return summary


def _apply(intent: Intent, rec: dict, ledger: Ledger, risk: Risk, broker, now: float) -> str:
    if intent.kind == "close":
        key = intent.meta.get("key")
        pos = next((p for p in ledger.positions if (intent.position_id and p.id == intent.position_id)
                    or (not intent.position_id and key and p.strategy == intent.strategy and p.meta.get("key") == key)), None)
        if pos is None:
            return "stale_close"
        trade, row = broker.close(pos, intent)
        ledger.positions.remove(pos)
        ledger.add_trade(trade)
        ledger.journal({**row, "logged_at": now})
        return "closed"
    if rec["status"] == "retired":
        ledger.journal({"event": "skipped", "strategy": intent.strategy, "asset": intent.asset, "at": intent.at,
                        "reason": "strategy retired", "logged_at": now})
        return "skipped"
    intent.notional_usd *= rec.get("size_factor", 1.0)
    why = risk.allow_open(intent, ledger.positions)
    if why:
        ledger.journal({"event": "rejected", "strategy": intent.strategy, "asset": intent.asset, "at": intent.at,
                        "notional_usd": intent.notional_usd, "reason": why, "logged_at": now})
        return "rejected"
    pos, row = broker.open(intent)
    ledger.positions.append(pos)
    ledger.journal({**row, "logged_at": now})
    return "opened"


def fmt_t(t: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t)) if t else "-"


def write_report(root: Path, ledger: Ledger, strategies: dict, now: float, risk: Risk) -> None:
    lines = ["# Paper trading agent: report", "",
             f"Updated {fmt_t(now)}. Mode: **paper** (no real money). Generated by `python -m tartar.autotrade run`; "
             "rules in `tartar/autotrade/`, settings in `autotrade/config.json`.", ""]
    why = risk.kill_reason()
    lines.append(f"**Halted:** {why}" if why else "**Running.** Kill switch: create `autotrade/HALT` (its text is the reason).")
    lines += ["", "| Strategy | Status | Open | Closed trades | Mean net/trade | PnL (USD) | Score vs registered rule |",
              "|---|---|---|---|---|---|---|"]
    total = 0.0
    names = sorted(set(strategies) | set(ledger.state["strategies"]))
    for name in names:
        rec = ledger.strategy(name)
        tr = ledger.trades(name)
        pnl = sum(t.pnl_usd for t in tr)
        total += pnl
        mean = f"{100 * sum(t.net_return for t in tr) / len(tr):+.2f}%" if tr else "-"
        v = rec.get("verdict") or {}
        n_open = sum(1 for p in ledger.positions if p.strategy == name)
        lines.append(f"| {name} | {rec['status']} | {n_open} | {len(tr)} | {mean} | {pnl:+.2f} | "
                     f"{v.get('decision', '-')}: {v.get('reason', '')} |")
    unreal = sum(p.unrealized() for p in ledger.positions)
    lines += ["", f"Realized PnL {total:+.2f} USD; open positions {len(ledger.positions)}, unrealized {unreal:+.2f} USD "
              f"(entry costs included); today {risk.day_pnl(now, ledger.positions):+.2f} USD "
              f"(cap -{risk.limits['daily_loss_cap_usd']:.0f}).", ""]
    changes = ledger.changes()[-10:]
    if changes:
        lines += ["## Recent changes", ""]
        for c in reversed(changes):
            what = f"{c.get('from')} → {c.get('to')}" if c.get("kind") == "status" else c.get("kind")
            if c.get("kind") == "registered" and "~" in c.get("scope", ""):
                continue  # variant registrations: see changes.jsonl
            lines.append(f"* {fmt_t(c['t'])} **{c.get('scope')}** {what}: {c.get('reason')}")
        lines.append("")
    if ledger.positions:
        lines += ["## Open positions", "", "| Strategy | Asset | Side | Notional | Entry | Mark | Unrealized |", "|---|---|---|---|---|---|---|"]
        for p in sorted(ledger.positions, key=lambda p: p.entry_at)[-30:]:
            lines.append(f"| {p.strategy} | {p.meta.get('label', p.asset)[:24]} | {'long' if p.side > 0 else 'short'} | "
                         f"{p.notional_usd:.0f} | {p.entry_price:.6g} @ {fmt_t(p.entry_at)} | "
                         f"{p.mark_price if p.mark_price is None else f'{p.mark_price:.6g}'} | {p.unrealized():+.2f} |")
        lines.append("")
    (root / "REPORT.md").write_text("\n".join(lines))
