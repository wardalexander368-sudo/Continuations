"""Edge hunt F (edge-hunt.md): pump.fun signals from *who* trades. Dev launches only unless --test.

    python3 handoff/experiments/who_trades.py OUT.pkl [OUT.pkl ...]          # exit_study.py extract pickles
    python3 handoff/experiments/who_trades.py --test SPEC.json OUT.pkl ...   # the pre-registered rule, once

Path rows (exit_study.extract): time, virtual SOL, virtual tokens, side (+1 buy / -1 sell), SOL,
creator flag, wallet index (per pickle; mapped to addresses here). Tokens per trade are the change
in virtual token reserves from the previous state.

* F1, who sold the dip: §3.23's signal (price >= d below its running peak, once the peak's real SOL
  reached X, within 30 min of the create). `conc` = share of the sell SOL between the peak and the
  signal from the creator and the top seller; `done` = those wallets now hold <= 5% of the most
  they held.
* F2, who buys the dip: a wallet's causal track record = mean of (price 120 s after each of its buys
  / its buy price - 1) over buys whose 120 s resolved before this signal, on other launches, shrunk
  as sum / (n + 5); `smart` = a wallet with >= 5 such buys and score > 0.05 bought between the peak
  and the signal.
* F3, overhang left: the bundle = wallets (creator included) that bought within 2 s of the create.
  Signal = the first trade after +60 s at which the bundle holds <= h of the most it held and >= k
  distinct other wallets bought in the last 30 s.

Each signal buys 1 s later at 0.02 SOL, 1.25%/side (Jupiter / own instructions), and exits by TP or
max hold (exit_study.Window). Dev = created before 16:00 UTC 10-09; rules are chosen on dev's first
60% and checked on its last 40%.
"""
from __future__ import annotations

import itertools
import json
import pickle
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "handoff/experiments")
from exit_study import TEST_FROM, Window, exit_time, fmt, stats  # noqa: E402

SIZE, FEE, NET, LAT = 0.02, 0.0125, 0.000011, 1.0
LTN_FEE, LTN_LAT = 0.0225, 1.4


def load(pkls):
    """exit_study.load, plus each path's wallet addresses."""
    best: dict[str, dict] = {}
    for p in pkls:
        with open(p, "rb") as f:
            d = pickle.load(f)
        names = np.array(d["wallets"], dtype=object)
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
                if b > L["t"]:
                    stop = L["t"]
            if L["mint"] in d["aged"]:
                stop = min(stop, d["aged"][L["mint"]])
            best[L["mint"]] = {**L, "path": path, "who": names[path[:, 6].astype(int)], "grad": d["graduated"].get(L["mint"]), "known_until": stop}
    return sorted(best.values(), key=lambda L: L["created"])


def token_flows(a):
    """Tokens moved by each row: the drop (buy) or rise (sell) in virtual token reserves."""
    dt = np.zeros(len(a))
    dt[1:] = a[:-1, 2] - a[1:, 2]
    return np.abs(dt)


def holdings(who, side, tok, upto):
    h: dict = defaultdict(float)
    peak: dict = defaultdict(float)
    for i in range(upto + 1):
        h[who[i]] += side[i] * tok[i]
        peak[who[i]] = max(peak[who[i]], h[who[i]])
    return h, peak


def track_records(launches):
    """Every buy's (wallet, resolve time, 120 s return), for causal wallet scores."""
    rec = []
    for n, L in enumerate(launches):
        a = L["path"]
        price = a[:, 1] / a[:, 2]
        for i in np.flatnonzero(a[:, 3] > 0):
            j = int(np.searchsorted(a[:, 0], a[i, 0] + 120, side="right")) - 1
            if a[i, 0] + 120 <= min(L["known_until"], a[-1, 0] + 600):
                rec.append((L["who"][i], a[i, 0] + 120, price[j] / price[i] - 1, n))
    rec.sort(key=lambda r: r[1])
    return rec


class Scores:
    """Causal wallet scores: advance(t) folds in every buy resolved before t."""

    def __init__(self, rec):
        self.rec, self.k, self.sum, self.n, self.by_launch = rec, 0, defaultdict(float), defaultdict(int), defaultdict(list)

    def advance(self, t):
        while self.k < len(self.rec) and self.rec[self.k][1] < t:
            w, _, r, n = self.rec[self.k]
            self.sum[w] += r
            self.n[w] += 1
            self.by_launch[(w, n)].append(r)
            self.k += 1

    def smart(self, w, launch):
        own = self.by_launch.get((w, launch), [])
        n = self.n[w] - len(own)
        s = self.sum[w] - sum(own)
        return n >= 5 and s / (n + 5) > 0.05


def dip_signals(launches, X, d):
    out = []
    for n, L in enumerate(launches):
        a = L["path"]
        a_ok = a[:, 0] <= L["created"] + 1800
        if a_ok.sum() < 2:
            continue
        price = a[:, 1] / a[:, 2]
        rs = a[:, 1] - 30.0
        best, peak_i = 0, np.zeros(len(a), int)
        for i in range(len(a)):
            if price[i] > price[best]:
                best = i
            peak_i[i] = best
        k = np.flatnonzero(a_ok & (rs[peak_i] >= X) & (price <= (1 - d) * price[peak_i]))
        if len(k):
            out.append((n, int(k[0]), int(peak_i[k[0]])))
    return out


def f1_f2(launches, sig, scores):
    feats = [None] * len(sig)
    for m in sorted(range(len(sig)), key=lambda m: launches[sig[m][0]]["path"][sig[m][1], 0]):  # time order: scores only advance
        n, i, p = sig[m]
        L = launches[n]
        a, who = L["path"], L["who"]
        side, sol, tok = a[:, 3], a[:, 4], token_flows(a)
        sells = defaultdict(float)
        for j in range(p + 1, i + 1):
            if side[j] < 0:
                sells[who[j]] += sol[j]
        total = sum(sells.values())
        creator = who[0]
        top = sorted((w for w in sells if w != creator), key=lambda w: -sells[w])[:1] + [creator]
        conc = sum(sells.get(w, 0.0) for w in top) / total if total > 0 else 0.0
        h, peak = holdings(who, side, tok, i)
        done = all(h[w] <= 0.05 * peak[w] for w in top if peak[w] > 0)
        scores.advance(a[i, 0])
        smart = any(side[j] > 0 and scores.smart(who[j], n) for j in range(p + 1, i + 1))
        feats[m] = {"conc": conc, "done": done, "smart": smart}
    return feats


def f3_signals(launches, hmax, kmin):
    out = []
    for n, L in enumerate(launches):
        a, who = L["path"], L["who"]
        t0 = L["created"]
        side, tok = a[:, 3], token_flows(a)
        bundle = {who[j] for j in range(len(a)) if a[j, 0] <= t0 + 2 and side[j] > 0}
        held = peak = 0.0
        recent: list = []
        for j in range(len(a)):
            if a[j, 0] > t0 + 1800:
                break
            if who[j] in bundle:
                held += side[j] * tok[j]
                peak = max(peak, held)
            elif side[j] > 0:
                recent.append((a[j, 0], who[j]))
            if a[j, 0] < t0 + 60 or peak <= 0:
                continue
            recent = [r for r in recent if r[0] >= a[j, 0] - 30]
            if held <= hmax * peak and len({w for _, w in recent}) >= kmin:
                out.append((n, j, j))
                break
    return out


def trade(launches, sig, rule, fee=FEE, lat=LAT):
    vals = np.full(len(sig), np.nan)
    for m, (n, i, _) in enumerate(sig):
        L = {**launches[n], "t": float(launches[n]["path"][i, 0])}
        w = Window(L, SIZE, fee, NET, lat)
        if w.tokens is None:
            continue
        v = w.exit_at(exit_time(w, rule), lat, w.entry_t + rule["hold"])
        if v is not None:
            vals[m] = v
    return vals


EXITS = [{"tp": tp, "hold": hold} for tp, hold in itertools.product((0.3, 1.0), (180, 600))]


def explore(launches):
    dev = [L for L in launches if L["created"] < TEST_FROM]
    cut = dev[int(0.6 * len(dev))]["created"]
    print(f"{len(dev)} dev launches; choose < {cut:.0f}, check after", flush=True)
    scores = Scores(track_records(dev))
    rows = []
    for X, d in itertools.product((20, 40), (0.5, 0.7)):
        sig = dip_signals(dev, X, d)
        feats = f1_f2(dev, sig, Scores(scores.rec))
        conc = np.array([f["conc"] for f in feats])
        done = np.array([f["done"] for f in feats])
        smart = np.array([f["smart"] for f in feats])
        early = np.array([dev[n]["created"] < cut for n, _, _ in sig])
        med = float(np.median(conc[early])) if early.any() else 0.5
        subsets = {"all": np.ones(len(sig), bool), "conc>med": conc > med, "conc<=med": conc <= med,
                   "conc>med & done": (conc > med) & done, "done": done, "not done": ~done,
                   "smart bought": smart, "no smart": ~smart}  # fmt: skip
        print(f"\nF1/F2 dip X {X} d {d}: {len(sig)} signals, conc median {med:.2f}, done {done.mean():.2f}, smart {smart.mean():.2f}")
        for r in EXITS:
            v = trade(dev, sig, r)
            for name, m in subsets.items():
                a, b = v[m & early], v[m & ~early]
                a, b = a[np.isfinite(a)], b[np.isfinite(b)]
                rows.append((f"F1/2 X{X} d{d} TP{r['tp']} {r['hold']}s {name}", a, b))
                print(f"  TP {r['tp']} hold {r['hold']:4d} {name:<16} choose {fmt(stats(a))}  |  check {fmt(stats(b))}", flush=True)
    for hmax, kmin in itertools.product((0.05, 0.2), (3, 10)):
        sig = f3_signals(dev, hmax, kmin)
        early = np.array([dev[n]["created"] < cut for n, _, _ in sig])
        print(f"\nF3 bundle <= {hmax} of peak, >= {kmin} other buyers in 30 s: {len(sig)} signals")
        for r in EXITS:
            v = trade(dev, sig, r)
            a, b = v[early], v[~early]
            a, b = a[np.isfinite(a)], b[np.isfinite(b)]
            rows.append((f"F3 h{hmax} k{kmin} TP{r['tp']} {r['hold']}s", a, b))
            print(f"  TP {r['tp']} hold {r['hold']:4d} choose {fmt(stats(a))}  |  check {fmt(stats(b))}", flush=True)
    ok = [r for r in rows if len(r[1]) >= 100]
    print("\nbest 8 on 'choose' (n >= 100), with their 'check':")
    for name, a, b in sorted(ok, key=lambda r: -r[1].mean())[:8]:
        print(f"  {name:<44} choose {fmt(stats(a))}  |  check {fmt(stats(b))}")


def test(spec_path, pkls):
    """The pre-registered rule (preregistration/who-trades/SPEC.json) on launches created >= its test_from, once."""
    spec = json.load(open(spec_path))
    launches = [L for L in load(pkls) if L["created"] >= spec["test_from_unix"]]
    sig = dip_signals(launches, spec["peak_real_sol"], spec["dip"])
    rec = track_records(launches)
    feats = f1_f2(launches, sig, Scores(rec))
    take = [s for s, f in zip(sig, feats) if f["conc"] > spec["conc_above"]]
    rule = {"tp": spec["take_profit"], "hold": spec["max_hold_s"]}
    print(f"{len(launches)} test launches, {len(sig)} dip signals, {len(take)} with conc > {spec['conc_above']}")
    for name, fee, lat in (("PRIMARY (curve fees 1.25%/side, 1 s)", FEE, LAT), ("secondary: Lightning (+1%/side, 1.4 s)", LTN_FEE, LTN_LAT)):
        v = trade(launches, take, rule, fee, lat)
        v = v[np.isfinite(v)]
        print(f"  {name}: {fmt(stats(v))}")
    base = trade(launches, sig, rule)
    print(f"  every dip signal (no conc filter), curve fees: {fmt(stats(base[np.isfinite(base)]))}")


if __name__ == "__main__":
    if sys.argv[1] == "--test":
        test(sys.argv[2], sys.argv[3:])
    else:
        explore(load(sys.argv[1:]))
