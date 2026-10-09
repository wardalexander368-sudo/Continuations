"""Re-simulate the direction calibrator offline on blend_calibration.py output (all rows, in token order).

    python3 handoff/experiments/blend_calibration_sim.py FILE.jsonl

Checks the re-simulation against the replay, then scores calibrator variants on trading candles
(selection hours 12-13, confirmation 14-16) and on all candles (predictor doc 8.4.1).
"""
import json, sys, math, datetime
from collections import deque
import numpy as np

def lg(p): p = min(max(p, 1e-9), 1 - 1e-9); return math.log(p / (1 - p))
def sg(x): return 1 / (1 + math.exp(-x))

class Cal:
    def __init__(self, hi=1.0, k=50.0, discount=0.995, window=1000):
        self.k, self.d, self.hi, self.obs, self.a = k, discount, hi, deque(maxlen=window), 1.0
    def update(self, L, up):
        self.obs.append((min(max(L, -3.0), 3.0), 1.0 if up else 0.0))
        Ls, Y = np.array(self.obs).T
        W = self.d ** np.arange(len(Ls) - 1, -1, -1)
        m = max(float(np.sum(W * Ls * Ls) / np.sum(W)), 1e-2); h0 = self.k * m / 4.0; a = self.a
        for _ in range(3):
            p = 0.5 * (1.0 + np.tanh(0.5 * a * Ls))
            a += (float(np.sum(W * (Y - p) * Ls)) - h0 * (a - 1.0)) / (float(np.sum(W * p * (1 - p) * Ls * Ls)) + h0)
        self.a = min(self.hi, max(0.0, a))

rows = [json.loads(l) for l in open(sys.argv[1])]
hour = lambda r: datetime.datetime.fromtimestamp(r["t"], datetime.UTC).hour
VARIANTS = {"current (a<=1, full)": (1.0, False), "(A) a<=1, x(1-w)": (1.0, True),
            "a<=1.5, full": (1.5, False), "a<=2, full": (2.0, False), "a<=1.5, x(1-w)": (1.5, True)}
def run(hi, share):
    out = []; cal = None; mint = None
    for r in rows:
        if r["mint"] != mint: mint, cal = r["mint"], Cal(hi=hi)
        L = lg(r["q_raw"]); a = 1 + (cal.a - 1) * ((1 - r["w"]) if share else 1.0)
        out.append(sg(a * L))
        if r["actual"] != "flat": cal.update(L, r["actual"] == "up")
    return np.array(out)
check = run(1.0, False); fq = np.array([r["p_up"] / max(r["p_up"] + r["p_down"], 1e-12) for r in rows])
print("re-simulation matches the replay:", np.allclose(check, fq, atol=1e-6), np.abs(check - fq).max())
m = np.array([r["p_flat"] for r in rows]); act = np.array([{"up": 0, "down": 1, "flat": 2}[r["actual"]] for r in rows])
trading = np.array([r["trading"] for r in rows]); hrs = np.array([hour(r) for r in rows])
def score(q, mask):
    P = np.stack([(1 - m) * q, (1 - m) * (1 - q), m], 1)[mask]; a = act[mask]
    return (P.argmax(1) == a).mean() - P.max(1).mean(), -np.mean(np.log(np.clip(P[np.arange(len(a)), a], 1e-12, 1)))
for name, (hi, share) in VARIANTS.items():
    q = run(hi, share); line = [name.ljust(22)]
    for label, mask in (("val 12-13", trading & (hrs <= 13)), ("test 14-16", trading & (hrs >= 14)), ("all candles", np.ones_like(trading))):
        g, ll = score(q, mask); line.append(f"{label}: gap {g:+.4f} ll {ll:.4f}")
    print("  ".join(line))
