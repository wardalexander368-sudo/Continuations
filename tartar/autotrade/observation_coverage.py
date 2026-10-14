"""Persisted hourly observation receipts; reporting evidence, never an execution cursor.

Recent detail is bounded. Lifetime counts include archived gaps and legacy hours,
so pruning or a later successful fetch cannot make an incomplete forward record green.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

VERSION = 1
DETAIL_LIMIT = 2048
RETRY_HOURS = 72
STATES = ("observed-no-signal", "signal-intent", "busy", "outside-window", "incomplete")
MAX_AGE = 2 * 3600


def latest_eligible_hour(at: float, delay: int) -> int:
    """The strategy's existing closed-candle eligibility formula, unchanged."""
    return (int(at) - 60 - delay * 900) // 3600 - 1


def _hour(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()) // 3600


def initialize(data: dict, *, done: int, now: int, coins: list[str], start: str, end: str, delay: int, rule: str) -> dict:
    if "coverage" not in data:
        start_h, end_h = _hour(start), _hour(end) + 23
        old_end = min(done, end_h)
        unknown = max(0, old_end - start_h + 1) * len(coins)
        data["coverage"] = {
            "schema_version": VERSION, "coins": list(coins), "start_hour": start_h, "end_hour": end_h,
            "delay_bars": delay, "rule": rule, "first_hour": done + 1, "through_hour": done,
            "initialized_at": now, "checked_at": now,
            "legacy_unknown": {"from_hour": start_h, "through_hour": old_end, "coin_hours": unknown},
            "counts": dict.fromkeys(STATES, 0), "reasons": {}, "late_recovered": 0,
            "receipts": {}, "pending": {}, "progress": {},
            "archived": {"receipts": 0, "unresolved": 0, "late_first": 0, "unknown_first": 0},
        }
    c = data["coverage"]
    if not isinstance(c, dict) or c.get("schema_version") != VERSION:
        raise ValueError("unsupported or malformed observation coverage; preserve it for review")
    if (c.get("coins"), c.get("start_hour"), c.get("end_hour"), c.get("delay_bars"), c.get("rule")) != \
            (list(coins), _hour(start), _hour(end) + 23, delay, rule):
        raise ValueError("observation coverage configuration changed; preserve the original evidence")
    c["checked_at"] = now
    return c


def record(c: dict, coin: str, hour: int, state: str, now: int, *, reason: str = "", source: dict | None = None) -> None:
    key = f"{coin}:{hour}"
    if key in c["receipts"]:
        return
    row = {"coin": coin, "hour": hour, "state": state, "first_attempt_at": now}
    if reason:
        row["reason"] = reason
        c["reasons"][reason] = c["reasons"].get(reason, 0) + 1
    if source:
        row["source"] = source
    c["receipts"][key] = row
    c["counts"][state] += 1
    c["progress"][coin] = hour
    if state == "incomplete":
        c["pending"][key] = hour


def pending_hours(c: dict, coin: str, h_max: int) -> list[int]:
    """Retry only recent gaps using the ordinary candle fetch; older gaps remain counted."""
    return sorted(h for key, h in c["pending"].items()
                  if key.rsplit(":", 1)[0] == coin and h_max - RETRY_HOURS <= h <= h_max)


def recovered(c: dict, coin: str, hour: int, now: int, *, signal: bool) -> None:
    key = f"{coin}:{hour}"
    row = c["receipts"].get(key)
    if row and key in c["pending"]:
        # The original state and reason are immutable: recovered data is hindsight.
        row["recovery"] = {"observed_at": now, "signal": bool(signal), "execution": "annotation-only"}
        c["late_recovered"] += 1
        del c["pending"][key]


def finish(c: dict, through: int) -> None:
    c["through_hour"] = max(c["through_hour"], through)
    rows = c["receipts"]
    if len(rows) > DETAIL_LIMIT:
        archive = c["archived"]
        # Old archives contain no per-hour observation times. Preserve their
        # unknown timing rather than retroactively declaring them timely.
        if "late_first" not in archive or "unknown_first" not in archive:
            archive["late_first"] = 0
            archive["unknown_first"] = archive["receipts"]
        old = sorted(rows, key=lambda key: (rows[key]["hour"], key))[:len(rows) - DETAIL_LIMIT]
        for key in old:
            row = rows[key]
            if row["state"] != "outside-window":
                at = row.get("first_attempt_at")
                if (not isinstance(at, (int, float)) or isinstance(at, bool) or not math.isfinite(at) or
                        not c["initialized_at"] <= at <= c["checked_at"]):
                    archive["unknown_first"] += 1
                elif latest_eligible_hour(at, c["delay_bars"]) < row["hour"]:
                    archive["unknown_first"] += 1
                elif latest_eligible_hour(at, c["delay_bars"]) > row["hour"]:
                    archive["late_first"] += 1
            del rows[key]
            c["archived"]["receipts"] += 1
            if key in c["pending"]:
                del c["pending"][key]
                c["archived"]["unresolved"] += 1


def _integer(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def summarize(c, now: float) -> dict:
    """Fail closed on missing/malformed coverage, stale progress, or any original gap."""
    unknown = {"status": "unknown", "complete": False, "detail": "coverage missing; historical observation is unknown"}
    if c is None:
        return unknown
    try:
        if not isinstance(c, dict) or c.get("schema_version") != VERSION:
            raise ValueError("unknown schema")
        coins = c["coins"]
        if not isinstance(coins, list) or not coins or any(not isinstance(s, str) or not s for s in coins) or len(set(coins)) != len(coins):
            raise ValueError("invalid coins")
        counts = c["counts"]
        if not isinstance(counts, dict) or set(counts) != set(STATES) or any(not _integer(v) or v < 0 for v in counts.values()):
            raise ValueError("invalid counts")
        for k in ("start_hour", "end_hour", "first_hour", "through_hour", "delay_bars", "late_recovered"):
            if not _integer(c[k]):
                raise ValueError(f"invalid {k}")
        if c["end_hour"] < c["start_hour"] or c["delay_bars"] < 1 or c["late_recovered"] < 0:
            raise ValueError("invalid interval")
        if c["rule"] not in ("capit", "volspike"):
            raise ValueError("invalid rule")
        at = c["checked_at"]
        if not isinstance(at, (float, int)) or isinstance(at, bool) or not math.isfinite(at) or at > now + 60:
            raise ValueError("invalid checked_at")
        initialized = c["initialized_at"]
        if (not isinstance(initialized, (float, int)) or isinstance(initialized, bool) or
                not math.isfinite(initialized) or initialized > at):
            raise ValueError("invalid initialized_at")
        legacy = c["legacy_unknown"]
        if not isinstance(legacy, dict) or not _integer(legacy["coin_hours"]) or legacy["coin_hours"] < 0:
            raise ValueError("invalid legacy count")
        prior_end = min(c["first_hour"] - 1, c["end_hour"])
        expected_legacy = max(0, prior_end - c["start_hour"] + 1) * len(coins)
        if legacy["coin_hours"] != expected_legacy or legacy["from_hour"] != c["start_hour"] or legacy["through_hour"] != prior_end:
            raise ValueError("legacy denominator mismatch")
        observed = sum(counts.values()) - counts["outside-window"]
        expected = max(0, min(c["through_hour"], c["end_hour"]) - max(c["first_hour"], c["start_hour"]) + 1) * len(coins)
        if observed != expected or c["late_recovered"] > counts["incomplete"]:
            raise ValueError("observation denominator mismatch")
        archive = c["archived"]
        pending, receipts = c["pending"], c["receipts"]
        if not isinstance(archive, dict) or any(not _integer(archive[k]) or archive[k] < 0 for k in ("receipts", "unresolved")):
            raise ValueError("invalid archive counts")
        if not isinstance(pending, dict) or not isinstance(receipts, dict) or len(receipts) + archive["receipts"] != sum(counts.values()):
            raise ValueError("invalid receipts")
        recent_counts = dict.fromkeys(STATES, 0)
        late_first = archive.get("late_first", 0)
        unknown_first = archive.get("unknown_first", archive["receipts"])
        if (not _integer(late_first) or not _integer(unknown_first) or
                min(late_first, unknown_first) < 0 or late_first + unknown_first > archive["receipts"]):
            raise ValueError("invalid archived observation timing")
        for key, row in receipts.items():
            if not isinstance(row, dict) or row.get("coin") not in coins or not _integer(row.get("hour")) or row.get("state") not in STATES:
                raise ValueError("invalid receipt")
            h, s = row["hour"], row["state"]
            if key != f"{row['coin']}:{h}" or not c["first_hour"] <= h <= c["through_hour"]:
                raise ValueError("receipt interval mismatch")
            if (s == "outside-window") != (not c["start_hour"] <= h <= c["end_hour"]):
                raise ValueError("receipt window mismatch")
            if s in ("incomplete", "busy") and (not isinstance(row.get("reason"), str) or not row["reason"]):
                raise ValueError("missing gap reason")
            first_at = row["first_attempt_at"]
            if (not isinstance(first_at, (int, float)) or isinstance(first_at, bool) or not math.isfinite(first_at) or
                    not initialized <= first_at <= at):
                raise ValueError("invalid receipt time")
            if s != "outside-window":
                eligible = latest_eligible_hour(first_at, c["delay_bars"])
                if eligible < h:
                    raise ValueError("observation predates eligible candle")
                late_first += eligible > h
            if "recovery" in row:
                r = row["recovery"]
                if (s != "incomplete" or not isinstance(r, dict) or not isinstance(r.get("signal"), bool) or
                        r.get("execution") != "annotation-only" or not isinstance(r.get("observed_at"), (int, float)) or
                        isinstance(r["observed_at"], bool) or not math.isfinite(r["observed_at"]) or
                        not first_at <= r["observed_at"] <= at):
                    raise ValueError("invalid recovery annotation")
            recent_counts[s] += 1
        if any(recent_counts[s] > counts[s] for s in STATES):
            raise ValueError("receipt count mismatch")
        for key, h in pending.items():
            if not _integer(h) or key not in receipts or receipts[key]["state"] != "incomplete" or receipts[key]["hour"] != h or "recovery" in receipts[key]:
                raise ValueError("invalid pending gap")
        unresolved = len(pending) + archive["unresolved"]
        if unresolved + c["late_recovered"] != counts["incomplete"]:
            raise ValueError("gap denominator mismatch")
        latest = latest_eligible_hour(now, c["delay_bars"])
        if c["through_hour"] > latest:
            raise ValueError("future observation progress")
        want = min(latest, c["end_hour"])
        stale = now - at > MAX_AGE or c["through_hour"] < want
        issues = []
        if legacy["coin_hours"]:
            issues.append(f"{legacy['coin_hours']} historically unknown coin-hours")
        if counts["incomplete"]:
            issues.append(f"{counts['incomplete']} original incomplete coin-hours ({unresolved} unresolved, {c['late_recovered']} recovered late)")
        if late_first:
            issues.append(f"{late_first} late first observations (historical catch-up, not first-run coverage)")
        if unknown_first:
            issues.append(f"{unknown_first} archived first-observation times unknown")
        if stale:
            issues.append("stale observation progress")
        return {"status": "stale" if stale else "incomplete" if issues else "complete", "complete": not issues,
                "observed_coin_hours": observed, "expected_coin_hours": expected + legacy["coin_hours"],
                "legacy_unknown_coin_hours": legacy["coin_hours"], "incomplete_coin_hours": counts["incomplete"],
                "unresolved_coin_hours": unresolved, "late_recovered_coin_hours": c["late_recovered"],
                "late_first_observation_coin_hours": late_first, "unknown_first_observation_coin_hours": unknown_first,
                "detail": "; ".join(issues) if issues else f"all {observed} eligible coin-hours observed or explicitly busy"}
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"status": "malformed", "complete": False, "detail": "malformed coverage; observation completeness cannot be established"}


def from_state(state, strategy: str, now: float) -> dict:
    try:
        c = state["strategies"][strategy]["data"].get("coverage")
    except (KeyError, TypeError, AttributeError):
        c = None
    return summarize(c, now)
