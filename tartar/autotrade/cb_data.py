"""Coinbase daily history for the coins that have Coinbase US perps ("-CDE"), as the cde-vol-momentum
registration uses it (handoff/preregistration/cde-vol-momentum/SPEC.md, cde_forward.py): Coinbase
Exchange's public USD spot daily candles stand in for the perps (the perps are too new for history).
Cached as <COIN>.csv (day, close, USD volume) and topped up incrementally."""

from __future__ import annotations

import csv
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

CB = "https://api.exchange.coinbase.com"
COINS = ["BTC", "ETH", "SOL", "XRP", "ADA", "AVAX", "LINK", "LTC", "DOT", "DOGE", "BCH", "NEAR", "SUI", "HYPE",
         "BNB", "AAVE", "ONDO", "XLM", "ENA", "HBAR", "PEPE", "SHIB", "ZEC"]
FIRST = date(2019, 1, 1)


def fetch(http, coin: str, d0: date, d1: date, pause: float = 0.2) -> dict[str, tuple[float, float]]:
    """Daily (close, USD volume) for days d0 .. d1 (300 a request); {} for a coin Coinbase doesn't list."""
    out: dict[str, tuple[float, float]] = {}
    d = d0
    while d <= d1:
        e = min(d + timedelta(days=299), d1)
        for i in range(5):
            r = http.get(f"{CB}/products/{coin}-USD/candles", params={
                "granularity": 86400, "start": datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat(),
                "end": datetime(e.year, e.month, e.day, tzinfo=timezone.utc).isoformat()})
            if r.status_code in (200, 404):
                break
            time.sleep(2 * (i + 1))
        if r.status_code == 404:
            return out
        r.raise_for_status()
        for ts, lo, hi, op, cl, v in r.json():
            out[datetime.fromtimestamp(ts, timezone.utc).date().isoformat()] = (float(cl), float(v) * float(cl))
        d = e + timedelta(days=1)
        time.sleep(pause)
    return out


def load_daily(http, today: date, daily_dir: Path, coins: list[str] = COINS, pause: float = 0.2):
    """(days, coins, C, V): completed daily closes and USD volumes up to yesterday, cache topped up."""
    end = today - timedelta(days=1)
    daily_dir.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict[str, tuple[float, float]]] = {}
    for coin in coins:
        f = daily_dir / f"{coin}.csv"
        have = {r[0]: (float(r[1]), float(r[2])) for r in csv.reader(f.open())} if f.exists() else {}
        d0 = date.fromisoformat(max(have)) - timedelta(days=3) if have else FIRST
        if d0 <= end:
            have.update({d: x for d, x in fetch(http, coin, d0, end, pause).items() if d <= end.isoformat()})
            f.write_text("".join(f"{d},{have[d][0]},{have[d][1]}\n" for d in sorted(have)))
        rows[coin] = have
    first = min((date.fromisoformat(min(r)) for r in rows.values() if r), default=end)
    days = [first + timedelta(days=i) for i in range((end - first).days + 1)]
    ix = {d.isoformat(): i for i, d in enumerate(days)}
    C = np.full((len(days), len(coins)), np.nan)
    V = np.full_like(C, np.nan)
    for j, c in enumerate(coins):
        for d, (px, vol) in rows[c].items():
            if d in ix:
                C[ix[d], j], V[ix[d], j] = px, vol
    return days, list(coins), C, V
