"""Offline CAPIT episode robustness; exploratory reporting, not a registered scorer.

Requires an already downloaded, SHA-256-verified 11-coin cache. No fetching, orders,
strategy changes or registration writes. Prices are hourly candle closes: enter at
C[h+1] and exit C[h+25], whose timestamps are respectively h+2 and h+26.
Common shifts preserve every coin/time offset in each full-11 episode. Screened-8
uses that same support and episode universe. Shifted controls are mean-return
diagnostics, not executable competing accounts.

    python capit_robustness.py --cache CACHE --output OUTSIDE_CACHE.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from tartar.autotrade.strategies.coinbase_pattern import COINS, signals  # noqa: E402

T0 = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp()) // 3600
T1 = int(datetime(2026, 10, 10, tzinfo=timezone.utc).timestamp()) // 3600
HOLD, GAP, WINDOW, DRAWS, SEED, STAKE = 24, 72, 360, 10000, 1, 100.0
SCREENED = [c for c in COINS if c not in {"AVAX", "BCH", "LTC"}]
EXTRA = ["AAVE", "UNI", "SHIB", "CRV", "GRT", "XTZ", "BAT", "SUSHI", "YFI", "PEPE"]
COSTS = (0.0039, 0.0050)


def _unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _json(raw: bytes):
    return json.loads(raw, object_pairs_hook=_unique_object)


def load_cache(cache: Path) -> tuple[dict, dict[str, tuple[np.ndarray, np.ndarray]]]:
    """Fail closed on incomplete/wrong-window/altered caches; never fill missing prices."""
    cache = cache.resolve()
    raw_manifest = (cache / "manifest.json").read_bytes()
    manifest = _json(raw_manifest)
    if (not isinstance(manifest, dict) or manifest.get("status") != "complete"
            or manifest.get("analysis_ready") is not True):
        raise ValueError("cache manifest status must be complete")
    if manifest.get("start_hour") != T0 or manifest.get("end_hour_exclusive") != T1:
        raise ValueError("cache window must be 2023-01-01 through 2026-10-10 exclusive")
    if (not isinstance(manifest.get("coins"), dict)
            or set(manifest["coins"]) not in (set(COINS), set(COINS + EXTRA))):
        raise ValueError("cache manifest must contain the complete original 11 or 21 coins")
    series = {}
    n = T1 - T0
    for coin in manifest["coins"]:
        info = manifest["coins"][coin]
        if not isinstance(info, dict) or not isinstance(info.get("file"), str):
            raise ValueError(f"{coin}: missing cache file metadata")
        chunks = info.get("planned_chunks")
        validated = info.get("validated_chunks")
        if (isinstance(chunks, bool) or not isinstance(chunks, int) or chunks < 1
                or isinstance(validated, bool) or not isinstance(validated, int) or chunks != validated):
            raise ValueError(f"{coin}: all planned chunks must be validated")
        rel = Path(info["file"])
        path = (cache / rel).resolve()
        if (rel.is_absolute() or cache not in path.parents or rel.name != f"{coin}.json"
                or path == cache / "manifest.json"):
            raise ValueError(f"{coin}: cache file must stay inside cache")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != info.get("sha256"):
            raise ValueError(f"{coin}: SHA-256 mismatch")
        data = _json(raw)
        if not isinstance(data, dict) or info.get("rows") != len(data):
            raise ValueError(f"{coin}: row count mismatch")
        close, volume = np.full(n, np.nan), np.zeros(n)
        for hour, row in data.items():
            try:
                h = int(hour)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{coin}: invalid hour") from exc
            if str(h) != hour or not T0 <= h < T1:
                raise ValueError(f"{coin}: noncanonical or out-of-window hour")
            if (not isinstance(row, list) or len(row) != 2
                    or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in row)
                    or not np.isfinite(row).all() or row[0] <= 0 or row[1] < 0):
                raise ValueError(f"{coin}: close/volume must be finite positive/nonnegative")
            close[h - T0], volume[h - T0] = row
        if info.get("missing_hours") != n - len(data):
            raise ValueError(f"{coin}: missing-hour count mismatch")
        series[coin] = close, volume
    provenance = dict(manifest)
    provenance["manifest_sha256"] = hashlib.sha256(raw_manifest).hexdigest()
    return provenance, series


def forward_gross(close: np.ndarray, hold: int = HOLD) -> np.ndarray:
    """Only finite positive endpoint closes supply a return; missing hours stay missing."""
    close = np.asarray(close, dtype=float)
    if close.ndim != 1 or hold < 1:
        raise ValueError("one-dimensional closes and positive hold required")
    out = np.full(len(close), np.nan)
    size = len(close) - hold - 1
    if size > 0:
        entry, exit_ = close[1:size + 1], close[hold + 1:]
        valid = np.isfinite(entry) & np.isfinite(exit_) & (entry > 0) & (exit_ > 0)
        out[np.flatnonzero(valid)] = exit_[valid] / entry[valid] - 1
    return out


def accepted_hours(signal: np.ndarray, gross: np.ndarray, hold: int = HOLD) -> list[int]:
    """Existing one-position selection: accepting h makes that coin busy until h+H+1."""
    if np.shape(signal) != np.shape(gross) or np.ndim(signal) != 1 or hold < 1:
        raise ValueError("equal one-dimensional signal/return arrays and positive hold required")
    hours, busy = [], -1
    for h in np.flatnonzero(signal):
        if h < busy or not np.isfinite(gross[h]):
            continue
        hours.append(int(h))
        busy = int(h) + hold + 1
    return hours


def assign_episodes(rows: list[dict], gap: int = GAP) -> list[dict]:
    """Chronological connected episodes, fixed before filtering the coin universe."""
    if gap < 0:
        raise ValueError("episode gap must be nonnegative")
    ordered = sorted(rows, key=lambda r: (r["signal_index"], r["coin"]))
    out, episode, previous = [], -1, None
    for row in ordered:
        h = row["signal_index"]
        if previous is None or h - previous > gap:
            episode += 1
        out.append({**row, "episode_id": episode})
        previous = h
    return out


def matched_controls(closes: dict[str, np.ndarray], rows: list[dict],
                     window: int = WINDOW, hold: int = HOLD) -> tuple[list[dict], list[dict]]:
    """Enumerate exact common episode shifts; no independent coin shifts or outcome filters."""
    if window < 0 or hold < 1:
        raise ValueError("nonnegative shift window and positive hold required")
    groups = defaultdict(list)
    for row in rows:
        groups[row["episode_id"]].append(row)
    updated, episodes = [], []
    for episode, group in sorted(groups.items()):
        shifts = np.arange(-window, window + 1)
        valid = np.ones(len(shifts), dtype=bool)
        for row in group:
            close = np.asarray(closes[row["coin"]], dtype=float)
            entry = row["signal_index"] + shifts + 1
            exit_ = entry + hold
            inside = (entry >= 0) & (exit_ < len(close))
            ok = np.zeros(len(shifts), dtype=bool)
            ok[inside] = (np.isfinite(close[entry[inside]]) & np.isfinite(close[exit_[inside]])
                          & (close[entry[inside]] > 0) & (close[exit_[inside]] > 0))
            valid &= ok
        support = shifts[valid]
        if not len(support) or 0 not in support:
            raise ValueError(f"episode {episode}: actual zero shift must remain in common support")
        episodes.append({"episode_id": episode, "trades": len(group),
                         "first_signal_index": min(r["signal_index"] for r in group),
                         "last_signal_index": max(r["signal_index"] for r in group),
                         "support_count": len(support), "valid_shift_hours": support.tolist()})
        for row in group:
            close = np.asarray(closes[row["coin"]], dtype=float)
            entry = row["signal_index"] + support + 1
            expected = float(np.mean(close[entry + hold] / close[entry] - 1))
            updated.append({**row, "expected_control_gross": expected,
                            "gross_excess": float(row["gross_return"] - expected)})
    return sorted(updated, key=lambda r: (r["signal_index"], r["coin"])), episodes


def select_universe(rows: list[dict], coins: list[str]) -> list[dict]:
    """Filter only after full-universe episodes and control expectations are fixed."""
    return [dict(row) for row in rows if row["coin"] in set(coins)]


def episode_bootstrap(values: list[float], labels: list[int], episode_ids: list[int],
                      draws: int = DRAWS, seed: int = SEED) -> dict:
    """Trade-weighted whole-episode mean; undefined draws remain undefined, never zero."""
    if len(values) != len(labels) or draws < 1 or len(set(episode_ids)) != len(episode_ids):
        raise ValueError("matching values/labels, positive draws and unique episode IDs required")
    if not set(labels).issubset(episode_ids) or not np.isfinite(values).all():
        raise ValueError("finite values and labels in the fixed episode universe required")
    by_sum, by_count = defaultdict(float), defaultdict(int)
    for value, label in zip(values, labels):
        by_sum[label] += float(value)
        by_count[label] += 1
    result = {"mean": float(np.mean(values)) if values else None, "ci90": [None, None],
              "requested_draws": draws, "draws_generated": 0, "defined_draws": 0,
              "undefined_draws": 0, "seed": seed, "resampling_episodes": len(episode_ids),
              "interval_condition": "quantiles over draws with nonzero trade count"}
    if not episode_ids:
        return result
    sums = np.array([by_sum[k] for k in episode_ids])
    counts = np.array([by_count[k] for k in episode_ids])
    pick = np.random.default_rng(seed).integers(0, len(episode_ids), (draws, len(episode_ids)))
    denominators = counts[pick].sum(axis=1)
    ok = denominators > 0
    result.update(draws_generated=draws, defined_draws=int(ok.sum()), undefined_draws=int((~ok).sum()))
    if ok.any():
        means = sums[pick].sum(axis=1)[ok] / denominators[ok]
        result["ci90"] = np.percentile(means, [5, 95]).tolist()
    return result


def leave_one_episode_out(rows: list[dict], episode_ids: list[int], cost: float) -> list[dict]:
    out = []
    for episode in episode_ids:
        residual = [r for r in rows if r["episode_id"] != episode]
        out.append({"omitted_episode_id": episode, "removed_trades": len(rows) - len(residual),
                    "remaining_trades": len(residual),
                    "mean_model_net": float(np.mean([r["gross_return"] - 2 * cost for r in residual])) if residual else None,
                    "mean_excess": float(np.mean([r["gross_excess"] for r in residual])) if residual else None})
    return out


def peak_positions(rows: list[dict], hold: int = HOLD) -> int:
    """Actual hourly close timestamps, with exits processed before entries at a tie."""
    events = [(r["signal_index"] + 2, 1) for r in rows]
    events += [(r["signal_index"] + hold + 2, -1) for r in rows]
    count = peak = 0
    for _, change in sorted(events):
        count += change
        peak = max(peak, count)
    return peak


def summarize(rows: list[dict], episode_ids: list[int], universe: str, cost: float) -> dict:
    labels = [r["episode_id"] for r in rows]
    gross = [r["gross_return"] for r in rows]
    net = [r - 2 * cost for r in gross]
    excess = [r["gross_excess"] for r in rows]
    loo = leave_one_episode_out(rows, episode_ids, cost)
    weakest = {}
    for metric in ("mean_model_net", "mean_excess"):
        defined = [r for r in loo if r[metric] is not None]
        weakest[metric] = min(defined, key=lambda r: (r[metric], r["omitted_episode_id"])) if defined else None
    peak = peak_positions(rows)
    return {"universe": universe, "cost_per_side": cost, "trades": len(rows),
            "represented_episodes": len(set(labels)), "full_11_episodes": len(episode_ids),
            "mean_gross": float(np.mean(gross)) if rows else None,
            "mean_model_net": float(np.mean(net)) if rows else None,
            "mean_control_model_net": float(np.mean([r["expected_control_gross"] - 2 * cost for r in rows])) if rows else None,
            "mean_excess": float(np.mean(excess)) if rows else None,
            "net_episode_bootstrap": episode_bootstrap(net, labels, episode_ids),
            "excess_episode_bootstrap": episode_bootstrap(excess, labels, episode_ids),
            "leave_one_episode_out": loo, "weakest_residual": weakest,
            "fixed_stake_usd": STAKE, "realized_model_net_usd": float(STAKE * sum(net)),
            "peak_concurrent_positions": peak, "peak_open_notional_usd": peak * STAKE}


def analyze(provenance: dict, series: dict[str, tuple[np.ndarray, np.ndarray]]) -> dict:
    rows = []
    for coin in COINS:
        close, volume = series[coin]
        gross = forward_gross(close)
        hs = accepted_hours(signals("capit", close, volume), gross)
        rows.extend({"coin": coin, "signal_index": h, "gross_return": float(gross[h])} for h in hs)
    controlled, episodes = matched_controls({c: series[c][0] for c in COINS}, assign_episodes(rows))
    episode_ids = [r["episode_id"] for r in episodes]
    summaries = [summarize(select_universe(controlled, coins), episode_ids, universe, cost)
                 for universe, coins in (("study_11", COINS), ("snapshot_screened_8", SCREENED)) for cost in COSTS]
    return {"analysis_id": "capit-route-robustness-20261013", "status": "complete",
            "classification": "exploratory robustness of previously explored history; not untouched forward validation",
            "cache_manifest": provenance,
            "method": {"rule": "existing CAPIT Z=4 H=24", "hold_hours": HOLD,
                       "episode_gap_hours": GAP, "common_shift_window_hours": WINDOW,
                       "cost_formula": "gross - 2 * cost_per_side; additive proxy, not observed Alpaca fills",
                       "entry_index": "h+1", "exit_index": "h+25",
                       "entry_close_hour": "h+2", "exit_close_hour": "h+26",
                       "support": "full11 common finite-positive endpoints, including zero and actual signals",
                       "screen": "static AVAX/BCH/LTC exclusion using prior quote snapshot; not dynamic historical eligibility",
                       "bootstrap": "fixed full11 episode universe; empty subset clusters have zero sums/counts; undefined draws reported and excluded only from conditional quantiles",
                       "cash": "fixed $100 per trade, no reinvestment, stops, borrowing or control-account simulation"},
            "episodes": episodes,
            "trades": [{**r, "signal_hour": T0 + r["signal_index"],
                        "entry_close_hour": T0 + r["signal_index"] + 2,
                        "exit_close_hour": T0 + r["signal_index"] + 26} for r in controlled],
            "summaries": summaries,
            "limits": ["hourly timing proxy differs from registered 30-minute entry and actual fill latency",
                       "historical screen and costs are proxies; no observed Alpaca execution profitability",
                       "episode bootstrap does not prove episodes statistically independent",
                       "shifted episodes can overlap: controls are not a runnable account",
                       "realized model dollars exclude reinvestment, account stops and idle-capital opportunity cost"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        cache, output = args.cache.resolve(), args.output.resolve()
        if output == cache or cache in output.parents:
            raise ValueError("output must be outside read-only cache")
        provenance, series = load_cache(cache)
        result = analyze(provenance, series)
        payload = json.dumps(result, indent=2, allow_nan=False) + "\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".tmp")
        try:
            temporary.write_text(payload)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    except (ValueError, OSError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
