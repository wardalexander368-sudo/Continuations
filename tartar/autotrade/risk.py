"""Risk limits and the kill switch.

* Kill switch: the file ``autotrade/HALT`` (any content is the reason) or a global halt set by the
  daily loss cap stops every new entry. Exits still run so positions close on schedule; with
  ``flatten_on_halt`` the agent closes everything at the latest marks instead.
* Caps: max notional per position, max open positions per strategy and in total, max gross exposure.
* Shadow variants (research copies of a rule) count only against their own per-strategy cap.
* Daily loss cap: realized + unrealized PnL of the UTC day below ``-daily_loss_cap_usd`` halts the
  agent until ``resume``.
* Errors: a strategy whose step raises ``max_consecutive_errors`` times in a row is halted
  (status "halted") until ``resume``.
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
    "flatten_on_halt": False,
}


class Risk:
    def __init__(self, config: dict, root: Path, ledger):
        self.limits = {**DEFAULTS, **config.get("risk", {})}
        self.root = Path(root)
        self.ledger = ledger

    def kill_reason(self) -> str | None:
        f = self.root / "HALT"
        if f.exists():
            return "kill switch: " + (f.read_text().strip() or "HALT file present")
        return self.ledger.state.get("halted")

    def day_pnl(self, now: float, positions: list[Position]) -> float:
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        realized = self.ledger.state["daily"].get(day, 0.0)
        return realized + sum(p.unrealized() for p in positions if not p.meta.get("shadow"))

    def check_daily(self, now: float, positions: list[Position]) -> str | None:
        pnl = self.day_pnl(now, positions)
        if pnl < -self.limits["daily_loss_cap_usd"] and not self.ledger.state.get("halted"):
            reason = f"daily loss cap: {pnl:.2f} USD < -{self.limits['daily_loss_cap_usd']:.2f}"
            self.ledger.state["halted"] = reason
            self.ledger.change({"t": now, "kind": "halt", "scope": "agent", "reason": reason})
            return reason
        return None

    def allow_open(self, intent: Intent, positions: list[Position]) -> str | None:
        """None if allowed, else why not."""
        why = self.kill_reason()
        if why:
            return why
        lim = self.limits
        if intent.notional_usd <= 0:
            return "zero size"
        if intent.notional_usd > lim["max_position_usd"]:
            return f"position {intent.notional_usd:.2f} > max {lim['max_position_usd']:.2f} USD"
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
            self.ledger.change({"t": now, "kind": "halt", "scope": name, "reason": f"{rec['errors']} consecutive errors: {err[:300]}"})
            return True
        return False

    def record_ok(self, name: str) -> None:
        self.ledger.strategy(name)["errors"] = 0
