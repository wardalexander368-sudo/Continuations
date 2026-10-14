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

Random-entry control (live rule item 6, reporting only; the verdict is unchanged): 15 days after each signal's
window closes, the agent prices the trade's control, the mean gross return of buying the same coin at every hour
within +-15 days of the signal with the same entry delay and hold (the "local" control of
handoff/experiments/edge-hunt/patterns/random_entry.py, as an exact mean instead of random draws). The score shows
the trades' excess over their controls with a 90% CI bootstrapped over entry days, so a market-wide drift is not
mistaken for the bounce.
"""

from __future__ import annotations

import time
import warnings
from collections import defaultdict
from datetime import date, datetime, timezone

import numpy as np

from .. import cde_book, observation_coverage as coverage
from ..core import Context, CostModel, Intent, Trade, Verdict

CB = "https://api.exchange.coinbase.com"
COINS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC", "BCH", "DOT"]
COST, DELAY, WIN, G = 0.0062, 2, 168, 900
RULES = {"capit": {"z": 4.0, "hold": 24}, "volspike": {"k": 10.0, "hold": 72}}
START, END = "2026-10-12", "2027-10-11"
CONTROL = 15 * 24  # hours either side of the signal hour: the random-entry control's window
_CACHE: dict[tuple[str, int, int], list] = {}  # one fetch per coin and range per process, shared by both rules


class CandleRows(list):
    """Keep the list interface, with evidence about an empty HTTP result."""

    def __init__(self, rows=(), *, status: int = 200, source: str = "candles"):
        super().__init__(rows)
        self.source = {"http_status": status, "result": source}


def day(h: int) -> str:
    return datetime.fromtimestamp(h * 3600, timezone.utc).date().isoformat()


def hourly(t0: int, rows: list, n_hours: int):
    """15-minute rows [t, o, h, l, c, v] from hour index t0 -> hourly O, H, L, C, V and the 15m closes,
    exactly as patterns.py (an hour with any missing 15m close is missing)."""
    a = np.full((n_hours * 4, 5), np.nan)
    for r in rows:
        k = (int(r[0]) - t0 * 3600) // G
        if int(r[0]) % G == 0 and 0 <= k < len(a):
            a[k] = r[1:6]
    a[~np.isfinite(a[:, 3]) | (a[:, 3] <= 0), 3] = np.nan
    b = a.reshape(n_hours, 4, 5)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        O, Hh, L, C, V = b[:, 0, 0], np.nanmax(b[:, :, 1], 1), np.nanmin(b[:, :, 2], 1), b[:, 3, 3].copy(), np.sum(b[:, :, 4], 1)
    bad = (~np.isfinite(b[:, :, 3]) | (b[:, :, 3] <= 0)).any(1)
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


def control_gross(C15: np.ndarray, lo_h: int, h: int, hold: int, delay: int) -> float | None:
    """Mean gross return of entering at every hour within +-CONTROL of signal hour ``h`` (15m closes from hour
    ``lo_h``), with the strategy's entry delay and hold. None if fewer than half the hours have both candles."""
    rets = []
    for j in range(h - CONTROL, h + CONTROL + 1):
        e = 4 * (j - lo_h + 1) + delay - 1
        x = e + 4 * hold
        if 0 <= e and x < len(C15) and not (np.isnan(C15[e]) or np.isnan(C15[x])):
            rets.append(C15[x] / C15[e] - 1)
    return float(np.mean(rets)) if len(rets) >= CONTROL else None


def day_ci(by: dict) -> tuple[float, float]:
    """90% CI of the pooled mean, resampling entry days (trades on one crash day are one bet)."""
    keys = list(by)
    s = np.array([sum(by[k]) for k in keys])
    c = np.array([len(by[k]) for k in keys])
    pick = np.random.default_rng(1).integers(0, len(keys), (10000, len(keys)))
    lo, hi = np.percentile(s[pick].sum(axis=1) / c[pick].sum(axis=1), [5, 95])
    return float(lo), float(hi)


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
        # 15m bars from the signal hour's close to the entry (2 = registered; 1 = the first hourly run after the signal,
        # which starts :21-:32, so the :15 bar is final: handoff/reviews/timing-2026-10-11.md)
        self.delay = int(cfg.get("delay_bars", DELAY))
        # shadow = research line outside the risk caps, live twins and the Alpaca mirror (as dip variants)
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
                if r.status_code == 404:  # unavailable; this status alone cannot establish delisting
                    return CandleRows(status=404, source="http-unavailable")
                time.sleep(2 * (i + 1))
            else:
                r.raise_for_status()
            t = e
            time.sleep(0.25)
        _CACHE.clear() if len(_CACHE) > 64 else None
        result = CandleRows(out, source="candles" if out else "empty-response")
        # Keep incomplete responses retryable at the same range too; the cache is
        # only an optimization shared by rules, never proof that a gap is final.
        if out and len({row[0] for row in out}) == (t1 - t0) // G:
            _CACHE[key] = result
        return result

    def input_reason(self, C, V, C15, i: int, sig: bool) -> str:
        """The previous 168 returns need 169 preceding closes, plus the signal hour.

        A false comparison with NaN is missing evidence, never an observed no-signal.
        The formula and registered constants themselves stay in ``signals``.
        """
        if i < WIN + 1 or i >= len(C) or not np.isfinite(C[i - WIN - 1:i + 1]).all():
            return "missing-signal-lookback"
        with np.errstate(all="ignore"):
            previous = C[i - WIN:i] / C[i - WIN - 1:i - 1] - 1
            current = C[i] / C[i - 1] - 1
            sigma = previous.std()
        if not np.isfinite(previous).all() or not np.isfinite(current) or not np.isfinite(sigma):
            return "invalid-signal-returns"
        if self.rule == "volspike" and (not np.isfinite(V[i - WIN:i + 1]).all() or (V[i - WIN:i + 1] < 0).any()):
            return "missing-signal-volume"
        e = 4 * (i + 1) + self.delay - 1
        if sig and (e >= len(C15) or not np.isfinite(C15[e]) or C15[e] <= 0):
            return "missing-entry-candle"
        return ""

    def step(self, ctx: Context) -> list[Intent]:
        now = int(ctx.now)
        self.price_controls(ctx, now)
        # the last signal hour whose entry candle (closing 30 min after the hour) is final
        h_max = (now - 60 - self.delay * G) // 3600 - 1
        done = int(ctx.state.setdefault("done_hour", h_max))
        observed = coverage.initialize(ctx.state, done=done, now=now, coins=self.coins,
                                       start=self.start, end=self.end, delay=self.delay, rule=self.rule)
        due = [p for p in ctx.positions if p.meta["exit_t"] + 60 <= now]
        if done >= h_max and not due and not observed["pending"]:
            return []
        if day(h_max) < self.start and not ctx.positions:
            ctx.state["done_hour"] = h_max
            coverage.finish(observed, h_max)
            return []
        lo_h = min([done + 1] + [p.meta["signal_hour"] for p in ctx.positions]) - WIN - 30
        n_hours = now // 3600 + 1 - lo_h
        intents: list[Intent] = []
        for coin in self.coins:
            mine = [p for p in ctx.positions if p.asset == coin]
            pending = coverage.pending_hours(observed, coin, h_max)
            if done >= h_max and not any(p in due for p in mine) and not pending:
                continue
            coin_lo = min([lo_h] + [h - WIN - 1 for h in pending])
            coin_n = n_hours + lo_h - coin_lo
            source, fetch_error = {}, ""
            try:
                rows = self.get(ctx, coin, coin_lo * 3600, now // G * G)
                source = getattr(rows, "source", {"result": "candles" if rows else "empty-result"})
                O, Hh, L, C, V, C15 = hourly(coin_lo, rows, coin_n)
            except Exception as exc:  # noqa: BLE001 - one coin's missing observations must not hide the others
                fetch_error = f"fetch-error:{type(exc).__name__}"
                source = {"result": "fetch-error", "error_type": type(exc).__name__}
                O, Hh, L, C, V, C15 = hourly(coin_lo, [], coin_n)
            ok15 = np.where(np.isfinite(C15) & (C15 > 0))[0]
            if len(ok15):
                self._last[coin] = (float(C15[ok15[-1]]), float(coin_lo * 3600 + (ok15[-1] + 1) * G))
            for p in mine:
                if p.meta["exit_t"] + 60 <= now:
                    x = self.exit_intent(coin, coin_lo, C15, p.meta["exit_t"], now, position_id=p.id)
                    if x:
                        intents.append(x)
            sig = signals(self.rule, C, V)
            for h in pending:
                i = h - coin_lo
                if not fetch_error and not self.input_reason(C, V, C15, i, bool(sig[i])):
                    coverage.recovered(observed, coin, h, now, signal=bool(sig[i]))
            busy = max([p.meta["signal_hour"] + self.hold + 1 for p in mine], default=-1)
            for h in range(done + 1, h_max + 1):
                i = h - coin_lo
                if not (self.start <= day(h) <= self.end):
                    coverage.record(observed, coin, h, "outside-window", now)
                    continue
                if h < busy:
                    coverage.record(observed, coin, h, "busy", now, reason="position-overlap")
                    continue
                reason = fetch_error or ("http-unavailable" if source.get("http_status") == 404 else
                                         "empty-response" if not len(rows) else self.input_reason(C, V, C15, i, bool(sig[i])))
                if reason:
                    coverage.record(observed, coin, h, "incomplete", now, reason=reason, source=source)
                    continue
                if not sig[i]:
                    coverage.record(observed, coin, h, "observed-no-signal", now)
                    continue
                e = 4 * (i + 1) + self.delay - 1
                entry_t = float((h + 1) * 3600 + self.delay * G)
                exit_t = entry_t + self.hold * 3600
                key = f"{coin}:{h}"
                intents.append(Intent("open", self.name, entry_t, float(C15[e]),
                                      f"{self.rule} signal at the {day(h)} {h % 24:02d}:00 UTC hour, hold {self.hold} h",
                                      asset=coin, side=1, notional_usd=self.size, cost=CostModel(fee=self.cost),
                                      meta={"key": key, "signal_hour": h, "exit_t": exit_t, "label": f"{coin}-USD",
                                            "venue": "coinbase", "entry_day": day(h), "rule": self.rule,
                                            "shadow": bool(self.cfg.get("shadow"))}))
                busy = h + self.hold + 1
                coverage.record(observed, coin, h, "signal-intent", now)
                ctx.state.setdefault("control_due", {})[key] = [coin, h]
                if exit_t + 60 <= now:  # a late look: the whole hold is in the data
                    x = self.exit_intent(coin, coin_lo, C15, exit_t, now, key=key)
                    if x:
                        intents.append(x)
        ctx.state["done_hour"] = h_max
        coverage.finish(observed, h_max)
        if self.cfg.get("cde_book"):
            self.snap_cde(ctx, intents, now)
        return intents

    def snap_cde(self, ctx: Context, intents: list[Intent], now: int) -> None:
        """Coinbase US perp top of book at each fresh entry and exit (cde_book.py; reporting only)."""
        coin_of = {p.id: p.asset for p in ctx.positions}
        http = self.cfg.get("_cde_http") or ctx.http
        for it in intents:
            if now - it.at > 3600:  # a catch-up booking: today's book says nothing about that hour
                continue
            coin = it.asset if it.kind == "open" else coin_of.get(it.position_id) or it.meta.get("key", "").split(":")[0]
            snap = cde_book.snapshot(http, coin, now) if coin else None
            if snap:
                it.meta["cde_entry" if it.kind == "open" else "cde_exit"] = snap

    def price_controls(self, ctx: Context, now: int) -> None:
        """Price the random-entry control of each signal whose +-15-day window has closed (reporting only: a failure
        is retried for 3 days, then the trade simply has no control; it never stops the strategy)."""
        due = ctx.state.get("control_due") or {}
        for key, (coin, h) in list(due.items()):
            ready = (h + CONTROL + 1 + self.hold) * 3600 + self.delay * G + 60  # the last control exit candle is final
            if now < ready:
                continue
            lo_h, n = h - CONTROL - 1, 2 * CONTROL + self.hold + 3
            try:
                m = control_gross(hourly(lo_h, self.get(ctx, coin, lo_h * 3600, (lo_h + n) * 3600), n)[5], lo_h, h, self.hold, self.delay)
            except Exception:  # noqa: BLE001
                if now - ready < 3 * 86400:
                    continue
                m = None
            ctx.state.setdefault("controls", {})[key] = m
            del due[key]

    def exit_intent(self, coin, lo_h, C15, exit_t, now, position_id="", key="") -> Intent | None:
        """The close at the 15m bar ending at exit_t (or the next one there is). None while Coinbase has no
        close at or after it yet: wait for the next run, and after a day give up waiting and use the latest."""
        k = int((exit_t - lo_h * 3600) // G) - 1  # the 15m bar closing at exit_t
        j = k
        while j < len(C15) and (j < 0 or np.isnan(C15[j])):
            j += 1
        if j >= len(C15):
            ok = np.where(~np.isnan(C15))[0]
            if now - exit_t < 86400 or not len(ok):
                return None
            j = int(ok[-1])
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
                "entry": f"{self.delay * 15} min after the signal hour's close", "venue": "coinbase (US spot)",
                "size_usd": self.size, "window": [self.start, self.end]}

    def evaluate(self, trades: list[Trade], now: float, state: dict) -> Verdict:
        by = defaultdict(list)
        for t in trades:
            by[t.meta.get("entry_day")].append(t.net_return)
        n = len(trades)
        if n < 2:
            return Verdict("pending", n, {"n": n}, f"{n} trade(s); scored after {self.end} (registered)")
        lo, hi = day_ci(by)
        m = float(np.mean([t.net_return for t in trades]))
        stats = {"n": n, "days": len(by), "mean_net": m, "lo": lo, "hi": hi}
        summary = f"{n} trades on {len(by)} days: mean {m * 100:+.2f}%/trade [{lo * 100:+.2f}, {hi * 100:+.2f}]"
        gross = [t.exit_price / t.entry_price - 1 for t in trades]
        for venue, c in self.venue_costs.items():  # same fills, each venue's cost per side (additive, as the scorer)
            stats[f"mean_net_{venue}"] = v = float(np.mean(gross)) - 2 * float(c)
            summary += f"; {v * 100:+.2f}% at {venue} ({float(c) * 100:.2f}%/side)"
        cde = [t.meta[k]["half_spread_bps"] for t in trades for k in ("cde_entry", "cde_exit") if t.meta.get(k)]
        if cde:
            stats.update(cde_half_spread_bps=float(np.median(cde)), cde_sides=len(cde))
            summary += f"; Coinbase US perp half-spread at our fills median {stats['cde_half_spread_bps']:.1f} bp over {len(cde)} sides (fees not included)"
        ctl = (state or {}).get("controls") or {}
        ex = defaultdict(list)  # costs cancel: the control pays the same cost per side
        for t, g in zip(trades, gross):
            if ctl.get(t.meta.get("key")) is not None:
                ex[t.meta.get("entry_day")].append(g - ctl[t.meta["key"]])
        k = sum(len(v) for v in ex.values())
        if k >= 2:
            e_lo, e_hi = day_ci(ex)
            stats.update(excess=sum(map(sum, ex.values())) / k, excess_lo=e_lo, excess_hi=e_hi, excess_n=k)
            summary += (f"; excess over random entries (same coin, +-15 days) {stats['excess'] * 100:+.2f}% "
                        f"[{e_lo * 100:+.2f}, {e_hi * 100:+.2f}] on {k} trades")
        if datetime.fromtimestamp(now, timezone.utc).date() <= date.fromisoformat(self.end):
            return Verdict("pending", n, stats, f"{summary}; scored after {self.end} (registered)")
        return Verdict("pass" if m > 0 and lo > 0 else "fail", n, stats, summary)
