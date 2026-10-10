"""Holding a Hyperliquid vault on paper: the registered HLP test (handoff/preregistration/hlp-hold/SPEC.md,
scorer handoff/experiments/edge-hunt/vaults/hlp_forward.py).

The vault's allTime history has a point about every 14 days plus a moving "now" point. Each booked point
(every point but the newest) inside the window is one interval: the paper position closes at the
vault's index there and reopens at once, so each closed trade is one interval's time-weighted return
(PnL change / account value at the interval's start; HLP takes no commission, so no cost). Marks use
the newest point. Interval closes carry ``kept`` (the position reopens at once), so a vault twin
(``vault.py``) stays deposited across them; only the window-end close withdraws it. Scoring follows the registration: annualised return minus a 5% a year hurdle, 90%
moving-block bootstrap CI over intervals (2-interval blocks), at the end of the window; nothing earlier.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from ..core import Context, CostModel, Intent, Trade, Verdict

HL = "https://api.hyperliquid.xyz/info"
HLP = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"


def ts(s: str) -> float:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


class VaultHold:
    def __init__(self, name: str, cfg: dict):
        self.name, self.cfg = name, cfg
        self.prereg = cfg.get("prereg", "handoff/preregistration/hlp-hold/SPEC.md")
        self.vault = cfg.get("vault", HLP)
        self.size_usd = float(cfg.get("size_usd", 1000.0))
        self.start, self.end = ts(cfg.get("start", "2026-10-12")), ts(cfg.get("end", "2027-04-10"))
        self.hurdle = float(cfg.get("hurdle_apr", 0.05))
        self.fetch = cfg.get("_fetch") or self._fetch  # tests inject the history
        self._hist = None

    def _fetch(self, ctx: Context) -> tuple[list[tuple[float, float]], dict[float, float]]:
        import time

        import httpx

        if self._hist and ctx.now - self._hist[0] < 600:  # step and marks in one run share one fetch
            return self._hist[1]
        http = ctx.http or httpx.Client(timeout=60)
        for i in range(4):
            r = http.post(HL, json={"type": "vaultDetails", "vaultAddress": self.vault})
            d = r.json() if r.status_code == 200 else None
            if isinstance(d, dict) and d.get("portfolio"):
                break
            time.sleep(2 * (i + 1))
        else:
            raise RuntimeError(f"vaultDetails unavailable (HTTP {r.status_code})")
        port = dict((n, x) for n, x in d["portfolio"])["allTime"]
        av = [(t / 1000, float(v)) for t, v in port["accountValueHistory"]]
        pnl = {t / 1000: float(v) for t, v in port["pnlHistory"]}
        self._hist = (ctx.now, (av, pnl))
        return av, pnl

    def step(self, ctx: Context) -> list[Intent]:
        av, pnl = self.fetch(ctx)
        points = [(t, v) for t, v in av[:-1] if t >= self.start]  # the newest point still moves
        st = ctx.state
        idx, last, key = st.get("index", 1.0), st.get("last_t"), st.get("open_key")
        if key is None and ctx.positions:
            key = ctx.positions[0].meta.get("key")
        intents: list[Intent] = []
        for t, v in points:
            if last is not None and t <= last:
                continue
            if t > self.end:  # the window is over: the interval that crosses its end is not scored
                if key:
                    intents.append(Intent("close", self.name, t, idx, "window ended", cost=CostModel(),
                                          meta={"key": key, "window_end": True}))
                    key = None
                break
            if last is not None:
                idx *= 1 + (pnl[t] - pnl[last]) / st["last_av"]
                if key:
                    intents.append(Intent("close", self.name, t, idx, "vault history point", cost=CostModel(),
                                          meta={"key": key, "interval_days": (t - last) / 86400, "kept": True}))
            key = f"{self.name}:{int(t)}"
            intents.append(Intent("open", self.name, t, idx, "hold the vault", asset=f"vault:{self.vault[:10]}",
                                  side=1, notional_usd=self.size_usd, cost=CostModel(),
                                  meta={"key": key, "venue": "hyperliquid_vault", "vault": self.vault}))
            last, st["last_av"] = t, v
        st["index"], st["last_t"], st["open_key"] = idx, last, key
        return intents

    def marks(self, ctx: Context) -> dict[str, tuple[float, float]]:
        if not ctx.positions or ctx.state.get("last_t") is None:
            return {}
        av, pnl = self.fetch(ctx)
        t_now = av[-1][0]
        last = ctx.state["last_t"]
        px = ctx.state["index"] * (1 + (pnl[t_now] - pnl.get(last, pnl[t_now])) / ctx.state["last_av"])
        return {p.id: (px, t_now) for p in ctx.positions}

    def evaluate(self, trades: list[Trade], now: float, state: dict) -> Verdict:
        trades = [t for t in trades if not t.meta.get("window_end")]
        r = np.array([t.net_return for t in trades])
        dts = np.array([(t.exit_at - t.entry_at) / 86400 for t in trades])
        n = len(r)
        if n < 2:
            return Verdict("pending", n, {"intervals": n}, f"{n} interval(s); scored after {datetime.fromtimestamp(self.end, timezone.utc):%Y-%m-%d} (registered)")
        apr = float(np.expm1(np.log1p(r).sum() / dts.sum() * 365))
        rng = np.random.default_rng(1)
        boots = []
        for _ in range(10_000):
            ix = np.concatenate([np.arange(k, k + 2) % n for k in rng.integers(0, n, n // 2 + 1)])[:n]
            boots.append(np.expm1(np.log1p(r[ix]).sum() / dts[ix].sum() * 365) - self.hurdle)
        lo, hi = np.percentile(boots, [5, 95])
        ex = apr - self.hurdle
        stats = {"intervals": n, "days": float(dts.sum()), "apr": apr, "excess": ex, "lo": float(lo), "hi": float(hi)}
        summary = (f"{n} intervals over {dts.sum():.0f} days: {100 * apr:+.1f}% a year, minus the {100 * self.hurdle:g}% hurdle "
                   f"{100 * ex:+.1f} points [{100 * lo:+.1f}, {100 * hi:+.1f}]")
        if now < self.end + 86400:
            return Verdict("pending", n, stats, f"{summary}; scored after the window ends (registered)")
        return Verdict("pass" if ex > 0 and lo > 0 else "fail", n, stats, summary)
