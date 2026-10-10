"""LP return (in SOL) on PumpSwap pools from their first recorded swap, vs holding SOL (edge hunt C).

    python3 handoff/experiments/edge-hunt/liquidity/pumpswap_lp.py handoff/data/raw-v3 handoff/data/raw-clever handoff/data/raw-clever2

Constant product: LP value in SOL = 2 sqrt(k P), so price alone scales it by sqrt(P1/P0); fee growth
is each swap's LP fee over twice the SOL reserve, at an LP share of 0.02% and 0.20%.
"""
import gzip, json, sys, glob, collections, numpy as np
pools = collections.defaultdict(list)
for d in sys.argv[1:]:
    for f in sorted(glob.glob(d + "/*.jsonl.gz")):
        with gzip.open(f, "rt") as fh:
            for l in fh:
                if '"swap"' not in l: continue
                e = json.loads(l)
                if e.get("e") != "swap" or not e.get("tok_after") or not e.get("sol_after"): continue
                pools[e["pool"]].append(e)
res = {h: [] for h in (1, 4)}
vol = []
for p, ev in pools.items():
    ev.sort(key=lambda e: e["t"])
    t0 = ev[0]["t"]; p0 = ev[0]["sol_after"] / ev[0]["tok_after"]
    for H in res:
        if ev[-1]["t"] - t0 < H * 3600 * 0.9: continue
        fee = {}
        for lp_rate, name in ((0.0002, "lp2bp"), (0.002, "lp20bp")):
            g = 1.0
            for e in ev:
                if e["t"] - t0 > H * 3600: break
                g *= 1 + lp_rate * abs(e["sol"]) / (2 * e["sol_after"])
            fee[name] = g
        last = [e for e in ev if e["t"] - t0 <= H * 3600][-1]
        r = (last["sol_after"] / last["tok_after"]) / p0
        res[H].append((np.sqrt(r), fee["lp2bp"], fee["lp20bp"]))
for H, v in res.items():
    if not v: continue
    a = np.array(v)
    il = a[:, 0]
    print(f"{H}h after first recorded swap: {len(a)} pools; LP value/ initial (SOL) price-only median {np.median(il):.3f} mean {il.mean():.3f}; "
          f"with LP 0.02%: mean {(il*a[:,1]).mean():.3f}; with LP 0.20%: mean {(il*a[:,2]).mean():.3f}; "
          f"fee growth at 0.20% median {np.median(a[:,2])-1:.4f} p90 {np.percentile(a[:,2],90)-1:.4f}")
