"""Real fills on the pre-registered dip rule (handoff/preregistration/dip-rolling): at most 2 trips.

    python3 handoff/experiments/dip_real_fills.py watch --real [--minutes 110] [--trips 2] [--size 0.01]
    python3 handoff/experiments/dip_real_fills.py report

REAL MONEY (AJ's go, 2026-10-10 02:18 UTC: "a couple real fills if an opportunity looks good"; the
coordinator's defaults: at most 2 round trips of at most 0.01 SOL, only on a registered rule's
signal, each compared with the paper agent's fill for the same signal).

Rule (SPEC.json, as the paper agent trades it in tartar/autotrade/strategies/dip.py): on 5-minute
bars, a pool's close fell more than 5% over the last 12 bars -> buy at the next bar's open, sell at
the close of bar t+48 (4 hours). This script checks every registered pool 2 s after each bar
closes (re-polling pools whose bar isn't out yet); a signal on the bar that just completed is bought at once (inside bar t+1, as close to its
open as the API allows) and sold once bar t+48 has closed. Older signals are never chased.

Trades go through real_fills.py (`buy` / `sell`, fills in data/real-fills/dip-fills.jsonl).
State in data/real-fills/dip-state.json, so a restarted watch resumes open trips (run it again).
`report` compares each trip with the agent's paper trade for the same key (autotrade/trades.jsonl)
and with GeckoTerminal's SOL-quoted bars at the rule's entry and exit.
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

PREREG = Path("handoff/preregistration/dip-rolling")
GECKO = "https://api.geckoterminal.com/api/v2/networks/solana"
STATE = Path("data/real-fills/dip-state.json")
FILLS = Path("data/real-fills/dip-fills.jsonl")
FILLS_SCRIPT = str(Path(__file__).with_name("real_fills.py"))
BAR = 300

ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=("watch", "report"))
ap.add_argument("--real", action="store_true")
ap.add_argument("--minutes", type=float, default=110.0, help="stop watching after this long (state persists)")
ap.add_argument("--trips", type=int, default=2)
ap.add_argument("--size", type=float, default=0.01)
args = ap.parse_args()
spec = json.loads((PREREG / "SPEC.json").read_text())["rule"]
L, H, DROP = spec["lookback_bars"], spec["hold_bars"], spec["drop"]
http = httpx.Client(timeout=30, headers={"accept": "application/json"})
_last = [0.0]


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}", flush=True)


def pools() -> list[dict]:
    seen, out = set(), []
    for c in sorted((json.loads(f.read_text()) for f in PREREG.glob("cohort-*.json")), key=lambda c: c["registered_at"]):
        for p in c["pools"]:
            if p["token"] not in seen:
                seen.add(p["token"])
                out.append({**p, "mint": p["token"].split("_", 1)[-1]})
    return out


def bars(pool: str, currency: str = "usd") -> list[list[float]]:
    for attempt in range(6):
        wait = 2.2 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        r = http.get(f"{GECKO}/pools/{pool}/ohlcv/minute", params={"aggregate": 5, "limit": 100, "currency": currency})
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        rows = r.json().get("data", {}).get("attributes", {}).get("ohlcv_list") or []
        return sorted([[int(t), float(o), float(h), float(lo), float(c), float(v)] for t, o, h, lo, c, v in rows])
    raise RuntimeError("GeckoTerminal rate limit")


def grid(rows: list, now: float) -> tuple[list[int], list[float], list[float]]:
    """Completed bars on a regular grid, missing bars carry the last close (as the paper agent does)."""
    rows = [r for r in rows if r[0] + BAR <= now]
    if not rows:
        return [], [], []
    by_t = {r[0]: r for r in rows}
    t, o, c, prev = [], [], [], rows[0][4]
    for ti in range(rows[0][0], rows[-1][0] + BAR, BAR):
        r = by_t.get(ti)
        t.append(ti)
        o.append(prev if r is None else r[1])
        c.append(prev if r is None else r[4])
        prev = c[-1]
    return t, o, c


def agent_pools() -> dict:
    """The paper agent's per-pool dip state (cursor, busy_until) as last committed to main."""
    subprocess.run(["git", "fetch", "-q", "origin", "main"], capture_output=True)
    out = subprocess.run(["git", "show", "origin/main:autotrade/state.json"], capture_output=True, text=True)
    try:
        return json.loads(out.stdout)["strategies"]["dip"]["data"]["pools"]
    except (ValueError, KeyError):
        return {}


def agent_enters_at(t: list, c: list, ag: dict, i: int) -> bool:
    """Replay the paper agent from its committed cursor: does it open at signal bar i (not busy)?"""
    if "cursor" not in ag:
        return False  # the agent hasn't seen this pool yet: it would start from its first sight, no entry
    busy = ag.get("busy_until", 0.0)
    for j in range(L, i + 1):
        if t[j] <= ag["cursor"] or t[j] <= busy:
            continue
        if c[j] / c[j - L] - 1 < -DROP:
            if j == i:
                return True
            busy = t[j] + H * BAR
    return False


def load() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"trips": []}


def save(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1))


def trade(kind: str, mint: str) -> dict | None:
    """Run real_fills.py buy/sell; return the leg it logged (None if nothing was logged)."""
    before = FILLS.read_text().count("\n") if FILLS.exists() else 0
    cmd = [sys.executable, FILLS_SCRIPT, kind, "--real", "--mint", mint, "--out", str(FILLS)]
    if kind == "buy":
        cmd += ["--size", str(args.size)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    log(f"{kind} {mint}: exit {out.returncode} {out.stdout.strip().splitlines()[-1:] if out.stdout else ''} {out.stderr.strip()[-300:]}")
    lines = FILLS.read_text().splitlines() if FILLS.exists() else []
    return json.loads(lines[-1]) if len(lines) > before else None


def watch() -> None:
    if not args.real:
        sys.exit("refusing: pass --real")
    st = load()
    end = time.time() + 60 * args.minutes
    while time.time() < end:
        now = time.time()
        # exits: the rule sells at the close of bar exit_t
        for tr in st["trips"]:
            if tr["status"] == "open" and now >= tr["exit_t"] + BAR:
                leg = trade("sell", tr["mint"])
                tr["sell"] = leg
                ok = bool(leg and leg.get("effects") and not leg["effects"].get("err"))
                tr["status"] = "closed" if ok else "open"
                save(st)
        live = [tr for tr in st["trips"] if tr["status"] != "failed"]  # a buy that failed spent nothing
        started = len(live)
        if started >= args.trips and all(tr["status"] == "closed" for tr in live):
            log("all trips closed")
            return
        # entries: scan right after each bar ends. GeckoTerminal's first close after bar end was final
        # 95% of the time (fast_dip.py, 2026-10-10); the old +75 s wake and a single pass cost minutes.
        # Pools whose bar i isn't out yet are polled again until +4 min.
        if started < args.trips:
            busy = {tr["pool"] for tr in st["trips"] if tr["status"] == "open"}
            agent = agent_pools()
            bar_i = (int(time.time()) // BAR - 1) * BAR
            pending = [p for p in pools() if p["pool"] not in busy]
            while pending and time.time() < bar_i + BAR + 240:
                retry = []
                for p in pending:
                    if sum(tr["status"] != "failed" for tr in st["trips"]) >= args.trips:
                        retry = []
                        break
                    try:
                        t, o, c = grid(bars(p["pool"]), time.time())
                    except Exception as exc:  # noqa: BLE001
                        log(f"{p['name']}: data error {str(exc)[:120]}")
                        continue
                    if len(t) <= L:
                        continue
                    if t[-1] < bar_i:
                        retry.append(p)  # bar i not published yet
                        continue
                    i = len(t) - 1
                    ret = c[i] / c[i - L] - 1
                    if ret < -DROP and not agent_enters_at(t, c, agent.get(p["pool"], {}), i):
                        log(f"{p['name']}: signal, but the paper agent is still in this pool (skipped: no paper twin)")
                    elif ret < -DROP:
                        log(f"SIGNAL {p['name']}: close fell {-100 * ret:.1f}% over {L} bars (bar {t[i]})")
                        tr = {"key": f"{p['pool']}:{t[i]}", "pool": p["pool"], "mint": p["mint"], "label": p["name"],
                              "signal_t": t[i], "entry_bar": t[i] + BAR, "exit_t": t[i] + H * BAR, "drop": ret, "status": "buying"}
                        st["trips"].append(tr)
                        save(st)
                        leg = trade("buy", p["mint"])
                        tr["buy"] = leg
                        ok = bool(leg and leg.get("effects") and not leg["effects"].get("err") and leg["effects"]["token_change"] > 0)
                        tr["status"] = "open" if ok else "failed"
                        save(st)
                        busy.add(p["pool"])
                pending = retry
        # wake 2 s after the next bar ends
        nxt = (int(time.time()) // BAR + 1) * BAR + 2
        time.sleep(max(1.0, min(nxt - time.time(), end - time.time())))
    log("watch window over; run again to resume")


def report() -> None:
    st = load()
    paper = {}
    for line in Path("autotrade/trades.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r.get("strategy", "dip") == "dip" and r.get("meta", {}).get("key"):
            paper.setdefault(r["meta"]["key"], r)
    for tr in st["trips"]:
        b, s = tr.get("buy") or {}, tr.get("sell") or {}
        be, se = b.get("effects") or {}, s.get("effects") or {}
        line = f"{tr['label']} signal {datetime.fromtimestamp(tr['signal_t'], timezone.utc):%m-%d %H:%M} drop {-100 * tr['drop']:.1f}% [{tr['status']}]"
        if be:
            spent = -be["sol_change"] - be["ata_rent_sol"]
            line += f"\n  real buy: {spent:.6f} SOL (+ rent {be['ata_rent_sol']:.6f}), sent {b.get('sent_at', 0) - tr['entry_bar']:+.0f} s after bar t+1 opened"
            if se:
                back = se["sol_change"]
                line += f"\n  real sell: {back:.6f} SOL, sent {s.get('sent_at', 0) - tr['exit_t'] - BAR:+.0f} s after bar t+48 closed"
                line += f"\n  real net (SOL, rent excluded): {100 * (back / spent - 1):+.2f}%"
                try:
                    by_t = {r[0]: r for r in bars(tr["pool"], "token")}  # SOL-quoted bars
                except Exception:  # noqa: BLE001
                    by_t = {}
                if tr["entry_bar"] in by_t and tr["exit_t"] in by_t:
                    g = by_t[tr["exit_t"]][4] / by_t[tr["entry_bar"]][1]
                    line += f"\n  rule's gross in SOL (bar t+1 open -> bar t+48 close): {100 * (g - 1):+.2f}%"
        pp = paper.get(tr["key"])
        if pp:
            gross = pp["exit_price"] / pp["entry_price"] - 1
            line += f"\n  paper agent: gross {100 * gross:+.2f}% (USD), net {100 * pp['meta'].get('alt_net_return', float('nan')):+.2f}% at measured fees"
        else:
            line += "\n  paper agent: no closed trade for this key yet"
        print(line)


{"watch": watch, "report": report}[args.mode]()
