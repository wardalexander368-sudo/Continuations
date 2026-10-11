"""Workflows see what they need: health's sparse checkout covers every input it checks, and each
script a workflow runs has its third-party imports installed (perps-ctx once ran wick_forward.py
without numpy, and `|| true` hid it for a day)."""
import re
from pathlib import Path

from tartar.autotrade import health

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows"
THIRD_PARTY = {"httpx", "numpy", "websockets"}


def test_health_sparse_checkout_covers_inputs():
    yml = (WF / "health.yml").read_text()
    sparse = re.search(r"sparse-checkout: \|\n((?:\s+\S+\n)+)", yml).group(1).split()
    for rel, _, _ in health.INPUTS.values():
        assert any(rel == s or rel.startswith(s + "/") for s in sparse), rel


def test_workflow_scripts_have_their_imports():
    for wf in WF.glob("*.yml"):
        text = wf.read_text()
        installed = set(re.findall(r'"(\w+)[>=<]', " ".join(re.findall(r"pip install (.*)", text))))
        if "pip install -e" in text:
            continue
        for script in set(re.findall(r"python3 (handoff/\S+\.py)", text)):
            src = (ROOT / script).read_text()
            top = {m for m in re.findall(r"^(?:import|from) (\w+)", src, re.M)} & THIRD_PARTY
            assert top <= installed, f"{wf.name}: {script} imports {top - installed}"
