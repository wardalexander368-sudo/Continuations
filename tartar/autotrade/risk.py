"""Risk limits and the kill switch.

* Kill switch: the file ``autotrade/HALT`` (any content is the reason) stops every new entry. Exits still run so positions close on schedule; with
  ``flatten_on_halt`` the agent closes everything at the latest marks instead.
* Caps: max notional per position, max open positions per strategy and in total, max gross exposure. A weekly
  long-short book leg (meta ``week`` and ``leg_usd``) is capped by its side's budget ``leg_usd`` instead of
  ``max_position_usd``: a small universe (Coinbase's 23 US-perp coins) makes 3-coin quintiles, and refusing one
  leg would leave a half book the registered rule never holds.
* Shadow variants (research copies of a rule) count only against their own per-strategy cap.
* Daily loss cap, per strategy: a strategy whose realized + unrealized PnL of the UTC day is below
  ``-daily_loss_cap_usd`` takes no new entries for the rest of that UTC day (its exits still run); the
  stop clears by itself at the next UTC day, logged as a change. One strategy's bad day (the memecoin dip
  rule, say) no longer stops the others (audit 2026-10-10, 1b).
* Errors: a strategy whose step raises ``max_consecutive_errors`` times in a row is halted
  (status "halted"). Every ``error_retry_hours`` (default 6) the runner tries it once more; a clean step
  resumes it (logged), since steps book from candles retroactively and an outage loses no trades.
  ``resume`` still works by hand.
"""

from __future__ import annotations

import time
from pathlib import Path

from .core import Intent, Position

DEFAULTS = {
    "max_position_usd": 250.0,
    "max_open_per_strategy": 20,
    "max_open_total": 60,
    "max_gross_usd": 10_000.0,
    "daily_loss_cap_usd": 500.0,
    "max_consecutive_errors": 3,
    "error_retry_hours": 6.0,
    "flatten_on_halt": False,
}


class Risk:
    def __init__(self, config: dict, root: Path, ledger):
        self.limits = {**DEFAULTS, **config.get("risk", {})}
        self.now: float | None = None  # the run's clock (set by the runner)
        self.root = Path(root)
        self.ledger = ledger
        from .perp_risk import BOOKS, book_names

        self.book_of = {n: b for b in BOOKS for n in book_names(config, b)}  # perps book strategies -> book

    def kill_reason(self) -> str | None:
        f = self.root / "HALT"
        if f.exists():
            return "kill switch: " + (f.read_text().strip() or "HALT file present")
        return self.ledger.state.get("halted")

    def day_pnl(self, now: float, positions: list[Position]) -> float:
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        realized = self.ledger.state["daily"].get(day, 0.0)
        return realized + sum(p.unrealized() for p in positions if not p.meta.get("shadow"))

    def strategy_day_pnl(self, name: str, now: float, positions: list[Position]) -> float:
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        realized = self.ledger.state.get("daily_by_strategy", {}).get(day, {}).get(name, 0.0)
        return realized + sum(p.unrealized() for p in positions if p.strategy == name and not p.meta.get("shadow"))

    def book_for(self, intent: Intent) -> str:
        """The perps book an entry belongs to: registered members by config; shadow variants and search candidates
        by their legs' venue, so they pause with their book too."""
        from .perp_risk import BOOK_VENUE

        if intent.strategy in self.book_of:
            return self.book_of[intent.strategy]
        if "week" in intent.meta and "leg_usd" in intent.meta:
            return next((b for b, v in BOOK_VENUE.items() if v == intent.meta.get("venue")), "")
        return ""

    def daily_block(self, name: str, now: float) -> str | None:
        st = self.ledger.state.get("strategies", {}).get(name, {}).get("daily_stop")
        if st and st["day"] == time.strftime("%Y-%m-%d", time.gmtime(now)):
            return st["reason"]
        return None

    def check_daily(self, now: float, positions: list[Position]) -> list[str]:
        """Per-strategy daily stops: set today's, clear earlier days'. Returns the reasons set now."""
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        out = []
        names = set(self.ledger.state.get("strategies", {})) | {p.strategy for p in positions}
        for name in sorted(names):
            rec = self.ledger.strategy(name)
            st = rec.get("daily_stop")
            if st and st["day"] != day:
                del rec["daily_stop"]
                self.ledger.change({"t": now, "kind": "resume", "scope": name, "reason": f"daily loss stop of {st['day']} cleared (new UTC day)"})
            if "daily_stop" in rec:
                continue
            pnl = self.strategy_day_pnl(name, now, positions)
            if pnl < -self.limits["daily_loss_cap_usd"]:
                reason = f"daily loss cap: {name} {pnl:.2f} USD < -{self.limits['daily_loss_cap_usd']:.2f} today; entries resume next UTC day"
                rec["daily_stop"] = {"day": day, "reason": reason}
                self.ledger.change({"t": now, "kind": "halt", "scope": name, "reason": reason})
                out.append(reason)
        if (self.ledger.state.get("halted") or "").startswith("daily loss cap"):  # the old agent-wide stop: superseded
            self.ledger.state["halted"] = None
            self.ledger.change({"t": now, "kind": "resume", "scope": "agent", "reason": "agent-wide daily loss stop replaced by per-strategy stops"})
        return out

    def allow_open(self, intent: Intent, positions: list[Position]) -> str | None:
        """None if allowed, else why not."""
        why = self.kill_reason() or self.daily_block(intent.strategy, time.time() if self.now is None else self.now) \
            or (self.ledger.state.get("book_halts") or {}).get(self.book_for(intent))
        if why:
            return why
        lim = self.limits
        if intent.notional_usd <= 0:
            return "zero size"
        cap = lim["max_position_usd"]
        if "week" in intent.meta and "leg_usd" in intent.meta:  # a book leg: bounded by its side's budget
            cap = max(cap, float(intent.meta["leg_usd"]) * (1 + 1e-9))
        if intent.notional_usd > cap:
            return f"position {intent.notional_usd:.2f} > max {cap:.2f} USD"
        mine = [p for p in positions if p.strategy == intent.strategy]
        if len(mine) >= lim["max_open_per_strategy"]:
            return f"{len(mine)} open >= max {lim['max_open_per_strategy']} for {intent.strategy}"
        if intent.meta.get("shadow"):
            return None  # shadow variants are research: outside the agent-wide caps
        positions = [p for p in positions if not p.meta.get("shadow")]
        if len(positions) >= lim["max_open_total"]:
            return f"{len(positions)} open >= max {lim['max_open_total']} in total"
        gross = sum(p.notional_usd for p in positions)
        if gross + intent.notional_usd > lim["max_gross_usd"]:
            return f"gross {gross + intent.notional_usd:.2f} > max {lim['max_gross_usd']:.2f} USD"
        return None

    def record_error(self, name: str, now: float, err: str) -> bool:
        """Count a strategy error; halt the strategy at the limit. Returns True if it was halted now."""
        rec = self.ledger.strategy(name)
        rec["errors"] += 1
        rec["last_error"] = err[:500]
        if rec["errors"] >= self.limits["max_consecutive_errors"] and rec["status"] != "halted":
            rec["status_before_halt"] = rec["status"]
            rec["status"] = "halted"
            rec["halted_by_errors_at"] = now
            self.ledger.change({"t": now, "kind": "halt", "scope": name, "reason": f"{rec['errors']} consecutive errors: {err[:300]}"})
            return True
        return False

    def retry_due(self, name: str, now: float) -> bool:
        """A strategy halted by errors gets one more try every ``error_retry_hours``."""
        rec = self.ledger.strategy(name)
        t = rec.get("halted_by_errors_at")
        if rec["status"] != "halted" or t is None:
            return False
        if now - float(rec.get("last_retry_at", t)) < 3600 * float(self.limits.get("error_retry_hours", 6.0)):
            return False
        rec["last_retry_at"] = now
        return True

    def record_ok(self, name: str, now: float | None = None) -> None:
        rec = self.ledger.strategy(name)
        rec["errors"] = 0
        if rec["status"] == "halted" and rec.get("halted_by_errors_at") is not None:
            rec["status"] = rec.pop("status_before_halt", "paper")
            for k in ("halted_by_errors_at", "last_retry_at"):
                rec.pop(k, None)
            self.ledger.change({"t": now or time.time(), "kind": "resume", "scope": name,
                                "reason": "a retry after the error halt ran cleanly; steps book retroactively, so nothing was missed"})
