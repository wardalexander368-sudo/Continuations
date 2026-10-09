"""Execution. PaperBroker books fills at the reference price less the cost model.

LiveBroker keeps that paper book unchanged (the lifecycle keeps scoring the registered rule on it) and
mirrors each entry with a real "live twin" in SOL, sized by the ``live`` config, through the route
``execution.select_route`` picks (Jupiter with our own key, else PumpPortal Lightning). The twin's
exit follows the paper exit, and every leg goes to ``fills.jsonl`` beside its paper twin.

Modes (config ``mode``):
* ``paper``: no twins.
* ``dry_live``: twins through the quote-only ``dry`` route: nothing is signed or sent, no key needed.
  Exercises the whole live path (sizing, limits, kill switch, fill log) on real quotes.
* ``live``: real twins. Needs config ``live_approved_on`` set to a date AND the environment variable
  ``TARTAR_LIVE_APPROVED`` equal to it (the user's standing approval) AND a route key. The committed
  config stays on paper; going live needs the user's explicit go.

Only ``promoted`` strategies get new twins; a twin's exit runs whatever the strategy's status is now.
Live-only limits (config ``live``) sit on top of the paper risk caps: see ``LIVE_DEFAULTS``."""

from __future__ import annotations

import os
import time
from pathlib import Path

from .core import CostModel, Intent, Position, Trade
from .execution import make_executor, select_route
from .perps import PERP_DEFAULTS, is_perp, make_perp_executor, perp_keys, select_perp_route


class LiveNotAllowed(RuntimeError):
    pass


class PaperBroker:
    mode = "paper"

    def open(self, intent: Intent) -> tuple[Position, dict]:
        cost = intent.cost.side_cost(intent.notional_usd)
        pos = Position.new(intent, cost, self.mode)
        return pos, {"event": "open", "mode": self.mode, "position": pos.id, "strategy": intent.strategy,
                     "asset": intent.asset, "side": intent.side, "notional_usd": intent.notional_usd,
                     "price": intent.price, "at": intent.at, "cost_usd": round(cost, 6), "reason": intent.reason}

    def close(self, pos: Position, intent: Intent) -> tuple[Trade, dict]:
        exit_cost = intent.cost.side_cost(pos.notional_usd)
        gross = pos.gross_pnl(intent.price)
        extra = float(intent.meta.get("carry_usd", 0.0))  # e.g. perp funding over the holding period
        pnl = gross - pos.entry_cost_usd - exit_cost + extra
        meta = {**pos.meta, **intent.meta}
        alt = meta.get("alt_cost")  # a second cost model to report beside the registered one
        if alt:
            alt_cost = CostModel(**alt).side_cost(pos.notional_usd)
            meta["alt_net_return"] = (gross - 2 * alt_cost + extra) / pos.notional_usd
        measured = meta.get("jup_impact_measured_pct")  # impact measured on the real route at entry (quotes.py)
        if measured is not None:
            base = CostModel(**alt) if alt else intent.cost
            q_cost = CostModel(fee=base.fee, impact=max(measured, 0.0) / 100, fixed_usd=base.fixed_usd).side_cost(pos.notional_usd)
            meta["quoted_net_return"] = (gross - 2 * q_cost + extra) / pos.notional_usd  # exit assumed as deep as entry
        trade = Trade(id=pos.id, strategy=pos.strategy, asset=pos.asset, side=pos.side, notional_usd=pos.notional_usd,
                      entry_price=pos.entry_price, entry_at=pos.entry_at, exit_price=intent.price, exit_at=intent.at,
                      cost_usd=pos.entry_cost_usd + exit_cost, pnl_usd=pnl, net_return=pnl / pos.notional_usd,
                      mode=self.mode, reason=intent.reason, meta=meta)
        return trade, {"event": "close", "mode": self.mode, "position": pos.id, "strategy": pos.strategy,
                       "asset": pos.asset, "price": intent.price, "at": intent.at, "cost_usd": round(exit_cost, 6),
                       "pnl_usd": round(pnl, 6), "net_return": round(trade.net_return, 6), "reason": intent.reason}


LIVE_DEFAULTS = {
    "route": "auto",              # auto | jupiter | lightning | dry
    "max_trade_sol": 0.01,        # per live entry
    "min_trade_sol": 0.002,       # smaller entries are skipped (fees and rent dominate)
    "budget_sol": 0.03,           # SOL at risk in open live twins, all strategies together
    "reserve_sol": 0.01,          # always left in the wallet for network fees and rent
    "daily_loss_cap_sol": 0.01,   # realized live loss in a UTC day; beyond it live entries stop until resume
    "max_trade_loss_pct": 0.25,   # one live round trip losing more halts live entries for that strategy
    "max_divergence_pct": 0.03,   # live net return worse than its paper twin by more than this ...
    "divergence_streak": 3,       # ... this many closes in a row halts live entries for that strategy
    "max_signal_age_s": 900,      # an entry whose reference price is older than this is not mirrored
    "priority_sol": 0.00002,
    "dry_balance_sol": 0.05,
    # "perps": Hyperliquid perp twins, in USD; defaults in perps.PERP_DEFAULTS
}


class LiveBroker(PaperBroker):
    """The paper fill plus a live twin. ``entries=False`` only runs exits of existing twins."""

    def __init__(self, config: dict, ledger=None, root=None, executor=None, env=None, entries: bool = True, now: float | None = None,
                 perp_executor=None):
        env = os.environ if env is None else env
        mode = config.get("mode")
        self.cfg = {**LIVE_DEFAULTS, **config.get("live", {})}
        if mode == "dry_live":
            self.cfg["route"] = "dry"
        elif mode == "live":
            approved = config.get("live_approved_on")
            if not approved or env.get("TARTAR_LIVE_APPROVED") != approved:
                raise LiveNotAllowed("live trading is not approved (config live_approved_on and TARTAR_LIVE_APPROVED must match)")
        else:
            raise LiveNotAllowed(f"mode {mode!r} has no live twins")
        route = select_route(self.cfg, env)
        if route is None:
            raise LiveNotAllowed("no route key: set TARTAR_WALLET_KEY (Jupiter) or PUMPPORTAL_API_KEY (Lightning)")
        self.route = route
        self.mode = "dry_live" if route == "dry" else "live"
        self.executor = executor or make_executor(route, self.cfg, env)
        self.ledger, self.root, self.env, self.entries = ledger, Path(root) if root else None, env, entries
        self.now = time.time() if now is None else now
        self._sol_usd: float | None = None
        self.pcfg = {**PERP_DEFAULTS, **self.cfg.get("perps", {})}
        self.perp_route = select_perp_route(mode, env)
        self._perp_exec = perp_executor

    # state
    def live_state(self) -> dict:
        st = self.ledger.state.setdefault("live", {})
        st.setdefault("halted", None)
        st.setdefault("strategies", {})
        st.setdefault("daily_sol", {})
        st.setdefault("orphans", [])
        return st

    def strat_state(self, name: str) -> dict:
        rec = self.live_state()["strategies"].setdefault(name, {})
        rec.setdefault("halted", None)
        rec.setdefault("divergence_run", 0)
        return rec

    def sol_usd(self) -> float:
        if self._sol_usd is None:
            self._sol_usd = float(self.executor.sol_usd())
        return self._sol_usd

    def log(self, row: dict) -> None:
        self.ledger._append("fills.jsonl", {"logged_at": self.now, "route": self.route, "mode": self.mode, **row})

    def halt(self, scope: str, reason: str) -> None:
        if scope == "live":
            self.live_state()["halted"] = reason
        else:
            self.strat_state(scope)["halted"] = reason
        self.ledger.change({"t": self.now, "kind": "halt", "scope": f"live:{scope}", "reason": reason})

    def kill_reason(self, strategy: str) -> str | None:
        if self.root and (self.root / "HALT").exists():
            return "kill switch: HALT"
        if self.root and (self.root / "HALT_LIVE").exists():
            return "live kill switch: " + ((self.root / "HALT_LIVE").read_text().strip() or "HALT_LIVE file present")
        if self.env.get("TARTAR_LIVE_KILL"):
            return "live kill switch: TARTAR_LIVE_KILL is set"
        st = self.live_state()
        return st["halted"] or self.ledger.state.get("halted") or self.strat_state(strategy)["halted"]

    # entry
    def entry_block(self, intent: Intent, positions: list[Position]) -> tuple[str | None, float]:
        """(why not, SOL size)."""
        if not self.entries:
            return "strategy not promoted", 0.0
        if intent.meta.get("shadow"):
            return "shadow variant", 0.0
        why = self.kill_reason(intent.strategy)
        if why:
            return why, 0.0
        mint = intent.meta.get("mint")
        if not mint:
            return "asset has no Solana mint (no live route)", 0.0
        if intent.side != 1:
            return "short side has no spot route", 0.0
        age = self.now - intent.at
        if age > self.cfg["max_signal_age_s"]:
            return f"signal {age:.0f} s old > {self.cfg['max_signal_age_s']:.0f} s", 0.0
        twins = [p.meta["live"] for p in positions if p.meta.get("live") and not is_perp(p.meta["live"])]
        if any(t["mint"] == mint for t in twins):
            return "a live twin already holds this mint", 0.0
        at_risk = sum(t["sol_in"] for t in twins)
        try:
            free = self.executor.balance_sol() - self.cfg["reserve_sol"]
        except Exception as exc:  # noqa: BLE001
            return f"balance unavailable: {exc}"[:200], 0.0
        size = min(self.cfg["max_trade_sol"], self.cfg["budget_sol"] - at_risk, free)
        size *= self.ledger.strategy(intent.strategy).get("size_factor", 1.0) if self.ledger else 1.0
        if size < self.cfg["min_trade_sol"]:
            return f"size {size:.4f} SOL < min {self.cfg['min_trade_sol']} (budget {self.cfg['budget_sol']}, at risk {at_risk:.4f}, free {free:.4f})", 0.0
        return None, round(size, 6)

    def open(self, intent: Intent, positions: list[Position] | None = None) -> tuple[Position, dict]:
        if is_perp(intent.meta):
            return self._open_perp(intent, positions or [])
        pos, row = super().open(intent)
        pos.mode = row["mode"] = "paper"  # until a twin is bought
        why, size = self.entry_block(intent, positions or [])
        if why:
            row["live"] = {"skipped": why}
            if self.entries and not intent.meta.get("shadow"):
                self.log({"event": "skip", "strategy": intent.strategy, "position": pos.id, "reason": why, "at": intent.at})
            return pos, row
        mint = intent.meta["mint"]
        try:
            sol_usd = self.sol_usd()
        except Exception as exc:  # noqa: BLE001 - no reference price: don't trade blind
            self.log({"event": "skip", "strategy": intent.strategy, "position": pos.id, "reason": f"SOL/USD unavailable: {exc}"[:200]})
            return pos, row
        f = self.executor.buy(mint, size)
        rec = {"event": "buy", "strategy": intent.strategy, "position": pos.id, "asset": intent.asset, "fill": f.to_dict(),
               "paper_price_usd": intent.price, "paper_at": intent.at, "sol_usd": sol_usd,
               "paper_side_cost_pct": 100 * intent.cost.side_cost(intent.notional_usd) / intent.notional_usd}
        if f.ok:
            if f.quote_out:
                rec["shortfall_vs_quote_bps"] = 1e4 * (1 - f.token_raw / f.quote_out)
            pos.meta["live"] = {"mint": mint, "route": self.route, "sol_in": f.sol, "token_raw": f.token_raw, "sol_usd_in": sol_usd,
                                "paper_price_in": intent.price, "bought_at": self.now,
                                "rent_sol": f.rent_sol, "signature": f.signature, "dry": f.dry}
            pos.mode = row["mode"] = self.mode
            row["live"] = {k: pos.meta["live"][k] for k in ("route", "sol_in", "token_raw")}
        else:
            row["live"] = {"failed": f.error}
            self.ledger.journal({"event": "live_error", "strategy": intent.strategy, "position": pos.id, "leg": "buy",
                                 "error": f.error, "at": self.now})
        self.log(rec)
        return pos, row

    # exit
    def close(self, pos: Position, intent: Intent) -> tuple[Trade, dict]:
        twin = pos.meta.get("live")
        if twin and is_perp(twin):
            return self._close_perp(pos, intent)
        trade, row = super().close(pos, intent)
        trade.mode = pos.mode
        if not twin:
            return trade, row
        if twin["route"] != self.route:
            if twin.get("dry"):  # a dry twin held nothing real
                row["live"] = {"dropped": f"dry twin closed while on route {self.route}"}
                return trade, row
            self.live_state()["orphans"].append({"position": pos.id, "strategy": pos.strategy, **twin, "at": self.now,
                                                 "error": f"bought on {twin['route']}, now on {self.route}"})
            self.ledger.journal({"event": "live_orphan", "strategy": pos.strategy, "position": pos.id, "at": self.now,
                                 "reason": f"twin bought on {twin['route']}, current route {self.route}; tokens still held"})
            row["live"] = {"failed": "route changed"}
            return trade, row
        f = self.executor.sell(twin["mint"], twin["token_raw"])
        if not f.ok:
            self.live_state()["orphans"].append({"position": pos.id, "strategy": pos.strategy, **twin, "error": f.error, "at": self.now})
            self.ledger.journal({"event": "live_error", "strategy": pos.strategy, "position": pos.id, "leg": "sell",
                                 "error": f.error, "at": self.now})
            self.log({"event": "sell_failed", "strategy": pos.strategy, "position": pos.id, "fill": f.to_dict()})
            self.halt(pos.strategy, f"live sell failed ({f.error}); twin kept in live.orphans")
            row["live"] = {"failed": f.error}
            return trade, row
        try:
            sol_usd_out = self.sol_usd()
        except Exception:  # noqa: BLE001
            sol_usd_out = twin["sol_usd_in"]
        net_sol = f.sol + float(f.extra.get("rent_back_sol", 0.0)) - twin["sol_in"] - twin.get("rent_sol", 0.0)
        live_ret_sol = net_sol / twin["sol_in"]
        live_ret_usd = (f.sol * sol_usd_out) / (twin["sol_in"] * twin["sol_usd_in"]) - 1
        cmp = {"live_net_return_sol": live_ret_sol, "live_net_return_usd": live_ret_usd, "paper_net_return": trade.net_return,
               "live_minus_paper": live_ret_usd - trade.net_return, "sol_in": twin["sol_in"], "sol_out": f.sol, "net_sol": net_sol,
               "route": twin["route"], "dry": twin.get("dry", False),
               "shortfall_vs_quote_bps": 1e4 * (1 - f.sol * 1e9 / f.quote_out) if f.quote_out else None,
               "paper_exit_price": intent.price, "hold_s": self.now - twin["bought_at"]}
        trade.meta["live"] = cmp
        row["live"] = cmp
        self.log({"event": "sell", "strategy": pos.strategy, "position": pos.id, "fill": f.to_dict(), "compare": cmp})
        st = self.live_state()
        day = time.strftime("%Y-%m-%d", time.gmtime(self.now))
        st["daily_sol"][day] = st["daily_sol"].get(day, 0.0) + net_sol
        if st["daily_sol"][day] < -self.cfg["daily_loss_cap_sol"] and not st["halted"]:
            self.halt("live", f"live daily loss {st['daily_sol'][day]:.4f} SOL < -{self.cfg['daily_loss_cap_sol']} SOL")
        srec = self.strat_state(pos.strategy)
        if live_ret_sol < -self.cfg["max_trade_loss_pct"] and not srec["halted"]:
            self.halt(pos.strategy, f"live round trip {100 * live_ret_sol:+.1f}% < -{100 * self.cfg['max_trade_loss_pct']:.0f}%")
        srec["divergence_run"] = srec["divergence_run"] + 1 if cmp["live_minus_paper"] < -self.cfg["max_divergence_pct"] else 0
        if srec["divergence_run"] >= self.cfg["divergence_streak"] and not srec["halted"]:
            self.halt(pos.strategy, f"live fills worse than paper by > {100 * self.cfg['max_divergence_pct']:.0f} points "
                                    f"{srec['divergence_run']} closes in a row")
        return trade, row


    # perps (Hyperliquid; perps.py)
    def perp_exec(self):
        if self._perp_exec is None:
            self._perp_exec = make_perp_executor(self.perp_route, self.pcfg, self.env)
        return self._perp_exec

    def perp_entry_block(self, intent: Intent, positions: list[Position]) -> tuple[str | None, float]:
        """(why not, USD notional)."""
        if intent.meta.get("shadow"):
            return "shadow variant", 0.0
        if self.perp_route is None:
            return "no perp route: live Hyperliquid orders are not built (perps.py)", 0.0
        if not (self.entries or (self.perp_route == "dry" and self.pcfg["dry_all"])):
            return "strategy not promoted", 0.0
        why = self.kill_reason(intent.strategy)
        if why:
            return why, 0.0
        age = self.now - intent.at
        if age > self.pcfg["max_signal_age_s"]:
            return f"signal {age:.0f} s old > {self.pcfg['max_signal_age_s']:.0f} s", 0.0
        at_risk = sum(p.meta["live"]["notional_in"] for p in positions if p.meta.get("live") and is_perp(p.meta["live"]))
        at_risk += sum(h["notional_in"] for h in self.live_state().get("perp_handover", []))
        size = min(self.pcfg["max_leg_usd"], self.pcfg["budget_usd"] - at_risk)
        size *= self.ledger.strategy(intent.strategy).get("size_factor", 1.0) if self.ledger else 1.0
        if size < self.pcfg["min_leg_usd"]:
            return f"size ${size:.2f} < min ${self.pcfg['min_leg_usd']:.0f} (budget ${self.pcfg['budget_usd']:.0f}, at risk ${at_risk:.2f})", 0.0
        return None, round(size, 2)

    def _open_perp(self, intent: Intent, positions: list[Position]) -> tuple[Position, dict]:
        pos, row = PaperBroker.open(self, intent)
        pos.mode = row["mode"] = "paper"
        coin, side = intent.meta.get("coin", intent.asset), intent.side
        hand = self.live_state().setdefault("perp_handover", [])
        held = next((h for h in hand if h["strategy"] == intent.strategy and h["coin"] == coin and h["side"] == side), None)
        if held:  # a kept leg: the twin carries on without trading
            hand.remove(held)
            pos.meta["live"] = {k: v for k, v in held.items() if k != "strategy"} | {"paper_price_in": intent.price}
            pos.mode = row["mode"] = self.mode
            row["live"] = {"rolled": True, "notional_in": held["notional_in"]}
            self.log({"event": "perp_roll_in", "strategy": intent.strategy, "position": pos.id, "coin": coin, "side": side})
            return pos, row
        why, usd = self.perp_entry_block(intent, positions)
        if why:
            row["live"] = {"skipped": why}
            if not intent.meta.get("shadow"):
                self.log({"event": "skip", "venue": "hyperliquid", "strategy": intent.strategy, "position": pos.id, "reason": why, "at": intent.at})
            return pos, row
        f = self.perp_exec().open(coin, side, usd)
        rec = {"event": "perp_open", "strategy": intent.strategy, "position": pos.id, "coin": coin, "fill": f.to_dict(),
               "paper_price_usd": intent.price, "paper_at": intent.at,
               "paper_side_cost_pct": 100 * intent.cost.side_cost(intent.notional_usd) / intent.notional_usd}
        if f.ok:
            rec["vs_paper_price_bps"] = 1e4 * side * (f.px / intent.price - 1)
            pos.meta["live"] = {"venue": "hyperliquid", "coin": coin, "side": side, "route": self.perp_route, "sz": f.sz,
                                "px_in": f.px, "notional_in": f.notional_usd, "fee_in": f.fee_usd, "opened_at": self.now,
                                "paper_price_in": intent.price, "dry": f.dry}
            pos.mode = row["mode"] = self.mode
            row["live"] = {"venue": "hyperliquid", "sz": f.sz, "px_in": f.px, "notional_in": f.notional_usd}
        else:
            row["live"] = {"failed": f.error}
            self.ledger.journal({"event": "live_error", "strategy": intent.strategy, "position": pos.id, "leg": "perp_open",
                                 "error": f.error, "at": self.now})
        self.log(rec)
        return pos, row

    def _close_perp(self, pos: Position, intent: Intent) -> tuple[Trade, dict]:
        twin = pos.meta["live"]
        trade, row = PaperBroker.close(self, pos, intent)
        trade.mode = pos.mode
        coin, side, ex = twin["coin"], twin["side"], None
        if twin["route"] != self.perp_route:
            if twin.get("dry"):
                row["live"] = {"dropped": f"dry perp twin closed while the perp route is {self.perp_route}"}
                return trade, row
            self.live_state()["orphans"].append({"position": pos.id, "strategy": pos.strategy, **twin, "at": self.now,
                                                 "error": f"opened on {twin['route']}, perp route now {self.perp_route}"})
            self.ledger.journal({"event": "live_orphan", "strategy": pos.strategy, "position": pos.id, "at": self.now,
                                 "reason": f"perp twin opened on {twin['route']}, perp route now {self.perp_route}; position still open"})
            row["live"] = {"failed": "perp route changed"}
            return trade, row
        ex = self.perp_exec()
        kept = bool(intent.meta.get("kept")) or "(kept)" in intent.reason
        if kept:  # the leg stays: mark at mid, no trade, hand the twin to the reopen
            try:
                px_out, fee_out = ex.mid(coin), 0.0
            except Exception:  # noqa: BLE001
                px_out, fee_out = intent.price * twin["px_in"] / twin["paper_price_in"], 0.0
            event = "perp_roll_out"
        else:
            f = ex.close(coin, side, twin["sz"])
            if not f.ok:
                self.live_state()["orphans"].append({"position": pos.id, "strategy": pos.strategy, **twin, "error": f.error, "at": self.now})
                self.ledger.journal({"event": "live_error", "strategy": pos.strategy, "position": pos.id, "leg": "perp_close",
                                     "error": f.error, "at": self.now})
                self.log({"event": "perp_close_failed", "strategy": pos.strategy, "position": pos.id, "fill": f.to_dict()})
                self.halt(pos.strategy, f"perp close failed ({f.error}); twin kept in live.orphans")
                row["live"] = {"failed": f.error}
                return trade, row
            px_out, fee_out, event = f.px, f.fee_usd, "perp_close"
        try:
            funding = ex.funding_usd(coin, side, twin["notional_in"], twin["opened_at"], self.now)
            ferr = None
        except Exception as exc:  # noqa: BLE001
            funding, ferr = 0.0, f"{type(exc).__name__}: {exc}"[:120]
        gross = side * twin["sz"] * (px_out - twin["px_in"])
        net = gross - twin["fee_in"] - fee_out + funding
        ret = net / twin["notional_in"]
        cmp = {"venue": "hyperliquid", "live_net_return_usd": ret, "paper_net_return": trade.net_return,
               "live_minus_paper": ret - trade.net_return, "net_usd": net, "notional_in": twin["notional_in"],
               "px_in": twin["px_in"], "px_out": px_out, "fees_usd": twin["fee_in"] + fee_out, "funding_usd": funding,
               "funding_error": ferr, "route": twin["route"], "dry": twin.get("dry", False), "rolled": kept,
               "paper_exit_price": intent.price, "hold_s": self.now - twin["opened_at"]}
        trade.meta["live"] = cmp
        row["live"] = cmp
        self.log({"event": event, "strategy": pos.strategy, "position": pos.id, "coin": coin, "compare": cmp})
        if kept:
            self.live_state().setdefault("perp_handover", []).append(
                {**{k: v for k, v in twin.items() if k != "paper_price_in"}, "strategy": pos.strategy, "px_in": px_out,
                 "notional_in": twin["sz"] * px_out, "fee_in": 0.0, "opened_at": self.now})
        st = self.live_state()
        day = time.strftime("%Y-%m-%d", time.gmtime(self.now))
        st.setdefault("daily_usd_perps", {})
        st["daily_usd_perps"][day] = st["daily_usd_perps"].get(day, 0.0) + net
        if st["daily_usd_perps"][day] < -self.pcfg["daily_loss_cap_usd"] and not st["halted"]:
            self.halt("live", f"perp twins' daily loss ${st['daily_usd_perps'][day]:.2f} < -${self.pcfg['daily_loss_cap_usd']:.2f}")
        srec = self.strat_state(pos.strategy)
        if not kept and ret < -self.pcfg["max_trade_loss_pct"] and not srec["halted"]:
            self.halt(pos.strategy, f"perp twin round trip {100 * ret:+.1f}% < -{100 * self.pcfg['max_trade_loss_pct']:.0f}%")
        srec["divergence_run"] = srec["divergence_run"] + 1 if cmp["live_minus_paper"] < -self.pcfg["max_divergence_pct"] else 0
        if srec["divergence_run"] >= self.pcfg["divergence_streak"] and not srec["halted"]:
            self.halt(pos.strategy, f"perp twins worse than paper by > {100 * self.pcfg['max_divergence_pct']:.0f} points "
                                    f"{srec['divergence_run']} closes in a row")
        return trade, row


def make_broker(config: dict, strategy_status: str, ledger=None, root=None, now: float | None = None) -> PaperBroker:
    """Paper unless the mode has live twins; live conditions that fail raise LiveNotAllowed (the runner then
    falls back to paper and journals why)."""
    if config.get("mode") in ("live", "dry_live"):
        return LiveBroker(config, ledger=ledger, root=root, entries=strategy_status == "promoted", now=now)
    return PaperBroker()


def preflight(config: dict, ledger, root, env=None) -> dict:
    """Everything the live path needs, checked without trading: what would happen on the next run."""
    env = os.environ if env is None else env
    cfg = {**LIVE_DEFAULTS, **config.get("live", {})}
    mode = config.get("mode", "paper")
    approved = config.get("live_approved_on")
    route = "dry" if mode == "dry_live" else select_route(cfg, env)
    root = Path(root)
    out = {"mode": mode, "route": route, "approved_on": approved,
           "approval_matches": bool(approved) and env.get("TARTAR_LIVE_APPROVED") == approved,
           "keys": {"TARTAR_WALLET_KEY": bool(env.get("TARTAR_WALLET_KEY")), "PUMPPORTAL_API_KEY": bool(env.get("PUMPPORTAL_API_KEY")),
                    "JUPITER_API_KEY": bool(env.get("JUPITER_API_KEY"))},
           "kill_switches": [k for k, on in (("HALT", (root / "HALT").exists()), ("HALT_LIVE", (root / "HALT_LIVE").exists()),
                                              ("TARTAR_LIVE_KILL", bool(env.get("TARTAR_LIVE_KILL")))) if on],
           "live_halts": {**({"all": ledger.state.get("live", {}).get("halted")} if ledger.state.get("live", {}).get("halted") else {}),
                          **{n: r["halted"] for n, r in ledger.state.get("live", {}).get("strategies", {}).items() if r.get("halted")}},
           "orphans": len(ledger.state.get("live", {}).get("orphans", [])),
           "promoted": sorted(n for n, r in ledger.state.get("strategies", {}).items() if r.get("status") == "promoted"),
           "limits": cfg, "problems": [],
           "perps": {"route": select_perp_route(mode, env), "keys": perp_keys(env),
                     "limits": {**PERP_DEFAULTS, **cfg.get("perps", {})},
                     "note": "dry only: live Hyperliquid orders are not built (tartar/autotrade/perps.py)"}}
    p = out["problems"]
    if mode == "paper":
        p.append("mode is paper: no live twins")
    if mode == "live" and not out["approval_matches"]:
        p.append("live_approved_on and TARTAR_LIVE_APPROVED do not match")
    if mode == "live" and route is None:
        p.append("no route key (TARTAR_WALLET_KEY or PUMPPORTAL_API_KEY)")
    if route == "lightning" and not cfg.get("lightning_wallet"):
        p.append("route lightning needs live.lightning_wallet (public key)")
    if out["kill_switches"]:
        p.append("kill switch on: " + ", ".join(out["kill_switches"]))
    if not out["promoted"]:
        p.append("no strategy is promoted yet")
    if route in ("jupiter", "lightning") and not p:
        try:
            ex = make_executor(route, cfg, env)
            out["wallet"] = ex.wallet
            out["balance_sol"] = ex.balance_sol()
            if out["balance_sol"] - cfg["reserve_sol"] < cfg["min_trade_sol"]:
                p.append(f"wallet balance {out['balance_sol']:.4f} SOL leaves less than min_trade_sol after the reserve")
        except Exception as exc:  # noqa: BLE001
            p.append(f"executor: {type(exc).__name__}: {exc}"[:300])
    out["ready"] = not p
    return out
