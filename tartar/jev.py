"""TypeSafe's Jev decision model as a launch scorer.

Jev takes a state and typed questions and returns calibrated probabilities.
Here the state is a launch snapshot from `decide.launch_states` and the
question is yes/no: is buying now worth more than the round-trip cost?

UNVERIFIED REQUEST FORMAT. This was written without access to
docs.typesafe.ai (unreachable from the session that wrote it), from public
summaries: POST https://api.typesafe.ai/v1/systemone, Bearer auth, a yes/no
("noul") question answered with a probability. `build_request` and
`parse_probability` are the only places that know the wire format. Check
them against TypeSafe's OpenAPI spec before trusting any result.
`parse_probability` raises `JevFormatError` with the raw response instead of
guessing.

Configuration: `TYPESAFE_API_KEY` (required), `TYPESAFE_URL` (endpoint
override, e.g. a gateway), `TYPESAFE_MODEL` (model id, if the endpoint wants one).
"""

from __future__ import annotations

import math
import os
import time

import httpx
import numpy as np

DEFAULT_URL = "https://api.typesafe.ai/v1/systemone"
QUESTION = (
    "This pump.fun token launched {seconds:g} seconds ago. If we buy now and sell {horizon}, "
    "will we get back more than we paid after about 3.5% in fees and slippage?"
)
STATE_KEYS = (
    "name", "symbol", "buyers", "trades", "buy_sol", "sell_sol", "rise_pct", "raised_sol", "creator_sold_share",
    "creator_launches", "creator_rugs", "drawdown_pct", "top10_share", "holders", "creator_share", "sniper_share",
    "wash_share", "trades_per_wallet", "nonstandard_curve", "risk", "flags",
)  # fmt: skip


class JevFormatError(RuntimeError):
    """The response did not have the shape this client expects (see the module docstring)."""


def _clean(value):
    if isinstance(value, float):
        return None if math.isnan(value) else round(value, 4)
    return value


def build_request(state: dict, horizon: str, model: str | None = None) -> dict:
    body = {
        "state": {key: _clean(state.get(key)) for key in STATE_KEYS},
        "questions": [{"id": "buy", "type": "noul", "question": QUESTION.format(seconds=state.get("seconds", 20), horizon=horizon)}],
    }
    if model:
        body["model"] = model
    return body


def parse_probability(body: dict) -> float:
    """P(yes) for the "buy" question."""
    answers = body.get("answers") if isinstance(body, dict) else None
    if isinstance(answers, dict):
        answers = [dict(answers.get("buy") or {}, id="buy")] if "buy" in answers else None
    for answer in answers or []:
        if isinstance(answer, dict) and answer.get("id", "buy") == "buy":
            p = answer.get("probability", answer.get("p_yes"))
            if isinstance(p, (int, float)) and 0.0 <= p <= 1.0:
                return float(p)
    raise JevFormatError(f"unexpected Jev response (update tartar/jev.py to the documented format): {str(body)[:500]}")


class JevScorer:
    name = "jev"

    def __init__(self, api_key: str, *, url: str | None = None, model: str | None = None, horizon: str = "within 3 minutes", client: httpx.Client | None = None, timeout: float = 10.0):
        self.url = url or os.environ.get("TYPESAFE_URL") or DEFAULT_URL
        self.model = model or os.environ.get("TYPESAFE_MODEL")
        self.horizon = horizon
        self.client = client or httpx.Client(timeout=timeout)
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.latencies: list[float] = []  # seconds per call: decides whether Jev fits a split-second path

    def score_one(self, state: dict) -> float:
        started = time.perf_counter()
        response = self.client.post(self.url, json=build_request(state, self.horizon, self.model), headers=self.headers)
        self.latencies.append(time.perf_counter() - started)
        response.raise_for_status()
        return parse_probability(response.json())

    def score(self, states: list[dict]) -> np.ndarray:
        return np.array([self.score_one(s) for s in states])

    def latency_summary(self) -> dict:
        if not self.latencies:
            return {}
        ms = np.array(self.latencies) * 1000
        return {"calls": len(ms), "median_ms": float(np.median(ms)), "p90_ms": float(np.quantile(ms, 0.9)), "max_ms": float(ms.max())}
