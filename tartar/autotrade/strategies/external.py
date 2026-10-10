"""Plug-in point for strategies whose signals come from elsewhere (e.g. the launch selector).

The producer appends one JSON line per action to ``signals`` (path in the strategy config):

    {"kind": "open",  "key": "...", "at": unix, "asset": "MINT", "side": 1, "notional_usd": 20,
     "price": 1.2e-6, "label": "TOKEN", "reason": "..."}
    {"kind": "close", "key": "...", "at": unix, "price": 1.5e-6, "reason": "..."}

``price`` is the reference price the producer saw (from recorded or live data); the agent applies
the configured cost model, the risk limits and the lifecycle rules. Scoring uses the strategy's
``eval`` config, which must copy its pre-registration: ``min_trades`` (score once reached),
``deadline_days`` (fail if not passed by then, counted from the first trade), and success =
mean net per trade > 0 with the 90% bootstrap CI lower bound > 0.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core import Context, CostModel, Intent, Trade, Verdict, bootstrap_ci


class ExternalSignals:
    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self.prereg = cfg.get("prereg", "")
        self.path = Path(cfg["signals"])
        self.cost = CostModel(**cfg.get("cost", {}))
        self.eval = {"min_trades": 100, "deadline_days": 30, **cfg.get("eval", {})}

    def step(self, ctx: Context) -> list[Intent]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()
        start = int(ctx.state.get("line", 0))
        intents = []
        for line in lines[start:]:
            if not line.strip():
                continue
            s = json.loads(line)
            meta = {"key": s["key"], "label": s.get("label", s.get("asset", ""))}
            if s["kind"] == "open":
                intents.append(Intent("open", self.name, float(s["at"]), float(s["price"]), s.get("reason", ""),
                                      asset=s["asset"], side=int(s.get("side", 1)), notional_usd=float(s["notional_usd"]),
                                      cost=self.cost, meta=meta))
            elif s["kind"] == "close":
                intents.append(Intent("close", self.name, float(s["at"]), float(s["price"]), s.get("reason", ""),
                                      cost=self.cost, meta=meta))
        ctx.state["line"] = len(lines)
        return intents

    def marks(self, ctx: Context) -> dict[str, tuple[float, float]]:
        return {}

    def evaluate(self, trades: list[Trade], now: float, state: dict) -> Verdict:
        n = len(trades)
        if not n:
            return Verdict("pending", 0, {}, "no closed trades yet")
        m, lo, hi = bootstrap_ci([t.net_return for t in trades])
        days = (now - min(t.entry_at for t in trades)) / 86400
        stats = {"n": n, "days": round(days, 2), "mean_net": m, "lo": lo, "hi": hi}
        summary = f"{n} trades: mean net {100 * m:+.2f}% [{100 * lo:+.2f}, {100 * hi:+.2f}]"
        if n >= self.eval["min_trades"]:
            if m > 0 and lo > 0:
                return Verdict("pass", n, stats, summary)
            if days >= self.eval["deadline_days"]:
                return Verdict("fail", n, stats, summary + f"; not passed by day {self.eval['deadline_days']}")
        elif days >= self.eval["deadline_days"]:
            return Verdict("fail", n, stats, summary + f"; fewer than {self.eval['min_trades']} trades by day {self.eval['deadline_days']}")
        return Verdict("pending", n, stats, summary)
