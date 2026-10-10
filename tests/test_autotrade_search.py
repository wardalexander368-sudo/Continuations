import json
from datetime import date, datetime, timedelta, timezone

import numpy as np

from tartar.autotrade import search
from tartar.autotrade.ledger import Ledger
from tartar.autotrade.runner import run_once
from tartar.autotrade.strategies.vault_hold import VaultHold
from tartar.autotrade.strategies.xs_momentum import rank_signal


def panel(n_days=900, n_coins=40, persistent=True, seed=0):
    """Synthetic perps: each coin has a drift that persists for ~60 days (momentum works) or none."""
    rng = np.random.default_rng(seed)
    days = [date(2023, 1, 1) + timedelta(days=i) for i in range(n_days)]
    drift = np.zeros((n_days, n_coins))
    if persistent:
        for start in range(0, n_days, 60):
            drift[start:start + 60] = rng.normal(0, 0.01, n_coins)
    r = drift + rng.normal(0, 0.02, (n_days, n_coins))
    C = 100 * np.exp(np.cumsum(r, axis=0))
    V = np.full_like(C, 5e6)
    coins = [f"C{j}" for j in range(n_coins)]
    return search.Panel(days, coins, C, V, None)


def test_backtest_finds_momentum_and_charges_costs():
    P = panel()
    p = {"lookback": 14, "quant": 5, "scaled": False, "signal_weekday": 0, "lag_days": 1}
    s = search.backtest(P, p)
    assert len(s) > 100 and np.mean([v for _, v in s]) > 0.005
    assert all(d.weekday() == 0 for d, _ in s)
    free = search.backtest(P, p, cost=0.0)
    assert np.mean([v for _, v in free]) > np.mean([v for _, v in s])  # turnover costs bite


def test_funding_is_charged_to_longs_and_paid_to_shorts():
    P = panel(seed=3)
    p = {"lookback": 14, "quant": 5, "scaled": False, "signal_weekday": 0, "lag_days": 1}
    base = dict(search.backtest(P, p))
    F = {c: {d.isoformat(): 0.001 for d in P.days} for c in P.coins}  # every coin pays 0.1%/day to longs
    P2 = search.Panel(P.days, P.coins, P.C, P.V, F)
    charged = dict(search.backtest(P2, p))
    # equal weight long and short: longs pay 7 days of funding, shorts receive it, so the net is unchanged
    assert all(abs(charged[d] - base[d]) < 1e-9 for d in base)
    F = {c: {d.isoformat(): (0.001 if j % 2 else 0.0) for d in P.days} for j, c in enumerate(P.coins)}
    P3 = search.Panel(P.days, P.coins, P.C, P.V, F)
    assert any(abs(dict(search.backtest(P3, p))[d] - base[d]) > 1e-6 for d in base)


def test_scaled_signal_matches_vmom_definition():
    P = panel()
    i = 200
    s = rank_signal(P.C, i, 14, True)
    daily = P.C[i - 13: i + 1] / P.C[i - 14: i] - 1
    assert np.allclose(s, (P.C[i] / P.C[i - 14] - 1) / daily.std(axis=0))


def test_judge_penalizes_and_checks_holdout():
    weeks = [date(2023, 7, 3) + timedelta(weeks=k) for k in range(150)]
    rng = np.random.default_rng(0)
    strong = [(d, 0.02 + 0.01 * rng.standard_normal()) for d in weeks]
    noise = [(d, 0.003 + 0.04 * rng.standard_normal()) for d in weeks]
    decayed = [(d, (0.02 if k < 124 else -0.01) + 0.005 * rng.standard_normal()) for k, d in enumerate(weeks)]
    reg = [(d, 0.04 * rng.standard_normal()) for d in weeks]
    v = search.judge({"strong": strong, "noise": noise, "decayed": decayed, "xs_momentum": reg}, M=94)
    assert v["strong"]["survives"]
    assert not v["noise"]["checks"]["penalized_train"]
    assert v["decayed"]["checks"]["penalized_train"] and not v["decayed"]["checks"]["holdout"]
    copy = search.judge({"copy": [(d, x + 1e-4) for d, x in strong], "xs_momentum": strong}, M=94)
    assert not copy["copy"]["checks"]["not_a_copy"]


def test_run_queues_survivors_and_agent_starts_them_after_the_wait(tmp_path, monkeypatch):
    P = panel()
    now = datetime(2025, 7, 1, 12, tzinfo=timezone.utc).timestamp()
    s = search.run(tmp_path, now=now, panel=P)
    assert s["tested"] == 94 and s["M"] == 94
    assert (tmp_path / "search" / "REPORT.md").exists()
    lines = (tmp_path / "search" / "tested.jsonl").read_text().splitlines()
    assert len(lines) == 94
    assert s["survivors"], "a persistent-drift market should give survivors"
    assert 1 <= len(s["queued"]) <= search.MAX_NEW
    spec = json.loads((tmp_path / "candidates" / f"{s['queued'][0]}.json").read_text())
    assert spec["starts_at"] == "2025-07-08" and spec["score_weeks"] == search.SCORE_WEEKS
    assert date.fromisoformat(spec["start"]).weekday() == spec["params"]["signal_weekday"]
    # a second run the same day: same rules, nothing queued twice, M unchanged
    s2 = search.run(tmp_path, now=now + 60, panel=P)
    assert s2["M"] == 94 and not set(s2["queued"]) & set(s["queued"])
    # the agent: not before the wait, then registered as a (shadow) paper strategy
    (tmp_path / "config.json").write_text(json.dumps({"mode": "paper", "strategies": {}}))
    assert search.active_candidates(tmp_path, now + 86400) == {}
    later = datetime(2025, 7, 8, 1, tzinfo=timezone.utc).timestamp()
    act = search.active_candidates(tmp_path, later)
    assert set(s["queued"]) <= set(act) and all(c["shadow"] for c in act.values())
    run_once(tmp_path, now=later)
    reg = [c for c in Ledger(tmp_path).changes() if c.get("kind") == "registered"]
    assert {c["scope"] for c in reg} >= set(s["queued"])


def vault_history(points):
    av = [(t * 1000, v) for t, v, _ in points]
    pnl = {t: p for t, _, p in points}
    return lambda ctx: ([(t / 1000, v) for t, v in av], {t: p for t, p in pnl.items()})


def test_vault_hold_books_each_interval_and_stops_at_window_end(tmp_path):
    t0 = datetime(2026, 10, 12, tzinfo=timezone.utc).timestamp()
    pts = [(t0 - 86400, 100.0, 0.0), (t0 + 3600, 100.0, 0.0), (t0 + 14 * 86400, 101.0, 1.0),
           (t0 + 28 * 86400, 103.0, 3.0), (t0 + 30 * 86400, 104.0, 4.0)]  # the last point is "now"
    cfg = {"kind": "vault_hold", "size_usd": 200, "start": "2026-10-12", "end": "2026-11-10"}
    (tmp_path / "config.json").write_text(json.dumps({"mode": "paper", "strategies": {"hlp": cfg}}))
    strat = VaultHold("hlp", {**cfg, "_fetch": vault_history(pts)})
    s = run_once(tmp_path, now=t0 + 30 * 86400, strategies={"hlp": strat})
    assert s["opened"] == 3 and s["closed"] == 2
    tr = Ledger(tmp_path).trades("hlp")
    assert [round(t.net_return, 6) for t in tr] == [0.01, round(2 / 101, 6)]
    # a later point beyond the window closes the open interval without scoring it
    pts2 = pts[:-1] + [(t0 + 42 * 86400, 105.0, 5.0), (t0 + 43 * 86400, 105.0, 5.0)]
    strat = VaultHold("hlp", {**cfg, "_fetch": vault_history(pts2)})
    s = run_once(tmp_path, now=t0 + 43 * 86400, strategies={"hlp": strat})
    L = Ledger(tmp_path)
    assert s["closed"] == 1 and not L.positions
    assert L.trades("hlp")[-1].meta.get("window_end")
    v = strat.evaluate(L.trades("hlp"), t0 + 43 * 86400, {})
    assert v.n == 2 and v.decision in ("pass", "fail")
