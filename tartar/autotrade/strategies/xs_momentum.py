"""The pre-registered weekly cross-sectional momentum rule on Hyperliquid perps
(handoff/preregistration/xs-momentum/SPEC.md; constants as in handoff/experiments/xs_momentum_forward.py).

Each Monday (UTC daily close): universe = perps with 60 consecutive daily closes and 30-day median
USD volume >= $2M; rank by 14-day return; long the top quintile, short the bottom, equal weight,
``leg_usd`` per side. Enter at Tuesday's close, exit at the next Tuesday's close (a delisted coin at
its last close). Costs 20 bps per side per unit of turnover (a coin kept on the same side pays
nothing), plus each leg's hourly funding. Signal Mondays 2026-10-12 .. 2027-10-11.

The agent books it on paper when it runs on or after each Wednesday 00:00 UTC (Tuesday's close is
then final), so a missed run only delays the booking. Scoring follows the registration: mean weekly
long-short return > 0 with the 90% 4-week moving-block bootstrap CI above 0, at 52 weeks; no
earlier verdict (the one interim look is informative only).
"""

from __future__ import annotations

import time
import warnings
from datetime import date, datetime, timedelta, timezone

import numpy as np

from ..core import Context, CostModel, Intent, Trade, Verdict

HL = "https://api.hyperliquid.xyz/info"
START, END = date(2026, 10, 12), date(2027, 10, 11)
LOOKBACK, MIN_HIST, MIN_VOL, QUANT, COST, BLOCK = 14, 60, 2e6, 5, 0.002, 4


def ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def close_ts(d: date) -> float:
    """Unix time of day d's daily close (the next 00:00 UTC)."""
    return ms(d + timedelta(days=1)) / 1000


class XSMomentum:
    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self.prereg = cfg.get("prereg", "handoff/preregistration/xs-momentum/SPEC.md")
        self.leg_usd = float(cfg.get("leg_usd", 100.0))
        self.post = cfg.get("_post") or self._post  # tests inject a fake API
        self._mids: dict[str, float] = {}

    def _post(self, ctx: Context, body: dict):
        import httpx

        http = ctx.http or httpx.Client(timeout=60)
        for i in range(8):
            r = http.post(HL, json=body)
            if r.status_code == 200:
                return r.json()
            time.sleep(3 * (i + 1))
        r.raise_for_status()

    def due_tuesday(self, now: float, last: str | None) -> date | None:
        """The latest Tuesday whose close is final and not yet booked, inside the window."""
        today = datetime.fromtimestamp(now, timezone.utc).date()
        d = today - timedelta(days=(today.weekday() - 1) % 7)  # latest Tuesday <= today
        if close_ts(d) > now:
            d -= timedelta(days=7)
        if d < START + timedelta(days=1) or d > END + timedelta(days=8):
            return None
        if last and d <= date.fromisoformat(last):
            return None
        return d

    def closes(self, ctx: Context, coins: list[str], d0: date, d1: date):
        days = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
        ix = {d: i for i, d in enumerate(days)}
        C = np.full((len(days), len(coins)), np.nan)
        V = np.full_like(C, np.nan)
        for j, coin in enumerate(coins):
            for x in self.post(ctx, {"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d", "startTime": ms(d0),
                                                                        "endTime": ms(d1 + timedelta(days=1))}}) or []:
                d = datetime.fromtimestamp(x["t"] / 1000, timezone.utc).date()
                if d in ix:
                    C[ix[d], j] = float(x["c"])
                    V[ix[d], j] = float(x["v"]) * float(x["c"])
            if not self.cfg.get("_post"):
                time.sleep(0.2)
        return days, ix, C, V

    def funding(self, ctx: Context, coin: str, t0: float, t1: float) -> float:
        out, s = {}, int(t0 * 1000)
        while s < int(t1 * 1000):
            part = self.post(ctx, {"type": "fundingHistory", "coin": coin, "startTime": s, "endTime": int(t1 * 1000)})
            if not part:
                break
            for x in part:
                out[x["time"] // 3600_000] = float(x["fundingRate"])
            s = part[-1]["time"] + 1
            if len(part) < 500:
                break
        h0, h1 = int(t0 * 1000) // 3600_000, int(t1 * 1000) // 3600_000
        return sum(out.get(h, 0.0) for h in range(h0, h1))

    def step(self, ctx: Context) -> list[Intent]:
        d = self.due_tuesday(ctx.now, ctx.state.get("last_tuesday"))
        if d is None:
            return []
        coins = [u["name"] for u in self.post(ctx, {"type": "meta"})["universe"]]
        held = {p.asset for p in ctx.positions}
        coins += sorted(held - set(coins))  # delisted coins we hold still need their last close
        days, ix, C, V = self.closes(ctx, coins, d - timedelta(days=MIN_HIST + 10), d)
        col = {c: j for j, c in enumerate(coins)}
        intents: list[Intent] = []
        # 1) close last week's legs at this Tuesday's close (or the coin's last close), with funding
        m = d - timedelta(days=1)
        new_w: dict[str, float] = {}
        if m <= END:
            i = ix[m]
            hist = ~np.isnan(C[i - MIN_HIST + 1: i + 1]).any(axis=0)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                medv = np.nanmedian(V[i - 29: i + 1], axis=0)
            ok = hist & (medv >= MIN_VOL) & ~np.isnan(C[i - LOOKBACK]) & ~np.isnan(C[ix[d]])
            ids = np.where(ok)[0]
            if len(ids) >= 15:
                order = ids[np.argsort(C[i, ids] / C[i - LOOKBACK, ids] - 1)]
                q = len(order) // QUANT
                new_w = {**{coins[j]: 1.0 for j in order[-q:]}, **{coins[j]: -1.0 for j in order[:q]}}
                ctx.state["last_q"] = q
        week = m.isoformat()
        for pos in ctx.positions:
            path = C[:, col[pos.asset]]
            valid = np.where(~np.isnan(path[: ix[d] + 1]))[0]
            px = float(path[valid[-1]]) if len(valid) else pos.entry_price
            keep = new_w.get(pos.asset) == pos.side
            fund = self.funding(ctx, pos.asset, pos.entry_at, close_ts(d))
            carry = -pos.side * fund * pos.notional_usd  # longs pay positive funding, shorts receive it
            intents.append(Intent("close", self.name, close_ts(d), px, "weekly rebalance" + (" (kept)" if keep else ""),
                                  position_id=pos.id, cost=CostModel(fee=0.0 if keep else COST),
                                  meta={"carry_usd": carry, "funding": fund, "kept": keep}))
        # 2) open this week's legs at Tuesday's close
        q = ctx.state.get("last_q") or 1
        for coin, side in new_w.items():
            kept = any(p.asset == coin and p.side == side for p in ctx.positions)
            intents.append(Intent("open", self.name, close_ts(d), float(C[ix[d], col[coin]]),
                                  f"14-day return rank, {'top' if side > 0 else 'bottom'} quintile (signal {week})",
                                  asset=coin, side=int(side), notional_usd=self.leg_usd / q,
                                  cost=CostModel(fee=0.0 if kept else COST),
                                  meta={"week": week, "leg_usd": self.leg_usd, "label": coin, "venue": "hyperliquid"}))
        ctx.state["last_tuesday"] = d.isoformat()
        return intents

    def marks(self, ctx: Context) -> dict[str, tuple[float, float]]:
        if not ctx.positions:
            return {}
        mids = self.post(ctx, {"type": "allMids"}) or {}
        return {p.id: (float(mids[p.asset]), ctx.now) for p in ctx.positions if p.asset in mids}

    def evaluate(self, trades: list[Trade], now: float, state: dict) -> Verdict:
        weeks: dict[str, float] = {}
        for t in trades:
            w = t.meta.get("week")
            if w:
                weeks[w] = weeks.get(w, 0.0) + t.pnl_usd / float(t.meta.get("leg_usd", self.leg_usd))
        n = len(weeks)
        if n < 2:
            return Verdict("pending", n, {"weeks": n}, f"{n} complete week(s); scored at 52 weeks (registered)")
        x = np.array([weeks[k] for k in sorted(weeks)])
        rng = np.random.default_rng(1)
        means = [x[np.concatenate([np.arange(s, s + BLOCK) % n for s in rng.integers(0, n, n // BLOCK + 1)])[:n]].mean()
                 for _ in range(2000)]
        lo, hi = np.percentile(means, [5, 95])
        stats = {"weeks": n, "mean_weekly": float(x.mean()), "lo": float(lo), "hi": float(hi),
                 "cumulative": float(np.prod(1 + x) - 1)}
        summary = f"{n} weeks: mean {100 * x.mean():+.2f}%/week [{100 * lo:+.2f}, {100 * hi:+.2f}], cumulative {100 * stats['cumulative']:+.1f}%"
        if n < 52:
            return Verdict("pending", n, stats, f"{summary}; scored at 52 weeks (registered)")
        return Verdict("pass" if x.mean() > 0 and lo > 0 else "fail", n, stats, summary)
