"""Health of the repo's unattended jobs: ``python -m tartar.autotrade health`` (hourly Action ``health.yml``).

Checks, each green / yellow / red:
* **Actions:** every scheduled workflow's latest finished run (failed = red) and whether one has run
  within its cadence (none = red: skipped or stuck). Cancelled runs are ignored (concurrency supersedes them).
* **Recorder hours:** every UTC hour since the recorder started, up to two hours ago, has an asset in its
  day's release (`raw-gha-YYYYMMDD`); missing hours are red.
* **Paper-test inputs:** the newest row or file of each forward test's data is recent enough.
* **Agent:** no agent run in 20 minutes, open orphans and live halts are red; twins whose last closes drift from paper are yellow.

Writes ``autotrade/health.json``; the agent's REPORT.md shows it at the top. Exit code 1 while anything is
red, so the Actions run fails and GitHub notifies the repository owner.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY") or "wardalexander368-sudo/Continuations"  # moved from StaticPush7217/TARTAR 2026-10-10
API = f"https://api.github.com/repos/{REPO}"

# workflow file -> (longest normal gap between runs in s, what it does)
WORKFLOWS = {
    "autotrade.yml": (2 * 3600, "the agent, hourly"),
    "paper-tests.yml": (5 * 3600, "JLP check-ins every 4 h, dip cohort daily"),
    "pumpflow-paper.yml": (2 * 3600, "pumpflow snapshots, hourly"),
    "perps-ctx.yml": (5 * 3600, "Hyperliquid OI/funding snapshots, every 4 h"),
}
RECORDER_START = datetime(2026, 10, 9, 21, tzinfo=timezone.utc)  # first full hour of the recorder Action
RECORDER_MOVED = datetime(2026, 10, 10, 20, tzinfo=timezone.utc)  # first hour recorded in Continuations; earlier releases stayed in TARTAR

# forward-test input -> (path, max age in s, how to read its newest time)
INPUTS = {
    "JLP snapshots": ("handoff/data/jlp-paper/snapshots.jsonl", 9 * 3600, "jsonl_t"),
    "dip cohorts": ("handoff/preregistration/dip-rolling", 28 * 3600, "cohort_name"),
    "pumpflow snapshots": ("handoff/data/pumpflow-paper/snapshots.jsonl", 54 * 3600, "jsonl_t"),
    "HL OI/funding snapshots": ("handoff/data/edge-hunt/hl-ctx", 9 * 3600, "jsonl_t_dir"),
}
DRIFT_POINTS, DRIFT_N = 0.03, 10
AGENT_MAX_GAP = 2 * 3600  # the agent runs once an hour
# The recorder and pumpflow-live Actions were turned off 2026-10-10 21:05 UTC (AJ, GitHub's Actions terms:
# handoff/reviews/tos-check-2026-10-10.md), so their workflows and the recorder's hours are no longer checked.
CHECK_RECORDER = False


def _get(http, url, **params):
    for wait in (2, 4, 0):
        r = http.get(url, params=params)
        if r.status_code == 200:
            return r.json()
        if not wait:
            break
        time.sleep(wait)
    r.raise_for_status()


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def check_workflows(http, now: float) -> list[dict]:
    out = []
    for wf, (gap, what) in WORKFLOWS.items():
        try:
            runs = _get(http, f"{API}/actions/workflows/{wf}/runs", per_page=20)["workflow_runs"]
        except Exception as exc:  # noqa: BLE001
            out.append({"check": f"Action {wf}", "level": "yellow", "detail": f"couldn't read runs: {exc}"[:200]})
            continue
        runs = [r for r in runs if r.get("conclusion") != "cancelled"]
        done = [r for r in runs if r["status"] == "completed"]
        alive = [r for r in runs if r["status"] == "in_progress"]
        latest = done[0] if done else None
        started = max([_ts(r["run_started_at"]) for r in runs if r.get("run_started_at")] or [0])
        if not runs:
            out.append({"check": f"Action {wf}", "level": "yellow", "detail": f"no runs yet [{what}]"})
        elif latest and latest["conclusion"] not in ("success", "skipped", "neutral"):
            out.append({"check": f"Action {wf}", "level": "red",
                        "detail": f"latest run {latest['conclusion']} ({latest['html_url']}) [{what}]"})
        elif not alive and now - started > gap:
            out.append({"check": f"Action {wf}", "level": "red",
                        "detail": f"no run for {(now - started) / 3600:.1f} h (expected within {gap / 3600:.1f} h) [{what}]"})
        else:
            out.append({"check": f"Action {wf}", "level": "green", "detail": what})
    return out


def check_recorder(http, now: float) -> list[dict]:
    end = datetime.fromtimestamp(now, timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    start = max(RECORDER_START, RECORDER_MOVED, end - timedelta(hours=48))
    want, h = [], start
    while h <= end:
        want.append(h.strftime("%Y%m%d-%H"))
        h += timedelta(hours=1)
    have = set()
    for day in sorted({w[:8] for w in want}):
        try:
            rel = _get(http, f"{API}/releases/tags/raw-gha-{day}")
            have |= {a["name"].split(".")[0] for a in rel.get("assets", []) if ".run" in a["name"] and a["name"].endswith(".jsonl.gz")}
        except Exception:  # noqa: BLE001 - no release for that day = all its hours missing
            pass
    missing = [w for w in want if w not in have]
    if not want:
        return [{"check": "Recorder hours", "level": "green", "detail": "nothing due yet"}]
    if missing:
        return [{"check": "Recorder hours", "level": "red",
                 "detail": f"{len(missing)} of the last {len(want)} hours missing: {', '.join(missing[:12])}{' …' if len(missing) > 12 else ''}"}]
    return [{"check": "Recorder hours", "level": "green", "detail": f"all {len(want)} hours through {want[-1]} UTC uploaded"}]


def _newest(path: Path, how: str) -> float | None:
    if how == "jsonl_t":
        files = [path] if path.exists() else []
    elif how == "jsonl_t_dir":
        files = sorted(path.glob("*.jsonl"))[-1:] if path.exists() else []
    else:  # cohort_name: cohort-YYYY-MM-DDTHHMM.json
        names = sorted(p.name for p in path.glob("cohort-*.json")) if path.exists() else []
        if not names:
            return None
        return datetime.strptime(names[-1][7:22], "%Y-%m-%dT%H%M").replace(tzinfo=timezone.utc).timestamp()
    for f in files:
        lines = [x for x in f.read_text().splitlines() if x.strip()]
        if lines:
            t = json.loads(lines[-1]).get("t")
            return _ts(t) if isinstance(t, str) else float(t)
    return None


def check_inputs(repo: Path, now: float) -> list[dict]:
    out = []
    for name, (rel, max_age, how) in INPUTS.items():
        t = _newest(repo / rel, how)
        if t is None:
            out.append({"check": f"Input: {name}", "level": "red", "detail": f"nothing in {rel}"})
        elif now - t > max_age:
            out.append({"check": f"Input: {name}", "level": "red",
                        "detail": f"newest is {(now - t) / 3600:.1f} h old (max {max_age / 3600:.0f} h) in {rel}"})
        else:
            out.append({"check": f"Input: {name}", "level": "green", "detail": f"newest {(now - t) / 3600:.1f} h old"})
    return out


def check_agent(root: Path, now: float | None = None) -> list[dict]:
    out = []
    state = json.loads((root / "state.json").read_text()) if (root / "state.json").exists() else {}
    last = (state.get("last_run") or {}).get("at")
    if now is not None and last is not None and now - last > AGENT_MAX_GAP:
        out.append({"check": "Agent: last run", "level": "red",
                    "detail": f"the agent last ran {(now - last) / 60:.0f} min ago (expected hourly; its Action job may be stuck)"})
    live = state.get("live", {})
    if live.get("orphans"):
        out.append({"check": "Agent: orphans", "level": "red",
                    "detail": f"{len(live['orphans'])} live twin(s) without an exit (state.json live.orphans)"})
    halts = ([f"all: {live['halted']}"] if live.get("halted") else []) + \
            [f"{n}: {r['halted']}" for n, r in live.get("strategies", {}).items() if r.get("halted")]
    if state.get("halted"):
        halts.insert(0, f"agent: {state['halted']}")
    if halts:
        out.append({"check": "Agent: halts", "level": "red", "detail": "; ".join(halts)[:400]})
    path = root / "fills.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
    closes = [r for r in rows if r.get("event") in ("sell", "perp_close", "perp_roll_out", "usd_sell") and "compare" in r]
    by: dict[str, list[float]] = {}
    for r in closes:
        by.setdefault(r.get("strategy", "?"), []).append(r["compare"]["live_minus_paper"])
    for name, d in by.items():
        last = sorted(d[-DRIFT_N:])
        med = last[len(last) // 2]
        if len(last) >= 3 and med < -DRIFT_POINTS:
            out.append({"check": f"Twins: {name}", "level": "yellow",
                        "detail": f"median twin − paper {100 * med:+.2f} points over the last {len(last)} closes"})
        else:
            out.append({"check": f"Twins: {name}", "level": "green",
                        "detail": f"median twin − paper {100 * med:+.2f} points over the last {len(last)} closes"})
    if not out:
        out.append({"check": "Agent", "level": "green", "detail": "no halts, no orphans, no closed twins yet"})
    return out


def run(root: Path, repo: Path, now: float | None = None, http=None) -> dict:
    import httpx

    now = time.time() if now is None else now
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    http = http or httpx.Client(timeout=30, headers=headers, follow_redirects=True)
    items = check_workflows(http, now) + (check_recorder(http, now) if CHECK_RECORDER else []) + check_inputs(repo, now) + check_agent(root, now)
    levels = [i["level"] for i in items]
    status = "red" if "red" in levels else "yellow" if "yellow" in levels else "green"
    out = {"checked_at": now, "status": status, "items": items}
    (root / "health.json").write_text(json.dumps(out, indent=1) + "\n")
    return out


def report_lines(root: Path, now: float) -> list[str]:
    """The Health section for the top of REPORT.md."""
    p = root / "health.json"
    if not p.exists():
        return ["## Health", "", "No health check yet (`health.yml` runs hourly).", ""]
    h = json.loads(p.read_text())
    age = (now - h["checked_at"]) / 3600
    icon = {"red": "🔴", "yellow": "🟡", "green": "🟢"}
    status = h["status"] if age <= 3 else "yellow" if h["status"] == "green" else h["status"]
    lines = [f"## Health {icon[status]} {status.upper()}", "",
             f"Checked {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(h['checked_at']))}"
             + (f" (**{age:.1f} h ago: the health job itself may be stuck**)" if age > 3 else "") + "."]
    bad = [i for i in h["items"] if i["level"] != "green"]
    if bad:
        lines += [""] + [f"* {icon[i['level']]} **{i['check']}:** {i['detail']}" for i in bad]
    lines += ["", f"{sum(1 for i in h['items'] if i['level'] == 'green')} of {len(h['items'])} checks green "
                  "(`autotrade/health.json` lists them all).", ""]
    return lines
