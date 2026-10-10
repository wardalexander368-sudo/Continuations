# Addendum, 2026-10-09 ~04:30 UTC: PumpSwap fees are higher than registered

Written before any out-of-sample result was computed or looked at (cohort 1 was registered
02:24 UTC the same day; the rule needs 62 five-minute bars, so no trade could exist yet).
SPEC.json, the rule, the universe rule and the success criteria are **unchanged**.

## What was wrong
SPEC.json charges `fee_per_side: 0.005`, with the note "PumpSwap charges ~0.30%/side".
Measured on mainnet (`handoff/experiments/pumpswap_fees.py`, the fee basis points the
program writes into every BuyEvent/SellEvent), PumpSwap's fee is **LP 0.20% + protocol
0.05% + a coin-creator fee tiered by market cap**:

| market cap (SOL) | creator | total per side |
|---|---|---|
| below ~420 (just graduated) | LP 0.02 + protocol 0.93 + creator 0.30 | **1.25%** |
| ~500–1,200 | 0.95% | 1.20% |
| ~5,600–6,300 | 0.75% | 1.00% |
| ~12,000 | 0.70% | 0.95% |
| ~18,000 | 0.65% | 0.90% |
| ~28,000 | 0.55% | 0.80% |
| ~32,000–34,000 | 0.50% | 0.75% |
| ~47,000 | 0.35% | 0.60% |
| ~500,000 | 0.05% | 0.30% |

Cohort 1's pools, measured 04:27 UTC (`fees-measured.json`): 0.30% to 1.20% per side,
**mean 0.85%**. Four of twelve pay 1.00% or more.

## Effect on the registered test
* **Primary (excess over random entries in the same pool):** essentially unaffected. Trades
  and the random-entry baseline in a pool pay the same fee, so it cancels except for a
  second-order multiplicative term.
* **Second success criterion (mean net per trade > 0):** the registered fee understates the
  cost by ~0.35 points per side on average (~0.7 points per round trip), and by 1.0–1.4
  points per round trip on the four pools at 1.00–1.20%.

## What is added (secondary, not a success criterion)
`established_prereg_eval.py` also prints the mean net per trade with each pool's measured
fee (`fees-measured.json`; a pool without a measurement keeps the registered fee). The
registered RESULT line is computed exactly as before. A reader should treat a SUCCESS whose
secondary mean net is ≤ 0 as not profitable at real costs.

For later cohorts: right after `established_cohort.py` writes a cohort, run
`python3 handoff/experiments/pumpswap_fees.py --cohort <that file> --save handoff/preregistration/dip-rolling/fees-measured.json`
and commit both together. A pool's tier moves with its market cap; the fee measured at
registration is used for all of its trades (an approximation, stated here in advance).
