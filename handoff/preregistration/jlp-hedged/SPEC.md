# Pre-registration: delta-hedged JLP vs Kamino USDC lending (paper, 90 days)

Registered 2026-10-09 by the dip/jevtrader session (session_01Htqh7pc1Lh1PP6Dkm1rVvz). The
commit that adds this file is the registration time. No result inside the test window exists
yet: the window opens 2026-10-10 00:00 UTC. Paper only: no wallet, no exchange account, no Jev.

Origin: edge hunt angle A1 (`handoff/edge-hunt.md`). Exploratory, seen before this rule was
fixed: hedged JLP +7.9% APR over Kamino USDC, 90% CI [+3.0, +12.4], 304 days to 2026-10-08,
with a 60-day price-beta hedge on daily data. This test uses the pool's exact delta instead and
real costs, forward, on data nobody has seen.

## Window
2026-10-10 00:00 UTC to 2027-01-08 00:00 UTC (90 days). Check-ins outside it are ignored.

## Position ($10,000 paper capital)
* **Long JLP** bought on Jupiter (USDC -> JLP) at the quoted cost vs the pool's NAV.
* **Short SOL, ETH, BTC perps on Hyperliquid**, one cross-margin account, sized to the JLP
  held times the pool's delta per JLP:
  `delta_a = (owned_a - locked_a + globalShortSizes_a / globalShortAveragePrice_a) / jlpTotalSupply`
  from `perps-api.jup.ag/v1/jlp-info` (WBTC custody hedged with BTC).
* **Split:** JLP = capital / (1 + h/3), margin = the rest, where h is hedge notional per JLP-$.

## The rule (decisions only at check-ins, scheduled every 4 hours)
1. **Rebalance** every short to target when any asset's |short - target| x mark > 5% of the
   JLP value. Cost: traded notional x (4.5 bps taker + half the quoted spread).
2. **Margin:** if margin < notional / 5, sell JLP (quoted sell cost) to bring it to notional / 3;
   if margin > notional x 2/3, buy JLP (quoted buy cost) with the excess down to notional / 3.
3. **Funding** accrues on each short at Hyperliquid's hourly rate (shorts receive positive).
4. **Liquidation:** between check-ins, on every Hyperliquid 1h candle, equity with every asset
   at its candle high together < sum(short x high x maintenance) (SOL 2.5%, ETH 2%, BTC 1.25%)
   is a simulated liquidation. That ends the test as a FAIL.
5. **Exit cost** is charged once at the end: JLP sold at the last quote, shorts closed at taker.

A missed check-in means the trader didn't look; P&L still comes from history.

## Benchmark
Kamino main-market USDC supply, valued by its reserve exchange rate (hourly history API).

## Primary statistic
Mean daily excess return (equity from the last check-in of each UTC day, minus the benchmark's
return over the same day), annualized x 365, with a 90% moving-block bootstrap CI (10-day
blocks, 10,000 resamples, seed 1).

## Success (all three)
* mean excess > 0;
* the CI's lower bound > 0;
* no simulated liquidation.

Anything else is a FAIL. Scored by `python3 handoff/experiments/jlp_paper.py evaluate --final`
on or after 2027-01-08. Interim `evaluate` runs may be read, but they change nothing.

## Fixed after this commit
Every number above and in `jlp_paper.py`'s registered constants. A mistake found later gets a
dated addendum in this directory that leaves the primary statistic as registered.
