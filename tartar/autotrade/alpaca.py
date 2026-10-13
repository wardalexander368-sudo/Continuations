"""Alpaca paper mirror: the US-spot paper strategies' trades sent as real orders to an Alpaca *paper* account.

The paper book keeps its registered cost model and is scored as before. Beside it, each entry of a mirrored
strategy (config ``alpaca_paper.strategies``, venue ``coinbase``) is bought on Alpaca's paper endpoint at the
paper size, and sold when the paper position closes. The fills go to ``alpaca_fills.jsonl`` and onto the trade
(``meta["alpaca"]``), so the ~0.39%/side Alpaca cost assumption (handoff/autotrade.md) becomes a measurement:
fill price against the paper reference at entry and exit, plus Alpaca's fee schedule.

Paper only, in every mode: the only URL here is ``https://paper-api.alpaca.markets``, which rejects live keys.
There is no live Alpaca route; going live needs its own route, the gate, and AJ's word.
Keys: ``APCA_API_KEY_ID`` and ``APCA_API_SECRET_KEY`` (GitHub secrets, passed by autotrade.yml). Either missing
means no mirror: the strategies paper-trade exactly as before. A failed Alpaca call never stops the run."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

PAPER_URL = "https://paper-api.alpaca.markets"
DATA_URL = "https://data.alpaca.markets"
KEY_VARS = ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY")

ALPACA_DEFAULTS = {
    "enabled": False,
    "strategies": [],          # paper strategies to mirror (venue "coinbase" only: Alpaca has no perps)
    "taker_fee": 0.0025,       # Alpaca crypto tier 1 taker; the buy fee comes out of the coin received
    "max_spread_bps": None,    # skip an entry when Alpaca's quoted spread is wider (None: record only)
    "fill_wait_s": 10,         # wait this long for a market order's fill, then look again at the exit
}


def keys(env) -> tuple[str, str] | None:
    vals = tuple(env.get(k) or "" for k in KEY_VARS)
    return vals if all(vals) else None


class AlpacaPaper:
    """The few trading-API calls the mirror needs, against the paper endpoint only."""

    def __init__(self, key_id: str, secret: str, http=None, sleep=time.sleep):
        if http is None:
            import httpx

            http = httpx.Client(timeout=30)
        self.http, self.sleep = http, sleep
        self.headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret}

    def _req(self, method: str, path: str, base: str = PAPER_URL, **kw) -> dict:
        if base not in (PAPER_URL, DATA_URL):  # never a live-money endpoint (a raise, not an assert: -O strips asserts)
            raise ValueError(f"Alpaca base URL {base!r} is not the paper or data endpoint")
        r = self.http.request(method, base + path, headers=self.headers, **kw)
        if r.status_code >= 400:
            raise AlpacaError(r.status_code, r.text[:200])
        return r.json()

    def account(self) -> dict:
        return self._req("GET", "/v2/account")

    def asset(self, symbol: str) -> dict:
        return self._req("GET", f"/v2/assets/{symbol.replace('/', '')}")

    def submit(self, client_order_id: str, symbol: str, side: str, notional: float | None = None, qty: float | None = None) -> dict:
        body = {"symbol": symbol, "side": side, "type": "market", "time_in_force": "gtc", "client_order_id": client_order_id}
        body.update({"notional": f"{notional:.2f}"} if notional is not None else {"qty": f"{qty:.9f}".rstrip("0").rstrip(".")})
        try:
            return self._req("POST", "/v2/orders", json=body)
        except AlpacaError as exc:  # a repeated client_order_id (a rerun after a crash) returns the order already placed
            if exc.status == 422 and "client_order_id" in exc.text:
                return self.by_client_id(client_order_id)
            raise

    def by_client_id(self, client_order_id: str) -> dict:
        return self._req("GET", "/v2/orders:by_client_order_id", params={"client_order_id": client_order_id})

    def order(self, order_id: str) -> dict:
        return self._req("GET", f"/v2/orders/{order_id}")

    def wait_fill(self, order: dict, wait_s: float) -> dict:
        t = 0.0
        while order.get("status") not in ("filled", "canceled", "expired", "rejected") and t < wait_s:
            self.sleep(1.0)
            t += 1.0
            order = self.order(order["id"])
        return order

    def position_qty(self, symbol: str) -> float:
        try:
            return float(self._req("GET", f"/v2/positions/{symbol.replace('/', '')}")["qty"])
        except AlpacaError as exc:
            if exc.status == 404:
                return 0.0
            raise

    def positions(self) -> list[dict]:
        return self._req("GET", "/v2/positions")

    def open_orders(self) -> list[dict]:
        return self._req("GET", "/v2/orders", params={"status": "open", "limit": 500})

    def spread_bps(self, symbol: str) -> float | None:
        q = self._req("GET", "/v1beta3/crypto/us/latest/quotes", base=DATA_URL, params={"symbols": symbol})["quotes"][symbol]
        bid, ask = float(q["bp"]), float(q["ap"])
        return 1e4 * (ask - bid) / ((ask + bid) / 2) if bid > 0 and ask > 0 else None


class AlpacaError(Exception):
    def __init__(self, status: int, text: str):
        super().__init__(f"HTTP {status}: {text}")
        self.status, self.text = status, text


def symbol(asset: str) -> str:
    return f"{asset.upper()}/USD"


def _fill(order: dict) -> tuple[float, float] | None:
    if order.get("status") != "filled" and not float(order.get("filled_qty") or 0):
        return None
    qty, price = float(order["filled_qty"]), float(order.get("filled_avg_price") or "nan")
    return (qty, price) if math.isfinite(qty) and math.isfinite(price) and qty > 0 and price > 0 else None


class AlpacaMirror:
    """Built once per run; ``make_mirror`` returns None when it is off or has no keys."""

    def __init__(self, cfg: dict, client: AlpacaPaper, root: Path | None, journal=None):
        self.cfg, self.client, self.root, self.journal = cfg, client, Path(root) if root else None, journal
        self._ok: bool | None = None
        self.last_error, self.crypto_status = "", None
        self._incr: dict[str, float] = {}

    def log(self, row: dict) -> None:
        if self.root:
            with (self.root / "alpaca_fills.jsonl").open("a") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")

    def error(self, row: dict) -> None:
        self.log({"event": "error", **row})
        if self.journal:
            self.journal({"event": "alpaca_error", **row})

    def ready(self, now: float, quiet: bool = False) -> bool:
        """Once per run: the key must open a paper account (paper account numbers start with PA)."""
        if self._ok is None:
            try:
                acct = self.client.account()
                self._ok = str(acct.get("account_number", "")).startswith("PA") and acct.get("status") == "ACTIVE"
                self.crypto_status = acct.get("crypto_status")
                if not self._ok:
                    self.last_error = f"account not an active paper account (status {acct.get('status')})"
            except Exception as exc:  # noqa: BLE001
                self._ok = False
                self.last_error = f"account check: {type(exc).__name__}: {exc}"[:300]
            if not self._ok and not quiet:
                self.error({"at": now, "error": self.last_error})
        return self._ok

    def status(self, now: float) -> dict:
        """The per-run key check, kept in state.json (no row in alpaca_fills.jsonl unless a trade needed it)."""
        ok = self.ready(now, quiet=True)
        return {"checked_at": now, "ok": ok, **({"crypto_status": self.crypto_status} if ok else {"error": self.last_error})}

    def wants(self, strategy: str, meta: dict) -> bool:
        return strategy in self.cfg["strategies"] and meta.get("venue") == "coinbase"

    def on_open(self, pos, intent, now: float) -> None:
        if not self.wants(pos.strategy, pos.meta) or intent.meta.get("shadow") or not self.ready(now):
            return
        sym = symbol(pos.asset)
        cid = f"tt:{pos.strategy}:{pos.asset}:{pos.meta.get('signal_hour', pos.id)}:buy"
        rec = {"event": "buy", "at": now, "strategy": pos.strategy, "position": pos.id, "symbol": sym, "client_order_id": cid,
               "notional_usd": round(pos.notional_usd, 2), "paper_price_in": intent.price, "paper_at": intent.at}
        try:
            spread = self.client.spread_bps(sym)
        except Exception:  # noqa: BLE001 - the quote is a measurement, not a requirement
            spread = None
        rec["spread_bps"] = spread
        cap = self.cfg.get("max_spread_bps")
        if cap is not None and spread is not None and spread > cap:
            self.log({**rec, "event": "skip", "reason": f"spread {spread:.0f} bp > {cap} bp"})
            return
        try:
            order = self.client.wait_fill(self.client.submit(cid, sym, "buy", notional=pos.notional_usd), self.cfg["fill_wait_s"])
        except Exception as exc:  # noqa: BLE001
            self.error({**rec, "error": f"{type(exc).__name__}: {exc}"[:300]})
            return
        twin = {"symbol": sym, "buy_id": order["id"], "buy_cid": cid, "paper_price_in": intent.price, "spread_in_bps": spread}
        f = _fill(order)
        if f:
            twin.update(qty=f[0], price_in=f[1], entry_gap_bps=1e4 * (f[1] / intent.price - 1))
        pos.meta["alpaca"] = twin
        self.log({**rec, "order_status": order.get("status"), **twin})

    def on_close(self, pos, trade, intent, now: float) -> None:
        twin = pos.meta.get("alpaca")
        if not twin or not self.ready(now):
            return
        sym = twin["symbol"]
        rec = {"event": "sell", "at": now, "strategy": pos.strategy, "position": pos.id, "symbol": sym}
        try:
            if "qty" not in twin:  # the buy had not filled when last looked at
                f = _fill(self.client.order(twin["buy_id"]))
                if not f:
                    self.error({**rec, "error": "buy never filled; nothing to sell"})
                    return
                twin.update(qty=f[0], price_in=f[1], entry_gap_bps=1e4 * (f[1] / twin["paper_price_in"] - 1))
            incr = self._incr.get(sym)
            if incr is None:
                incr = self._incr[sym] = float(self.client.asset(sym).get("min_trade_increment") or 1e-9)
            held = self.client.position_qty(sym)
            want = twin["qty"] * (1 - self.cfg["taker_fee"])  # the buy fee was taken out of the coin received
            qty = math.floor(min(want, held) / incr) * incr
            if qty <= 0:
                self.error({**rec, "error": f"nothing to sell (held {held}, want {want})"})
                return
            order = self.client.wait_fill(self.client.submit(f"tt:{pos.id}:sell", sym, "sell", qty=qty), self.cfg["fill_wait_s"])
            f = _fill(order)
            if not f:
                self.error({**rec, "error": f"sell not filled (status {order.get('status')})", "sell_id": order.get("id")})
                return
        except Exception as exc:  # noqa: BLE001
            self.error({**rec, "error": f"{type(exc).__name__}: {exc}"[:300]})
            return
        fee = self.cfg["taker_fee"]
        gross = f[1] / twin["price_in"] - 1
        cmp = {"symbol": sym, "price_in": twin["price_in"], "price_out": f[1], "qty_in": twin["qty"], "qty_out": f[0],
               "paper_price_in": twin["paper_price_in"], "paper_price_out": intent.price,
               "entry_gap_bps": twin["entry_gap_bps"], "exit_gap_bps": 1e4 * (1 - f[1] / intent.price),
               "spread_in_bps": twin.get("spread_in_bps"),
               "alpaca_gross_return": gross, "alpaca_net_return": (1 + gross) * (1 - fee) ** 2 - 1,
               "paper_net_return": trade.net_return, "fee_per_side": fee}
        # measured cost per side: fee plus the average fill gap against the paper reference (the 0.39% assumption)
        cmp["measured_side_cost"] = fee + (cmp["entry_gap_bps"] + cmp["exit_gap_bps"]) / 2e4
        trade.meta["alpaca"] = cmp
        self.log({**rec, "sell_id": order["id"], **cmp})


RECON_MIN_USD = 1.0      # a holding differing from the book by less than this (or RECON_FRAC of it) is rounding dust
RECON_FRAC = 0.02
RECON_ORDER_AGE_S = 3600  # an order still open after an hour is stuck (market orders fill in seconds)


def _ts(s: str | None) -> float | None:
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def reconcile(client: AlpacaPaper, positions, taker_fee: float, now: float) -> dict:
    """Does the paper account hold exactly what the book's mirrored positions say? (live rule section 5: in live
    mode an unmatched order or holding must write HALT; on paper it turns health red, so the check is proven first.)

    Expected per symbol: each open book position's filled Alpaca buy, less the fee Alpaca took in coin. Crypto
    holdings only (the account may later hold other asset classes with their own checks)."""
    want: dict[str, float] = {}
    mark: dict[str, float] = {}
    unconfirmed = []
    for p in positions:
        twin = (p.meta or {}).get("alpaca")
        if not twin:
            continue
        key = twin["symbol"].replace("/", "")
        if "qty" not in twin:  # the buy had not filled when last looked at: can't say what it should hold
            unconfirmed.append(key)
            continue
        want[key] = want.get(key, 0.0) + twin["qty"] * (1 - taker_fee)
        mark[key] = p.mark_price or twin.get("price_in") or 0.0
    held, price = {}, {}
    for r in client.positions():
        if r.get("asset_class", "crypto") != "crypto":
            continue
        key = str(r["symbol"]).replace("/", "")
        held[key] = float(r["qty"])
        price[key] = float(r.get("current_price") or 0) or mark.get(key, 0.0)
    mismatches = []
    for key in sorted(set(want) | set(held)):
        if key in unconfirmed:
            continue
        w, h = want.get(key, 0.0), held.get(key, 0.0)
        px = price.get(key) or mark.get(key) or 0.0
        diff_usd = abs(h - w) * px
        if diff_usd > max(RECON_MIN_USD, RECON_FRAC * w * px):
            mismatches.append({"symbol": key, "book_qty": round(w, 9), "held_qty": round(h, 9), "diff_usd": round(diff_usd, 2)})
    stuck = []
    for o in client.open_orders():
        t = _ts(o.get("submitted_at") or o.get("created_at"))
        if t is None or now - t > RECON_ORDER_AGE_S:
            stuck.append({"symbol": o.get("symbol"), "side": o.get("side"), "client_order_id": o.get("client_order_id"),
                          "submitted_at": o.get("submitted_at")})
    return {"checked_at": now, "ok": not mismatches and not stuck, "mismatches": mismatches, "stuck_orders": stuck,
            "unconfirmed": sorted(set(unconfirmed)), "symbols": len(set(want) | set(held))}


def reconcile_safe(mirror: "AlpacaMirror | None", positions, now: float) -> dict | None:
    """The runner's call: never raises (the hourly run must not break); a failed check is reported, not hidden."""
    if mirror is None or not mirror.ready(now, quiet=True):
        return None
    try:
        return reconcile(mirror.client, positions, mirror.cfg["taker_fee"], now)
    except Exception as exc:  # noqa: BLE001
        return {"checked_at": now, "ok": None, "error": f"{type(exc).__name__}: {exc}"[:300]}


def health_items(root: Path, now: float | None = None) -> list[dict]:
    """Health check "Alpaca paper account matches book", from state.json (written by the hourly run)."""
    try:
        state = json.loads((Path(root) / "state.json").read_text()) if (Path(root) / "state.json").exists() else {}
        rec = (state.get("alpaca") or {}).get("reconcile")
        if not rec:
            return [{"check": "Alpaca account vs book", "level": "green", "detail": "not checked yet (needs the paper keys)"}]
        if now is not None and now - rec["checked_at"] > 3 * 3600:
            return [{"check": "Alpaca account vs book", "level": "yellow",
                     "detail": f"last checked {(now - rec['checked_at']) / 3600:.0f} h ago"}]
        if rec.get("ok") is None:
            return [{"check": "Alpaca account vs book", "level": "yellow", "detail": f"could not check: {rec.get('error')}"[:300]}]
        if not rec["ok"]:
            bits = [f"{m['symbol']} book {m['book_qty']} vs held {m['held_qty']} (${m['diff_usd']})" for m in rec["mismatches"]]
            bits += [f"{o['side']} {o['symbol']} open since {o['submitted_at']}" for o in rec["stuck_orders"]]
            return [{"check": "Alpaca account vs book", "level": "red",
                     "detail": ("paper account differs from the book (live rule: would write HALT): " + "; ".join(bits))[:400]}]
        return [{"check": "Alpaca account vs book", "level": "green",
                 "detail": f"{rec['symbols']} symbol(s) match the book"
                           + (f"; buys not yet confirmed: {', '.join(rec['unconfirmed'])}" if rec.get("unconfirmed") else "")}]
    except Exception as exc:  # noqa: BLE001 - never break the health run
        return [{"check": "Alpaca account vs book", "level": "yellow", "detail": f"could not read state: {type(exc).__name__}: {exc}"[:300]}]


def make_mirror(config: dict, env, root=None, journal=None, client=None) -> AlpacaMirror | None:
    cfg = {**ALPACA_DEFAULTS, **(config.get("alpaca_paper") or {})}
    if not cfg["enabled"] or not cfg["strategies"]:
        return None
    if client is None:
        k = keys(env)
        if not k:
            return None
        client = AlpacaPaper(*k)
    return AlpacaMirror(cfg, client, root, journal)


def report_lines(root: Path, state: dict | None = None) -> list[str]:
    path = Path(root) / "alpaca_fills.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
    st = (state or {}).get("alpaca")
    if not rows and not st:
        return []
    head = ["", "## Alpaca paper fills (US spot, paper account; alpaca_fills.jsonl)", ""]
    rec = (st or {}).get("reconcile")
    if rec:
        head.append("Account vs book: " + ("matches" if rec.get("ok") else "could not check" if rec.get("ok") is None else
                                          f"**differs** ({len(rec.get('mismatches', []))} holding(s), {len(rec.get('stuck_orders', []))} stuck order(s))") + ".")
    if st:
        head.append("Key check this run: " + ("paper account OK" + (f", crypto {st['crypto_status']}" if st.get("crypto_status") else "")
                                             if st.get("ok") else f"not working ({st.get('error')})") + ".")
    if not rows:
        return head
    sells = [r for r in rows if r.get("event") == "sell"]
    out = head + [f"{sum(r.get('event') == 'buy' for r in rows)} buys, {len(sells)} round trips, "
           f"{sum(r.get('event') == 'error' for r in rows)} errors."]
    if sells:
        n = len(sells)
        mean = lambda k: sum(r[k] for r in sells) / n  # noqa: E731
        out.append(f"Mean measured cost per side {100 * mean('measured_side_cost'):.2f}% (assumed 0.39%): entry gap "
                   f"{mean('entry_gap_bps'):+.0f} bp, exit gap {mean('exit_gap_bps'):+.0f} bp, fee {100 * sells[0]['fee_per_side']:.2f}%. "
                   f"Mean net per trade {100 * mean('alpaca_net_return'):+.2f}% on Alpaca vs {100 * mean('paper_net_return'):+.2f}% on paper.")
    return out
