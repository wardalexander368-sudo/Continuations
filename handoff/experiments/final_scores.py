"""Runs each pre-registered forward test's final scorer once it is due (the `final-scores` Action, weekly).

    python3 handoff/experiments/final_scores.py [--today YYYY-MM-DD] [--dry]

Why: several registered tests (vol-momentum, HLP hold, wick bounce, US patterns, Coinbase US-perp momentum) had no scheduled final
scoring, and the others rely on Claude routines that wake one session up to a year from now. This is
the free backstop. A test is scored here when its date has passed (plus a grace period when a
routine is meant to score it first) and its directory holds no RESULT file yet. The output is
written verbatim to `<prereg dir>/RESULT-auto-<date>.md`; nothing is interpreted, and no rule or
scorer is changed. Scorers fetch public history at scoring time; nothing here needs a key.
The dip forward test is left to its routine (its scoring adds a dated cost addendum first).
Execution evidence and prospective source checks live outside preregistration in handoff/scoring/.
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
LOCK_REL = "handoff/scoring/SOURCE_LOCK.json"
RECEIPTS = ROOT / "handoff/scoring/receipts"

try:  # direct script invocation and importlib-based tests both use the same helper
    from handoff.experiments import scoring_receipts as receipts
except ModuleNotFoundError:
    import scoring_receipts as receipts

# name, prereg dir, first day the final score is allowed, grace days (routine scores first), command[, secondary]
TESTS = [
    ("HLP hold vs 5% hurdle", "hlp-hold", "2027-04-11", 0, [f"{EXP}/edge-hunt/vaults/hlp_forward.py", "--final"]),
    ("pumpflow (PUMP revenue surprise)", "pumpflow", "2027-04-09", 7, [f"{EXP}/pumpflow_paper.py", "evaluate", "--final"]),
    ("hedged JLP", "jlp-hedged", "2027-01-08", 7, [f"{EXP}/jlp_paper.py", "evaluate", "--final"]),
    ("US-spot patterns", "us-patterns", "2027-10-12", 0, [f"{EXP}/edge-hunt/patterns/pattern_forward.py", "{cache}", "--final"],
     [f"{EXP}/edge-hunt/patterns/pattern_forward_costs.py", "{cache}", "--no-fetch"]),  # ADDENDUM-2026-10-11
    ("wick bounce (HL)", "wick-bounce", "2027-10-12", 0, [f"{EXP}/edge-hunt/perps/wick_forward.py", "--final"]),
    ("vol-scaled momentum", "vol-momentum", "2027-10-20", 0, [f"{EXP}/edge-hunt/perps/vmom_forward.py", "--final"]),
    ("vol-momentum on Coinbase US perps", "cde-vol-momentum", "2027-10-19", 0, [f"{EXP}/edge-hunt/perps/cde_forward.py", "{cache}", "--final"]),
    ("cross-sectional momentum", "xs-momentum", "2027-10-21", 7, [f"{EXP}/xs_momentum_forward.py", "--final"]),
]


def due(today: dt.date) -> list[tuple]:
    out = []
    for name, d, first, grace, cmd, *extra in TESTS:
        when = dt.date.fromisoformat(first) + dt.timedelta(days=grace)
        scored = any(p.name.startswith("RESULT") for p in (PRE / d).iterdir())
        out.append((name, d, when, scored, [cmd, *extra]))
    return out


def _text(value) -> str:
    return value.decode(errors="replace") if isinstance(value, bytes) else value or ""


def main() -> int:
    today = dt.date.fromisoformat(sys.argv[sys.argv.index("--today") + 1]) if "--today" in sys.argv else dt.datetime.now(dt.timezone.utc).date()
    rc = 0
    for name, d, when, scored, cmds in due(today):
        state = "scored" if scored else ("DUE" if today >= when else f"waits until {when}")
        print(f"{name} ({d}): {state}")
        if scored or today < when or "--dry" in sys.argv:
            continue
        before = receipts.verify(ROOT, LOCK_REL, d, cmds)
        receipt_path, evidence = receipts.start_attempt(ROOT, RECEIPTS, d, name, today, when, cmds, before)
        if before["status"] != "PROSPECTIVE_SOURCE_MATCH":
            receipts.finish_attempt(receipt_path, evidence, after=before, inputs={"status": "not_run"}, status="INVALID/PROTOCOL_DRIFT")
            print("  INVALID/PROTOCOL_DRIFT; no scorer executed or RESULT created: " + "; ".join(before["issues"]))
            rc = 1
            continue
        with tempfile.TemporaryDirectory() as cache:
            # TemporaryDirectory may be below macOS's /var symlink; use its physical owned path.
            cache_path = Path(cache).resolve()
            receipts.record_inputs_before(receipt_path, evidence, receipts.inventory(ROOT, cache_path, before["declared_inputs"]))
            for cmd in cmds:  # original order, including informative secondary after a failed primary
                argv = [sys.executable, *[c.replace("{cache}", cache) for c in cmd]]
                started = receipts.utc_now()
                try:
                    p = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=3000)
                    receipts.record_run(receipt_path, evidence, argv=argv, started=started, ended=receipts.utc_now(),
                                        returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
                except subprocess.TimeoutExpired as exc:
                    receipts.record_run(receipt_path, evidence, argv=argv, started=started, ended=receipts.utc_now(),
                                        stdout=_text(exc.stdout), stderr=_text(exc.stderr), failure="TIMEOUT")
                except OSError as exc:
                    receipts.record_run(receipt_path, evidence, argv=argv, started=started, ended=receipts.utc_now(),
                                        stderr=f"{type(exc).__name__}: {exc}", failure="EXECUTION_ERROR")
            after = receipts.verify(ROOT, LOCK_REL, d, cmds)
            if before["source_lock"].get("sha256") != after["source_lock"].get("sha256"):
                after["status"] = "INVALID/PROTOCOL_DRIFT"
                after["issues"].append("prospective source lock changed during execution")
            inputs = receipts.inventory(ROOT, cache_path, before["declared_inputs"])
            runs = evidence["runs"]
            if after["status"] != "PROSPECTIVE_SOURCE_MATCH":
                status = "INVALID/PROTOCOL_DRIFT"
            elif any(q["returncode"] != 0 or q["failure"] or q["acquisition_failure_evidence"] for q in runs):
                status = "FAILED_EXECUTION"
            elif inputs["status"] == "unknown_or_incomplete":
                status = "INVALID/INPUT_PROVENANCE"
            else:
                status = "EXECUTION_COMPLETE"  # exit zero is never interpreted as a profitable test
            receipts.finish_attempt(receipt_path, evidence, after=after, inputs=inputs, status=status)
        if status != "EXECUTION_COMPLETE":
            print(f"  {status}; not recorded; evidence: {receipt_path.relative_to(ROOT)}")
            for q in runs:
                if q["returncode"] != 0 or q["failure"] or q["acquisition_failure_evidence"]:
                    print("\n".join((q["stderr"] or q["stdout"]).strip().splitlines()[-40:]))
            rc = 1
            continue
        p, cmd = runs[0], cmds[0]
        sha = after["head"].get("commit", "unknown")[:7]
        body = (f"# {name}: final score (automatic)\n\nRun {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC by the "
                f"`final-scores` Action (`handoff/experiments/final_scores.py`) at commit {sha}: "
                f"`python3 {' '.join(cmd).replace('{cache}', 'CACHE')}`. "
                "Verbatim output below; the registered criteria are in SPEC.md.\n\n```\n"
                f"{p['stdout'].strip()}\n```\n")
        for q, c2 in zip(runs[1:], cmds[1:]):
            body += f"\nSecondary (informative), `python3 {' '.join(c2).replace('{cache}', 'CACHE')}`:\n\n```\n{(q['stdout'] or q['stderr']).strip()}\n```\n"
        result = PRE / d / f"RESULT-auto-{today}.md"
        try:
            result.write_text(body)
        except OSError as exc:
            evidence["result_write_error"] = f"{type(exc).__name__}: {exc}"
            receipts.finish_attempt(receipt_path, evidence, after=after, inputs=inputs, status="FAILED_RESULT_WRITE")
            raise
        receipts.finish_attempt(receipt_path, evidence, after=after, inputs=inputs, status="RESULT_RECORDED", official_result=result.relative_to(ROOT).as_posix())
        print(f"  wrote {d}/RESULT-auto-{today}.md")
    return rc


if __name__ == "__main__":
    sys.exit(main())
