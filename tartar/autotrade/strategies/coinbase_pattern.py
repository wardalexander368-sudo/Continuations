"""The two pre-registered chart patterns on US spot (handoff/preregistration/us-patterns/SPEC.md; signals and
timing reproduced from handoff/experiments/edge-hunt/patterns/patterns.py, whose constants are fixed).

On Coinbase's 15-minute candles for 11 USD pairs, rolled into clock hours (an hour with a missing 15-minute
close is missing); sigma = population std of the previous 168 hourly returns:

* ``capit`` (CAPIT Z=4 H=24): the 24-hour return at an hourly close <= -4 sigma sqrt(24).
* ``volspike`` (VOLSPIKE K=10 H=72): the hour's volume >= 10x the mean of the previous 168 hours and the hour
  closed up >= 1 sigma.

Long only. Buy at the close of the 15-minute bar ending 30 minutes after the signal hour, sell the same
delay after the hold; one position per coin per rule; 0.62% per side (Coinbase's taker fee below $10k a
month plus spread). Entries for signal days 2026-10-12 .. 2027-10-11. US venue (us_only-safe).

The agent books every signal since its last look, at the candle times and prices, once the entry candle
is closed (with hourly runs at ~:20 that is the next run), so the cadence never changes the trades. A
missing exit candle closes at the next 15-minute close instead (the scorer would drop that trade; rare).
Scoring follows the registration: mean return per trade > 0 with the 90% bootstrap CI over entry days
above 0, after the window ends. The official scorer (pattern_forward.py) stays the authority.
"""

from __future__ import annotations

import time
import warnings
from collections import defaultdict
from datetime import date, datetime, timezone

import numpy as np

from ..core import Context, CostModel, Intent, Trade, Verdict

CB = "https://api.exchange.coinbase.com"
COINS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC", "BCH", "DOT"]
COST, DELAY, WIN, G = 0.0062, 2, 168, 900
RULES = {"capit": {"z": 4.0, "hold": 24}, "volspike": {"k": 10.0, "hold": 72}}
START, END = "2026-10-12", "2027-10-11"
_CACHE: dict[tuple[str, int, int], list] = {}  # one fetch per coin and range per process, shared by both rules


def day(h: int) -> str:
    return datetime.fromtimestamp(h * 3600, timezone.utc).date().isoformat()


def hourly(t0: int, rows: list, n_hours: int):
    """15-minute rows [t, o, h, l, c, v] from hour index t0 -> hourly O, H, L, C, V and the 15m closes,
    exactly as patterns.py (an hour with any missing 15m close is missing)."""
    a = np.full((n_hours * 4, 5), np.nan)
    for r in rows:
        k = (int(r[0]) - t0 * 3600) // G
        if 0 <= k < len(a):
            a[k] = r[1:6]
    b = a.reshape(n_hours, 4, 5)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        O, Hh, L, C, V = b[:, 0, 0], np.nanmax(b[:, :, 1], 1), np.nanmin(b[:, :, 2], 1), b[:, 3, 3].copy(), np.nansum(b[:, :, 4], 1)
    bad = np.isnan(b[:, :, 3]).any(1)
    O[bad] = Hh[bad] = L[bad] = C[bad] = np.nan
    return O, Hh, L, C, V, a[:, 3]


def signals(rule: str, C: np.ndarray, V: np.ndarray) -> np.ndarray:
    """Boolean signal per hour index, as patterns.capit(4) / patterns.volspike(10) (needs 169+ hours of history)."""
    n = len(C)
    R = np.full(n, np.nan)
    R[1:] = C[1:] / C[:-1] - 1
    S = np.full(n, np.nan)
    for i in range(169, n):
        w = R[i - WIN: i]
        if not np.isnan(w).any():
            S[i] = w.std()
    with np.errstate(all="ignore"):
        if rule == "capit":
            r24 = np.full(n, np.nan)
            r24[24:] = C[24:] / C[:-24] - 1
            return r24 <= -RULES["capit"]["z"] * S * np.sqrt(24)
        Vz = np.nan_to_num(V)
        cs = np.concatenate([[0], np.cumsum(Vz)])
        m = np.full(n, np.nan)
        i = np.arange(WIN, n)
        m[i] = (cs[i] - cs[i - WIN]) / WIN
        return (V >= RULES["volspike"]["k"] * m) & (R >= S)


class CoinbasePattern:
    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self.rule = cfg.get("rule", "capit")
        self.hold = RULES[self.rule]["hold"]
        self.prereg = cfg.get("prereg", "handoff/preregistration/us-patterns/SPEC.md")
        self.size = float(cfg.get("size_usd", 200.0))
        # the paper book pays the registered cost; venue_costs are what the same trades net at real venues
        self.cost = float(cfg.get("cost_per_side", COST))
        self.venue_costs = dict(cfg.get("venue_costs") or {})
        self.coins = cfg.get("coins") or COINS
        self.start, self.end = cfg.get("start", START), cfg.get("end", END)
        self.get = cfg.get("_get") or self._get  # tests inject a fake API
        self._last: dict[str, tuple[float, float]] = {}

    def _get(self, ctx: Context, coin: str, t0: int, t1: int) -> list:
        """15-minute candles [t, o, h, l, c, v] with t0 <= t < t1 (unix seconds), 300 per request."""
        key = (coin, t0, t1)
        if key in _CACHE:
            return _CACHE[key]
        import httpx

        http = ctx.http or httpx.Client(timeout=30)
        out, t = [], t0
        while t < t1:
            e = min(t + 300 * G, t1)
            for i in range(6):
                r = http.get(f"{CB}/products/{coin}-USD/candles", params={
                    "granularity": G, "start": datetime.fromtimestamp(t, timezone.utc).isoformat(),
                    "end": datetime.fromtimestamp(e - G, timezone.utc).isoformat()})
                if r.status_code == 200:
                    out += [[int(ts), op, hi, lo, cl, v] for ts, lo, hi, op, cl, v in r.json() if t <= ts < e]
                    break
                time.sleep(2 * (i + 1))
            else:
                r.raise_for_status()
            t = e
            time.sleep(0.25)
        _CACHE.clear() if len(_CACHE) > 64 else None
        _CACHE[key] = out
        return out

    def step(self, ctx: Context) -> list[Intent]:
        now = int(ctx.now)
        # the last signal hour whose entry candle (closing 30 min after the hour) is final
        h_max = (now - 60 - DELAY * G) // 3600 - 1
        done = int(ctx.state.setdefault("done_hour", h_max))
        due = [p for p in ctx.positions if p.meta["exit_t"] + 60 <= now]
        if done >= h_max and not due:
            return []
        if day(h_max) < self.start and not ctx.positions:
            ctx.state["done_hour"] = h_max
            return []
        lo_h = min([done + 1] + [p.meta["signal_hour"] for p in ctx.positions]) - WIN - 30
        n_hours = now // 3600 + 1 - lo_h
        intents: list[Intent] = []
        for coin in self.coins:
            mine = [p for p in ctx.positions if p.asset == coin]
            if done >= h_max and not any(p in due for p in mine):
                continue
            rows = self.get(ctx, coin, lo_h * 3600, now // G * G)
            O, Hh, L, C, V, C15 = hourly(lo_h, rows, n_hours)
            ok15 = np.where(~np.isnan(C15))[0]
            if len(ok15):
                self._last[coin] = (float(C15[ok15[-1]]), float(lo_h * 3600 + (ok15[-1] + 1) * G))
            for p in mine:
                if p.meta["exit_t"] + 60 <= now:
                    intents.append(self.exit_intent(coin, lo_h, C15, p.meta["exit_t"], now, position_id=p.id))
            sig = signals(self.rule, C, V)
            busy = max([p.meta["signal_hour"] + self.hold + 1 for p in mine], default=-1)
            for h in range(done + 1, h_max + 1):
                i = h - lo_h
                if h < busy or not sig[i] or not (self.start <= day(h) <= self.end):
                    continue
                e = 4 * (i + 1) + DELAY - 1
                if np.isnan(C15[e]):
                    continue  # the scorer skips a trade without its entry candle
                entry_t = float((h + 1) * 3600 + DELAY * G)
                exit_t = entry_t + self.hold * 3600
                key = f"{coin}:{h}"
                intents.append(Intent("open", self.name, entry_t, float(C15[e]),
                                      f"{self.rule} signal at the {day(h)} {h % 24:02d}:00 UTC hour, hold {self.hold} h",
                                      asset=coin, side=1, notional_usd=self.size, cost=CostModel(fee=self.cost),
                                      meta={"key": key, "signal_hour": h, "exit_t": exit_t, "label": f"{coin}-USD",
                                            "venue": "coinbase", "entry_day": day(h), "rule": self.rule}))
                busy = h + self.hold + 1
                if exit_t + 60 <= now:  # a late look: the whole hold is in the data
                    intents.append(self.exit_intent(coin, lo_h, C15, exit_t, now, key=key))
        ctx.state["done_hour"] = h_max
        return intents

    def exit_intent(self, coin, lo_h, C15, exit_t, now, position_id="", key="") -> Intent:
        k = int((exit_t - lo_h * 3600) // G) - 1  # the 15m bar closing at exit_t
        j = k
        while j < len(C15) and (j < 0 or np.isnan(C15[j])):
            j += 1
        if j >= len(C15):  # no close at or after the exit yet: use the latest
            j = int(np.where(~np.isnan(C15))[0][-1])
        at = float(lo_h * 3600 + (j + 1) * G)
        meta = {"key": key} if key else {}
        if j != k:
            meta["exit_gap"] = True
        return Intent("close", self.name, at, float(C15[j]), f"held {self.hold} h", position_id=position_id,
                      cost=CostModel(fee=self.cost), meta=meta)

    def marks(self, ctx: Context) -> dict[str, tuple[float, float]]:
        return {p.id: self._last[p.asset] for p in ctx.positions if p.asset in self._last}

    def describe(self) -> dict:
        return {"kind": "coinbase_pattern", "rule": self.rule, **RULES[self.rule], "coins": self.coins, "cost_per_side": self.cost, "venue_costs": self.venue_costs,
                "entry": f"{DELAY * 15} min after the signal hour's close", "venue": "coinbase (US spot)",
                "size_usd": self.size, "window": [self.start, self.end]}

    def evaluate(self, trades: list[Trade], now: float, state: dict) -> Verdict:
        by = defaultdict(list)
        for t in trades:
            by[t.meta.get("entry_day")].append(t.net_return)
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
        summary = f"{n} trades on {len(keys)} days: mean {m * 100:+.2f}%/trade [{lo * 100:+.2f}, {hi * 100:+.2f}]"
        gross = [t.exit_price / t.entry_price - 1 for t in trades]
        for venue, c in self.venue_costs.items():  # same fills, each venue's cost per side (additive, as the scorer)
            stats[f"mean_net_{venue}"] = v = float(np.mean(gross)) - 2 * float(c)
            summary += f"; {v * 100:+.2f}% at {venue} ({float(c) * 100:.2f}%/side)"
        if datetime.fromtimestamp(now, timezone.utc).date() <= date.fromisoformat(self.end):
            return Verdict("pending", n, stats, f"{summary}; scored after {self.end} (registered)")
        return Verdict("pass" if m > 0 and lo > 0 else "fail", n, stats, summary)
