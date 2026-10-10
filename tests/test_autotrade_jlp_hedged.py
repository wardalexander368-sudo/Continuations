"""The hedged-JLP basket in the agent, offline: paper legs, rebalances, and the dry twins of all four legs."""

import json
from datetime import datetime, timezone

import pytest

from tartar.autotrade import broker as broker_mod
from tartar.autotrade.core import Context
from tartar.autotrade.ledger import Ledger
from tartar.autotrade.perps import DryPerpExecutor
from tartar.autotrade.runner import run_once
from tartar.autotrade.strategies.jlp_hedged import JLP_MINT, JLPHedged
from tartar.autotrade.usd_spot import DryUsdSpotExecutor


def t(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


MARK = {"SOL": 110.0, "ETH": 2500.0, "BTC": 80000.0}


def snap(when, price=4.65, delta=None, mark=None):
    delta = delta or {"SOL": 0.0186, "ETH": 0.000144, "BTC": 7.0e-6}
    mark = mark or MARK
    return {"t": when, "jlp": {"price": price, "delta": delta},
            "hl": {c: {"mark": m, "bid": m * 0.9995, "ask": m * 1.0005} for c, m in mark.items()},
            "quote": {"buy_bps": 5.0, "sell_bps": 20.0}}


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


class FakeInfo:
    def __init__(self):
        self.mid = dict(MARK)

    def funding_rate_sum(self, coin, t0, t1):
        return 0.0001

    def post(self, body):
        return {c: str(m) for c, m in self.mid.items()}

    def book(self, coin):
        m = self.mid[coin]
        return ([{"px": str(m * 0.9995), "sz": "1000"}], [{"px": str(m * 1.0005), "sz": "1000"}])

    def sz_decimals(self, coin):
        return 5


class FakeQuotes:
    price = 4.65

    def quote(self, a, b, amount):
        if b == JLP_MINT:  # USDC -> JLP, 6 decimals both
            return {"outAmount": str(int(amount / self.price * 0.999)), "priceImpactPct": "0.001"}
        return {"outAmount": str(int(amount * self.price * 0.998)), "priceImpactPct": "0.002"}


def test_opens_basket_rebalances_on_drift_and_closes_at_end(tmp_path):
    p = tmp_path / "s.jsonl"
    write(p, [snap("2026-10-09T17:36:45Z"), snap("2026-10-10T00:40:00Z")])  # the pilot row is before the window
    s = JLPHedged("jlp_hedged", {"snapshots": str(p), "_info": FakeInfo(), "size_usd": 200})
    ctx = Context(t("2026-10-10T01:00:00"), [], {}, {})
    out = s.step(ctx)
    assert [(i.asset, i.side, i.meta["venue"]) for i in out] == [
        ("JLP", 1, "jupiter_usd"), ("SOL", -1, "hyperliquid"), ("ETH", -1, "hyperliquid"), ("BTC", -1, "hyperliquid")]
    sol = out[1]
    assert sol.notional_usd == pytest.approx(200 * 0.0186 * 110 / 4.65, abs=0.01)
    assert all(i.meta["basket"] == "jlp" for i in out) and out[0].meta["mint"] == JLP_MINT
    assert s.step(ctx) == []

    class Pos:
        def __init__(self, i):
            self.asset, self.side, self.notional_usd, self.entry_price = i.asset, i.side, i.notional_usd, i.price
            self.entry_at, self.meta, self.id = i.at, i.meta, i.asset

    ctx.positions = [Pos(i) for i in out]
    write(p, [snap("2026-10-10T00:40:00Z"), snap("2026-10-10T04:40:00Z", mark={**MARK, "SOL": 111.0})])
    assert s.step(ctx) == []  # 1% move: inside the 5% band
    write(p, [snap("2026-10-10T08:40:00Z", delta={"SOL": 0.0215, "ETH": 0.000144, "BTC": 7.0e-6})])
    out = s.step(ctx)
    assert [(i.kind, i.asset or i.meta["key"]) for i in out] == [
        ("close", "jlp:SOL"), ("open", "SOL"), ("close", "jlp:ETH"), ("open", "ETH"), ("close", "jlp:BTC"), ("open", "BTC")]
    assert out[0].cost.fee > 1e-5 and out[2].cost.fee < 1e-6 and out[1].cost.fee == 0  # ETH barely moved
    assert out[0].meta["carry_usd"] == pytest.approx(sol.notional_usd * 0.0001)  # short receives positive funding
    end = Context(t("2027-01-09T00:00:00"), ctx.positions, ctx.state, {})
    closes = s.step(end)
    assert {i.meta["key"] for i in closes} == {"jlp:JLP", "jlp:SOL", "jlp:ETH", "jlp:BTC"}
    assert next(i for i in closes if i.meta["key"] == "jlp:JLP").cost.fee == pytest.approx(20e-4)


def test_basket_runs_as_dry_twins_in_the_agent(tmp_path, monkeypatch):
    info = FakeInfo()
    now = t("2026-10-10T01:00:00")
    monkeypatch.setattr(broker_mod, "make_perp_executor", lambda route, cfg, env=None, *a: DryPerpExecutor(info, clock=lambda: now))
    monkeypatch.setattr(broker_mod, "make_usd_spot_executor", lambda route: DryUsdSpotExecutor(FakeQuotes(), clock=lambda: now))
    monkeypatch.setattr(broker_mod, "make_executor", lambda route, cfg, env=None: None)
    monkeypatch.delenv("TARTAR_LIVE_KILL", raising=False)
    p = tmp_path / "s.jsonl"
    write(p, [snap("2026-10-10T00:40:00Z")])
    root = tmp_path / "root"
    root.mkdir()
    (root / "config.json").write_text(json.dumps({"mode": "dry_live", "strategies": {}, "live": {"perps": {}}}))
    strat = JLPHedged("jlp_hedged", {"snapshots": str(p), "_info": info, "size_usd": 200, "twin_basket_usd": 200})
    run_once(root, now=now, strategies={"jlp_hedged": strat})
    led = Ledger(root)
    twins = {pos.asset: pos.meta.get("live") for pos in led.positions}
    assert set(twins) == {"JLP", "SOL", "ETH", "BTC"} and all(twins.values()), twins
    assert twins["JLP"]["venue"] == "jupiter_usd" and twins["JLP"]["notional_in"] == 200
    assert twins["SOL"]["side"] == -1 and twins["SOL"]["notional_in"] == pytest.approx(88, abs=1)
    assert twins["ETH"]["notional_in"] >= 10
    rows = [json.loads(x) for x in (root / "fills.jsonl").read_text().splitlines()]
    assert sorted(r["event"] for r in rows) == ["perp_open", "perp_open", "perp_open", "usd_buy"]
    # the end of the window closes every leg and compares each twin with its paper twin
    later = t("2027-01-09T00:00:00")
    monkeypatch.setattr(broker_mod, "make_perp_executor", lambda route, cfg, env=None, *a: DryPerpExecutor(info, clock=lambda: later))
    monkeypatch.setattr(broker_mod, "make_usd_spot_executor", lambda route: DryUsdSpotExecutor(FakeQuotes(), clock=lambda: later))
    run_once(root, now=later, strategies={"jlp_hedged": strat})
    led = Ledger(root)
    assert not led.positions and len(led.trades()) == 4
    rows = [json.loads(x) for x in (root / "fills.jsonl").read_text().splitlines()]
    assert sorted(r["event"] for r in rows[4:]) == ["perp_close", "perp_close", "perp_close", "usd_sell"]
    assert all("live_minus_paper" in r["compare"] for r in rows[4:])
