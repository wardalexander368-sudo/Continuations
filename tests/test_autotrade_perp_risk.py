import json

from tartar.autotrade.core import Position
from tartar.autotrade.ledger import Ledger
from tartar.autotrade.runner import run_once


class Idle:
    """A perps strategy that does nothing this run and marks legs at preset prices."""

    prereg = "test"

    def __init__(self, name, marks):
        self.name, self._marks = name, marks

    def step(self, ctx):
        return []

    def marks(self, ctx):
        return {p.id: (self._marks[p.asset], ctx.now) for p in ctx.positions}

    def evaluate(self, trades, now, state):
        from tartar.autotrade.core import Verdict
        return Verdict("pending", len(trades), {}, "")


def book(root, name="xs", week="2026-10-12"):
    led = Ledger(root)
    for i, (coin, side) in enumerate([("A", 1), ("B", 1), ("C", -1), ("D", -1)]):
        led.positions.append(Position(f"p{i}", name, coin, side, 250.0, 1.0, 1000.0, 0.5,
                                      meta={"venue": "hyperliquid", "week": week, "leg_usd": 1000.0}))
    led.save()


def setup(tmp_path, cfg_extra=None):
    cfg = {"mode": "paper", "strategies": {"xs": {"kind": "xs_momentum", "leg_usd": 1000}}, **(cfg_extra or {})}
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    return tmp_path


def test_weekly_loss_limit_flattens_and_pauses_once(tmp_path):
    root = setup(tmp_path)
    book(root)
    # longs -10%, shorts +10% against us: week P&L about -100 -1 = -101 < -120? no: -2 entry costs
    s = run_once(root, now=2000.0, strategies={"xs": Idle("xs", {"A": 0.9, "B": 0.9, "C": 1.1, "D": 1.1})})
    assert s.get("closed", 0) == 0  # -102 USD is inside the 12% (120 USD) limit
    s = run_once(root, now=3000.0, strategies={"xs": Idle("xs", {"A": 0.85, "B": 0.85, "C": 1.15, "D": 1.15})})
    led = Ledger(root)
    assert s["closed"] == 4 and not led.positions
    assert all(t.meta.get("stop") == "weekly_loss" for t in led.trades())
    pauses = [c for c in led.changes() if c["kind"] == "pause"]
    assert len(pauses) == 1 and pauses[0]["week"] == "2026-10-12"
    assert led.strategy("xs")["stopped_week"] == "2026-10-12"


def test_account_drawdown_writes_halt(tmp_path):
    root = setup(tmp_path, {"perp_risk": {"weekly_stop_frac": 10.0, "account_drawdown_stop_frac": 0.35}})
    book(root)
    run_once(root, now=2000.0, strategies={"xs": Idle("xs", {"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0})})
    assert not (root / "HALT").exists()
    s = run_once(root, now=3000.0, strategies={"xs": Idle("xs", {"A": 0.6, "B": 0.6, "C": 1.4, "D": 1.4})})
    assert (root / "HALT").exists() and "drawdown" in (root / "HALT").read_text()
    assert s["new_halts"] and s["halted"]
