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

Execution at real-trading costs (config ``execution``, from 2026-10-10, profitability real fills): two
real 0.01 SOL round trips on the rule's signals trailed its gross by 5-6 points
(handoff/data/real-fills/dip-report-2026-10-10.txt). With ``entry: next_bar_close`` the paper entry is
bar t+1's close instead of its open (the real buys went out 228-296 s into bar t+1, after GeckoTerminal's
~1 min publish delay and the pool scan, and the price had already rebounded 1-2%), booked when that bar
completes; ``route_fee_per_side`` adds the route's own fee (PumpPortal Lightning 1%) on both sides. The
rule (signal, hold, exit at bar t+48's close) is unchanged. The random-entry baseline uses the same
execution, and each trade keeps the registered-execution figure (``registered_net``) as a secondary.
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
        ex = cfg.get("execution") or {}
        self.late_entry = ex.get("entry") in ("next_bar_close", "delay", "schedule")
        # "schedule": entry at the agent's next scheduled run after the signal bar closes (hourly Action at
        # minute ``run_minute``, plus ``run_lag_s`` to fetch and act), priced inside the bar holding that moment
        self.schedule = (float(ex.get("run_minute", 6)) * 60 + float(ex.get("run_lag_s", 60))) % 3600 \
            if ex.get("entry") == "schedule" else None
        # entry this many seconds into bar t+1, priced between its open and close (300 = its close)
        self.entry_delay = float(ex.get("entry_delay_s", 300.0 if ex.get("entry") == "next_bar_close" else 0.0))
        self.replay = None if cfg.get("rule_overrides") else cfg.get("replay")  # registered rule only
        self.route_fee = float(ex.get("route_fee_per_side", 0.0))
        self.costs_version = ex.get("version")

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

    def cost(self, liquidity_usd: float, route_fee: float | None = None) -> CostModel:
        impact = self.size / max(liquidity_usd / 2.0, 1.0)
        fee = self.costs["fee_per_side"] + (self.route_fee if route_fee is None else route_fee)
        return CostModel(fee=fee, impact=impact, fixed_usd=self.costs["network_usd_per_tx"])

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
                    pos_cost = self.cost(p["liquidity_usd"], pos.meta.get("route_fee", 0.0))  # as it was opened
                    intents.append(Intent("close", self.name, float(exit_t + bar), float(c[idx]), "hold elapsed",
                                          position_id=pos.id, cost=pos_cost,
                                          meta={"baseline": self.baseline(t, o, c, st["first_bar"], exit_t, cost)}))
            # entries: signal at bar i (completed, after the cursor), filled at bar i+1's open
            start = int(np.searchsorted(t, st["cursor"], side="right"))
            last_i = st["cursor"]
            for i in range(max(start, L), len(t) - 1):
                if c[i] / c[i - L] - 1 < -drop and t[i] > st["busy_until"] and self.entry(t, o, c, i) is None:
                    break  # the entry moment isn't in the data yet: look again next run
                last_i = float(t[i])
                if t[i] <= st["busy_until"]:
                    continue
                if c[i] / c[i - L] - 1 < -drop:
                    exit_t = float(t[i] + H * bar)
                    key = f"{pid}:{int(t[i])}"
                    at, px = self.entry(t, o, c, i)
                    intents.append(Intent("open", self.name, at, px,
                                          f"close fell {100 * (1 - c[i] / c[i - L]):.1f}% over {L} bars"
                                          + (f" (entry {(at - t[i + 1]) / 60:.0f} min after the signal bar: {self.entry_desc()})" if self.late_entry else ""),
                                          asset=pid, side=1, notional_usd=self.size, cost=cost,
                                          meta={"pool": pid, "label": p["name"], "signal_t": float(t[i]), "exit_t": exit_t,
                                                "key": key, "liquidity_usd": p["liquidity_usd"],
                                                "alt_cost": self.measured_cost(pid, cost), "shadow": self.shadow,
                                                "mint": p["token"].split("_", 1)[-1], "impact_assumed": cost.impact,
                                                "registered_entry_price": float(o[i + 1]), "route_fee": self.route_fee,
                                                "late_entry": self.late_entry}))
                    st["busy_until"] = exit_t
                    idx = np.searchsorted(t, exit_t)
                    if idx < len(t) and t[idx] == exit_t:  # the whole hold is already in the data
                        intents.append(Intent("close", self.name, float(exit_t + bar), float(c[idx]), "hold elapsed",
                                              cost=cost, meta={"key": key, "baseline": self.baseline(t, o, c, st["first_bar"], exit_t, cost)}))
            if len(t) - 1 > max(start, L) and last_i > st["cursor"]:
                st["cursor"] = last_i
        if pools and failures == len(pools):
            raise RuntimeError(f"no pool data this run ({failures} fetch failures)")
        return intents

    def entry(self, t, o, c, i: int) -> tuple[float, float] | None:
        """(time, price) of the entry for a signal at bar i, or None if that moment isn't in the data yet."""
        bar = self.rule["bar_seconds"]
        t1 = float(t[i] + bar)  # the signal bar's close
        if not self.late_entry:
            return (t1, float(o[i + 1])) if i + 1 < len(t) else None
        # a run sees a bar ~60 s after it closes (GeckoTerminal's publishing lag), so a bar closing just before
        # the run's check waits for the next run; the entry bar is complete one run later, when it is booked
        at = t1 + (60 + (self.schedule - t1 - 60) % 3600 if self.schedule is not None else self.entry_delay)
        k = i + 1 + int((at - t1) // bar)
        if self.schedule is None and k > i + 1:  # "delay" / "next_bar_close": capped at bar t+1's close
            k = i + 1
        if k >= len(t):
            return None
        f = min(max((at - float(t[k])) / bar, 0.0), 1.0)
        return at, float(o[k] + (c[k] - o[k]) * f)

    def entry_desc(self) -> str:
        if self.schedule is not None:
            return f"the next hourly run, :{int(self.schedule // 60):02d}:{int(self.schedule % 60):02d}"
        return f"{self.entry_delay:.0f} s into bar t+1"

    def delayed_px(self, o: float, c: float) -> float:
        """Price ``entry_delay`` seconds into a bar, interpolated between its open and close."""
        f = min(max(self.entry_delay / self.rule["bar_seconds"], 0.0), 1.0)
        return float(o + (c - o) * f)

    def describe(self) -> dict:
        return {"rule": self.rule, "costs": self.costs, "size_usd": self.size, "shadow": self.shadow,
                "family_size": self.family_size, "costs_version": self.costs_version,
                "execution": {"entry": self.entry_desc() if self.late_entry else "next_bar_open",
                              "route_fee_per_side": self.route_fee},
                "change_note": (f"paper execution at real-trading costs: entry at {self.entry_desc()} (signal latency), "
                                f"+{100 * self.route_fee:g}%/side route fee; rule unchanged "
                                "(handoff/data/real-fills/dip-report-2026-10-10.txt)") if self.costs_version else "",
                "success": "at >= 200 trades or 21 days: excess over random entries > 0 with its CI above 0 "
                           f"(two-sided {100 * (1 - 0.1 / self.family_size):.1f}% pool bootstrap) AND mean net > 0"}

    def measured_cost(self, pool: str, cost: CostModel) -> dict:
        """The registered cost model with the pool's measured PumpSwap fee (secondary, ADDENDUM-2026-10-09-fees)."""
        fee = self.measured.get(pool, {}).get("fee_per_side", self.costs["fee_per_side"]) + (cost.fee - self.costs["fee_per_side"])
        return {"fee": fee, "impact": cost.impact, "fixed_usd": cost.fixed_usd}

    def replay_rows(self) -> list[dict]:
        if not getattr(self, "replay", None):
            return []
        if not hasattr(self, "_replay_rows"):
            path = Path(self.replay)
            self._replay_rows = json.loads(path.read_text()) if path.exists() else []
        return self._replay_rows

    def replay_nets(self, trades: list[Trade] = ()) -> tuple[list[float], list[str]]:
        """Net returns of the replay's trades (gross from bar t+1's open) at this strategy's execution costs:
        registered fee + route fee and the pool's impact on both sides, network fees; the entry delay is not
        re-applied (the replay has no intrabar prices), so this is if anything optimistic. Replay trades the
        agent also took on paper (same pool label, within 10 minutes) are dropped so nothing counts twice."""
        seen = [(t.meta.get("label"), t.meta.get("signal_t", t.entry_at)) for t in trades]
        rows = [r for r in self.replay_rows()
                if not any(lab == r["name"] and abs(st - r["t"]) <= 600 for lab, st in seen)]
        if not rows:
            return [], []
        by_name = {p["name"]: p for p in self.pools()}
        fee = self.costs["fee_per_side"] + self.route_fee
        out, groups = [], []
        for r in rows:
            p = by_name.get(r["name"])
            impact = self.size / max(p["liquidity_usd"] / 2.0, 1.0) if p else 0.0
            out.append((1 + r["gross"]) * (1 - fee) ** 2 * (1 - impact) ** 2 - 1 - 2 * self.costs["network_usd_per_tx"] / self.size)
            groups.append(p["pool"] if p else r["name"])
        return out, groups

    def spec_net(self, t: Trade) -> float:
        """A closed trade's net return as the registration and its official scorer compute it
        (established_prereg_eval.py ``net``: fee and impact multiply both sides). The paper broker books
        costs additively; scoring uses this so the agent's verdict and the baseline match the scorer."""
        impact = t.meta.get("impact_assumed", 0.0)
        fee = self.costs["fee_per_side"] + t.meta.get("route_fee", 0.0)
        return ((t.exit_price / t.entry_price) * (1 - fee) ** 2 * (1 - impact) ** 2
                - 1 - 2 * self.costs["network_usd_per_tx"] / self.size)

    def registered_net(self, t: Trade) -> float:
        """The same trade under the registered execution (bar t+1's open, no route fee): secondary."""
        impact = t.meta.get("impact_assumed", 0.0)
        entry = t.meta.get("registered_entry_price", t.entry_price)
        return ((t.exit_price / entry) * (1 - self.costs["fee_per_side"]) ** 2 * (1 - impact) ** 2
                - 1 - 2 * self.costs["network_usd_per_tx"] / self.size)

    def baseline(self, t, o, c, first_bar, exit_t, cost: CostModel) -> float:
        """Mean net of entering this pool at every bar since the agent first saw it, same hold."""
        H = self.rule["hold_bars"]
        lo = int(np.searchsorted(t, first_bar))
        hi = int(np.searchsorted(t, exit_t, side="right"))
        i = np.arange(lo, hi - H - 1)
        if not len(i):
            return float("nan")
        ent = [self.entry(t, o, c, int(j)) for j in i]  # same execution as the agent's entries
        gross = np.array([c[j + H] / e[1] for j, e in zip(i, ent) if e is not None])
        if not len(gross):
            return float("nan")
        return float(np.mean(gross * (1 - cost.fee) ** 2 * (1 - cost.impact) ** 2 - 1 - 2 * cost.fixed_usd / self.size))

    def marks(self, ctx: Context) -> dict[str, tuple[float, float]]:
        out = {}
        for pos in ctx.positions:
            g = self._grids.get(pos.meta.get("pool"))
            if g and len(g[0]):
                out[pos.id] = (float(g[2][-1]), float(g[0][-1] + self.rule["bar_seconds"]))
        return out

    def evaluate(self, trades: list[Trade], now: float, state: dict) -> Verdict:
        n = len(trades)
        if not n and not self.replay_rows():
            return Verdict("pending", 0, {}, "no closed trades yet")
        first = min([t.entry_at for t in trades] + [r["t"] for r in self.replay_rows()])
        days = (now - first) / 86400
        net = [self.spec_net(t) for t in trades]
        pools = [t.meta.get("pool", t.asset) for t in trades]
        rep_net, rep_pools = self.replay_nets(trades)
        if rep_net:  # out-of-sample replay of the same rule (counts toward the verdict, never toward the excess test)
            net, pools, n = net + rep_net, pools + rep_pools, n + len(rep_net)
        valid = [(self.spec_net(t) - t.meta["baseline"], t.meta.get("pool", t.asset)) for t in trades
                 if t.meta.get("baseline") == t.meta.get("baseline") and t.meta.get("baseline") is not None]
        a = 0.05 / self.family_size  # Bonferroni across a variant family (1 for the registered rule)
        m, lo_m, hi_m = bootstrap_ci(net, pools, q=(a, 1 - a))
        stats = {"n": n, "days": round(days, 2), "mean_net": m, "mean_lo": lo_m, "mean_hi": hi_m, "n_replay": len(rep_net)}
        if valid:
            e, lo_e, hi_e = bootstrap_ci([x for x, _ in valid], [g for _, g in valid], q=(a, 1 - a))
            stats.update(excess=e, excess_lo=lo_e, excess_hi=hi_e)
        alt = [t.meta["alt_net_return"] for t in trades if "alt_net_return" in t.meta]
        if alt:
            stats["mean_net_measured_fees"] = float(np.mean(alt))
        late = [t for t in trades if t.meta.get("late_entry") or t.meta.get("route_fee")]
        if late:
            stats["mean_net_registered_execution"] = float(np.mean([self.registered_net(t) for t in late]))
            stats["mean_net_real_execution"] = float(np.mean([self.spec_net(t) for t in late]))
            stats["n_real_execution"] = len(late)
        quoted = [t.meta["quoted_net_return"] for t in trades if "quoted_net_return" in t.meta]
        if quoted:
            stats["mean_net_quoted_impact"] = float(np.mean(quoted))
            stats["n_quoted"] = len(quoted)
        due = n >= 200 or days >= 21
        summary = (f"{n} trades{f' ({len(rep_net)} from the out-of-sample replay)' if rep_net else ''} over {days:.1f} days: "
                   f"mean net {100 * m:+.2f}% [{100 * lo_m:+.2f}, {100 * hi_m:+.2f}]"
                   + (f" ({len(late)} at real-trading execution: {100 * stats['mean_net_real_execution']:+.2f}% vs "
                      f"{100 * stats['mean_net_registered_execution']:+.2f}% at the registered execution)" if late else "")
                   + (f" ({100 * stats['mean_net_measured_fees']:+.2f}% at measured pool fees)" if alt else "")
                   + (f" ({100 * stats['mean_net_quoted_impact']:+.2f}% at Jupiter-measured impact, {len(quoted)} trades)" if quoted else "")
                   + (f", excess over random entries {100 * stats['excess']:+.2f}% [{100 * stats['excess_lo']:+.2f}, {100 * stats['excess_hi']:+.2f}]" if valid else ""))
        if not due:
            return Verdict("pending", n, stats, f"{summary}; scored at 200 trades or 21 days")
        ok = valid and stats["excess_lo"] > 0 and m > 0
        return Verdict("pass" if ok else "fail", n, stats, summary)
