"""Smallest Hyperliquid account the recommended perps book can run on (paper only, no orders).

    python3 handoff/experiments/perps_min_account.py      # needs data/momentum-audit/panel.pkl (momentum_audit.py panel)

Book (STATUS 2026-10-10, perps_book.py): equal weights, 1/4 each to xs_momentum, vol_momentum, the
search winner (cand) and HLP; the book scaled to ~2%/week trailing vol (x0.5 .. x1.5). A momentum
sleeve with weight a runs $a x scale x account per side, split equally over its q coins.

Per account size: the per-coin order sizes every week (opens and closes are whole positions; a kept
coin's weight change is a resize, skipped if under the minimum), how many fall under Hyperliquid's $10
minimum order value, and the weekly dollars at 6 bps per side (live book walk, momentum_audit.py
books) with funding, under two return cases: backtest (cand's selection haircut of 0.33 pts/wk) and
conservative (the same book without its best 5 weeks). Bad week = the 5th-percentile week and the
worst week of the backtest, in dollars.
"""
import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
sys.argv = sys.argv[:1]
src = Path(__file__).with_name("perps_book.py").read_text().replace("\nmain()\n", "\n")
pb: dict = {"__name__": "perps_book"}
exec(compile(src, "perps_book.py", "exec"), pb)

MIN_ORDER = 10.0
COST = 0.0006
TARGET = 0.02
CAND_HAIRCUT = 0.0033
SIZES = (200, 500, 1000, 2000, 5000)


def main():
    d = pickle.loads(Path("data/momentum-audit/panel.pkl").read_bytes())
    P = pb["Panel"](d["days"], d["coins"], d["C"], d["V"], pb["hl_data"].load_funding(Path("autotrade/search/funding_daily.csv")))
    pb["COST"] = COST
    import tartar.autotrade.search as search
    search.COST = COST
    lg = {}
    for s, p in pb["RULES"].items():
        pb["legs"].__globals__["COST"] = COST
        lg[s] = pb["legs"](P, p)
    weeks = sorted(set.intersection(*(set(v) for v in lg.values())))
    hlp = pb["hlp_weekly"](weeks)
    weeks = [w for w in weeks if w in hlp]
    # cand selection haircut: subtract from each of its legs' return (long legs lower, short legs higher)
    lg_adj = dict(lg)
    lg_adj["cand"] = {w: ([(j, s, wt, r - s * CAND_HAIRCUT / 2, f) for j, s, wt, r, f in legs_], c) for w, (legs_, c) in lg["cand"].items()}
    pb["WEIGHTS"].clear()
    r = pb["book"](lg_adj, hlp, weeks, "vol_target", None, target=TARGET)
    scales = [w["xs_momentum"] / 0.25 for w in pb["WEIGHTS"]]
    m = pb["summary"](r, weeks)
    p5 = float(np.percentile(r, 5))
    print(f"Book at 6 bps/side, cand haircut {100 * CAND_HAIRCUT:.2f} pts: mean {m['mean']:+.2f}%/wk (last 26 wk {100 * r[-26:].mean():+.2f}), "
          f"without best 5 wks {m['ex_best5']:+.2f}%, 5th-pct week {100 * p5:+.1f}%, worst {m['worst']:+.1f}%, max DD {m['maxdd']:.1f}%; "
          f"vol scale median {np.median(scales):.2f} (min {min(scales):.2f}, max {max(scales):.2f})")
    last = weeks[-52:]
    qs = {s: [len(lg[s][w][0]) // 2 for w in last] for s in pb["RULES"]}
    print("Coins per side over the last 52 weeks: " + ", ".join(f"{s} median {int(np.median(v))} (min {min(v)}, max {max(v)})" for s, v in qs.items()))
    print()
    print("| account | smallest position (scale 0.5 / median) | orders under $10, last 52 wks | weekly $ backtest | weekly $ conservative | 5th-pct week $ | worst week $ |")
    print("|---|---|---|---|---|---|---|")
    k = {w: sc for w, sc in zip(weeks, scales)}
    for A in SIZES:
        small = total = 0
        sizes = []
        for s in pb["RULES"]:
            prev = {}
            for w in last:
                legs_ = lg[s][w][0]
                q = len(legs_) // 2
                per = 0.25 * k[w] * A / q
                cur = {j: sd * per for j, sd, _, _, _ in legs_}
                for j in set(cur) | set(prev):
                    delta = abs(cur.get(j, 0) - prev.get(j, 0))
                    if delta == 0:
                        continue
                    whole = j not in prev or j not in cur or np.sign(cur[j]) != np.sign(prev[j])
                    if whole:  # a new position or a full close: must clear the minimum
                        total += 1
                        small += delta < MIN_ORDER
                    sizes.append(abs(cur.get(j, 0)) or abs(prev.get(j, 0)))
                prev = cur
        min_pos = 0.25 * 0.5 * A / max(max(v) for v in qs.values())
        med_pos = 0.25 * float(np.median(scales)) * A / np.median([np.median(v) for v in qs.values()])
        print(f"| ${A:,} | ${min_pos:,.0f} / ${med_pos:,.0f} | {small} of {total} ({100 * small / total:.0f}%) | "
              f"{A * m['mean'] / 100:+,.2f} | {A * m['ex_best5'] / 100:+,.2f} | {A * p5:+,.0f} | {A * m['worst'] / 100:+,.0f} |")


main()
