# Pre-registration: pump.fun revenue surprise -> PUMP perp (edge hunt E1)

Registered 2026-10-09 ~22:10 UTC, before the window opens. The rule's constants are in
`handoff/experiments/pumpflow_paper.py` and are fixed by this commit. Paper only.

## The question
pump.fun spends its revenue on buying back PUMP. If a day's revenue comes in above its recent
level, does PUMP rise over the next day by more than costs, after the day's total is public?
TARTAR's decoder sees the same flow live; this test uses DefiLlama's published daily totals,
which anyone can read, so it measures the slower, public version of the signal.

## Rule
* Every hour, check DefiLlama's daily revenue for pump.fun (launchpad) and PumpSwap. The first
  time a new UTC day *d* has both, compute
  `surprise = log(rev_d / mean(rev_{d-7} .. rev_{d-1}))` from the numbers published at that
  moment (later revisions are never used).
* At that moment, go long the Hyperliquid PUMP perp if `surprise > 0`, short otherwise, at the
  recorded mid, at fixed notional. Hold until the next day's snapshot, then take its position.
* Cost: 0.10% per side per unit of turnover (taker 0.045% plus spread and impact; a flip pays two
  sides). Funding from Hyperliquid's hourly history between snapshots (longs pay positive rates).

Snapshots: `.github/workflows/pumpflow-paper.yml` runs `pumpflow_paper.py snapshot` at :15
every hour and commits `handoff/data/pumpflow-paper/snapshots.jsonl` when a day is new. The
2026-10-09 pilot snapshot precedes the window and is ignored.

## Window and criteria
Window: snapshots taken 2026-10-10 00:00 UTC .. 2027-04-08 00:00 UTC (180 days). Score once with
`python3 handoff/experiments/pumpflow_paper.py evaluate --final` after 2027-04-08.
A look at 90 days (2027-01-08) is a report only, never a stop or a change.

**Confirmed** only if all hold:
1. at least 120 trades;
2. the 90% interval of mean net per trade (block bootstrap, blocks of 10 trades) is above 0;
3. the timing part is positive (net minus the average position times buy-and-hold), so a
   PUMP trend that the rule happened to be long in does not count as an edge.

## What the evidence was, and what was looked at (read before trusting any result)
Data: DefiLlama daily revenue 2024-03-01 .. 2026-10-08; Hyperliquid daily candles and funding for
PUMP (from 2025-07-10), SOL, BTC, kBONK, WIF, POPCAT, FARTCOIN, kPEPE. Train < 2026-04-01 <= test.
Scripts and outputs: `handoff/experiments/edge-hunt/pumpflow/`, `handoff/data/edge-hunt/pumpflow/`.

* **PUMP was named before any data was read** (STATUS claim, 21:40 UTC: "daily fees/revenue,
  which fund PUMP buybacks"). Looked at in all: 5 signals x 8 perps x 2 lags of rank correlation
  (80 cells), then 3 signals x 2 modes x 2 lags of rules on PUMP, then 8 entry hours. Of the 80
  cells only PUMP's next-day cells are positive in both halves for all three surprise signals;
  the trend signals flip sign between train and test on most perps.
* **The registered rule on daily closes** (enter at day *d*'s close, before the total is
  public; not executable on DefiLlama, only with a live feed), 0.10%/side:
  train +0.76%/day [−0.01, +1.49] (n 265), test +0.95% [+0.08, +1.86] (n 191). Timing part
  +0.75% [+0.01, +1.48] / +0.82% [+0.05, +1.61]. At 0.20%/side the intervals touch 0.
* **Entering later on day d+1** (hourly candles, last 207 days, mostly test): timing part
  +0.72% at 00:00, +0.63% at 06:00, +0.50% at 16:00 UTC, each ± ~0.63 (90%). **One day later
  (enter at d+1's close) it is gone:** +0.02% train, +0.20% test. So the edge, if real, decays
  within the day, and this forward test's result depends on how early DefiLlama publishes.
* **Not PUMP's own momentum:** with both in one regression, sign(surprise) keeps +0.77% (t 1.6)
  train and +0.89% (t 1.9) test; sign(PUMP's day-*d* return) adds +0.48% (t 1.0) / +0.05% (t 0.1).
* **Caveats.** PUMP rose about 2.8x from August to October 2026 (+0.78%/day buy-and-hold),
  and the rule was long 59% of test days, hence criterion 3. The backtest used DefiLlama's
  current, possibly revised, numbers; the forward test uses first-published ones. Each half
  alone is about 1.6–1.9 standard errors. **Prior expectation: a small edge or none**; a 90%
  interval of about ±0.8%/trade at 180 trades means only an effect at least as large as the
  backtest's can confirm.

## Addendum 2026-10-10 (after registration; the rule, window and criteria are unchanged)
DefiLlama publishes a day at least ~25 h after it ends (measured 2026-10-10 00:50 UTC: newest day
10-08). Re-scoring the backtest at that lag (`handoff/experiments/edge-hunt/pumpflow/publish_lag.py`)
puts the timing part at about +0.05% to +0.12% with intervals of about ±0.6%, against +0.75% /
+0.82% at the daily close. This test therefore measures a version with an expected edge of about
zero and is expected to fail. It keeps running as registered because it costs nothing and records the
public version honestly; the agent's paper copy is disabled. The same-day version (our recorder's
bonding-curve volume) is being validated separately (edge-hunt.md §E1, "publish delay").
