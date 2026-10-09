"""The fast loop (policy, paper broker, deciders, journal) and the slow loop's review."""

import json
import time

import numpy as np
import pytest

from tartar.data.dataset import load_trade_tokens
from tartar.data.simulate import simulate_raw
from tartar.decide import FunctionScorer, launch_states
from tartar.fastloop import FastLoop, InlineDecider, Journal, Policy, PolicyError, PolicyFile, ThreadDecider, replay
from tartar.profit import Costs, Exit, curves_for, round_trip
from tartar.review import load_journal, review, to_markdown


@pytest.fixture(scope="module")
def raw(tmp_path_factory):
    directory = tmp_path_factory.mktemp("raw")
    simulate_raw(directory, 60, seed=11)
    return directory


def open_policy(**changes) -> Policy:
    base = dict(skip_flags=[], max_open=100, max_entries_per_hour=1000, daily_loss_limit_sol=100.0)
    base.update(changes)
    return Policy.from_dict(base)


def journal_events(directory, kind):
    return [r for r in load_journal(directory) if r["e"] == kind]


def test_policy_limits():
    assert Policy.from_dict({}).mode == "paper"
    with pytest.raises(PolicyError):
        Policy.from_dict({"mode": "live"})
    with pytest.raises(PolicyError):
        Policy.from_dict({"size_sol": 5.0})
    with pytest.raises(PolicyError):
        Policy.from_dict({"threshold": 1.5})
    with pytest.raises(PolicyError):
        Policy.from_dict({"leverage": 10})
    with pytest.raises(PolicyError):
        Policy.from_dict({"scorer": "gpt"})


def test_policy_file_reloads_and_keeps_last_good(tmp_path):
    path = tmp_path / "policy.json"
    pf = PolicyFile(path)  # created with defaults
    assert pf.policy.threshold == 0.5
    data = json.loads(path.read_text())
    data["threshold"] = 0.7
    path.write_text(json.dumps(data))
    import os

    os.utime(path, (time.time() + 5, time.time() + 5))
    assert pf.reload() == (True, None) and pf.policy.threshold == 0.7
    data["mode"] = "live"
    path.write_text(json.dumps(data))
    os.utime(path, (time.time() + 10, time.time() + 10))
    changed, error = pf.reload()
    assert not changed and "paper" in error and pf.policy.threshold == 0.7


def test_paper_fills_match_the_backtest(raw, tmp_path):
    """Every paper trade equals profit.round_trip for the same decision."""
    rule = dict(hold_seconds=120.0, take_profit=0.3, stop_loss=0.2)
    policy = open_policy(**rule)
    loop = FastLoop(policy, Journal(tmp_path / "j"))
    replay(raw, loop)
    tokens = load_trade_tokens(raw, 60)
    curves = curves_for(tokens)
    by_mint = {t.mint: k for k, t in enumerate(tokens)}
    costs = policy.costs()
    exits = {r["mint"]: r for r in journal_events(tmp_path / "j", "exit")}
    decisions = {r["mint"]: r for r in journal_events(tmp_path / "j", "decision")}
    compared = 0
    for mint, record in exits.items():
        if mint not in by_mint:
            continue
        k = by_mint[mint]
        trade = round_trip(curves[k], decisions[mint]["t"], costs, Exit(120.0, 0.3, 0.2))
        if trade is None or trade.censored:
            continue
        assert record["pnl_sol"] == pytest.approx(trade.pnl_sol, rel=1e-9, abs=1e-12), mint
        assert record["reason"] == trade.reason
        compared += 1
    assert compared >= 10


def test_live_states_match_offline_states(raw, tmp_path):
    loop = FastLoop(open_policy(), Journal(tmp_path / "j"))
    replay(raw, loop)
    live = {r["mint"]: r["state"] for r in journal_events(tmp_path / "j", "screen")}
    tokens = load_trade_tokens(raw, 60)
    offline = launch_states(tokens, curves_for(tokens), 20.0)
    own = ("buyers", "trades", "buy_sol", "sell_sol", "holders", "top10_share", "sniper_share", "creator_share")
    compared = 0
    for state in offline:
        if state["mint"] in live:
            for key in own:
                a, b = state[key], live[state["mint"]][key]
                assert (b is None and a != a) or a == pytest.approx(b), (key, a, b)
            compared += 1
    assert compared >= 10


def test_skip_rules_and_caps(raw, tmp_path):
    loop = FastLoop(open_policy(max_open=2, min_buyers=1), Journal(tmp_path / "j"))
    summary = replay(raw, loop)
    screens = journal_events(tmp_path / "j", "screen")
    reasons = {r["skip"].split(" ")[0] for r in screens if "skip" in r}
    assert "max_open" in reasons
    assert summary["buys"] == len(journal_events(tmp_path / "j", "decision"))


def test_scorer_errors_and_timeouts_mean_skip(raw, tmp_path):
    def broken(state):
        raise RuntimeError("api down")

    policy = open_policy(scorer="jev")
    loop = FastLoop(policy, Journal(tmp_path / "j"), jev_factory=lambda: FunctionScorer("jev", broken), decider_factory=lambda s: InlineDecider(s, fixed_latency=0.1))
    summary = replay(raw, loop)
    assert summary["buys"] == 0 and summary["errors"] > 0
    slow = InlineDecider(FunctionScorer("slow", lambda s: 0.9), fixed_latency=5.0)
    slow.submit("m", {}, 100.0, timeout=2.0)
    (decision,) = slow.poll(200.0)
    assert decision.score is None and "timeout" in decision.error and decision.decided_at == 105.0


def test_thread_decider():
    decider = ThreadDecider(FunctionScorer("x", lambda s: 0.8), workers=2)
    decider.submit("a", {}, time.time(), timeout=5.0)
    deadline = time.time() + 5
    out = []
    while not out and time.time() < deadline:
        out = decider.poll(time.time())
        time.sleep(0.01)
    assert out[0].mint == "a" and out[0].score == 0.8 and out[0].error is None
    decider.close()


def test_review_reads_journal_and_counterfactuals(raw, tmp_path):
    rng = np.random.default_rng(0)
    loop = FastLoop(
        open_policy(scorer="jev", threshold=0.6),
        Journal(tmp_path / "j"),
        jev_factory=lambda: FunctionScorer("jev", lambda s: float(rng.random())),
        decider_factory=lambda s: InlineDecider(s, fixed_latency=0.2),
    )
    replay(raw, loop)
    result = review(load_journal(tmp_path / "j"), raw)
    assert result["scorer"]["decisions"] > 0 and result["scorer"]["latency_ms"]["median"] == pytest.approx(200.0)
    cf = result["counterfactual"]
    assert cf["all_screened"]["n"] >= cf["bought"]["n"] > 0
    assert result["calibration"]["buckets"]
    text = to_markdown(result)
    assert "Scorer calibration" in text and "paper trades" in text


def test_recorder_feeds_the_fast_loop(tmp_path):
    from tartar.data.recorder import Recorder

    seen = []
    recorder = Recorder(tmp_path / "raw")
    recorder.on_event = seen.append
    recorder.handle({"txType": "create", "mint": "M", "traderPublicKey": "C", "solAmount": 1, "initialBuy": 1e7, "vSolInBondingCurve": 31, "vTokensInBondingCurve": 1.04e9, "name": "x", "symbol": "X"})
    assert seen and seen[0]["e"] == "create" and seen[0]["mint"] == "M"
    recorder.writer.close()


def test_jev_shadow_answers_are_journaled_not_acted_on(raw, tmp_path):
    from tartar.fastloop import ShadowAsker

    class FakeJev:
        def ask(self, state):
            return {"buy": 0.9, "copycat": 0.1 if state["buyers"] else 0.8}

    policy = open_policy(shadow_jev=True, skip_flags=["sniped"])
    loop = FastLoop(policy, Journal(tmp_path / "j"), shadow_factory=lambda: ShadowAsker(FakeJev(), threaded=False))
    summary = replay(raw, loop)
    shadows = journal_events(tmp_path / "j", "shadow")
    screens = journal_events(tmp_path / "j", "screen")
    assert summary["shadow"] == len(shadows) == len(screens)  # every screened launch, skipped or not
    decisions = journal_events(tmp_path / "j", "decision")
    assert all(d["scorer"] == "rules" for d in decisions)  # the answers never decide anything
    result = review(load_journal(tmp_path / "j"), raw)
    assert set(result["shadow"]["questions"]) == {"buy", "copycat"}
    assert "Jev shadow answers" in to_markdown(result)
    with pytest.raises(PolicyError):
        FastLoop(open_policy(shadow_jev=True), Journal(tmp_path / "k"))  # no Jev client configured


K_CURVE = 30.0 * 1_073_000_000.0  # standard curve: virtual SOL x virtual tokens


def curve_event(kind, t, raised, sol=0.5, side="b", mint="RUN", **extra):
    vsol = 30.0 + raised
    event = {"e": kind, "t": t, "mint": mint, "sol": sol, "tok": 1.0, "vsol": vsol, "vtok": K_CURVE / vsol, "rsol": raised, **extra}
    if kind == "trade":
        event.update(side=side, trader=f"w{t}")
    else:
        event.update(creator="dev", name="Run", symbol="RUN", uri="")
    return event


def test_graduation_runup_entry_matches_the_hand_computation(tmp_path):
    from tartar.profit import buy_tokens, sell_sol

    policy = open_policy(runup_enter_sol=75.0, runup_exit_sol=80.0, runup_hold_seconds=600.0, skip_flags=[], min_buyers=1000)
    loop = FastLoop(policy, Journal(tmp_path / "j"))
    events = [curve_event("create", 0.0, 1.0)] + [
        curve_event("trade", t, r) for t, r in ((50.0, 50.0), (99.0, 70.0), (100.0, 76.0), (100.5, 78.0), (101.5, 79.0), (110.0, 81.0), (111.5, 82.0), (200.0, 83.0))
    ]
    loop.start(0.0)
    for event in events:
        loop.on_event(event)
    loop.finish(300.0)
    (runup,) = journal_events(tmp_path / "j", "runup")
    assert runup["raised"] == 76.0 and "skip" not in runup
    (fill,) = journal_events(tmp_path / "j", "fill")
    (exit_,) = journal_events(tmp_path / "j", "exit")
    assert fill["kind"] == exit_["kind"] == "runup" and exit_["reason"] == "raised"
    # decided at 100.0 -> fills 1 s later at the state after the 100.5 trade (78 SOL raised);
    # 81 SOL raised at 110.0 triggers the exit, which fills at 111.0: still the 110.0 state.
    costs = policy.costs()
    v_in, v_out = 30.0 + 78.0, 30.0 + 81.0
    tokens = buy_tokens(v_in, K_CURVE / v_in, costs.size_sol, costs.fee)
    pnl = sell_sol(v_out, K_CURVE / v_out, tokens, costs.fee) - costs.size_sol - 2 * costs.network_sol
    assert exit_["pnl_sol"] == pytest.approx(pnl, rel=1e-9) and exit_["pnl_sol"] > 0
    review_text = to_markdown(review(load_journal(tmp_path / "j")))
    assert "runup entries" in review_text and "run-ups triggered: 1" in review_text


def test_runup_policy_limits_and_quote_launches(tmp_path):
    with pytest.raises(PolicyError):
        Policy.from_dict({"runup_enter_sol": 80.0, "runup_exit_sol": 75.0})
    with pytest.raises(PolicyError):
        Policy.from_dict({"runup_enter_sol": 90.0})
    assert Policy.from_dict({}).runup_enter_sol is None  # off unless asked for
    loop = FastLoop(open_policy(runup_enter_sol=75.0), Journal(tmp_path / "j"))
    loop.on_event(curve_event("create", 0.0, 1.0, mint="Q", quote="USDC"))
    loop.on_event(curve_event("trade", 5.0, 80.0, mint="Q", quote="USDC"))
    summary = loop.finish(100.0)
    assert summary["launches"] == 0 and summary["runups"] == 0  # quote-paired curves are ignored


def test_completed_curves_cancel_buys_and_haircut_late_exits(tmp_path):
    policy = open_policy(runup_enter_sol=60.0, runup_exit_sol=80.0, runup_hold_seconds=600.0, graduation_haircut=0.2, min_buyers=1000)
    loop = FastLoop(policy, Journal(tmp_path / "j"))
    loop.start(0.0)
    # A: crosses 60 and completes in the same second, so the buy can't land.
    for event in (curve_event("create", 0.0, 1.0, mint="A"), curve_event("trade", 10.0, 61.0, mint="A"), curve_event("trade", 10.2, 85.0, mint="A")):
        loop.on_event(event)
    loop.on_event({"e": "migrate", "t": 10.3, "mint": "A"})
    # B: crosses 60, fills, then jumps from 79 to complete before the 80-level exit can land.
    for event in (curve_event("create", 20.0, 1.0, mint="B"), curve_event("trade", 30.0, 61.0, mint="B"), curve_event("trade", 32.0, 70.0, mint="B"),
                  curve_event("trade", 40.0, 79.0, mint="B"), curve_event("trade", 40.5, 85.0, mint="B")):  # fmt: skip
        loop.on_event(event)
    loop.on_event({"e": "migrate", "t": 40.6, "mint": "B"})
    loop.on_event(curve_event("trade", 100.0, 5.0, mint="OTHER"))
    loop.finish(1000.0)
    cancels = {r["mint"]: r for r in journal_events(tmp_path / "j", "cancel")}
    exits = {r["mint"]: r for r in journal_events(tmp_path / "j", "exit")}
    assert "completed" in cancels["A"]["reason"] and "A" not in exits
    assert exits["B"]["reason"] == "after_graduation"
    from tartar.profit import buy_tokens, sell_sol

    c = policy.costs()
    tokens = buy_tokens(91.0, K_CURVE / 91.0, c.size_sol, c.fee)  # filled at the 61 SOL state (30.0 + 1 s)
    expected = sell_sol(115.0, K_CURVE / 115.0, tokens, c.fee) * 0.8 - c.size_sol - 2 * c.network_sol
    assert exits["B"]["pnl_sol"] == pytest.approx(expected, rel=1e-9)
