"""Hedged-JLP liquidation stress test (STRATEGY-REVIEW item 2): replay 5 years of hourly SOL/ETH/BTC (Coinbase,
2021-07 .. 2026-10) through the hedge's margin rules and count liquidations.

The registered paper test (handoff/experiments/jlp_paper.py): shorts sized to JLP's deltas (today SOL 0.437,
ETH 0.077, BTC 0.123 USD per JLP-$, so 69% / 12% / 19% of the short notional), check-ins every 4 h; at a check-in
the shorts are reset to target and margin is topped up to notional/3 when below notional/5 (withdrawn above 2/3).
Between check-ins nothing moves. A short is liquidated when, at some hour, every coin at its hourly high together
leaves equity below maintenance (SOL 2.5%, ETH 2%, BTC 1.25%), as in jlp_paper.py.

Variants: margin target (3x registered, 2x, 1.5x; top-up trigger at 60% of target, as 1/5 is of 1/3), check-in
cadence (4 h registered, 1 h), and "restore to target at every check-in".

    python3 handoff/experiments/edge-hunt/jlp_stress_fetch.py   # once
    python3 handoff/experiments/edge-hunt/jlp_stress.py         -> handoff/data/edge-hunt/jlp-stress.txt
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

IN = Path("data/jlp-stress")
OUT = Path("handoff/data/edge-hunt/jlp-stress.txt")
W = {"SOL": 0.437, "ETH": 0.077, "BTC": 0.123}
MAINT = {"SOL": 0.025, "ETH": 0.02, "BTC": 0.0125}
tot = sum(W.values())
W = {k: v / tot for k, v in W.items()}

series = {c: dict((int(t), v) for t, v in json.loads((IN / f"cb_{c}-USD_1h.json").read_text())) for c in W}
hours = sorted(set.intersection(*(set(s) for s in series.values())))
LOW, HIGH, OPEN, CLOSE = range(4)


def utc(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")


def run(lev=3.0, cadence=4, always_restore=False):
    target = 1 / lev
    trigger, cap = 0.6 * target, 2 * target
    m, p0, liq, near, min_buf = target, None, [], 0, 1.0
    for i, h in enumerate(hours):
        if p0 is None or i % cadence == 0:  # check-in at this hour's open
            if p0 is not None:
                m += sum(W[c] * (1 - series[c][h][OPEN] / p0[c]) for c in W)  # settle to now
            p0 = {c: series[c][h][OPEN] for c in W}
            if always_restore or m < trigger or m > cap:
                m = target
        hi = {c: series[c][h][HIGH] / p0[c] for c in W}
        eq = m + sum(W[c] * (1 - hi[c]) for c in W)
        req = sum(W[c] * MAINT[c] * hi[c] for c in W)
        buf = eq - req
        min_buf = min(min_buf, buf)
        if buf < 0:
            liq.append(utc(h))
            p0 = None  # liquidated: the hedge is gone; re-open fresh at the next hour
            m = target
            continue
        if buf < 0.05:
            near += 1
    return liq, near, min_buf


_ww = {}


def worst_windows(n_hours, k=8):
    """Largest basket rises (short notional-weighted, open -> later high) within n_hours."""
    if n_hours in _ww:
        return _pick(_ww[n_hours], k)
    out = []
    for i in range(len(hours) - n_hours):
        h0 = hours[i]
        p0 = {c: series[c][h0][OPEN] for c in W}
        rise = max(sum(W[c] * (series[c][hours[j]][HIGH] / p0[c] - 1) for c in W) for j in range(i, i + n_hours))
        out.append((rise, h0))
    out.sort(reverse=True)
    _ww[n_hours] = out
    return _pick(out, k)


def _pick(out, k):
    picked = []
    for r, h in out:
        if r < 0.05:
            break
        if all(abs(h - q) > 86400 * 3 for _, q in picked):
            picked.append((r, h))
        if len(picked) == k:
            break
    return picked


def main():
    years = (hours[-1] - hours[0]) / (365 * 86400)
    lines = [f"Hourly SOL/ETH/BTC, Coinbase, {utc(hours[0])} .. {utc(hours[-1])} UTC ({years:.1f} years, {len(hours)} hours).",
             f"Short weights SOL {W['SOL']:.2f} ETH {W['ETH']:.2f} BTC {W['BTC']:.2f}.", "",
             "| Margin | Check-ins | Restore every check-in | Liquidations | Hours within 5 pts of maintenance | Thinnest buffer |",
             "|---|---|---|---|---|---|"]
    for lev in (3.0, 2.0, 1.5):
        for cad in (4, 1):
            for restore in (False, True):
                liq, near, mb = run(lev, cad, restore)
                tag = " (registered)" if (lev, cad, restore) == (3.0, 4, False) else ""
                lines.append(f"| {lev:g}x{tag} | {cad} h | {'yes' if restore else 'no'} | {len(liq)}"
                             f"{(': ' + ', '.join(liq[:6]) + (' …' if len(liq) > 6 else '')) if liq else ''} | {near} | {100 * mb:+.1f}% |")
    maint = sum(W[c] * MAINT[c] for c in W)
    lines += ["", "Basket rise between check-ins that liquidates, whatever the path (equity m - x = maint * (1 + x)):"]
    for lev in (3.0, 2.0, 1.5):
        for label, m in (("at the top-up trigger", 0.6 / lev), ("just restored", 1 / lev)):
            x = (m - maint) / (1 + maint)
            n = sum(1 for r, _ in worst_windows(5, k=200) if r > x)
            lines.append(f"* {lev:g}x, margin {label} ({100 * m:.0f}% of notional): +{100 * x:.1f}%; "
                         f"separate 5-hour episodes above it since 2021: {n}")
    lines += ["", "Largest basket rises within 5 hours (one check-in gap plus the hour):"]
    lines += [f"* {utc(h)} UTC: +{100 * r:.1f}%" for r, h in worst_windows(5)]
    lines += ["", "Largest basket rises within 24 hours:"]
    lines += [f"* {utc(h)} UTC: +{100 * r:.1f}%" for r, h in worst_windows(24)]
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
