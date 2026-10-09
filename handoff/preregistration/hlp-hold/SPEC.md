# Pre-registration: holding HLP (Hyperliquid's protocol vault) against a 5% cash hurdle (paper, 180 days)

Registered 2026-10-09 (~23:40 UTC) by the trading-skills thread (new-markets lane). The commit that
adds this file is the registration. The window starts 2026-10-12, so no test data exists yet.
Paper only. Scored from Hyperliquid's public history by
`handoff/experiments/edge-hunt/vaults/hlp_forward.py`; nothing has to be recorded live.

## Where it came from (exploratory, seen before this rule was fixed)
The vault-following study (`handoff/edge-hunt.md` §F, `experiments/edge-hunt/vaults/vault_follow.py`)
used HLP as a benchmark. Following past-winner vaults failed (18 rules, none passed validation), but
HLP itself earned in every period, from its account value and PnL history (time-weighted, no leader
commission): monthly mean +7.3% (2023-08..2024-12), +0.97% (2025-01..06), +1.33% [+0.18, +2.70]
(2025-07..2026-09). Calendar years: 2023 +83%, 2024 +79%, 2025 +19%, 2026 to 10-09 +8.1%. The
return is falling as HLP grows (~$181M). With this scorer: 2025-H1 +12.3% a year, 2025-H2 +28.0%,
2026-01..10 +11.1%. Worst two-week interval −4.4% (2023); max drawdown of the index −5.8%. Only this
one holding rule was looked at, but its edge over cash is thin and decaying, and HLP carries tail
risk (it absorbs liquidations and market-making losses).

## Rule
Hold HLP. Return per interval = PnL change / account value at the interval's start, from HLP's
allTime history (points about every 14 days); deposits are locked 4 days, HLP takes no commission.

## Window
History points from 2026-10-12 to 2027-04-10 (180 days, ~13 intervals).

## Primary statistic
HLP's annualised return over the window minus a fixed 5% a year (a stand-in for USDC lending),
with a 90% moving-block bootstrap CI over intervals (2-interval blocks, 10,000 resamples, seed 1).

## Success
Excess > 0 AND the CI's lower bound > 0. Anything else is a FAIL. Scored with
`hlp_forward.py --final` after 2027-04-11.

## Fixed
Every constant in `hlp_forward.py`. Checked on history: 2025-01..06 +7.3 points [+0.9, +14.8],
2025-07..12 +23.0 [−3.9, +82.7], 2026-01..10 +6.1 [−5.2, +28.8]. Mistakes found later get a dated
addendum that leaves the primary statistic as registered.
