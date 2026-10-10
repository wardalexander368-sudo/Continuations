"""Near-real-time dip signal for the pre-registered dip rule, from on-chain pool reserves. PAPER ONLY.

    python3 handoff/experiments/fast_dip.py run [--minutes 115] [--out data/fast-dip/log.jsonl]
    python3 handoff/experiments/fast_dip.py report [--out data/fast-dip/log.jsonl]

Why: real fills on the dip rule (STATUS, 2026-10-10) bought 4-5 minutes after the signal bar closed,
because GeckoTerminal publishes a 5-minute bar about a minute late and a scan then walks the pools
(2.2 s per request). By then the price had rebounded 1-2%.

How: the rule (handoff/preregistration/dip-rolling/SPEC.json, unchanged) compares bar i's close with
bar i-12's close. Bar i-12 closed an hour ago, so GeckoTerminal has long published it; only bar i's
close needs to be fast. A PumpSwap pool's price is its effective quote reserves (vault + virtual) over its base
vault (constant product), so one `getMultipleAccounts` call on the public RPC, made the moment bar i ends, reads
every registered pool's price at the bar close (SOL per token, times Coinbase SOL-USD to match the
USD bars). Signal: fast close / Gecko close of bar i-12 - 1 < -5%. No websocket, no API key, no
private RPC, no PumpPortal stream (that one is metered to the wallet).

Measurement: the same run then polls GeckoTerminal until it publishes bar i for every pool and logs
its signal (the one the paper agent and dip_real_fills.py act on): the close at the first poll after
bar end (Gecko also serves the bar in progress, so this can be stale), the time the bar became final
(Gecko already shows a later bar), and the pool's on-chain price at that moment. `report` joins the two per (pool, bar): agreement,
latency gained, and price gained (how much cheaper the fast entry was than an entry at the moment
the Gecko signal became visible; bar t+1's open, the rule's paper entry, is shown too).

Log rows (JSONL): kind "fast" (one per pool per bar), "gecko" (one per pool per bar), "error".
"""
import argparse
import base64
import json
import statistics
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

PREREG = Path("handoff/preregistration/dip-rolling")
GECKO = "https://api.geckoterminal.com/api/v2/networks/solana"
RPC = "https://api.mainnet-beta.solana.com"
COINBASE = "https://api.exchange.coinbase.com/products/SOL-USD/ticker"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BAR = 300

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=("run", "report"))
ap.add_argument("--minutes", type=float, default=115.0)
ap.add_argument("--out", default="data/fast-dip/log.jsonl")
ap.add_argument("--gecko-deadline", type=float, default=240.0, help="seconds after bar end to keep polling Gecko")
args = ap.parse_args()
rule = json.loads((PREREG / "SPEC.json").read_text())["rule"]
L, DROP = rule["lookback_bars"], rule["drop"]
http = httpx.Client(timeout=20, headers={"accept": "application/json"})
_gecko_last = [0.0]


def b58(raw: bytes) -> str:
    n, s = int.from_bytes(raw, "big"), ""
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + s


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def write(row: dict) -> None:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def rpc(method: str, params: list):
    for wait in (1, 2, 4, 0):
        r = http.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if r.status_code != 429 or not wait:
            break
        time.sleep(wait)
    r.raise_for_status()
    body = r.json()
    if body.get("error"):
        raise RuntimeError(f"{method}: {body['error']}")
    return body["result"]


def pools() -> list[dict]:
    seen, out = set(), []
    for c in sorted((json.loads(f.read_text()) for f in PREREG.glob("cohort-*.json")), key=lambda c: c["registered_at"]):
        for p in c["pools"]:
            if p["token"] not in seen:
                seen.add(p["token"])
                out.append({"pool": p["pool"], "name": p["name"], "mint": p["token"].split("_", 1)[-1]})
    return out


_vaults: dict[str, dict] = {}


def vaults(ps: list[dict]) -> None:
    """PumpSwap pool layout: 8 disc, u8 bump, u16 index, creator, base_mint, quote_mint, lp_mint,
    base vault (offset 139), quote vault (offset 171). Decimals from the base mint (offset 44)."""
    need = [p for p in ps if p["pool"] not in _vaults]
    for k in range(0, len(need), 50):
        chunk = need[k:k + 50]
        accs = rpc("getMultipleAccounts", [[p["pool"] for p in chunk], {"encoding": "base64"}])["value"]
        mints = rpc("getMultipleAccounts", [[p["mint"] for p in chunk], {"encoding": "base64"}])["value"]
        for p, a, m in zip(chunk, accs, mints):
            if not a or not m:
                continue
            d = base64.b64decode(a["data"][0])
            base_mint, quote_mint = b58(d[43:75]), b58(d[75:107])
            if base_mint != p["mint"] or quote_mint != "So11111111111111111111111111111111111111112":
                write({"kind": "error", "t": time.time(), "pool": p["pool"], "error": "unexpected pool layout or quote"})
                continue
            _vaults[p["pool"]] = {"base": b58(d[139:171]), "quote": b58(d[171:203]),
                                  "dec": base64.b64decode(m["data"][0])[44]}


def onchain_prices(ps: list[dict]) -> tuple[dict[str, float], int, float]:
    """SOL per token (spot mid) for every pool, from one getMultipleAccounts on pools and vaults; plus
    slot and time. Effective quote reserves = quote vault + the pool's signed `virtual_quote_reserves`
    (i128 at offset 245; boosted pools carry ~17.5 SOL of it, tartar/feeds/pumpswap.py). Without it the
    price read 1-72% low; with it, it sits 0.2-1.2% under a Jupiter buy quote (the buy fee)."""
    keys = [k for p in ps if p["pool"] in _vaults for k in (p["pool"], _vaults[p["pool"]]["base"], _vaults[p["pool"]]["quote"])]
    accs, slot = {}, 0
    for k in range(0, len(keys), 99):
        res = rpc("getMultipleAccounts", [keys[k:k + 99], {"encoding": "base64", "commitment": "confirmed"}])
        slot = max(slot, res["context"]["slot"])
        accs.update({key: base64.b64decode(a["data"][0]) for key, a in zip(keys[k:k + 99], res["value"]) if a})
    t = time.time()
    out = {}
    for p in ps:
        v = _vaults.get(p["pool"])
        if not v or not all(x in accs for x in (p["pool"], v["base"], v["quote"])):
            continue
        base = struct.unpack_from("<Q", accs[v["base"]], 64)[0] / 10 ** v["dec"]  # SPL token account amount
        quote = struct.unpack_from("<Q", accs[v["quote"]], 64)[0] / 1e9
        quote += int.from_bytes(accs[p["pool"]][245:261], "little", signed=True) / 1e9
        if base > 0 and quote > 0:
            out[p["pool"]] = quote / base
    return out, slot, t


def sol_usd() -> float | None:
    try:
        d = http.get(COINBASE, timeout=5).json()
        return (float(d["bid"]) + float(d["ask"])) / 2
    except Exception:  # noqa: BLE001
        return None


def gecko_bars(pool: str, limit: int = 30) -> list[list[float]]:
    for attempt in range(4):
        wait = 2.2 - (time.time() - _gecko_last[0])
        if wait > 0:
            time.sleep(wait)
        _gecko_last[0] = time.time()
        r = http.get(f"{GECKO}/pools/{pool}/ohlcv/minute", params={"aggregate": 5, "limit": limit, "currency": "usd"})
        if r.status_code == 429:
            time.sleep(8 * (attempt + 1))
            continue
        r.raise_for_status()
        rows = r.json().get("data", {}).get("attributes", {}).get("ohlcv_list") or []
        return sorted([[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in rows])
    raise RuntimeError("GeckoTerminal rate limit")


def close_at(rows: list, bar_t: int) -> float | None:
    """The rule's close of the bar starting at bar_t: missing bars carry the last close (as the agent's grid does)."""
    prior = [r for r in rows if r[0] <= bar_t]
    return prior[-1][4] if prior else None


def cycle(bar_end: int, ps: list[dict], ref_rows: dict[str, list]) -> None:
    """Bar i = [bar_end - 300, bar_end). Fast signal now; then poll Gecko until it shows bar i."""
    bar_i = bar_end - BAR
    try:
        prices, slot, t_fast = onchain_prices(ps)
    except Exception as exc:  # noqa: BLE001
        write({"kind": "error", "t": time.time(), "bar": bar_i, "error": f"rpc {str(exc)[:200]}"})
        return
    usd = sol_usd()
    for p in ps:
        px, rows = prices.get(p["pool"]), ref_rows.get(p["pool"]) or []
        ref = close_at(rows, bar_i - L * BAR)
        row = {"kind": "fast", "pool": p["pool"], "name": p["name"], "bar": bar_i, "t": round(t_fast, 3),
               "lag_s": round(t_fast - bar_end, 3), "slot": slot, "px_sol": px, "sol_usd": usd, "ref_close": ref}
        if px and usd and ref:
            row["close_usd"] = px * usd
            row["ret"] = px * usd / ref - 1
            row["signal"] = row["ret"] < -DROP
        write(row)
    # Gecko: poll every pool round robin (its rate limit) until bar i is final, i.e. Gecko already shows
    # a later bar (it has ingested trades after bar i ended). Gecko also serves the bar in progress, so
    # the first poll after bar end may show bar i with a stale close; both are logged.
    pending = {p["pool"]: p for p in ps}
    first: dict[str, dict] = {}
    while pending and time.time() < bar_end + args.gecko_deadline:
        for pid in list(pending):
            if time.time() >= bar_end + args.gecko_deadline:
                break
            p = pending[pid]
            try:
                rows = gecko_bars(pid)
            except Exception as exc:  # noqa: BLE001
                write({"kind": "error", "t": time.time(), "bar": bar_i, "pool": pid, "error": f"gecko {str(exc)[:200]}"})
                continue
            t_seen = time.time()
            ref_rows[pid] = rows
            c_i, ref = close_at(rows, bar_i), close_at(rows, bar_i - L * BAR)
            if pid not in first:
                first[pid] = {"t": t_seen, "close": c_i}
            if not rows or rows[-1][0] < bar_end:  # bar i not final yet
                continue
            del pending[pid]
            try:
                px_now = onchain_prices([p])[0].get(pid)
            except Exception:  # noqa: BLE001
                px_now = None
            row = {"kind": "gecko", "pool": pid, "name": p["name"], "bar": bar_i, "t_final": round(t_seen, 3),
                   "lag_s": round(t_seen - bar_end, 3), "close_usd": c_i, "ref_close": ref, "px_sol_at_final": px_now,
                   "first_lag_s": round(first[pid]["t"] - bar_end, 3), "first_close": first[pid]["close"],
                   "next_open": next((r[1] for r in rows if r[0] == bar_end), None)}
            if c_i and ref:
                row["ret"] = c_i / ref - 1
                row["signal"] = row["ret"] < -DROP
                if first[pid]["close"]:
                    row["signal_first"] = first[pid]["close"] / ref - 1 < -DROP
            write(row)
    for pid, p in pending.items():  # no trade after bar i within the deadline (or Gecko errors)
        f = first.get(pid, {})
        rows = ref_rows.get(pid) or []
        ref = close_at(rows, bar_i - L * BAR)
        row = {"kind": "gecko", "pool": pid, "name": p["name"], "bar": bar_i, "final": False,
               "lag_s": round(time.time() - bar_end, 3), "first_lag_s": round(f["t"] - bar_end, 3) if f else None,
               "close_usd": close_at(rows, bar_i), "ref_close": ref}
        if row["close_usd"] and ref:
            row["ret"] = row["close_usd"] / ref - 1
            row["signal"] = row["ret"] < -DROP
        write(row)


def run() -> None:
    end = time.time() + 60 * args.minutes
    ps = pools()
    vaults(ps)
    ref_rows = {}
    for p in ps:  # reference bars for the first cycle
        try:
            ref_rows[p["pool"]] = gecko_bars(p["pool"])
        except Exception as exc:  # noqa: BLE001
            write({"kind": "error", "t": time.time(), "pool": p["pool"], "error": f"gecko {str(exc)[:200]}"})
    print(f"{iso(time.time())} watching {len(_vaults)} of {len(ps)} pools", flush=True)
    while True:
        bar_end = (int(time.time()) // BAR + 1) * BAR
        if bar_end + args.gecko_deadline > end:
            break
        time.sleep(max(0.0, bar_end - time.time()))
        ps = pools()  # a new daily cohort joins at the next bar
        vaults(ps)
        ps = [p for p in ps if p["pool"] in _vaults]
        cycle(bar_end, ps, ref_rows)
        n = sum(1 for _ in open(args.out))
        print(f"{iso(time.time())} bar {iso(bar_end - BAR)} done ({n} log rows)", flush=True)


def report() -> None:
    fast, gecko = {}, {}
    errors = 0
    for line in Path(args.out).read_text().splitlines():
        r = json.loads(line)
        if r["kind"] == "fast":
            fast[(r["pool"], r["bar"])] = r
        elif r["kind"] == "gecko":
            gecko[(r["pool"], r["bar"])] = r
        else:
            errors += 1
    both = [(fast[k], gecko[k]) for k in fast if k in gecko and "ret" in fast[k] and "ret" in gecko[k]]
    if not both:
        print("no joined rows yet")
        return
    bars = sorted({k[1] for k in fast})
    print(f"{len(bars)} bars ({iso(bars[0])} .. {iso(bars[-1])}), {len(both)} pool-bars joined, {errors} errors")
    fl = [f["lag_s"] for f, _ in both]
    gl = [g["lag_s"] for _, g in both]
    fin = [g["lag_s"] for _, g in both if g.get("final", True)]
    print(f"bar close readable after bar end: fast median {statistics.median(fl):.1f} s (max {max(fl):.1f}); "
          f"Gecko final median {statistics.median(fin):.0f} s (max {max(fin):.0f}; {len(both) - len(fin)} not final by the deadline)")
    fp = [g["first_lag_s"] for _, g in both if g.get("first_lag_s") is not None]
    print(f"Gecko first poll after bar end (one request per pool, 2.2 s apart): median {statistics.median(fp):.0f} s, max {max(fp):.0f} s")
    stale = [g for _, g in both if g.get("first_close") and g.get("close_usd") and g.get("final", True)]
    if stale:
        print(f"Gecko's first poll after bar end already had the final close for {sum(abs(g['first_close'] / g['close_usd'] - 1) < 1e-9 for g in stale)} of {len(stale)} pool-bars"
              f"; its signal flipped between first and final for {sum(g.get('signal_first') != g.get('signal') for g in stale)}")
    dc = [100 * (f["close_usd"] / g["close_usd"] - 1) for f, g in both if g.get("close_usd")]
    print(f"fast close vs Gecko close of the same bar: median {statistics.median(dc):+.2f}%, "
          f"mean |diff| {statistics.mean(abs(x) for x in dc):.2f}%")
    tp = sum(f["signal"] and g["signal"] for f, g in both)
    fo = sum(f["signal"] and not g["signal"] for f, g in both)
    go = sum(g["signal"] and not f["signal"] for f, g in both)
    print(f"signals: both {tp}, fast only {fo}, Gecko only {go}")
    gains, gains_open = [], []
    for f, g in both:
        if not (f["signal"] and g["signal"]):
            continue
        moved = float("nan")
        if f.get("px_sol") and g.get("px_sol_at_final"):
            moved = 100 * (g["px_sol_at_final"] / f["px_sol"] - 1)  # >0: fast entry was cheaper
            gains.append(moved)
        if g.get("next_open") and f.get("close_usd"):
            gains_open.append(100 * (g["next_open"] / f["close_usd"] - 1))
        print(f"  {g['name']:<20} {iso(g['bar'])} fast {100 * f['ret']:+.1f}% at +{f['lag_s']:.1f} s, Gecko "
              f"{100 * g['ret']:+.1f}% final at +{g['lag_s']:.0f} s; price moved {moved:+.2f}% in between")
    if gains:
        print(f"price gained by the fast entry vs entering when Gecko's bar was final: median {statistics.median(gains):+.2f}%, "
              f"mean {statistics.mean(gains):+.2f}% (n={len(gains)}; >0 means cheaper)")
    if gains_open:
        print(f"bar t+1 open (the rule's paper entry) vs fast close: median {statistics.median(gains_open):+.2f}% (n={len(gains_open)})")


{"run": run, "report": report}[args.mode]()
