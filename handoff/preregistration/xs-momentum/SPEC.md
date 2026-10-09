# Pre-registration: weekly cross-sectional momentum on Hyperliquid perps (paper, 52 weeks)

Registered 2026-10-09 by the dip/jevtrader session (session_01Htqh7pc1Lh1PP6Dkm1rVvz). The commit
that adds this file is the registration. The first signal day is Monday 2026-10-12, so no test
data exists yet. Paper only. Scored from Hyperliquid's public history by
`handoff/experiments/xs_momentum_forward.py`; nothing has to be recorded live.

## Where it came from (exploratory, seen before this rule was fixed)
Edge hunt angle D (`handoff/edge-hunt.md`, `handoff/experiments/edge-hunt/crosssection/`). On all
234 Hyperliquid perps (56 delisted, so survivorship is limited), 12 rules were tried
(lookback 1/3/7/14/28/56 days x momentum/reversal). Chosen on train (2023-07..2025-03): 14-day
momentum, +2.20%/week. Validation (2025-04..12) +1.80%, test (2026-01..10) +1.76% before funding;
after funding +2.08 / +1.79 / +1.50%/week, test 90% CI [−0.12, +3.31] (39 weeks). The
1-day-lag, 20 bps variant below kept train/val/test at +1.44 / +0.81 / +1.64% before funding.
Twelve rules were looked at, so the true edge is likely smaller than these numbers.

## Rule
* **Universe each Monday (UTC daily close):** every Hyperliquid perp with 60 consecutive daily
  closes up to that Monday and a 30-day median USD volume >= $2M.
* **Signal:** 14-day return to Monday's close. Long the top quintile and short the bottom quintile,
  equal weight, $1 per leg.
* **Execution:** enter at Tuesday's close (one day after the signal), exit at the next Tuesday's
  close. A delisted coin exits at its last close.
* **Costs:** 20 bps per side per unit of turnover, plus each leg's actual hourly funding (longs pay
  positive funding, shorts receive it).

## Window
Signal Mondays 2026-10-12 .. 2027-10-11 (52 weeks).

## Primary statistic
Mean weekly long-short return net of costs and funding, with a 90% moving-block bootstrap CI
(4-week blocks, 10,000 resamples, seed 1).

## Success
Mean > 0 AND the CI's lower bound > 0. Anything else is a FAIL. Scored with
`xs_momentum_forward.py --final` after 2027-10-20. One interim look on 2027-04-13 is informative only.

## Fixed
Every constant in `xs_momentum_forward.py`. Mistakes found later get a dated addendum that leaves
the primary statistic as registered.
