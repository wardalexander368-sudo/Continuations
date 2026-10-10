"""What the pre-registered dip rule nets on executable quotes, with the watcher delay fixed. PAPER ONLY.

    python3 handoff/experiments/dip_cost_paper.py watch [--minutes 115]   (resumable; run again)
    python3 handoff/experiments/dip_cost_paper.py report

Question (coordinator, 2026-10-10 18:06 UTC): real dip fills lost 5-6 points to the rule's gross
(STATUS); the 4-5 min entry delay was the watcher's own fault (fast_dip.py), and PumpPortal
Lightning charges 1% per side. With both fixed, does the rule clear its costs?

Watcher fix: at each bar end the script reads every registered pool's on-chain price (one public
RPC call, fast_dip.py's method) and polls GeckoTerminal for the pools closest to a signal first, so
the rule's own signal (Gecko close of bar i vs bar i-12, as the paper agent computes it) is seen
seconds after the bar ends instead of minutes. Gecko's first close after bar end was final 95% of
the time (fast_dip report); pools whose bar i isn't out yet are polled again until +4 min.

Paper trade per signal (one open position per pool, as the rule says): at the moment the signal is
seen, free Jupiter quotes (lite-api, no key) to buy 0.01, 0.1 and 1 SOL of the token, both by
Jupiter's best route and by PumpSwap only (Lightning's route); at bar t+48's end, quotes to sell
exactly those token amounts. Nets, in SOL:
  jupiter    = best-route sell / buy size - 1 - 2 x network fee / size   (own wallet, own key)
  pumpswap   = the same on PumpSwap only
  lightning  = pumpswap with Lightning's 1% on each side: x 0.99 tokens bought, x 0.99 SOL back
Network fee 0.000011 SOL per transaction (measured, STATUS); token-account rent is excluded (an own
key closes the account and gets it back). The rule's gross on Gecko bars is reported beside it.
"""
import argparse
import base64
import json
import statistics
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

PREREG = Path("handoff/preregistration/dip-rolling")
GECKO = "https://api.geckoterminal.com/api/v2/networks/solana"
RPC = "https://api.mainnet-beta.solana.com"
JUP = "https://lite-api.jup.ag/swap/v1/quote"
SOL = "So11111111111111111111111111111111111111112"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BAR = 300
SIZES = (0.01, 0.1, 1.0)
NETWORK_SOL = 0.000011
LIGHTNING = 0.01

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=("watch", "report"))
ap.add_argument("--minutes", type=float, default=115.0)
ap.add_argument("--dir", default="data/dip-cost")
args = ap.parse_args()
STATE, LOG = Path(args.dir) / "state.json", Path(args.dir) / "trades.jsonl"
rule = json.loads((PREREG / "SPEC.json").read_text())["rule"]
L, H, DROP = rule["lookback_bars"], rule["hold_bars"], rule["drop"]
http = httpx.Client(timeout=20, headers={"accept": "application/json"})
_last = {"gecko": 0.0, "jup": 0.0}


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    print(f"{iso(time.time())} {msg}", flush=True)


def b58(raw: bytes) -> str:
    n, s = int.from_bytes(raw, "big"), ""
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + s


def pace(kind: str, gap: float) -> None:
    wait = gap - (time.time() - _last[kind])
    if wait > 0:
        time.sleep(wait)
    _last[kind] = time.time()


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


def onchain_prices(ps: list[dict]) -> dict[str, float]:
    """SOL per token (spot) per pool: (quote vault + virtual_quote_reserves) / base vault (see fast_dip.py)."""
    need = [p for p in ps if p["pool"] not in _vaults]
    if need:
        accs = rpc("getMultipleAccounts", [[p["pool"] for p in need], {"encoding": "base64"}])["value"]
        mints = rpc("getMultipleAccounts", [[p["mint"] for p in need], {"encoding": "base64"}])["value"]
        for p, a, m in zip(need, accs, mints):
            if a and m:
                d = base64.b64decode(a["data"][0])
                if b58(d[43:75]) == p["mint"] and b58(d[75:107]) == SOL:
                    _vaults[p["pool"]] = {"base": b58(d[139:171]), "quote": b58(d[171:203]), "dec": base64.b64decode(m["data"][0])[44]}
    keys = [k for p in ps if p["pool"] in _vaults for k in (p["pool"], _vaults[p["pool"]]["base"], _vaults[p["pool"]]["quote"])]
    raw = {}
    for k in range(0, len(keys), 99):
        res = rpc("getMultipleAccounts", [keys[k:k + 99], {"encoding": "base64", "commitment": "confirmed"}])["value"]
        raw.update({key: base64.b64decode(a["data"][0]) for key, a in zip(keys[k:k + 99], res) if a})
    out = {}
    for p in ps:
        v = _vaults.get(p["pool"])
        if v and all(x in raw for x in (p["pool"], v["base"], v["quote"])):
            base = struct.unpack_from("<Q", raw[v["base"]], 64)[0] / 10 ** v["dec"]
            quote = struct.unpack_from("<Q", raw[v["quote"]], 64)[0] / 1e9 + int.from_bytes(raw[p["pool"]][245:261], "little", signed=True) / 1e9
            if base > 0 and quote > 0:
                out[p["pool"]] = quote / base
    return out


def gecko_bars(pool: str) -> list[list[float]]:
    for attempt in range(4):
        pace("gecko", 2.2)
        r = http.get(f"{GECKO}/pools/{pool}/ohlcv/minute", params={"aggregate": 5, "limit": 30, "currency": "usd"})
        if r.status_code == 429:
            time.sleep(8 * (attempt + 1))
            continue
        r.raise_for_status()
        rows = r.json().get("data", {}).get("attributes", {}).get("ohlcv_list") or []
        return sorted([[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in rows])
    raise RuntimeError("GeckoTerminal rate limit")


def close_at(rows: list, bar_t: int) -> float | None:
    """Close of the bar starting at bar_t; missing bars carry the last close (the paper agent's grid)."""
    prior = [r for r in rows if r[0] <= bar_t]
    return prior[-1][4] if prior else None


def quote(inp: str, out: str, amount: int, pump_only: bool) -> dict:
    params = {"inputMint": inp, "outputMint": out, "amount": amount, "slippageBps": 100}
    if pump_only:
        params["dexes"] = "Pump.fun Amm"
    for attempt in range(4):
        pace("jup", 1.1)
        try:
            r = http.get(JUP, params=params)
            if r.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            q = r.json()
            if "outAmount" in q:
                return {"out": int(q["outAmount"]), "route": [x["swapInfo"].get("label") for x in q.get("routePlan", [])],
                        "impact": float(q.get("priceImpactPct") or 0)}
            return {"error": str(q)[:200]}
        except (httpx.HTTPError, ValueError) as exc:
            err = str(exc)[:200]
    return {"error": err if "err" in locals() else "rate limited"}


def load() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"open": {}, "busy_until": {}}


def save(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1))


def write(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def enter(st: dict, p: dict, bar_i: int, ret: float, bar_end: int, px: float | None) -> None:
    t0 = time.time()
    legs = {}
    for size in SIZES:
        for route, pump in (("best", False), ("pump", True)):
            legs[f"{route}:{size}"] = quote(SOL, p["mint"], int(size * 1e9), pump)
    tr = {"key": f"{p['pool']}:{bar_i}", "pool": p["pool"], "mint": p["mint"], "name": p["name"], "signal_bar": bar_i,
          "ret": ret, "seen_lag_s": round(t0 - bar_end, 1), "quoted_lag_s": round(time.time() - bar_end, 1),
          "entry_px_sol": px, "exit_t": bar_i + H * BAR + BAR, "buy": legs}
    st["open"][tr["key"]] = tr
    st["busy_until"][p["pool"]] = bar_i + H * BAR
    save(st)
    log(f"ENTRY {p['name']} dip {100 * ret:.1f}% seen +{tr['seen_lag_s']} s; best 0.1 SOL route {legs['best:0.1'].get('route')}")


def exit_(st: dict, tr: dict) -> None:
    legs = {}
    for k, b in tr["buy"].items():
        if "out" in b:
            legs[k] = quote(tr["mint"], SOL, b["out"], k.startswith("pump"))
    tr["sell"] = legs
    tr["exit_quoted_lag_s"] = round(time.time() - tr["exit_t"], 1)
    try:
        tr["exit_px_sol"] = onchain_prices([{"pool": tr["pool"], "mint": tr["mint"], "name": tr["name"]}]).get(tr["pool"])
    except Exception:  # noqa: BLE001
        tr["exit_px_sol"] = None
    write(tr)
    del st["open"][tr["key"]]
    save(st)
    log(f"EXIT {tr['name']} quoted +{tr['exit_quoted_lag_s']} s after bar t+48 ended")


def cycle(st: dict, bar_end: int) -> None:
    bar_i = bar_end - BAR
    ps = pools()
    try:
        px = onchain_prices(ps)
    except Exception as exc:  # noqa: BLE001
        log(f"rpc error {str(exc)[:120]}")
        px = {}
    # exits first: sell quotes right when bar t+48 ends
    for tr in list(st["open"].values()):
        if tr["exit_t"] <= bar_end:
            exit_(st, tr)
    # entries: free pools only (one position per pool), nearest to a signal first by on-chain price
    free = [p for p in ps if st["busy_until"].get(p["pool"], 0) < bar_i]
    refs = st.setdefault("ref", {})
    def chain_ret(p):
        r = refs.get(p["pool"])
        return px[p["pool"]] / r - 1 if r and p["pool"] in px else 0.0
    free.sort(key=chain_ret)
    pending = {p["pool"]: p for p in free}
    while pending and time.time() < bar_end + 240:
        for pid in list(pending):
            p = pending[pid]
            try:
                rows = gecko_bars(pid)
            except Exception as exc:  # noqa: BLE001
                log(f"{p['name']}: gecko error {str(exc)[:100]}")
                continue
            if not rows or rows[-1][0] < bar_i:
                continue  # bar i not out yet: poll again
            del pending[pid]
            c_i, ref = close_at(rows, bar_i), close_at(rows, bar_i - L * BAR)
            if ref and pid in px:  # SOL-price reference for next bar's ordering (approx: USD ref / SOL-USD drift ignored)
                refs[pid] = px[pid] * ref / c_i if c_i else None
            if c_i and ref and c_i / ref - 1 < -DROP:
                enter(st, p, bar_i, c_i / ref - 1, bar_end, px.get(pid))
    save(st)


def watch() -> None:
    st = load()
    end = time.time() + 60 * args.minutes
    log(f"watching; {len(st['open'])} open paper trades")
    while True:
        bar_end = (int(time.time()) // BAR + 1) * BAR
        if bar_end + 240 > end:
            break
        time.sleep(max(0.0, bar_end + 2 - time.time()))
        cycle(st, bar_end)
    log("window over; run again to resume")


def report() -> None:
    rows = [json.loads(x) for x in LOG.read_text().splitlines()] if LOG.exists() else []
    if not rows:
        print("no closed paper trades yet")
        return
    net = {}
    for tr in rows:
        for size in SIZES:
            b, s = tr["buy"].get(f"best:{size}", {}), tr.get("sell", {}).get(f"best:{size}", {})
            pb, ps_ = tr["buy"].get(f"pump:{size}", {}), tr.get("sell", {}).get(f"pump:{size}", {})
            fee = 2 * NETWORK_SOL / size
            if "out" in s:
                net.setdefault(("jupiter", size), []).append(s["out"] / 1e9 / size - 1 - fee)
            if "out" in ps_:
                pn = ps_["out"] / 1e9 / size
                net.setdefault(("pumpswap", size), []).append(pn - 1 - fee)
                net.setdefault(("lightning", size), []).append(pn * (1 - LIGHTNING) ** 2 - 1 - fee)
    lag = [tr["seen_lag_s"] for tr in rows]
    print(f"{len(rows)} closed paper trades ({iso(rows[0]['signal_bar'])} .. {iso(rows[-1]['signal_bar'])}); "
          f"signal seen median {statistics.median(lag):.0f} s after bar end (max {max(lag):.0f})")
    for route in ("jupiter", "pumpswap", "lightning"):
        for size in SIZES:
            v = net.get((route, size), [])
            if v:
                se = statistics.stdev(v) / len(v) ** 0.5 if len(v) > 1 else float("nan")
                print(f"  {route:<9} {size:>5} SOL: mean net {100 * statistics.mean(v):+.2f}% (SE {100 * se:.2f}), "
                      f"median {100 * statistics.median(v):+.2f}%, win {sum(x > 0 for x in v)}/{len(v)}")
    gross = [tr["exit_px_sol"] / tr["entry_px_sol"] - 1 for tr in rows if tr.get("exit_px_sol") and tr.get("entry_px_sol")]
    if gross:
        print(f"  spot gross (on-chain price at bar end -> at bar t+48 end): mean {100 * statistics.mean(gross):+.2f}%, n={len(gross)}")
    cost = [(tr["exit_px_sol"] / tr["entry_px_sol"]) - tr["sell"]["best:0.1"]["out"] / 1e8 for tr in rows
            if tr.get("exit_px_sol") and tr.get("entry_px_sol") and "out" in tr.get("sell", {}).get("best:0.1", {})]
    if cost:
        print(f"  round-trip cost vs spot, best route, 0.1 SOL: mean {100 * statistics.mean(cost):.2f} points")


{"watch": watch, "report": report}[args.mode]()
