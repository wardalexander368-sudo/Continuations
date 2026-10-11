"""The final-scores backstop names real pre-registration dirs and scorer scripts."""
import datetime as dt
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("final_scores", ROOT / "handoff/experiments/final_scores.py")
fs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fs)


def test_tests_point_at_real_files():
    for name, d, first, grace, cmd, *extra in fs.TESTS:
        assert (ROOT / "handoff/preregistration" / d / "SPEC.md").exists(), d
        assert (ROOT / cmd[0]).exists(), cmd[0]
        assert "--final" in cmd
        dt.date.fromisoformat(first)


def test_nothing_due_before_first_date():
    rows = fs.due(dt.date(2026, 10, 11))
    assert all(dt.date(2026, 10, 11) < when for _, _, when, _, _ in rows)
