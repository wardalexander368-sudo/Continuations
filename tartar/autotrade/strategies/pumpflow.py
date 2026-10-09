"""The pre-registered pump.fun revenue-surprise rule on the Hyperliquid PUMP perp
(handoff/preregistration/pumpflow/SPEC.md; recorder and official scorer handoff/experiments/pumpflow_paper.py).

The pumpflow-paper Action writes one snapshot per UTC day the first time DefiLlama publishes it, with the
signal and PUMP's mid at that moment. This strategy books each snapshot: close the previous position at its
mid, open the new one (long if the surprise is positive, short otherwise). Cost 0.10% per side per unit of
turnover (a kept side pays nothing), plus funding from Hyperliquid's history. Window 2026-10-10 ..
2027-04-08. The agent's verdict scores only its own book; ``pumpflow_paper.py evaluate --final`` is the
authority.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..core import Context, CostModel, Intent, Trade, Verdict

START = datetime(2026, 10, 10, tzinfo=timezone.utc).timestamp()
END = datetime(2027, 4, 8, tzinfo=timezone.utc).timestamp()
COIN, COST, MIN_TRADES, BLOCK = "PUMP", 1e-3, 120, 10
KEY = "pumpflow"


def ts(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


class PumpFlow:
    def __init__(self, name: str, cfg: dict):
        self.name, self.cfg = name, cfg
        self.prereg = cfg.get("prereg", "handoff/preregistration/pumpflow/SPEC.md")
        self.size_usd = float(cfg.get("size_usd", 200.0))
        self.path = Path(cfg.get("snapshots", "handoff/data/pumpflow-paper/snapshots.jsonl"))
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
        return sorted((r for r in rows if START <= ts(r["t"]) < END), key=lambda r: r["t"])

    def step(self, ctx: Context) -> list[Intent]:
        last = ctx.state.get("last_t", "")
        new = [s for s in self.snapshots() if s["t"] > last]
        if not new:
            return []
        intents: list[Intent] = []
        held = next((p for p in ctx.positions if p.meta.get("key") == KEY), None)
        side, since, entry = (held.side, held.entry_at, held.notional_usd) if held else (0, None, 0.0)
        for s in new:
            at, p = ts(s["t"]), int(s["position"])
            keep = side == p
            if side:
                rate = self._info().funding_rate_sum(COIN, since, at)
                intents.append(Intent("close", self.name, at, float(s["mid"]), f"next day's signal ({s['day']})" + (" (kept)" if keep else ""),
                                      cost=CostModel(fee=0.0 if keep else COST),
                                      meta={"key": KEY, "kept": keep, "carry_usd": -side * entry * rate, "funding_rate": rate}))
            intents.append(Intent("open", self.name, at, float(s["mid"]),
                                  f"revenue surprise {s['signal']:+.3f} for {s['day']}: {'long' if p > 0 else 'short'}",
                                  asset=COIN, side=p, notional_usd=self.size_usd, cost=CostModel(fee=0.0 if keep else COST),
                                  meta={"key": KEY, "venue": "hyperliquid", "coin": COIN, "day": s["day"], "signal": s["signal"]}))
            side, since, entry = p, at, self.size_usd
        ctx.state["last_t"] = new[-1]["t"]
        return intents

    def marks(self, ctx: Context) -> dict[str, tuple[float, float]]:
        if not ctx.positions:
            return {}
        mids = self._info().post({"type": "allMids"}) or {}
        return {p.id: (float(mids[COIN]), ctx.now) for p in ctx.positions if COIN in mids}

    def evaluate(self, trades: list[Trade], now: float, state: dict) -> Verdict:
        n = len(trades)
        if n < 2:
            return Verdict("pending", n, {"trades": n}, f"{n} trade(s); scored after 2027-04-08 (registered)")
        tr = sorted(trades, key=lambda t: t.entry_at)
        net = np.array([t.net_return for t in tr])
        pos = np.array([t.side for t in tr], dtype=float)
        hold = np.array([t.exit_price / t.entry_price - 1 - float(t.meta.get("funding_rate", 0.0)) for t in tr])
        timing = net - pos.mean() * hold
        rng = np.random.default_rng(0)
        k = int(np.ceil(n / BLOCK))
        means = [net[np.concatenate([np.arange(s, s + BLOCK) % n for s in rng.integers(0, n, k)])[:n]].mean() for _ in range(2000)]
        lo, hi = np.percentile(means, [5, 95])
        stats = {"trades": n, "mean": float(net.mean()), "lo": float(lo), "hi": float(hi), "timing": float(timing.mean())}
        summary = (f"{n} trades: mean {100 * net.mean():+.2f}%/trade [{100 * lo:+.2f}, {100 * hi:+.2f}], "
                   f"timing part {100 * timing.mean():+.2f}%")
        if now < END:
            return Verdict("pending", n, stats, f"{summary}; scored after 2027-04-08 (registered)")
        ok = n >= MIN_TRADES and lo > 0 and timing.mean() > 0
        return Verdict("pass" if ok else "fail", n, stats, summary)

    def describe(self) -> dict:
        return {"coin": COIN, "cost_per_side": COST, "window": ["2026-10-10", "2027-04-08"], "size_usd": self.size_usd,
                "rule": "sign(log(rev_d / mean of the 7 days before)) on the PUMP perp, entered at DefiLlama's first publication"}
