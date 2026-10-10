"""Hyperliquid perps history for the candidate search: daily closes and volumes of every perp (delisted
ones from handoff/data/edge-hunt/hl-daily, read only, merged with fresh candles from the API) and
daily funding sums, cached incrementally in autotrade/search/funding_daily.csv."""

from __future__ import annotations

import csv
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

HL = "https://api.hyperliquid.xyz/info"
DAILY_DIR = Path("handoff/data/edge-hunt/hl-daily")
FUND_START = date(2023, 6, 1)


def ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def post(http, body, tries=8):
    for i in range(tries):
        try:
            r = http.post(HL, json=body)
            if r.status_code == 200:
                return r.json()
        except Exception:  # noqa: BLE001 - network blips: retry
            pass
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"Hyperliquid info failed: {body.get('type')} {body.get('coin', '')}")


def load_daily(http, today: date, daily_dir: Path = DAILY_DIR, pause: float = 0.1):
    """(days, coins, C, V): completed daily closes and USD volumes up to yesterday, every perp ever seen."""
    rows: dict[str, dict[str, tuple[float, float]]] = {}
    for f in sorted(daily_dir.glob("*.csv")) if daily_dir.exists() else []:
        rows[f.stem] = {r["day"]: (float(r["close"]), float(r["volume"]) * float(r["close"])) for r in csv.DictReader(f.open())}
    live = [u["name"] for u in post(http, {"type": "meta"})["universe"]]
    for coin in live:
        have = rows.setdefault(coin, {})
        d0 = (date.fromisoformat(max(have)) - timedelta(days=3)) if have else date(2023, 1, 1)
        for x in post(http, {"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d", "startTime": ms(d0),
                                                              "endTime": ms(today + timedelta(days=1))}}) or []:
            d = datetime.fromtimestamp(x["t"] / 1000, timezone.utc).date()
            have[d.isoformat()] = (float(x["c"]), float(x["v"]) * float(x["c"]))
        time.sleep(pause)
    end = today - timedelta(days=1)
    days = [date(2023, 1, 1) + timedelta(days=i) for i in range((end - date(2023, 1, 1)).days + 1)]
    ix = {d.isoformat(): i for i, d in enumerate(days)}
    coins = sorted(c for c, r in rows.items() if len(r) >= 60)
    C = np.full((len(days), len(coins)), np.nan)
    V = np.full_like(C, np.nan)
    for j, c in enumerate(coins):
        for d, (px, vol) in rows[c].items():
            if d in ix:
                C[ix[d], j], V[ix[d], j] = px, vol
    return days, coins, C, V, set(live)


def load_funding(path: Path) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    if path.exists():
        for r in csv.DictReader(path.open()):
            out.setdefault(r["coin"], {})[r["day"]] = float(r["funding"])
    return out


def save_funding(path: Path, F: dict[str, dict[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        f.write("coin,day,funding\n")
        for c in sorted(F):
            for d in sorted(F[c]):
                f.write(f"{c},{d},{F[c][d]:.8g}\n")
    tmp.replace(path)


def update_funding(http, path: Path, coins: list[str], today: date, budget_s: float = 2400.0) -> dict:
    """Bring the daily funding cache up to yesterday for `coins`. A day's sum covers the payments stamped
    in its hours (h, h+1], i.e. what a position held from the previous close to that day's close paid.
    Stops after budget_s seconds (the next run continues); returns the cache."""
    F = load_funding(path)
    t_stop = time.time() + budget_s
    end = today - timedelta(days=1)
    for coin in coins:
        have = F.setdefault(coin, {})
        last = max(have) if have else None
        if last and date.fromisoformat(last) >= end:
            continue
        d0 = date.fromisoformat(last) + timedelta(days=1) if last else FUND_START
        hourly: dict[int, float] = {}
        s = ms(d0)
        while s < ms(end + timedelta(days=1)) + 3600_000:
            part = post(http, {"type": "fundingHistory", "coin": coin, "startTime": s, "endTime": ms(end + timedelta(days=1)) + 3600_000})
            if not part:
                break
            for x in part:
                hourly[x["time"] // 3600_000] = float(x["fundingRate"])
            s = part[-1]["time"] + 1
            if len(part) < 500:
                break
        day = d0
        while day <= end:
            h0 = ms(day) // 3600_000
            have[day.isoformat()] = sum(hourly.get(h, 0.0) for h in range(h0 + 1, h0 + 25))
            day += timedelta(days=1)
        if time.time() > t_stop:
            break
    save_funding(path, F)
    return F
