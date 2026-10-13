"""Offline, fixed-cohort CAPIT cash-account controls; not an executable route/scorer.

Requires the verified existing cache and saved cohort/protocol; fetches nothing.
The received-asset fee model and cash/stops apply identically to all accounts.
Closed-P&L drawdown excludes intratrade and intrahour mark-to-market risk.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capit_robustness import COINS, T0, T1, load_cache  # noqa: E402

LOCKED_COHORT_SHA256 = "3b8209549c3af7105440b322a151a32c5506f03aa662a81b13004e64a4b968e2"
LOCKED_PROTOCOL_SHA256 = "de993555d9aeb0621eb06c4b5ceb2d5653050d2f086e3b0407a84f3355b16cd9"


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _constant(value):
    raise ValueError(f"nonstandard JSON constant: {value}")


def read_json(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=_object, parse_constant=_constant)


@dataclass(frozen=True)
class Policy:
    cash: float = 1500.0
    stake: float = 100.0
    cap: float = 1100.0
    fee: float = 0.0025
    budget: float = 0.0039
    loss_stop: float = 250.0
    min_days: int = 5
    mean_stop: float = -0.038

    def __post_init__(self):
        values = (self.cash, self.stake, self.cap, self.fee, self.budget, self.loss_stop, self.mean_stop)
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in values):
            raise ValueError("finite numeric account policy required")
        if min(self.cash, self.stake, self.cap, self.loss_stop) <= 0 or not 0 <= self.fee <= self.budget < 1:
            raise ValueError("positive cash/stake/cap/stop and 0<=fee<=budget<1 required")
        if isinstance(self.min_days, bool) or not isinstance(self.min_days, int) or self.min_days < 1:
            raise ValueError("positive integer min_days required")


def validate_rows(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty cohort required")
    seen, slots = set(), set()
    for r in rows:
        if not isinstance(r, dict) or r.get("coin") not in COINS:
            raise ValueError("study coin required")
        for key in ("cohort_id", "signal_index", "episode_id"):
            if isinstance(r.get(key), bool) or not isinstance(r.get(key), int) or r[key] < 0:
                raise ValueError(f"nonnegative integer {key} required")
        slot = (r["coin"], r["signal_index"])
        if r["cohort_id"] in seen or slot in slots:
            raise ValueError("duplicate cohort identity or coin/signal opportunity")
        seen.add(r["cohort_id"]); slots.add(slot)


def supports(closes, rows, delays=(1, 2), hold=24, window=360):
    """Full11 common endpoint support for BOTH delays; never filter on returns."""
    validate_rows(rows)
    if hold < 1 or window < 0 or any(not isinstance(d, int) or isinstance(d, bool) or d < 1 for d in delays):
        raise ValueError("positive hold/delays and nonnegative window required")
    groups = defaultdict(list)
    for r in rows:
        groups[r["episode_id"]].append(r)
    out = {}
    for eid, group in sorted(groups.items()):
        shifts = np.arange(-window, window + 1)
        valid = np.ones(len(shifts), dtype=bool)
        for r in group:
            for delay in delays:
                entry = r["signal_index"] + shifts + delay
                exit_ = entry + hold
                close = np.asarray(closes[r["coin"]], dtype=float)
                inside = (entry >= 0) & (exit_ < len(close))
                ok = np.zeros(len(shifts), dtype=bool)
                ok[inside] = (np.isfinite(close[entry[inside]]) & np.isfinite(close[exit_[inside]])
                              & (close[entry[inside]] > 0) & (close[exit_[inside]] > 0))
                valid &= ok
        out[eid] = shifts[valid]
        if 0 not in out[eid]:
            raise ValueError(f"episode {eid}: actual zero shift unavailable; account comparison non-evaluable")
    return out


def sampled_shifts(support, draws=10000, seed=61013):
    if draws < 1 or not support:
        raise ValueError("positive draws and nonempty support required")
    rng = np.random.default_rng(seed)
    eids = sorted(support)
    result = np.empty((draws, len(eids)), dtype=np.int32)
    for col, eid in enumerate(eids):
        result[:, col] = support[eid][rng.integers(0, len(support[eid]), size=draws)]
    return eids, result


def account(closes, rows, shifts, delay, policy=Policy(), hold=24, trace=False):
    """Process full cash account, exits before entries, deterministic coin priority.

    Stops use cumulative net realized P&L and completed accepted UTC signal days.
    A stop blocks new entries, while scheduled exits always continue.
    """
    validate_rows(rows)
    if isinstance(delay, bool) or not isinstance(delay, int) or delay < 1 or hold < 1:
        raise ValueError("positive integer delay/hold required")
    events = defaultdict(lambda: {"entry": [], "exit": []})
    for r in rows:
        offset = shifts[r["episode_id"]]
        if isinstance(offset, bool) or not isinstance(offset, (int, np.integer)):
            raise ValueError("integer shift required")
        h = r["signal_index"] + int(offset)
        e, x = h + delay, h + delay + hold
        close = closes[r["coin"]]
        if not 0 <= e <= x < len(close) or not all(math.isfinite(float(close[i])) and close[i] > 0 for i in (e, x)):
            raise ValueError("missing, invalid or out-of-range execution price")
        row = {**r, "entry_index": e, "exit_index": x, "signal_day": (T0 + h) // 24}
        events[e]["entry"].append(row); events[x]["exit"].append(row)
    cash, min_cash, realized, peak_realized, max_closed_dd = policy.cash, policy.cash, 0.0, 0.0, 0.0
    positions, coins, active_days, entered_days = {}, set(), Counter(), set()
    counts, executed, peak_open, halted, halt_index, history = Counter(), 0, 0, None, None, []
    friction = policy.budget - policy.fee
    for at, ev in sorted(events.items()):
        for r in ev["exit"]:
            p = positions.pop(r["cohort_id"], None)
            if p is None:
                continue
            credit = p["quantity"] * float(closes[r["coin"]][at]) * (1 - friction) * (1 - policy.fee)
            cash += credit; realized += credit - policy.stake
            coins.remove(r["coin"]); active_days[r["signal_day"]] -= 1
            if trace:
                history.append({"event": "exit", "cohort_id": r["cohort_id"], "at_index": at,
                                "credit_usd": credit, "cash_usd": cash, "net_usd": credit - policy.stake})
        peak_realized = max(peak_realized, realized)
        max_closed_dd = max(max_closed_dd, peak_realized - realized)
        completed = sum(active_days[d] == 0 for d in entered_days)
        closed = executed - len(positions)
        if halted is None and (realized <= -policy.loss_stop or
                (completed >= policy.min_days and closed and realized / (closed * policy.stake) < policy.mean_stop)):
            halted = "cumulative_net_loss" if realized <= -policy.loss_stop else "mean_after_completed_days"
            halt_index = at
        for r in sorted(ev["entry"], key=lambda z: (COINS.index(z["coin"]), z["cohort_id"])):
            reason = ("halted" if halted else "coin_busy" if r["coin"] in coins else
                      "open_stake_cap" if (len(positions) + 1) * policy.stake > policy.cap + 1e-9 else
                      "cash" if cash < policy.stake - 1e-9 else None)
            if reason:
                counts[reason] += 1
                if trace:
                    history.append({"event": "rejected", "cohort_id": r["cohort_id"], "at_index": at, "reason": reason})
                continue
            quantity = policy.stake / (float(closes[r["coin"]][at]) * (1 + friction)) * (1 - policy.fee)
            positions[r["cohort_id"]] = {"quantity": quantity}
            coins.add(r["coin"]); entered_days.add(r["signal_day"]); active_days[r["signal_day"]] += 1
            cash -= policy.stake; executed += 1
            min_cash = min(min_cash, cash); peak_open = max(peak_open, len(positions))
            if trace:
                history.append({"event": "entry", "cohort_id": r["cohort_id"], "at_index": at,
                                "quantity": quantity, "cash_usd": cash})
    if positions or min_cash < -1e-7 or not math.isclose(cash - policy.cash, realized, abs_tol=1e-7):
        raise ValueError("cash reconciliation/open-position invariant failed")
    out = {"candidates": len(rows), "executed": executed, "rejected": dict(sorted(counts.items())),
           "terminal_cash_usd": cash, "net_pnl_usd": realized, "minimum_cash_usd": min_cash,
           "peak_open_original_stakes_usd": peak_open * policy.stake,
           "closed_pnl_drawdown_usd": max_closed_dd, "completed_signal_days": len(entered_days),
           "halt_reason": halted, "halt_index": halt_index,
           "mean_closed_net_return": realized / (executed * policy.stake) if executed else None,
           "account_return": realized / policy.cash,
           "full_window_cagr_equivalent": (cash / policy.cash) ** (365.25 * 24 / (T1 - T0)) - 1}
    if trace:
        out["events"] = history
    return out


def analyze(protocol, cohort, provenance, series):
    rows = cohort["trades"]
    if len(rows) != 71 or set(r["episode_id"] for r in rows) != set(range(22)):
        raise ValueError("fixed71/22 input cohort required")
    closes = {c: series[c][0] for c in COINS}
    support = supports(closes, rows, delays=protocol['entry_delays_hours'], hold=protocol['hold_hours'])
    eids, matrix = sampled_shifts(support, protocol["control_draws"], protocol["control_seed"])
    actual_shift = {e: 0 for e in eids}
    summaries, replicates = [], {}
    for universe, coins in protocol["universes"].items():
        subset = [r for r in rows if r["coin"] in coins]
        for delay in protocol["entry_delays_hours"]:
            for budget in protocol["effective_side_budgets"]:
                policy = Policy(cash=protocol["starting_cash_usd"], stake=protocol["stake_cash_debit_usd"],
                                cap=protocol["max_open_original_stakes_usd"], fee=protocol["taker_fee_fraction"],
                                budget=budget, loss_stop=protocol["realized_loss_stop_usd"],
                                min_days=protocol["mean_stop"]["completed_signal_utc_days"],
                                mean_stop=protocol["mean_stop"]["mean_closed_net_return_below"])
                label = f"{universe}:delay{delay}:side{budget}"
                actual = account(closes, subset, actual_shift, delay, policy, hold=protocol['hold_hours'], trace=True)
                draws = [account(closes, subset, dict(zip(eids, vector)), delay, policy, hold=protocol['hold_hours']) for vector in matrix]
                pnl = np.array([r["net_pnl_usd"] for r in draws])
                summaries.append({"line": label, "universe": universe, "delay_hours": delay, "side_budget": budget,
                                  "actual": actual,
                                  "control_reference": {"draws": len(draws), "mean_net_usd": float(pnl.mean()),
                                      "net_usd_q05_q50_q95": np.percentile(pnl, [5, 50, 95]).tolist(),
                                      "actual_minus_control_mean_usd": float(actual["net_pnl_usd"] - pnl.mean()),
                                      "share_controls_at_least_actual": float(np.mean(pnl >= actual["net_pnl_usd"])),
                                      "mean_executed": float(np.mean([r["executed"] for r in draws])),
                                      "halt_counts": dict(Counter(r["halt_reason"] or "none" for r in draws)),
                                      "rejected_totals": dict(sum((Counter(r["rejected"]) for r in draws), Counter()))}})
                replicates[label] = draws
    return {"analysis_id": protocol["analysis_id"], "status": "complete", "protocol": protocol,
            "provenance": {"cache_manifest_sha256": provenance["manifest_sha256"],
                           "source_cohort_analysis_sha256": cohort["source_sha256"], "numpy_version": np.__version__},
            "episode_support": [{"episode_id": e, "count": len(support[e]), "shifts": support[e].tolist()} for e in eids],
            "shared_shift_matrix_sha256_le_int32": hashlib.sha256(matrix.astype('<i4').tobytes()).hexdigest(),
            "summaries": summaries, "control_accounts": replicates}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", required=True, type=Path)
    p.add_argument("--cohort", required=True, type=Path)
    p.add_argument("--protocol", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    try:
        cache, output = a.cache.resolve(), a.output.resolve()
        if output == cache or cache in output.parents or output in (a.cohort.resolve(), a.protocol.resolve()):
            raise ValueError("output must not replace cache or inputs")
        if hashlib.sha256(a.protocol.read_bytes()).hexdigest() != LOCKED_PROTOCOL_SHA256:
            raise ValueError('protocol bytes differ from the locked diagnostic')
        if hashlib.sha256(a.cohort.read_bytes()).hexdigest() != LOCKED_COHORT_SHA256:
            raise ValueError('cohort bytes differ from the fixed historical opportunities')
        protocol, cohort = read_json(a.protocol), read_json(a.cohort)
        provenance, series = load_cache(cache)
        result = analyze(protocol, cohort, provenance, series)
        result["provenance"].update(protocol_sha256=hashlib.sha256(a.protocol.read_bytes()).hexdigest(),
                                     cohort_sha256=hashlib.sha256(a.cohort.read_bytes()).hexdigest())
        payload = json.dumps(result, indent=2, allow_nan=False) + "\n"
        temporary = output.with_name(output.name + '.tmp')
        try:
            temporary.write_text(payload)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
