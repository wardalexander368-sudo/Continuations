"""The adopted US live rule's start gate and cost checks, read from the Alpaca paper fills (paper only).

Rule: ``handoff/live-rule-us.md`` (v2, adopted by AJ 2026-10-12). Only ``us_capit`` is eligible. Its gate is judged
on the Alpaca paper fills of the mirror line whose orders go at the first hourly run after the signal, the timing a
live route would have: ``us_capit_fast`` (config ``alpaca_paper``). Nothing here sends an order or changes a trade;
it reads ``alpaca_fills.jsonl`` and reports. Meeting the gate does not start live trading: that still needs AJ's
go in words, a funded Alpaca live account and a live route, none of which exists.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

GATE_STRATEGY = "us_capit_fast"  # Alpaca paper fills at the live route's timing (first run after the signal)
MIN_CRASH_DAYS, MIN_TRADES = 3, 8
MIN_MEAN_NET = -0.047            # backtest 10th percentile of the mean after 3 crash days (120-min entry)
MAX_MEDIAN_COST = 0.0050         # per side, gate and coin screen
STOP_COST = 0.0060               # per side: the rule's cost stop; health goes red above it
MAX_GAP_BPS = 50                 # no fill more than 0.5% from the paper book's price
MIN_COIN_FILLS = 3               # round trips before a coin's own cost is judged
HEALTH_MIN_FILLS = 5             # round trips before health judges the measured cost


def _rows(root: Path) -> list[dict]:
    p = Path(root) / "alpaca_fills.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def round_trips(rows: list[dict], strategy: str | None = None) -> list[dict]:
    """Closed Alpaca round trips (``sell`` rows with a measured cost), each with ``day``: its buy's UTC date."""
    buys = {r.get("position"): r for r in rows if r.get("event") == "buy"}
    out = []
    for r in rows:
        if r.get("event") != "sell" or "measured_side_cost" not in r:
            continue
        if strategy is not None and r.get("strategy") != strategy:
            continue
        b = buys.get(r.get("position"))
        at = (b or {}).get("paper_at") or (b or {}).get("at") or r.get("at")
        out.append({**r, "day": time.strftime("%Y-%m-%d", time.gmtime(at))})
    return out


def coin_screen(trips: list[dict]) -> dict[str, dict]:
    """Per coin: round trips, median measured cost per side, and whether it passes (None: too few fills yet)."""
    by: dict[str, list[float]] = {}
    for r in trips:
        by.setdefault(r["symbol"], []).append(r["measured_side_cost"])
    return {s: {"n": len(c), "median_cost": _median(c), "ok": (_median(c) <= MAX_MEDIAN_COST) if len(c) >= MIN_COIN_FILLS else None}
            for s, c in sorted(by.items())}


def gate(rows: list[dict]) -> dict:
    """The paper side of the start gate (items 2-4 of the rule); item 1 (AJ, funded account, live route) is never checked here."""
    trips = round_trips(rows, GATE_STRATEGY)
    days = sorted({r["day"] for r in trips})
    out = {"strategy": GATE_STRATEGY, "trades": len(trips), "crash_days": len(days), "coins": coin_screen(trips)}
    unmet = []
    if len(days) < MIN_CRASH_DAYS or len(trips) < MIN_TRADES:
        unmet.append(f"{len(days)}/{MIN_CRASH_DAYS} crash days, {len(trips)}/{MIN_TRADES} trades")
    if trips:
        out["mean_net"] = sum(r["alpaca_net_return"] for r in trips) / len(trips)
        out["median_cost"] = _median([r["measured_side_cost"] for r in trips])
        out["max_gap_bps"] = max(max(abs(r.get("entry_gap_bps") or 0), abs(r.get("exit_gap_bps") or 0)) for r in trips)
        if out["mean_net"] <= MIN_MEAN_NET:
            unmet.append(f"mean net {100 * out['mean_net']:+.2f}% is not above {100 * MIN_MEAN_NET:.1f}%")
        if out["median_cost"] > MAX_MEDIAN_COST:
            unmet.append(f"median cost {100 * out['median_cost']:.2f}%/side is above {100 * MAX_MEDIAN_COST:.2f}%")
        if out["max_gap_bps"] > MAX_GAP_BPS:
            unmet.append(f"a fill was {out['max_gap_bps']:.0f} bp from the paper price (max {MAX_GAP_BPS})")
    out["unmet"] = unmet
    out["met"] = not unmet
    return out


def health_items(root: Path) -> list[dict]:
    """Measured Alpaca paper cost against the rule: yellow above 0.50%/side, red above 0.60%, after 5 round trips."""
    trips = round_trips(_rows(root))
    if len(trips) < HEALTH_MIN_FILLS:
        return [{"check": "Alpaca paper cost", "level": "green",
                 "detail": f"{len(trips)} round trip(s); judged from {HEALTH_MIN_FILLS} (live rule: at most 0.50%/side)"}]
    med = _median([r["measured_side_cost"] for r in trips[-20:]])
    level = "red" if med > STOP_COST else "yellow" if med > MAX_MEDIAN_COST else "green"
    wide = [s for s, c in coin_screen(trips).items() if c["ok"] is False]
    return [{"check": "Alpaca paper cost", "level": level,
             "detail": f"median {100 * med:.2f}%/side over the last {min(len(trips), 20)} round trips "
                       f"(live rule: gate 0.50%, stop 0.60%; assumed 0.39%)"
                       + (f"; coins above 0.50%: {', '.join(wide)}" if wide else "")}]


def report_lines(root: Path) -> list[str]:
    """One REPORT line: where the adopted live rule's gate stands."""
    g = gate(_rows(root))
    head = (f"**Live rule gate** (`handoff/live-rule-us.md`, us_capit, judged on `{g['strategy']}`'s Alpaca paper fills): "
            f"{g['crash_days']}/{MIN_CRASH_DAYS} crash days, {g['trades']}/{MIN_TRADES} trades")
    if "mean_net" in g:
        head += f", mean net {100 * g['mean_net']:+.2f}% (bar {100 * MIN_MEAN_NET:.1f}%), median cost {100 * g['median_cost']:.2f}%/side (bar 0.50%)"
    head += ". " + ("**Paper side met**; going live still needs AJ's go, a funded Alpaca live account and a live route."
                    if g["met"] else "Not met yet. Nothing trades live.")
    coins = [f"{s} {100 * c['median_cost']:.2f}% ({c['n']}){'' if c['ok'] is not False else ' ✗'}" for s, c in g["coins"].items()]
    return ["", head] + ([f"Coin cost screen (median per side, round trips; ✗ = above 0.50%): {', '.join(coins)}."] if coins else [])
