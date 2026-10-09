# Pre-registration: volatility-scaled cross-sectional momentum on Hyperliquid perps (paper, 52 weeks)

Registered 2026-10-09 (~22:45 UTC) by the trading-skills thread (perps lane). The commit that adds
this file is the registration. The first signal day is Monday 2026-10-12, so no test data exists
yet. Paper only. Scored from Hyperliquid's public history by
`handoff/experiments/edge-hunt/perps/vmom_forward.py`; nothing has to be recorded live.

## Where it came from (exploratory, seen before this rule was fixed)
Perps lane of the edge hunt (`handoff/edge-hunt.md` §D3, `handoff/experiments/edge-hunt/perps/perp_rules.py`).
Same data, universe, splits and costs as edge hunt D. 24 rules in 7 families were tried (time-series
trend on BTC/ETH/SOL weekly and daily, daily cross-sectional reversal, volatility-scaled momentum,
residual momentum, volume-confirmed momentum, nearness to the 30/90-day high). Volatility-scaled
14-day momentum was chosen on train within its family (L = 7/14/28). With a 1-day execution lag,
20 bps per side and actual funding (validation and test): train +0.73%/week [−1.22, +2.74] (no
funding charged in train), validation +2.15% [+0.46, +3.88], test (2026-01..10) **+2.03% [+0.26,
+3.97]** (39 weeks). D's plain 14-day rule under the same settings: validation +0.63%, test +1.29%.
**The two rules' weekly returns correlate 0.87**: this is mostly D's momentum, ranked so that a
coin's move counts relative to its own daily volatility. 24 rules were looked at in this lane (and
12 in D before it), so the true edge is likely smaller than these numbers.

## Rule
* **Universe each Monday (UTC daily close):** every Hyperliquid perp with 60 consecutive daily
  closes up to that Monday and a 30-day median USD volume >= $2M (as D).
* **Signal:** 14-day return to Monday's close divided by the standard deviation (population, ddof 0)
  of its last 14 daily close-to-close returns. Long the top quintile and short the bottom quintile,
  equal weight, $1 per leg.
* **Execution:** enter at Tuesday's close (one day after the signal), exit at the next Tuesday's
  close. A delisted coin exits at its last close.
* **Costs:** 20 bps per side per unit of turnover, plus each leg's actual hourly funding (longs pay
  positive funding, shorts receive it).

## Window
Signal Mondays 2026-10-12 .. 2027-10-11 (52 weeks), the same weeks as D's forward test.

## Primary statistic
Mean weekly long-short return net of costs and funding, with a 90% moving-block bootstrap CI
(4-week blocks, 10,000 resamples, seed 1).

## Success
Mean > 0 AND the CI's lower bound > 0. Anything else is a FAIL. Scored with
`vmom_forward.py --final` after 2027-10-20. One interim look on 2027-04-13 is informative only.

## Secondary (informative, not a criterion)
The weekly difference from D's plain 14-day rule on the same weeks, with the same CI method: does
volatility scaling add anything over D? Printed by the scorer.

## Fixed
Every constant in `vmom_forward.py`. The scorer was checked once on 2026-01-05 .. 2026-09-28 with
funding off: +2.17%/week on 39 weeks, against the exploration harness's +2.19%. Mistakes found
later get a dated addendum that leaves the primary statistic as registered.
