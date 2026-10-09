"""The slow loop's view of the fast loop: what happened, and what would have happened.

`review` reads the fast loop's journal and, from the raw trades recorded over
the same period, computes what *every* screened launch would have earned if it
had been bought (the counterfactual). That shows:

* the paper result of the policy as run;
* whether the skip rules removed losers or winners;
* whether the scorer's probabilities line up with real outcomes (calibration);
* which threshold would have done best in hindsight (in-sample: a hint for
  the next policy, never proof).
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .profit import Exit, curves_for, label_round_trips


def load_journal(directory: str | Path, since: float | None = None, until: float | None = None) -> list[dict]:
    records = []
    for path in sorted(Path(directory).glob("journal-*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            t = record.get("t", 0.0)
            if (since is None or t >= since) and (until is None or t <= until):
                records.append(record)
    return records


def _boot_mean(values: np.ndarray, boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    if len(values) == 0:
        return math.nan, math.nan
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, len(values), size=(boot, len(values)))].mean(axis=1)
    return float(np.quantile(means, 0.05)), float(np.quantile(means, 0.95))


def _stats(values) -> dict:
    v = np.asarray([x for x in values if x is not None and not math.isnan(x)], dtype=float)
    if len(v) == 0:
        return {"n": 0}
    low, high = _boot_mean(v)
    return {"n": int(len(v)), "mean": float(v.mean()), "ci_low": low, "ci_high": high, "win": float((v > 0).mean())}


def review(records: list[dict], raw_dir: str | Path | None = None, timeframe: int = 60) -> dict:
    """Summary of a journal period, with counterfactual outcomes if `raw_dir` covers it."""
    screens = {r["mint"]: r for r in records if r["e"] == "screen"}
    decisions = {r["mint"]: r for r in records if r["e"] == "decision"}
    exits = [r for r in records if r["e"] == "exit"]
    policies = [r["policy"] for r in records if r["e"] in ("start", "policy")]
    policy = policies[-1] if policies else {}
    out: dict = {
        "period": [min((r["t"] for r in records), default=None), max((r["t"] for r in records), default=None)],
        "policy": policy,
        "policy_changes": max(len(policies) - 1, 0),
        "counts": dict(Counter(r["e"] for r in records)),
        "skips": dict(Counter(r["skip"].split(" ")[0] for r in screens.values() if "skip" in r)),
        "paper": {**_stats([r["ret"] for r in exits]), "total_sol": float(sum(r["pnl_sol"] for r in exits)), "reasons": dict(Counter(r["reason"] for r in exits))},
        "paper_by_kind": {
            kind: {**_stats([r["ret"] for r in exits if r.get("kind", "launch") == kind]), "total_sol": float(sum(r["pnl_sol"] for r in exits if r.get("kind", "launch") == kind))}
            for kind in sorted({r.get("kind", "launch") for r in exits})
        },
        "runups": {"triggered": sum(1 for r in records if r["e"] == "runup"), "skipped": dict(Counter(r["skip"].split(" ")[0] for r in records if r["e"] == "runup" and "skip" in r))},
    }
    latencies = np.array([r["latency_ms"] for r in decisions.values() if r.get("latency_ms") is not None])
    scored = [r for r in decisions.values() if r.get("score") is not None]
    out["scorer"] = {
        "name": next(iter(decisions.values())).get("scorer") if decisions else None,
        "decisions": len(decisions),
        "errors": sum(1 for r in decisions.values() if r.get("error")),
        "latency_ms": {"median": float(np.median(latencies)), "p90": float(np.quantile(latencies, 0.9)), "max": float(latencies.max())} if len(latencies) else {},
        "buy_share": (sum(1 for r in decisions.values() if r.get("buy")) / len(decisions)) if decisions else None,
    }
    if raw_dir is None or not screens:
        return out

    from .data.dataset import load_trade_tokens

    tokens = load_trade_tokens(raw_dir, timeframe)
    index = {t.mint: k for k, t in enumerate(tokens)}
    curves = curves_for(tokens)
    rule = Exit(policy.get("hold_seconds", 180.0), policy.get("take_profit"), policy.get("stop_loss"))
    from .profit import Costs

    costs = Costs(policy.get("size_sol", 0.1), policy.get("fee", 0.0125), policy.get("network_sol", 0.0002), policy.get("exec_latency", 1.0))
    mints = [m for m in screens if m in index]
    median_latency = float(np.median(latencies)) / 1000 if len(latencies) else 0.0
    when = np.array([decisions[m]["t"] if m in decisions else screens[m]["t"] + median_latency for m in mints])
    ret = label_round_trips(curves, np.array([index[m] for m in mints]), when, costs, rule)
    cf = dict(zip(mints, ret))
    out["counterfactual"] = {
        "rule": rule.label(),
        "launches_with_data": len(mints),
        "all_screened": _stats(ret),
        "passed_skip_rules": _stats([cf[m] for m in mints if "skip" not in screens[m]]),
        "bought": _stats([cf[m] for m in mints if decisions.get(m, {}).get("buy")]),
        "not_bought": _stats([cf[m] for m in mints if not decisions.get(m, {}).get("buy")]),
        "by_skip_reason": {},
        "by_flag": {},
    }
    by_reason = defaultdict(list)
    for m in mints:
        reason = screens[m].get("skip")
        if reason:
            by_reason[reason.split(" ")[0]].append(cf[m])
    out["counterfactual"]["by_skip_reason"] = {k: _stats(v) for k, v in by_reason.items()}
    flags = Counter(f for m in mints for f in (screens[m]["state"].get("flags") or []))
    for flag, n in flags.most_common():
        if n >= 20:
            with_flag = [cf[m] for m in mints if flag in (screens[m]["state"].get("flags") or [])]
            without = [cf[m] for m in mints if flag not in (screens[m]["state"].get("flags") or [])]
            out["counterfactual"]["by_flag"][flag] = {"with": _stats(with_flag), "without": _stats(without)}

    shadows = {r["mint"]: r["answers"] for r in records if r["e"] == "shadow" and r.get("answers")}
    shadow_mints = [m for m in mints if m in shadows and not math.isnan(cf[m])]
    if len(shadow_mints) >= 50:
        y = np.array([cf[m] for m in shadow_mints])
        out["shadow"] = {"launches": len(shadow_mints), "base_p_net_positive": float((y > 0).mean()), "questions": {}}
        for qid in sorted({q for m in shadow_mints for q in shadows[m]}):
            p = np.array([shadows[m].get(qid, math.nan) for m in shadow_mints])
            ok = ~np.isnan(p)
            edges = np.unique(np.quantile(p[ok], np.linspace(0, 1, 6)))
            buckets = []
            for low, high in zip(edges[:-1], edges[1:]):
                sel = ok & (p >= low) & ((p < high) | (high == edges[-1]))
                if sel.sum():
                    buckets.append({"low": float(low), "high": float(high), "mean_answer": float(p[sel].mean()), "p_net_positive": float((y[sel] > 0).mean()), **_stats(y[sel])})
            ranks = lambda v: np.argsort(np.argsort(v))  # noqa: E731
            rho = float(np.corrcoef(ranks(p[ok]), ranks(y[ok]))[0, 1]) if ok.sum() > 2 else math.nan
            out["shadow"]["questions"][qid] = {"spearman_with_net": rho, "buckets": buckets}

    scored_mints = [m for m in mints if decisions.get(m, {}).get("score") is not None]
    if len(scored_mints) >= 20 and len({decisions[m]["score"] for m in scored_mints}) > 1:
        s = np.array([decisions[m]["score"] for m in scored_mints])
        y = np.array([cf[m] for m in scored_mints])
        ok = ~np.isnan(y)
        s, y = s[ok], y[ok]
        edges = np.unique(np.quantile(s, np.linspace(0, 1, 6)))
        buckets = []
        for low, high in zip(edges[:-1], edges[1:]):
            sel = (s >= low) & ((s < high) | (high == edges[-1]))
            if sel.sum():
                buckets.append({"score_low": float(low), "score_high": float(high), "mean_score": float(s[sel].mean()), "p_net_positive": float((y[sel] > 0).mean()), **_stats(y[sel])})
        best = None
        for thr in np.unique(np.quantile(s, [0, 0.25, 0.5, 0.75, 0.9, 0.95])):
            sel = s >= thr
            if sel.sum() >= 10:
                total = float(y[sel].sum() * costs.size_sol)
                if best is None or total > best["total_sol"]:
                    best = {"threshold": float(thr), "trades": int(sel.sum()), "total_sol": total, **_stats(y[sel])}
        out["calibration"] = {"buckets": buckets, "hindsight_best_threshold": best, "note": "in-sample: a hint, not proof"}
    return out


def _pct(x) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:+.2f}%"


def _line(name: str, s: dict) -> str:
    if not s or not s.get("n"):
        return f"| {name} | 0 | — | — | — |"
    return f"| {name} | {s['n']} | {_pct(s['mean'])} | {_pct(s['ci_low'])} … {_pct(s['ci_high'])} | {100 * s['win']:.0f}% |"


def to_markdown(r: dict) -> str:
    from datetime import datetime, timezone

    def ts(t):
        return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if t else "?"

    p = r.get("policy", {})
    lines = [
        f"# Fast-loop review: {ts(r['period'][0])} → {ts(r['period'][1])}",
        "",
        f"Policy: scorer **{p.get('scorer')}**, threshold {p.get('threshold')}, screen {p.get('screen_seconds')}s, "
        f"skip flags {p.get('skip_flags')}, hold {p.get('hold_seconds')}s, TP {p.get('take_profit')}, SL {p.get('stop_loss')} "
        f"({r['policy_changes']} change(s) during the period). Note: {p.get('note') or '—'}",
        "",
        f"Events: {r['counts']}. Skips: {r['skips']}.",
        "",
        f"Scorer: {r['scorer']}",
        "",
        "| | trades | mean net | 90% CI | win |",
        "|---|---|---|---|---|",
        _line("paper trades (as run)", r["paper"]),
    ]
    if len(r.get("paper_by_kind", {})) > 1 or "runup" in r.get("paper_by_kind", {}):
        lines += [_line(f"  of which {kind} entries", v) for kind, v in r["paper_by_kind"].items()]
    if r.get("runups", {}).get("triggered"):
        lines += [f"| (graduation run-ups triggered: {r['runups']['triggered']}, skipped {r['runups']['skipped']}) | | | | |"]
    cf = r.get("counterfactual")
    if cf:
        lines += [
            _line("every screened launch, if bought", cf["all_screened"]),
            _line("passed the skip rules", cf["passed_skip_rules"]),
            _line("bought (scorer said yes)", cf["bought"]),
            _line("not bought", cf["not_bought"]),
        ]
        lines += [_line(f"skipped: {k}", v) for k, v in cf["by_skip_reason"].items()]
        lines += ["", f"Counterfactual exit: {cf['rule']}; {cf['launches_with_data']} launches with recorded trades.", "", "| flag | with | without |", "|---|---|---|"]
        for flag, v in cf["by_flag"].items():
            lines.append(f"| {flag} | {_pct(v['with'].get('mean'))} ({v['with'].get('n', 0)}) | {_pct(v['without'].get('mean'))} ({v['without'].get('n', 0)}) |")
    shadow = r.get("shadow")
    if shadow:
        lines += [
            "",
            f"Jev shadow answers on {shadow['launches']} screened launches (not acted on; base P(net > 0) {100 * shadow['base_p_net_positive']:.0f}%):",
            "",
            "| question | Spearman with net | P(net > 0) lowest → highest answer quintile |",
            "|---|---|---|",
        ]
        for qid, q in shadow["questions"].items():
            trend = " → ".join(f"{100 * b['p_net_positive']:.0f}%" for b in q["buckets"])
            lines.append(f"| {qid} | {q['spearman_with_net']:+.3f} | {trend} |")
    cal = r.get("calibration")
    if cal:
        lines += ["", "Scorer calibration (counterfactual outcomes by score quintile):", "", "| score | mean score | P(net > 0) | mean net | n |", "|---|---|---|---|---|"]
        for b in cal["buckets"]:
            lines.append(f"| {b['score_low']:.3f}–{b['score_high']:.3f} | {b['mean_score']:.3f} | {100 * b['p_net_positive']:.0f}% | {_pct(b.get('mean'))} | {b['n']} |")
        best = cal["hindsight_best_threshold"]
        if best:
            lines += ["", f"Hindsight-best threshold {best['threshold']:.3f}: {best['trades']} trades, {_pct(best.get('mean'))} mean, {best['total_sol']:+.3f} SOL ({cal['note']})."]
    return "\n".join(lines) + "\n"
