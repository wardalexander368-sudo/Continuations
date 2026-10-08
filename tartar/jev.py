"""TypeSafe's Jev decision model: judgments about new launches, as scores and as features.

Wire format from https://docs.typesafe.ai/api (checked 2026-10-08):
POST https://api.typesafe.ai/v1/systemone with {"state", "model", "questions":
{id: {"type": "noul", "instructions", "criteria": {"true", "false"}}}} returns
{"model", "answers": {id: {"type": "noul", "noul": p}}, "usage"}.

Design, following TypeSafe's guidance (docs.typesafe.ai, model jaggedness page):

* Jev is weak with raw numbers and arithmetic, so code turns the launch's
  numbers into short phrases before they reach the state.
* One narrow judgment per question, all questions in one request (they run
  in parallel and cost less together).
* The judgments code can't make are about the *text*: whether the name copies
  a known brand, looks low-effort, reads as a meme, or uses scam wording.
  Those answers become features for a model trained on real outcomes
  (`decide.LightGBMScorer` with `extra`). The direct "will buying beat the
  costs?" question is kept as a baseline, not as the plan.

Authentication: `TYPESAFE_API_KEY` if set (Bearer header). In a Claude cloud
environment with the key stored as a network secret, the proxy adds the
credentials and no key is needed here.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

DEFAULT_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"

QUESTIONS: dict[str, dict] = {
    "buy": {
        "type": "noul",
        "instructions": (
            "`launch` describes a pump.fun memecoin in its first seconds of trading. If someone buys it now and "
            "sells it 3 minutes later, will they get back more SOL than they paid, after about 3.5% in fees and slippage?"
        ),
        "criteria": {"true": "Selling after 3 minutes returns more than the purchase cost", "false": "It returns the same or less"},
    },
    "copycat": {
        "type": "noul",
        "instructions": "Do `launch.name` or `launch.symbol` copy or imitate an existing well-known coin, company, brand, product or celebrity?",
        "criteria": {"true": "Imitates something that already exists and is well known", "false": "An original name, or a generic word"},
    },
    "low_effort": {
        "type": "noul",
        "instructions": "Do `launch.name` and `launch.symbol` look random, placeholder, test-like or low-effort?",
        "criteria": {"true": "Keyboard mash, 'test', a single letter, or meaningless characters", "false": "A deliberate, readable name"},
    },
    "meme": {
        "type": "noul",
        "instructions": "Is `launch.name` a recognizable internet meme, joke, or currently popular cultural reference?",
        "criteria": {"true": "Refers to a known meme, joke or trend", "false": "No meme or trend reference"},
    },
    "scam_wording": {
        "type": "noul",
        "instructions": "Do `launch.name` or `launch.symbol` use wording typical of scams, such as airdrop, giveaway, official, v2, free, or claim?",
        "criteria": {"true": "Uses scam or impersonation wording", "false": "No such wording"},
    },
}
FEATURES = ("copycat", "low_effort", "meme", "scam_wording")  # judgments used as model features
QUESTION_VERSION = hashlib.sha1(json.dumps(QUESTIONS, sort_keys=True).encode()).hexdigest()[:10]

FLAG_PHRASES = {
    "dev_dumped": "the creator sold almost all of their tokens",
    "dev_selling": "the creator sold over half of their tokens",
    "dev_bag": "the creator still holds a large share of the supply",
    "sniped": "much of the supply was bought in the first 5 seconds (likely bundled)",
    "concentrated": "the top 10 wallets hold most of the supply",
    "collapsed": "the price fell over 90% from its peak",
    "wash_trading": "many trades are quick buy-sell round trips",
    "few_traders": "a handful of wallets make most trades",
    "odd_curve": "the bonding curve is non-standard",
    "serial_rugger": "the creator rugged earlier tokens",
    "serial_launcher": "the creator launched many tokens today",
    "repeat_creator": "the creator launched other tokens before",
    "copycat": "other recent launches use the same name or metadata",
}


class JevFormatError(RuntimeError):
    """The response did not match the documented format."""


def _bucket(value: float, edges: list[tuple[float, str]], missing: str = "unknown") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return missing
    for limit, label in edges:
        if value < limit:
            return label
    return edges[-1][1]


def describe(state: dict) -> dict:
    """The launch as Jev should see it: its text, and its numbers turned into phrases in code."""
    buyers = int(state.get("buyers") or 0)
    rise = state.get("rise_pct")
    return {
        "launch": {
            "name": state.get("name") or "",
            "symbol": state.get("symbol") or "",
            "seconds_since_launch": round(float(state.get("seconds") or 0)),
            "early_buyers": "none" if buyers == 0 else f"{buyers} wallet(s) besides the creator",
            "buying": _bucket(state.get("buy_sol"), [(0.01, "almost none"), (1, "light (under 1 SOL)"), (5, "moderate (1-5 SOL)"), (math.inf, "heavy (over 5 SOL)")]),
            "price_since_launch": _bucket(rise, [(-50, "down sharply"), (-5, "down"), (5, "about flat"), (50, "up"), (math.inf, "up sharply")]),
            "warning_signs": [FLAG_PHRASES.get(f, f) for f in state.get("flags") or []] or ["none detected"],
        }
    }


def build_request(state: dict, model: str = DEFAULT_MODEL, questions: dict | None = None) -> dict:
    return {"state": describe(state), "model": model, "questions": questions or QUESTIONS}


def parse_answers(body: dict, questions: dict | None = None) -> dict[str, float]:
    """{question id: P(yes)} for every Noul question asked."""
    answers = body.get("answers") if isinstance(body, dict) else None
    out = {}
    for qid in questions or QUESTIONS:
        answer = (answers or {}).get(qid)
        value = answer.get("noul") if isinstance(answer, dict) else None
        if not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
            raise JevFormatError(f"no noul for {qid!r} in the response: {str(body)[:300]}")
        out[qid] = float(value)
    return out


class JevClient:
    """Asks Jev about launches, caching answers by mint (and question version) in a JSON-lines file."""

    def __init__(self, *, api_key: str | None = None, url: str | None = None, model: str | None = None, cache: str | Path | None = None, client: httpx.Client | None = None, timeout: float = 10.0, workers: int = 8, retries: int = 4):
        self.url = url or os.environ.get("TYPESAFE_URL") or DEFAULT_URL
        self.model = model or os.environ.get("TYPESAFE_MODEL") or DEFAULT_MODEL
        key = api_key if api_key is not None else os.environ.get("TYPESAFE_API_KEY")
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}  # else the environment's proxy authenticates
        self.client = client or httpx.Client(timeout=timeout, limits=httpx.Limits(max_connections=workers))
        self.workers, self.retries = workers, retries
        self.latencies: list[float] = []
        self.tokens = {"input": 0, "output": 0}
        self.cache_path = Path(cache) if cache else None
        self.cache: dict[str, dict[str, float]] = {}
        if self.cache_path is not None and self.cache_path.exists():
            for line in self.cache_path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row.get("version") == QUESTION_VERSION:
                        self.cache[row["mint"]] = row["answers"]

    def ask(self, state: dict) -> dict[str, float]:
        mint = state.get("mint")
        if mint and mint in self.cache:
            return self.cache[mint]
        body = build_request(state, self.model)
        for attempt in range(self.retries + 1):
            started = time.perf_counter()
            response = self.client.post(self.url, json=body, headers=self.headers)
            if response.status_code in (429, 529) and attempt < self.retries:
                time.sleep(0.5 * 2**attempt)
                continue
            break
        self.latencies.append(time.perf_counter() - started)
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") or {}
        self.tokens["input"] += usage.get("input_tokens", 0)
        self.tokens["output"] += usage.get("output_tokens", 0)
        answers = parse_answers(data)
        if mint:
            self.cache[mint] = answers
            if self.cache_path is not None:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                with self.cache_path.open("a") as out:
                    out.write(json.dumps({"mint": mint, "version": QUESTION_VERSION, "answers": answers}) + "\n")
        return answers

    def ask_many(self, states: list[dict]) -> list[dict[str, float]]:
        if len(states) <= 1:
            return [self.ask(s) for s in states]
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(self.ask, states))

    def features(self, states: list[dict]) -> np.ndarray:
        """The semantic judgments (`FEATURES`) for each state, as a matrix."""
        return np.array([[a[k] for k in FEATURES] for a in self.ask_many(states)], dtype=float)

    def latency_summary(self) -> dict:
        if not self.latencies:
            return {}
        ms = np.array(self.latencies) * 1000
        return {"calls": len(ms), "median_ms": float(np.median(ms)), "p90_ms": float(np.quantile(ms, 0.9)), "max_ms": float(ms.max()), "tokens": dict(self.tokens)}


class JevScorer:
    """Jev's answer to the direct question ("buy") as a launch score."""

    name = "jev (direct question)"

    def __init__(self, client: JevClient | None = None, **kwargs):
        self.client = client or JevClient(**kwargs)

    def score(self, states: list[dict]) -> np.ndarray:
        return np.array([a["buy"] for a in self.client.ask_many(states)])

    @property
    def latencies(self) -> list[float]:
        return self.client.latencies

    def latency_summary(self) -> dict:
        return self.client.latency_summary()
