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

Execution-realistic score (audit 2026-10-10, 1c): an hourly agent can't trade at the wick hour's close.
Every trade is also scored as a twin would get it: entry at the first scheduled run after the wick hour
(``exec_lag_s`` after the hour: cron :05 plus GitHub's observed 13-14 min start delay and a minute to act,
so :20), exit at the first run after the hold, both priced inside Hyperliquid's 5-minute candles, same
costs. A "pass" also needs that score's mean above 0, so the agent can't promote a rule it can't execute.
The registered statistic (wick_forward.py) stays the authority for the pre-registered test itself.
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
EXEC_LAG_S = 20 * 60
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
        self.exec_lag = float(cfg.get("exec_lag_s", EXEC_LAG_S))

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

    def price_at(self, ctx: Context, coin: str, t0: float, t1: float) -> tuple[float | None, float | None]:
        """Prices at t0 and t1 from 5-minute candles, interpolated between each bar's open and close."""
        rows = self.post(ctx, {"type": "candleSnapshot", "req": {"coin": coin, "interval": "5m", "startTime": int(t0 - 300) * 1000,
                                                                "endTime": int(t1 + 300) * 1000}}) or []
        bars = {int(x["t"]) // 1000: (float(x["o"]), float(x["c"])) for x in rows}

        def at(t):
            b = int(t // 300 * 300)
            if b not in bars:
                return None
            o, c = bars[b]
            return o + (c - o) * (t - b) / 300

        return at(t0), at(t1)

    def score_executions(self, ctx: Context) -> None:
        """Execution-realistic returns of trades whose exit moment has passed (state ``exec``)."""
        pend = ctx.state.setdefault("exec_pending", {})
        done = ctx.state.setdefault("exec", {})
        for key, e in list(pend.items()):
            if e["exit_t"] + 300 > ctx.now:
                continue
            p_in, p_out = self.price_at(ctx, e["coin"], e["entry_t"], e["exit_t"])
            if p_in and p_out:
                done[key] = {"day": e["day"], "net": e["side"] * (p_out / p_in - 1) - 2 * COST,
                             "entry_t": e["entry_t"], "exit_t": e["exit_t"]}
            elif ctx.now - e["exit_t"] > 3 * 86400:  # candles never came: give up, logged as missing
                done[key] = {"day": e["day"], "net": None}
            else:
                continue
            del pend[key]

    def step(self, ctx: Context) -> list[Intent]:
        self.score_executions(ctx)
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
                ctx.state.setdefault("exec_pending", {})[key] = {
                    "coin": coin, "side": s, "day": day(h),
                    "entry_t": (h + 1) * 3600 + self.exec_lag, "exit_t": (h + HOLD + 1) * 3600 + self.exec_lag}
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
        ex = [e["net"] for e in (state or {}).get("exec", {}).values() if e.get("net") is not None]
        if ex:
            stats.update(exec_n=len(ex), exec_mean_net=float(np.mean(ex)))
            summary += (f"; as an hourly agent would trade it (entry and exit {self.exec_lag / 60:.0f} min after the hour): "
                        f"{np.mean(ex) * 1e4:+.1f} bp/trade over {len(ex)}")
        if datetime.fromtimestamp(now, timezone.utc).date() <= date.fromisoformat(self.end):
            return Verdict("pending", n, stats, f"{summary}; scored after {self.end} (registered)")
        ok = m > 0 and lo > 0
        if ok and not (ex and np.mean(ex) > 0):
            return Verdict("fail", n, stats, f"{summary}; the registered statistic passes but the agent can't execute it at a profit")
        return Verdict("pass" if ok else "fail", n, stats, summary)
