"""Delta-hedged JLP vs Kamino USDC lending: the paper forward test (pre-registered).

    python3 handoff/experiments/jlp_paper.py snapshot            # one check-in: append a snapshot
    python3 handoff/experiments/jlp_paper.py evaluate [--final]  # replay the registered rule

The rule, the accounting and the success criteria are in
handoff/preregistration/jlp-hedged/SPEC.md and are fixed by its commit. Paper only: nothing here
signs or sends a transaction, and no session needs a wallet or exchange account for it.

**Check-ins.** A paper trader who looks every few hours: each `snapshot` (scheduled every 4 h)
records what the trader would see at that moment: the pool's exact delta (Jupiter
`perps-api.jup.ag/v1/jlp-info`), Hyperliquid's marks and top of book for SOL/ETH/BTC, and Jupiter
quotes for $10k USDC <-> JLP. Decisions (rebalance, margin top-up) happen only at check-ins.
Between check-ins, `evaluate` fetches what happened from history: Hyperliquid's hourly funding
and 1h candles (liquidation check on each candle's high), and Kamino's USDC exchange rate for
the benchmark. A missed check-in only means the trader didn't look; it is not a gap in P&L.

**JLP delta per asset** (tokens per JLP): (owned - locked + shortSize / shortAvgPrice) / supply.
The pool holds `owned - locked` outright; it is counterparty to traders' shorts, so it is long
their size (USD / average entry); longs' locked collateral and guaranteed USD carry no delta.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

OUT = Path("handoff/data/jlp-paper/snapshots.jsonl")
JLP_MINT = "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
KAMINO = ("https://api.kamino.finance/kamino-market/7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF"
          "/reserves/D6q6wuQSrifJKZYpR1M8R4YawnLDtDsMmWM1NbBmgJ59/metrics/history")
HL = "https://api.hyperliquid.xyz/info"
COINS = {"SOL": "SOL", "ETH": "ETH", "WBTC": "BTC"}   # Jupiter custody symbol -> Hyperliquid coin

# The registered rule (SPEC.md). Changing any of these after registration voids the test.
START = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
END = datetime(2027, 1, 8, 0, 0, tzinfo=timezone.utc)      # 90 days
CAPITAL = 10_000.0
LEVERAGE = 3.0              # hedge margin = notional / 3 after every top-up or withdrawal
TOPUP_BELOW = 1 / 5         # margin < notional / 5 -> top up to notional / 3 (sell JLP)
WITHDRAW_ABOVE = 2 / 3      # margin > notional * 2/3 -> withdraw to notional / 3 (buy JLP)
DRIFT = 0.05                # rebalance all shorts when any |short - target| > 5% of JLP value
TAKER = 4.5e-4              # Hyperliquid taker fee, plus half the quoted spread
MAINT = {"SOL": 0.025, "ETH": 0.02, "BTC": 0.0125}   # half the initial margin at max leverage
QUOTE_USD = 10_000


def utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def custody_delta(c, supply):
    """Tokens of the custody's asset per JLP."""
    dec = round(np.log10(float(c["aumTokenAmount"]) / float(c["aumTokenAmountFormatted"])))
    held = (float(c["owned"]) - float(c["locked"])) / 10 ** dec
    short_px = float(c["globalShortAveragePrice"]) / 1e6
    shorts = float(c["globalShortSizes"]) / 1e6 / short_px if short_px > 0 else 0.0
    return (held + shorts) / supply


def jlp_state(info):
    supply = float(info["jlpTotalSupplyFormatted"])
    delta = {COINS[c["symbol"]]: custody_delta(c, supply) for c in info["custodies"] if c["symbol"] in COINS}
    return {"price": float(info["jlpPriceUsdFormatted"]), "supply": supply, "aum": float(info["aumUsdFormatted"]),
            "delta": delta}


def get(client, method, url, **kw):
    for attempt in range(6):
        try:
            r = client.request(method, url, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError(str(r.status_code), request=r.request, response=r)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            if attempt == 5:
                raise
            time.sleep(3 * (attempt + 1))


def quote_bps(client, nav):
    """Cost in bps vs the pool's NAV of buying, then selling, $10k of JLP on Jupiter."""
    q = "https://lite-api.jup.ag/swap/v1/quote"
    buy = get(client, "GET", q, params={"inputMint": USDC_MINT, "outputMint": JLP_MINT, "amount": QUOTE_USD * 10**6, "slippageBps": 50})
    jlp = int(buy["outAmount"])
    sell = get(client, "GET", q, params={"inputMint": JLP_MINT, "outputMint": USDC_MINT, "amount": jlp, "slippageBps": 50})
    return {"buy_bps": (1 - jlp / 1e6 * nav / QUOTE_USD) * 1e4,
            "sell_bps": (1 - int(sell["outAmount"]) / 1e6 / (jlp / 1e6 * nav)) * 1e4}


def snapshot(args):
    client = httpx.Client(timeout=30, headers={"accept": "application/json"})
    t = time.time()
    info = get(client, "GET", "https://perps-api.jup.ag/v1/jlp-info")
    meta, ctxs = get(client, "POST", HL, json={"type": "metaAndAssetCtxs"})
    hl = {}
    for u, c in zip(meta["universe"], ctxs):
        if u["name"] in MAINT:
            book = get(client, "POST", HL, json={"type": "l2Book", "coin": u["name"]})["levels"]
            hl[u["name"]] = {"mark": float(c["markPx"]), "oracle": float(c["oraclePx"]), "funding": float(c["funding"]),
                             "bid": float(book[0][0]["px"]), "ask": float(book[1][0]["px"])}
    jlp = jlp_state(info)
    try:
        quote = quote_bps(client, jlp["price"])
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        # a Jupiter quote outage must not lose the check-in (delta, HL marks): carry the last quote, flagged
        # (audit 2026-10-10: a 503 on 2026-10-10 20:49 UTC dropped a whole check-in)
        last = json.loads(OUT.read_text().splitlines()[-1]) if OUT.exists() and OUT.read_text().strip() else None
        if not last or "quote" not in last:
            raise
        quote = {**{k: last["quote"][k] for k in ("buy_bps", "sell_bps")}, "stale_from": last["t"], "error": f"{type(exc).__name__}: {exc}"[:120]}
    rec = {"t": utc(t), "ts": t, "jlp": jlp, "hl": hl, "quote": quote, "raw_custodies": [
        {k: c[k] for k in ("symbol", "owned", "locked", "guaranteedUsd", "globalShortSizes", "globalShortAveragePrice",
                           "aumTokenAmount", "aumTokenAmountFormatted")} for c in info["custodies"]]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    d = jlp["delta"]
    usd = {a: d[a] * hl[a]["mark"] / jlp["price"] for a in d}
    print(f"{rec['t']}: JLP ${jlp['price']:.4f}, delta per JLP-$ " + ", ".join(f"{a} {v:.3f}" for a, v in usd.items())
          + f"; quotes buy {rec['quote']['buy_bps']:+.1f} / sell {rec['quote']['sell_bps']:+.1f} bps -> {OUT}")


# ---------------------------------------------------------------- replay

def hourly(client, coin, t0, t1):
    """Hyperliquid 1h candles and hourly funding between t0 and t1 (seconds)."""
    ms0, ms1 = int(t0 * 1000), int(t1 * 1000)
    candles, fund = [], []
    s = ms0
    while s < ms1:
        part = get(client, "POST", HL, json={"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h", "startTime": s, "endTime": ms1}})
        if not part:
            break
        candles += part
        s = part[-1]["t"] + 3600_000
        if len(part) < 2:
            break
    s = ms0
    while s < ms1:
        part = get(client, "POST", HL, json={"type": "fundingHistory", "coin": coin, "startTime": s, "endTime": ms1})
        if not part:
            break
        fund += part
        s = part[-1]["time"] + 1
        if len(part) < 2:
            break
    c = {x["t"] // 1000: x for x in candles}
    return ([(t, float(x["o"]), float(x["h"]), float(x["c"])) for t, x in sorted(c.items())],
            sorted({x["time"] // 1000: float(x["fundingRate"]) for x in fund}.items()))


def kamino_index(client, t0, t1):
    """Value of 1 USDC deposited in Kamino, by hour (1 / exchangeRate)."""
    out = {}
    s = t0 - 3600
    while s < t1:
        e = min(s + 30 * 86400, t1 + 3600)
        h = get(client, "GET", KAMINO, params={"env": "mainnet-beta", "start": utc(s)[:16] + "Z", "end": utc(e)[:16] + "Z", "frequency": "hour"})
        for x in h.get("history", []):
            ts = datetime.fromisoformat(x["timestamp"].replace("Z", "+00:00")).timestamp()
            out[int(ts)] = 1 / float(x["metrics"]["exchangeRate"])
        s = e
    return sorted(out.items())


def at(series, t):
    """Last value at or before t."""
    i = np.searchsorted([s for s, _ in series], t, side="right") - 1
    return series[max(i, 0)][1]


def replay(snaps, market, bench):
    """Run the registered rule over the check-ins. market[coin] = (candles, funding).

    Returns (rows, liquidated): one row per check-in with total equity and the benchmark index.
    """
    rows, shorts, margin, jlp_units, liquidated = [], {}, 0.0, 0.0, None
    opens = {a: [(c[0], c[1]) for c in market[a][0]] for a in MAINT}
    highs = {a: {c[0]: c[2] for c in market[a][0]} for a in MAINT}
    hours = sorted(set().union(*(highs[a] for a in MAINT)))
    prev = None
    for s in snaps:
        t, nav, hl = s["ts"], s["jlp"]["price"], s["hl"]
        if prev is None:
            notional_per_jlp_usd = sum(s["jlp"]["delta"][a] * hl[a]["mark"] for a in MAINT) / nav
            jlp_usd = CAPITAL / (1 + notional_per_jlp_usd / LEVERAGE)
            jlp_units = jlp_usd * (1 - s["quote"]["buy_bps"] / 1e4) / nav
            margin = CAPITAL - jlp_usd
        else:
            for a, size in shorts.items():
                funding = market[a][1]
                p0 = prev["hl"][a]["mark"]
                for ft, rate in funding:          # shorts receive positive funding
                    if prev["ts"] < ft <= t:
                        margin += size * at(opens[a], ft) * rate
                margin += size * (p0 - hl[a]["mark"])
            worst = None                          # every asset at its hourly high together
            for ct in hours:
                if not prev["ts"] - 3600 < ct < t:
                    continue
                eq, req = margin, 0.0
                for a, size in shorts.items():
                    hi = highs[a].get(ct, hl[a]["mark"])
                    eq += size * (hl[a]["mark"] - hi)   # margin already settled to this check's mark
                    req += size * hi * MAINT[a]
                worst = min(worst, eq - req) if worst is not None else eq - req
            if worst is not None and worst < 0:
                liquidated = s["t"]
                rows.append({"t": s["t"], "ts": t, "equity": jlp_units * nav, "bench": at(bench, t), "event": "liquidated"})
                break
        # decisions at the check-in
        events = []
        jlp_value = jlp_units * nav
        target = {a: s["jlp"]["delta"][a] * jlp_units for a in MAINT}
        if prev is None or any(abs(shorts.get(a, 0) - target[a]) * hl[a]["mark"] > DRIFT * jlp_value for a in MAINT):
            for a in MAINT:
                px = hl[a]["mark"]
                half = (hl[a]["ask"] - hl[a]["bid"]) / 2 / px
                margin -= abs(target[a] - shorts.get(a, 0)) * px * (TAKER + half)
            shorts = dict(target)
            events.append("rebalance")
        notional = sum(shorts[a] * hl[a]["mark"] for a in MAINT)
        if margin < notional * TOPUP_BELOW or margin > notional * WITHDRAW_ABOVE:
            move = notional / LEVERAGE - margin          # > 0: sell JLP into margin
            if move > 0:
                jlp_units -= move / (nav * (1 - s["quote"]["sell_bps"] / 1e4))
            else:
                jlp_units += -move * (1 - s["quote"]["buy_bps"] / 1e4) / nav
            margin += move
            events.append("topup" if move > 0 else "withdraw")
        rows.append({"t": s["t"], "ts": t, "equity": jlp_units * nav + margin, "bench": at(bench, t),
                     "event": "+".join(events), "jlp": jlp_units * nav, "margin": margin, "notional": notional})
        prev = s
    return rows, liquidated


def exit_cost(snap, rows, shorts_notional):
    q = snap["quote"]["sell_bps"] / 1e4
    return rows[-1]["jlp"] * q + shorts_notional * TAKER


def daily_excess(rows):
    """Excess daily return over Kamino USDC, from the last check-in of each UTC day."""
    last = {}
    for r in rows:
        last[r["t"][:10]] = r
    days = [last[d] for d in sorted(last)]
    out = []
    for a, b in zip(days, days[1:]):
        out.append(b["equity"] / a["equity"] - b["bench"] / a["bench"])
    return np.array(out)


def block_ci(x, block=10, n=10_000, seed=1):
    rng = np.random.default_rng(seed)
    m = len(x)
    means = [x[np.concatenate([np.arange(s, s + block) % m for s in rng.integers(0, m, m // block + 1)])[:m]].mean()
             for _ in range(n)]
    return np.percentile(means, [5, 95])


def evaluate(args):
    snaps = [json.loads(l) for l in OUT.read_text().splitlines() if l.strip()]
    snaps = [s for s in snaps if START.timestamp() <= s["ts"] <= END.timestamp()]
    if len(snaps) < 2:
        print(f"{len(snaps)} check-ins inside {START:%Y-%m-%d}..{END:%Y-%m-%d}: nothing to evaluate yet")
        return
    client = httpx.Client(timeout=60, headers={"accept": "application/json"})
    t0, t1 = snaps[0]["ts"] - 3600, snaps[-1]["ts"] + 3600
    market = {a: hourly(client, a, t0, t1) for a in MAINT}
    bench = kamino_index(client, t0, t1)
    rows, liquidated = replay(snaps, market, bench)
    first, last = rows[0], rows[-1]
    days = (last["ts"] - first["ts"]) / 86400
    final = last["equity"] - (exit_cost(snaps[len(rows) - 1], rows, last.get("notional", 0)) if not liquidated else 0)
    ret = final / CAPITAL - 1
    bret = last["bench"] / first["bench"] - 1
    print(f"{len(rows)} check-ins, {first['t']} .. {last['t']} ({days:.1f} days); "
          f"rebalances {sum('rebalance' in r['event'] for r in rows) - 1}, top-ups {sum('topup' in r['event'] for r in rows)}, "
          f"withdrawals {sum('withdraw' in r['event'] for r in rows)}")
    print(f"equity ${final:,.2f} after exit costs ({ret * 100:+.2f}%), Kamino USDC {bret * 100:+.2f}%")
    x = daily_excess(rows)
    if liquidated:
        print(f"RESULT: FAIL (simulated liquidation at {liquidated})")
        return
    if len(x) < 10:
        print(f"{len(x)} daily excess returns: too few for a CI")
        return
    lo, hi = block_ci(x)
    print(f"excess over Kamino USDC: {x.mean() * 36500:+.2f}% APR, 90% CI [{lo * 36500:+.2f}, {hi * 36500:+.2f}] "
          f"(10-day moving blocks, {len(x)} days)")
    if args.final:
        ok = x.mean() > 0 and lo > 0
        print("RESULT: " + ("SUCCESS" if ok else "FAIL") + " (registered: mean > 0, CI lower bound > 0, no liquidation)")
    else:
        print("interim: not the registered result (that is `--final` on or after "
              f"{END:%Y-%m-%d})")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot")
    e = sub.add_parser("evaluate")
    e.add_argument("--final", action="store_true")
    a = p.parse_args()
    {"snapshot": snapshot, "evaluate": evaluate}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
