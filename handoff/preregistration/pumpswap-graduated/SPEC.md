# Pre-registration: trading graduated pump.fun tokens on PumpSwap (queue 11a)

Registered 2026-10-09 ~04:50 UTC by the research session, before any return was computed on
the evaluation data. The git commit that adds this file is the registration time.

## Question
After a pump.fun token graduates to its PumpSwap pool, does any simple entry rule, chosen on
earlier pools, make money on later pools after real costs?

## Data
* **Evaluation data:** `tartar record --pumpswap-hours 4` recordings that started at or after
  2026-10-09 04:06 UTC (first: `data/raw-eager` in the research session's container, copied to
  `handoff/data/raw-eager/` as hours finish). Any later recording made the same way may be
  added; each directory is one timeline. Nothing in these has been looked at for returns.
* **Development data (excluded):** `handoff/data/raw-pumpswap` (12 pools, 01:30–01:50 UTC), on
  which the harness was written and checked.

## Design (frozen in `handoff/experiments/pumpswap_study.py` at this commit)
* **Universe:** every graduated SOL pool from its `graduate` event (quote-paired graduations
  have no SOL pool). Pools with no recorded swap at all have no price and are counted and
  reported, not traded.
* **Exclusion:** a signal is dropped only if the recorder was down during the trade (an event
  gap > 30 s, or the recording ended first). After 30 min without swaps the price is held flat.
* **Fills:** constant product on the reserves after the last recorded swap before execution;
  PumpSwap fee by market-cap tier (profitability.md 3.13); 0.0002 SOL per transaction; 0.1 SOL
  per entry; 1 s from decision to execution.
* **Rules** (one trade per pool per rule; holds 1, 5, 15, 60 min):
  * `grad`: buy 5 / 30 / 60 / 300 s after graduation;
  * `mom`: at 1 / 5 / 15 min after graduation, buy if up more than 20 / 50 / 100% since graduation;
  * `dip`: same times, buy if down more than 20 / 40 / 60%;
  * `active`: at 15 / 30 / 60 min, buy if the pool had at least 10 / 50 recorded swaps in the last 5 min.
* **Selection:** pools ordered by graduation time. On the first 60% (validation), the rule with
  the best mean net per trade among those with at least 20 trades is chosen in each family. Each
  chosen rule is reported once on the last 40% (test).

## When to evaluate
Once, when the evaluation data holds **at least 250 graduated SOL pools** (≈ 6–7 h of
recording): `python3 handoff/experiments/pumpswap_study.py <dirs> --show-test`. Report every
family's test line and the reference line, whatever they show.

## Success
A family has an edge if its chosen rule's test mean net per trade has a lower bound above zero
at one-sided 1.25% (5% Bonferroni-split over the four families), from a bootstrap over pools.
Anything that passes must then be confirmed on a later, separate recording before it is
traded, even on paper. Sensitivity (reported, not criteria): `--latency 3`, `--size 1`.

## Expectation
Probably no edge. Fresh graduates pay 1.25% per side (the same as the bonding curve), and
early trading after a graduation is dominated by the same insiders who held the curve.
