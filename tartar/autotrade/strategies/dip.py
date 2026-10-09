"""The pre-registered dip rule on established PumpSwap memecoins (handoff/preregistration/dip-rolling).

Rule (SPEC.json, unchanged): on 5-minute bars, if a pool's close fell more than 5% over the last 12
bars, buy at the next bar's open and sell at the close of bar t+48 (4 hours); one position per pool.
Universe: every pool in the rolling cohort files (a token counts from its first cohort). Costs: the
registered ones (0.5%/side fee, impact size / (liquidity / 2) per side, $0.05 per transaction).

The agent trades it forward on paper from the first bar it sees for each pool (no back-filled
trades). Each run fetches the latest 5-minute OHLCV per pool from GeckoTerminal and acts on every
bar completed since its cursor, so the schedule's cadence only delays fills, never changes them.

Scoring (SPEC.json "evaluation", applied to the agent's own paper trades): once there are >= 200
trades or 21 days since the agent's first trade, success = excess over random entries in the same
pools > 0 with its 90% pool-bootstrap CI above 0, AND mean net > 0. The random-entry baseline per
trade is the mean net of entering the same pool at every bar since the agent first saw it (within
the ~3.5 days of 5-minute bars one GeckoTerminal request returns), same hold.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from ..core import Context, CostModel, Intent, Trade, Verdict, bootstrap_ci

GECKO = "https://api.geckoterminal.com/api/v2/networks/solana"


class DipStrategy:
    _cache: dict = {}  # (pool, 5-minute bucket) -> rows: variants share one fetch per run

    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self.prereg = cfg.get("prereg", "handoff/preregistration/dip-rolling")
        spec = json.loads((Path(self.prereg) / "SPEC.json").read_text())
        self.rule, self.costs, self.eval = dict(spec["rule"]), spec["costs"], spec["evaluation"]
        self.rule.update(cfg.get("rule_overrides", {}))
        self.shadow = bool(cfg.get("shadow"))
        self.family_size = int(cfg.get("family_size", 1))
        self.size = float(cfg.get("size_usd", self.costs["size_usd"]))
        measured = Path(self.prereg) / "fees-measured.json"  # per-pool PumpSwap fees measured on chain (addendum)
        self.measured = json.loads(measured.read_text()) if measured.exists() else {}
        self._grids: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        self._last_call = 0.0
        self.fetch = cfg.get("_fetch") or self._fetch  # tests inject a fake fetcher

    # data
    def pools(self) -> list[dict]:
        seen, out = set(), []
        files = sorted(Path(self.prereg).glob("cohort-*.json"))
        for c in sorted((json.loads(f.read_text()) for f in files), key=lambda c: c["registered_at"]):
            t_reg = datetime.fromisoformat(c["registered_at"].replace("Z", "+00:00")).timestamp()
            for p in c["pools"]:
                if p["token"] not in seen:
                    seen.add(p["token"])
                    out.append({**p, "registered_ts": t_reg})
        return out

    def _fetch(self, ctx: Context, pool: str) -> list[list[float]]:
        import httpx

        http = ctx.http or httpx.Client(timeout=30, headers={"accept": "application/json"})
        for attempt in range(8):
            wait = 2.2 - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()
            r = http.get(f"{GECKO}/pools/{pool}/ohlcv/minute", params={"aggregate": 5, "limit": 1000, "currency": "usd"})
            if r.status_code == 429:
                time.sleep(min(10 * (attempt + 1), 60))
                continue
            if r.status_code == 404:
                return []
            r.raise_for_status()
            rows = r.json().get("data", {}).get("attributes", {}).get("ohlcv_list") or []
            return sorted([[int(t), float(o), float(h), float(lo), float(c), float(v)] for t, o, h, lo, c, v in rows])
        raise RuntimeError("GeckoTerminal rate limit")

    def grid(self, rows, now: float):
        """Bars on a regular 5-minute grid (missing bars carry the last close), completed bars only."""
        bar = self.rule["bar_seconds"]
        rows = [r for r in rows if r[0] + bar <= now]
        if not rows:
            return np.array([]), np.array([]), np.array([])
        t = np.arange(rows[0][0], rows[-1][0] + bar, bar)
        by_t = {r[0]: r for r in rows}
        o, c = np.empty(len(t)), np.empty(len(t))
        prev = rows[0][4]
        for i, ti in enumerate(t):
            r = by_t.get(int(ti))
            o[i], c[i] = (prev, prev) if r is None else (r[1], r[4])
            prev = c[i]
        return t, o, c

    def cost(self, liquidity_usd: float) -> CostModel:
        impact = self.size / max(liquidity_usd / 2.0, 1.0)
        return CostModel(fee=self.costs["fee_per_side"], impact=impact, fixed_usd=self.costs["network_usd_per_tx"])

    # the Strategy interface
    def step(self, ctx: Context) -> list[Intent]:
        bar, L, H, drop = self.rule["bar_seconds"], self.rule["lookback_bars"], self.rule["hold_bars"], self.rule["drop"]
        pools_state = ctx.state.setdefault("pools", {})
        open_by_pool = {}
        for p in ctx.positions:
            open_by_pool.setdefault(p.meta.get("pool"), []).append(p)
        intents: list[Intent] = []
        failures = 0
        pools = self.pools()
        for p in pools:
            pid = p["pool"]
            st = pools_state.setdefault(pid, {})
            try:
                ck = (pid, int(ctx.now // 300))
                if ck not in DipStrategy._cache:
                    DipStrategy._cache = {k: v for k, v in DipStrategy._cache.items() if k[1] == ck[1]}
                    DipStrategy._cache[ck] = self.fetch(ctx, pid)
                rows = DipStrategy._cache[ck]
            except Exception:  # noqa: BLE001 - one pool's data error skips that pool this run
                failures += 1
                continue
            t, o, c = self.grid(rows, ctx.now)
            if not len(t):
                continue
            self._grids[pid] = (t, o, c)
            cost = self.cost(p["liquidity_usd"])
            if "cursor" not in st:  # first sight: trade forward from here, no back-filled entries
                st["cursor"] = float(t[-1])
                st["first_bar"] = float(t[-1])
                st["busy_until"] = 0.0
                continue
            # exits first: positions whose exit bar has completed
            for pos in open_by_pool.get(pid, []):
                exit_t = pos.meta["exit_t"]
                idx = np.searchsorted(t, exit_t)
                if idx < len(t) and t[idx] == exit_t:
                    intents.append(Intent("close", self.name, float(exit_t + bar), float(c[idx]), "hold elapsed",
                                          position_id=pos.id, cost=cost,
                                          meta={"baseline": self.baseline(t, o, c, st["first_bar"], exit_t, cost)}))
            # entries: signal at bar i (completed, after the cursor), filled at bar i+1's open
            start = int(np.searchsorted(t, st["cursor"], side="right"))
            last_i = st["cursor"]
            for i in range(max(start, L), len(t) - 1):
                last_i = float(t[i])
                if t[i] <= st["busy_until"]:
                    continue
                if c[i] / c[i - L] - 1 < -drop:
                    exit_t = float(t[i] + H * bar)
                    key = f"{pid}:{int(t[i])}"
                    intents.append(Intent("open", self.name, float(t[i + 1]), float(o[i + 1]),
                                          f"close fell {100 * (1 - c[i] / c[i - L]):.1f}% over {L} bars",
                                          asset=pid, side=1, notional_usd=self.size, cost=cost,
                                          meta={"pool": pid, "label": p["name"], "signal_t": float(t[i]), "exit_t": exit_t,
                                                "key": key, "liquidity_usd": p["liquidity_usd"],
                                                "alt_cost": self.measured_cost(pid, cost), "shadow": self.shadow,
                                                "mint": p["token"].split("_", 1)[-1], "impact_assumed": cost.impact}))
                    st["busy_until"] = exit_t
                    idx = np.searchsorted(t, exit_t)
                    if idx < len(t) and t[idx] == exit_t:  # the whole hold is already in the data
                        intents.append(Intent("close", self.name, float(exit_t + bar), float(c[idx]), "hold elapsed",
                                              cost=cost, meta={"key": key, "baseline": self.baseline(t, o, c, st["first_bar"], exit_t, cost)}))
            if len(t) - 1 > max(start, L):
                st["cursor"] = last_i
        if pools and failures == len(pools):
            raise RuntimeError(f"no pool data this run ({failures} fetch failures)")
        return intents

    def describe(self) -> dict:
        return {"rule": self.rule, "costs": self.costs, "size_usd": self.size, "shadow": self.shadow,
                "family_size": self.family_size,
                "success": "at >= 200 trades or 21 days: excess over random entries > 0 with its CI above 0 "
                           f"(two-sided {100 * (1 - 0.1 / self.family_size):.1f}% pool bootstrap) AND mean net > 0"}

    def measured_cost(self, pool: str, cost: CostModel) -> dict:
        """The registered cost model with the pool's measured PumpSwap fee (secondary, ADDENDUM-2026-10-09-fees)."""
        fee = self.measured.get(pool, {}).get("fee_per_side", cost.fee)
        return {"fee": fee, "impact": cost.impact, "fixed_usd": cost.fixed_usd}

    def baseline(self, t, o, c, first_bar, exit_t, cost: CostModel) -> float:
        """Mean net of entering this pool at every bar since the agent first saw it, same hold."""
        H = self.rule["hold_bars"]
        lo = int(np.searchsorted(t, first_bar))
        hi = int(np.searchsorted(t, exit_t, side="right"))
        i = np.arange(lo, hi - H - 1)
        if not len(i):
            return float("nan")
        gross = c[i + H] / o[i + 1]
        side = cost.fee + cost.impact
        return float(np.mean(gross * (1 - side) ** 2 - 1 - 2 * cost.fixed_usd / self.size))

    def marks(self, ctx: Context) -> dict[str, tuple[float, float]]:
        out = {}
        for pos in ctx.positions:
            g = self._grids.get(pos.meta.get("pool"))
            if g and len(g[0]):
                out[pos.id] = (float(g[2][-1]), float(g[0][-1] + self.rule["bar_seconds"]))
        return out

    def evaluate(self, trades: list[Trade], now: float, state: dict) -> Verdict:
        n = len(trades)
        if not n:
            return Verdict("pending", 0, {}, "no closed trades yet")
        first = min(t.entry_at for t in trades)
        days = (now - first) / 86400
        net = [t.net_return for t in trades]
        pools = [t.meta.get("pool", t.asset) for t in trades]
        valid = [(t.net_return - t.meta["baseline"], t.meta.get("pool", t.asset)) for t in trades
                 if t.meta.get("baseline") == t.meta.get("baseline") and t.meta.get("baseline") is not None]
        a = 0.05 / self.family_size  # Bonferroni across a variant family (1 for the registered rule)
        m, lo_m, hi_m = bootstrap_ci(net, pools, q=(a, 1 - a))
        stats = {"n": n, "days": round(days, 2), "mean_net": m, "mean_lo": lo_m, "mean_hi": hi_m}
        if valid:
            e, lo_e, hi_e = bootstrap_ci([x for x, _ in valid], [g for _, g in valid], q=(a, 1 - a))
            stats.update(excess=e, excess_lo=lo_e, excess_hi=hi_e)
        alt = [t.meta["alt_net_return"] for t in trades if "alt_net_return" in t.meta]
        if alt:
            stats["mean_net_measured_fees"] = float(np.mean(alt))
        due = n >= 200 or days >= 21
        summary = (f"{n} trades over {days:.1f} days: mean net {100 * m:+.2f}% [{100 * lo_m:+.2f}, {100 * hi_m:+.2f}]"
                   + (f" ({100 * stats['mean_net_measured_fees']:+.2f}% at measured pool fees)" if alt else "")
                   + (f", excess over random entries {100 * stats['excess']:+.2f}% [{100 * stats['excess_lo']:+.2f}, {100 * stats['excess_hi']:+.2f}]" if valid else ""))
        if not due:
            return Verdict("pending", n, stats, f"{summary}; scored at 200 trades or 21 days")
        ok = valid and stats["excess_lo"] > 0 and m > 0
        return Verdict("pass" if ok else "fail", n, stats, summary)
