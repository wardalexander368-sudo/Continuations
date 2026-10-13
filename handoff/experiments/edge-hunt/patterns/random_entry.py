"""Random-entry control for the US-spot patterns (plan A2 / E2, 2026-10-13).

Does `us_capit` / `us_volspike` beat buying the same coin at a random hour with the same hold and cost? Same data
and entry timing as wide_coins.py (Coinbase hourly candles 2023-01..2026-10, buy the close of the hour after the
signal, sell H hours later, 0.39%/side Alpaca cost). Signals are the agent's own (coinbase_pattern.signals).

Two matched controls, 2,000 draws each (seed 1). Every signal trade is swapped for a random entry hour on the
same coin:
  * local: within +-15 days of the signal (same market regime, so it separates the bounce from drift);
  * any:   anywhere in 2023-2026 (unconditional buy-and-hold over H hours).
For each control: its mean net per trade, the pattern's excess over it, and p = share of draws whose mean is at
least the pattern's (one-sided). Trades cluster on a few crash days, so p alone overstates the evidence; the
honest number is the 90% CI of the excess, bootstrapped over entry days (each trade minus its own control mean).
Reporting only; registered verdicts are unchanged.

    python handoff/experiments/edge-hunt/patterns/random_entry.py CACHE_DIR
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from wide_coins import COST, EXTRA, T0, T1, fetch  # noqa: E402
from tartar.autotrade.strategies.coinbase_pattern import COINS, RULES, signals  # noqa: E402

LOCAL, DRAWS = 15 * 24, 2000


def series(d: dict):
    n = T1 - T0
    C, V = np.full(n, np.nan), np.zeros(n)
    for k, (c, v) in d.items():
        i = int(k) - T0
        if 0 <= i < n:
            C[i], V[i] = c, v
    return C, V


def forward(C: np.ndarray, H: int) -> np.ndarray:
    """Net return of buying the close of hour h+1 and selling the close of hour h+1+H."""
    n = len(C)
    f = np.full(n, np.nan)
    f[:n - 1 - H] = C[1 + H:] / C[1:n - H] - 1 - 2 * COST
    return f


def entries(sig: np.ndarray, fwd: np.ndarray, H: int) -> list[int]:
    """Signal hours, one position at a time (as wide_coins.py and the agent)."""
    out, busy = [], -1
    for h in np.where(sig)[0]:
        if h < busy or np.isnan(fwd[h]):
            continue
        out.append(int(h))
        busy = h + H + 1
    return out


def control(fwd: np.ndarray, hours: list[int], window: int | None, rng, draws: int = DRAWS) -> np.ndarray:
    """draws x len(hours) matrix of random-entry net returns on the same coin (window=None: any hour)."""
    ok = np.where(~np.isnan(fwd))[0]
    out = np.empty((draws, len(hours)))
    for j, h in enumerate(hours):
        pool = ok if window is None else ok[(ok >= h - window) & (ok <= h + window)]
        out[:, j] = fwd[rng.choice(pool, draws)]
    return out


def compare(actual: np.ndarray, ctrl: np.ndarray) -> dict:
    m, cm = float(actual.mean()), ctrl.mean(1)
    return {"n": len(actual), "net": m, "ctrl": float(cm.mean()), "excess": m - float(cm.mean()),
            "p": float((cm >= m).mean())}


def run(coins: list[str], cache: Path, rng) -> dict:
    res = {r: {"act": [], "local": [], "any": [], "day": []} for r in RULES}
    for coin in coins:
        C, V = series(fetch(coin, cache))
        for rule, spec in RULES.items():
            fwd = forward(C, spec["hold"])
            hs = entries(signals(rule, C, V), fwd, spec["hold"])
            if not hs:
                continue
            res[rule]["act"].append(fwd[hs])
            res[rule]["local"].append(control(fwd, hs, LOCAL, rng))
            res[rule]["any"].append(control(fwd, hs, None, rng))
            res[rule]["day"] += [(T0 + h) // 24 for h in hs]
    return res


def day_ci(x: np.ndarray, days: list[int], rng) -> tuple[float, float]:
    """90% bootstrap CI of mean(x), resampling whole entry days."""
    keys = sorted(set(days))
    s = np.array([x[[d == k for d in days]].sum() for k in keys])
    c = np.array([days.count(k) for k in keys])
    pick = rng.integers(0, len(keys), (10000, len(keys)))
    lo, hi = np.percentile(s[pick].sum(1) / c[pick].sum(1), [5, 95])
    return float(lo), float(hi)


def fmt(rule: str, r: dict) -> str:
    if not r["act"]:
        return f"{rule}: no trades"
    a = np.concatenate(r["act"])
    lines = [f"{rule}: {len(a)} trades on {len(set(r['day']))} days, net {a.mean()*100:+.2f}%/trade"]
    for k in ("local", "any"):
        ctrl = np.concatenate(r[k], axis=1)
        c = compare(a, ctrl)
        lo, hi = day_ci(a - ctrl.mean(0), r["day"], np.random.default_rng(1))
        lines.append(f"  vs random {k:5s}: random {c['ctrl']*100:+.2f}%, excess {c['excess']*100:+.2f}% "
                     f"[{lo*100:+.2f}, {hi*100:+.2f}] by day, p={c['p']:.3f}")
    return "\n".join(lines)


if __name__ == "__main__":
    cache = Path(sys.argv[1])
    cache.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1)
    for label, group in (("study 11 coins", COINS), ("10 extra US coins (out of sample)", EXTRA)):
        res = run(group, cache, rng)
        print(f"\n## {label}")
        for rule in RULES:
            print(fmt(rule, res[rule]))
