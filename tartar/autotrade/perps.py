"""Live twins on Hyperliquid perps: the route for strategies whose intents carry ``meta["venue"] == "hyperliquid"``
(xs_momentum, pumpflow, and the shorts of the hedged-JLP basket).

The SOL twins in ``execution.py`` swap a Solana token; a perp twin opens a long or short on Hyperliquid at a
USD notional instead. Same design: the paper book is unchanged, a promoted strategy's entries get a twin, the
twin exits with the paper exit, every leg goes to ``fills.jsonl`` beside its paper twin, and the live limits
and kill switches apply (here in USD, config ``live.perps``, defaults ``PERP_DEFAULTS``).

Routes:
* ``dry`` (mode ``dry_live``): the "fill" is the order walked through Hyperliquid's live L2 book at that
  moment (taker), with the taker fee; funding over the hold comes from Hyperliquid's funding history.
  Nothing is signed or sent; no account or key.
* ``live`` (mode ``live``, past the gate in ``gate.py``): IOC taker orders signed with an API ("agent")
  wallet the trading account approved, key in ``HYPERLIQUID_AGENT_KEY``, the account's address in
  ``HYPERLIQUID_ACCOUNT`` (USDC deposited there); see ``hl_exchange.py``. Without the approval or
  either key ``select_perp_route`` returns None and perp strategies stay on paper.

Restarts (``safety.py``): every order carries a client order id (``cloid``) derived from what it is for
(the entry, or the position it closes), so a retry after a crash asks the venue for that id first and
adopts its fill instead of trading twice; each run checks the account's positions and open orders
against the book before trading. The dry route keeps a simulated account in ``dry_perp_account.json``.

Kept legs: a weekly rebalance that keeps a leg closes and reopens it on paper at no cost. The twin does
the same without trading: it is marked at the book's mid, handed over, and picked up by the reopen.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

HL_INFO = "https://api.hyperliquid.xyz/info"
MIN_ORDER_USD = 10.0

PERP_DEFAULTS = {
    "max_leg_usd": 12.0,          # notional of one twin (Hyperliquid's minimum order is $10)
    "min_leg_usd": 10.0,
    "budget_usd": 60.0,           # notional in open perp twins, all strategies together (basket legs excluded)
    "basket_budget_usd": 500.0,   # notional in open basket twins (hedged JLP: JLP leg + shorts), each leg sized by meta.twin_usd
    "daily_loss_cap_usd": 6.0,    # realized perp-twin loss in a UTC day; beyond it all live entries stop
    "max_trade_loss_pct": 0.25,   # one twin losing more halts that strategy's live entries
    "max_divergence_pct": 0.03,   # twin worse than paper by more than this ...
    "divergence_streak": 3,       # ... this many closes in a row halts that strategy's live entries
    "max_signal_age_s": 172800,   # perp rules are daily/weekly: a reference price up to 2 days old is mirrored
    "taker_fee": 0.00045,         # Hyperliquid base tier taker
    "dry_all": True,              # in dry_live, mirror every (non-shadow) perp strategy, promoted or not
    "network": "mainnet",         # live orders: "mainnet", or "testnet" (CI test only)
    "slippage": 0.01,             # live IOC limit this far through the mid
}


def cloid(text: str) -> str:
    """A Hyperliquid client order id (16 bytes, hex) that is the same every time for the same ``text``."""
    import hashlib

    return "0x" + hashlib.sha256(text.encode()).hexdigest()[:32]


def is_perp(meta: dict) -> bool:
    return meta.get("venue") == "hyperliquid"


PERP_KEYS = ("HYPERLIQUID_AGENT_KEY", "HYPERLIQUID_ACCOUNT")


def select_perp_route(mode: str, env=None, config: dict | None = None) -> str | None:
    """"dry" in mode dry_live; "live" in mode live when the gate's approval and both keys are present; else None."""
    if mode == "dry_live":
        return "dry"
    if mode == "live" and config is not None:
        from .gate import approval_reason, missing_keys

        if approval_reason(config, env) is None and not missing_keys(PERP_KEYS, env):
            return "live"
    return None


@dataclass
class PerpFill:
    """One leg: ``side`` +1 bought, -1 sold; ``px`` the average fill price; ``fee_usd`` the venue fee."""

    route: str
    leg: str  # "open" | "close" | "roll"
    coin: str
    side: int
    ok: bool
    px: float = 0.0
    sz: float = 0.0
    notional_usd: float = 0.0
    fee_usd: float = 0.0
    mid: float = 0.0
    at: float = 0.0
    dry: bool = False
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def walk(levels: list[dict], sz: float | None = None, usd: float | None = None) -> tuple[float, float]:
    """Average price and size for taking ``sz`` units or ``usd`` notional from one side of the book."""
    got_sz = got_usd = 0.0
    for lv in levels:
        px, avail = float(lv["px"]), float(lv["sz"])
        need = (sz - got_sz) if sz is not None else (usd - got_usd) / px
        take = min(avail, need)
        got_sz += take
        got_usd += take * px
        if take >= need - 1e-12:
            return got_usd / got_sz, got_sz
    raise ValueError("order larger than the visible book")


class HyperliquidInfo:
    """Hyperliquid's public info API (no key)."""

    def __init__(self, http=None, sleep=time.sleep, url: str = HL_INFO):
        import httpx

        self.http = http or httpx.Client(timeout=30)
        self.url = url
        self.sleep = sleep
        self._decimals: dict[str, int] | None = None

    def post(self, body: dict):
        for wait in (1, 2, 4, 0):
            r = self.http.post(self.url, json=body)
            if r.status_code == 200:
                return r.json()
            if not wait:
                break
            self.sleep(wait)
        r.raise_for_status()

    def asset_index(self, coin: str) -> int:
        if getattr(self, "_assets", None) is None:
            self._assets = {u["name"]: i for i, u in enumerate(self.post({"type": "meta"})["universe"])}
        return self._assets[coin]

    def sz_decimals(self, coin: str) -> int:
        if self._decimals is None:
            self._decimals = {u["name"]: int(u["szDecimals"]) for u in self.post({"type": "meta"})["universe"]}
        return self._decimals[coin]

    def book(self, coin: str) -> tuple[list[dict], list[dict]]:
        bids, asks = self.post({"type": "l2Book", "coin": coin})["levels"]
        return bids, asks

    def funding_rate_sum(self, coin: str, t0: float, t1: float) -> float:
        """Sum of hourly funding rates paid in (t0, t1] (positive: longs pay)."""
        out, s, end = 0.0, int(t0 * 1000) + 1, int(t1 * 1000)
        while s <= end:
            part = self.post({"type": "fundingHistory", "coin": coin, "startTime": s, "endTime": end}) or []
            out += sum(float(x["fundingRate"]) for x in part)
            if len(part) < 500:
                break
            s = part[-1]["time"] + 1
        return out


class DryPerpExecutor:
    """Prices each leg on the live book as a taker order; sends nothing."""

    name = "dry"

    def __init__(self, info: HyperliquidInfo | None = None, taker_fee: float = PERP_DEFAULTS["taker_fee"], clock=time.time,
                 slippage: float = PERP_DEFAULTS["slippage"]):
        self.info = info or HyperliquidInfo()
        self.taker_fee, self.clock, self.slippage = taker_fee, clock, slippage
        self.path = None

    # the simulated account (written through on every fill, like the venue would be)
    def attach(self, path, seed: dict[str, float] | None = None) -> None:
        from pathlib import Path

        self.path = Path(path)
        if not self.path.exists():
            self._save({"positions": {c: v for c, v in (seed or {}).items() if abs(v) > 1e-12}, "orders": {}})

    def _load(self) -> dict:
        import json

        if self.path and self.path.exists():
            return json.loads(self.path.read_text())
        return {"positions": {}, "orders": {}}

    def _save(self, acct: dict) -> None:
        import json

        if self.path:
            acct["note"] = "simulated Hyperliquid account of the dry perp route (no real funds)"
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(acct, indent=1, sort_keys=True))
            tmp.replace(self.path)

    def _book(self, f: PerpFill, cloid_: str | None) -> PerpFill:
        if cloid_ and isinstance(f.extra, dict) and "order" in f.extra:
            f.extra["order"]["c"] = cloid_  # the client order id goes last, as the live sender writes it
        if f.ok and self.path:
            acct = self._load()
            pos = round(acct["positions"].get(f.coin, 0.0) + f.side * f.sz, 10)
            if abs(pos) > 1e-12:
                acct["positions"][f.coin] = pos
            else:
                acct["positions"].pop(f.coin, None)
            if cloid_:
                acct["orders"][cloid_] = f.to_dict()
            self._save(acct)
        return f

    def account(self) -> dict:
        """{"positions": {coin: signed size}, "open_orders": [...]}."""
        return {"positions": dict(self._load()["positions"]), "open_orders": []}

    def find(self, cloid_: str) -> PerpFill | None:
        """The fill of an earlier order with this client order id, if there was one."""
        row = self._load()["orders"].get(cloid_)
        return PerpFill(**row) if row else None

    def _take(self, leg: str, coin: str, side: int, sz: float | None = None, usd: float | None = None) -> PerpFill:
        try:
            bids, asks = self.info.book(coin)
            mid = (float(bids[0]["px"]) + float(asks[0]["px"])) / 2
            if usd is not None:  # round the size down to the venue's step, as a real order would be
                d = self.info.sz_decimals(coin)
                sz = round(math.floor(usd / mid * 10 ** d) / 10 ** d, d)
                if sz <= 0:
                    return PerpFill("dry", leg, coin, side, False, mid=mid, at=self.clock(), dry=True, error="size rounds to 0")
            px, got = walk(asks if side > 0 else bids, sz=sz)
            notional = px * got
            if leg == "open" and notional < MIN_ORDER_USD:
                return PerpFill("dry", leg, coin, side, False, mid=mid, at=self.clock(), dry=True,
                                error=f"${notional:.2f} after rounding is under Hyperliquid's ${MIN_ORDER_USD:.0f} minimum")
            return PerpFill("dry", leg, coin, side, True, px=px, sz=got, notional_usd=notional, fee_usd=notional * self.taker_fee,
                            mid=mid, at=self.clock(), dry=True,
                            extra={"slippage_bps": 1e4 * side * (px / mid - 1), "spread_bps": 1e4 * (float(asks[0]["px"]) / float(bids[0]["px"]) - 1),
                                   **self.order_preview(leg, coin, side, got, mid, asks if side > 0 else bids)})
        except Exception as exc:  # noqa: BLE001 - a failed quote is a failed leg, logged by the broker
            return PerpFill("dry", leg, coin, side, False, at=self.clock(), dry=True, error=f"{type(exc).__name__}: {exc}"[:200])

    def order_preview(self, leg: str, coin: str, side: int, sz: float, mid: float, levels: list[dict]) -> dict:
        """The exact order the live sender (hl_exchange.LivePerpExecutor) would sign for this leg, unsigned and
        unsent: IOC limit ``slippage`` through the mid, reduce-only on closes, and whether the visible book
        fills it inside that limit (a live IOC would fill only that part)."""
        try:
            from .hl_exchange import float_to_wire, round_px

            d = self.info.sz_decimals(coin)
            limit = round_px(mid * (1 + side * self.slippage), d)
            inside = sum(float(lv["sz"]) for lv in levels if (float(lv["px"]) <= limit if side > 0 else float(lv["px"]) >= limit))
            order = {"a": self.info.asset_index(coin), "b": side > 0, "p": float_to_wire(limit), "s": float_to_wire(round(sz, d)),
                     "r": leg == "close", "t": {"limit": {"tif": "Ioc"}}}
            return {"order": order, "limit_px": limit, "ioc_fill_frac": min(1.0, inside / sz) if sz else 0.0}
        except Exception as exc:  # noqa: BLE001 - the preview never blocks the dry fill
            return {"order_error": f"{type(exc).__name__}: {exc}"[:200]}

    def open(self, coin: str, side: int, usd: float, cloid: str | None = None) -> PerpFill:
        return self._book(self._take("open", coin, side, usd=usd), cloid)

    def close(self, coin: str, side: int, sz: float, cloid: str | None = None) -> PerpFill:
        """Close a position of ``side`` (so trade the other way)."""
        return self._book(self._take("close", coin, -side, sz=sz), cloid)

    def mid(self, coin: str) -> float:
        bids, asks = self.info.book(coin)
        return (float(bids[0]["px"]) + float(asks[0]["px"])) / 2

    def funding_usd(self, coin: str, side: int, notional_usd: float, t0: float, t1: float) -> float:
        """Funding received (+) or paid (-) by the position over (t0, t1]."""
        return -side * notional_usd * self.info.funding_rate_sum(coin, t0, t1)


def make_perp_executor(route: str, cfg: dict, env=None, config: dict | None = None, root=None):
    if route == "dry":
        return DryPerpExecutor(taker_fee=cfg.get("taker_fee", PERP_DEFAULTS["taker_fee"]),
                               slippage=cfg.get("slippage", PERP_DEFAULTS["slippage"]))
    if route == "live":
        from .hl_exchange import make_live_perp_executor

        return make_live_perp_executor(config or {}, cfg, os.environ if env is None else env, root)
    raise ValueError(f"unknown perp route {route!r}")


def perp_keys(env=None) -> dict:
    env = os.environ if env is None else env
    return {k: bool(env.get(k)) for k in PERP_KEYS}
