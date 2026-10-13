"""The always-on box: CAPIT entries minutes after the signal hour closes, on an Alpaca *paper* account.

AJ approved the ~$5/month always-on machine on 2026-10-13 (thread "Perfect trading system vs ours"). The hourly
GitHub runner reaches a capit signal ~90 minutes after the hour closes, which costs about a third of the edge
(+4.11%/trade at a 15-minute entry vs +1.93% at ~90 min, handoff/reviews/timing-2026-10-11.md). This loop runs on
the box (not in GitHub Actions: no always-on Actions), checks every coin a minute or two after each hour closes with
the registered CAPIT Z=4 signal (``coinbase_pattern.signals``, the same code the paper book uses), buys at once on
Alpaca paper and sells 24 hours later. It measures what the box adds; the registered ``us_capit`` lines are unchanged.

Paper only: orders go through ``alpaca.AlpacaPaper``, which refuses any URL but the paper and data endpoints, and the
key must open an active paper account (number starting PA). Use a **second** Alpaca paper account for the box, so
the hourly runner's account-vs-book check (``alpaca.reconcile``) keeps seeing only its own trades.

Safety: one position per coin, ``--usd`` per trade (default $100, the live rule's stake), at most ``--max-open``
open. The file ``<dir>/HALT`` stops new entries (exits still run). Every pass compares the account's crypto holdings
with the box's open positions; a mismatch or an order open over an hour writes ``HALT`` (live rule section 5).

Files in ``<dir>`` (default ``box/``): ``state.json`` (open positions, last hour checked) and ``fills.jsonl``. With
``--push`` they are committed hourly to the branch ``box-data`` (never ``main``), so the project can read them.

    python -m tartar.autotrade.box run [--dir box] [--usd 100] [--coins BTC,ETH,...] [--push]
    python -m tartar.autotrade.box once     # one pass, then exit (for testing on the box)

Keys: ``APCA_API_KEY_ID`` / ``APCA_API_SECRET_KEY`` in the box's environment (never in the repo).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from . import alpaca
from .strategies.coinbase_pattern import CB, COINS, G, RULES, WIN, hourly, signals

SETTLE_S = 90         # look this long after the hour, so the hour's last 15-minute candle is published
HOLD_H = RULES["capit"]["hold"]
LOOKBACK_H = WIN + 30


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def candles(http, coin: str, t0: int, t1: int) -> list:
    """Coinbase 15-minute candles [t, o, h, l, c, v] with t0 <= t < t1 (300 per request)."""
    out, t = [], t0
    while t < t1:
        e = min(t + 300 * G, t1)
        r = http.get(f"{CB}/products/{coin}-USD/candles", params={"granularity": G, "start": _iso(t), "end": _iso(e - G)})
        r.raise_for_status()
        out += [[int(ts), op, hi, lo, cl, v] for ts, lo, hi, op, cl, v in r.json() if t <= ts < e]
        t = e
    return out


class Box:
    def __init__(self, root: Path, client: alpaca.AlpacaPaper, http, coins=None, usd: float = 100.0, max_open: int = 11,
                 taker_fee: float = 0.0025, fill_wait_s: float = 10):
        self.root, self.client, self.http = Path(root), client, http
        self.coins, self.usd, self.max_open, self.fee, self.wait = list(coins or COINS), usd, max_open, taker_fee, fill_wait_s
        self.root.mkdir(parents=True, exist_ok=True)
        f = self.root / "state.json"
        self.state = json.loads(f.read_text()) if f.exists() else {"done_hour": None, "open": {}}

    def save(self) -> None:
        tmp = self.root / "state.json.tmp"
        tmp.write_text(json.dumps(self.state, indent=1, sort_keys=True))
        tmp.replace(self.root / "state.json")

    def log(self, row: dict) -> None:
        with (self.root / "fills.jsonl").open("a") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    def halted(self) -> str | None:
        f = self.root / "HALT"
        return (f.read_text().strip() or "HALT file present") if f.exists() else None

    def halt(self, reason: str, now: float) -> None:
        (self.root / "HALT").write_text(reason + "\n")
        self.log({"event": "halt", "at": now, "reason": reason})

    def paper_ok(self) -> bool:
        a = self.client.account()
        return str(a.get("account_number", "")).startswith("PA") and a.get("status") == "ACTIVE"

    def step(self, now: float) -> None:
        """One pass: exits that are due, then (once per hour, after it settles) new signals, then the account check."""
        if not self.paper_ok():
            raise RuntimeError("the key does not open an active Alpaca paper account; nothing sent")
        for coin, p in list(self.state["open"].items()):
            if p["exit_at"] <= now:
                self.sell(coin, p, now)
        h = int((now - SETTLE_S) // 3600) - 1  # the last hour whose candles are final
        if self.state["done_hour"] is None:
            self.state["done_hour"] = h - 1  # first start: look at the last closed hour only
        if h > self.state["done_hour"]:
            for coin in self.coins:
                try:
                    self.check(coin, h, now)
                except Exception as exc:  # noqa: BLE001 - one coin's data error must not stop the others
                    self.log({"event": "error", "at": now, "coin": coin, "hour": h, "error": f"{type(exc).__name__}: {exc}"[:300]})
            self.state["done_hour"] = h
        self.save()
        self.reconcile(now)

    def check(self, coin: str, h: int, now: float) -> None:
        lo = h - LOOKBACK_H
        rows = candles(self.http, coin, lo * 3600, (h + 1) * 3600)
        O, Hh, L, C, V, C15 = hourly(lo, rows, LOOKBACK_H + 1)
        if not signals("capit", C, V)[h - lo]:
            return
        why = None if not self.halted() else f"halted: {self.halted()}"
        if coin in self.state["open"]:
            why = "already holding this coin"
        elif len(self.state["open"]) >= self.max_open:
            why = f"{self.max_open} positions open"
        rec = {"at": now, "coin": coin, "signal_hour": h, "signal_close": float(C[h - lo]),
               "latency_s": now - (h + 1) * 3600}
        if why:
            self.log({"event": "skip", **rec, "reason": why})
            return
        sym = alpaca.symbol(coin)
        cid = f"box:{coin}:{h}:buy"
        order = self.client.wait_fill(self.client.submit(cid, sym, "buy", notional=self.usd), self.wait)
        f = alpaca._fill(order)
        p = {"symbol": sym, "buy_id": order["id"], "signal_hour": h, "signal_close": rec["signal_close"],
             "entry_at": now, "exit_at": now + HOLD_H * 3600, "usd": self.usd}
        if f:
            p.update(qty=f[0], price_in=f[1], gap_bps=1e4 * (f[1] / rec["signal_close"] - 1))
        self.state["open"][coin] = p
        self.save()
        self.log({"event": "buy", **rec, "order_status": order.get("status"), **p})

    def sell(self, coin: str, p: dict, now: float) -> None:
        if "qty" not in p:
            f = alpaca._fill(self.client.order(p["buy_id"]))
            if not f:
                self.halt(f"{coin}: buy {p['buy_id']} never filled", now)
                return
            p.update(qty=f[0], price_in=f[1])
        held = self.client.position_qty(p["symbol"])
        incr = float(self.client.asset(p["symbol"]).get("min_trade_increment") or 1e-9)
        qty = int(min(p["qty"] * (1 - self.fee), held) / incr) * incr
        if qty <= 0:
            self.halt(f"{coin}: nothing to sell (held {held})", now)
            return
        order = self.client.wait_fill(self.client.submit(f"box:{coin}:{p['signal_hour']}:sell", p["symbol"], "sell", qty=qty), self.wait)
        f = alpaca._fill(order)
        if not f:
            self.halt(f"{coin}: sell not filled (status {order.get('status')})", now)
            return
        gross = f[1] / p["price_in"] - 1
        self.log({"event": "sell", "at": now, "coin": coin, **p, "price_out": f[1], "qty_out": f[0], "gross_return": gross,
                  "net_return": (1 + gross) * (1 - self.fee) ** 2 - 1})
        del self.state["open"][coin]
        self.save()

    def reconcile(self, now: float) -> None:
        pos = [SimpleNamespace(meta={"alpaca": p}, mark_price=p.get("price_in")) for p in self.state["open"].values()]
        rec = alpaca.reconcile(self.client, pos, self.fee, now)
        self.state["reconcile"] = rec
        self.save()
        if not rec["ok"] and not self.halted():
            self.halt(f"account differs from the box's book: {rec['mismatches'] + rec['stuck_orders']}"[:500], now)


def push(root: Path, now: float) -> None:
    """Commit the box's files to the branch ``box-data`` (never main). Needs a git checkout with push access."""
    repo = Path(subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                               check=True).stdout.strip())
    rel = root.resolve().relative_to(repo)
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)  # noqa: E731
    if run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() != "box-data":
        raise RuntimeError("the box's checkout must be on branch box-data")
    run("add", "-f", str(rel / "state.json"), str(rel / "fills.jsonl"))
    if run("diff", "--cached", "--quiet").returncode:
        run("commit", "-m", f"box: {_iso(now)[:16]} UTC")
        run("push", "origin", "box-data")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m tartar.autotrade.box")
    ap.add_argument("cmd", choices=["run", "once"])
    ap.add_argument("--dir", default="box")
    ap.add_argument("--usd", type=float, default=100.0)
    ap.add_argument("--max-open", type=int, default=11)
    ap.add_argument("--coins", default=",".join(COINS))
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args(argv)
    k = alpaca.keys(os.environ)
    if not k:
        raise SystemExit("set APCA_API_KEY_ID and APCA_API_SECRET_KEY (a paper account's keys)")
    import httpx

    http = httpx.Client(timeout=30)
    box = Box(Path(a.dir), alpaca.AlpacaPaper(*k, http=http), http, coins=a.coins.split(","), usd=a.usd, max_open=a.max_open)
    last_push = 0.0
    while True:
        now = time.time()
        try:
            box.step(now)
        except Exception as exc:  # noqa: BLE001 - log and keep going; a broken key keeps failing loudly in the log
            box.log({"event": "error", "at": now, "error": f"{type(exc).__name__}: {exc}"[:300]})
        if a.push and now - last_push >= 3600:
            try:
                push(Path(a.dir), now)
                last_push = now
            except Exception as exc:  # noqa: BLE001
                box.log({"event": "push_error", "at": now, "error": f"{type(exc).__name__}: {exc}"[:300]})
        if a.cmd == "once":
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
