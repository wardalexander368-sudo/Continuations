# Funding-spike event trades on Hyperliquid perps (edge hunt F2): study design

Written 2026-10-10 05:25 UTC by the curve-model retrain thread, **before any funding-spike number was
computed** (the hourly funding cache was still being fetched). Paper only.

## Question

When a coin's funding spikes (longs pay a lot to hold), does the coin then fall (crowded longs unwind:
short it) or keep rising (D2's hint that high funding goes with momentum: long it)? Measured per event,
hedged against the market, after costs and funding.

## Data

* Daily closes and volumes of every Hyperliquid perp, delisted included: `data/edge-hunt/hl-daily/` (D's).
* Hourly funding of every perp from 2023-06: `data/edge-hunt/hl-funding/` (`crosssection/fetch_hl_funding.py`).
  Day d's funding F(c, d) = sum of the 24 hourly rates in UTC day d.

## Universe and event

* Universe on day d (D's): ≥ 60 days of closes and 30-day median USD volume ≥ $2M.
* **Event** for coin c on day d: F(c, d) ≥ θ, with θ ∈ {0.10%, 0.20%, 0.40%} per day (about 37%, 73%, 146% a
  year), and c had no event in the previous 14 days (a fresh spike; also stops the same spike re-firing).
* Entry at day d+1's close (one day lag, as D's registration). Exit at the close H days later,
  H ∈ {3, 7, 14}, or the last close if the coin is delisted earlier.
* **Direction** s ∈ {short (fade), long (follow)}.

18 rules = 3 θ × 3 H × 2 directions. Nothing else is tried; every rule's numbers are printed.

## Trade return (per $1 in the coin)

pair return = s × (coin return − equal-weight universe return over the same closes)
            − 4 × 20 bps (both legs in and out)
            − s × (sum of the coin's hourly funding over the hold) + s × (mean universe funding over the hold)

(A short receives the coin's funding and pays the hedge's.) Universe = that day's universe minus c.

## Splits and decision

* Train: events entered 2023-07-01 .. 2025-03-31. Validation: 2025-04-01 .. 2025-12-31. Test: 2026-01-01 .. last day.
* Per split: mean pair return per event, 90% CI by bootstrap over entry weeks (all events entered in the
  same ISO week resampled together), and the event count.
* **Choose** the rule with the highest train mean among rules with ≥ 30 train events.
* **Read test** only if the chosen rule's validation mean is > 0. Test is read for that rule only (the
  others print "-").
* **Register a forward paper test** only if validation and test both have a CI lower bound > 0. Otherwise
  F2 is closed with the numbers.
