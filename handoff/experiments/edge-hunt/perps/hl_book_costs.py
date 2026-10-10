"""Hyperliquid execution cost snapshot: spread and market-order slippage from the public L2 book.

    python3 handoff/experiments/edge-hunt/perps/hl_book_costs.py [--out handoff/data/edge-hunt/hl-book]

For every listed perp with >= $500k 24h volume: top-20-level book (`l2Book`), then for each order
size the volume-weighted fill price of a market buy and a market sell walked through the book,
in bps from mid (half-spread included). Sizes the full-precision 20 levels can't fill are walked
through coarser books (`nSigFigs` 4, then 3: levels aggregated, prices rounded away from mid, so a
little conservative); `coarse_<size>` records which. Still unfilled at 3 figures: null. Taker fee is not included (Hyperliquid base tier: 4.5 bps taker, 1.5 maker).
Appends one JSON line per snapshot to <out>/<YYYY-MM>.jsonl. Public data only; nothing is traded.
"""
import argparse, json, time
from datetime import datetime, timezone
from pathlib import Path
import httpx

HL = "https://api.hyperliquid.xyz/info"
SIZES = (250, 1_000, 5_000, 25_000, 100_000)       # USD notional per order
MIN_VOL = 500_000


def post(c, body):
    for i in range(8):
        try:
            r = c.post(HL, json=body)
            if r.status_code == 200:
                return r.json()
        except httpx.HTTPError:
            pass
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"Hyperliquid info failed: {body}")


def walk(levels, usd):
    """Average fill price for `usd` notional through `levels` [(px, sz)], or None if too shallow."""
    got, cost = 0.0, 0.0
    for px, sz in levels:
        take = min(sz, (usd - cost) / px)
        got += take; cost += take * px
        if cost >= usd * (1 - 1e-9):
            return cost / got
    return None


def sides(book):
    return ([(float(x["px"]), float(x["sz"])) for x in book["levels"][0]],
            [(float(x["px"]), float(x["sz"])) for x in book["levels"][1]])


def costs(c, coin):
    bids, asks = sides(post(c, {"type": "l2Book", "coin": coin}))
    if not bids or not asks:
        return None
    mid = (bids[0][0] + asks[0][0]) / 2
    coarse = {}
    out = {"mid": mid, "spread_bps": round((asks[0][0] - bids[0][0]) / mid * 1e4, 3),
           "depth_bid_usd": round(sum(p * s for p, s in bids)), "depth_ask_usd": round(sum(p * s for p, s in asks))}
    for usd in SIZES:
        b, s = walk(asks, usd), walk(bids, usd)
        for figs in (4, 3):
            if b is not None and s is not None:
                break
            if figs not in coarse:
                coarse[figs] = sides(post(c, {"type": "l2Book", "coin": coin, "nSigFigs": figs}))
            cb, ca = coarse[figs]
            b = b if b is not None else walk(ca, usd)
            s = s if s is not None else walk(cb, usd)
            out[f"coarse_{usd}"] = figs
        out[f"buy_{usd}"] = None if b is None else round((b / mid - 1) * 1e4, 3)
        out[f"sell_{usd}"] = None if s is None else round((1 - s / mid) * 1e4, 3)
    return out


def main():
    p = argparse.ArgumentParser(); p.add_argument("--out", default="handoff/data/edge-hunt/hl-book"); a = p.parse_args()
    c = httpx.Client(timeout=30)
    meta, ctxs = post(c, {"type": "metaAndAssetCtxs"})
    t = time.time(); rows = {}
    for u, x in zip(meta["universe"], ctxs):
        vol = float(x.get("dayNtlVlm") or 0)
        if u.get("isDelisted") or vol < MIN_VOL:
            continue
        cst = costs(c, u["name"])
        if cst:
            cst["vol24_usd"] = round(vol); cst["oi_usd"] = round(float(x["openInterest"]) * float(x["markPx"]))
            rows[u["name"]] = cst
        time.sleep(0.1)
    ts = datetime.fromtimestamp(t, timezone.utc)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    with (out / f"{ts:%Y-%m}.jsonl").open("a") as f:
        f.write(json.dumps({"t": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "coins": rows}) + "\n")
    med = sorted(r["buy_5000"] for r in rows.values() if r["buy_5000"] is not None)
    print(f"{ts:%Y-%m-%dT%H:%MZ}: {len(rows)} perps; $5k market buy median {med[len(med) // 2]:.1f} bps from mid")


if __name__ == "__main__":
    main()
