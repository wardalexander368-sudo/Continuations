import pytest
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


def test_hl_sqrt_costs_scale_with_size_and_liquidity():
    import pytest
    from tartar.autotrade.strategies.xs_momentum import XSMomentum

    flat = XSMomentum("xs", {})
    assert flat.side_cost(1e6, 1e6) == 0.002  # registered: flat 20 bps
    s = XSMomentum("xs", {"costs": {"model": "hl_sqrt", "taker": 0.00045, "impact_k": 0.022}})
    assert s.side_cost(5_000, 10e6) == pytest.approx(0.00045 + 0.00049, abs=1e-5)   # ~4 bps over the fee
    assert s.side_cost(100_000, 2e6) == pytest.approx(0.00045 + 0.0049, abs=1e-4)   # ~49 bps over the fee
    assert s.side_cost(100, float("nan")) < 0.001


def test_dry_perp_fill_carries_the_exact_unsigned_order():
    from tartar.autotrade.perps import DryPerpExecutor

    class Info:
        def book(self, coin):
            return ([{"px": "99.9", "sz": "5"}], [{"px": "100.1", "sz": "0.05"}, {"px": "100.5", "sz": "5"}, {"px": "102", "sz": "9"}])

        def sz_decimals(self, coin):
            return 2

        def asset_index(self, coin):
            return 7

    ex = DryPerpExecutor(info=Info(), clock=lambda: 0.0, slippage=0.01)
    f = ex.open("X", 1, 50.0, cloid="0xabc")
    o = f.extra["order"]
    assert o == {"a": 7, "b": True, "p": "101", "s": "0.5", "r": False, "t": {"limit": {"tif": "Ioc"}}, "c": "0xabc"}
    assert f.extra["ioc_fill_frac"] == 1.0
    c = ex.close("X", 1, 0.5)
    assert c.extra["order"]["r"] is True and c.extra["order"]["b"] is False


def test_book_vol_target_scales_new_legs(tmp_path):
    from tartar.autotrade import perp_risk
    from tartar.autotrade.core import Trade

    root = setup(tmp_path)
    led = Ledger(root)
    cfg = json.loads((root / "config.json").read_text())
    assert perp_risk.book_scale(led, cfg, {})[0] == 1.0  # no history yet
    for k, r in enumerate([0.08, -0.08] * 5):  # 8%/week book vol -> scale clipped to 0.5
        led.add_trade(Trade(f"t{k}", "xs", "A", 1, 1000, 1, 0, 1, 1, 0, 1000 * r, r,
                            meta={"week": f"2026-{k + 1:02d}", "leg_usd": 1000.0}))
    k, why = perp_risk.book_scale(led, cfg, {})
    assert k == 0.5 and "scale x0.50" in why
    for t in led.trades():
        t.pnl_usd /= 10  # 0.8%/week -> clipped to 1.5
    assert perp_risk.book_scale(led, cfg, {})[0] == 1.5
    assert perp_risk.book_scale(led, cfg, {"book_vol_target": 0.0113})[0] == pytest.approx(0.0113 / 0.008433, rel=1e-3)


def test_us_and_hyperliquid_books_are_sized_and_stopped_separately(tmp_path):
    from tartar.autotrade import perp_risk
    from tartar.autotrade.core import Position, Trade

    cfg = {"strategies": {"xs": {"kind": "xs_momentum"}, "cde": {"kind": "xs_momentum", "data": "coinbase"},
                          "cand": {"kind": "xs_momentum", "data": "coinbase", "shadow": True}}}
    assert perp_risk.book_names(cfg, "hl") == ["xs"] and perp_risk.book_names(cfg, "us") == ["cde"]
    root = setup(tmp_path, {"strategies": cfg["strategies"]})
    led = Ledger(root)
    for k, r in enumerate([0.08, -0.08] * 5):  # a volatile Hyperliquid book must not shrink the US book
        led.add_trade(Trade(f"t{k}", "xs", "A", 1, 1000, 1, 0, 1, 1, 0, 1000 * r, r,
                            meta={"week": f"2026-{k + 1:02d}", "leg_usd": 1000.0}))
    assert perp_risk.book_scale(led, cfg, {}, "hl")[0] == 0.5 and perp_risk.book_scale(led, cfg, {}, "us")[0] == 1.0
    # a US leg down 15% of its side budget trips the weekly loss limit (no funding on Coinbase)
    p = Position("p1", "cde", "BTC", 1, 250.0, 100.0, 0.0, 0.5, meta={"week": "2026-10-12", "leg_usd": 250.0, "venue": "coinbase_perps"})
    p.mark_price, p.mark_at = 85.0, 10.0
    led.positions.append(p)
    out = perp_risk.weekly_stops(led, {}, 20.0, {})
    assert len(out) == 1 and out[0].position_id == "p1" and out[0].meta["carry_usd"] == 0.0
    # the US book's drawdown is tracked on its own (here -50% of its side budget)
    p.mark_price = 50.0
    assert perp_risk.account_drawdown(led, cfg, root, 20.0, {}, "hl") is None
    perp_risk.account_drawdown(led, cfg, root, 20.0, {}, "us")
    assert "perp_risk_us" in led.state and (root / "HALT").exists()
