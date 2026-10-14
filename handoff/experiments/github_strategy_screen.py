"""Trusted offline screening of reviewed, hash-pinned public strategy methods.

This module never imports or executes external strategy code. Its first adapter
transcribes constant target-weight rebalancing into cash/share accounting. An
hour-t decision executes at hour t+1's saved close, which is a candle proxy, not
an executable quote. Every outcome is explored history and unvalidated.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

ADAPTER = "constant_weight_rebalance"
ADAPTER_VERSION = 1
PERMISSIVE_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unlicense", "0BSD"}
MAX_HOURS = 40_000
MAX_ASSETS = 16
MAX_INPUT_BYTES = 32 * 1024 * 1024
LIMITATIONS = [
    "Explored historical Coinbase hourly closes; no untouched holdout or official result.",
    "Execution at the next hourly close is a modeled candle proxy, not an executable quote.",
    "Side costs are predeclared modeled all-in allowances charged once per traded notional.",
    "Actual spread, slippage, latency, liquidity, order limits, taxes and account eligibility remain unknown.",
    "No parameter selection, profitability validation, strategy promotion or live authorization.",
    "License and transcription checks are reviewed attestations, not independent legal or fidelity proof.",
]


class ScreenBlocked(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code, self.detail = code, detail


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def code_footprint():
    """Own trusted adapter identity for a durable orchestration fingerprint."""
    return {"adapter": ADAPTER, "adapter_version": ADAPTER_VERSION,
            "path": "handoff/experiments/github_strategy_screen.py", "sha256": _sha(Path(__file__).read_bytes())}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ScreenBlocked("INVALID_JSON", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(data: bytes):
    try:
        return json.loads(data, object_pairs_hook=_pairs, parse_constant=lambda v: (_ for _ in ()).throw(
            ScreenBlocked("INVALID_JSON", f"non-finite JSON constant: {v}")))
    except ScreenBlocked:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ScreenBlocked("INVALID_JSON", str(exc)) from exc


def _keys(value, required, optional=(), label="object"):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ScreenBlocked("INVALID_SPEC", f"{label} has missing or unsupported fields")


def _number(value, label, minimum=0.0, maximum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScreenBlocked("INVALID_SPEC", f"{label} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ScreenBlocked("INVALID_SPEC", f"{label} must be finite") from exc
    if not math.isfinite(number) or number < minimum or (positive and number <= minimum) or (
            maximum is not None and number > maximum):
        raise ScreenBlocked("INVALID_SPEC", f"{label} is outside its finite permitted range")
    return number


def _integer(value, label, minimum=0, maximum=100_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ScreenBlocked("INVALID_SPEC", f"{label} must be a bounded integer")
    return value


def _text(value, label, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ScreenBlocked("INVALID_SPEC", f"{label} must be nonempty bounded text")
    return value


def _relative(value):
    _text(value, "source path", 500)
    if "\\" in value or value.startswith("/") or any(p in {"", ".", ".."} for p in value.split("/")):
        raise ScreenBlocked("UNSAFE_PATH", f"source path must be a plain relative path: {value}")
    return PurePosixPath(value)


def _safe_file(root: Path, relative: str) -> Path:
    parts = _relative(relative).parts
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise ScreenBlocked("UNSAFE_PATH", "artifact root may not be a symlink")
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ScreenBlocked("UNSAFE_PATH", f"symlink artifact forbidden: {relative}")
    if not path.is_file():
        raise ScreenBlocked("MISSING_INPUT", f"missing artifact: {relative}")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ScreenBlocked("INPUT_TOO_LARGE", f"artifact exceeds bounded input size: {relative}")
    return path


def validate_spec(spec: dict) -> dict:
    _keys(spec, {"schema_version", "candidate_id", "source", "review", "method", "protocol"}, label="spec")
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 1:
        raise ScreenBlocked("INVALID_SPEC", "schema_version must be 1")
    if not isinstance(spec["candidate_id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", spec["candidate_id"]):
        raise ScreenBlocked("INVALID_SPEC", "candidate_id must be a plain bounded identifier")
    source = spec["source"]
    _keys(source, {"repo_url", "commit", "files", "license_spdx", "license_file", "license_sha256"}, label="source")
    if not isinstance(source["repo_url"], str) or not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source["repo_url"]):
        raise ScreenBlocked("INVALID_SPEC", "repo_url must name a public GitHub repository")
    if not isinstance(source["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", source["commit"]):
        raise ScreenBlocked("INVALID_SPEC", "source commit must be a full lowercase 40-character SHA")
    if not isinstance(source["license_spdx"], str) or source["license_spdx"] not in PERMISSIVE_LICENSES:
        raise ScreenBlocked("UNSUPPORTED_LICENSE", "license requires a separate reviewed adapter/intake decision")
    _relative(source["license_file"])
    if not isinstance(source["license_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", source["license_sha256"]):
        raise ScreenBlocked("INVALID_SPEC", "license_sha256 must be a lowercase SHA256")
    files = source["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= 32:
        raise ScreenBlocked("INVALID_SPEC", "source.files must contain 1 to 32 pinned files")
    seen = set()
    for item in files:
        _keys(item, {"path", "sha256"}, label="source file")
        _relative(item["path"])
        if item["path"] in seen or not isinstance(item["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ScreenBlocked("INVALID_SPEC", "source files must have unique paths and lowercase SHA256 hashes")
        seen.add(item["path"])
    review = spec["review"]
    _keys(review, {"reviewer", "transcription_checked", "license_checked", "closed_lane_checked", "mechanism_note"}, label="review")
    _text(review["reviewer"], "reviewer", 200)
    _text(review["mechanism_note"], "mechanism_note")
    for field in ("transcription_checked", "license_checked", "closed_lane_checked"):
        if review[field] is not True:
            raise ScreenBlocked("REVIEW_REQUIRED", f"review.{field} must be explicitly true")
    method = spec["method"]
    _keys(method, {"adapter", "weights", "interval_bars"}, {"drift_band"}, label="method")
    if method["adapter"] != ADAPTER:
        raise ScreenBlocked("UNSUPPORTED_ADAPTER", "external source code is never executed; this adapter is unsupported")
    weights = method["weights"]
    if not isinstance(weights, dict) or not 1 <= len(weights) <= MAX_ASSETS:
        raise ScreenBlocked("INVALID_SPEC", "weights must contain 1 to 16 selected assets")
    for asset, weight in weights.items():
        if not isinstance(asset, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{0,14}", asset):
            raise ScreenBlocked("INVALID_SPEC", "asset names must be plain uppercase symbols")
        _number(weight, f"weight.{asset}", maximum=1, positive=True)
    if math.fsum(weights.values()) > 1:
        raise ScreenBlocked("INVALID_SPEC", "target weights must sum to at most 1; remainder is cash")
    _integer(method["interval_bars"], "interval_bars", 1, MAX_HOURS)
    _number(method.get("drift_band", 0), "drift_band", maximum=1)
    protocol = spec["protocol"]
    _keys(protocol, {"capital_usd", "side_cost_bps", "stress_side_cost_bps", "start_hour", "end_hour", "evidence_class", "planned_at"}, label="protocol")
    _number(protocol["capital_usd"], "capital_usd", maximum=1e12, positive=True)
    for field in ("side_cost_bps", "stress_side_cost_bps"):
        _number(protocol[field], field, maximum=9999)
    if protocol["stress_side_cost_bps"] < protocol["side_cost_bps"]:
        raise ScreenBlocked("INVALID_SPEC", "stress cost must be at least the declared base cost")
    start = _integer(protocol["start_hour"], "start_hour")
    end = _integer(protocol["end_hour"], "end_hour")
    if not 2 <= end - start < MAX_HOURS:
        raise ScreenBlocked("INVALID_SPEC", "window needs 3 to 40000 consecutive hourly closes")
    if protocol["evidence_class"] != "explored-history":
        raise ScreenBlocked("INVALID_EVIDENCE_CLASS", "only explored-history is supported; no fresh holdout claim")
    try:
        planned = datetime.fromisoformat(_text(protocol["planned_at"], "planned_at", 100).replace("Z", "+00:00"))
        if planned.tzinfo is None or planned > datetime.now(timezone.utc):
            raise ValueError("planned_at must have a timezone and may not be in the future")
    except ValueError as exc:
        raise ScreenBlocked("INVALID_SPEC", str(exc)) from exc
    return spec


def load_inputs(spec: dict, cache: Path, sources: Path):
    source_hashes = {}
    expected = {row["path"]: row["sha256"] for row in spec["source"]["files"]}
    license_path = spec["source"]["license_file"]
    if license_path in expected and expected[license_path] != spec["source"]["license_sha256"]:
        raise ScreenBlocked("SOURCE_HASH_MISMATCH", "license hash conflicts with the source file pin")
    expected[license_path] = spec["source"]["license_sha256"]
    for relative, digest in expected.items():
        actual = _sha(_safe_file(sources, relative).read_bytes())
        source_hashes[relative] = actual
        if actual != digest:
            raise ScreenBlocked("SOURCE_HASH_MISMATCH", f"source artifact hash mismatch: {relative}")
    protocol = spec["protocol"]
    start, end = protocol["start_hour"], protocol["end_hour"]
    prices, cache_hashes = {}, {}
    for asset in sorted(spec["method"]["weights"]):
        data = _safe_file(cache, f"{asset}.json").read_bytes()
        cache_hashes[f"{asset}.json"] = _sha(data)
        rows = _json(data)
        if not isinstance(rows, dict):
            raise ScreenBlocked("INVALID_CACHE", f"{asset}: expected epoch-hour mapping")
        values = {}
        for hour, row in rows.items():
            if not isinstance(hour, str) or not re.fullmatch(r"0|[1-9][0-9]{0,8}", hour):
                raise ScreenBlocked("INVALID_CACHE", f"{asset}: noncanonical epoch-hour key")
            if not isinstance(row, list) or len(row) != 2:
                raise ScreenBlocked("INVALID_CACHE", f"{asset}: expected [close, volume]")
            close = _number(row[0], f"{asset}.close", positive=True)
            _number(row[1], f"{asset}.volume")
            key = int(hour)
            if start <= key <= end:
                values[key] = close
        missing = [hour for hour in range(start, end + 1) if hour not in values]
        if missing:
            raise ScreenBlocked("MISSING_PRICE_COVERAGE", f"{asset}: {len(missing)} missing hourly prices; first {missing[:5]}; no imputation")
        prices[asset] = values
    return prices, {"cache_sha256": cache_hashes, "source_sha256": source_hashes}


def simulate(prices: dict, method: dict, protocol: dict, side_cost_bps: float, account: str, collect_trades=True):
    """Simulate one funded account; decisions use current/past closes only.

    Trade direction and share quantity are frozen at t using that hour's
    closes. A t+1 buy may be capped by cash available at its proxy fill, but
    never resized upward or reversed. All inventory is liquidated at end.
    """
    if account not in {"strategy", "buy_and_hold", "cash"}:
        raise ValueError("unknown account")
    assets = sorted(method["weights"])
    weights = {asset: float(method["weights"][asset]) for asset in assets}
    target_cash = 1 - math.fsum(weights.values())
    start, end = protocol["start_hour"], protocol["end_hour"]
    capital = _number(protocol["capital_usd"], "capital_usd", maximum=1e12, positive=True)
    cost = _number(side_cost_bps, "side_cost_bps", maximum=9999) / 10000
    cash, shares = capital, dict.fromkeys(assets, 0.0)
    costs, turnover, trade_count, rebalance_count = 0.0, 0.0, 0, 0
    peak, max_drawdown = capital, 0.0
    pending = None
    rows, trades = [], []

    def equity(current):
        value = math.fsum([cash] + [shares[a] * current[a] for a in assets])
        if not math.isfinite(value) or value <= 0:
            raise ScreenBlocked("INCOMPLETE_ACCOUNT", "nonfinite or nonpositive derived account equity")
        return value

    def trade(asset, delta, current, hour, signal_hour, reason):
        nonlocal cash, costs, turnover, trade_count
        notional = abs(delta) * current[asset]
        if not math.isfinite(notional):
            raise ScreenBlocked("INCOMPLETE_ACCOUNT", "nonfinite derived trade notional")
        if notional <= 0 or (reason != "terminal_liquidation" and notional <= 1e-13 * capital):
            return
        if delta > 0:
            # Roundoff may reduce a buy by a few ulps; never borrow for fees.
            notional = min(notional, max(0, cash) / (1 + cost))
            delta = notional / current[asset]
            cash -= notional * (1 + cost)
        else:
            delta = -min(-delta, shares[asset])
            notional = -delta * current[asset]
            cash += notional * (1 - cost)
        if notional <= 0 or (reason != "terminal_liquidation" and notional <= 1e-13 * capital):
            return
        shares[asset] += delta
        fee = notional * cost
        costs += fee
        turnover += notional
        trade_count += 1
        if cash < -1e-10 * capital or shares[asset] < -1e-12 or not math.isfinite(shares[asset]):
            raise ScreenBlocked("INCOMPLETE_ACCOUNT", "cash/share budget invariant failed")
        cash = max(cash, 0.0)
        shares[asset] = max(shares[asset], 0.0)
        if collect_trades:
            trades.append({"hour": hour, "signal_hour": signal_hour, "asset": asset, "side": "BUY" if delta > 0 else "SELL",
                           "share_quantity": abs(delta), "notional_usd": notional, "fee_usd": fee, "reason": reason})

    def intents(current):
        before = equity(current)
        held = {a: shares[a] * current[a] for a in assets}
        # Solve post-fee equity = pre-fee equity - fees on all target changes.
        low, high = 0.0, before
        for _ in range(70):
            mid = (low + high) / 2
            residual = mid + cost * math.fsum(abs(weights[a] * mid - held[a]) for a in assets) - before
            if residual > 0:
                high = mid
            else:
                low = mid
        target_equity = (low + high) / 2
        return {a: (weights[a] * target_equity - held[a]) / current[a] for a in assets}

    for hour in range(start, end + 1):
        current = {a: prices[a][hour] for a in assets}
        executed_signal = None
        if pending is not None and hour < end:
            executed_signal, deltas = pending
            for buying in (False, True):
                for asset in assets:
                    if (deltas[asset] > 0) is buying:
                        trade(asset, deltas[asset], current, hour, executed_signal, "target_rebalance")
            rebalance_count += 1
            pending = None
        if hour == end:
            for asset in assets:
                trade(asset, -shares[asset], current, hour, end - 1, "terminal_liquidation")
            # Zero only numerical dust; trading fees were included above.
            if any(shares[a] * current[a] > 1e-12 * capital for a in assets):
                raise ScreenBlocked("INCOMPLETE_ACCOUNT", "terminal inventory remains")
            shares = dict.fromkeys(assets, 0.0)
        value = equity(current)
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak - value) / peak)
        signal = False
        if account != "cash" and hour + 1 < end:
            if hour == start:
                signal = True
            elif account == "strategy" and (hour - start) % method["interval_bars"] == 0:
                drift = max([abs(shares[a] * current[a] / value - weights[a]) for a in assets]
                            + [abs(cash / value - target_cash)])
                signal = drift >= method.get("drift_band", 0)
            if signal:
                pending = (hour, intents(current))
        rows.append({"hour": hour, "account": account, "cash_usd": cash, "inventory_usd": value - cash,
                     "equity_usd": value, "cumulative_cost_usd": costs, "cumulative_turnover_usd": turnover,
                     "executed_signal_hour": executed_signal, "signal_for_next_hour": signal,
                     "shares": dict(shares)})
    return {"account": account, "initial_capital_usd": capital, "final_cash_usd": cash, "net_usd": cash - capital,
            "net_return_fraction": cash / capital - 1, "max_drawdown_fraction": max_drawdown,
            "modeled_cost_usd": costs, "traded_notional_usd": turnover, "trade_count": trade_count,
            "rebalance_executions": rebalance_count, "terminal_inventory_usd": 0.0}, rows, trades


def _durable_json(path: Path, data: Any):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _event(path: Path, data: Any):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical(data).decode() + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def run_screen(spec_path: Path, cache_dir: Path, sources_dir: Path, output_dir: Path):
    """Create a new, durable offline attempt; never overwrite prior receipts."""
    cache, output = Path(cache_dir), Path(output_dir)
    spec_path, sources_dir = Path(spec_path), Path(sources_dir)
    if output.is_symlink() or any(parent.is_symlink() for parent in output.parents):
        raise ScreenBlocked("UNSAFE_PATH", "output path may not use symlinks")
    output.mkdir(parents=True, exist_ok=False)
    attempt = {"schema_version": 1, "attempted_at": _utc(), "phase": "STARTED", "code_sha256": _sha(Path(__file__).read_bytes()),
               "evidence_class": "explored-history", "outcomes_available": False, "limitations": LIMITATIONS}
    _durable_json(output / "attempt.json", attempt)
    events = output / "attempt-events.jsonl"
    _event(events, attempt)
    try:
        if spec_path.is_symlink() or any(parent.is_symlink() for parent in spec_path.parents) or not spec_path.is_file() or spec_path.stat().st_size > 1_000_000:
            raise ScreenBlocked("UNSAFE_SPEC", "spec must be a bounded regular non-symlink JSON file")
        data = spec_path.read_bytes()
        _event(events, {"phase": "SPEC_HASHED_BEFORE_VALIDATION", "spec_sha256": _sha(data), "outcomes_available": False})
        spec = validate_spec(_json(data))
        prices, hashes = load_inputs(spec, cache, sources_dir)
        receipt = {"schema_version": 1, "phase": "INPUTS_VERIFIED_BEFORE_OUTCOMES", "verified_at": _utc(),
                   "candidate_id": spec["candidate_id"], "spec_sha256": _sha(data), "protocol_sha256": _sha(_canonical(spec["protocol"])),
                   "method_sha256": _sha(_canonical(spec["method"])), "source": spec["source"], "review": spec["review"],
                   "protocol": spec["protocol"], "method": spec["method"], "input_hashes": hashes,
                   "code_sha256": attempt["code_sha256"], "outcomes_available": False, "limitations": LIMITATIONS}
        _durable_json(output / "verified-inputs.json", receipt)
        _event(events, receipt)
        results = {}
        assets = sorted(spec["method"]["weights"])
        fields = ["hour", "account", "cash_usd", "inventory_usd", "equity_usd", "cumulative_cost_usd",
                  "cumulative_turnover_usd", "executed_signal_hour", "signal_for_next_hour"] + [f"shares_{a}" for a in assets]
        for scenario, side_cost in (("base", spec["protocol"]["side_cost_bps"]), ("stress", spec["protocol"]["stress_side_cost_bps"])):
            summaries = {}
            with (output / f"equity-{scenario}.csv").open("x", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fields, lineterminator="\n")
                writer.writeheader()
                for account in ("strategy", "buy_and_hold", "cash"):
                    summary, rows, _ = simulate(prices, spec["method"], spec["protocol"], side_cost, account, collect_trades=False)
                    summaries[account] = summary
                    for row in rows:
                        shares = row.pop("shares")
                        row.update({f"shares_{a}": shares[a] for a in assets})
                        writer.writerow(row)
            strategy = summaries["strategy"]
            results[scenario] = {"side_cost_bps": side_cost, "accounts": summaries,
                                 "strategy_minus_buy_and_hold_usd": strategy["net_usd"] - summaries["buy_and_hold"]["net_usd"],
                                 "strategy_minus_cash_usd": strategy["net_usd"],
                                 "strategy_minus_buy_and_hold_drawdown_fraction": strategy["max_drawdown_fraction"] - summaries["buy_and_hold"]["max_drawdown_fraction"]}
        positive = all(v["strategy_minus_cash_usd"] > 0 and v["strategy_minus_buy_and_hold_usd"] > 0 for v in results.values())
        result = {"schema_version": 1, "candidate_id": spec["candidate_id"], "status": "REVIEW_ONLY" if positive else "FAIL_SCREEN",
                  "completed_at": _utc(), "evidence_class": "explored-history", "validated_profitability": False,
                  "promotion_authorized": False, "scenarios": results, "limitations": LIMITATIONS}
    except ScreenBlocked as exc:
        result = {"schema_version": 1, "status": "BLOCKED", "error_code": exc.code, "detail": exc.detail,
                  "completed_at": _utc(), "validated_profitability": False, "promotion_authorized": False, "limitations": LIMITATIONS}
    except Exception as exc:
        result = {"schema_version": 1, "status": "INCOMPLETE", "error_code": type(exc).__name__, "detail": str(exc),
                  "completed_at": _utc(), "validated_profitability": False, "promotion_authorized": False, "limitations": LIMITATIONS}
    _durable_json(output / "result.json", result)
    _event(events, {"phase": "COMPLETED", "status": result["status"], "completed_at": result["completed_at"],
                    "result_sha256": _sha((output / "result.json").read_bytes())})
    lines = ["# Public GitHub strategy screen", "", f"Status: **{result['status']}**.", "",
             "All outcomes are explored history and unvalidated. Positive screens need independent review and a fresh protocol.", ""]
    if "scenarios" in result:
        for name, values in result["scenarios"].items():
            lines += [f"{name}: modeled side cost {values['side_cost_bps']:g} bp; strategy account net "
                      f"${values['accounts']['strategy']['net_usd']:.2f}; excess over matched buy-and-hold "
                      f"${values['strategy_minus_buy_and_hold_usd']:.2f}; drawdown "
                      f"{values['accounts']['strategy']['max_drawdown_fraction']:.2%}.", ""]
    else:
        lines += [f"{result['error_code']}: {result['detail']}", ""]
    lines += ["Limitations:", ""] + [f"- {item}" for item in LIMITATIONS]
    (output / "REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


# Kept as a short name for callers of the first offline draft.
run = run_screen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("spec", "cache", "sources-dir", "output"):
        parser.add_argument(f"--{flag}", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = run(args.spec, args.cache, args.sources_dir, args.output)
    except (OSError, ScreenBlocked) as exc:
        parser.exit(2, f"Cannot create a durable attempt receipt: {exc}\n")
    print(json.dumps({"status": result["status"], "output": str(args.output), "validated_profitability": False}))
    return 2 if result["status"] in {"BLOCKED", "INCOMPLETE"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
