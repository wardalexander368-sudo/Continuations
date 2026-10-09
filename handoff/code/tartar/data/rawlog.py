"""Raw event log of pump.fun launches and trades (JSON lines, hourly files, gzipped when done).

Event types (short keys keep files small):

    {"e": "create",  "t": ts, "mint", "creator", "name", "symbol", "sol", "tok", "vsol", "vtok", "rsol"?, "quote"?}
    {"e": "trade",   "t": ts, "mint", "side": "b"|"s", "trader", "sol", "tok", "vsol", "vtok", "rsol"?,
                     "quote"?, "qamt"?, "vq"?, "rq"?}
    {"e": "migrate", "t": ts, "mint"}                      # graduated off the bonding curve
    {"e": "track",   "t": ts, "mint"}                      # trades are being recorded from here
    {"e": "untrack", "t": ts, "mint", "reason"}            # ...until here
    {"e": "session", "t": ts, "state": "connected"|"disconnected"|"stopped"}

"quote" (since 2026-10-09) marks a curve priced in another token (USDC, a tokenized
stock, another pump coin...): its trades have no SOL fields, only raw quote amounts
("qamt", "vq", "rq" in base units of the quote mint) and token fields, so nothing
SOL-denominated reads them. Older files dropped those trades entirely.

create, trade and migrate events from the chain recorder also carry "slot": the
Solana slot of the transaction (since 2026-10-09; absent in older files and from
PumpPortal). Slots order events across transactions and measure how many blocks
after a launch each trade landed (~0.4 s per slot).

Trades are only complete while the recorder was connected, so the dataset
builder cuts each token's history at the first disconnection.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Iterator


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def event_from_message(msg: dict, t: float) -> dict | None:
    """Convert a PumpPortal websocket message into a raw log event."""
    kind = msg.get("txType")
    mint = msg.get("mint")
    if not mint:
        return None
    slot = msg.get("slot")
    if kind in ("migrate", "migration"):
        return {"e": "migrate", "t": t, "mint": mint} | ({"slot": int(slot)} if slot is not None else {})
    if kind not in ("create", "buy", "sell"):
        return None
    event = {
        "e": "create" if kind == "create" else "trade",
        "t": t,
        "mint": mint,
        "sol": _num(msg.get("solAmount")),
        "tok": _num(msg.get("tokenAmount")),
        "vsol": _num(msg.get("vSolInBondingCurve")),
        "vtok": _num(msg.get("vTokensInBondingCurve")),
    }
    if msg.get("realSolReserves") is not None:
        event["rsol"] = _num(msg.get("realSolReserves"))
    if kind == "create":
        if event["tok"] is None:
            event["tok"] = _num(msg.get("initialBuy"))  # PumpPortal names the dev's token amount this way
        event.update(creator=msg.get("traderPublicKey") or "", name=msg.get("name") or "", symbol=msg.get("symbol") or "", uri=msg.get("uri") or "")
    else:
        event.update(side="b" if kind == "buy" else "s", trader=msg.get("traderPublicKey") or "")
    if msg.get("quote"):
        event["quote"] = msg["quote"]
        for key, src in (("qamt", "quoteAmount"), ("vq", "vQuote"), ("rq", "rQuote")):
            if msg.get(src) is not None:
                event[key] = int(msg[src])
    if slot is not None:
        event["slot"] = int(slot)
    return event


def event_price(event: dict) -> float | None:
    vsol, vtok = event.get("vsol"), event.get("vtok")
    if vsol and vtok and vsol > 0 and vtok > 0:
        return vsol / vtok
    sol, tok = event.get("sol"), event.get("tok")
    if sol and tok and sol > 0 and tok > 0:
        return sol / tok
    return None


class RawWriter:
    """Appends events to `<dir>/<YYYYmmdd-HH>.jsonl`, gzipping each hour's file once it is done."""

    def __init__(self, directory: str | Path, clock: Callable[[], float] = time.time):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._path: Path | None = None
        self._fh = None
        self.events = 0

    def _target(self) -> Path:
        return self.directory / (time.strftime("%Y%m%d-%H", time.gmtime(self._clock())) + ".jsonl")

    def write(self, event: dict) -> None:
        path = self._target()
        if path != self._path:
            self._rotate(path)
        self._fh.write(json.dumps(event, separators=(",", ":")) + "\n")
        self.events += 1

    def flush(self) -> None:
        if self._fh is not None:
            self._fh.flush()

    def _rotate(self, path: Path | None) -> None:
        if self._fh is not None:
            self._fh.close()
            _compress(self._path)
        self._path = path
        self._fh = open(path, "a") if path is not None else None

    def close(self) -> None:
        self._rotate(None)


def _compress(path: Path) -> None:
    target = path.with_suffix(".jsonl.gz")
    mode = "ab" if target.exists() else "wb"
    with open(path, "rb") as src, gzip.open(target, mode) as dst:
        shutil.copyfileobj(src, dst)
    os.remove(path)


def read_events(paths: list[Path]) -> Iterator[dict]:
    """Events from .jsonl and .jsonl.gz files (malformed lines are skipped)."""
    for path in sorted(paths):
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt") as fh:
            for line in fh:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict) and "e" in event and "t" in event:
                    yield event


def raw_files(directory: str | Path) -> list[Path]:
    directory = Path(directory)
    return sorted([*directory.glob("*.jsonl"), *directory.glob("*.jsonl.gz")])
