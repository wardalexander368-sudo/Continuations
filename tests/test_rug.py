import math

import numpy as np
import pytest

from tartar.candles import Tick
from tartar.decide import NUMERIC, state_from_ticks
from tartar.feeds.base import Status
from tartar.feeds.pumpchain import ChainCreate, ChainTrade
from tartar.rug import RugModel, auc, find_rug_model, fit_platt, labelled_states, rug_model_name, rug_report, train_rug
from tartar.scam import CreatorIndex
from tartar.screen import next_clean_launch

T0 = 1_700_000_000.0


def test_auc_and_platt():
    assert auc([0.1, 0.2, 0.8, 0.9], [False, False, True, True]) == 1.0
    assert auc([0.9, 0.8, 0.2, 0.1], [False, False, True, True]) == 0.0
    assert auc([0.5, 0.5, 0.5, 0.5], [False, True, False, True]) == 0.5  # ties count half
    rng = np.random.default_rng(0)
    z = rng.normal(size=20000)
    y = rng.random(20000) < 1 / (1 + np.exp(-(2.0 * z - 1.0)))
    a, b = fit_platt(1 / (1 + np.exp(-z)), y)  # logit(p) = z, true model: 2 z - 1
    assert a == pytest.approx(2.0, abs=0.1) and b == pytest.approx(-1.0, abs=0.1)


def _rows(n=3000, seed=1):
    """Synthetic launches: rugs are likelier on non-standard curves and with a big raise."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        odd = rng.random() < 0.3
        raised = float(rng.exponential(2.0))
        p = 0.02 + 0.4 * odd + 0.05 * min(raised, 4)
        state = {k: float(rng.normal()) for k in NUMERIC}
        state.update(nonstandard_curve=float(odd), raised_sol=raised, risk="caution", risk_rank=2)
        rows.append({"t": T0 + i, "mint": f"M{i}", "state": state, "ratio": 1.0, "rug": bool(rng.random() < p), "moon": False, "simulated": False})
    return rows


def test_train_save_load_and_report(tmp_path):
    rows = _rows()
    model, report = train_rug(rows, log=lambda *_: None)
    assert report["test"]["auc"] > 0.75
    assert report["test"]["log_loss"] < report["test"]["log_loss_base_rate"]
    assert report["launches"] == {"train": 2100, "valid": 450, "test": 450}
    assert list(report["feature_gain"])[0] in ("nonstandard_curve", "raised_sol")
    path = model.save(tmp_path / rug_model_name())
    loaded = find_rug_model(tmp_path)
    assert loaded is not None and path.name == "rug-20s.txt"
    states = [r["state"] for r in rows[-50:]]
    assert np.allclose(loaded.predict_many(states), model.predict_many(states))
    assert rug_report(loaded, rows)["test"]["log_loss"] == pytest.approx(report["test"]["log_loss"])
    p = loaded.predict({"nonstandard_curve": 1.0, "raised_sol": 3.0})  # missing features are NaN
    assert 0.0 < p < 1.0
    assert find_rug_model(tmp_path / "nowhere") is None


def test_state_from_ticks_matches_the_screen():
    ticks = [
        Tick(T0 + 0.5, 1e-7, volume=0.1, buy_volume=0.1, buys=1, trader="dev", creator=True, liquidity=0.1, tokens=1e6, virtual_sol=30.1),
        Tick(T0 + 8, 1.1e-7, volume=0.3, buy_volume=0.3, buys=1, trader="a", liquidity=0.4, tokens=1e6, virtual_sol=30.4),
        Tick(T0 + 9, 1.2e-7, volume=0.2, buy_volume=0.2, buys=1, trader="b", liquidity=0.6, tokens=1e6, virtual_sol=30.6),
    ]
    state = state_from_ticks("M", T0, "dev", ticks, T0 + 20, CreatorIndex(), "Dog", "DOG")
    assert state["buyers"] == 2 and state["trades"] == 3 and state["seconds"] == 20
    assert state["buy_sol"] == pytest.approx(0.5) and state["raised_sol"] == pytest.approx(0.6)
    assert state["nonstandard_curve"] == 0.0 and not state["avoid"]


class _Stub:
    meta = {"screen": 20.0}

    def __init__(self):
        self.states = []

    def predict(self, state):
        self.states.append(state)
        return min(state["buyers"] / 10, 1.0)


def _trade(mint, user, sol, creator="dev"):
    vsol = 31.0
    return ChainTrade(mint, sol, sol * 3e7, True, user, int(T0), vsol, 32.19e9 / vsol, creator, vsol - 30)


async def test_screen_verdicts_carry_p_rug():
    clock = [T0]

    async def stream():
        yield Status("connected")
        yield T0, "sigC", [ChainCreate("MintC", "C", "C", "dev3", None), _trade("MintC", "dev3", 0.5, creator="dev3")]
        for i in range(4):
            clock[0] = T0 + 10 + i
            yield T0 + 10 + i, f"s{i}", [_trade("MintC", f"buyer{i}", 0.3, creator="dev3")]
        clock[0] = T0 + 21
        yield T0 + 21, "tick", [_trade("MintC", "buyer9", 0.2, creator="dev3")]

    stub = _Stub()
    verdict = await next_clean_launch(stream(), screen_seconds=20, min_buyers=3, creators=CreatorIndex(), clock=lambda: clock[0], rug_model=stub)
    assert verdict.passed and verdict.p_rug == pytest.approx(0.5)  # five buyers by the screen
    assert stub.states[0]["seconds"] == pytest.approx(21) and stub.states[0]["mint"] == "MintC"
    assert verdict.report.to_dict()["p_rug"] == 0.5 and "P(rug) 50%" in verdict.report.p_rug_text()


def test_labelled_states_from_a_recording(tmp_path):
    """End to end on a tiny recording: a launch that collapses is a rug, one that holds is not."""
    import gzip
    import json

    def create(mint, t, creator):
        return {"e": "create", "t": t, "mint": mint, "creator": creator, "name": mint, "symbol": mint, "sol": 0.5, "tok": 1.7e7, "vsol": 30.5, "vtok": 1.05e9, "rsol": 0.5, "trader": creator}

    def trade(mint, t, who, side, sol, vsol):
        return {"e": "trade", "t": t, "mint": mint, "side": side, "sol": sol, "tok": sol * 3e7, "vsol": vsol, "vtok": 32.19e9 / vsol, "rsol": vsol - 30, "trader": who}

    events = [{"e": "session", "t": T0 - 1, "state": "connected"}]
    for k, mint in enumerate(("RUG", "HOLD")):
        t = T0 + k
        events += [create(mint, t, f"dev{k}"), {"e": "track", "t": t, "mint": mint}]
        events += [trade(mint, t + 2 + i, f"w{k}{i}", "b", 10.0, 31.0 + 10 * i) for i in range(6)]  # to 81 SOL
    events += [trade("RUG", T0 + 30 + i, f"w0{i}", "s", 9.0, 72.0 - 9 * i) for i in range(5)]  # dumped to 36 SOL
    events += [trade("RUG", T0 + 40, "dev0", "s", 5.0, 31.0)]  # price (31/81)^2 = 15% of the screen's
    for k in range(3, 6 * 35):  # keep the recording alive past the 30-min horizon, no 30 s gaps
        events.append({"e": "trade", "t": T0 + 10 * k, "mint": "HOLD", "side": "b", "sol": 0.01, "tok": 3e5, "vsol": 81.0, "vtok": 32.19e9 / 81.0, "rsol": 51.0, "trader": "x"})
    path = tmp_path / "raw" / "20231114-22.jsonl.gz"
    path.parent.mkdir()
    with gzip.open(path, "wt") as f:
        for e in sorted(events, key=lambda e: e["t"]):
            f.write(json.dumps(e) + "\n")
    rows = labelled_states(str(tmp_path / "raw"))
    by_mint = {r["mint"]: r for r in rows}
    assert set(by_mint) == {"RUG", "HOLD"}
    assert by_mint["RUG"]["rug"] and not by_mint["HOLD"]["rug"]
    assert by_mint["RUG"]["ratio"] < 0.2 and math.isclose(by_mint["HOLD"]["ratio"], 1.0, rel_tol=0.2)
    assert not by_mint["HOLD"]["simulated"]
