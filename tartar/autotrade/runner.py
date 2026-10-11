"""One run of the agent: step every strategy, apply risk limits, fill on paper, mark, score, report."""

from __future__ import annotations

import json
import os
import time
import traceback
from pathlib import Path

from . import lifecycle
from .alpaca import make_mirror, report_lines as alpaca_report
from .broker import LiveBroker, LiveNotAllowed, PaperBroker, make_broker
from .core import Context, Intent
from .ledger import Ledger
from .risk import Risk
from .safety import holder_id, lease_blocker, reconcile, reconcile_perps, record_wallet

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


def _broker(config: dict, status: str, ledger: Ledger, name: str, now: float, root: Path | None = None):
    try:
        return make_broker(config, status, ledger=ledger, root=root, now=now)
    except LiveNotAllowed as exc:
        ledger.journal({"event": "live_refused", "strategy": name, "at": now, "reason": str(exc)})
        return PaperBroker()


def _exit_broker(config: dict, ledger: Ledger, root: Path, now: float):
    """A broker that can sell existing live twins (no new entries), or None if no live route works now."""
    try:
        return LiveBroker(config, ledger=ledger, root=root, entries=False, now=now)
    except LiveNotAllowed:
        return None


def run_once(root: Path = ROOT, now: float | None = None, strategies: dict | None = None, http=None, alpaca=None) -> dict:
    now = time.time() if now is None else now
    root = Path(root)
    config = load_config(root)
    config["mode"] = config.get("mode", "paper")
    ledger = Ledger(root)
    summary = {"at": now, "opened": 0, "closed": 0, "rejected": 0, "errors": {}}
    n_changes = len(ledger.changes())
    if config["mode"] == "live":  # one live trader at a time (safety.py)
        blocker = lease_blocker(ledger.state, holder_id(), now)
        if blocker:
            ledger.journal({"event": "run_skipped", "at": now, "reason": f"live lease held by {blocker}"})
            return {**summary, "skipped": f"live lease held by {blocker}", "changes": [], "halted": None, "new_halts": []}
    risk = Risk(config, root, ledger)
    risk.now = now
    mirror = make_mirror(config, os.environ, root, ledger.journal, client=alpaca)  # Alpaca paper fills (alpaca.py)
    if (config.get("alpaca_paper") or {}).get("enabled"):  # the key is checked every run, trades or not
        ledger.state["alpaca"] = mirror.status(now) if mirror else {"checked_at": now, "ok": False,
                                                                     "error": "secrets APCA_API_KEY_ID / APCA_API_SECRET_KEY not set"}
    if strategies is None:
        from .search import active_candidates

        # candidates queued by the agent's own search (search.py), once their wait is over
        config.setdefault("strategies", {}).update(active_candidates(root, now))
        strategies = build_strategies(config)
    wallet = None
    if config["mode"] in ("live", "dry_live"):  # the book must match the wallet before anything trades
        wallet = _exit_broker(config, ledger, root, now)
        if wallet is not None:
            try:
                rec = reconcile(wallet, now)
            except Exception as exc:  # noqa: BLE001 - can't verify the wallet: paper goes on, live entries stop
                rec = {}
                if not wallet.live_state()["halted"]:
                    wallet.halt("live", f"reconcile failed: {type(exc).__name__}: {exc}"[:300])
            if rec.get("claims") or rec.get("orphans") or rec.get("sold_unrecorded"):
                summary["reconcile"] = {k: len(rec[k]) for k in ("claims", "orphans", "sold_unrecorded")}
            try:
                prec = reconcile_perps(wallet, now)
            except Exception as exc:  # noqa: BLE001 - can't verify the perp account: perp entries stop
                prec = {}
                st = wallet.live_state()
                if not st.get("perps_halted"):
                    st["perps_halted"] = f"perp reconcile failed: {type(exc).__name__}: {exc}"[:300]
                    ledger.change({"t": now, "kind": "halt", "scope": "live:perps", "reason": st["perps_halted"]})
            if prec.get("inflight") or prec.get("mismatch") or prec.get("orphans"):
                summary["perp_reconcile"] = {k: len(prec[k]) for k in ("inflight", "mismatch", "orphans")}

    from . import perp_risk

    books = {n: b for b in perp_risk.BOOKS for n in perp_risk.book_names(config, b)}  # strategy -> its book
    scales = {b: perp_risk.book_scale(ledger, config, config.get("perp_risk", {}), b) for b in perp_risk.BOOKS}
    for name, strat in strategies.items():
        rec = ledger.strategy(name)
        if "registered_at" not in rec:  # the agent's own pre-registration: rule and criteria before any data
            rec["registered_at"] = now
            describe = getattr(strat, "describe", None)
            ledger.change({"t": now, "kind": "registered", "scope": name, "reason": "first run under this rule",
                           "rule": describe() if describe else {}, "prereg": getattr(strat, "prereg", "")})
        describe = getattr(strat, "describe", None)
        desc = describe() if describe else {}
        if desc.get("costs_version") != rec.get("costs_version"):  # a strategy's cost or execution model changed
            if desc.get("costs_version"):
                ledger.change({"t": now, "kind": "cost_update", "scope": name, "reason": desc.get("change_note") or "cost model updated",
                               "from": rec.get("costs_version"), "to": desc.get("costs_version"), "rule": desc})
            rec["costs_version"] = desc.get("costs_version")
        if rec["status"] == "halted" and not risk.retry_due(name, now):
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
        risk.record_ok(name, now)
        broker = _broker(config, rec["status"], ledger, name, now, root)
        exits = lambda: _exit_broker(config, ledger, root, now)  # noqa: E731
        for intent in intents:  # book volatility target (perp_risk.book_scale), before twins are sized from the legs
            scale, scale_why = scales[books[name]] if name in books else (1.0, "")
            if intent.kind == "open" and name in books and "leg_usd" in intent.meta and scale != 1.0:
                intent.notional_usd *= scale
                intent.meta.update(leg_usd=float(intent.meta["leg_usd"]) * scale, book_scale=scale, book_scale_why=scale_why)
        plan = getattr(broker, "plan_book", None)
        if callable(plan) and rec["status"] != "retired":
            plan(name, intents, ledger.positions)
        for intent in sorted(intents, key=lambda i: (i.at, i.kind != "close")):
            summary_key = _apply(intent, rec, ledger, risk, broker, now,
                                 quote=bool(config.get("execution", {}).get("quote_check")) and not intent.meta.get("shadow"),
                                 exit_broker=exits, mirror=mirror)
            summary[summary_key] = summary.get(summary_key, 0) + 1
        finish = getattr(broker, "finish_book", None)
        if callable(finish):
            finish(name, ledger.positions)
        ctx.positions = [p for p in ledger.positions if p.strategy == name]
        try:
            marks = strat.marks(ctx) if ctx.positions else {}
        except Exception as exc:  # noqa: BLE001 - a failed mark keeps the previous one
            marks = {}
            ledger.journal({"event": "mark_error", "strategy": name, "at": now, "error": f"{type(exc).__name__}: {exc}"})
        for pos in ctx.positions:
            if pos.id in marks:
                pos.mark_price, pos.mark_at = marks[pos.id]

    # perps risk controls (perp_risk.py): weekly loss limit per strategy, then the account drawdown stop
    prc = config.get("perp_risk", {})
    for intent in perp_risk.weekly_stops(ledger, strategies, now, prc, http):
        rec = ledger.strategy(intent.strategy)
        k = _apply(intent, rec, ledger, risk, _broker(config, rec["status"], ledger, intent.strategy, now, root), now,
                   exit_broker=lambda: _exit_broker(config, ledger, root, now))
        summary[k] = summary.get(k, 0) + 1
    for b in perp_risk.BOOKS:
        perp_risk.account_drawdown(ledger, config, root, now, prc, b)
    why = risk.kill_reason()
    if why and risk.limits.get("flatten_on_halt"):
        for pos in list(ledger.positions):
            if pos.mark_price is not None:
                intent = Intent("close", pos.strategy, pos.mark_at or now, pos.mark_price, reason=f"flatten: {why}",
                                position_id=pos.id)
                _apply(intent, ledger.strategy(pos.strategy), ledger, risk, PaperBroker(), now,
                       exit_broker=lambda: _exit_broker(config, ledger, root, now), mirror=mirror)
    risk.check_daily(now, ledger.positions)
    summary["changes"] = lifecycle.review(ledger, strategies, now, config.get("lifecycle", {}))
    summary["halted"] = risk.kill_reason()
    summary["new_halts"] = [c for c in ledger.changes()[n_changes:] if c.get("kind") == "halt"]
    if wallet is not None:
        record_wallet(wallet, now)
    ledger.state["last_run"] = {k: v for k, v in summary.items() if k != "changes"}
    ledger._append("equity.jsonl", {
        "t": now, "realized_usd": round(sum(t.pnl_usd for t in ledger.trades()), 4),
        "unrealized_usd": round(sum(p.unrealized() for p in ledger.positions), 4), "open": len(ledger.positions),
        "by_strategy": {n: round(sum(t.pnl_usd for t in ledger.trades(n)), 4) for n in strategies}})
    ledger.save()
    write_report(root, ledger, strategies, now, risk)
    return summary


def _apply(intent: Intent, rec: dict, ledger: Ledger, risk: Risk, broker, now: float, quote: bool = False,
           exit_broker=None, mirror=None) -> str:
    if intent.kind == "close":
        key = intent.meta.get("key")
        pos = next((p for p in ledger.positions if (intent.position_id and p.id == intent.position_id)
                    or (not intent.position_id and key and p.strategy == intent.strategy and p.meta.get("key") == key)), None)
        if pos is None:
            return "stale_close"
        if pos.meta.get("live") and not isinstance(broker, LiveBroker):  # a live twin exits live whatever the status now
            broker = (exit_broker() if exit_broker else None) or broker
            if not isinstance(broker, LiveBroker):
                ledger.state.setdefault("live", {}).setdefault("orphans", []).append(
                    {"position": pos.id, "strategy": pos.strategy, **pos.meta["live"], "error": "no live route at exit", "at": now})
                ledger.journal({"event": "live_orphan", "strategy": pos.strategy, "position": pos.id, "at": now,
                                "reason": "paper exit ran but no live route works now; tokens still held (state live.orphans)"})
        trade, row = broker.close(pos, intent)
        if mirror:
            mirror.on_close(pos, trade, intent, now)
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
    if quote:
        from .quotes import quote_check

        check = quote_check(intent, now)
        if check:
            intent.meta.update(check)
    pos, row = broker.open(intent, ledger.positions) if isinstance(broker, LiveBroker) else broker.open(intent)
    if mirror:
        mirror.on_open(pos, intent, now)
    ledger.positions.append(pos)
    ledger.journal({**row, "logged_at": now})
    return "opened"


def config_mode(root: Path) -> str:
    return load_config(root).get("mode", "paper")


def live_report(ledger: Ledger, mode: str) -> list[str]:
    """Live twins against their paper twins (fills.jsonl)."""
    path = ledger.root / "fills.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
    st = ledger.state.get("live", {})
    if mode == "paper" and not rows:
        return []
    out = ["", f"## Live twins (mode `{mode}`)", ""]
    halts = [f"all live entries: {st['halted']}"] if st.get("halted") else []
    halts += [f"{n}: {r['halted']}" for n, r in st.get("strategies", {}).items() if r.get("halted")]
    out.append("**Live halted:** " + "; ".join(halts) if halts else "Live entries: allowed for promoted strategies.")
    sells = [r for r in rows if r.get("event") == "sell"]
    if sells:
        d = sorted(r["compare"]["live_minus_paper"] for r in sells)
        out += ["", "| Closed | Mean live net (SOL) | Mean paper net | Median live − paper | Net SOL | Dry |", "|---|---|---|---|---|---|",
                f"| {len(sells)} | {100 * sum(r['compare']['live_net_return_sol'] for r in sells) / len(sells):+.2f}% | "
                f"{100 * sum(r['compare']['paper_net_return'] for r in sells) / len(sells):+.2f}% | {100 * d[len(d) // 2]:+.2f} points | "
                f"{sum(r['compare']['net_sol'] for r in sells):+.5f} | {sum(1 for r in sells if r['compare'].get('dry'))} |"]
    perp = [r for r in rows if r.get("event") in ("perp_close", "perp_roll_out")]
    if perp:
        d = sorted(r["compare"]["live_minus_paper"] for r in perp)
        out += ["", "| Perp twins closed (Hyperliquid) | Mean twin net | Mean paper net | Median twin − paper | Net USD | Dry |",
                "|---|---|---|---|---|---|",
                f"| {len(perp)} ({sum(1 for r in perp if r['compare'].get('rolled'))} rolled) | "
                f"{100 * sum(r['compare']['live_net_return_usd'] for r in perp) / len(perp):+.2f}% | "
                f"{100 * sum(r['compare']['paper_net_return'] for r in perp) / len(perp):+.2f}% | {100 * d[len(d) // 2]:+.2f} points | "
                f"{sum(r['compare']['net_usd'] for r in perp):+.2f} | {sum(1 for r in perp if r['compare'].get('dry'))} |"]
    perp_open = [p for p in ledger.positions if p.meta.get("live", {}).get("venue") == "hyperliquid"]
    if perp_open or perp:
        out += ["", f"Open perp twins {len(perp_open)} (${sum(p.meta['live']['notional_in'] for p in perp_open):.2f} notional)."]
    usd = [r for r in rows if r.get("event") == "usd_sell"]
    if usd:
        d = sorted(r["compare"]["live_minus_paper"] for r in usd)
        out += ["", "| USD spot twins closed (Jupiter, USDC) | Mean twin net | Mean paper net | Median twin − paper | Net USD | Dry |",
                "|---|---|---|---|---|---|",
                f"| {len(usd)} | {100 * sum(r['compare']['live_net_return_usd'] for r in usd) / len(usd):+.2f}% | "
                f"{100 * sum(r['compare']['paper_net_return'] for r in usd) / len(usd):+.2f}% | {100 * d[len(d) // 2]:+.2f} points | "
                f"{sum(r['compare']['net_usd'] for r in usd):+.2f} | {sum(1 for r in usd if r['compare'].get('dry'))} |"]
    usd_open = [p for p in ledger.positions if p.meta.get("live", {}).get("venue") == "jupiter_usd"]
    if usd_open or usd:
        out += ["", f"Open USD spot twins {len(usd_open)} (${sum(p.meta['live']['notional_in'] for p in usd_open):.2f})."]
    vault = [r for r in rows if r.get("event") in ("vault_roll_out", "vault_withdraw")]
    if vault:
        d = sorted(r["compare"]["live_minus_paper"] for r in vault)
        out += ["", "| Vault twin intervals (Hyperliquid HLP) | Mean twin | Mean paper | Median twin − paper | Net USD | Dry |",
                "|---|---|---|---|---|---|",
                f"| {len(vault)} | {100 * sum(r['compare']['live_net_return_usd'] for r in vault) / len(vault):+.2f}% | "
                f"{100 * sum(r['compare']['paper_net_return'] for r in vault) / len(vault):+.2f}% | {100 * d[len(d) // 2]:+.2f} points | "
                f"{sum(r['compare']['net_usd'] for r in vault):+.2f} | {sum(1 for r in vault if r['compare'].get('dry'))} |"]
    vault_open = [p for p in ledger.positions if p.meta.get("live", {}).get("venue") == "hyperliquid_vault"]
    if vault_open or vault:
        out += ["", f"Open vault twins {len(vault_open)} (${sum(p.meta['live']['equity'] for p in vault_open):.2f} at their last mark)."]
    open_twins = [p for p in ledger.positions if p.meta.get("live") and p.meta["live"].get("venue") not in ("hyperliquid", "jupiter_usd", "hyperliquid_vault")]
    skips = [r for r in rows if r.get("event") == "skip"]
    out += ["", f"Open twins {len(open_twins)} ({sum(p.meta['live']['sol_in'] for p in open_twins):.4f} SOL); "
                f"skipped entries {len(skips)}" + (f" (latest: {skips[-1]['reason']})" if skips else "") +
            f"; orphans {len(st.get('orphans', []))}.", ""]
    return out


def fmt_t(t: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t)) if t else "-"


def venue_of(cfg: dict) -> tuple[str, bool]:
    """(where it trades, usable by a US person) under AJ's US-only rule (2026-10-11)."""
    kind = cfg.get("kind", "")
    if kind == "coinbase_pattern":
        return "US spot (Coinbase prices, Alpaca paper)", True
    if cfg.get("data") == "coinbase":
        return "US perps (Coinbase)", True
    if kind == "dip":
        return "Solana memecoins (PumpPortal)", True
    if kind in ("xs_momentum", "wick_bounce", "vault_hold"):
        return "Hyperliquid: research only", False
    if kind == "jlp_hedged":
        return "Jupiter + Hyperliquid: research only", False
    if kind == "pumpflow":
        return "Hyperliquid perp: research only", False
    return kind or "-", False


def write_report(root: Path, ledger: Ledger, strategies: dict, now: float, risk: Risk) -> None:
    lines = ["# Paper trading agent: report", "",
             f"Updated {fmt_t(now)}. Mode: **{config_mode(root)}**{' (no real money)' if config_mode(root) != 'live' else ''}. Generated by `python -m tartar.autotrade run`; "
             "rules in `tartar/autotrade/`, settings in `autotrade/config.json`.", ""]
    from .health import report_lines

    lines += report_lines(root, now)
    why = risk.kill_reason()
    lines.append(f"**Halted:** {why}" if why else "**Running.** Kill switch: create `autotrade/HALT` (its text is the reason).")
    scfg = load_config(root).get("strategies", {})
    names = sorted(set(strategies) | set(ledger.state["strategies"]))
    variants = [n for n in names if "~" in n]
    cands = [n for n in names if n.startswith("cand-")]
    names = [n for n in names if "~" not in n and not n.startswith("cand-")]
    names.sort(key=lambda n: not venue_of(scfg.get(n, {}))[1])  # US-usable strategies first
    us = [n for n in names if venue_of(scfg.get(n, {}))[1] and scfg.get(n, {}).get("kind") != "dip"]
    if us:
        us_open = [p for p in ledger.positions if p.strategy in us]
        us_pnl = sum(t.pnl_usd for n in us for t in ledger.trades(n))
        lines += ["", f"**US book at a glance** (strategies a US account could take live: {', '.join(us)}): "
                  f"{len(us_open)} open (${sum(p.notional_usd for p in us_open):,.0f}), realized {us_pnl:+.2f} USD, "
                  f"unrealized {sum(p.unrealized() for p in us_open):+.2f} USD. All paper; scored by their registrations."]
    lines += ["", "| Strategy | Venue | Status | Open | Closed trades | Mean net/trade | PnL (USD) | Score vs registered rule |",
              "|---|---|---|---|---|---|---|---|"]
    total = 0.0
    for name in names + variants + cands:
        if name == (variants[0] if variants else None):
            lines += ["", f"<details><summary>Shadow variants ({len(variants)} research copies of a rule; scored with a family-wide CI; "
                      "outside the risk caps)</summary>", "",
                      "| Variant | Venue | Status | Open | Closed trades | Mean net/trade | PnL (USD) | Score |", "|---|---|---|---|---|---|---|---|"]
        if name == (cands[0] if cands else None):
            if variants:
                lines += ["", "</details>"]
            lines += ["", "Candidates found by the agent's own search (autotrade/candidates/, autotrade/search/REPORT.md; "
                      "paper, outside the risk caps):", "",
                      "| Candidate | Venue | Status | Open | Closed trades | Mean net/trade | PnL (USD) | Score |", "|---|---|---|---|---|---|---|---|"]
        rec = ledger.strategy(name)
        tr = ledger.trades(name)
        pnl = sum(t.pnl_usd for t in tr)
        total += 0.0 if "~" in name or name.startswith("cand-") else pnl
        mean = f"{100 * sum(t.net_return for t in tr) / len(tr):+.2f}%" if tr else "-"
        v = rec.get("verdict") or {}
        n_open = sum(1 for p in ledger.positions if p.strategy == name)
        cfg = scfg.get(name) or scfg.get(name.split("~")[0]) or (strategies[name].cfg if hasattr(strategies.get(name), "cfg") else {})
        lines.append(f"| {name} | {venue_of(cfg)[0]} | {rec['status']} | {n_open} | {len(tr)} | {mean} | {pnl:+.2f} | "
                     f"{v.get('decision', '-')}: {v.get('reason', '')} |")
    if variants and not cands:
        lines += ["", "</details>"]
    checked = [x for x in [*(t.meta for t in ledger.trades()), *(p.meta for p in ledger.positions)] if "jup_impact_measured_pct" in x]
    if checked:
        q = sorted(x["jup_impact_measured_pct"] for x in checked)
        a = sorted(100 * x.get("impact_assumed", 0) for x in checked)
        worse = sum(1 for x in checked if x["jup_impact_measured_pct"] > 2 * 100 * x.get("impact_assumed", 0) + 0.1)
        qn = [t.meta["quoted_net_return"] for t in ledger.trades() if "quoted_net_return" in t.meta and "~" not in t.strategy]
        lines += ["", f"Execution check (Jupiter quotes at entry, same USD size against a $1 probe, {len(checked)} entries): "
                  f"measured price impact median {q[len(q) // 2]:.2f}% (max {q[-1]:.2f}%) vs the cost model's median "
                  f"{a[len(a) // 2]:.2f}% per side; {worse} entries more than twice the model."
                  + (f" Registered strategies' closed trades at the measured impact: mean net {100 * sum(qn) / len(qn):+.2f}% "
                     f"over {len(qn)} trades." if qn else "")]
    lines += live_report(ledger, config_mode(root))
    lines += alpaca_report(root, ledger.state)
    unreal = sum(p.unrealized() for p in ledger.positions if not p.meta.get("shadow"))
    lines += ["", f"Realized PnL {total:+.2f} USD (registered strategies; variants listed above); open positions {len(ledger.positions)}, unrealized {unreal:+.2f} USD "
              f"(entry costs included); today {risk.day_pnl(now, ledger.positions):+.2f} USD "
              f"(each strategy stops new entries for the day below -{risk.limits['daily_loss_cap_usd']:.0f}).", ""]
    changes = ledger.changes()[-10:]
    if changes:
        lines += ["## Recent changes", ""]
        for c in reversed(changes):
            what = f"{c.get('from')} → {c.get('to')}" if c.get("kind") == "status" else c.get("kind")
            if c.get("kind") in ("registered", "cost_update") and "~" in c.get("scope", ""):
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
