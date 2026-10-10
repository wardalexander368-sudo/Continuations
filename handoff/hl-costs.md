# Hyperliquid execution costs (for autotrade and the perps strategies)

Measured from the public L2 book by `handoff/experiments/edge-hunt/perps/hl_book_costs.py`, every
2 hours by the `hl-book` Action (`handoff/data/edge-hunt/hl-book/<YYYY-MM>.jsonl`): spread and
market-order fill price at $250 / $1k / $5k / $25k / $100k for every perp with >= $500k 24h volume
(sizes past 20 levels walked through coarser books, a little conservative).

## Cost model (use this instead of a flat 20 bps)
Per side = **taker fee 4.5 bps** (base tier) + **impact**, where impact for an order of `s` USD on a
coin trading `v` USD a day is `exp(a_s + b_s * ln v)` x lognormal correction, fitted across coins and
snapshots, interpolated in ln(size), growing with sqrt(size) past $100k
(`rescore_costs.py`: `fit`, `impact_bps`). First snapshot (2026-10-10 15:52 UTC, 92 perps):

| order size | $2M/day coin | $20M/day | $200M/day |
|---|---|---|---|
| $1,000 | 3.0 bps | 1.3 | 0.6 |
| $5,000 | 6.6 | 2.4 | 0.9 |
| $25,000 | 16.4 | 5.0 | 1.5 |
| $100,000 | 49.4 | 12.3 | 3.1 |

Caveats: current books applied to past weeks through each coin's then-volume; walking the visible
book assumes no replenishment and no adverse move while filling; limit orders (maker 1.5 bps) would
be cheaper but may not fill.

## Effect on the strategies (weekly long-short %, $1 per leg; all weeks / last 26)
With the search harness (`tartar/autotrade/search.py`), funding included, capital per leg:

| rule | flat 20 bps | $1k | $10k | $100k | $1M |
|---|---|---|---|---|---|
| xs_momentum (D) | +1.02 / +1.74 | +1.35 / +2.05 | +1.32 / +2.02 | +1.20 / +1.90 | +0.62 / +1.37 |
| vol_momentum | +1.42 / +1.68 | +1.76 / +2.02 | +1.74 / +1.99 | +1.61 / +1.87 | +1.01 / +1.28 |
| search grid mean (96 rules) | +0.85 | +1.18 | +1.15 | +0.99 | +0.34 |

Up to $100k per leg the measured cost is below the registered 20 bps, so the registered tests are
conservative there; at $1M per leg impact takes 40-60% of the edge. Rerun after several days of
snapshots: `python3 handoff/experiments/edge-hunt/perps/rescore_costs.py`.
