"""Launch decisions: causal launch states, scorer evaluation, caching, and the Jev client."""

import httpx
import numpy as np
import pytest

from tartar.data.dataset import load_trade_tokens
from tartar.data.simulate import simulate_raw
from tartar.decide import NUMERIC, CachedScorer, FlagScorer, FunctionScorer, evaluate, launch_states, state_matrix
from tartar.jev import JevFormatError, JevScorer, build_request, parse_probability
from tartar.profit import Costs, Exit, curves_for


@pytest.fixture(scope="module")
def launches(tmp_path_factory):
    directory = tmp_path_factory.mktemp("sim")
    simulate_raw(directory, 60, seed=7)
    tokens = load_trade_tokens(directory, 60)
    curves = curves_for(tokens)
    return tokens, curves, launch_states(tokens, curves, 20.0)


def test_launch_states_use_only_the_first_seconds(launches):
    tokens, curves, states = launches
    assert len(states) == len(tokens)
    assert [s["decide_at"] for s in states] == sorted(s["decide_at"] for s in states)
    for s in states:
        token = tokens[s["token"]]
        early = [t for group in token.ticks.values() for t, _ in group if t.ts <= s["decide_at"]]
        assert s["trades"] == len(early)
    assert state_matrix(states).shape == (len(states), len(NUMERIC))


def test_creator_history_is_causal(launches):
    tokens, curves, states = launches
    seen: dict[str, int] = {}
    for s in states:  # launch order
        creator = tokens[s["token"]].creator
        assert s["creator_launches"] <= seen.get(creator, 0)
        seen[creator] = seen.get(creator, 0) + 1


def test_evaluate_picks_threshold_on_validation(launches):
    tokens, curves, states = launches
    n = len(states)
    split = np.where(np.arange(n) < 0.5 * n, 0, np.where(np.arange(n) < 0.75 * n, 1, 2))
    everything = evaluate(FunctionScorer("all", lambda s: 1.0), states, split, curves, Costs(), Exit(60.0), min_trades=1)
    assert everything["kept_share_valid"] == 1.0 and everything["test"]["trades"] > 0
    nothing = evaluate(FunctionScorer("none", lambda s: 0.0), states, split, curves, Costs(), Exit(60.0), min_trades=10**6)
    assert nothing["threshold"] is None


def test_flag_scorer_learns_from_training_outcomes():
    states = [{"flags": ["bad"]} for _ in range(40)] + [{"flags": ["meh"]} for _ in range(40)] + [{"flags": []} for _ in range(40)]
    labels = np.array([-0.5] * 40 + [-0.05] * 40 + [-0.04] * 40)
    scorer = FlagScorer(states, labels)
    assert scorer.bad == ["bad"]
    assert scorer.score([{"flags": ["bad", "x"]}, {"flags": ["meh"]}]).tolist() == [0.0, 1.0]


def test_cached_scorer_asks_once(tmp_path):
    calls = []

    class Counting:
        name = "counting"

        def score(self, states):
            calls.extend(s["mint"] for s in states)
            return np.array([0.5] * len(states))

    path = tmp_path / "cache.jsonl"
    states = [{"mint": "a"}, {"mint": "b"}]
    assert CachedScorer(Counting(), path).score(states).tolist() == [0.5, 0.5]
    assert CachedScorer(Counting(), path).score(states + [{"mint": "c"}]).tolist() == [0.5, 0.5, 0.5]
    assert calls == ["a", "b", "c"]


def test_jev_client_request_and_errors():
    state = {"name": "Dog", "buyers": 4, "rise_pct": float("nan"), "flags": ["sniped"], "seconds": 20}
    body = build_request(state, "within 3 minutes", model="typesafe/jev")
    assert body["state"]["rise_pct"] is None and body["state"]["flags"] == ["sniped"] and body["model"] == "typesafe/jev"
    assert body["questions"][0]["type"] == "noul"
    assert parse_probability({"answers": [{"id": "buy", "probability": 0.31}]}) == 0.31
    with pytest.raises(JevFormatError):
        parse_probability({"result": "yes"})

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={"answers": [{"id": "buy", "probability": 0.7}]})

    scorer = JevScorer("k3y", url="https://jev.test/v1/systemone", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert scorer.score([state, state]).tolist() == [0.7, 0.7]
    assert seen["auth"] == "Bearer k3y" and scorer.latency_summary()["calls"] == 2
