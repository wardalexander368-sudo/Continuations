# Pre-registration: two chart patterns on US spot (Coinbase), paper, 52 weeks

Registered 2026-10-11 (~03:30 UTC) by the trading-skills thread (chart-pattern lane, AJ's "what
other chart watching methods"). The commit adding this file is the registration; the window
starts 2026-10-12. Paper only, long only (US spot). Scored from Coinbase's public candles by
`handoff/experiments/edge-hunt/patterns/pattern_forward.py`; nothing has to be recorded live.

## Where they came from (exploratory)
`experiments/edge-hunt/patterns/patterns.py` (edge-hunt §K): 24 long-only rules in 6 families on 11
Coinbase coins, 15-minute candles 2020-01..2026-10 rolled into hours. Entry and exit 30 minutes after
the hourly close (the agent runs once an hour, 14-26 minutes past), 0.62% per side (Coinbase
Exchange's published taker fee below $10k a month, 0.60%, plus ~2 bps spread). Each family's rule
chosen on train (2020-23), kept only if validation (2024) agreed; two of six reached test
(2025-01..2026-10), where buying at random hours earned −0.05% (24 h) and −0.17% (72 h) gross:

| Rule | Train | Validation | Test |
|---|---|---|---|
| CAPIT Z=4 H=24 | +0.32% (55) | +3.84% (22) | **+5.77% [−1.5, +11.4]** (28 trades, 11 days) |
| VOLSPIKE K=10 H=72 | +0.38% (122) | +2.14% (39) | **+1.32% [−1.9, +4.5]** (87 trades, 55 days) |

Both test CIs span zero; train is barely positive; capitulations cluster on a few market-wide crash
days. Prior: low. The other four families (wick bounce, breakouts, RSI oversold, Bollinger squeeze)
did not pass.

## Rules (11 coins: BTC ETH SOL XRP DOGE ADA AVAX LINK LTC BCH DOT, USD pairs)
Hourly bars from 15-minute candles; sigma = std (ddof 0) of the previous 168 hourly returns.
* **CAPIT (capitulation bounce):** when the 24-hour return at an hourly close is at most
  −4 x sigma x sqrt(24), buy 30 minutes after that close; sell 24 hours later (30 minutes after).
* **VOLSPIKE (volume-spike follow-through):** when an hour's volume is at least 10x the mean hourly
  volume of the previous 168 hours and the hour closed up by at least 1 sigma, buy 30 minutes after
  the close; sell 72 hours later.
One position per coin per rule at a time; cost 0.62% per side.

## Window, statistic, success
Entries 2026-10-12..2027-10-11. Per rule: mean return per trade with a 90% bootstrap CI over entry
days (10,000 resamples, seed 1). Each rule succeeds if its mean > 0 AND CI lower bound > 0, from
`pattern_forward.py CACHE --final` after 2027-10-12 (two tests; a pass at the 90% level on either
alone is weak evidence). Every constant in `patterns.py` and `pattern_forward.py` is fixed.
