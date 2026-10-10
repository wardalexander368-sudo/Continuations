"""Which launches move? Early-flow features against the outcome of a trade with the default exit.

    python3 handoff/experiments/mover_study.py features OUT.pkl [OUT.pkl ...]   # -> scratch features table
    python3 handoff/experiments/mover_study.py test TABLE.pkl [--entry 20|60]

`exit_study.py extract` pickles (with trader indices, column 6) give every screened launch's full
path. For entry at +20 s or +60 s after the create, this builds causal features from the trades
up to the decision (buyer composition, wallet history across every recording, holder growth,
curve shape, the creator's behaviour, name), and the outcome of a trade at that moment with the
paper policy's default exit (TP +100%, 30 min, no stop) at Jupiter-route costs (1.25% per side,
0.02 SOL, 0.000011 SOL per transaction), plus whether any sale in 30 min cleared cost ("mover").

`test` trains LightGBM on the first 70% of dev launches (created before 16:00 UTC 10-09), picks
a top-fraction threshold on the last 30% of dev, and reports the test launches once, for every
feature group alone and together.
"""
from __future__ import annotations

import bisect
import math
import pickle
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "handoff/experiments")
from exit_study import TEST_FROM, Window, exit_time, fmt, stats  # noqa: E402

SIZE, FEE, NET, LAT = 0.02, 0.0125, 0.000011, 1.0
RULE = {"hold": 1800, "tp": 1.0}
ROUND = (0.1, 0.2, 0.25, 0.3, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0)


def load_all(pkls):
    best = {}
    for p in pkls:
        with open(p, "rb") as f:
            d = pickle.load(f)
        names = d["wallets"]
        for L in d["launches"]:
            path = d["paths"][L["mint"]]
            prev = best.get(L["mint"])
            if prev is not None and len(prev["path"]) >= len(path):
                continue
            stop = d["end"]
            for a, b in d["gaps"]:
                if a >= L["created"]:
                    stop = min(stop, a)
                    break
                if b > L["created"]:
                    stop = L["created"]
            if L["mint"] in d["aged"]:
                stop = min(stop, d["aged"][L["mint"]])
            wal = [names[int(i)] for i in path[:, 6]]
            best[L["mint"]] = {**L, "path": path, "wal": wal, "grad": d["graduated"].get(L["mint"]), "known_until": stop}
    return sorted(best.values(), key=lambda L: L["created"])


def wallet_index(launches):
    """wallet -> sorted times of its first buy in each launch (every recording, one copy per mint)."""
    firsts = defaultdict(list)
    for L in launches:
        seen = set()
        a = L["path"]
        for k in range(len(a)):
            w = L["wal"][k]
            if a[k, 3] > 0 and w not in seen and not a[k, 5]:
                seen.add(w)
                firsts[w].append(a[k, 0])
    for v in firsts.values():
        v.sort()
    return firsts


def features(L, T, firsts):
    a, wal = L["path"], L["wal"]
    t0 = L["created"]
    n = int(np.searchsorted(a[:, 0], t0 + T, side="right"))
    a, wal = a[:n], wal[:n]
    t, vsol, side, sol, cre = a[:, 0] - t0, a[:, 1], a[:, 3], a[:, 4], a[:, 5]
    rsol = vsol - 30.0
    buy = (side > 0) & (cre == 0)
    sell = (side < 0) & (cre == 0)
    f = {}
    # flow
    f["n_buys"] = int(buy.sum()); f["n_sells"] = int(sell.sum())
    f["buy_sol"] = float(sol[buy].sum()); f["sell_sol"] = float(sol[sell].sum())
    f["net_sol"] = f["buy_sol"] - f["sell_sol"]
    buyers = [wal[k] for k in np.flatnonzero(buy)]
    ub = list(dict.fromkeys(buyers))
    f["buyers"] = len(ub)
    f["sellers"] = len({wal[k] for k in np.flatnonzero(sell)})
    # holders: wallets with net tokens > 0 (approx by SOL in minus out)
    net = defaultdict(float)
    for k in range(len(a)):
        net[wal[k]] += sol[k] * side[k]
    f["holders"] = sum(1 for v in net.values() if v > 0)
    # buy sizes
    bs = sol[buy]
    f["buy_med"] = float(np.median(bs)) if len(bs) else 0.0
    f["buy_max_share"] = float(bs.max() / bs.sum()) if len(bs) and bs.sum() > 0 else 0.0
    f["round_share"] = float(np.mean([any(abs(x - r) < 0.0005 * r + 1e-9 for r in ROUND) for x in bs])) if len(bs) else 0.0
    f["small_share"] = float((bs < 0.05).mean()) if len(bs) else 0.0
    # timing / acceleration
    half = T / 2
    f["buyers_first_half"] = len({wal[k] for k in np.flatnonzero(buy & (t <= half))})
    f["buyers_second_half"] = len({wal[k] for k in np.flatnonzero(buy & (t > half))}) - 0
    f["accel"] = f["buyers_second_half"] - f["buyers_first_half"]
    f["buys_first2s_share"] = float(sol[buy & (t <= 2)].sum() / max(f["buy_sol"], 1e-9))
    f["last_trade_age"] = float(T - t[-1]) if len(t) else T
    # curve shape
    for q in (0.25, 0.5, 0.75, 1.0):
        j = int(np.searchsorted(t, q * T, side="right")) - 1
        f[f"rsol_{int(q * 100)}"] = float(rsol[j]) if j >= 0 else 0.0
    f["rsol_max"] = float(rsol.max()) if len(rsol) else 0.0
    f["drawdown"] = f["rsol_100"] / f["rsol_max"] if f["rsol_max"] > 0 else 1.0
    f["t_max"] = float(t[int(rsol.argmax())]) if len(rsol) else 0.0
    f["rise_last_q"] = f["rsol_100"] - f["rsol_75"]
    # creator
    f["dev_buy"] = float(sol[(cre == 1) & (side > 0)].sum())
    f["dev_sold"] = float(sol[(cre == 1) & (side < 0)].sum())
    f["dev_sold_share"] = f["dev_sold"] / f["dev_buy"] if f["dev_buy"] > 0 else 0.0
    f["dev_trades"] = int((cre == 1).sum())
    # wallet history (causal: first buys in other launches before the decision)
    cut = t0 + T
    counts = []
    for w in ub:
        ts = firsts.get(w, [])
        c = bisect.bisect_left(ts, cut)
        own = bisect.bisect_left(ts, t0)  # this launch's own first buy is at or after t0
        counts.append(c - (1 if c > own else 0))
    counts = np.array(counts, dtype=float)
    f["w_fresh_share"] = float((counts == 0).mean()) if len(counts) else 0.0
    f["w_bot_share"] = float((counts >= 20).mean()) if len(counts) else 0.0
    f["w_mid_share"] = float(((counts >= 1) & (counts < 20)).mean()) if len(counts) else 0.0
    f["w_log_mean"] = float(np.log1p(counts).mean()) if len(counts) else 0.0
    # name
    st = L["state"]
    f["name_len"] = len(st.get("name") or ""); f["sym_len"] = len(st.get("symbol") or "")
    f["sym_upper"] = int((st.get("symbol") or "").isupper())
    f["prug"] = L["prug"]
    f["flags_ok"] = int(not ({"concentrated", "sniped", "dev_bag"} & set(st["flags"])))
    f["creator_launches"] = st.get("creator_launches") or 0
    f["creator_rugs"] = st.get("creator_rugs") or 0
    return f


GROUPS = {
    "flow": ["n_buys", "n_sells", "buy_sol", "sell_sol", "net_sol", "buyers", "sellers", "last_trade_age"],
    "buyers+wallets": ["buyers", "buy_med", "buy_max_share", "round_share", "small_share", "buys_first2s_share", "w_fresh_share", "w_bot_share", "w_mid_share", "w_log_mean"],
    "holders+growth": ["holders", "buyers_first_half", "buyers_second_half", "accel", "last_trade_age"],
    "curve shape": ["rsol_25", "rsol_50", "rsol_75", "rsol_100", "rsol_max", "drawdown", "t_max", "rise_last_q"],
    "dev": ["dev_buy", "dev_sold", "dev_sold_share", "dev_trades", "creator_launches", "creator_rugs"],
    "name": ["name_len", "sym_len", "sym_upper"],
}
GROUPS["all"] = sorted({c for v in GROUPS.values() for c in v} | {"prug", "flags_ok"})


def build(pkls, out):
    launches = load_all(pkls)
    firsts = wallet_index(launches)
    rows = []
    for L in launches:
        for T in (20.0, 60.0):
            Lx = {**L, "t": L["created"] + T}
            w = Window(Lx, SIZE, FEE, NET, LAT)
            if w.tokens is None:
                continue
            ret = w.exit_at(exit_time(w, RULE), LAT, w.entry_t + RULE["hold"])
            if ret is None:
                continue
            ok = w.t + LAT + 5.0 <= w.ok_until  # (the whole 30 min is covered: exit_at checked it)
            best = (w.value[ok].max() - SIZE - 2 * NET) / SIZE if ok.any() else math.nan
            rows.append({"mint": L["mint"], "created": L["created"], "T": T, "ret": ret, "oracle": best, **features(L, T, firsts)})
    with open(out, "wb") as f:
        pickle.dump(rows, f)
    print(f"{len(rows)} rows from {len(launches)} launches")


def test(table, entry=20.0):
    import lightgbm as lgb

    with open(table, "rb") as f:
        rows = [r for r in pickle.load(f) if r["T"] == entry]
    rows.sort(key=lambda r: r["created"])
    dev = [r for r in rows if r["created"] < TEST_FROM]
    tst = [r for r in rows if r["created"] >= TEST_FROM]
    cut = int(0.7 * len(dev))
    tr, va = dev[:cut], dev[cut:]
    print(f"entry +{entry:g}s: train {len(tr)}, valid {len(va)}, test {len(tst)}")
    base = lambda part: np.array([r["ret"] for r in part])
    print(f"  buy all: valid {fmt(stats(base(va)))}\n           test  {fmt(stats(base(tst)))}")
    for g, cols in GROUPS.items():
        X = lambda part: np.array([[r[c] for c in cols] for r in part], dtype=float)
        for target in ("ret", "mover"):
            y = np.array([r["ret"] for r in tr]) if target == "ret" else np.array([r["oracle"] > 0 for r in tr], float)
            params = {"objective": "huber" if target == "ret" else "binary", "alpha": 0.2, "learning_rate": 0.03, "num_leaves": 15, "min_data_in_leaf": 100, "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "verbose": -1, "seed": 7, "num_threads": 2}
            m = lgb.train(params, lgb.Dataset(X(tr), y), num_boost_round=300)
            sv, st = m.predict(X(va)), m.predict(X(tst))
            yv = base(va); mv = np.array([r["oracle"] > 0 for r in va])
            auc = _auc(sv, mv)
            best = None
            for q in (0.5, 0.7, 0.8, 0.9, 0.95, 0.98):
                thr = np.quantile(sv, q)
                sel = yv[sv > thr]
                if len(sel) >= 50 and (best is None or sel.mean() > best[0]):
                    best = (sel.mean(), thr, q, len(sel))
            _, thr, q, nv = best
            yt = base(tst)[st > thr]
            mt = np.array([r["oracle"] > 0 for r in tst])
            print(f"  {g:15s} {target:5s} mover AUC valid {auc:.3f} test {_auc(st, mt):.3f} | top {100 * (1 - q):g}%: valid {100 * best[0]:+.2f}% (n={nv}) test {fmt(stats(yt))}")


def _auc(s, y):
    y = np.asarray(y, bool)
    if y.all() or not y.any():
        return math.nan
    r = np.argsort(np.argsort(s)) + 1
    return float((r[y].sum() - y.sum() * (y.sum() + 1) / 2) / (y.sum() * (~y).sum()))


if __name__ == "__main__":
    if sys.argv[1] == "features":
        build(sys.argv[3:], sys.argv[2])
    elif sys.argv[1] == "test":
        entry = float(sys.argv[sys.argv.index("--entry") + 1]) if "--entry" in sys.argv else 20.0
        test(sys.argv[2], entry)
