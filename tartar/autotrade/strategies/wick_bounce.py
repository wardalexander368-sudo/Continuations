"""The pre-registered wick-bounce rule on Hyperliquid perps (handoff/preregistration/wick-bounce/SPEC.md;
signal reproduced from handoff/experiments/edge-hunt/perps/wick_forward.py, whose constants are fixed).

For each of 20 liquid coins: sigma = population std of the previous 168 hourly close-to-close returns.
When an hour's lower wick (min(open, close) - low) / open is at least 6 sigma, go long at that hour's
close; an upper wick of 6 sigma, go short (both: no trade). Hold 4 hours, exit at that hour's close.
One position per coin at a time. 8.5 bps per side, funding ignored. Entries 2026-10-12 .. 2027-10-11.

The agent reads Hyperliquid's hourly candles once per closed hour and books every signal since its last
look, so a missed run only delays the booking (entries and exits carry the candle times). Scoring follows
the registration: mean return per trade > 0 with the 90% bootstrap CI over entry days above 0, after
the window ends; no earlier verdict.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, datetime, timezone

import numpy as np

from ..core import Context, CostModel, Intent, Trade, Verdict

HL = "https://api.hyperliquid.xyz/info"
COINS = ["ADA", "APT", "ARB", "AVAX", "BCH", "BNB", "BTC", "DOGE", "DOT", "ETH", "INJ", "LINK", "LTC",
         "NEAR", "OP", "SEI", "SOL", "SUI", "TIA", "XRP"]
Z, HOLD, WIN, COST = 6.0, 4, 168, 0.00085
START, END = "2026-10-12", "2027-10-11"


def day(h: int) -> str:
    return datetime.fromtimestamp(h * 3600, timezone.utc).date().isoformat()


class WickBounce:
    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self.prereg = cfg.get("prereg", "handoff/preregistration/wick-bounce/SPEC.md")
        self.size = float(cfg.get("size_usd", 200.0))
        self.coins = cfg.get("coins") or COINS
        self.start, self.end = cfg.get("start", START), cfg.get("end", END)
        self.post = cfg.get("_post") or self._post  # tests inject a fake API

    def _post(self, ctx: Context, body: dict):
        import httpx

        http = ctx.http or httpx.Client(timeout=60)
        for i in range(6):
            r = http.post(HL, json=body)
            if r.status_code == 200:
                return r.json()
            time.sleep(3 * (i + 1))
        r.raise_for_status()

    def candles(self, ctx: Context, coin: str, h0: int, h1: int):
        """O, H, L, C arrays for hours h0 .. h1 - 1 (closed hours only)."""
        n = h1 - h0
        O, Hi, Lo, C = (np.full(n, np.nan) for _ in range(4))
        for x in self.post(ctx, {"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h",
                                                                  "startTime": h0 * 3600_000, "endTime": h1 * 3600_000}}) or []:
            h = int(x["t"]) // 3600_000
            if h0 <= h < h1:
                O[h - h0], Hi[h - h0], Lo[h - h0], C[h - h0] = (float(x[k]) for k in ("o", "h", "l", "c"))
        if not self.cfg.get("_post"):
            time.sleep(0.2)
        return O, Hi, Lo, C

    def step(self, ctx: Context) -> list[Intent]:
        now_h = int(ctx.now) // 3600  # hours < now_h are closed
        done = int(ctx.state.setdefault("done_hour", now_h - 1))  # last hour already checked for entries
        due = [p for p in ctx.positions if p.meta.get("exit_hour", 0) < now_h]
        if done >= now_h - 1 and not due:
            return []
        if day(now_h - 1) < self.start and not ctx.positions:
            ctx.state["done_hour"] = now_h - 1
            return []
        lo_h = min([done + 1] + [p.meta["entry_hour"] for p in ctx.positions]) - WIN - 2
        intents: list[Intent] = []
        for coin in self.coins:
            mine = [p for p in ctx.positions if p.asset == coin]
            if done >= now_h - 1 and not any(p.meta["exit_hour"] < now_h for p in mine):
                continue
            O, Hi, Lo, C = self.candles(ctx, coin, lo_h, now_h)
            R = np.full(len(C), np.nan)
            R[1:] = C[1:] / C[:-1] - 1
            busy = max([p.meta["exit_hour"] for p in mine], default=-1)
            for p in mine:  # exits of legs opened in earlier runs
                j = p.meta["exit_hour"] - lo_h
                if j < len(C) and not np.isnan(C[j]):
                    intents.append(self.close_intent(coin, p.meta["exit_hour"], float(C[j]), position_id=p.id))
            for h in range(done + 1, now_h):
                i = h - lo_h
                if h < busy or not (self.start <= day(h) <= self.end):
                    continue
                s = self.signal(O, Hi, Lo, C, R, i)
                if not s:
                    continue
                if i + HOLD < len(C) and np.isnan(C[i + HOLD]):
                    continue  # the scorer skips a trade whose exit candle is missing
                key = f"{coin}:{h}"
                intents.append(Intent("open", self.name, (h + 1) * 3600, float(C[i]),
                                      f"{'lower' if s > 0 else 'upper'} hourly wick >= {Z:.0f} sigma, hold {HOLD} h",
                                      asset=coin, side=s, notional_usd=self.size, cost=CostModel(fee=COST),
                                      meta={"key": key, "entry_hour": h, "exit_hour": h + HOLD, "label": coin,
                                            "venue": "hyperliquid", "entry_day": day(h)}))
                busy = h + HOLD
                if i + HOLD < len(C):  # the exit candle is already closed (a late run): book it now
                    intents.append(self.close_intent(coin, h + HOLD, float(C[i + HOLD]), key=key))
        ctx.state["done_hour"] = now_h - 1
        return intents

    def close_intent(self, coin: str, h: int, px: float, position_id: str = "", key: str = "") -> Intent:
        return Intent("close", self.name, (h + 1) * 3600, px, f"held {HOLD} h", position_id=position_id,
                      cost=CostModel(fee=COST), meta={"key": key} if key else {})

    @staticmethod
    def signal(O, Hi, Lo, C, R, i: int) -> int:
        """+1 / -1 / 0 at index i, exactly as wick_forward.score."""
        if i < WIN + 1:
            return 0
        w = R[i - WIN: i]
        if np.isnan(w).any() or np.isnan(O[i]) or np.isnan(C[i]):
            return 0
        sig = np.sqrt(max(np.mean(w * w) - np.mean(w) ** 2, 0))
        if sig == 0:
            return 0
        lw = (min(O[i], C[i]) - Lo[i]) / O[i] / sig
        uw = (Hi[i] - max(O[i], C[i])) / O[i] / sig
        return int(lw >= Z) - int(uw >= Z)

    def marks(self, ctx: Context) -> dict[str, tuple[float, float]]:
        if not ctx.positions:
            return {}
        mids = self.post(ctx, {"type": "allMids"}) or {}
        return {p.id: (float(mids[p.asset]), ctx.now) for p in ctx.positions if p.asset in mids}

    def describe(self) -> dict:
        return {"kind": "wick_bounce", "coins": self.coins, "z": Z, "hold_hours": HOLD, "sigma_window": WIN,
                "cost_per_side": COST, "size_usd": self.size, "window": [self.start, self.end]}

    def evaluate(self, trades: list[Trade], now: float, state: dict) -> Verdict:
        by = defaultdict(list)
        for t in trades:
            by[t.meta.get("entry_day") or day(int(t.entry_at) // 3600)].append(t.net_return)
        n = len(trades)
        if n < 2:
            return Verdict("pending", n, {"n": n}, f"{n} trade(s); scored after {self.end} (registered)")
        keys = list(by)
        s = np.array([sum(by[k]) for k in keys])
        c = np.array([len(by[k]) for k in keys])
        pick = np.random.default_rng(1).integers(0, len(keys), (10000, len(keys)))
        lo, hi = np.percentile(s[pick].sum(axis=1) / c[pick].sum(axis=1), [5, 95])
        m = float(np.mean([t.net_return for t in trades]))
        stats = {"n": n, "days": len(keys), "mean_net": m, "lo": float(lo), "hi": float(hi)}
        summary = f"{n} trades on {len(keys)} days: mean {m * 1e4:+.1f} bp/trade [{lo * 1e4:+.1f}, {hi * 1e4:+.1f}]"
        if datetime.fromtimestamp(now, timezone.utc).date() <= date.fromisoformat(self.end):
            return Verdict("pending", n, stats, f"{summary}; scored after {self.end} (registered)")
        return Verdict("pass" if m > 0 and lo > 0 else "fail", n, stats, summary)
