"""Agent-based simulation of pump.fun launches on the real bonding-curve math.

Produces PumpPortal-format messages, so the recorder's raw format, the dataset
builder, the trainer and the live agent can all be exercised without network
access. The dynamics (self-exciting hype, momentum buyers, profit taking, dev
dumps, graduation) are made up: results on simulated data say nothing about
accuracy on real tokens.
"""

from __future__ import annotations

import heapq
import json
import math
import random
from collections import deque
from pathlib import Path
from typing import Iterator

from .rawlog import event_from_message

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
CURVE_SOL = 30.0
CURVE_TOKENS = 1_073_000_000.0
GRADUATION_SOL = 115.0
SUPPLY = 1_000_000_000.0


def _address(rng: random.Random, suffix: str = "") -> str:
    body = "".join(rng.choice(_B58) for _ in range(44 - len(suffix)))
    return body + suffix


class BondingCurve:
    def __init__(self) -> None:
        self.vsol = CURVE_SOL
        self.vtok = CURVE_TOKENS
        self.k = self.vsol * self.vtok

    @property
    def price(self) -> float:
        return self.vsol / self.vtok

    def buy(self, sol: float) -> float:
        self.vsol += sol
        new_vtok = self.k / self.vsol
        tokens = self.vtok - new_vtok
        self.vtok = new_vtok
        return tokens

    def sell(self, tokens: float) -> float:
        self.vtok += tokens
        new_vsol = self.k / self.vtok
        sol = self.vsol - new_vsol
        self.vsol = new_vsol
        return sol


def _message(kind: str, mint: str, trader: str, sol: float, tokens: float, curve: BondingCurve, **extra) -> dict:
    return {
        "signature": "",
        "mint": mint,
        "traderPublicKey": trader,
        "txType": kind,
        "tokenAmount": tokens,
        "solAmount": sol,
        "vTokensInBondingCurve": curve.vtok,
        "vSolInBondingCurve": curve.vsol,
        "marketCapSol": curve.price * SUPPLY,
        "pool": "pump",
        **extra,
    }


def simulate_token(rng: random.Random, created: float, max_minutes: float = 60.0, lively: bool = False) -> Iterator[tuple[float, dict]]:
    """Yield (time, PumpPortal message) for one token's life, starting with its creation."""
    curve = BondingCurve()
    mint, creator = _address(rng, "pump"), _address(rng)
    symbol = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(rng.randint(3, 6)))
    dev_sol = rng.uniform(0.2, 3.0)
    holdings = {creator: curve.buy(dev_sol)}
    yield created, _message("create", mint, creator, dev_sol, holdings[creator], curve, name=symbol.title(), symbol=symbol)

    quality = rng.lognormvariate(0.8 if lively else 0.0, 0.7)
    tau = rng.uniform(15, 40) * 60 if lively else rng.uniform(2, 20) * 60  # hype half-life scale (s)
    hype = 1.0 + rng.expovariate(1.0)  # snipers make the first seconds busy
    base_rate = 0.25 * quality  # trades per second at hype 1
    dev_dump = created + rng.expovariate(1 / (12 * 60)) if rng.random() < 0.55 else math.inf
    cost_sol, cost_tok = dev_sol, holdings[creator]
    recent: deque[tuple[float, float]] = deque()
    wallets = [creator]
    t = created
    end = created + max_minutes * 60
    while True:
        rate = base_rate * hype
        if rate < 0.003:
            return  # dead: nobody trades any more
        dt = rng.expovariate(rate)
        t += dt
        if t >= end:
            return
        hype = 1.0 + (hype - 1.0) * math.exp(-dt / 30) if hype > 1 else hype
        hype *= math.exp(-dt / tau)
        while recent and recent[0][0] < t - 30:
            recent.popleft()
        momentum = math.log(curve.price / recent[0][1]) if recent else 0.0
        profit = math.log(curve.price / (cost_sol / cost_tok))

        if t >= dev_dump and holdings.get(creator, 0) > 0:
            tokens = holdings.pop(creator)
            sol = curve.sell(tokens)
            hype *= rng.uniform(0.1, 0.5)
            dev_dump = math.inf
            yield t, _message("sell", mint, creator, sol, tokens, curve)
            recent.append((t, curve.price))
            continue

        p_buy = 1 / (1 + math.exp(-(0.25 + 6.0 * momentum - 1.2 * max(profit, 0.0) + rng.gauss(0, 0.5))))
        sellers = [w for w in wallets if holdings.get(w, 0) > 0 and w != creator]
        if rng.random() < p_buy or not sellers:
            sol = rng.lognormvariate(math.log(0.25), 1.1) * (1 + 0.3 * min(hype, 5))
            wallet = _address(rng) if rng.random() < 0.7 or len(wallets) < 3 else rng.choice(wallets)
            if wallet not in holdings:
                wallets.append(wallet)
            tokens = curve.buy(sol)
            holdings[wallet] = holdings.get(wallet, 0.0) + tokens
            cost_sol, cost_tok = cost_sol + sol, cost_tok + tokens
            hype += 0.04 * min(sol, 5.0)
            kind = "buy"
        else:
            wallet = rng.choice(sellers)
            tokens = holdings[wallet] * rng.choice((0.25, 0.5, 1.0, 1.0))
            holdings[wallet] -= tokens
            sol = curve.sell(tokens)
            hype = max(hype - 0.03 * min(sol, 5.0), 0.05)
            kind = "sell"
        yield t, _message(kind, mint, wallet, sol, tokens, curve)
        recent.append((t, curve.price))
        if curve.vsol >= GRADUATION_SOL:
            yield t, {"txType": "migrate", "mint": mint, "signature": "", "pool": "pump"}
            return


def simulate_raw(
    out_dir: str | Path,
    tokens: int,
    *,
    seed: int = 0,
    start: float = 1_760_000_000.0,
    launch_every: float = 20.0,
    track_minutes: float = 60.0,
) -> Path:
    """Write a raw log (recorder format) for `tokens` simulated launches. Returns the file path."""
    rng = random.Random(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    streams = []
    t = start
    for i in range(tokens):
        t += rng.expovariate(1 / launch_every)
        streams.append(simulate_token(random.Random(rng.getrandbits(64)), t, track_minutes))
    path = out / "simulated.jsonl"
    last = start
    with open(path, "w") as fh:

        def write(event: dict) -> None:
            fh.write(json.dumps(event, separators=(",", ":")) + "\n")

        write({"e": "session", "t": start, "state": "connected", "simulated": True})
        tracked: dict[str, float] = {}
        for ts, msg in heapq.merge(*streams, key=lambda item: item[0]):
            event = event_from_message(msg, ts)
            if event is None:
                continue
            write(event)
            last = max(last, ts)
            if event["e"] == "create":
                tracked[event["mint"]] = ts
                write({"e": "track", "t": ts, "mint": event["mint"]})
            elif event["e"] == "migrate":
                write({"e": "untrack", "t": ts, "mint": event["mint"], "reason": "migrated"})
                tracked.pop(event["mint"], None)
        for mint, created in tracked.items():
            write({"e": "untrack", "t": created + track_minutes * 60, "mint": mint, "reason": "age"})
        write({"e": "session", "t": max(last, t) + track_minutes * 60, "state": "stopped"})
    return path
