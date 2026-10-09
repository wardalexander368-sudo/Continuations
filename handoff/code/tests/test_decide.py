"""Launch decisions: causal launch states, scorer evaluation, caching, and the Jev client."""

import json

import httpx
import numpy as np
import pytest

from tartar.data.dataset import load_trade_tokens
from tartar.data.simulate import simulate_raw
from tartar.decide import NUMERIC, CachedScorer, FlagScorer, FunctionScorer, evaluate, launch_states, state_matrix
from tartar.jev import FEATURES, QUESTIONS, JevClient, JevFormatError, JevScorer, build_request, describe, parse_answers
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


def test_jev_request_follows_the_documented_format():
    state = {"mint": "M1", "name": "Dog", "symbol": "DOG", "buyers": 4, "buy_sol": 2.0, "rise_pct": float("nan"), "flags": ["sniped"], "seconds": 20}
    body = build_request(state)
    assert body["model"] == "jev-latest" and set(body["questions"]) == set(QUESTIONS)
    assert all(q["type"] == "noul" and q["instructions"] and set(q["criteria"]) == {"true", "false"} for q in body["questions"].values())
    launch = describe(state)["launch"]
    assert launch["name"] == "Dog" and launch["price_since_launch"] == "unknown" and launch["buying"] == "moderate (1-5 SOL)"
    assert "first 5 seconds" in launch["warning_signs"][0]  # numbers and flags become phrases, not raw values
    answers = {qid: {"type": "noul", "noul": 0.25} for qid in QUESTIONS}
    assert parse_answers({"model": "jev-1.13.0", "answers": answers}) == {qid: 0.25 for qid in QUESTIONS}
    with pytest.raises(JevFormatError):
        parse_answers({"answers": {"buy": {"type": "noul", "noul": 0.4}}})


def test_jev_client_auth_cache_retries_and_features(tmp_path):
    seen = {"calls": 0, "auth": set()}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["calls"] += 1
        seen["auth"].add(request.headers.get("authorization"))
        if seen["calls"] == 1:
            return httpx.Response(429, json={"error": "slow down"})
        name = json.loads(request.content)["state"]["launch"]["name"]
        p = 0.9 if name == "Dog" else 0.1
        return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {q: {"type": "noul", "noul": p} for q in QUESTIONS}, "usage": {"input_tokens": 300, "output_tokens": 20}})

    transport = httpx.MockTransport(handler)
    client = JevClient(api_key="k3y", url="https://jev.test/v1/systemone", client=httpx.Client(transport=transport), cache=tmp_path / "c.jsonl", workers=2, retries=2)
    states = [{"mint": "a", "name": "Dog"}, {"mint": "b", "name": "Cat"}]
    assert JevScorer(client).score(states).tolist() == [0.9, 0.1]
    assert seen["auth"] == {"Bearer k3y"} and client.tokens["input"] == 600
    assert client.features(states).shape == (2, len(FEATURES))  # from the cache, no new calls
    calls = seen["calls"]
    again = JevClient(api_key="", url="https://jev.test/v1/systemone", client=httpx.Client(transport=transport), cache=tmp_path / "c.jsonl")
    assert again.ask({"mint": "a", "name": "Dog"})["buy"] == 0.9 and seen["calls"] == calls
    assert again.headers == {}  # no key: the environment's proxy authenticates


def test_metadata_question_set_and_score_answers():
    from tartar.jev import LAUNCH, METADATA, describe_metadata

    assert LAUNCH.version != METADATA.version and "narrative_unc" in METADATA.columns
    state = {"name": "Boston Bot", "symbol": "BOSTON", "metadata": {"description": "x" * 900, "twitter": "https://x.com/a", "image": "skip me"}}
    launch = describe_metadata(state)["launch"]
    assert set(launch) == {"name", "symbol", "description", "twitter", "website"} and len(launch["description"]) == 600
    body = {"answers": {qid: ({"type": "noul", "noul": 0.2} if q["type"] == "noul" else {"type": "score", "score": 1.5, "confidence": 0.7}) for qid, q in METADATA.questions.items()}}
    answers = parse_answers(body, METADATA)
    assert answers["explains"] == 0.2 and answers["narrative"] == 1.5 and answers["narrative_unc"] == pytest.approx(0.3)
    assert set(answers) == set(METADATA.columns)
    with pytest.raises(JevFormatError):
        parse_answers({"answers": {"narrative": {"type": "score", "score": 1.0}}}, {"narrative": METADATA.questions["narrative"]})


def test_metadata_urls_and_link_features():
    from tartar.metadata import LINK_FEATURES, candidate_urls, link_features

    assert candidate_urls("https://ipfs.io/ipfs/QmAbc")[0] == "https://pump.mypinata.cloud/ipfs/QmAbc"
    assert candidate_urls("ipfs://bafyX")[0].endswith("/ipfs/bafyX")
    assert candidate_urls("https://meta.uxento.io/x.json") == ["https://meta.uxento.io/x.json"]
    assert candidate_urls("") == []
    f = link_features({"description": "a real token", "twitter": "https://x.com/u/status/1", "website": "https://www.instagram.com/p/1"}, "https://meta.uxento.io/x")
    assert f["desc_words"] == 3 and f["twitter_is_post"] == 1 and f["website_is_social"] == 1 and f["tool_uri"] == 1
    assert link_features(None)["meta_found"] == 0 and tuple(link_features(None)) == LINK_FEATURES
