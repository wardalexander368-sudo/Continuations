"""Runs each pre-registered forward test's final scorer once it is due (the `final-scores` Action, weekly).

    python3 handoff/experiments/final_scores.py [--today YYYY-MM-DD] [--dry]

Why: four registered tests (vol-momentum, HLP hold, wick bounce, US patterns) had no scheduled final
scoring, and the others rely on Claude routines that wake one session up to a year from now. This is
the free backstop. A test is scored here when its date has passed (plus a grace period when a
routine is meant to score it first) and its directory holds no RESULT file yet. The output is
written verbatim to `<prereg dir>/RESULT-auto-<date>.md`; nothing is interpreted, and no rule or
scorer is changed. Scorers fetch public history at scoring time; nothing here needs a key.
The dip forward test is left to its routine (its scoring adds a dated cost addendum first).
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRE = ROOT / "handoff/preregistration"
EXP = "handoff/experiments"

# name, prereg dir, first day the final score is allowed, grace days (routine scores first), command[, secondary]
TESTS = [
    ("HLP hold vs 5% hurdle", "hlp-hold", "2027-04-11", 0, [f"{EXP}/edge-hunt/vaults/hlp_forward.py", "--final"]),
    ("pumpflow (PUMP revenue surprise)", "pumpflow", "2027-04-09", 7, [f"{EXP}/pumpflow_paper.py", "evaluate", "--final"]),
    ("hedged JLP", "jlp-hedged", "2027-01-08", 7, [f"{EXP}/jlp_paper.py", "evaluate", "--final"]),
    ("US-spot patterns", "us-patterns", "2027-10-12", 0, [f"{EXP}/edge-hunt/patterns/pattern_forward.py", "{cache}", "--final"],
     [f"{EXP}/edge-hunt/patterns/pattern_forward_costs.py", "{cache}", "--no-fetch"]),  # ADDENDUM-2026-10-11
    ("wick bounce (HL)", "wick-bounce", "2027-10-12", 0, [f"{EXP}/edge-hunt/perps/wick_forward.py", "--final"]),
    ("vol-scaled momentum", "vol-momentum", "2027-10-20", 0, [f"{EXP}/edge-hunt/perps/vmom_forward.py", "--final"]),
    ("cross-sectional momentum", "xs-momentum", "2027-10-21", 7, [f"{EXP}/xs_momentum_forward.py", "--final"]),
]


def due(today: dt.date) -> list[tuple]:
    out = []
    for name, d, first, grace, cmd, *extra in TESTS:
        when = dt.date.fromisoformat(first) + dt.timedelta(days=grace)
        scored = any(p.name.startswith("RESULT") for p in (PRE / d).iterdir())
        out.append((name, d, when, scored, [cmd, *extra]))
    return out


def main() -> int:
    today = dt.date.fromisoformat(sys.argv[sys.argv.index("--today") + 1]) if "--today" in sys.argv else dt.datetime.now(dt.timezone.utc).date()
    rc = 0
    for name, d, when, scored, cmds in due(today):
        state = "scored" if scored else ("DUE" if today >= when else f"waits until {when}")
        print(f"{name} ({d}): {state}")
        if scored or today < when or "--dry" in sys.argv:
            continue
        with tempfile.TemporaryDirectory() as cache:
            runs = [subprocess.run([sys.executable, *[c.replace("{cache}", cache) for c in cmd]], cwd=ROOT,
                                   capture_output=True, text=True, timeout=3000) for cmd in cmds]
        p, cmd = runs[0], cmds[0]
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        body = (f"# {name}: final score (automatic)\n\nRun {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC by the "
                f"`final-scores` Action (`handoff/experiments/final_scores.py`) at commit {sha}: "
                f"`python3 {' '.join(cmd).replace('{cache}', 'CACHE')}`. "
                "Verbatim output below; the registered criteria are in SPEC.md.\n\n```\n"
                f"{p.stdout.strip()}\n```\n")
        for q, c2 in zip(runs[1:], cmds[1:]):
            body += f"\nSecondary (informative), `python3 {' '.join(c2).replace('{cache}', 'CACHE')}`:\n\n```\n{(q.stdout or q.stderr).strip()}\n```\n"
        if p.returncode:  # no file: a failed run (network, API change) is retried next week; the job goes red
            print(f"  FAILED (exit {p.returncode}); not recorded:\n" + "\n".join(p.stderr.strip().splitlines()[-40:]))
            rc = 1
            continue
        (PRE / d / f"RESULT-auto-{today}.md").write_text(body)
        print(f"  wrote {d}/RESULT-auto-{today}.md")
    return rc


if __name__ == "__main__":
    sys.exit(main())
