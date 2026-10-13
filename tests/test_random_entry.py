import importlib.util
import sys
from pathlib import Path

import numpy as np

D = Path(__file__).resolve().parents[1] / "handoff/experiments/edge-hunt/patterns"


def load():
    sys.path.insert(0, str(D))
    spec = importlib.util.spec_from_file_location("random_entry", D / "random_entry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_forward_entries_and_controls():
    m = load()
    C = np.array([100.0, 100, 110, 121, 121, 121])
    f = m.forward(C, 1)  # buy close h+1, sell close h+2
    assert np.isclose(f[0], 0.10 - 2 * m.COST) and np.isclose(f[1], 0.10 - 2 * m.COST)
    assert np.isnan(f[-1]) and np.isnan(f[-2])
    sig = np.array([True, True, True, False, False, False])
    assert m.entries(sig, f, 1) == [0, 2]  # one position at a time
    rng = np.random.default_rng(0)
    ctrl = m.control(f, [0], window=1, rng=rng, draws=500)
    assert ctrl.shape == (500, 1) and set(np.round(ctrl[:, 0], 6)) <= set(np.round(f[:2], 6))
    c = m.compare(np.array([0.05]), np.full((10, 1), 0.01))
    assert np.isclose(c["excess"], 0.04) and c["p"] == 0.0
    lo, hi = m.day_ci(np.array([0.01, 0.03]), [5, 5], np.random.default_rng(1))
    assert np.isclose(lo, 0.02) and np.isclose(hi, 0.02)
