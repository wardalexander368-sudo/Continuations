# Addendum 2026-10-11 (before the window opens 2026-10-12): secondary lines at real US venue costs

Written by the gap-review thread before any test-window candle exists. **The registered rule, cost
(0.62% per side) and success criterion are unchanged**; this adds informative lines only.

Why: the SPEC's 0.62% per side was Coinbase's old sub-$10k taker fee. On 2026-09-16 Coinbase set US
Advanced entry fees to **0.50% maker / 0.90% taker** (Coinbase's announcement as reported by
securities.io and primexbt, 2026-09-16; tiers from $10k of 30-day volume). A pass at 0.62% would not
be a pass at what a small US account pays on Coinbase. A cheaper US route exists: Alpaca's crypto
desk, 0.15% maker / 0.25% taker at tier 1 (docs.alpaca.markets/docs/crypto-fees), but with wider
spreads (measured 2026-10-11 ~03:55 UTC from Alpaca's public order book: BTC 1.7 bps, ETH 2.0, SOL
9.1, XRP 12.9, DOGE 32.6, ADA 29.5, AVAX 56.9, LINK 17.5, LTC 62.6, BCH 60.1, DOT 22.4; Coinbase's
were 0-3.6 bps).

Secondary lines, printed by `experiments/edge-hunt/patterns/pattern_forward_costs.py CACHE` (same
trades and bootstrap as the registered scorer, net of a fixed per-side cost):

| Line | Per side |
|---|---|
| Coinbase taker (0.90% + ~1 bp half spread) | 0.91% |
| Coinbase maker (assumes every resting order fills: an upper bound) | 0.50% |
| Alpaca taker (0.25% + 14 bp mean half spread) | 0.39% |

Reading: going live on either rule needs the registered pass **and** a positive line at the route
actually used. These costs are snapshots; a later re-measure may be added as a further dated note
but never replaces these lines.
