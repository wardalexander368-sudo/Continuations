# Pre-registration: vol-scaled momentum on Coinbase's US perps (paper, 52 weeks)

Registered 2026-10-11 by the trading-skills thread (US-tradable lane; AJ's rule that live venues must
be US-accessible). The commit adding this file is the registration; the window starts 2026-10-12.
Paper only. Scored from Coinbase Exchange's public daily candles by
`handoff/experiments/edge-hunt/perps/cde_forward.py`; nothing has to be recorded live.

## Why
The registered HL rules D and D3 (`preregistration/vol-momentum/`) trade Hyperliquid, which is not
US-usable. Coinbase Financial Markets lists CFTC-regulated perpetual-style futures ("-CDE", hourly
funding, published taker fee from 0.02%) on 23 crypto coins (public product list, 2026-10-11). This
registers the same D3 rule on that universe, so a US account has a version to trade.

## Evidence (exploratory; no new selection, the rule is D3 as registered)
`perps/xs_coinbase.py` on Coinbase daily history of the 23 coins, 20 bps/side, funding not charged:
train 2020-23 +0.51%/week [−0.84, +2.00] (126), validation 2024 +1.08% [−2.33, +4.67] (53), test
2025-01..2026-10 **+0.39% [−1.05, +1.94]** (90). D (plain 14-day return) is similar (+0.84 / +0.45 /
+0.40). On Hyperliquid's data cut to the same coins (`perps/cde_momentum.py`, fewer weeks) D3 test is
+0.48%/week, D −0.81%. Long-only versions on Coinbase spot do no better than holding every coin.
Weak points: 23 coins make 4-coin legs; today's list has look-ahead; every CI spans zero; Coinbase
US perp books are thin on some coins (24 h volume $35k–$32M). Prior: low to moderate.

## Rule
Coins: BTC ETH SOL XRP ADA AVAX LINK LTC DOT DOGE BCH NEAR SUI HYPE BNB AAVE ONDO XLM ENA HBAR PEPE
SHIB ZEC (Coinbase USD spot candles stand in for the perps). Each Monday, among coins with 60 days
of history and 30-day median USD volume >= $1M: signal = 14-day return / std (ddof 0) of the last 14
daily returns; long the top quintile, short the bottom (equal weight, $1 a leg), entered at
Tuesday's close and held to the next Tuesday's close; 20 bps per side of turnover; funding ignored.

## Window, statistic, success
Signals 2026-10-12..2027-10-11 (52 weeks). Mean weekly return with a 90% moving-block bootstrap CI
(4-week blocks, 10,000 resamples, seed 1). Success: mean > 0 AND lower bound > 0, from
`cde_forward.py CACHE --final` after 2027-10-19. Every constant is fixed in the two scripts.
