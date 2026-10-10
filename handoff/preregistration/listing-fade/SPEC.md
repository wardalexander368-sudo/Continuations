# Pre-registration: shorting newly listed Hyperliquid perps (edge hunt round 2, F1)

Registered 2026-10-09 ~23:30 UTC, **before any new-listing price, funding or listing date was
read** (only the size of Hyperliquid's universe, 234 perps of which 56 delisted, was checked).
D/D3 used daily candles of every perp but required 60 days of history, so no rule so far has
looked at a perp's first weeks. Script, written after this commit:
`handoff/experiments/edge-hunt/listings/listing_fade.py`. Paper only.

## Why (the payer)
New perps list on Hyperliquid when a token is hot. Late buyers and leveraged longs pay a premium
to get exposure; that premium tends to fade as supply unlocks and attention moves on, and crowded
longs pay shorts funding meanwhile. Costs on Hyperliquid are small next to a fade of several
percent. The risk is a short squeeze.

## Rule family (6 rules, fixed)
* **Universe:** every Hyperliquid perp, delisted ones included. Listing day `L` = the date of its
  first daily candle. Only `L >= 2023-09-01` (earlier first candles are the venue's initial batch,
  not new listings).
* **Trade:** short at the close of day `L + k`, cover at the close of day `L + k + H`, fixed
  notional, no stop. `k` in {1, 3} (entry delay), `H` in {7, 14, 28} days.
  If the perp stops trading before the exit (delisted), cover at its last close.
* **Costs:** 0.20% per side (taker 0.045% plus the wider spread and impact of new listings);
  funding: the sum of Hyperliquid's hourly rates over the holding days, shorts receive positive
  rates. If a coin has no funding history, funding is 0 and the count is reported.
* **Secondary (reported, not a criterion):** the same short hedged with a long of equal notional
  in BTC (removes the market's direction).

## Splits and choice (by listing day)
* train: `L < 2025-01-01`; validation: 2025-01-01 .. 2025-12-31; test: `L >= 2026-01-01` and the
  exit on or before 2026-10-08.
* Choose the rule with the best train mean net. Read validation for that rule only. **Read test
  only if the chosen rule's validation mean is > 0**, once, for that rule only.
* Intervals: 90%, bootstrap by calendar month of `L` (listings in one month share the market),
  5,000 draws, seed 0.

## Criterion for a forward test
Validation mean > 0 **and** the test interval's lower bound > 0. Then: a forward test scored
from Hyperliquid's history alone (no collection), every listing with `L` in 2026-10-12 ..
2027-10-11, the chosen rule unchanged, success = mean > 0 with the same interval above 0 at
≥ 30 listings. Otherwise F1 is closed.

**Prior:** 0.25. Listing fades are widely believed in; if the edge were large and easy, it would
be competed down, and squeezes make the mean noisy.
