"""Scam detection: who holds and trades a token, what its mint allows, and its creator's record.

Three layers, combined into a risk level (ok / caution / danger / scam) with
reasons:

* behaviour, from the token's own trades (same code live and in training, so
  these also feed the model): creator dumping, sniped/bundled launch, holder
  concentration, wash trading, non-standard bonding curve, collapse from peak
* the mint, from Solana RPC: mint/freeze authority, dangerous Token-2022
  extensions (permanent delegate, transfer hook, fees, pausable, frozen by
  default, non-transferable)
* reputation: RugCheck's report (risks, insider networks, rugged flag, LP
  locks), and the creator's history in recorded data (serial launches, past
  rugs, copycat names/metadata)
"""

from __future__ import annotations

import asyncio
import math
import os
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .candles import Tick

SNIPE_SECONDS = 5.0  # buys this soon after launch count as sniped / bundled
ROUND_TRIP_SECONDS = 120.0  # a sell this soon after the same wallet's buy is a round trip
RPC_HTTP = os.environ.get("SOLANA_RPC_HTTP", "https://api.mainnet-beta.solana.com")
RUGCHECK = "https://api.rugcheck.xyz/v1"
STANDARD_VIRTUAL_SOL = 30.0

LEVELS = ("unknown", "ok", "caution", "danger", "scam")
NAN = float("nan")

RISK_FEATURES = (
    "top10_share",  # share of trader-held tokens in the 10 biggest wallets
    "log_holders",  # wallets holding a positive balance
    "creator_share",  # creator's share of trader-held tokens
    "sniper_share",  # share of bought tokens bought in the first seconds by non-creators
    "wash_share",  # share of recent trades that are quick round trips
    "trades_per_wallet",  # recent trades per distinct wallet
    "nonstandard_curve",  # 1 if the bonding curve has non-standard virtual reserves
)


class WalletTracker:
    """Positions and behaviour of every wallet trading one token, built from its trades."""

    def __init__(self, launched_at: float | None = None, recent: int = 200):
        self.launched_at = launched_at
        self.balances: dict[str, float] = defaultdict(float)
        self._last_buy: dict[str, float] = {}
        self._recent: deque[tuple[str, bool]] = deque(maxlen=recent)
        self.creator: str | None = None
        self.creator_bought = 0.0  # tokens
        self.creator_sold = 0.0  # tokens
        self.bought_tokens = 0.0
        self.sniped_tokens = 0.0
        self.trades = 0
        self.curve_offset: float | None = None
        self.peak = 0.0
        self.price = 0.0

    def update(self, tick: Tick) -> None:
        if tick.price > 0:
            self.price = tick.price
            self.peak = max(self.peak, tick.price)
        if not tick.trader or tick.trades != 1:
            return  # price observation without a single identified trade
        wallet, buy = tick.trader, tick.buys > 0
        self.trades += 1
        round_trip = False
        if buy:
            self.balances[wallet] += tick.tokens
            self.bought_tokens += tick.tokens
            self._last_buy[wallet] = tick.ts
            if self.launched_at is not None and not tick.creator and tick.ts - self.launched_at <= SNIPE_SECONDS:
                self.sniped_tokens += tick.tokens
        else:
            self.balances[wallet] -= tick.tokens
            bought_at = self._last_buy.get(wallet)
            round_trip = bought_at is not None and tick.ts - bought_at <= ROUND_TRIP_SECONDS
        if tick.creator:
            self.creator = wallet
            if buy:
                self.creator_bought += tick.tokens
            else:
                self.creator_sold += tick.tokens
        self._recent.append((wallet, round_trip))
        if tick.virtual_sol:
            self.curve_offset = tick.virtual_sol - tick.liquidity

    def snapshot(self) -> dict[str, float]:
        held = sorted((b for b in self.balances.values() if b > 1e-9), reverse=True)
        total = sum(held)
        recent = list(self._recent)
        wallets = {w for w, _ in recent}
        out = {
            "top10_share": sum(held[:10]) / total if total > 0 else NAN,
            "log_holders": math.log1p(len(held)),
            "creator_share": (max(self.balances.get(self.creator, 0.0), 0.0) / total) if self.creator and total > 0 else NAN,
            "sniper_share": self.sniped_tokens / self.bought_tokens if self.launched_at is not None and self.bought_tokens > 0 else NAN,
            "wash_share": sum(rt for _, rt in recent) / len(recent) if len(recent) >= 10 else NAN,
            "trades_per_wallet": len(recent) / len(wallets) if wallets else NAN,
            "nonstandard_curve": NAN if self.curve_offset is None else float(abs(self.curve_offset - STANDARD_VIRTUAL_SOL) > 0.5),
        }
        return out

    @property
    def holders(self) -> int:
        return sum(1 for b in self.balances.values() if b > 1e-9)

    @property
    def creator_sold_share(self) -> float | None:
        """Share of the tokens the creator bought that they have sold (capped at 1)."""
        return min(self.creator_sold / self.creator_bought, 1.0) if self.creator_bought > 0 else None

    @property
    def drawdown(self) -> float | None:
        return self.price / self.peak - 1.0 if self.peak > 0 else None


@dataclass(frozen=True)
class Flag:
    code: str
    severity: str  # caution | danger | scam
    message: str


@dataclass
class ScamReport:
    level: str = "unknown"
    flags: list[Flag] = field(default_factory=list)

    @property
    def is_scam_or_danger(self) -> bool:
        return self.level in ("danger", "scam")

    def summary(self, limit: int = 3) -> str:
        if not self.flags:
            return {"unknown": "not enough data yet", "ok": "no red flags"}.get(self.level, "")
        order = {"scam": 0, "danger": 1, "caution": 2}
        return " · ".join(f.message for f in sorted(self.flags, key=lambda f: order[f.severity])[:limit])

    def to_dict(self) -> dict:
        return {"level": self.level, "flags": [{"code": f.code, "severity": f.severity, "message": f.message} for f in self.flags]}


@dataclass
class StaticReport:
    """Mint checks and RugCheck's report, fetched once per token (and refreshed occasionally)."""

    mint_authority: str | None = None
    freeze_authority: str | None = None
    token_program: str | None = None
    extensions: dict[str, Any] = field(default_factory=dict)
    rugcheck: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    fetched_at: float = 0.0


@dataclass
class CreatorRecord:
    tokens: dict[str, bool] = field(default_factory=dict)  # mint -> rugged
    recent: set[str] = field(default_factory=set)  # mints launched in the index's last 24h

    def excluding(self, mint: str | None) -> tuple[int, int, int]:
        """(launches, rugs, launches in the last day), leaving out `mint`."""
        others = {m: r for m, r in self.tokens.items() if m != mint}
        return len(others), sum(others.values()), len(self.recent - {mint})


class CreatorIndex:
    """Creators' launch and rug history, plus recent names/metadata, from recorded raw logs."""

    def __init__(self) -> None:
        self.creators: dict[str, CreatorRecord] = defaultdict(CreatorRecord)
        self.names: Counter[str] = Counter()
        self.uris: Counter[str] = Counter()
        self.mint_creator: dict[str, str] = {}

    @classmethod
    def from_raw(cls, raw_dir: str | Path, *, rug_drop: float = 0.8) -> CreatorIndex:
        """Scan recorded launches. A token counts as rugged if its creator sold at least half
        of what they bought and the price ended down `rug_drop` or more from its peak."""
        from .data.rawlog import event_price, raw_files, read_events

        index = cls()
        files = raw_files(raw_dir) if Path(raw_dir).exists() else []
        stats: dict[str, dict] = {}
        latest = 0.0
        for event in read_events(files):
            latest = max(latest, event["t"])
            mint = event.get("mint")
            if event["e"] == "create":
                creator = event.get("creator") or ""
                index.mint_creator[mint] = creator
                stats[mint] = {"creator": creator, "t": event["t"], "bought": event.get("sol") or 0.0, "sold": 0.0, "peak": event_price(event) or 0.0, "last": event_price(event) or 0.0}
                index.names[_norm(event.get("name"), event.get("symbol"))] += 1
                if event.get("uri"):
                    index.uris[event["uri"]] += 1
            elif event["e"] == "trade" and mint in stats:
                s = stats[mint]
                price = event_price(event)
                if price:
                    s["peak"] = max(s["peak"], price)
                    s["last"] = price
                if event.get("trader") == s["creator"]:
                    s["bought" if event.get("side") == "b" else "sold"] += event.get("sol") or 0.0
        for mint, s in stats.items():
            record = index.creators[s["creator"]]
            dumped = s["bought"] > 0 and s["sold"] >= 0.5 * s["bought"]
            crashed = s["peak"] > 0 and s["last"] <= (1 - rug_drop) * s["peak"]
            record.tokens[mint] = dumped and crashed
            if latest - s["t"] <= 86400:
                record.recent.add(mint)
        return index

    def note_launch(self, creator: str, name: str = "", symbol: str = "", uri: str = "", mint: str = "") -> None:
        """Count a launch seen live (e.g. on the chain stream)."""
        if creator and mint and mint not in self.mint_creator:
            record = self.creators[creator]
            record.tokens.setdefault(mint, False)
            record.recent.add(mint)
            self.mint_creator[mint] = creator
            self.names[_norm(name, symbol)] += 1
            if uri:
                self.uris[uri] += 1


def _norm(name: str | None, symbol: str | None) -> str:
    return f"{(name or '').strip().lower()}|{(symbol or '').strip().lower()}"


def assess(
    tracker: WalletTracker | None = None,
    static: StaticReport | None = None,
    creators: CreatorIndex | None = None,
    *,
    mint: str | None = None,
    creator: str | None = None,
    name: str = "",
    symbol: str = "",
    uri: str = "",
) -> ScamReport:
    """Combine every available signal into a risk level with reasons."""
    flags: list[Flag] = []

    def flag(code: str, severity: str, message: str) -> None:
        flags.append(Flag(code, severity, message))

    evidence = False
    if tracker is not None and tracker.trades >= 3:
        evidence = True
        snap = tracker.snapshot()
        sold = tracker.creator_sold_share
        if sold is not None and sold >= 0.9:
            flag("dev_dumped", "danger", f"creator sold {sold:.0%} of their tokens")
        elif sold is not None and sold >= 0.5:
            flag("dev_selling", "caution", f"creator sold {sold:.0%} of their tokens")
        drawdown = tracker.drawdown
        if drawdown is not None and drawdown <= -0.9 and tracker.trades >= 10:
            flag("collapsed", "scam", f"price {drawdown:.0%} from its peak")
        top10, holders = snap["top10_share"], tracker.holders
        if not math.isnan(top10) and holders >= 15:
            if top10 >= 0.7:
                flag("concentrated", "danger", f"top 10 wallets hold {top10:.0%}")
            elif top10 >= 0.5:
                flag("concentrated", "caution", f"top 10 wallets hold {top10:.0%}")
        creator_share = snap["creator_share"]
        if not math.isnan(creator_share) and creator_share >= 0.2:
            flag("dev_bag", "danger" if creator_share >= 0.4 else "caution", f"creator holds {creator_share:.0%}")
        sniped = snap["sniper_share"]
        if not math.isnan(sniped):
            if sniped >= 0.5:
                flag("sniped", "danger", f"{sniped:.0%} of buys sniped in the first {SNIPE_SECONDS:.0f}s (likely bundled)")
            elif sniped >= 0.25:
                flag("sniped", "caution", f"{sniped:.0%} of buys sniped in the first {SNIPE_SECONDS:.0f}s")
        wash, per_wallet = snap["wash_share"], snap["trades_per_wallet"]
        if not math.isnan(wash) and wash >= 0.5:
            flag("wash_trading", "caution", f"{wash:.0%} of recent trades are quick round trips")
        if not math.isnan(per_wallet) and per_wallet >= 8 and len(tracker._recent) >= 40:
            flag("few_traders", "caution", f"{per_wallet:.0f} trades per wallet: activity from a handful of wallets")
        if snap["nonstandard_curve"] == 1.0:
            flag("odd_curve", "caution", "non-standard bonding curve")

    if static is not None:
        evidence = evidence or static.token_program is not None or static.rugcheck is not None
        if static.mint_authority:
            flag("mint_authority", "danger", "mint authority not revoked: supply can be inflated")
        if static.freeze_authority:
            flag("freeze_authority", "danger", "freeze authority not revoked: wallets can be frozen (honeypot risk)")
        ext = static.extensions
        if ext.get("permanentDelegate"):
            flag("permanent_delegate", "scam", "permanent delegate: tokens can be taken from any wallet")
        if ext.get("nonTransferable"):
            flag("non_transferable", "scam", "token cannot be transferred or sold")
        if ext.get("transferHook"):
            flag("transfer_hook", "danger", "transfer hook: custom code runs on every transfer")
        if ext.get("pausableConfig"):
            flag("pausable", "danger", "transfers can be paused")
        state = ext.get("defaultAccountState")
        if state and "frozen" in str(state).lower():
            flag("frozen_default", "danger", "new token accounts start frozen")
        fee_bps = _transfer_fee_bps(ext.get("transferFeeConfig"))
        if fee_bps is not None and fee_bps > 0:
            flag("transfer_fee", "danger" if fee_bps > 500 else "caution", f"{fee_bps / 100:g}% transfer fee")
        rc = static.rugcheck
        if rc:
            if rc.get("rugged"):
                flag("rugcheck_rugged", "scam", "RugCheck marks it rugged")
            for risk in rc.get("risks") or []:
                level = str(risk.get("level", "")).lower()
                if level == "danger":
                    flag("rugcheck_" + _slug(risk.get("name")), "danger", f"RugCheck: {risk.get('name')}")
                elif level == "warn" and _slug(risk.get("name")) != "mutable_metadata":
                    flag("rugcheck_" + _slug(risk.get("name")), "caution", f"RugCheck: {risk.get('name')}")
            insiders = rc.get("graphInsidersDetected") or 0
            if insiders:
                flag("insiders", "danger" if insiders >= 5 else "caution", f"{insiders} insider wallets linked to each other")
            top10 = rugcheck_top10(rc)
            if top10 is not None and top10 >= 0.5 and (rc.get("totalHolders") or 0) >= 15:
                flag("rugcheck_concentrated", "caution", f"top 10 holders own {top10:.0%} (on-chain)")

    if creators is not None:
        who = creator or (tracker.creator if tracker else None)
        record = creators.creators.get(who) if who else None
        if record is not None:
            evidence = True
            launches, rugs, recent = record.excluding(mint)
            if rugs >= 1:
                flag("serial_rugger", "danger", f"creator rugged {rugs} other recorded token(s)")
            if recent >= 4:
                flag("serial_launcher", "danger", f"creator launched {recent} other tokens in a day")
            elif launches >= 2:
                flag("repeat_creator", "caution", f"creator launched {launches} other tokens")
        # The token itself is counted in the index when it was recorded or seen live.
        own = 1 if mint and mint in creators.mint_creator else 0
        copies = creators.names.get(_norm(name, symbol), 0) - own if (name or symbol) else 0
        if uri and creators.uris.get(uri, 0) - own >= 1:
            flag("copycat", "caution", "same metadata as other launches (copycat/spam)")
        elif copies >= 2:
            flag("copycat", "caution", f"{copies} other launches share this name")

    order = {"caution": 2, "danger": 3, "scam": 4}
    if flags:
        level = LEVELS[max(order[f.severity] for f in flags)]
    else:
        level = "ok" if evidence else "unknown"
    return ScamReport(level, flags)


def _slug(text: Any) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(text or "").lower()).strip("_")


def _transfer_fee_bps(config: Any) -> int | None:
    if not isinstance(config, dict):
        return None
    for key in ("newerTransferFee", "olderTransferFee"):
        fee = config.get(key)
        if isinstance(fee, dict) and fee.get("transferFeeBasisPoints") is not None:
            return int(fee["transferFeeBasisPoints"])
    return None


def rugcheck_top10(report: dict) -> float | None:
    """Top-10 holders' share, leaving out pools, bonding curves and lockers RugCheck knows."""
    known = set((report.get("knownAccounts") or {}).keys())
    for market in report.get("markets") or []:
        known.add(market.get("pubkey"))
        for key in ("liquidityA", "liquidityB"):
            if market.get(key):
                known.add(market[key])
    holders = [h for h in report.get("topHolders") or [] if h.get("owner") not in known and h.get("address") not in known]
    if not holders:
        return None
    return sum(float(h.get("pct") or 0.0) for h in holders[:10]) / 100.0


async def static_checks(mint: str, *, rugcheck: bool = True, client: httpx.AsyncClient | None = None) -> StaticReport:
    """Mint account (RPC) and RugCheck report. Failures are recorded, never raised."""
    report = StaticReport(fetched_at=time.time())
    own = client is None
    client = client or httpx.AsyncClient(timeout=30, headers={"User-Agent": "tartar"})
    try:
        try:
            r = await client.post(RPC_HTTP, json={"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo", "params": [mint, {"encoding": "jsonParsed"}]})
            value = (r.json().get("result") or {}).get("value") or {}
            info = ((value.get("data") or {}).get("parsed") or {}).get("info") or {}
            report.token_program = value.get("owner")
            report.mint_authority = info.get("mintAuthority")
            report.freeze_authority = info.get("freezeAuthority")
            report.extensions = {e.get("extension"): e.get("state", True) for e in info.get("extensions") or []}
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            report.errors.append(f"mint lookup failed: {exc.__class__.__name__}")
        if rugcheck:
            try:
                r = await client.get(f"{RUGCHECK}/tokens/{mint}/report")
                if r.status_code == 200:
                    report.rugcheck = r.json()
                    ext = report.rugcheck.get("token_extensions") or {}
                    for key in ("permanentDelegate", "transferHook", "pausableConfig", "defaultAccountState", "transferFeeConfig"):
                        if ext.get(key) and key not in report.extensions:
                            report.extensions[key] = ext[key]
                    if ext.get("nonTransferable"):
                        report.extensions["nonTransferable"] = True
                else:
                    # Some tokens have no full report; the summary still has score, risks and LP locks.
                    summary = await client.get(f"{RUGCHECK}/tokens/{mint}/report/summary")
                    if summary.status_code == 200:
                        report.rugcheck = summary.json()
                    elif r.status_code not in (400, 404):
                        report.errors.append(f"RugCheck HTTP {r.status_code}")
                    # 400/404: RugCheck has not indexed the token yet (normal for new launches)
            except (httpx.HTTPError, ValueError) as exc:
                try:
                    summary = await client.get(f"{RUGCHECK}/tokens/{mint}/report/summary")
                    if summary.status_code == 200:
                        report.rugcheck = summary.json()
                    else:
                        report.errors.append(f"RugCheck failed: {exc.__class__.__name__}")
                except (httpx.HTTPError, ValueError):
                    report.errors.append(f"RugCheck failed: {exc.__class__.__name__}")
    finally:
        if own:
            await client.aclose()
    return report


async def static_checks_many(mints: list[str], spacing: float = 1.0) -> dict[str, StaticReport]:
    out = {}
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "tartar"}) as client:
        for mint in mints:
            out[mint] = await static_checks(mint, client=client)
            await asyncio.sleep(spacing)
    return out
