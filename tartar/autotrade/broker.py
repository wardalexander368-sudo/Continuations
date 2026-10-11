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
from .execution import DryExecutor, make_executor, select_route
from .gate import LiveNotAllowed, approval_reason, kill_reason, require_live  # LiveNotAllowed is re-exported for the runner
from .safety import Pending, buy_order_id
from .perps import PERP_DEFAULTS, cloid, is_perp, make_perp_executor, perp_keys, select_perp_route
from .usd_spot import is_usd_spot, make_usd_spot_executor, sim_wallet_move
from .vault import VAULT_DEFAULTS, VaultPending, is_vault, make_vault_executor




def perp_open_cloid(intent: Intent, coin: str) -> str:
    return cloid(f"perp_open|{intent.strategy}|{intent.meta.get('key') or ''}|{coin}|{intent.side}|{intent.at:.0f}")


def perp_close_cloid(position_id: str) -> str:
    return cloid(f"perp_close|{position_id}")


def perp_twins_held(ledger, live_state: dict, route: str) -> list[dict]:
    """Every perp leg the book says the account holds on ``route``: open twins, handed-over kept legs, and
    unresolved perp orphans."""
    out = [p.meta["live"] for p in (ledger.positions if ledger else []) if p.meta.get("live") and is_perp(p.meta["live"])
           and p.meta["live"].get("route") == route]
    out += [h for h in live_state.get("perp_handover", []) if h.get("route") == route]
    out += [o for o in live_state.get("orphans", []) if o.get("venue") == "hyperliquid" and o.get("route") == route
            and o.get("sz") and not o.get("resolved")]
    return out


def seed_usd_twins(path: Path, ledger) -> None:
    """Once: put the dry USD-spot twins already in the book (the hedged basket's JLP) into the simulated wallet,
    which only started tracking them on 2026-10-10, so the first reconcile doesn't read them as missing."""
    import json

    w = json.loads(path.read_text()) if path.exists() else None
    if w is not None and w.get("usd_seeded"):
        return
    for p in ledger.positions:
        t = p.meta.get("live") or {}
        if is_usd_spot(t) and t.get("route") == "dry" and t.get("token_raw"):
            sim_wallet_move(path, t["mint"], int(t["token_raw"]))
    w = json.loads(path.read_text()) if path.exists() else {"sol": LIVE_DEFAULTS["dry_balance_sol"], "tokens": {}}
    w["usd_seeded"] = True
    path.write_text(json.dumps(w, indent=1, sort_keys=True))


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


BASKET_MIN_FILL = 0.95  # a basket hedge filling less than this share of its size unwinds the basket

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
                 perp_executor=None, usd_executor=None, vault_executor=None):
        env = os.environ if env is None else env
        mode = config.get("mode")
        self.cfg = {**LIVE_DEFAULTS, **config.get("live", {})}
        if mode == "dry_live":
            self.cfg["route"] = "dry"
        elif mode == "live":
            why = approval_reason(config, env)
            if why:
                raise LiveNotAllowed(why)
        else:
            raise LiveNotAllowed(f"mode {mode!r} has no live twins")
        route = select_route(self.cfg, env)
        self.perp_route = select_perp_route(mode, env, config)
        self.us_blocked: list[str] = []
        if mode == "live" and config.get("us_only", True):  # AJ 2026-10-11: only venues a US person may use
            testnet = (self.cfg.get("perps") or {}).get("network") == "testnet"  # CI's no-money test stays
            if self.perp_route is not None and not testnet:  # Hyperliquid (perps, HLP vault): its terms bar US persons
                self.perp_route = None
                self.us_blocked.append("Hyperliquid")
            if route == "jupiter":  # Jupiter's terms: it does not interact with US wallets
                route = "lightning" if env.get("PUMPPORTAL_API_KEY") else None
                self.us_blocked.append("Jupiter")
        if route is None and self.perp_route is None:
            raise LiveNotAllowed("no route key: set TARTAR_WALLET_KEY (Jupiter) or PUMPPORTAL_API_KEY (Lightning), "
                                 "or HYPERLIQUID_AGENT_KEY and HYPERLIQUID_ACCOUNT (perps)")
        self.config = config
        self.route = route
        self.mode = "dry_live" if mode == "dry_live" else "live"
        self.executor = executor or (make_executor(route, self.cfg, env) if route else None)
        self.ledger, self.root, self.env, self.entries = ledger, Path(root) if root else None, env, entries
        self.pending = Pending(self.root)
        if route in ("jupiter", "lightning") and hasattr(self.executor, "guard"):  # re-checked right before every send
            keys = ("TARTAR_WALLET_KEY",) if route == "jupiter" else ("PUMPPORTAL_API_KEY",)
            self.executor.guard = lambda: require_live(config, env, keys=keys, root=self.root)
        if isinstance(self.executor, DryExecutor) and self.root:
            seed: dict[str, int] = {}
            for p in (ledger.positions if ledger else []):
                t = p.meta.get("live") or {}
                if t.get("route") == "dry" and "sol_in" in t and "mint" in t:
                    seed[t["mint"]] = seed.get(t["mint"], 0) + int(t["token_raw"])
            self.executor.attach(self.root / "dry_wallet.json", seed)
        self.usd_route = "dry" if mode == "dry_live" else ("jupiter" if route == "jupiter" else None)
        if mode == "dry_live" and self.root and ledger is not None:
            seed_usd_twins(self.root / "dry_wallet.json", ledger)
        self.now = time.time() if now is None else now
        self._sol_usd: float | None = None
        self.pcfg = {**PERP_DEFAULTS, **self.cfg.get("perps", {})}
        self._perp_exec = perp_executor
        self._usd_exec = usd_executor
        self.vcfg = {**VAULT_DEFAULTS, **self.cfg.get("vault", {})}
        self._vault_exec = vault_executor
        self.vault_pending = VaultPending(self.root)

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
        why = kill_reason(self.root, self.env)
        if why:
            return why
        st = self.live_state()
        return st["halted"] or self.ledger.state.get("halted") or self.strat_state(strategy)["halted"]

    def _sol_usd_or_none(self) -> float | None:
        try:
            return self.sol_usd()
        except Exception:  # noqa: BLE001
            return None

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
        if self.executor is None:
            return "no Solana route key (TARTAR_WALLET_KEY or PUMPPORTAL_API_KEY)", 0.0
        if intent.side != 1:
            return "short side has no spot route", 0.0
        age = self.now - intent.at
        if age > self.cfg["max_signal_age_s"]:
            return f"signal {age:.0f} s old > {self.cfg['max_signal_age_s']:.0f} s", 0.0
        twins = [p.meta["live"] for p in positions if p.meta.get("live") and not is_perp(p.meta["live"]) and not is_usd_spot(p.meta["live"]) and not is_vault(p.meta["live"])]
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
        if intent.meta.get("venue") == "coinbase":  # US spot: paper until a Coinbase route exists (handoff/autotrade.md)
            pos, row = PaperBroker.open(self, intent)
            pos.mode = row["mode"] = "paper"
            row["live"] = {"skipped": "no Coinbase route yet (paper only)"}
            return pos, row
        if is_vault(intent.meta):
            return self._open_vault(intent, positions or [])
        if is_perp(intent.meta):
            return self._open_perp(intent, positions or [])
        if is_usd_spot(intent.meta):
            return self._open_usd(intent, positions or [])
        pos, row = super().open(intent)
        pos.mode = row["mode"] = "paper"  # until a twin is bought
        oid = buy_order_id(intent)
        claim = self.live_state().get("unclaimed", {}).pop(oid, None)
        if claim:  # a run that died bought this entry's tokens already: adopt them, don't buy again
            pos.meta["live"] = {"mint": claim["mint"], "route": self.route, "sol_in": claim["sol_in"], "token_raw": claim["token_raw"],
                                "sol_usd_in": claim.get("sol_usd_in") or self._sol_usd_or_none(), "paper_price_in": intent.price,
                                "bought_at": claim["at"],
                                "rent_sol": claim.get("rent_sol", 0.0), "signature": claim.get("signature"),
                                "dry": self.route == "dry", "adopted": oid}
            pos.mode = row["mode"] = self.mode
            row["live"] = {"adopted": oid, "token_raw": claim["token_raw"]}
            self.log({"event": "buy_adopted", "strategy": intent.strategy, "position": pos.id, "order_id": oid, "claim": claim})
            return pos, row
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
        self.pending.add(oid, {"leg": "buy", "strategy": intent.strategy, "position": pos.id, "mint": mint, "sol": size,
                               "at": self.now, "route": self.route})
        f = self.executor.buy(mint, size)
        rec = {"event": "buy", "strategy": intent.strategy, "position": pos.id, "order_id": oid, "asset": intent.asset, "fill": f.to_dict(),
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
            if f.unknown:  # it may have filled: keep the signature for a hand check and stop entering blind
                self.live_state()["orphans"].append({"position": pos.id, "strategy": intent.strategy, "mint": mint, "route": self.route,
                                                     "leg": "buy", "sol_in": size, "signature": f.signature, "unknown": True,
                                                     "error": f.error, "at": self.now})
                self.halt(intent.strategy, f"live buy outcome unknown ({f.signature}); check it, then resume-live")
        self.log(rec)
        self.pending.done(oid)
        return pos, row

    # exit
    def close(self, pos: Position, intent: Intent) -> tuple[Trade, dict]:
        twin = pos.meta.get("live")
        if twin and is_vault(twin):
            return self._close_vault(pos, intent)
        if twin and is_perp(twin):
            return self._close_perp(pos, intent)
        if twin and is_usd_spot(twin):
            return self._close_usd(pos, intent)
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
        if twin.get("sold_unrecorded"):  # reconcile found the tokens gone after a run died mid-sell
            row["live"] = {"sold_unrecorded": twin["sold_unrecorded"]}
            trade.meta["live"] = {"sold_unrecorded": True, "sol_in": twin["sol_in"], "route": twin["route"]}
            self.log({"event": "sell_unrecorded", "strategy": pos.strategy, "position": pos.id, "twin": twin})
            return trade, row
        sid = f"sell|{pos.id}"
        self.pending.add(sid, {"leg": "sell", "strategy": pos.strategy, "position": pos.id, "mint": twin["mint"],
                               "token_raw": twin["token_raw"], "at": self.now, "route": self.route})
        f = self.executor.sell(twin["mint"], twin["token_raw"])
        if not f.ok:
            self.pending.done(sid)
            self.live_state()["orphans"].append({"position": pos.id, "strategy": pos.strategy, **twin, "error": f.error, "at": self.now,
                                                 **({"sell_signature": f.signature, "unknown": True} if f.unknown else {})})
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
        self.pending.done(sid)
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
            self._perp_exec = make_perp_executor(self.perp_route, self.pcfg, self.env, self.config, self.root)
            if self.root and callable(getattr(self._perp_exec, "attach", None)):  # the dry route's simulated account
                seed: dict[str, float] = {}
                for t in perp_twins_held(self.ledger, self.live_state(), "dry"):
                    seed[t["coin"]] = seed.get(t["coin"], 0.0) + t["side"] * t["sz"]
                self._perp_exec.attach(self.root / "dry_perp_account.json", seed)
        return self._perp_exec

    def perp_order(self, leg: str, oid: str, coin: str, side: int, strategy: str, position: str, **kw):
        """Send a perp leg idempotently: an earlier order with this client order id is adopted, not repeated."""
        ex = self.perp_exec()
        find = getattr(ex, "find", None)
        if callable(find):
            try:
                prior = find(oid)
            except Exception as exc:  # noqa: BLE001 - can't tell whether it went out: don't send blind
                from .perps import PerpFill

                return PerpFill(self.perp_route, leg, coin, side, False, error=f"order lookup failed: {exc}"[:300]), False
            if prior is not None and prior.ok:
                self.live_state().get("perp_inflight", {}).pop(oid, None)
                prior.leg = leg
                prior.extra = {**prior.extra, "adopted": oid}
                return prior, True
        self.pending.add(oid, {"leg": f"perp_{leg}", "venue": "hyperliquid", "strategy": strategy, "position": position, "coin": coin,
                               "side": side, "at": self.now, "route": self.perp_route, **kw})
        f = ex.open(coin, side, kw["usd"], cloid=oid) if leg == "open" else ex.close(coin, side, kw["sz"], cloid=oid)
        return f, False

    def perp_entry_block(self, intent: Intent, positions: list[Position]) -> tuple[str | None, float]:
        """(why not, USD notional)."""
        if intent.meta.get("shadow"):
            return "shadow variant", 0.0
        if intent.meta.get("twin_block"):
            return intent.meta["twin_block"], 0.0
        failed = getattr(self, "_book_failed", {}).get(intent.strategy)
        if failed and self.is_book(intent.meta) and failed[0] == intent.meta.get("week"):
            return f"week {failed[0]} stays on paper: an earlier leg failed ({failed[1]})", 0.0
        if self.perp_route is None:
            return "no perp route: mode live needs the approval plus HYPERLIQUID_AGENT_KEY and HYPERLIQUID_ACCOUNT (perps.py)", 0.0
        basket = intent.meta.get("basket")
        if basket:  # a hedge without the asset it hedges is a bet: the basket's spot leg must hold a twin first
            if self.usd_route is None:
                return "basket leg: the basket's USD spot leg has no live route (needs TARTAR_WALLET_KEY), so its hedges stay on paper", 0.0
            if (self.live_state().get("basket_broken") or {}).get(basket):
                return f"basket {basket} stopped: {self.live_state()['basket_broken'][basket]}", 0.0
            if not any(p.meta.get("live") and is_usd_spot(p.meta["live"]) and p.meta["live"].get("basket") == basket for p in positions):
                return f"basket leg: basket {basket}'s spot leg has no live twin, so its hedge stays on paper", 0.0
        if not (self.entries or (self.perp_route == "dry" and self.pcfg["dry_all"])):
            return "strategy not promoted", 0.0
        why = self.kill_reason(intent.strategy) or self.live_state().get("perps_halted")
        if why:
            return why, 0.0
        age = self.now - intent.at
        if age > self.pcfg["max_signal_age_s"]:
            return f"signal {age:.0f} s old > {self.pcfg['max_signal_age_s']:.0f} s", 0.0
        return self.usd_size(intent, positions, self.pcfg["min_leg_usd"])

    # weekly perps books: all-or-nothing, balanced, sized from the paper legs
    @staticmethod
    def is_book(meta: dict) -> bool:
        return is_perp(meta) and "week" in meta and "leg_usd" in meta and not meta.get("basket")

    def plan_book(self, strategy: str, intents: list[Intent], positions: list[Position]) -> str | None:
        """Before a strategy's intents run: size this run's book twins (paper notional x book_fraction x the
        strategy's size_factor) and check the week opens whole: every new twin >= the venue minimum, longs and
        shorts within book_balance_tol, inside book_budget_usd. Kept legs roll their twin. If the week can't
        open whole, every leg's ``meta.twin_block`` says why and none gets a twin. Returns the reason or None."""
        opens = [i for i in intents if i.kind == "open" and self.is_book(i.meta) and not i.meta.get("shadow")]
        if not opens or self.perp_route is None:
            return None
        kept_ids = {i.position_id for i in intents if i.kind == "close" and i.meta.get("kept")}
        mine = {(p.meta.get("coin", p.asset), p.side): p for p in positions
                if p.strategy == strategy and p.id in kept_ids and p.meta.get("live")}
        week = opens[0].meta["week"]
        factor = self.ledger.strategy(strategy).get("size_factor", 1.0) if self.ledger else 1.0
        sides = {1: 0.0, -1: 0.0}
        why = None
        for i in opens:
            held = mine.get((i.meta.get("coin", i.asset), i.side))
            if held:
                usd = float(held.meta["live"]["notional_in"])
            else:
                usd = round(i.notional_usd * factor * self.pcfg["book_fraction"], 2)
                if usd < self.pcfg["min_leg_usd"] and not why:
                    why = f"{i.asset} twin ${usd:.2f} < Hyperliquid's ${self.pcfg['min_leg_usd']:.0f} minimum"
            i.meta["twin_usd"] = usd
            sides[i.side] += usd
        others = sum(float(p.meta["live"]["notional_in"]) for p in positions
                     if p.strategy != strategy and p.meta.get("live") and self.is_book(p.meta) and p.meta["week"] >= week)
        total = sides[1] + sides[-1]
        big = max(sides.values())
        if not why and abs(sides[1] - sides[-1]) > self.pcfg["book_balance_tol"] * big:
            why = f"unbalanced: longs ${sides[1]:.2f} vs shorts ${sides[-1]:.2f}"
        if not why and total + others > self.pcfg["book_budget_usd"]:
            why = f"book ${total:.2f} + other books ${others:.2f} > budget ${self.pcfg['book_budget_usd']:.0f}"
        if why:
            why = f"week {week} stays on paper (all or nothing): {why}"
            for i in opens:
                i.meta["twin_block"] = why
            self.log({"event": "book_skip", "venue": "hyperliquid", "strategy": strategy, "week": week, "reason": why, "at": self.now})
        return why

    def finish_book(self, strategy: str, positions: list[Position]) -> None:
        """After a strategy's intents ran: if a leg of this week's book failed, close the week's other twins
        (the paper legs stay), so no half book is left on the venue."""
        failed = getattr(self, "_book_failed", {}).pop(strategy, None)
        if not failed:
            return
        week, why = failed
        for p in positions:
            t = p.meta.get("live")
            if p.strategy != strategy or not t or not self.is_book(p.meta) or p.meta.get("week") != week:
                continue
            oid = cloid(f"book_unwind|{p.id}")
            f, _ = self.perp_order("close", oid, t["coin"], t["side"], p.strategy, p.id, sz=t["sz"])
            self.pending.done(oid)
            self.log({"event": "book_unwind", "strategy": strategy, "position": p.id, "week": week, "reason": why, "fill": f.to_dict()})
            if f.ok and f.sz >= t["sz"] * (1 - 1e-9):
                del p.meta["live"]
                p.mode = "paper"
            else:
                err = f.error or f"closed {f.sz:g} of {t['sz']:g}"
                self.live_state()["orphans"].append({"position": p.id, "strategy": strategy, **t, "at": self.now,
                                                     "error": f"book unwind: {err}"})

    def usd_size(self, intent: Intent, positions: list[Position], min_usd: float) -> tuple[str | None, float]:
        """USD twin size. Basket legs (``meta.basket``) take ``meta.twin_usd`` so the legs stay in proportion, under
        ``basket_budget_usd``; other perp twins take ``max_leg_usd`` under ``budget_usd``."""
        if self.is_book(intent.meta) and "twin_usd" in intent.meta:  # sized and budgeted by plan_book
            return None, float(intent.meta["twin_usd"])
        basket = intent.meta.get("basket")
        usd_twins = [p.meta["live"] for p in positions if p.meta.get("live") and (is_perp(p.meta["live"]) or is_usd_spot(p.meta["live"]))]
        usd_twins += self.live_state().get("perp_handover", [])
        at_risk = sum(t["notional_in"] for t in usd_twins if bool(t.get("basket")) == bool(basket))
        budget = self.pcfg["basket_budget_usd"] if basket else self.pcfg["budget_usd"]
        want = float(intent.meta.get("twin_usd", self.pcfg["max_leg_usd"])) if basket else self.pcfg["max_leg_usd"]
        size = min(want, budget - at_risk)
        size *= self.ledger.strategy(intent.strategy).get("size_factor", 1.0) if self.ledger else 1.0
        if size < min_usd or (basket and size < want - 1e-9):
            return (f"size ${size:.2f} < {'wanted $%.2f' % want if basket else 'min $%.0f' % min_usd} "
                    f"(budget ${budget:.0f}, at risk ${at_risk:.2f})"), 0.0
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
        oid = perp_open_cloid(intent, coin)
        f, adopted = self.perp_order("open", oid, coin, side, intent.strategy, pos.id, usd=usd)
        rec = {"event": "perp_open_adopted" if adopted else "perp_open", "strategy": intent.strategy, "position": pos.id, "coin": coin,
               "cloid": oid, "fill": f.to_dict(),
               "paper_price_usd": intent.price, "paper_at": intent.at,
               "paper_side_cost_pct": 100 * intent.cost.side_cost(intent.notional_usd) / intent.notional_usd}
        if f.ok:
            rec["vs_paper_price_bps"] = 1e4 * side * (f.px / intent.price - 1)
            pos.meta["live"] = {"venue": "hyperliquid", "coin": coin, "side": side, "route": self.perp_route, "sz": f.sz,
                                "px_in": f.px, "notional_in": f.notional_usd, "fee_in": f.fee_usd, "opened_at": self.now,
                                "paper_price_in": intent.price, "dry": f.dry, "basket": intent.meta.get("basket")}
            pos.mode = row["mode"] = self.mode
            row["live"] = {"venue": "hyperliquid", "sz": f.sz, "px_in": f.px, "notional_in": f.notional_usd}
        else:
            row["live"] = {"failed": f.error}
            if self.is_book(intent.meta):
                if not hasattr(self, "_book_failed"):
                    self._book_failed = {}
                self._book_failed.setdefault(intent.strategy, (intent.meta["week"], f"{coin}: {f.error}"[:200]))
            self.ledger.journal({"event": "live_error", "strategy": intent.strategy, "position": pos.id, "leg": "perp_open",
                                 "error": f.error, "at": self.now})
        self.log(rec)
        self.pending.done(oid)
        basket = intent.meta.get("basket")
        if basket and (not f.ok or f.notional_usd < BASKET_MIN_FILL * usd):
            why = f"hedge {coin} {'failed: ' + str(f.error) if not f.ok else f'filled ${f.notional_usd:.2f} of ${usd:.2f}'}"
            self.unwind_basket(basket, intent.strategy, list(positions) + [pos], why)
            row["live"] = {**row.get("live", {}), "basket_unwound": why}
        return pos, row

    def unwind_basket(self, basket: str, strategy: str, positions: list[Position], why: str) -> None:
        """A basket leg failed or filled short: close every live twin of the basket (the paper legs stay), stop
        the basket's live entries, and leave nothing unhedged. A twin that can't be closed becomes an orphan."""
        st = self.live_state()
        st.setdefault("basket_broken", {})[basket] = why
        for p in positions:
            t = p.meta.get("live")
            if not t or t.get("basket") != basket:
                continue
            if is_usd_spot(t):
                f = self.usd_exec().sell(t["mint"], t["token_raw"])
                ok, err, fill = f.ok, f.error, f.to_dict()
            elif is_perp(t):
                f, _ = self.perp_order("close", cloid(f"basket_unwind|{p.id}"), t["coin"], t["side"], p.strategy, p.id, sz=t["sz"])
                self.pending.done(cloid(f"basket_unwind|{p.id}"))
                ok, err, fill = f.ok, f.error, f.to_dict()
                if ok and f.sz < t["sz"] * (1 - 1e-9):  # a partial close: the rest stays open on the venue, as an orphan
                    rest = {**t, "sz": t["sz"] - f.sz, "notional_in": t["notional_in"] * (1 - f.sz / t["sz"])}
                    st["orphans"].append({"position": p.id, "strategy": p.strategy, **rest, "at": self.now,
                                          "error": f"basket unwind closed {f.sz:g} of {t['sz']:g}"})
            else:
                continue
            self.log({"event": "basket_unwind", "strategy": p.strategy, "position": p.id, "basket": basket, "reason": why, "fill": fill})
            if ok:
                del p.meta["live"]
                p.mode = "paper"
            else:
                st["orphans"].append({"position": p.id, "strategy": p.strategy, **t, "error": f"basket unwind failed: {err}", "at": self.now})
        self.halt(strategy, f"basket {basket} unwound: {why}")

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
            oid = perp_close_cloid(pos.id)
            f, adopted = self.perp_order("close", oid, coin, side, pos.strategy, pos.id, sz=twin["sz"])
            if not f.ok:
                self.pending.done(oid)
                self.live_state()["orphans"].append({"position": pos.id, "strategy": pos.strategy, **twin, "error": f.error, "at": self.now})
                self.ledger.journal({"event": "live_error", "strategy": pos.strategy, "position": pos.id, "leg": "perp_close",
                                     "error": f.error, "at": self.now})
                self.log({"event": "perp_close_failed", "strategy": pos.strategy, "position": pos.id, "fill": f.to_dict()})
                self.halt(pos.strategy, f"perp close failed ({f.error}); twin kept in live.orphans")
                row["live"] = {"failed": f.error}
                return trade, row
            px_out, fee_out, event = f.px, f.fee_usd, "perp_close_adopted" if adopted else "perp_close"
            self.pending.done(oid)
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
        if not self.is_book(pos.meta):  # weekly books realize a week at once; their stops are perp_risk's weekly and drawdown limits
            st["daily_usd_perps"][day] = st["daily_usd_perps"].get(day, 0.0) + net
        if st["daily_usd_perps"].get(day, 0.0) < -self.pcfg["daily_loss_cap_usd"] and not st["halted"]:
            self.halt("live", f"perp twins' daily loss ${st['daily_usd_perps'][day]:.2f} < -${self.pcfg['daily_loss_cap_usd']:.2f}")
        srec = self.strat_state(pos.strategy)
        if not kept and ret < -self.pcfg["max_trade_loss_pct"] and not srec["halted"]:
            self.halt(pos.strategy, f"perp twin round trip {100 * ret:+.1f}% < -{100 * self.pcfg['max_trade_loss_pct']:.0f}%")
        srec["divergence_run"] = srec["divergence_run"] + 1 if cmp["live_minus_paper"] < -self.pcfg["max_divergence_pct"] else 0
        if srec["divergence_run"] >= self.pcfg["divergence_streak"] and not srec["halted"]:
            self.halt(pos.strategy, f"perp twins worse than paper by > {100 * self.pcfg['max_divergence_pct']:.0f} points "
                                    f"{srec['divergence_run']} closes in a row")
        return trade, row


    # USD spot (Jupiter USDC quotes; usd_spot.py)
    def usd_exec(self):
        if self._usd_exec is None:
            self._usd_exec = make_usd_spot_executor(self.usd_route)
            if self.usd_route == "dry" and self.root and callable(getattr(self._usd_exec, "attach", None)):
                self._usd_exec.attach(self.root / "dry_wallet.json")
            if self.usd_route == "jupiter" and hasattr(self._usd_exec, "guard"):  # re-checked right before every send
                self._usd_exec.guard = lambda: require_live(self.config, self.env, keys=("TARTAR_WALLET_KEY",), root=self.root)
        return self._usd_exec

    def _open_usd(self, intent: Intent, positions: list[Position]) -> tuple[Position, dict]:
        pos, row = PaperBroker.open(self, intent)
        pos.mode = row["mode"] = "paper"
        mint, basket = intent.meta["mint"], intent.meta.get("basket")
        oid = buy_order_id(intent)
        claim = self.live_state().get("unclaimed", {}).pop(oid, None)
        if claim:  # a run that died bought this leg's tokens already: adopt them, don't buy again
            pos.meta["live"] = {"venue": "jupiter_usd", "mint": claim["mint"], "route": self.usd_route, "usd_in": claim.get("usd_in"),
                                "notional_in": claim.get("usd_in") or float(intent.meta.get("twin_usd", intent.notional_usd)),
                                "token_raw": claim["token_raw"], "opened_at": claim["at"], "paper_price_in": intent.price,
                                "dry": self.usd_route == "dry", "basket": basket, "adopted": oid}
            pos.mode = row["mode"] = self.mode
            row["live"] = {"adopted": oid, "token_raw": claim["token_raw"]}
            self.log({"event": "usd_buy_adopted", "strategy": intent.strategy, "position": pos.id, "order_id": oid, "claim": claim})
            return pos, row
        why = None
        if intent.meta.get("shadow"):
            why = "shadow variant"
        elif self.usd_route is None:
            why = "no USD spot route: mode live needs TARTAR_WALLET_KEY (Jupiter)"
        elif basket and self.perp_route is None:
            why = "basket leg: no perp route for its hedges, so the spot leg stays on paper (unhedged it would be a bet)"
        elif basket and (self.live_state().get("basket_broken") or {}).get(basket):
            why = f"basket {basket} stopped: {self.live_state()['basket_broken'][basket]}"
        elif not (self.entries or (self.usd_route == "dry" and self.pcfg["dry_all"])):
            why = "strategy not promoted"
        elif intent.side != 1:
            why = "short side has no spot route"
        else:
            why = self.kill_reason(intent.strategy)
            if not why and self.now - intent.at > self.pcfg["max_signal_age_s"]:
                why = f"signal {self.now - intent.at:.0f} s old > {self.pcfg['max_signal_age_s']:.0f} s"
        usd = 0.0
        if not why:
            why, usd = self.usd_size(intent, positions, 1.0)
        if why:
            row["live"] = {"skipped": why}
            if not intent.meta.get("shadow"):
                self.log({"event": "skip", "venue": "jupiter_usd", "strategy": intent.strategy, "position": pos.id, "reason": why, "at": intent.at})
            return pos, row
        self.pending.add(oid, {"leg": "usd_buy", "strategy": intent.strategy, "position": pos.id, "mint": mint, "usd": usd,
                               "at": self.now, "route": self.usd_route})
        f = self.usd_exec().buy(mint, usd)
        rec = {"event": "usd_buy", "strategy": intent.strategy, "position": pos.id, "order_id": oid, "asset": intent.asset,
               "fill": f.to_dict(), "paper_price_usd": intent.price, "paper_at": intent.at}
        if f.ok:
            pos.meta["live"] = {"venue": "jupiter_usd", "mint": mint, "route": self.usd_route, "usd_in": f.usd, "notional_in": usd,
                                "token_raw": f.token_raw, "opened_at": self.now, "paper_price_in": intent.price, "dry": f.dry,
                                "basket": basket, "signature": f.signature}
            pos.mode = row["mode"] = self.mode
            row["live"] = {"venue": "jupiter_usd", "usd_in": f.usd, "token_raw": f.token_raw}
        else:
            row["live"] = {"failed": f.error}
            self.ledger.journal({"event": "live_error", "strategy": intent.strategy, "position": pos.id, "leg": "usd_buy",
                                 "error": f.error, "at": self.now})
            if f.unknown:  # it may have filled: keep the signature for a hand check and stop entering blind
                self.live_state()["orphans"].append({"position": pos.id, "strategy": intent.strategy, "mint": mint, "route": self.usd_route,
                                                     "venue": "jupiter_usd", "leg": "usd_buy", "usd_in": usd, "signature": f.signature,
                                                     "unknown": True, "error": f.error, "at": self.now})
                self.halt(intent.strategy, f"live USD buy outcome unknown ({f.signature}); check it, then resume-live")
        self.log(rec)
        self.pending.done(oid)
        return pos, row

    def _close_usd(self, pos: Position, intent: Intent) -> tuple[Trade, dict]:
        twin = pos.meta["live"]
        trade, row = PaperBroker.close(self, pos, intent)
        trade.mode = pos.mode
        if twin.get("route") != self.usd_route:
            if twin.get("dry"):
                row["live"] = {"dropped": f"dry USD twin closed while the USD route is {self.usd_route}"}
                return trade, row
            self.live_state()["orphans"].append({"position": pos.id, "strategy": pos.strategy, **twin, "at": self.now,
                                                 "error": f"bought on {twin.get('route')}, USD route now {self.usd_route}"})
            row["live"] = {"failed": "USD route changed"}
            return trade, row
        if twin.get("sold_unrecorded"):  # reconcile found the tokens gone after a run died mid-sell
            row["live"] = {"sold_unrecorded": twin["sold_unrecorded"]}
            trade.meta["live"] = {"sold_unrecorded": True, "usd_in": twin.get("usd_in"), "route": twin["route"]}
            self.log({"event": "usd_sell_unrecorded", "strategy": pos.strategy, "position": pos.id, "twin": twin})
            return trade, row
        sid = f"usd_sell|{pos.id}"
        self.pending.add(sid, {"leg": "usd_sell", "strategy": pos.strategy, "position": pos.id, "mint": twin["mint"],
                               "token_raw": twin["token_raw"], "at": self.now, "route": self.usd_route})
        f = self.usd_exec().sell(twin["mint"], twin["token_raw"])
        if not f.ok:
            self.pending.done(sid)
            self.live_state()["orphans"].append({"position": pos.id, "strategy": pos.strategy, **twin, "error": f.error, "at": self.now,
                                                 **({"sell_signature": f.signature, "unknown": True} if f.unknown else {})})
            self.ledger.journal({"event": "live_error", "strategy": pos.strategy, "position": pos.id, "leg": "usd_sell",
                                 "error": f.error, "at": self.now})
            self.halt(pos.strategy, f"USD spot sell failed ({f.error}); twin kept in live.orphans")
            row["live"] = {"failed": f.error}
            return trade, row
        net = f.usd - (twin.get("usd_in") or twin["notional_in"])
        ret = net / twin["notional_in"]
        cmp = {"venue": "jupiter_usd", "live_net_return_usd": ret, "paper_net_return": trade.net_return,
               "live_minus_paper": ret - trade.net_return, "net_usd": net, "notional_in": twin["notional_in"],
               "usd_in": twin.get("usd_in"), "usd_out": f.usd, "route": twin["route"], "dry": bool(twin.get("dry")),
               "paper_exit_price": intent.price, "hold_s": self.now - twin["opened_at"], "basket": twin.get("basket")}
        trade.meta["live"] = cmp
        row["live"] = cmp
        self.log({"event": "usd_sell", "strategy": pos.strategy, "position": pos.id, "fill": f.to_dict(), "compare": cmp})
        self.pending.done(sid)
        return trade, row

    # vault deposits (Hyperliquid HLP; vault.py). The route is the perp route: same account, same keys.
    def vault_exec(self):
        if self._vault_exec is None:
            self._vault_exec = make_vault_executor(self.perp_route, self.vcfg, self.env, self.config, self.root, self.pcfg)
        return self._vault_exec

    def _vault_twins(self, positions: list[Position], vault: str | None = None) -> list[dict]:
        out = [p.meta["live"] for p in positions if p.meta.get("live") and is_vault(p.meta["live"])]
        out += self.live_state().get("vault_handover", [])
        return [t for t in out if vault is None or t["vault"] == vault]

    def _vault_leftover(self, oid: str, vault: str, positions: list[Position], usd: float) -> tuple[str, float]:
        """A transfer a dead run left in ``vault_pending.json``: ("none" | "landed" | "unclear", USD the account holds
        beyond the book). Dry moved nothing, so it is always "none"."""
        if oid not in self.vault_pending.load():
            return "none", 0.0
        try:
            held = self.vault_exec().held(vault)
        except Exception:  # noqa: BLE001 - can't tell: don't send blind
            return "unclear", 0.0
        if held is None:
            self.vault_pending.done(oid)
            return "none", 0.0
        extra = held - sum(t["equity"] for t in self._vault_twins(positions, vault) if t.get("route") == self.perp_route)
        return ("landed" if extra >= 0.9 * usd else "none"), extra

    def vault_entry_block(self, intent: Intent, positions: list[Position]) -> tuple[str | None, float]:
        if intent.meta.get("shadow"):
            return "shadow variant", 0.0
        if self.perp_route is None:
            return "no vault route: mode live needs the approval plus HYPERLIQUID_AGENT_KEY and HYPERLIQUID_ACCOUNT", 0.0
        if not (self.entries or (self.perp_route == "dry" and self.vcfg["dry_all"])):
            return "strategy not promoted", 0.0
        why = self.kill_reason(intent.strategy)
        if why:
            return why, 0.0
        age = self.now - intent.at
        if age > self.vcfg["max_signal_age_s"]:
            return f"signal {age:.0f} s old > {self.vcfg['max_signal_age_s']:.0f} s", 0.0
        at_risk = sum(t["equity"] for t in self._vault_twins(positions))
        size = min(self.vcfg["max_usd"], intent.notional_usd, self.vcfg["budget_usd"] - at_risk)
        size *= self.ledger.strategy(intent.strategy).get("size_factor", 1.0) if self.ledger else 1.0
        if size < self.vcfg["min_usd"]:
            return f"size ${size:.2f} < min ${self.vcfg['min_usd']:.0f} (budget ${self.vcfg['budget_usd']:.0f}, at risk ${at_risk:.2f})", 0.0
        return None, round(size, 2)

    def _open_vault(self, intent: Intent, positions: list[Position]) -> tuple[Position, dict]:
        pos, row = PaperBroker.open(self, intent)
        pos.mode = row["mode"] = "paper"
        vault = intent.meta["vault"]
        hand = self.live_state().setdefault("vault_handover", [])
        held = next((h for h in hand if h["strategy"] == intent.strategy and h["vault"] == vault), None)
        if held:  # the next paper interval: the deposit carries on
            hand.remove(held)
            pos.meta["live"] = {k: v for k, v in held.items() if k != "strategy"} | {"paper_price_in": intent.price}
            pos.mode = row["mode"] = self.mode
            row["live"] = {"rolled": True, "equity": held["equity"]}
            self.log({"event": "vault_roll_in", "strategy": intent.strategy, "position": pos.id, "vault": vault, "equity": held["equity"]})
            return pos, row
        why, usd = self.vault_entry_block(intent, positions)
        if why:
            row["live"] = {"skipped": why}
            if not intent.meta.get("shadow"):
                self.log({"event": "skip", "venue": "hyperliquid_vault", "strategy": intent.strategy, "position": pos.id, "reason": why, "at": intent.at})
            return pos, row
        oid = f"vault_deposit|{buy_order_id(intent)}"
        state, extra = self._vault_leftover(oid, vault, positions, usd)
        if state == "unclear":
            row["live"] = {"skipped": "an earlier deposit for this entry may have landed and the account can't be read"}
            self.log({"event": "skip", "venue": "hyperliquid_vault", "strategy": intent.strategy, "position": pos.id, **row["live"]})
            return pos, row
        if state == "landed":  # a run that died deposited already: adopt it, don't deposit again
            ex = self.vault_exec()
            m = ex.mark(vault)
            pos.meta["live"] = {"venue": "hyperliquid_vault", "vault": vault, "route": self.perp_route, "usd_in": extra, "equity": extra,
                                "mark": m.__dict__, "opened_at": self.now, "lockup_until": None, "paper_price_in": intent.price,
                                "dry": self.perp_route == "dry", "adopted": oid}
            pos.mode = row["mode"] = self.mode
            row["live"] = {"adopted": oid, "equity": extra}
            self.log({"event": "vault_deposit_adopted", "strategy": intent.strategy, "position": pos.id, "order_id": oid, "equity": extra})
            self.vault_pending.done(oid)
            return pos, row
        self.vault_pending.add(oid, {"leg": "vault_deposit", "venue": "hyperliquid_vault", "strategy": intent.strategy, "position": pos.id,
                                     "vault": vault, "usd": usd, "at": self.now, "route": self.perp_route})
        f = self.vault_exec().deposit(vault, usd)
        rec = {"event": "vault_deposit", "strategy": intent.strategy, "position": pos.id, "order_id": oid, "fill": f.to_dict(),
               "paper_price": intent.price, "paper_at": intent.at}
        if f.ok:
            pos.meta["live"] = {"venue": "hyperliquid_vault", "vault": vault, "route": self.perp_route, "usd_in": f.usd, "equity": f.usd,
                                "mark": f.mark, "opened_at": self.now, "lockup_until": f.lockup_until, "paper_price_in": intent.price,
                                "dry": f.dry}
            pos.mode = row["mode"] = self.mode
            row["live"] = {"venue": "hyperliquid_vault", "usd_in": f.usd}
            self.vault_pending.done(oid)
        else:
            row["live"] = {"failed": f.error}
            self.ledger.journal({"event": "live_error", "strategy": intent.strategy, "position": pos.id, "leg": "vault_deposit",
                                 "error": f.error, "at": self.now})
            if f.unknown:  # it may have landed: the pending row stays, so a re-run checks the account before depositing again
                self.halt(intent.strategy, f"vault deposit outcome unknown ({f.error}); check the account, then resume-live")
            else:
                self.vault_pending.done(oid)
        self.log(rec)
        return pos, row

    def _close_vault(self, pos: Position, intent: Intent) -> tuple[Trade, dict]:
        from .vault import Mark

        twin = pos.meta["live"]
        trade, row = PaperBroker.close(self, pos, intent)
        trade.mode = pos.mode
        vault = twin["vault"]
        if twin["route"] != self.perp_route:
            if twin.get("dry"):
                row["live"] = {"dropped": f"dry vault twin closed while the route is {self.perp_route}"}
                return trade, row
            self.live_state()["orphans"].append({"position": pos.id, "strategy": pos.strategy, **twin, "at": self.now,
                                                 "error": f"deposited on {twin['route']}, route now {self.perp_route}"})
            row["live"] = {"failed": "vault route changed"}
            return trade, row
        ex = self.vault_exec()
        try:
            m1 = ex.mark(vault)
            ferr = None
        except Exception as exc:  # noqa: BLE001 - mark with the paper move instead
            m1, ferr = None, f"{type(exc).__name__}: {exc}"[:200]
        m0 = Mark(**twin["mark"]) if twin.get("mark") else None
        growth = m0.growth(m1) if (m0 and m1) else (intent.price / twin["paper_price_in"] - 1)
        equity = twin["equity"] * (1 + growth)
        kept = bool(intent.meta.get("kept"))
        if kept:
            event, out_usd = "vault_roll_out", equity
        else:
            oid = f"vault_withdraw|{pos.id}"
            if oid in self.vault_pending.load():  # a run that died while withdrawing: did it go out?
                try:
                    held = ex.held(vault)
                except Exception:  # noqa: BLE001 - can't tell: don't send blind
                    held = -1.0
                book = twin["equity"] + sum(t["equity"] for t in self.live_state().get("vault_handover", []) if t["vault"] == vault)
                if held is not None and held >= 0 and held < book - 0.5 * twin["equity"]:
                    self.vault_pending.done(oid)
                    trade.meta["live"] = row["live"] = {"withdrawn_unrecorded": True, "equity_est": equity, "route": twin["route"]}
                    self.log({"event": "vault_withdraw_unrecorded", "strategy": pos.strategy, "position": pos.id, "held": held, "twin": twin})
                    return trade, row
                if held is not None and held < 0:
                    self.live_state()["orphans"].append({"position": pos.id, "strategy": pos.strategy, **twin, "equity": equity,
                                                         "error": "earlier withdrawal unclear and the account can't be read", "at": self.now})
                    self.halt(pos.strategy, "vault withdrawal unclear; check the account, then resume-live")
                    row["live"] = {"failed": "withdrawal unclear"}
                    return trade, row
            self.vault_pending.add(oid, {"leg": "vault_withdraw", "venue": "hyperliquid_vault", "strategy": pos.strategy, "position": pos.id,
                                         "vault": vault, "usd": equity, "at": self.now, "route": self.perp_route})
            f = ex.withdraw(vault, equity, twin.get("lockup_until"))
            if not f.ok:
                if not f.unknown:
                    self.vault_pending.done(oid)
                self.live_state()["orphans"].append({"position": pos.id, "strategy": pos.strategy, **twin, "equity": equity,
                                                     "error": f.error, "unknown": f.unknown, "at": self.now})
                self.ledger.journal({"event": "live_error", "strategy": pos.strategy, "position": pos.id, "leg": "vault_withdraw",
                                     "error": f.error, "at": self.now})
                self.log({"event": "vault_withdraw_failed", "strategy": pos.strategy, "position": pos.id, "fill": f.to_dict()})
                self.halt(pos.strategy, f"vault withdrawal failed ({f.error}); twin kept in live.orphans")
                row["live"] = {"failed": f.error}
                return trade, row
            self.vault_pending.done(oid)
            event, out_usd = "vault_withdraw", f.usd
        ret = out_usd / twin["equity"] - 1
        cmp = {"venue": "hyperliquid_vault", "live_net_return_usd": ret, "paper_net_return": trade.net_return,
               "live_minus_paper": ret - trade.net_return, "net_usd": out_usd - twin["equity"], "equity_in": twin["equity"],
               "equity_out": out_usd, "usd_in": twin["usd_in"], "route": twin["route"], "dry": bool(twin.get("dry")), "rolled": kept,
               "mark_error": ferr, "paper_exit_price": intent.price, "hold_s": self.now - twin["opened_at"]}
        trade.meta["live"] = cmp
        row["live"] = cmp
        self.log({"event": event, "strategy": pos.strategy, "position": pos.id, "vault": vault, "compare": cmp})
        if kept:
            self.live_state().setdefault("vault_handover", []).append(
                {**{k: v for k, v in twin.items() if k != "paper_price_in"}, "strategy": pos.strategy, "equity": equity,
                 "mark": m1.__dict__ if m1 else twin.get("mark")})
        srec = self.strat_state(pos.strategy)
        if ret < -self.vcfg["max_trade_loss_pct"] and not srec["halted"]:
            self.halt(pos.strategy, f"vault twin interval {100 * ret:+.1f}% < -{100 * self.vcfg['max_trade_loss_pct']:.0f}%")
        srec["divergence_run"] = srec["divergence_run"] + 1 if cmp["live_minus_paper"] < -self.vcfg["max_divergence_pct"] else 0
        if srec["divergence_run"] >= self.vcfg["divergence_streak"] and not srec["halted"]:
            self.halt(pos.strategy, f"vault twin worse than paper by > {100 * self.vcfg['max_divergence_pct']:.0f} points "
                                    f"{srec['divergence_run']} intervals in a row")
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
           "perps": {"route": select_perp_route(mode, env, config), "keys": perp_keys(env),
                     "limits": {**PERP_DEFAULTS, **cfg.get("perps", {})},
                     "note": "live: IOC orders via hl_exchange.py, only past the gate (gate.py)"},
           "vault": {"route": select_perp_route(mode, env, config), "limits": {**VAULT_DEFAULTS, **cfg.get("vault", {})},
                     "note": "HLP deposits: vaultTransfer via vault.py with the perp keys, only past the gate"}}
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
