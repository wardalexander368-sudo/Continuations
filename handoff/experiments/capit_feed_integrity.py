"""Offline CAPIT feed/cursor diagnostic; synthetic evidence, never a trading fix.

Run from any directory: python /path/to/repo/handoff/experiments/capit_feed_integrity.py
Optional --output writes only the requested JSON artifact. No bot book, accounts,
orders, keys, data cache, or network endpoints are read or written. The strategy's
real HTTP-response conversion and step are exercised with an in-memory transport.

The original-cursor counterfactual measures information discarded by advancing
the shared cursor. It is not a proposal to send late orders or backfill forward
trades. A missing entry candle is explicitly skipped by the current strategy;
404 is explicitly treated as a delisted pair. The probe distinguishes transient
restoration from persistent unavailability without claiming a production event.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

# Portable in the existing CI sparse checkout: no handoff/data fixture required.
REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tartar.autotrade import health  # noqa: E402
from tartar.autotrade.core import Context  # noqa: E402
from tartar.autotrade.strategies import coinbase_pattern as cp  # noqa: E402

H0, N_HOURS, CRASH_AT = 500_000, 260, 200
SIGNAL_HOUR = H0 + CRASH_AT
INITIAL_CURSOR = SIGNAL_HOUR - 1
FIRST_NOW = (SIGNAL_HOUR + 2) * 3600 + 1200
RECOVERY_NOW = FIRST_NOW + 3600
ENTRY_BAR_START = (SIGNAL_HOUR + 1) * 3600 + cp.G
MODES = (
    "complete",
    "transient_404",
    "transient_200_empty",
    "missing_entry_bar",
    "no_signal",
    "intentional_unavailable",
)


def bars(*, crash: bool) -> list[list[float]]:
    """Independent, deterministic OHLCV fixture: gentle variation, optional 40% crash.

    The no-signal control varies gently rather than having identically zero
    volatility (which is a separate boundary condition in the CAPIT formula).
    Distinct O/H/L/C values also exercise Coinbase's wire-field conversion.
    """
    rows = []
    for k in range(N_HOURS * 4):
        h = k // 4
        px = 100 * (1 + (k % 11 - 5) * 0.0004)
        if crash and h >= CRASH_AT:
            px = 60.0 if h == CRASH_AT else 63.0
        rows.append([(H0 * 4 + k) * cp.G, px - 0.01, px + 0.02, px - 0.03, px, 1.0])
    return rows


class _Response:
    def __init__(self, status: int, rows: list):
        self.status_code, self.rows = status, rows

    def json(self):
        # Coinbase Exchange: timestamp, low, high, open, close, volume.
        return [[t, lo, hi, op, cl, v] for t, op, hi, lo, cl, v in reversed(self.rows)]

    def raise_for_status(self):
        raise AssertionError(f"unexpected response branch: {self.status_code}")


class _Http:
    """Only permits the two synthetic candle URLs; no socket/client is created."""

    def __init__(self, mode: str):
        if mode not in MODES:
            raise ValueError(f"unknown diagnostic mode: {mode}")
        self.mode = mode
        self.rows = bars(crash=mode != "no_signal")
        self.requests: list[dict] = []

    def get(self, url: str, *, params: dict):
        allowed = {f"{cp.CB}/products/{coin}-USD/candles": coin for coin in ("BTC", "ETH")}
        if url not in allowed or params["granularity"] != cp.G:
            raise AssertionError(f"unexpected diagnostic request: {url}")
        coin = allowed[url]
        start = int(datetime.fromisoformat(params["start"]).timestamp())
        end = int(datetime.fromisoformat(params["end"]).timestamp())
        rows = [r for r in self.rows if start <= r[0] <= end]
        status = 200
        if coin == "BTC":
            if self.mode in ("transient_404", "intentional_unavailable"):
                status, rows = 404, []
            elif self.mode == "transient_200_empty":
                rows = []
            elif self.mode == "missing_entry_bar":
                rows = [r for r in rows if r[0] != ENTRY_BAR_START]
        self.requests.append({"coin": coin, "status_code": status, "wire_rows": len(rows),
                              "start": start, "end_inclusive": end})
        return _Response(status, rows)


class _MemoryPath:
    """Minimal read-only Path protocol for health.check_agent's synthetic book."""

    def __init__(self, files: dict[str, str], name: str = ""):
        self.files, self.name = files, name

    def __truediv__(self, name: str):
        return _MemoryPath(self.files, name)

    def exists(self):
        return self.name in self.files

    def read_text(self):
        return self.files[self.name]


def agent_health(data: dict, now: int, *, strategy_errors: int = 0) -> list[dict]:
    """Real check_agent, with a constructed recent/no-error state, entirely in memory.

    This does not run health.run, its other checks, or runner.run_once. Green here
    describes check_agent's observability given these inputs, not global health.
    """
    state = {"last_run": {"at": now}, "strategies": {
        "us_capit": {"status": "paper", "errors": strategy_errors, "data": copy.deepcopy(data)}}}
    if strategy_errors:
        state["strategies"]["us_capit"]["last_error"] = "synthetic diagnostic error"
    root = _MemoryPath({"state.json": json.dumps(state)})
    return health.check_agent(root, now)


def _step(strategy: cp.CoinbasePattern, data: dict, now: int, mode: str) -> dict:
    http = _Http(mode)
    before = data["done_hour"]
    # All positions are deliberately empty: this isolates signal discovery and
    # cursor handling, avoiding the ledger, risk layer, mirror, and order routes.
    intents = strategy.step(Context(now, [], data, {}, http))
    return {
        "now": now,
        "source_mode": mode,
        "done_hour_before": before,
        "done_hour_after": data["done_hour"],
        "open_intents": [{"key": i.meta["key"], "coin": i.asset, "at": i.at, "price": i.price}
                         for i in intents if i.kind == "open"],
        "other_intent_count": sum(i.kind != "open" for i in intents),
        "http_requests": http.requests,
        "state_keys": sorted(data),
        "check_agent_items": agent_health(data, now),
        "step_exception": None,
    }


def _strategy() -> cp.CoinbasePattern:
    return cp.CoinbasePattern("us_capit", {"coins": ["BTC", "ETH"], "rule": "capit",
        "start": "2000-01-01", "end": "2100-01-01", "delay_bars": 2, "size_usd": 100})


def scenario(mode: str) -> dict:
    """Three comparisons: first look, later recovery, recovery from original cursor."""
    if mode not in MODES:
        raise ValueError(f"unknown diagnostic mode: {mode}")
    recovery_mode = mode if mode in ("no_signal", "intentional_unavailable") else "complete"
    data = {"done_hour": INITIAL_CURSOR}
    # Restore pre-existing global cache and sleep function even on exceptions.
    # Isolate the counterfactual from the first/recovery comparison's own cache.
    with patch.dict(cp._CACHE, {}, clear=True), patch.object(cp.time, "sleep", lambda _: None):
        strategy = _strategy()
        first = _step(strategy, data, FIRST_NOW, mode)
        recovery = _step(strategy, data, RECOVERY_NOW, recovery_mode)
        with patch.dict(cp._CACHE, {}, clear=True):
            counterfactual = _step(_strategy(), {"done_hour": INITIAL_CURSOR}, RECOVERY_NOW, recovery_mode)
    observed = {i["key"] for step in (first, recovery) for i in step["open_intents"]}
    expected = {i["key"] for i in counterfactual["open_intents"]}
    return {
        "mode": mode,
        "first": first,
        "recovery": recovery,
        "original_cursor_counterfactual": counterfactual,
        "counterfactual_only_signal_keys": sorted(expected - observed),
        "interpretation": "diagnostic information difference; not an executable late trade or observed production loss",
    }


def run_probe() -> dict:
    inputs = [{"name": name, "path": rel, "max_age_seconds": age, "format": how}
              for name, (rel, age, how) in sorted(health.INPUTS.items())]
    return {
        "schema_version": 1,
        "kind": "offline_synthetic_capit_feed_integrity",
        "scope": "real _get/step and check_agent only; no runner, positions, broker, network, or bot-book disk access",
        "fixture": {"coins": ["BTC", "ETH"], "start_hour": H0, "hours": N_HOURS,
                    "crash_hour": SIGNAL_HOUR, "initial_done_hour": INITIAL_CURSOR,
                    "first_now": FIRST_NOW, "recovery_now": RECOVERY_NOW,
                    "missing_entry_bar_start": ENTRY_BAR_START, "delay_15m_bars": 2,
                    "price_pattern": "deterministic 11-bar gentle oscillation; optional 100-to-60 crash then 63"},
        "health_input_inventory": inputs,
        "health_error_detection_control": {
            "constructed_strategy_errors": 1,
            "check_agent_items": agent_health({"done_hour": INITIAL_CURSOR}, FIRST_NOW, strategy_errors=1),
        },
        "has_named_capit_or_coinbase_coverage_input": any(
            any(word in (i["name"] + " " + i["path"]).lower() for word in ("capit", "coinbase", "us-pattern"))
            for i in inputs),
        "scenarios": [scenario(mode) for mode in MODES],
        "limitations": [
            "Synthetic restoration is stipulated; HTTP 404 alone does not prove transient failure or delisting.",
            "Missing entry candles are explicitly skipped by the current implementation; the probe does not change that contract.",
            "check_agent receives constructed recent/no-error state; no claim that all production health checks are green.",
            "No production outage, missed trade, cost, return, profitability, or registered verdict is measured.",
            "No runner persistence, position handling, risk checks, Alpaca mirror, or order execution is tested.",
            "The original-cursor comparison is an offline completeness diagnostic, not authority for historical replay orders.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional JSON artifact path; stdout always contains the same JSON")
    args = parser.parse_args(argv)
    result = json.dumps(run_probe(), indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output is not None:
        # Refuse the actual or synthetic-name bot-book directory at every path
        # level. Resolving also rejects aliases into an autotrade directory.
        output = args.output.resolve()
        if "autotrade" in output.parts:
            parser.error("--output must be outside every autotrade directory")
        output.write_text(result)
    sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
