# Live rule for US strategies (DRAFT, 2026-10-12 ~00:20 UTC, not adopted)

Drafted for AJ ("draft the live rule") after `reviews/overall-2026-10-11.md` item 1: no US registration can clear
its CI bar in 52 weeks, so going live has to be a sizing decision with a hard loss limit, not a test result.
The registrations and their scoring are unchanged. Nothing here spends money: going live still needs AJ's go
in words and a funded Alpaca live account.

## Which strategy
**Only `us_capit` (CAPIT on the study's 11 coins) is eligible.** Reasons: strongest US signal, held on 10
coins outside the study (+4.52%/trade), cheap venue (Alpaca, ~0.39%/side), needs no short leg.
Not eligible: `us_volspike` (lost 0.30%/trade on the 10 extra coins), `us_capit~wide` (research line, thin
coins have wider spreads), `cde_vol_momentum` (needs ~$8,000 gross; look again after 26 paper weeks),
anything on Hyperliquid or Jupiter (US-only rule).

## What a real edge looks like at small samples
Backtest on Coinbase hourly candles 2023-01..2026-10, 11 coins, 0.39%/side, $200/trade, entry 1-2 hours after
the signal (the agent's hourly runs give ~90 min):

| | 60-min entry | 120-min entry |
|---|---|---|
| Mean net per trade | +3.66% | +2.68% |
| Trades / crash days | 71 / 25 | 71 / 25 |
| Most trades on one day | 8 | 8 |
| Worst day ($200/trade) | −$96 | −$152 |
| Worst drawdown ($200/trade) | −$156 | −$209 |
| Chance the mean is below zero after 3 / 5 / 10 crash days | 34% / 28% / 18% | 37% / 31% / 24% |
| 10th percentile of the mean after 3 / 5 / 10 crash days | −3.5% / −2.7% / −1.1% | −4.7% / −3.8% / −2.2% |

So even if the edge is real, a third of 3-crash-day samples are negative. The rule below therefore only screens
out clearly broken results and caps the loss; it cannot confirm the edge.

## Gate to start (all must hold)
1. AJ says go in words, opens and funds an Alpaca **live** account (suggested $1,500), and adds its keys as new
   GitHub secrets. The live order route is built only after that (today `alpaca.py` refuses any non-paper host).
2. Paper `us_capit` has at least **3 crash days and 8 trades** since 2026-10-12.
3. Its paper mean net per trade at the measured Alpaca cost is above **−4.7%** (the backtest's 10th percentile
   for 3 crash days at the slow entry).
4. Alpaca paper fills: median measured cost at most **0.50% per side**, and no fill more than 0.5% away from the
   paper book's price for the same trade.

## Stake
* **$100 per trade**, 11 coins, one position per coin, market orders at the first hourly run after the signal.
* At most **$1,100** open at once (11 coins); history's busiest day had 8 trades ($800).
* At this stake the backtest's worst day is about −$76 and its worst drawdown about −$105.

## Stops (any one ends live trading; restarting needs AJ again)
* Realized live loss reaches **$250** (about 2.4x the backtest's worst drawdown at this stake).
* After 5 live crash days, live mean net per trade below **−3.8%**.
* Median measured cost over the last 10 live fills above **0.60% per side** (that halves the edge).
* Any order the agent can't match to a paper trade, or a position left open past its exit by more than 2 hours:
  write `autotrade/HALT`.

## Scaling
After **10 live crash days** with live mean net above **+1%** per trade and median cost at most 0.45%/side,
AJ may double the stake to $200. Never above $500 per trade without a fresh review.

## Honest expectations
CAPIT fires on about 6 crash days and ~16 trades a year. At $100/trade and +2-3% net per trade that is about
**+$30 to +$50 a year**: this stage measures live execution, it doesn't make money. At $1,000/trade it would be
roughly +$300 to +$500 a year with up to $11,000 exposed for a day at a time. Reaching 10 live crash days takes
about 18 months at historical rates; a crash-heavy stretch would speed that up. Faster entries (an always-on
machine instead of hourly runs) are worth about +1 to +2 points per trade (`reviews/timing-2026-10-11.md`),
so that question comes back once the stake is above $100.
