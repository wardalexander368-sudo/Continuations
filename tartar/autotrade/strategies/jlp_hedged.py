"""The registered hedged-JLP paper test (handoff/experiments/jlp_paper.py) as a basket in the agent: hold JLP and
short its SOL, ETH and BTC exposure on Hyperliquid perps, so the book earns JLP's fee yield net of funding.

The paper-tests Action writes a check-in every 4 h to ``handoff/data/jlp-paper/snapshots.jsonl`` with JLP's
price, its token deltas per JLP and Hyperliquid marks. This strategy books each check-in:

* no basket open: buy ``size_usd`` of JLP (venue ``jupiter_usd``, cost the quoted sell-side spread in bps) and
  short ``size_usd * d_c`` of each coin c, where ``d_c = delta_c * mark_c / jlp_price`` is the USD exposure per
  JLP dollar (venue ``hyperliquid``, cost the taker fee);
* basket open: when any short is off its target by more than 5% of the JLP leg's value (``DRIFT``, as
  registered), close the shorts and reopen them at target. Paper pays the taker fee only on the size that
  changed, as the registered test does; funding over each hold is carried from Hyperliquid's history;
* at the end of the window (2027-01-08) everything closes.

Every leg carries ``meta.basket = "jlp"`` and ``meta.twin_usd``, so in mode ``dry_live`` the broker mirrors the
whole basket in proportion (``live.perps.basket_budget_usd``): the JLP leg on Jupiter USDC quotes
(usd_spot.py) and the shorts on Hyperliquid's book (perps.py). Nothing is signed or sent. The registered
test's margin top-ups are not modelled here; ``jlp_paper.py evaluate --final`` stays the authority.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..core import Context, CostModel, Intent, Trade, Verdict

START = datetime(2026, 10, 10, tzinfo=timezone.utc).timestamp()
END = datetime(2027, 1, 8, tzinfo=timezone.utc).timestamp()
COINS = ("SOL", "ETH", "BTC")
DRIFT, TAKER = 0.05, 4.5e-4
JLP_MINT = "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4"
BASKET = "jlp"


def ts(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def exposure(s: dict) -> dict[str, float]:
    """USD of each coin per USD of JLP."""
    return {c: s["jlp"]["delta"][c] * s["hl"][c]["mark"] / s["jlp"]["price"] for c in COINS}


class JLPHedged:
    def __init__(self, name: str, cfg: dict):
        self.name, self.cfg = name, cfg
        self.prereg = cfg.get("prereg", "handoff/experiments/jlp_paper.py")
        self.size_usd = float(cfg.get("size_usd", 200.0))
        self.twin_usd = float(cfg.get("twin_basket_usd", 200.0))
        self.path = Path(cfg.get("snapshots", "handoff/data/jlp-paper/snapshots.jsonl"))
        self.info = cfg.get("_info")  # tests inject a fake Hyperliquid client

    def _info(self):
        if self.info is None:
            from ..perps import HyperliquidInfo

            self.info = HyperliquidInfo()
        return self.info

    def snapshots(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = [json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]
        return sorted((r for r in rows if START <= ts(r["t"]) < END and all(c in r.get("hl", {}) for c in COINS)), key=lambda r: r["t"])

    # legs
    def _open_jlp(self, s: dict, at: float) -> Intent:
        fee = max(float(s.get("quote", {}).get("buy_bps", 0.0)), 0.0) / 1e4
        return Intent("open", self.name, at, s["jlp"]["price"], f"hedged JLP basket: JLP leg at {s['jlp']['price']:.4f}",
                      asset="JLP", side=1, notional_usd=self.size_usd, cost=CostModel(fee=fee),
                      meta={"key": f"{BASKET}:JLP", "venue": "jupiter_usd", "mint": JLP_MINT, "basket": BASKET, "twin_usd": self.twin_usd})

    def _open_short(self, s: dict, at: float, c: str, d: float, fee: float, why: str) -> Intent:
        return Intent("open", self.name, at, s["hl"][c]["mark"], f"{why}: short {c} {100 * d:.1f}% of the JLP leg",
                      asset=c, side=-1, notional_usd=round(self.size_usd * d, 2), cost=CostModel(fee=fee),
                      meta={"key": f"{BASKET}:{c}", "venue": "hyperliquid", "coin": c, "basket": BASKET,
                            "twin_usd": round(self.twin_usd * d, 2), "exposure": d})

    def _close(self, s: dict, at: float, p, fee: float, why: str) -> Intent:
        c = p.asset
        if c == "JLP":
            return Intent("close", self.name, at, s["jlp"]["price"], why, cost=CostModel(fee=fee), meta={"key": p.meta["key"]})
        rate = self._info().funding_rate_sum(c, p.entry_at, at)
        return Intent("close", self.name, at, s["hl"][c]["mark"], why, cost=CostModel(fee=fee),
                      meta={"key": p.meta["key"], "carry_usd": -p.side * p.notional_usd * rate, "funding_rate": rate})

    def step(self, ctx: Context) -> list[Intent]:
        held = {p.asset: p for p in ctx.positions if str(p.meta.get("key", "")).startswith(BASKET + ":")}
        snaps = self.snapshots()
        if ctx.now >= END:
            if not held or not snaps:
                return []
            s, at = snaps[-1], ts(snaps[-1]["t"])
            sell = max(float(s.get("quote", {}).get("sell_bps", 0.0)), 0.0) / 1e4
            return [self._close(s, at, p, sell if a == "JLP" else TAKER, "registered window ended (2027-01-08)") for a, p in held.items()]
        last = ctx.state.get("last_t", "")
        new = [s for s in snaps if s["t"] > last]
        if not new:
            return []
        intents: list[Intent] = []
        # the basket as the intents so far leave it: asset -> units and notional
        book = {a: {"units": p.notional_usd / p.entry_price, "notional": p.notional_usd} for a, p in held.items()}
        for s in new:
            at, d = ts(s["t"]), exposure(s)
            if "JLP" not in book:
                intents.append(self._open_jlp(s, at))
                book = {"JLP": {"units": self.size_usd / s["jlp"]["price"], "notional": self.size_usd}}
                for c in COINS:
                    intents.append(self._open_short(s, at, c, d[c], TAKER, "hedged JLP basket"))
                    book[c] = {"units": self.size_usd * d[c] / s["hl"][c]["mark"], "notional": self.size_usd * d[c]}
                continue
            jlp_units = book["JLP"]["units"]
            jlp_value = jlp_units * s["jlp"]["price"]
            target = {c: jlp_units * s["jlp"]["delta"][c] for c in COINS}
            off = {c: abs(book.get(c, {}).get("units", 0.0) - target[c]) * s["hl"][c]["mark"] for c in COINS}
            if max(off.values()) <= DRIFT * jlp_value:
                continue
            why = "rebalance: " + ", ".join(f"{c} off ${off[c]:.2f}" for c in COINS if off[c] > DRIFT * jlp_value)
            for c in COINS:
                cur = book.get(c)
                if cur:
                    # paper pays the taker fee on the size that changed, charged on this close
                    fee = TAKER * off[c] / cur["notional"]
                    p = held.get(c)
                    if p is not None:
                        intents.append(self._close(s, at, p, fee, why))
                    else:  # opened earlier in this same step
                        intents.append(Intent("close", self.name, at, s["hl"][c]["mark"], why, cost=CostModel(fee=fee),
                                              meta={"key": f"{BASKET}:{c}"}))
                dc = target[c] * s["hl"][c]["mark"] / self.size_usd
                intents.append(self._open_short(s, at, c, dc, 0.0, "rebalance"))
                book[c] = {"units": target[c], "notional": self.size_usd * dc}
            held = {a: p for a, p in held.items() if a == "JLP"}
        ctx.state["last_t"] = new[-1]["t"]
        return intents

    def marks(self, ctx: Context) -> dict[str, tuple[float, float]]:
        if not ctx.positions:
            return {}
        out = {}
        snaps = self.snapshots()
        if snaps:
            out.update({p.id: (snaps[-1]["jlp"]["price"], ts(snaps[-1]["t"])) for p in ctx.positions if p.asset == "JLP"})
        perps = [p for p in ctx.positions if p.asset in COINS]
        if perps:
            mids = self._info().post({"type": "allMids"}) or {}
            out.update({p.id: (float(mids[p.asset]), ctx.now) for p in perps if p.asset in mids})
        return out

    def evaluate(self, trades: list[Trade], now: float, state: dict) -> Verdict:
        n = len(trades)
        pnl = sum(t.pnl_usd for t in trades)
        stats = {"trades": n, "pnl_usd": pnl, "by_leg": {}}
        for t in trades:
            stats["by_leg"][t.asset] = stats["by_leg"].get(t.asset, 0.0) + t.pnl_usd
        summary = f"{n} closed legs, basket P&L ${pnl:+.2f} on ${self.size_usd:.0f} of JLP"
        return Verdict("pending", n, stats, f"{summary}; the registered verdict is `jlp_paper.py evaluate --final` after 2027-01-08")

    def describe(self) -> dict:
        return {"basket": ["JLP long", "SOL/ETH/BTC perp shorts at JLP's deltas"], "drift": DRIFT, "taker_fee": TAKER,
                "window": ["2026-10-10", "2027-01-08"], "size_usd": self.size_usd, "twin_basket_usd": self.twin_usd}
