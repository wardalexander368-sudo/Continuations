"""The agent's book on disk: state.json (open positions, strategy status, counters), journal.jsonl
(every fill and close), trades.jsonl (closed trades), changes.jsonl (every lifecycle or risk change)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .core import Position, Trade

DEFAULT_STATUS = "paper"


class Ledger:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        self.state.setdefault("positions", [])
        self.state.setdefault("strategies", {})  # name -> {"status", "errors", "size_factor", "data": {...}}
        self.state.setdefault("daily", {})  # "YYYY-MM-DD" -> realized pnl usd
        self.state.setdefault("halted", None)  # global halt reason, or None
        self.positions = [Position.from_dict(p) for p in self.state["positions"]]
        self._trades: list[Trade] | None = None

    # strategy records
    def strategy(self, name: str) -> dict:
        rec = self.state["strategies"].setdefault(name, {})
        rec.setdefault("status", DEFAULT_STATUS)
        rec.setdefault("errors", 0)
        rec.setdefault("size_factor", 1.0)
        rec.setdefault("data", {})
        return rec

    # trades
    def trades(self, strategy: str | None = None) -> list[Trade]:
        if self._trades is None:
            path = self.root / "trades.jsonl"
            self._trades = [Trade.from_dict(json.loads(line)) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
        return [t for t in self._trades if strategy is None or t.strategy == strategy]

    def add_trade(self, trade: Trade) -> None:
        self.trades()
        self._trades.append(trade)
        self._append("trades.jsonl", trade.to_dict())
        if not trade.meta.get("shadow"):
            day = time.strftime("%Y-%m-%d", time.gmtime(trade.exit_at))
            self.state["daily"][day] = self.state["daily"].get(day, 0.0) + trade.pnl_usd

    # logs
    def journal(self, row: dict) -> None:
        self._append("journal.jsonl", row)

    def change(self, row: dict) -> None:
        """A lifecycle or risk change: always logged, with the reason and the numbers behind it."""
        self._append("changes.jsonl", row)

    def changes(self) -> list[dict]:
        path = self.root / "changes.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []

    def _append(self, name: str, row: dict) -> None:
        with (self.root / name).open("a") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    def save(self) -> None:
        self.state["positions"] = [p.to_dict() for p in self.positions]
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1, sort_keys=True))
        tmp.replace(self.state_path)
