"""Would the perps momentum book survive on the coins a US person may soon reach? (gap review, 2026-10-11)

    python3 handoff/experiments/deribit_universe.py

The CFTC's no-action letter of 2026-05-29 lets Coinbase give US customers access to Deribit's perps
(institutional first; retail "later this year"). This reruns the agent's own momentum backtest
(`tartar.autotrade.search.backtest`: Hyperliquid daily closes and funding, 20 bps per side, registered
universe filters) with the universe cut to coins that have a Deribit perp today, beside the full
Hyperliquid universe on the same weeks. Two cuts:
  * deribit-now: every coin with a Deribit perp today, over all weeks (look-ahead in the choice of
    coins: most were listed in 2026, so this answers "trade this list from now on", not history);
  * deribit-2022: the 15 coins Deribit has listed since 2022 (no look-ahead, but a thin universe).
Prices and funding are Hyperliquid's, as a stand-in for Deribit's. Paper research only.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, ".")
from tartar.autotrade import hl_data  # noqa: E402
from tartar.autotrade.search import Panel, backtest  # noqa: E402

RULES = {
    "xs_momentum": {"lookback": 14, "quant": 5, "scaled": False, "signal_weekday": 0, "lag_days": 1},
    "vol_momentum": {"lookback": 14, "quant": 5, "scaled": True, "signal_weekday": 0, "lag_days": 1},
    "cand-L21-q10": {"lookback": 21, "quant": 10, "scaled": True, "signal_weekday": 0, "lag_days": 2},
}
HL_NAME = {"1000BONK": "kBONK", "1000PEPE": "kPEPE", "1000SHIB": "kSHIB", "1000MOG": "kMOG"}


def deribit_perps(http) -> dict[str, date]:
    r = http.get("https://www.deribit.com/api/v2/public/get_instruments",
                 params={"currency": "any", "kind": "future", "expired": "false"}).json()["result"]
    out: dict[str, date] = {}
    for i in r:
        if i["settlement_period"] != "perpetual":
            continue
        base = i["instrument_name"].split("-")[0].split("_")[0]
        d = datetime.fromtimestamp(i["creation_timestamp"] / 1000, timezone.utc).date()
        coin = HL_NAME.get(base, base)
        out[coin] = min(out.get(coin, d), d)
    return out


def sub_panel(days, coins, C, V, F, keep: set[str]) -> Panel:
    j = [k for k, c in enumerate(coins) if c in keep]
    return Panel(days, [coins[k] for k in j], C[:, j], V[:, j], F)


def stats(s: list[tuple[date, float]]) -> str:
    if not s:
        return "no weeks"
    r = np.array([v for _, v in s])
    srt = np.sort(r)
    ex5 = srt[:-5].mean() if len(r) > 5 else float("nan")
    rng = np.random.default_rng(1)
    nb = (len(r) + 3) // 4
    starts = rng.integers(0, max(len(r) - 3, 1), (5000, nb))
    bm = np.array([np.concatenate([r[s0:s0 + 4] for s0 in row])[:len(r)].mean() for row in starts])
    lo, hi = np.percentile(bm, [5, 95])
    return (f"{len(r):3d} wks  mean {r.mean() * 100:+.2f}%/wk [{lo * 100:+.2f}, {hi * 100:+.2f}]  "
            f"without best 5 {ex5 * 100:+.2f}  last 52 {r[-52:].mean() * 100:+.2f}  worst {r.min() * 100:+.1f}")


def main():
    http = httpx.Client(timeout=60)
    today = datetime.now(timezone.utc).date()
    der = deribit_perps(http)
    days, coins, C, V, _ = hl_data.load_daily(http, today)
    F = hl_data.load_funding(Path("autotrade/search/funding_daily.csv"))
    have = set(coins)
    now_set = {c for c in der if c in have}
    old_set = {c for c, d in der.items() if d < date(2023, 1, 1) and c in have}
    print(f"{today}: Deribit perps {len(der)}; on Hyperliquid with >= 60 days of history: {len(now_set)}; "
          f"listed on Deribit before 2023: {len(old_set)} ({', '.join(sorted(old_set))})")
    print(f"not on Hyperliquid: {', '.join(sorted(c for c in der if c not in have))}")
    panels = {"hyperliquid (all)": Panel(days, coins, C, V, F),
              "deribit-now": sub_panel(days, coins, C, V, F, now_set),
              "deribit-2022": sub_panel(days, coins, C, V, F, old_set)}
    for rn, p in RULES.items():
        print(f"\n{rn} (20 bps/side + funding):")
        full = dict(backtest(panels["hyperliquid (all)"], p))
        for pn, P in panels.items():
            s = backtest(P, p)
            print(f"  {pn:18s} {stats(s)}")
            if pn != "hyperliquid (all)" and s:
                same = [(d, full[d]) for d, _ in s if d in full]
                print(f"  {'  same weeks, HL':18s} {stats(same)}")


if __name__ == "__main__":
    main()
