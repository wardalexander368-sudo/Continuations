"""Restart and overlap safety for the live path.

The agent runs in a GitHub job that loops for ~5.5 h; the schedule queues the next job every 2 h. Live
trading has to stay correct when a job dies mid-order or two writers meet. Four layers:

1. **One trader.** The workflow's concurrency group (``autotrade-main``, never cancelling the running
   job) keeps a second job queued, not running. On one machine, ``run_lock`` (an exclusive ``flock`` on a
   lock file named after the checkout) stops two processes on the same checkout. In mode ``live`` a **lease** in
   ``state.json`` (holder = the GitHub run id, renewed each run, released when the loop ends) makes any
   other holder skip its run while the lease is fresh, e.g. a hand run with keys on another machine.
2. **Pending before sending.** Every live buy and sell is written to ``autotrade/pending.json`` (atomic
   replace) before the executor is called and removed after its fill is logged, so an order a crash
   interrupted is known. The workflow commits ``autotrade/`` even when a run fails.
3. **Idempotent orders.** A buy's order id is ``strategy|key|signal time``: the same entry re-emitted
   after a crash has the same id. Tokens a dead run bought for it are claimed by that id (``live.unclaimed``)
   and adopted as the twin instead of buying again.
4. **Reconcile before trading.** Each run first compares the wallet's real token holdings with what the
   book says it holds (open twins and orphans), for every mint the fill log or a pending order names
   (airdropped spam is ignored). Extra tokens that a pending order or a logged buy explains become a
   claim; anything else becomes an orphan and halts live entries. Missing tokens with a pending sell
   mean the sell landed unrecorded; otherwise an orphan and a halt. The wallet's SOL is checked against
   the balance recorded at the end of the last run: an unexplained drop counts against the live daily
   loss cap and halts live entries.

Covers the SOL spot twins (Jupiter / Lightning, and their quote-only dry twin, whose wallet is
simulated in ``autotrade/dry_wallet.json`` so this can be tested end to end) and, in ``reconcile_perps``,
the Hyperliquid perp twins (basket shorts included): each perp order carries a client order id
(``perps.cloid``) fixed by what it is for, a retry looks that id up and adopts its fill, and the
account's positions and open orders must equal the book's legs (plus orders a dead run filled) or perp
entries stop (``live.perps_halted``; closes still run, reduce-only). The dry perp route simulates the
account in ``autotrade/dry_perp_account.json``. USD-spot twins (the basket's JLP leg) are dry-only.
"""

from __future__ import annotations

import json
import os
import socket
import time
from contextlib import contextmanager
from pathlib import Path

LEASE_TTL_S = 600         # a lease not renewed for this long is free
CLAIM_TTL_S = 3600        # a claim the strategy never re-emits becomes an orphan
TOKEN_SLACK = 0           # base units of disagreement tolerated
SOL_SLACK = 0.001         # SOL drop between runs tolerated (rounding, rent-exempt quirks)


class Busy(RuntimeError):
    pass


def holder_id(env=None) -> str:
    env = os.environ if env is None else env
    if env.get("GITHUB_RUN_ID"):
        return f"gha:{env['GITHUB_RUN_ID']}"
    return f"local:{socket.gethostname()}:{os.getpid()}"


@contextmanager
def run_lock(root: Path):
    """Exclusive per-checkout lock for the length of a run; raises Busy if another process holds it."""
    import fcntl

    import hashlib
    import tempfile

    key = hashlib.sha1(str(Path(root).resolve()).encode()).hexdigest()[:12]
    path = Path(tempfile.gettempdir()) / f"tartar-autotrade-{key}.lock"  # outside autotrade/, which is committed
    f = path.open("a+")
    try:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Busy(f"another run holds {path}") from exc
        yield
    finally:
        f.close()


def lease_blocker(state: dict, holder: str, now: float) -> str | None:
    """The other holder whose fresh lease blocks this run, else None (and the lease is taken)."""
    lease = state.get("lease") or {}
    if lease.get("holder") not in (None, holder) and now - float(lease.get("at", 0)) < LEASE_TTL_S:
        return f"{lease['holder']} (renewed {now - float(lease['at']):.0f} s ago)"
    state["lease"] = {"holder": holder, "at": now}
    return None


def release_lease(state: dict, holder: str) -> bool:
    if (state.get("lease") or {}).get("holder") == holder:
        state["lease"] = None
        return True
    return False


# pending orders

class Pending:
    """``pending.json``: orders sent or about to be sent whose fill is not in the book yet."""

    def __init__(self, root: Path | None):
        self.path = Path(root) / "pending.json" if root else None

    def load(self) -> dict:
        if self.path and self.path.exists():
            return json.loads(self.path.read_text() or "{}")
        return {}

    def _write(self, rows: dict) -> None:
        if not self.path:
            return
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, indent=1, sort_keys=True))
        tmp.replace(self.path)

    def add(self, order_id: str, row: dict) -> None:
        rows = self.load()
        rows[order_id] = row
        self._write(rows)

    def done(self, order_id: str) -> None:
        rows = self.load()
        if rows.pop(order_id, None) is not None:
            self._write(rows)

    def clear(self, perps: bool = False) -> None:
        """Drop the spot entries (or, with ``perps``, the Hyperliquid ones) once a reconcile has settled them."""
        if self.path and self.path.exists():
            self._write({k: r for k, r in self.load().items() if (r.get("venue") == "hyperliquid") != perps})


def buy_order_id(intent) -> str:
    return f"{intent.strategy}|{intent.meta.get('key') or intent.asset}|{intent.at:.0f}"


# reconcile

def _fill_rows(root: Path) -> list[dict]:
    p = Path(root) / "fills.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def reconcile(broker, now: float) -> dict:
    """Bring the book in line with the wallet before any trade. Returns what it found (also journaled)."""
    ledger, root = broker.ledger, broker.root
    st = broker.live_state()
    if not callable(getattr(broker.executor, "holdings", None)):
        return {"at": now, "skipped": "executor cannot read holdings"}
    st.setdefault("unclaimed", {})
    pending = Pending(root)
    pend = {k: r for k, r in pending.load().items() if r.get("venue") != "hyperliquid"}
    report: dict = {"at": now, "claims": [], "orphans": [], "sold_unrecorded": [], "halts": []}

    open_twins = {p.id: p for p in ledger.positions if p.meta.get("live") and _is_sol_spot(p.meta["live"])}
    tracked: dict[str, int] = {}
    for p in open_twins.values():
        t = p.meta["live"]
        if t.get("route") == broker.route and not t.get("sold_unrecorded"):
            tracked[t["mint"]] = tracked.get(t["mint"], 0) + int(t["token_raw"])
    for o in st["orphans"]:
        if o.get("mint") and o.get("route") == broker.route and not o.get("resolved") and o.get("token_raw"):
            tracked[o["mint"]] = tracked.get(o["mint"], 0) + int(o["token_raw"])
    for c in st["unclaimed"].values():
        tracked[c["mint"]] = tracked.get(c["mint"], 0) + int(c["token_raw"])

    # buys the fill log has but the book lost (the run died after logging, before saving state)
    closed = {t.id for t in ledger.trades()}
    orphaned = {o.get("position") for o in st["orphans"]}
    claimed = {c.get("position") for c in st["unclaimed"].values()}
    logged_buys = {}
    for r in _fill_rows(root):
        f = r.get("fill") or {}
        if r.get("event") in ("buy", "usd_buy") and f.get("ok") and r.get("route") == broker.route and r.get("order_id") \
                and r["position"] not in open_twins and r["position"] not in closed and r["position"] not in orphaned \
                and r["position"] not in claimed:
            logged_buys[r["order_id"]] = {"mint": f["mint"], "token_raw": int(f["token_raw"]), "sol_in": f.get("sol", 0.0), "usd_in": f.get("usd"),
                                          "strategy": r["strategy"], "position": r["position"], "rent_sol": f.get("rent_sol", 0.0),
                                          "signature": f.get("signature"), "source": "fill log"}
    pend_buys = {oid: {"mint": r["mint"], "token_raw": None, "sol_in": r.get("sol", 0.0), "usd_in": r.get("usd"), "strategy": r["strategy"],
                       "position": r["position"], "rent_sol": 0.0, "source": "pending order"}
                 for oid, r in pend.items() if r["leg"] in ("buy", "usd_buy") and oid not in logged_buys}
    pend_sells = {r["position"]: r for r in pend.values() if r["leg"] in ("sell", "usd_sell")}

    mints = set(tracked) | {r["mint"] for r in pend.values()} | {b["mint"] for b in logged_buys.values()}
    mints |= {(r.get("fill") or {}).get("mint") for r in _fill_rows(root) if r.get("route") == broker.route} - {None}
    held = broker.executor.holdings(sorted(mints)) if mints else {}

    for mint in sorted(mints):
        have, want = int(held.get(mint, 0)), tracked.get(mint, 0)
        excess = have - want
        if excess > TOKEN_SLACK:
            cands = [(oid, b) for oid, b in {**logged_buys, **pend_buys}.items() if b["mint"] == mint]
            if len(cands) == 1:
                oid, b = cands[0]
                claim = {**b, "token_raw": excess, "at": now}
                st["unclaimed"][oid] = claim
                report["claims"].append({"order_id": oid, **claim})
            else:
                o = {"mint": mint, "route": broker.route, "token_raw": excess, "at": now, "position": None,
                     "error": f"untracked holding: wallet {have}, book {want}" + (f", {len(cands)} candidate orders" if cands else "")}
                st["orphans"].append(o)
                report["orphans"].append(o)
                report["halts"].append(("live", f"reconcile: {o['error']} for {mint}"))
        elif excess < -TOKEN_SLACK:
            gone = -excess
            sold = [p for pid, p in open_twins.items() if pid in pend_sells and p.meta["live"]["mint"] == mint]
            if sold and sum(int(p.meta["live"]["token_raw"]) for p in sold) <= gone:
                for p in sold:
                    p.meta["live"]["sold_unrecorded"] = {"at": now, "signature_unknown": True}
                    report["sold_unrecorded"].append(p.id)
            else:
                strat = next((p.strategy for p in open_twins.values() if p.meta["live"]["mint"] == mint), None)
                o = {"mint": mint, "route": broker.route, "token_raw": 0, "at": now, "position": None, "strategy": strat,
                     "error": f"missing tokens: wallet {have}, book {want}"}
                st["orphans"].append(o)
                report["orphans"].append(o)
                report["halts"].append((strat or "live", f"reconcile: {o['error']} for {mint}"))

    # claims nobody came back for
    for oid, c in list(st["unclaimed"].items()):
        if now - c["at"] > CLAIM_TTL_S:
            o = {**c, "route": broker.route, "error": f"claimed tokens of order {oid} never re-adopted", "at": now}
            st["orphans"].append(o)
            del st["unclaimed"][oid]
            report["orphans"].append(o)
            report["halts"].append((c["strategy"], o["error"]))

    # SOL between runs
    try:
        bal = float(broker.executor.balance_sol())
    except Exception as exc:  # noqa: BLE001 - can't check: don't trade on a book we can't verify
        report["halts"].append(("live", f"reconcile: balance unavailable ({exc})"[:200]))
        bal = None
    last = st.get("wallet_sol")
    if bal is not None and last is not None:
        explained = sum(c.get("sol_in") or 0.0 for c in report["claims"])
        drop = float(last["sol"]) - bal - explained
        report["sol"] = {"last": last["sol"], "now": bal, "explained": explained, "unexplained_drop": drop}
        if drop > SOL_SLACK:
            day = time.strftime("%Y-%m-%d", time.gmtime(now))
            st["daily_sol"][day] = st["daily_sol"].get(day, 0.0) - drop
            report["halts"].append(("live", f"reconcile: wallet SOL fell {drop:.4f} more than the book explains"))

    for scope, reason in report["halts"]:
        if not (st["halted"] if scope == "live" else broker.strat_state(scope)["halted"]):
            broker.halt(scope, reason)
    pending.clear()
    if any(report[k] for k in ("claims", "orphans", "sold_unrecorded", "halts")) or report.get("sol", {}).get("unexplained_drop", 0) > SOL_SLACK:
        ledger.journal({"event": "live_reconcile", **{k: v for k, v in report.items() if k != "halts"},
                        "halts": [list(h) for h in report["halts"]]})
    return report


def record_wallet(broker, now: float) -> None:
    try:
        broker.live_state()["wallet_sol"] = {"sol": float(broker.executor.balance_sol()), "at": now}
    except Exception:  # noqa: BLE001 - next run then skips the SOL check
        broker.live_state()["wallet_sol"] = None


def _is_sol_spot(twin: dict) -> bool:
    from .perps import is_perp

    return "mint" in twin and "token_raw" in twin and not is_perp(twin)  # SOL twins and USD-spot (USDC) twins share the wallet


PERP_TOL = 1e-9
INFLIGHT_TTL_S = 3600


def reconcile_perps(broker, now: float) -> dict:
    """Hyperliquid's real positions and open orders against the book, before any perp order."""
    from .broker import perp_twins_held

    report: dict = {"at": now, "inflight": [], "mismatch": [], "orphans": []}
    if broker.perp_route is None:
        return {**report, "skipped": "no perp route"}
    ex = broker.perp_exec()
    if not callable(getattr(ex, "account", None)):
        return {**report, "skipped": "executor cannot read the account"}
    st = broker.live_state()
    inflight = st.setdefault("perp_inflight", {})
    pending = Pending(broker.root)
    for oid, r in pending.load().items():
        if r.get("venue") != "hyperliquid" or oid in inflight:
            continue
        f = ex.find(oid)
        if f is not None and f.ok:  # it filled before the run died: count it until the retry adopts it
            inflight[oid] = {"coin": f.coin, "signed_sz": f.side * f.sz, "leg": r["leg"], "strategy": r["strategy"],
                             "position": r["position"], "px": f.px, "at": now}
            report["inflight"].append(oid)
    for oid, r in list(inflight.items()):
        if now - r["at"] > INFLIGHT_TTL_S:
            o = {"venue": "hyperliquid", "route": broker.perp_route, "coin": r["coin"], "side": 1 if r["signed_sz"] > 0 else -1,
                 "sz": abs(r["signed_sz"]), "strategy": r["strategy"], "cloid": oid, "at": now,
                 "error": f"{r['leg']} {oid} filled in a run that died and was never re-adopted"}
            st["orphans"].append(o)
            del inflight[oid]
            report["orphans"].append(o)
    want: dict[str, float] = {}
    for t in perp_twins_held(broker.ledger, st, broker.perp_route):
        want[t["coin"]] = want.get(t["coin"], 0.0) + t["side"] * t["sz"]
    for r in inflight.values():
        want[r["coin"]] = want.get(r["coin"], 0.0) + r["signed_sz"]
    acct = ex.account()
    have = acct["positions"]
    for coin in sorted(set(want) | set(have)):
        a, b = float(have.get(coin, 0.0)), float(want.get(coin, 0.0))
        if abs(a - b) > PERP_TOL * max(1.0, abs(b)):
            report["mismatch"].append({"coin": coin, "account": a, "book": b})
    if acct.get("open_orders"):
        report["mismatch"].append({"open_orders": len(acct["open_orders"])})
    pending.clear(perps=True)
    reason = None
    if report["mismatch"]:
        reason = "perp reconcile: account differs from the book: " + "; ".join(
            f"{m['coin']} account {m['account']:g} vs book {m['book']:g}" if "coin" in m else f"{m['open_orders']} open orders"
            for m in report["mismatch"])
    elif report["orphans"]:
        reason = "perp reconcile: " + report["orphans"][0]["error"]
    if reason and not st.get("perps_halted"):
        st["perps_halted"] = reason[:400]
        broker.ledger.change({"t": now, "kind": "halt", "scope": "live:perps", "reason": reason[:400]})
    if report["inflight"] or report["mismatch"] or report["orphans"]:
        broker.ledger.journal({"event": "perp_reconcile", **report})
    return report
