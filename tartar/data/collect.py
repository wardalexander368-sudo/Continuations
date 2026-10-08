"""Collect OHLCV histories of recently launched Solana pools from GeckoTerminal."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..candles import Candle
from ..feeds.geckoterminal import BASE_URL, GeckoTerminal
from ..feeds.http import ApiError, JsonClient


def _created_ts(created_at: str | None) -> float | None:
    if not created_at:
        return None
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


async def collect_ohlcv(
    out_dir: str | Path,
    timeframe: int,
    *,
    pages: int = 10,
    limit: int = 1000,
    interval: float = 6.5,
    gecko: GeckoTerminal | None = None,
    progress: Callable[[str], None] = lambda message: None,
) -> int:
    """Save `<out_dir>/<token>.json` for each new pool's base token. Returns files written.

    The free API's quota is tight (nominally 30 requests a minute, often less in
    practice), so requests are spaced `interval` seconds apart.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    gecko = gecko or GeckoTerminal(JsonClient(BASE_URL, min_interval=interval, retries=4))
    written = 0
    try:
        for page in range(1, pages + 1):
            try:
                pools = await gecko.new_pools(page)
            except ApiError as exc:
                progress(f"page {page}: {exc}")
                continue
            for pool in pools:
                path = out / f"{pool.base_token}.json"
                if path.exists() or not pool.base_token:
                    continue
                try:
                    candles = await gecko.ohlcv(pool.address, timeframe, token=pool.base_token, currency="usd", limit=limit)
                except ApiError as exc:
                    progress(f"{pool.base_symbol}: {exc}")
                    continue
                if len(candles) < 10:
                    continue
                record = {
                    "token": pool.base_token,
                    "pool": pool.address,
                    "symbol": pool.base_symbol,
                    "dex": pool.dex,
                    "created_at": _created_ts(pool.created_at),
                    "timeframe": timeframe,
                    "currency": "usd",
                    "candles": [[c.start, c.open, c.high, c.low, c.close, c.volume] for c in candles],
                }
                path.write_text(json.dumps(record))
                written += 1
                progress(f"{pool.base_symbol}: {len(candles)} candles")
    finally:
        await gecko.aclose()
    return written


def load_ohlcv_file(path: str | Path) -> tuple[dict, list[Candle]]:
    record = json.loads(Path(path).read_text())
    candles = [Candle(int(s), o, max(h, o, c), min(l, o, c), c, volume=v, trades=None) for s, o, h, l, c, v in record["candles"]]
    return record, candles
