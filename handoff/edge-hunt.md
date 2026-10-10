# Edge hunt: new strategy families

**Status: resumed 2026-10-09 17:32 UTC** (on hold 13:25–17:32). A1 is pre-registered and running as a
paper forward test (`handoff/preregistration/jlp-hedged/SPEC.md`, `handoff/experiments/jlp_paper.py`).
Predictor session, branch `claude/solana-candle-predictor-s95qjr`. Everything here is
**exploratory**. Nothing is pre-registered, and every number below was seen before any rule
was fixed. Treat them as reasons to test, not as results. No real-money code was written and
no Jev calls were made.

## Why

Profitability §1 closes every pump.fun launch family, longer holds, copy-trading, the
graduation run-up and graduated tokens on PumpSwap. The edge hunt asked where an edge could
exist for us: on-chain costs of ~0.5 bps on SOL-USD (§3.12), notification latency of ~1.2–1.5 s,
free data only, no private RPC, no Jev, and no deception (no token launches to dump, wash
trading, spoofing or sandwiching).

## How far it got

A workflow ran five "angles", each proposing studies with verified free data. Three
adversarial judges (economics, testability, fit) were to score each proposal, and a lead
would then write a ranked plan. It was stopped mid-way:

| Angle | State |
|---|---|
| Carry / structural yield | **done:** 3 proposals with verified data and preliminary numbers (below) |
| SOL microstructure (CEX–DEX lead-lag, seasonality, crash reversal) | **mostly done:** many analyses ran, but the proposal write-up was not reached (results below) |
| Memecoin liquidity / short side (PumpSwap LP, memecoin perps, P(rug) as a short signal) | barely started (read the docs only) |
| Established tokens, daily cross-section and event studies | not started |
| TARTAR's own assets (predictor, P(rug), decoder) turned into money | not started |
| Judges and ranked plan | not started |

To resume, rerun the three unfinished angles, then judge and rank all proposals. The
briefs are in *Resume* below. The workflow script itself was session-local.

## Findings so far

### A. Carry and structural yield (complete proposals)

Data verified by real requests on 2026-10-09:
- Hyperliquid funding: SOL hourly from 2023-05, plus ETH and BTC.
- Other venues' funding: Deribit hourly from 2022-03, Gate, KuCoin, BitMEX, dYdX v4, MEXC. OKX and Bitget have only ~3 months free.
- Kamino reserve APYs, daily from 2023-10.
- Jito pool APY, daily from 2022-11.
- CoinGecko JLP daily (365 days free); GeckoTerminal JLP pool OHLCV (180 days free).
- Jupiter `perps-api.jup.ag/v1/jlp-info`: live pool composition, which gives the exact JLP delta.
- Jupiter quotes.

Unavailable: Binance (HTTP 451) and Bybit (403) are geo-blocked here, and Drift's data APIs are refused at the proxy. Drift funding could only be recorded forward from its market account on the public RPC.

1. **Delta-hedged JLP vs Kamino USDC lending** (prior 0.40, the strongest candidate).
   - **The trade:** hold JLP (the liquidity token of Jupiter's perpetual-futures exchange, which earns 75% of its traders' fees plus their net losses). Short its SOL, ETH and BTC exposure on Hyperliquid, sized from the pool's exact on-chain delta (~0.44 SOL-$ per JLP-$ today).
   - **Exploratory result** (causal 60-day rolling hedge, 304 days to 2026-10-08): hedged JLP made **+11.8% APR vs Kamino USDC +3.9%, an excess of +7.9% APR, 90% block-bootstrap CI [+3.0, +12.4]**.
     - Both time halves are positive.
     - 90-day windows were positive 100% of the time.
     - Every quarter was positive, including the 2026 Q3 rally.
     - Unhedged JLP lost −21.8% APR over the same period.
   - **Costs:** about 15–25 bps of capital per entry plus exit at $10k:
     - JLP quotes: ~6 bps at $10k, 11–19 bps at $100k;
     - Hyperliquid fills: 4.5 bps taker or 1.5 maker;
     - a ~$1–2 bridge;
     - daily rebalancing: ~0.2% APR.
   - **Who pays:** leveraged perp traders (fees and net losses) and Hyperliquid longs (funding). It is a risk premium for selling leverage, not a forecast.
   - **Risks:**
     - JLP pays out when crowded traders win;
     - only one year of precise price history, mostly a SOL bear market;
     - smart-contract, oracle and venue risk;
     - liquidation of the 3x short on a fast rally;
     - it is a known, productized strategy;
     - eligibility to use perp venues is the user's to check.
   - **Proposed confirmatory test:** a pre-registered 90-day paper forward test (2026-10-12 to 2027-01-10):
     - hourly snapshots of `jlp-info`, Hyperliquid funding, order book and candles, a Jupiter JLP quote, and Kamino USDC daily;
     - a fixed rebalance rule (5% drift), 3x margin, top-ups charged at cost;
     - the primary statistic is annualized excess over Kamino USDC with a 90% moving-block bootstrap CI (10-day blocks);
     - success means a mean above 0, a CI lower bound above 0 and no simulated liquidation;
     - a 120–180-day window would be more decisive.
2. **LST cash-and-carry** (prior 0.25): hold JitoSOL (staked SOL) and short the same amount of SOL perpetual.
   - The edge is **decaying**. Excess over USDC: +40% APR in 2023 Q4, +16% in 2024, +4.7% in 2025, +0.3% in 2026 to date.
   - Time-split test (2025-07 to 2026-10, always-on was chosen on train): +2.34% APR [−0.05, +4.81].
   - The last 90 days made +4.4% at 3x, or +7.4% using the staked SOL as collateral.
   - Over the last year, a 90-day forward test would be close to a coin flip on regime.
   - Side finding: the **LST leverage loop is dead**. Its spread fell from +2.5 points (2023) to −1.5 (2026); positive on 24% of days.
3. **Cross-venue funding dispersion, Hyperliquid minus dYdX** (prior 0.10): +7.8% APR on capital in test. But it was picked after trying 5 pairs, and only it clears USDC (+3.7% excess). The spread flips sign often. Weakest of the three.

Scripts: `handoff/experiments/edge-hunt/carry/` (`fetch_funding.py`, `fetch_rates.py`,
`jlp_hedge.py`, `carry_prelim.py`, `persist.py`, `spread.py`, `power.py`, `final_prelim.py`).
Data: `handoff/data/edge-hunt/carry-sources/` and the daily CSVs in `handoff/data/edge-hunt/`.
The scripts were scratch code run from a scratch directory, so adjust their paths before rerunning.

### B. SOL-USD microstructure at our latency: mostly closed

The CEX data is Binance SOLUSDT 1 s klines for 28 days and 1 m klines for 6 years, from the public archive. It was not committed (1.2 GB) and can be downloaded again.

- **No usable lead-lag.**
  - Jupiter quotes track Binance with no lag. The quote-minus-Binance spread has its smallest dispersion at a 0 s offset (sd 0.61 bps, live 5.5 min sample).
  - In the committed `sol-dex` samples, Coinbase follows Jupiter (β 0.89, t 10), and Jupiter barely follows Coinbase (t 1.7).
  - Trading Jupiter on a ≥1 bps Coinbase–Jupiter gap: +0.15 ± 0.17 bps (n 93). Below cost.
- **Seconds-scale prediction dies at ~2 s.** On Binance 1 s data, out-of-sample R² is 0.45% at zero latency and ≈0 from 2 s. The top 1% of predictions make under 0.6 bps gross. Taker order-flow imbalance: |corr| < 0.03, with signs that flip between halves.
- **Intraday seasonality doesn't persist.** Hour-of-day means rank-correlate −0.34 between train (2020–23) and test (2025–26). Trading the train sign loses −2.1 bps/h in test. Effects around funding times don't persist either.
- **Crash reversal (buying after an extreme 30-minute drop) is real on Binance but not executable on-chain.**
  - Rule chosen on train: k = 30 min, z ≥ 5 down, hold 60 min.
  - Results net of 1.5 bps: train +96 bps [56, 136], n 110; validation +101 [41, 153], n 41; **test +33 [−16, +93], n 48**.
  - Test without its top 3 events: −6 bps.
  - On-chain execution (Orca SOL-USDC, entry at the next minute's open) over 46 events since 2026-04 makes a mean **+4.3 bps, median −7.6**, versus +35.5 on Binance. During crashes the on-chain price sits a median 14 bps worse at entry.
  - It would need a CEX account (real money and venue access, both out of scope). Worth at most a CEX-only paper observation.
- **LST fair value:** JitoSOL buys trade +5.65 bps versus fair value (from the stake pool's on-chain state), and a round trip loses 0.39 bps. No arbitrage.

Scripts: `handoff/experiments/edge-hunt/microstructure/`, in the order they ran:
- lead-lag: `leadlag_existing.py`, `ll1s.py`, `ll1s_ols.py`, `live_ll.py`, `recorder.py`;
- seasonality: `season.py`;
- crash reversal and its latency: `extremes*.py`, `evlatency.py`, `evdays.py`;
- on-chain events: `onchain_ev*.py`;
- order flow: `flow1s.py`.

Live Binance, Coinbase and Jupiter samples: `handoff/data/edge-hunt/live-sol-quotes/`.

### C. Memecoin liquidity and the short side (2026-10-09, dip/jevtrader session): closed

- **LP on graduated PumpSwap pools loses.** In SOL terms, from each pool's first recorded swap
  (`raw-v3`, `raw-clever`, `raw-clever2`), LP value is a mean 0.67x after 1 h (194 pools, median
  0.45x) and 0.70x after 4 h (53 pools, which are the survivors). LP fees add only +0.2 points
  at the 0.02% LP share these pools pay, and +1.8 to +2.0 points even at 0.20% (median fee growth
  1.8% at 1 h). Impermanent loss on dying tokens is ~15x the fee income.
- **No short exists on fresh tokens.** Hyperliquid lists perps only for established memes
  (DOGE, kPEPE, kSHIB, kBONK, WIF, BOME, POPCAT, MEW, GOAT, MOODENG, PNUT, CHILLGUY, PENGU,
  FARTCOIN, SPX, TRUMP, MELANIA, PUMP), so P(rug) can't be traded as a short signal. Those
  memes fall inside angle D's universe.

### D. Established tokens, weekly cross-section (2026-10-09, dip/jevtrader session): pre-registered

Universe: all 234 Hyperliquid perps, 56 of them delisted (daily candles from 2023,
`handoff/data/edge-hunt/hl-daily/`). Weekly Monday rebalance, quintile long-short, $2M median
volume filter, 10 bps per side. 12 rules (lookback 1/3/7/14/28/56 days x momentum/reversal):
**every momentum lookback beats its reversal twin in train**; chosen on train, **14-day momentum**:
train +2.20%/week, validation +1.80%, test (2026-01..10) +1.76% [+0.15, +3.55]. After actual
hourly funding: +2.08 / +1.79 / **+1.50%/week [−0.12, +3.31]** (39 test weeks). With a 1-day
execution lag and 20 bps per side it holds (+1.44 / +0.81 / +1.64% before funding). Not proven:
12 rules were looked at, and the test CI touches zero. **Pre-registered as a 52-week forward test**
(`handoff/preregistration/xs-momentum/SPEC.md`, scorer `handoff/experiments/xs_momentum_forward.py`),
scored from Hyperliquid's history alone, so no data collection is needed. Scripts:
`handoff/experiments/edge-hunt/crosssection/`.

### D2. Cross-sectional funding carry on Hyperliquid perps (2026-10-09): closed

Same universe, schedule, costs and splits as D; funding for all 231 perps with history
(`fetch_hl_funding.py`, cache not committed). Collecting funding (short the highest-funding
quintile, long the lowest) **loses in train at every lookback** (1/7/28 days: −0.55, −0.89,
−2.31%/week). The reverse, chosen on train (28-day, long high funding), makes +0.73%/week on
validation and **+0.78% [−0.44, +2.13] on test**, and its weekly returns correlate 0.55 with D's
momentum: mostly momentum again, weaker. Not registered. Script: `crosssection/xs_carry.py`.

### D3. More rule families on Hyperliquid perps (2026-10-09, trading-skills thread): one pre-registered

Same universe, splits and data as D (`experiments/edge-hunt/perps/perp_rules.py`; outputs
`data/edge-hunt/perps/`). 24 rules in 7 families, each family's rule chosen on train, test read
only if validation agrees. Settings below: 1-day execution lag, 20 bps per side, actual funding in
validation and test (funding fetched since 2025-04 for the 118 coins the momentum rules held;
`fetch_funding_since.py`).

| Family (rules) | Chosen on train | Validation | Test (39 weeks) |
|---|---|---|---|
| time-series trend, BTC/ETH/SOL, weekly (L 7–112) | 56 d | −0.5% | not read |
| time-series trend, daily (L 7–112) | 28 d | +0.1% at 10 bps; ≤ 0 here | +0.07% at 10 bps |
| daily cross-sectional reversal (1/2/3 d) | loses in train (−2.3 to −2.9%/wk) | | not read |
| **volatility-scaled momentum** (7/14/28 d) | **14 d** | **+2.15% [+0.46, +3.88]** | **+2.03% [+0.26, +3.97]** |
| residual momentum vs BTC (7/14/28 d) | 14 d | +1.16% | +1.40% [−0.31, +3.28] |
| volume-confirmed momentum (7/14/28 d) | 14 d | +2.9% at 10 bps | −0.02% |
| nearness to the 30/90-day high | 30 d | ≤ 0 | not read |

D's plain 14-day rule in the same settings: validation +0.63%, test +1.29% [−0.44, +3.21].
Volatility-scaled momentum (14-day return / std of the last 14 daily returns) is the only rule whose
validation and test intervals both clear zero; **its weekly returns correlate 0.87 with D's**, and
the difference from D is not significant (test +0.51%/week [−0.38, +1.33] at 10 bps, no lag), so it
is a better-behaved version of D, not an independent edge. Pre-registered anyway, since it passed
held-out data and is free to score: `preregistration/vol-momentum/SPEC.md`, same 52 weeks as D,
scorer `experiments/edge-hunt/perps/vmom_forward.py` (prints the difference from D as a secondary).
Trend on the majors and short-term reversal: no edge. Open interest and liquidations: Hyperliquid's
public API keeps no history (only the current snapshot), and Binance's OI history covers 30 days,
so nothing to test yet; the `perps-ctx` GitHub Action snapshots every perp's OI, funding, mark and
volume every 4 hours from 2026-10-09 (`data/edge-hunt/hl-ctx/`), enough for an OI study in a few months.

### G. Following Hyperliquid vaults (2026-10-09, trading-skills thread): closed; HLP pre-registered

Every Hyperliquid vault whose PnL ever reached $1k either way, **closed vaults included** (3,206 of
9,477 listed; `experiments/edge-hunt/vaults/fetch_vaults.py`, `vault_follow.py`; output
`data/edge-hunt/vaults/vault-follow.txt`). Monthly time-weighted returns from each vault's PnL and
account-value history (points every ~14 days), net of the leader's 10% of gains. Rule: each month,
among open vaults with ≥ $50k, buy the top N (5/10/20) by trailing 1/3/6-month return or return/std,
hold a month (18 rules; train 2023-08..2024-12, validation 2025-01..06, test 2025-07..2026-09).
**No rule has train and validation both positive**: past winners don't persist (top-5 by last month:
train +2.1%/month, validation −12.0%), and the equal-weight average vault ≥ $50k lost −8.6%/month in
validation. Few months have enough vaults, so every interval is wide. Top-trader leaderboards only
show today's survivors, so they can't be tested honestly. **HLP itself** (the protocol vault, no
commission) earned in every split (+1.33%/month [+0.18, +2.70] in test; 2025 +19%, 2026 YTD +8.1%,
falling as it grows), so holding it against a 5% cash hurdle is **pre-registered** for 180 days:
`preregistration/hlp-hold/SPEC.md`, scorer `experiments/edge-hunt/vaults/hlp_forward.py`.

### H. Polymarket biases (2026-10-10, trading-skills thread): closed, nothing passes

12,379 resolved Polymarket markets with volume ≥ $200k (random sample of the ~72k listed since
2023; `experiments/edge-hunt/predmkt/fetch_polymarket.py`, `pm_biases.py`; output
`data/edge-hunt/predmkt/pm-biases.txt`). Enter k = 1/7/30 days before the scheduled end at the
last daily price, hold to resolution, 1 cent a share for spread (2 where fees apply), bootstrap by
event. 33 rules: favourite bands (FAV), underdog bands (LONG), 7-day drift (DRIFT); splits by end
date, train 2023-01..2025-06, validation 2025-07..12, test 2026-01..09.
* **No favourite-longshot edge after the spread.** Every favourite band but one loses in train or
  validation; the chosen one (0.95–0.99, 30 days) loses in test, −2.46% [−4.51, −0.67]. Longshots
  under 5 cents lose almost everything.
* **LONG's chosen rule (0.15–0.30, 30 days): test +5.0% [−17.4, +28.5]**, no evidence. The 1-day
  underdog rules looked strong in validation, but re-priced at hourly prices
  (`pm_verify.py`, `data/edge-hunt/predmkt/pm-verify-long-partial.txt`, on the first 3,700 markets)
  most of the gain was stale daily prices: train +13.9% → +1.6%, validation +48% → +18%, both CIs
  spanning zero.
* **DRIFT:** train and validation disagree; test not read.

### E. TARTAR's assets

Covered by the fee-research thread's predictor + P(rug) strategy forward test (see STATUS.md);
not duplicated here.

**E1. pump.fun's own revenue -> PUMP perp (2026-10-09, edge hunt E thread): pre-registered.**
pump.fun buys back PUMP with its revenue, and our decoder sees that flow live. On DefiLlama's daily
revenue (pump.fun + PumpSwap, 2024-03..2026-10) and Hyperliquid perps, `surprise = log(rev_d /
mean of the 7 days before)` times PUMP's next day: long-short sign(surprise), 0.10%/side + funding,
+0.76%/day train [−0.01, +1.49] (n 265), +0.95% test [+0.08, +1.86] (n 191); the part not
explained by PUMP's trend is +0.75% / +0.82%, and it is not PUMP's own momentum. It fades over day
d+1 (+0.72% entering at 00:00, +0.50% at 16:00 UTC) and is gone a day later. No other perp (SOL,
BTC, five memecoins) shows it. 80 signal x perp x lag cells were looked at; PUMP was named first.
**Forward test:** `handoff/preregistration/pumpflow/SPEC.md`, 180 days from 2026-10-10, entering
when DefiLlama first publishes the day (hourly Action `pumpflow-paper.yml`), scored from
Hyperliquid's history. If it holds, the live version (our own decoder's revenue estimate at
00:00 UTC) is the next step. Scripts and outputs: `experiments/edge-hunt/pumpflow/`,
`data/edge-hunt/pumpflow/`.

**E1, publish delay: the public version has no edge; the live version needs our own feed (2026-10-10).**
Raised by the code audit. **Measured:** at 2026-10-10 00:50 UTC DefiLlama's newest day for both
pump.fun and PumpSwap was 10-08, so a day is published at least ~25 h after it ends (the pilot
snapshot shows 10-08 was out by 10-09 21:38, so at most ~46 h; the hourly snapshots now record each
day's first appearance, which will pin it down). **Re-scored** (`experiments/edge-hunt/pumpflow/
publish_lag.py`, output `data/edge-hunt/pumpflow/publish-lag.txt`), entering L hours after day d ends,
holding 24 h, 0.10%/side, funding pro-rated; timing part with 90% block-bootstrap interval:

| Entry | Timing part |
|---|---|
| L = 0 (SPEC backtest, daily closes) | train +0.75% [+0.01, +1.48], test +0.82% [+0.03, +1.64] |
| L = 4-8 h (hourly) | +0.65% [+0.03, +1.28] |
| L = 24 h, daily closes | train +0.02% [−0.79, +0.74], test +0.20% [−0.45, +0.85] |
| L = 25-28 h (hourly; earliest DefiLlama entry) | +0.05% to +0.12%, intervals about ±0.6 |
| L = 30-40 h (hourly) | −0.06% to −0.36% |
| L = 48 h, daily closes | train +0.50% [−0.17, +1.15], test +0.02% [−0.60, +0.65] |

So at any lag DefiLlama allows, the expected result is about zero. The registered forward test
keeps running unchanged (rule and scorer untouched; `preregistration/pumpflow/SPEC.md` has a dated
addendum saying so) because it is free and is the honest record of the public version, but it is now
**expected to fail**, and the agent's `pumpflow` strategy is disabled (no paper or dry book, no perp
twin budget used). **Faster source:** pump.fun-only revenue keeps the effect (sign agrees with the
total 96% of days; test timing +0.80%), and launchpad revenue is a fixed fee on bonding-curve volume,
which TARTAR's recorder streams live. The recorder saw ~420-530 SOL of fees an hour on 10-09 21-23 UTC
against DefiLlama's ~620 SOL/hour for 10-08, so roughly 70-85% coverage (it keeps each token 120 min).
`experiments/edge-hunt/pumpflow/curve_flow.py` and the daily Action `pumpflow-live.yml` now write each
day's curve volume to `data/pumpflow-live/curve-days.jsonl`. **Validation fixed now, before the data
exists:** once 21 complete recorder days (all 24 hours) are in, compare the curve-volume surprise
(log of day / mean of the 7 before) with DefiLlama's pump.fun-only surprise on the 14 days that have a
base. Usable only if signs agree on at least 12 of 14 and the correlation is at least 0.8; then a new
forward test (entry ~00:30 UTC d+1) gets its own pre-registration. Otherwise E1 is closed.

**E1b. The same rule on 8 other buyback / revenue-share tokens: does not hold (2026-10-09).**
Pre-registered before any of their data was read (`preregistration/revflow/SPEC.md`): HYPE, JUP,
AAVE, DYDX, GMX, CAKE, SKY, BANANA on Hyperliquid. Equal-weight family −0.01%/day [−0.14, +0.13]
(952 days), four tokens up and four down, none with an interval above zero
(`preregistration/revflow/RESULT-2026-10-09.md`). The mechanism doesn't generalize, so E1's PUMP
result is more likely luck or PUMP-specific; its forward test continues with a lower prior.

## Round 2: venues where costs are small next to the signal (2026-10-09 ~23:20 UTC, edge hunt E thread)

Brief (coordinator, under the user's "work continuously"): Hyperliquid perps, big Solana tokens near
Jupiter's ~1% round trip, funding or basis. Excluded as done or claimed: price momentum, trend,
reversal and cross-sectional funding on perps (D, D2, D3), LST and JLP carry (A1, A2), cross-venue
funding (A3), CEX lead-lag (B), vaults and Polymarket (trading-skills thread), revenue flow (E1,
E1b). Proposals, judged by this session under the three lenses (one judge, not three; scores
1-5, written before any of the proposals' data was read):

| # | Proposal | Payer | Econ | Test | Fit | Verdict |
|---|---|---|---|---|---|---|
| F1 | **Short newly listed HL perps** for 1-4 weeks | late hype buyers, crowded longs' funding | 3: fades of several % vs ~0.5% costs; squeezes | 4: ~150 listings since 2023-09 incl. delisted, free history, D-style forward test needs no collection | 4: one venue | **closed:** not confirmed (below) |
| F2 | Funding-spike event short (time series, per coin) | crowded longs | 2: overlaps D2's closed cross-section and momentum | 3 | 4 | hold; run only if F1 shows listing funding matters |
| F3 | On-chain spot vs HL perp gap on memecoins listed on both (convergence) | impatient perp traders | 2: gaps above ~1% are brief; our latency 1.2-1.5 s | 1: no history, must record seconds-level data first | 3: two venues | drop for now |
| F4 | Token-unlock shorts | unlock sellers | 3 | 1: unlock calendars are paid-only (DefiLlama emissions 402) | 4 | drop (no free data) |
| F5 | HL pre-market "hyperps" converging at spot launch | pre-market buyers | 2: few events | 1: a handful a year | 3 | drop |
| F6 | Decoder flow (pump.fun-born tokens) leading their HL perp | on-chain buyers | 2: few such perps, flow mostly off pump venues after graduation | 2 | 3 | drop |

**F1 result (closed).** Chosen on train (k=3, H=7; every train rule lost, −12% to −48% mean,
medians ~0), validation +5.7% [−9.4, +19.6] (51 listings), test +2.9% [−28.3, +24.9] (7 listings).
The median listing fades (short +13%, 2/3 win in 2025-26) but squeezes own the mean (PANDORA
−1,888%, JUP pre-market, PNUT −285%). `preregistration/listing-fade/RESULT-2026-10-09.md`.
Round 2 has nothing registered; F2 (funding-spike shorts) stays on hold.

## Ranking (2026-10-09, dip/jevtrader session)

1. **D, 14-day cross-sectional momentum on Hyperliquid perps:** test +1.50%/week after costs and
   funding, CI touching zero, 12 rules looked at. **Forward test registered** (52 weeks, free to run).
2. **A1, delta-hedged JLP:** +7.9% APR over USDC, exploratory. **Forward test registered** (90 days,
   data from the `paper-tests` Action).
3. **A2, LST cash-and-carry:** real but decaying to ~0 in 2026; not worth a slot now.
4. **B, crash reversal:** real on Binance only, needs a CEX account; on-chain median −7.6 bps.
5. **A3, funding dispersion:** chosen from 5 pairs, sign flips; weakest.
* (added) **E1, pump.fun revenue surprise -> PUMP perp:** both halves positive after costs, each
  ~1.7 SE, beyond-trend part positive. **Forward test registered** (180 days, hourly Action).
  E1b: the same rule on 8 other buyback tokens is flat (family −0.01%/day), so lower the prior.
* (added) **H, Polymarket biases:** 33 rules, nothing passes (closed).
* (added) **G, HLP holding:** +11–28% a year in recent halves vs a 5% hurdle, thin and decaying.
  **Forward test registered** (180 days, free). Following past-winner vaults: closed.
6. **D2, funding carry across perps:** loses; its reverse is weaker momentum (closed).
* (added) **D3, volatility-scaled 14-day momentum:** val +2.15%, test +2.03%/week after lag, 20 bps and
  funding, both CIs above zero, but 0.87 correlated with D. **Forward test registered** (52 weeks, free).
Closed: C (PumpSwap LP, memecoin shorts), B's lead-lag/seasonality/seconds-scale prediction.


## Judging (2026-10-09 ~20:30 UTC, curve-model retrain thread)

The three lenses the workflow planned, applied to every proposal by one session (not three
independent judges; read it as a structured second opinion on the ranking above). Each lens is
scored 1-5:

* **Economics:** the edge left after *measured* costs (§3.12, §3.19), who pays it, and whether it
  is worth anything at our size.
* **Testability:** free data, time to a decisive answer, and how many rules were looked at first.
* **Fit:** the hard constraints (no CEX account, no private RPC, no Jev, real money only as the
  user directs) and the venues the user would have to be eligible for.

| Proposal | Econ | Test | Fit | Verdict |
|---|---|---|---|---|
| **D** 14-day xs momentum, Hyperliquid perps | 4: +1.50%/week after funding is large; expect shrinkage (12 rules) | 3: free, scored from history, but 52 weeks to decide | 4: one venue, no KYC; ~20 legs need a few hundred $ at HL's $10 minimum | **running** (registered) |
| **A1** delta-hedged JLP | 4: +7.9% APR over USDC, a risk premium with a payer | 3: free; 90 days is short for a CI on a yield spread (the brief itself said 120-180 days would be more decisive) | 3: two venues (Jupiter + Hyperliquid), bridge, liquidation risk on the short | **running** (registered) |
| **E** predictor v3.1 + P(rug) | 2: must clear ~3.5% (Jupiter/own instructions, §3.19) to ~5.5% (Lightning) per round trip; dev 1m loses at every threshold | 5: ~100 trades within days | 5: TARTAR's own assets and route | **running** (registered, scored by 10-12) |
| A2 LST cash-and-carry | 1: excess over USDC +0.3% APR in 2026 | 2: regime-driven, a 90-day test is a coin flip | 3 | drop |
| A3 HL-dYdX funding dispersion | 2: best of 5 pairs, +3.7% excess | 2: sign flips; selection bias | 2: two perp venues | drop |
| B crash reversal | 2: test +33 bps (−6 without its top 3), on-chain mean +4.3 / median −7.6 bps | 1: ~5 events a month, so years to decide | 1: CEX account needed (out of scope) | drop |
| C PumpSwap LP / memecoin shorts | 1 | — | — | closed |

**Result:** the ranking stands. Every proposal that survives all three lenses already has a
registered forward test, and none of the rest earns a slot. The cheapest lever on the running work
is cost, not a new family: E's rule gains ~2 points per round trip if real trades go through
Jupiter or our own instructions instead of Lightning (§3.19). A new study should come from a new
idea with a payer and measured costs, not from re-running these angles.

## F. Pump.fun: who is trading (2026-10-09 ~23:20 UTC, retrain thread)

The coordinator's round under the user's "keep finding things": pump.fun-native signals built on
*who* trades, big enough to beat the ~2.7% (Jupiter / own instructions) to ~5% (Lightning) round
trip. Already closed, and not re-run: copying wallets that won before (§3.15), same-slot sniping and
bundles (§3.18), early-flow features incl. buyer mix, repeat bots, holders, creator history and buy
size (§3.22: movers predictable but they collapse; small creator buys +2 points over buy-all, still
−2.2%), and curve triggers (§3.23: a 70% dip after a 40-SOL run is break-even, −0.3% on test).

**Proposals.** Each conditions on the trader identities in the recorded paths (`exit_study.py
extract` keeps every trade's wallet).

* **F1 Who sold the dip.** §3.23's dip family is the closest rule to break-even. Split its signals by
  who caused the drawdown: the share of sell SOL from the run's peak to the signal that came from the
  creator and the top 3 sellers. Hypothesis: a concentrated dump that has *finished* (those wallets
  hold nothing more, or have stopped selling) leaves no overhang, so the bounce is cleaner than when
  the selling is broad (interest dying).
* **F2 Who buys the dip.** Within the same signals, whether wallets with a causal track record
  (earlier launches only: their buys were followed by a price above cost within 2 min) buy during the
  drawdown. §3.15 found such wallets less bad to follow at launch; the dip is a different context.
* **F3 Overhang left.** At any moment after +60 s, the share of the tokens bought in the first 2 s
  (the bundle) still held by those wallets. Enter when it falls to ~0 while buyers are still
  arriving, i.e. the snipers are out and the token is still alive.
* **F4 Creator reputation.** Serial creators whose earlier launches graduated. Overlaps §3.22's dev
  group (creator's earlier launches and rugs), so low novelty.
* **F5 Holder dispersion.** Gini / top-10 share at +60 s. Overlaps §3.22's holders group, and
  §2's top-10 flag; low novelty.

**Scoring** (one session; the three lenses as in *Judging*, 1-5):

| | Econ | Test | Fit | Note |
|---|---|---|---|---|
| F1 | 3: conditions the only family near zero; needs ≥ +3 points from the split | 4: dev/test split exists, signals already defined, a few dozen variants | 5 | **run** |
| F2 | 2: §3.15's track records never turned positive | 4 | 5 | **run** (cheap beside F1) |
| F3 | 3: new mechanism (overhang), untested | 3: more definitions to choose | 5 | **run** on dev, any time after +60 s |
| F4 | 1: covered by §3.22 | 4 | 5 | drop |
| F5 | 1: covered by §3.22 / §2 | 4 | 5 | drop |

**Protocol.** Explore on dev only (launches created before 16:00 UTC 10-09, as §3.21-3.23).
Anything positive on dev's later half is pre-registered (`handoff/preregistration/who-trades/`)
before the test launches (created ≥ 16:00) are scored once. Paper only, Jupiter costs (1.25%/side,
0.02 SOL) with Lightning (+1%/side) as a second line.

**Result (2026-10-10 ~00:05 UTC):** F2 and F3 found nothing on dev. F1 (a deep dip sold by the
creator and one other wallet) was pre-registered and scored once: **+1.12% [−6.30, +8.49] on 175
test trades at curve fees, −4.69% via Lightning: not confirmed** (profitability §3.25). F is closed.

## I. Pump.fun round 2 on the new recorder data (2026-10-10 ~01:30 UTC, retrain thread): closed

Coordinator's brief under the user's "continue working": another pump.fun / PumpSwap round on the
data added since F. Untested angles after §3.9-3.25 and F (one judge, three lenses):

* **I1, revival entries** (`revival.py`; econ 2, test 3, fit 5): 30-110 min after launch, a token
  that was quiet for 5/10 min and then gets >= 3/6 new buyers within 60 s. **Not observable at any
  useful rate:** the recorder stops following a token after 10 min without trades (`--idle-minutes`
  default), so a 10-min-quiet revival is never seen, and 5-min ones are rare (72 signals in 15,068
  dev launches; with an earlier 20-SOL peak, 20). Every variant with >= 2 trades loses on dev.
  Seeing revivals would need a recorder that keeps idle tokens (`--idle-minutes 120`), which costs
  RPC load for tokens that are almost all dead. Dropped. Output `data/exit-study/revival-dev.txt`.
* **I2, PumpSwap pools after their first hour** (`pumpswap_late.py`; econ 2, test 3, fit 5): §3.16's
  families (momentum, dip, active) at 60/90/120/180 min after graduation, on the 547 pools graduating
  after 12:00 UTC 10-09 that §3.16 never saw (incl. the recorder Action's run), 0.02 SOL, PumpSwap fee
  tiers. Few pools are still trading by then (active >= 50 swaps in 5 min at 90 min: 26 pools in the
  choosing 60%). Best on choosing: +2.8% [−2.1, +8.0] (26) → check −2.8% (8); everything else ≤ 0.
  Closed. Output `data/exit-study/pumpswap-late.txt`.
* Dropped without data work: quote-paired (USDC etc.) curves (V2 curves charge ~3.45%/side incl. a
  2.5% creator fee in samples, §queue 9), the PumpSwap models' candle calls as a trading rule (§3.20's
  result on curves, the same structure, fees 1.20-1.25%/side), graduation and copy-trading variants
  (§3.10, §3.15).

**Nothing pre-registered from I.** The one pump.fun line still open is F1's powered forward test
(`preregistration/who-trades-forward/`, scored after 2026-10-19).

## What looks worth doing when the hunt resumes

1. Pre-register and start the **hedged-JLP 90-day paper forward test** (A1). It needs only an
   hourly poller of free endpoints, about one HTTP call per source per hour. Run the
   GeckoTerminal-hourly diagnostic first.
2. Finish angles C–E. Then judge every proposal (A1–A3, B's crash reversal, and C–E's) under
   the three lenses before choosing a second study.
3. Close in profitability §1: seconds-scale SOL microstructure at our latency, intraday
   seasonality and the LST leverage loop (when the hunt is written up as §3.17).

## Resume: the angle briefs

Each angle gets the hard constraints from `handoff/STATUS.md` (no real money, no Jev,
jevtrader untouched, no private RPC, no deception), the closed list, and the measured costs.

- **C. Memecoin liquidity / short side:**
  - LP income on PumpSwap pools: use the fee split in §3.13 and the recorded swaps in `raw-eager`, `raw-clever` and `raw-v3` to set fee income against impermanent loss;
  - shorting or fading pumped tokens where perps or borrowing exist (memecoin perps on Drift, Jupiter, Hyperliquid);
  - our P(rug) (AUC 0.91) as a short or hedge signal where a short is possible;
  - exit-side signals.
- **D. Established tokens, daily:** cross-sectional momentum and reversal, market-neutral
  against SOL, volume or holder-growth factors, and event studies (CEX or perp listings,
  unlocks). Read §3.11 and `handoff/experiments/established_*.py` first, and mind
  survivorship bias.
- **E. TARTAR's assets:** the calibrated predictor (`tartar/models/*.report.json`), P(rug),
  the free real-time pump.fun and PumpSwap decoder with trader addresses and slots, and the
  recorded data. Which markets have costs below the predicted moves? Is there a market where
  a short exists?
