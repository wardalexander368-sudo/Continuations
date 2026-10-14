"""The adopted US live rule's start gate and cost checks, read from the Alpaca paper fills (paper only).

Rule: ``handoff/live-rule-us.md`` (v2, adopted by AJ 2026-10-12). Only ``us_capit`` is eligible. Its gate is judged
on the Alpaca paper fills of the mirror line whose orders go at the first hourly run after the signal, the timing a
live route would have: ``us_capit_fast`` (config ``alpaca_paper``). Nothing here sends an order or changes a trade;
it reads ``alpaca_fills.jsonl`` and reports. Meeting the gate does not start live trading: that still needs AJ's
go in words, a funded Alpaca live account and a live route, none of which exists.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path

from . import observation_coverage

GATE_STRATEGY = "us_capit_fast"  # Alpaca paper fills at the live route's timing (first run after the signal)
MIN_CRASH_DAYS, MIN_TRADES = 3, 8
MIN_MEAN_NET = -0.047            # backtest 10th percentile of the mean after 3 crash days (120-min entry)
MAX_MEDIAN_COST = 0.0050         # per side, gate and coin screen
STOP_COST = 0.0060               # per side: the rule's cost stop; health goes red above it
MAX_GAP_BPS = 50                 # no fill more than 0.5% from the paper book's price
MIN_COIN_FILLS = 3               # round trips before a coin's own cost is judged
HEALTH_MIN_FILLS = 5             # round trips before health judges the measured cost
WINDOW_START = 1_791_763_200     # 2026-10-12 00:00 UTC: the rule's forward window; earlier entries never count
NUMERIC = ("measured_side_cost", "alpaca_net_return", "entry_gap_bps", "exit_gap_bps")
FILL_EVENTS = {"buy", "sell", "error", "skip"}  # AlpacaMirror's trade, failure and information records
RECON_MAX_AGE = 3 * 3600  # same freshness limit as the existing paper-account health check


def _rows(root: Path) -> list[dict]:
    p = Path(root) / "alpaca_fills.jsonl"
    out = []
    for line, x in enumerate(p.read_text().splitlines() if p.exists() else [], 1):
        if not x.strip():
            continue
        try:
            r = json.loads(x)
        except ValueError:
            r = {"_invalid_fill_record": "malformed JSON", "line": line}
        if not isinstance(r, dict):
            r = {"_invalid_fill_record": "non-object JSON", "line": line}
        out.append(r)
    return out


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _completion_reason(row: dict, side: str) -> str | None:
    status = row.get("order_status")
    if status is not None and status != "filled":
        return f"{side} partial or unfilled"
    filled, requested = row.get("filled_qty"), row.get("requested_qty")
    if status != "filled" or not _finite(filled) or filled <= 0 or row.get("fill_completion") in (None, "unknown"):
        return f"{side} completion unknown"
    if side == "sell" and requested is None:
        return "sell completion unknown"
    if requested is not None:
        if not _finite(requested) or requested <= 0:
            return f"{side} requested quantity invalid"
        if not math.isclose(filled, requested, rel_tol=1e-9, abs_tol=0):
            return f"{side} filled quantity differs from request"
    if row.get("fill_completion") != "complete-requested-fill":
        return f"{side} partial or unfilled"
    return None


def _broker_time(value) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (ValueError, OverflowError, OSError):
        return None


def _timing_reason(buy: dict, sell: dict, now: float) -> str | None:
    hour = buy.get("signal_hour")
    paper_in, paper_out = buy.get("paper_at"), sell.get("paper_at")
    if not observation_coverage._integer(hour) or not all(_finite(v) for v in (paper_in, paper_out)):
        return "signal or paper execution timing unknown"
    delay = (paper_in - (hour + 1) * 3600) / 900
    if not math.isfinite(delay) or delay < 1 or not delay.is_integer():
        return "paper entry does not match signal candle timing"
    if buy.get("strategy") == GATE_STRATEGY and delay != 1:
        return "buy timing does not match fast CAPIT entry"
    if buy.get("strategy") == GATE_STRATEGY:
        from .strategies.coinbase_pattern import RULES

        if paper_out != paper_in + RULES["capit"]["hold"] * 3600:
            return "paper exit does not match registered CAPIT hold"
    if observation_coverage.latest_eligible_hour(buy["at"], int(delay)) != hour:
        return "buy observed after first eligible hourly run"
    clocks = {}
    for side, row, expected in (("buy", buy, paper_in), ("sell", sell, paper_out)):
        observed = row.get("response_observed_at")
        if not _finite(observed) or not row["at"] <= observed <= now:
            return f"{side} response observation time unknown or future"
        submitted = _broker_time(row.get("broker_submitted_at"))
        filled = _broker_time(row.get("broker_filled_at"))
        if submitted is None or filled is None:
            return f"{side} broker execution timing unknown"
        if not expected <= submitted <= filled <= observed:
            return f"{side} broker execution chronology contradictory"
        clocks[side] = (submitted, filled)
    if clocks["sell"][0] < clocks["buy"][1]:
        return "broker sell precedes matching buy fill"
    return None


def _closure_reason(buy: dict, sell: dict) -> str | None:
    """Requested-order completion alone does not close matching buy inventory."""
    fee = sell.get("configured_fee_per_side", sell.get("fee_per_side"))
    increment = sell.get("exit_qty_increment")
    if not _finite(fee) or not 0 <= fee < 1 or not _finite(increment) or increment <= 0:
        return "matching buy closure quantity evidence unknown"
    buy_fee = buy.get("configured_fee_per_side")
    if not _finite(buy_fee) or not math.isclose(buy_fee, fee, rel_tol=1e-12, abs_tol=0):
        return "matching buy configured fee unknown or contradictory"
    expected = buy["filled_qty"] * (1 - fee)
    sold = sell["filled_qty"]
    if not _finite(expected) or expected <= 0:
        return "matching buy net inventory invalid"
    if sold > expected and not math.isclose(sold, expected, rel_tol=1e-9, abs_tol=0):
        return "sell exceeds matching buy inventory"
    residual = max(0.0, expected - sold)
    if residual:
        from .alpaca import RECON_MIN_USD

        price = buy.get("price_in")
        if not _finite(price) or price <= 0:
            return "matching buy residual valuation unknown"
        if residual >= increment or residual * price > RECON_MIN_USD:
            return "matching buy inventory not closed"
    return None


def _terminal_inventory(state, now: float, after: float | None = None) -> dict:
    """Read existing full-account reconciliation; never infer a balance from fills."""
    try:
        rec = (state.get("alpaca") or {}).get("reconcile") if isinstance(state, dict) else None
        if not isinstance(rec, dict):
            return {"status": "unknown", "complete": False, "detail": "fresh paper reconciliation missing"}
        at = rec.get("checked_at")
        if not _finite(at) or at > now:
            return {"status": "unknown", "complete": False, "detail": "reconciliation time invalid or future"}
        if after is not None and at < after:
            return {"status": "unknown", "complete": False, "detail": "reconciliation predates the latest trade observation"}
        if now - at > RECON_MAX_AGE:
            return {"status": "stale", "complete": False, "detail": "paper reconciliation stale"}
        if rec.get("valuation_evidence") != "finite-inputs-checked":
            return {"status": "unknown", "complete": False, "detail": "finite holding valuation proof missing; legacy reconciliation is unknown"}
        fields = ("unconfirmed", "mismatches", "stuck_orders")
        if any(not isinstance(rec.get(k), list) for k in fields) or not isinstance(rec.get("ok"), bool):
            return {"status": "unknown", "complete": False, "detail": "paper reconciliation incomplete"}
        if rec["ok"] is not True or any(rec[k] for k in fields):
            return {"status": "unmatched", "complete": False,
                    "detail": f"{len(rec['unconfirmed'])} unconfirmed buy(s), {len(rec['mismatches'])} holding mismatch(es), {len(rec['stuck_orders'])} stuck order(s)"}
        return {"status": "reconciled", "complete": True, "detail": "fresh paper account reconciliation; no unconfirmed buys, mismatches or stuck orders"}
    except (AttributeError, TypeError, ValueError, OverflowError):
        return {"status": "unknown", "complete": False, "detail": "paper reconciliation malformed"}


def round_trips(rows: list[dict], strategy: str | None = None, rejected: list | None = None, now: float | None = None) -> list[dict]:
    """Closed Alpaca round trips, each with ``day``: its buy's UTC date. A sell counts once per position, only with a
    matching buy (same position, strategy and symbol) entered inside the forward window, chronological finite
    local-run/paper and broker times, first-run entry evidence, requested-fill completion,
    matching-buy quantity closure, and finite cost, return and gaps.
    Local run-start times are distinct from response observation and broker fill times.
    Anything else is appended to ``rejected`` (Codex review 2026-10-13: these inputs used to satisfy the gate)."""
    now = time.time() if now is None else now
    buys, rejected_buys = {}, set()
    for r in rows:
        malformed_event = isinstance(r, dict) and (not isinstance(r.get("event"), str) or not r.get("event"))
        if not isinstance(r, dict) or r.get("_invalid_fill_record") or malformed_event:
            if rejected is not None:
                rejected.append({"position": None, "why": r.get("_invalid_fill_record", "missing or invalid fill event") if isinstance(r, dict) else "non-object record",
                                 **({"line": r["line"]} if isinstance(r, dict) and "line" in r else {})})
            continue
        if r["event"] not in FILL_EVENTS:
            if rejected is not None:
                rejected.append({"position": r.get("position"), "why": "unexpected fill event", "event": r["event"]})
            continue
        if r.get("event") == "buy":
            pos, name = r.get("position"), r.get("strategy")
            if isinstance(pos, str) and pos and isinstance(name, str):
                buys.setdefault((pos, name), r)
                why = _completion_reason(r, "buy")
                if why and (strategy is None or name == strategy):
                    rejected_buys.add((pos, name))
                    if rejected is not None:
                        rejected.append({"position": pos, "why": why})
    out, seen = [], set()
    for r in rows:
        if not isinstance(r, dict) or r.get("event") != "sell":
            continue
        if strategy is not None and r.get("strategy") != strategy:
            continue
        pos = r.get("position")
        valid_pos = isinstance(pos, str) and bool(pos)
        name = r.get("strategy")
        b = buys.get((pos, name)) if valid_pos and isinstance(name, str) else None
        if b is not None and (pos, name) in rejected_buys:
            continue  # preserve the rejected buy once, including partial buys without a sell
        buy_at = (b or {}).get("at")
        sell_at = r.get("at")
        at = b.get("paper_at", buy_at) if b else None  # an explicit zero/NaN/null is evidence, never a fallback
        paper_exit = r.get("paper_at", sell_at)
        completion_why = (_completion_reason(b, "buy") or _completion_reason(r, "sell")) if b else None
        why = ("missing or invalid position" if not valid_pos else
               "duplicate sell" if pos in seen else
               "no matching buy" if b is None else
               "missing or invalid symbol" if not all(isinstance(x, str) and x for x in (b.get("symbol"), r.get("symbol"))) else
               "buy/sell symbol mismatch" if b["symbol"] != r["symbol"] else
               "missing or non-finite event time" if not all(_finite(x) for x in (buy_at, sell_at, at, paper_exit)) else
               "entered before the window" if at < WINDOW_START else
               "sell precedes buy" if sell_at < buy_at else
               "paper event time contradicts execution" if at > buy_at or paper_exit < at or paper_exit > sell_at else
               completion_why if completion_why else
               "unmeasured sell" if "measured_side_cost" not in r else
               "missing or non-finite value" if not all(_finite(r.get(k)) for k in NUMERIC) else None)
        if why is None:
            why = _timing_reason(b, r, now) or _closure_reason(b, r)
        if why:
            if rejected is not None:
                rejected.append({"position": pos, "why": why})
            continue
        seen.add(pos)
        out.append({**r, "day": time.strftime("%Y-%m-%d", time.gmtime(at))})
    return out


def coin_screen(trips: list[dict]) -> dict[str, dict]:
    """Per coin: round trips, median measured cost per side, and whether it passes (None: too few fills yet)."""
    by: dict[str, list[float]] = {}
    for r in trips:
        by.setdefault(r["symbol"], []).append(r["measured_side_cost"])
    return {s: {"n": len(c), "median_cost": _median(c), "ok": (_median(c) <= MAX_MEDIAN_COST) if len(c) >= MIN_COIN_FILLS else None}
            for s, c in sorted(by.items())}


def gate(rows: list[dict], state: dict | None = None, now: float | None = None) -> dict:
    """The paper side of the start gate (items 2-4 of the rule); item 1 (AJ, funded account, live route) is never checked here."""
    now = time.time() if now is None else now
    rejected: list[dict] = []
    trips = round_trips(rows, GATE_STRATEGY, rejected, now)
    days = sorted({r["day"] for r in trips})
    out = {"strategy": GATE_STRATEGY, "trades": len(trips), "crash_days": len(days), "coins": coin_screen(trips),
           "rejected": rejected, "paper_cost_evidence": "paper-fill-proxy" if trips else "unmeasured",
           "commission_evidence": "unknown"}
    unmet = []
    if rejected:  # unresolved records keep the gate unmet until someone looks at them
        unmet.append(f"{len(rejected)} fill record(s) rejected ({', '.join(sorted({x['why'] for x in rejected}))})")
    if len(days) < MIN_CRASH_DAYS or len(trips) < MIN_TRADES:
        unmet.append(f"{len(days)}/{MIN_CRASH_DAYS} crash days, {len(trips)}/{MIN_TRADES} trades")
    if trips:
        out["mean_net"] = sum(r["alpaca_net_return"] for r in trips) / len(trips)
        out["median_cost"] = _median([r["measured_side_cost"] for r in trips])
        out["max_gap_bps"] = max(max(abs(r["entry_gap_bps"]), abs(r["exit_gap_bps"])) for r in trips)
        if out["mean_net"] <= MIN_MEAN_NET:
            unmet.append(f"mean net {100 * out['mean_net']:+.2f}% is not above {100 * MIN_MEAN_NET:.1f}%")
        if out["median_cost"] > MAX_MEDIAN_COST:
            unmet.append(f"median cost {100 * out['median_cost']:.2f}%/side is above {100 * MAX_MEDIAN_COST:.2f}%")
        if out["max_gap_bps"] > MAX_GAP_BPS:
            unmet.append(f"a fill was {out['max_gap_bps']:.0f} bp from the paper price (max {MAX_GAP_BPS})")
    out["coverage"] = c = observation_coverage.from_state(state, GATE_STRATEGY, now)
    if c["complete"]:
        from .strategies.coinbase_pattern import COINS, END, START

        raw = state["strategies"][GATE_STRATEGY]["data"]["coverage"]
        if (set(raw["coins"]) != set(COINS) or raw["rule"] != "capit" or raw["delay_bars"] != 1 or
                raw["start_hour"] != observation_coverage._hour(START) or raw["end_hour"] != observation_coverage._hour(END) + 23):
            out["coverage"] = c = {"status": "malformed", "complete": False,
                                    "detail": "coverage does not match the fast CAPIT cohort, timing and forward window"}
    if not c["complete"]:
        unmet.append(f"Coinbase observation coverage {c['status']}: {c['detail']}")
    latest = max((r.get("response_observed_at", r.get("at")) for r in rows if isinstance(r, dict) and
                  r.get("event") in ("buy", "sell") and _finite(r.get("response_observed_at", r.get("at")))), default=None)
    out["terminal_inventory"] = terminal = _terminal_inventory(state, now, after=latest)
    if not terminal["complete"]:
        unmet.append(f"Terminal paper inventory {terminal['status']}: {terminal['detail']}")
    out["unmet"] = unmet
    out["met"] = not unmet
    return out


def health_items(root: Path) -> list[dict]:
    """Measured Alpaca paper cost against the rule: yellow above 0.50%/side, red above 0.60%, after 5 round trips."""
    try:
        return _health_items(root)
    except Exception as exc:  # noqa: BLE001 - the gate must never break the health run
        return [{"check": "Alpaca paper cost", "level": "yellow", "paper_cost_evidence": "unknown", "commission_evidence": "unknown",
                 "detail": f"paper_cost_evidence=unknown: could not read the fills: {type(exc).__name__}: {exc}"[:300]}]


def _health_items(root: Path) -> list[dict]:
    rejected = []
    trips = round_trips(_rows(root), rejected=rejected)
    evidence = "paper-fill-proxy" if len(trips) >= HEALTH_MIN_FILLS else "insufficient" if trips else "unmeasured"
    if len(trips) < HEALTH_MIN_FILLS:
        return [{"check": "Alpaca paper cost", "level": "yellow", "paper_cost_evidence": evidence, "commission_evidence": "unknown",
                 "detail": f"paper_cost_evidence={evidence}: {len(trips)} round trip(s); judged from {HEALTH_MIN_FILLS} (live rule: at most 0.50%/side)"
                           + (f"; {len(rejected)} rejected fill record(s)" if rejected else "")}]
    med = _median([r["measured_side_cost"] for r in trips[-20:]])
    level = "red" if med > STOP_COST else "yellow" if med > MAX_MEDIAN_COST else "green"
    if rejected and level == "green":
        level = "yellow"
    wide = [s for s, c in coin_screen(trips).items() if c["ok"] is False]
    return [{"check": "Alpaca paper cost", "level": level, "paper_cost_evidence": evidence, "commission_evidence": "unknown",
             "detail": f"paper_cost_evidence={evidence}: median {100 * med:.2f}%/side over the last {min(len(trips), 20)} round trips "
                       f"(live rule: gate 0.50%, stop 0.60%; assumed 0.39%; configured fee, actual commission unverified)"
                       + (f"; coins above 0.50%: {', '.join(wide)}" if wide else "")
                       + (f"; {len(rejected)} rejected fill record(s)" if rejected else "")}]


def control_line(state: dict | None) -> str:
    """Rule item 6 (needed before any scaling): ``us_capit``'s paper excess over random entries on the same coin
    within +-15 days, as scored by coinbase_pattern.py (each trade's control is priced 15 days after its signal)."""
    st = ((((state or {}).get("strategies") or {}).get("us_capit") or {}).get("verdict") or {}).get("stats") or {}
    if "excess" not in st:
        return ("Random-entry control (rule item 6, needed before scaling): no priced us_capit trades yet "
                "(each is priced 15 days after its signal; backtest +4.85%/trade [+0.98, +8.73]).")
    return (f"Random-entry control (rule item 6, needed before scaling): us_capit excess over random entries on the same coin "
            f"{100 * st['excess']:+.2f}%/trade [{100 * st['excess_lo']:+.2f}, {100 * st['excess_hi']:+.2f}] over "
            f"{st['excess_n']} paper trades (backtest +4.85% [+0.98, +8.73]).")


def report_lines(root: Path, state: dict | None = None, now: float | None = None) -> list[str]:
    """REPORT lines: where the adopted live rule's gate stands. Never raises (the hourly run must not break)."""
    try:
        return _report_lines(root, state, now) + [control_line(state)]
    except Exception as exc:  # noqa: BLE001
        return ["", f"**Live rule gate:** could not be computed ({type(exc).__name__}: {exc})"[:300] + "."]


def _report_lines(root: Path, state: dict | None = None, now: float | None = None) -> list[str]:
    if now is None:
        at = ((state or {}).get("last_run") or {}).get("at")
        now = at if _finite(at) else time.time()
    g = gate(_rows(root), state, now)
    head = (f"**Live rule gate** (`handoff/live-rule-us.md`, us_capit, judged on `{g['strategy']}`'s Alpaca paper fills): "
            f"{g['crash_days']}/{MIN_CRASH_DAYS} crash days, {g['trades']}/{MIN_TRADES} trades")
    if "mean_net" in g:
        head += f", mean net {100 * g['mean_net']:+.2f}% (bar {100 * MIN_MEAN_NET:.1f}%), median cost {100 * g['median_cost']:.2f}%/side (bar 0.50%)"
    head += ". " + ("**Paper side met**; going live still needs AJ's go, a funded Alpaca live account and a live route."
                    if g["met"] else "Not met yet. Nothing trades live.")
    coins = [f"{s} {100 * c['median_cost']:.2f}% ({c['n']}){'' if c['ok'] is not False else ' ✗'}" for s, c in g["coins"].items()]
    return ["", head] + ([f"Coin cost screen (median per side, round trips; ✗ = above 0.50%): {', '.join(coins)}."] if coins else []) + [
        f"Coinbase observation coverage ({GATE_STRATEGY}): {g['coverage']['status']}; {g['coverage']['detail']}.",
        f"Terminal paper inventory: {g['terminal_inventory']['status']}; {g['terminal_inventory']['detail']}.",
        f"Alpaca paper_cost_evidence={g['paper_cost_evidence']} ({g['trades']} paper round trips; configured fee, actual commission unverified)."] + (
        [f"Gate inputs rejected: {len(g['rejected'])} record(s); {', '.join(sorted({r['why'] for r in g['rejected']}))}."] if g["rejected"] else [])
