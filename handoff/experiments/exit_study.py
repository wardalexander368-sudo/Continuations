"""Exit rules, regime gating and sizing for the agent's launch trades (trading-skills audit, 2026-10-09).

    python3 handoff/experiments/exit_study.py extract DIR OUT.pkl   # one recorder directory
    python3 handoff/experiments/exit_study.py run OUT.pkl [OUT.pkl ...]

`extract` replays the fast loop on DIR with a policy that screens every launch at +20 s and buys
nothing (the exact live state, flags included), adds P(rug) from the installed `rug-20s` model,
and keeps every SOL curve's full trade path (time, reserves, side, size, creator or not), the
recorder's gaps (> 30 s) and graduations.

`run` trades the screened launches on those paths with causal exit rules, fills on the recorded
reserves after the execution latency (as `profit.round_trip`), and picks rules on the earlier
launches (dev) before reporting the later ones (test, launches created from 16:00 UTC on
2026-10-09, after the installed P(rug) model's training data). A trade is dropped only when the
recorder was down during it.
"""
from __future__ import annotations

import math
import pickle
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")

SCREEN = 20.0
GAP = 30.0


def extract(directory: str, out: str) -> None:
    from tartar.data.rawlog import raw_files, read_events
    from tartar.rug import _screens, find_rug_model

    paths: dict[str, list] = defaultdict(list)
    creators: dict[str, tuple[float, str]] = {}
    graduated: dict[str, float] = {}
    aged: dict[str, float] = {}  # the recorder stopped following the token (tracking limit): price unknown after
    times = []
    for e in read_events(raw_files(directory)):
        times.append(e["t"])
        if e.get("quote"):
            continue
        kind = e["e"]
        if kind == "create":
            creators[e["mint"]] = (e["t"], e.get("creator") or "")
            if e.get("vsol") and e.get("vtok"):
                paths[e["mint"]].append((e["t"], e["vsol"], e["vtok"], 1, e.get("sol") or 0.0, 1))
        elif kind == "trade" and e.get("vsol") and e.get("vtok"):
            creator = creators.get(e["mint"], (0, ""))[1]
            paths[e["mint"]].append((e["t"], e["vsol"], e["vtok"], 1 if e.get("side") == "b" else -1, e.get("sol") or 0.0, int(bool(creator) and e.get("trader") == creator)))
        elif kind in ("migrate", "graduate"):
            graduated.setdefault(e["mint"], e["t"])
        elif kind == "untrack" and e.get("reason") == "age":
            aged.setdefault(e["mint"], e["t"])
    times.sort()
    gaps = [(a, b) for a, b in zip(times, times[1:]) if b - a > GAP]
    arrays = {}
    for mint, rows in paths.items():
        rows.sort(key=lambda r: r[0])
        a = np.array(rows, dtype=float)
        arrays[mint] = a
    screens = _screens(directory, SCREEN)
    model = find_rug_model()
    states = [r["state"] for r in screens]
    prug = model.predict_many(states) if states and model is not None else np.full(len(states), np.nan)
    launches = []
    for r, p in zip(screens, prug):
        if r["mint"] not in arrays or r["mint"] not in creators:
            continue
        launches.append({"mint": r["mint"], "t": r["t"], "created": creators[r["mint"]][0], "state": r["state"], "prug": float(p), "dir": directory})
    with open(out, "wb") as f:
        pickle.dump({"dir": directory, "launches": launches, "paths": arrays, "graduated": graduated, "aged": aged, "gaps": gaps, "end": times[-1] if times else 0.0}, f)
    print(f"{directory}: {len(launches)} screened launches, {len(arrays)} paths, {len(gaps)} gaps")


# ---------------------------------------------------------------- trading the paths

TEST_FROM = 1791561600.0  # 2026-10-09 16:00 UTC
HAIRCUT = 0.10  # a position open at graduation is valued at the last curve price less this (fast-loop default)
MAX_AFTER = 1800.0  # no exit later than this after entry


def load(pkls: list[str]) -> list[dict]:
    """Screened launches with their paths, one copy per mint (the recording with the most trades for it)."""
    best: dict[str, dict] = {}
    for p in pkls:
        with open(p, "rb") as f:
            d = pickle.load(f)
        for L in d["launches"]:
            path = d["paths"][L["mint"]]
            prev = best.get(L["mint"])
            if prev is not None and len(prev["path"]) >= len(path):
                continue
            stop = d["end"]
            for a, b in d["gaps"]:
                if a >= L["t"]:
                    stop = min(stop, a)
                    break
                if b > L["t"]:  # inside a gap: unusable
                    stop = L["t"]
            if L["mint"] in d["aged"]:
                stop = min(stop, d["aged"][L["mint"]])
            best[L["mint"]] = {**L, "path": path, "grad": d["graduated"].get(L["mint"]), "known_until": stop}
    out = sorted(best.values(), key=lambda L: L["created"])
    return out


class Window:
    """One launch's path from the entry on, with the position's sale value at every recorded state."""

    __slots__ = ("t", "price", "value", "side", "sol", "creator", "rsol", "entry_t", "ok_until", "tokens", "size", "net")

    def __init__(self, L: dict, size: float, fee: float, net: float, latency: float):
        a = L["path"]
        t_in = L["t"] + latency
        i = int(np.searchsorted(a[:, 0], t_in, side="right")) - 1
        self.tokens = None
        if i < 0 or (L["grad"] is not None and L["grad"] <= t_in):
            return
        vsol, vtok = a[i, 1], a[i, 2]
        sol_in = size * (1 - fee)
        self.tokens = vtok * sol_in / (vsol + sol_in)
        end = t_in + MAX_AFTER
        j = int(np.searchsorted(a[:, 0], end, side="right"))
        w = a[i:j]
        self.t, self.side, self.sol, self.creator = w[:, 0], w[:, 3], w[:, 4], w[:, 5]
        self.price = w[:, 1] / w[:, 2]
        self.rsol = w[:, 1] - 30.0
        self.value = w[:, 1] * self.tokens / (w[:, 2] + self.tokens) * (1 - fee)
        self.entry_t, self.size, self.net = t_in, size, net
        g = L["grad"]
        if g is not None and g <= end:
            k = int(np.searchsorted(self.t, g, side="right"))  # states after graduation: sold on the pool at a haircut
            self.value[k:] = self.value[max(k - 1, 0)] * (1 - HAIRCUT)
        self.ok_until = L["known_until"]

    def exit_at(self, t_decide: float, latency: float) -> float | None:
        """Net return of selling at the state `latency` after `t_decide`; None if unknown then."""
        t_out = t_decide + latency
        if t_out + 5.0 > self.ok_until:
            return None
        k = int(np.searchsorted(self.t, t_out, side="right")) - 1
        return (self.value[k] - self.size - 2 * self.net) / self.size


def first(mask: np.ndarray) -> int | None:
    return int(mask.argmax()) if mask.any() else None


def exit_time(w: Window, rule: dict) -> float:
    """When the rule decides to sell (a trade's time), or the max hold."""
    deadline = w.entry_t + rule["hold"]
    n = int(np.searchsorted(w.t, deadline, side="right"))
    if n <= 1:
        return deadline
    t, price = w.t[1:n], w.price[1:n]
    cands = [deadline]
    fill_price = w.size / w.tokens
    if rule.get("tp"):
        k = first(price >= fill_price * (1 + rule["tp"]))
        if k is not None:
            cands.append(t[k])
    if rule.get("sl"):
        k = first(price <= fill_price * (1 - rule["sl"]))
        if k is not None:
            cands.append(t[k])
    if rule.get("trail"):
        peak = np.maximum.accumulate(np.concatenate([[w.price[0]], price]))[1:]
        k = first(price <= peak * (1 - rule["trail"]))
        if k is not None:
            cands.append(t[k])
    if rule.get("dev"):
        k = first((w.creator[1:n] == 1) & (w.side[1:n] < 0))
        if k is not None:
            cands.append(t[k])
    if rule.get("dump"):
        rs = np.maximum(w.rsol[0:n - 1], 0.5)  # real SOL in the curve before each trade
        k = first((w.side[1:n] < 0) & (w.sol[1:n] >= rule["dump"] * rs))
        if k is not None:
            cands.append(t[k])
    return min(cands)


def stats(v: np.ndarray, rng=None, boots: int = 2000) -> dict:
    if len(v) == 0:
        return {"n": 0}
    rng = rng or np.random.default_rng(0)
    means = v[rng.integers(0, len(v), (boots, len(v)))].mean(axis=1)  # one trade per launch
    lo, hi = np.quantile(means, [0.05, 0.95])
    return {"n": len(v), "mean": float(v.mean()), "lo": float(lo), "hi": float(hi), "median": float(np.median(v)), "win": float((v > 0).mean())}


def fmt(s: dict) -> str:
    if not s.get("n"):
        return "no trades"
    return f"{100 * s['mean']:+6.2f}% [{100 * s['lo']:+6.2f}, {100 * s['hi']:+6.2f}] n={s['n']:5d} med {100 * s['median']:+6.2f}% win {100 * s['win']:4.1f}%"


def rules() -> list[dict]:
    out = []
    for hold in (60, 180, 600, 1800):
        for trail in (None, 0.1, 0.2, 0.35, 0.5):
            for tp in (None, 0.3, 1.0):
                for dev in (False, True):
                    for dump in (None, 0.1, 0.25):
                        out.append({"hold": hold, "trail": trail, "tp": tp, "dev": dev, "dump": dump})
    return out


def label(r: dict) -> str:
    parts = [f"hold {r['hold']}s"]
    if r.get("tp"):
        parts.append(f"TP +{100 * r['tp']:g}%")
    if r.get("sl"):
        parts.append(f"SL -{100 * r['sl']:g}%")
    if r.get("trail"):
        parts.append(f"trail {100 * r['trail']:g}%")
    if r.get("dev"):
        parts.append("dev-sell")
    if r.get("dump"):
        parts.append(f"dump>{100 * r['dump']:g}%")
    return ", ".join(parts)


FILTERS = {
    "every launch": lambda L: True,
    "live skip flags": lambda L: not ({"concentrated", "sniped", "dev_bag"} & set(L["state"]["flags"])),
    "P(rug) < 0.1": lambda L: L["prug"] < 0.1,
    "flags + P(rug) < 0.1": lambda L: L["prug"] < 0.1 and not ({"concentrated", "sniped", "dev_bag"} & set(L["state"]["flags"])),
}


def run(pkls: list[str], fee: float = 0.0125, size: float = 0.1, net: float = 0.0002, latency: float = 1.0) -> None:
    launches = load(pkls)
    print(f"{len(launches)} launches; dev {sum(L['created'] < TEST_FROM for L in launches)}, test {sum(L['created'] >= TEST_FROM for L in launches)}; fee {fee}, size {size}, latency {latency}")
    wins = [Window(L, size, fee, net, latency) for L in launches]
    keep = [(L, w) for L, w in zip(launches, wins) if w.tokens is not None]
    rs = rules()
    rng = np.random.default_rng(0)
    for fname, f in FILTERS.items():
        sel = [(L, w) for L, w in keep if f(L)]
        dev = [(L, w) for L, w in sel if L["created"] < TEST_FROM]
        test = [(L, w) for L, w in sel if L["created"] >= TEST_FROM]
        # oracle: the best sale inside 30 minutes, decided with hindsight (upper bound on any exit rule)
        def oracle(part):
            v = []
            for L, w in part:
                ok = w.t + latency + 5.0 <= w.ok_until
                if ok.any():
                    v.append((w.value[ok].max() - w.size - 2 * w.net) / w.size)
            return np.array(v)
        print(f"\n== {fname}: dev {len(dev)}, test {len(test)}")
        print(f"  oracle exit (hindsight, 30 min)   dev {fmt(stats(oracle(dev), rng))}")
        results = []
        for r in rs:
            dv = [w.exit_at(exit_time(w, r), latency) for L, w in dev]
            dv = np.array([x for x in dv if x is not None])
            results.append((r, dv))
        base = {r["hold"]: dv for r, dv in results if not r["trail"] and not r["tp"] and not r["dev"] and not r["dump"]}
        for h, dv in base.items():
            print(f"  baseline hold {h:5d}s            dev {fmt(stats(dv, rng))}")
        results.sort(key=lambda x: -x[1].mean() if len(x[1]) >= 100 else 1e9)
        print("  top 5 rules on dev:")
        for r, dv in results[:5]:
            print(f"    {label(r):45s} dev {fmt(stats(dv, rng))}")
        best = results[0][0]
        tv = np.array([x for x in (w.exit_at(exit_time(w, best), latency) for L, w in test) if x is not None])
        print(f"  TEST, best dev rule ({label(best)}): {fmt(stats(tv, rng))}")
        for h in (180, 600):
            r0 = {"hold": h}
            tv0 = np.array([x for x in (w.exit_at(exit_time(w, r0), latency) for L, w in test) if x is not None])
            print(f"  TEST, baseline hold {h}s: {fmt(stats(tv0, rng))}")
        print(f"  TEST oracle: {fmt(stats(oracle(test), rng))}")


if __name__ == "__main__" and len(sys.argv) > 1:
    if sys.argv[1] == "extract":
        extract(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "run":
        args = sys.argv[2:]
        kw = {}
        while args and args[0].startswith("--"):
            kw[args[0][2:]] = float(args[1])
            args = args[2:]
        run(args, **kw)
