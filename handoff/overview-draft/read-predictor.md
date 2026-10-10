<!-- read:predictor: workflow section summary as of 2026-10-09 12:56 UTC; 'verify-*' files are fact-checked, 'read-*' are not -->

## The candle predictor: accuracy, models and what was tried

*(As of 2026-10-09 12:56 UTC. Sources: `handoff/candle-prediction-agent.md` (the "predictor doc"), `tartar/models/*.report.json`, `handoff/experiments/predictor-v3/compare-*.json`, `handoff/STATUS.md`, `tartar/train.py`, and git history.)*

### 1. What the predictor is and what "accuracy" means here

The user asked for an agent that watches a live **candle** chart of a new Solana token and predicts the **next candle's closing price**, with an honest confidence. A *candle* is one time bucket (15 s, 30 s, 1 min or 5 min) summarised by its open/high/low/close price. The user later said: "build the highest accuracy predictor that we can. That is this project's only job" (`handoff/candle-prediction-agent.md:16-25`).

The doc defines accuracy in three parts (`handoff/candle-prediction-agent.md:29-39`):
1. **Point error / "edge".** The predicted close is the median of a predicted probability distribution. Its absolute log error is compared with the **naive baseline "close = last price"**. *Edge* = the relative reduction in that error: `1 − MAE/naive_MAE` (`tartar/train.py:235,255`). For example, +5% means the error is 5% smaller than naive. It does **not** mean a 5% return.
2. **Calibration.** The stated confidence should equal the realised hit rate ("the system must never invent conviction"). The **hit rate** is a three-way call (up / down / flat versus the reference price), and the stated confidence is the largest of the three probabilities (`tartar/train.py:242-249`).
3. **Band coverage.** The 80% band should contain the close 80% of the time. Reports also show `band_stated`, the probability mass the model itself puts inside the band (`tartar/train.py:228-230`).

Other metrics:
- **Log loss**, the probabilistic score that decides which model gets installed.
- **Information gain in bits per row** over the label frequencies at the same point of the candle, so that knowing the time elapsed earns nothing (`tartar/train.py:258-261`).

Evaluation is always on **tokens launched after the training data** (a time split by launch: 70% train / 15% validation / 15% test). It also includes a **candle-by-candle replay of the live forecaster** on 300 held-out test tokens, with forecasts locked at the candle open (`handoff/candle-prediction-agent.md:38-39, 200`).

The model predicts at several points within a candle: f = 0, 0.2, 0.4, 0.6, 0.8 and 0.95 of the candle elapsed. f = 0 is "at the open"; later points are "nowcasts" (`handoff/candle-prediction-agent.md:185-187`).

A **"trading" candle** is one where the previous candle traded. This subset replaced "active candles", because filtering on the outcome biased hit rates (`handoff/candle-prediction-agent.md:344-346`).

**Baselines compared against:**
- naive "close = last price"
- the **online-only model** (the per-token fallback)
- the same-f base rate (for information gain)
- the previously installed model, scored on the same test launches. This is the **keep-better rule**: a model is installed only if its test log loss is lower (`handoff/candle-prediction-agent.md:347-348, 369, 464`).

### 2. The models

- **Online per-token model** (`handoff/candle-prediction-agent.md:247-291`). Components:
  - EWMA volatility (a moving average weighted toward recent candles)
  - an ensemble of experts: random walk, drift and three ridge regressions
  - an empirical residual distribution
  - an adaptive-conformal (ACI) band
  - flat-candle odds from a two-state Markov chain

  It is honest, but it **adds no point accuracy**: "its median stays at the last price". It is the fallback wherever no global model exists.
- **Global distributional model** (`handoff/candle-prediction-agent.md:295-298`). One LightGBM (gradient-boosted decision trees) multiclass model with 25 classes: class 0 means "no further move before the close", plus 24 bins of the volatility-scaled move (edges ±0.15…±4). It has exponential tails and **temperature scaling** (one factor that softens or sharpens all probabilities, fitted on validation). It uses about 55 features, including price action, activity, order flow, wallets, creator behaviour, lifecycle (`curve_progress` = real SOL raised / 85, i.e. progress toward **graduation**, when a pump.fun token leaves its **bonding curve**, the automatic price formula, for a PumpSwap pool), forming-candle features and scam/holder features (`handoff/candle-prediction-agent.md:213-230`).
- **Blend.** The live forecaster mixes the global and online distributions with weight σ(logit(p) + D). D is a discounted (0.98) running score difference clipped to ±5. The prior p was 0.8 and has been **0.95** since §8.4 (`handoff/candle-prediction-agent.md:544-547`).
- **Most important feature everywhere:** `p_idle` (time since the last trade in the forming candle). It accounts for 31% of gain in v1, and in v3 39.1% at 1m, 45.5% at 15s, 43.8% at 30s and 22.2% at 5m; `curve_progress` comes second. "Whether anything else trades before the close is the first question" (`handoff/candle-prediction-agent.md:239-243`; `tartar/models/trades-60s.report.json:267-268`; `trades-15s.report.json:267`; `trades-30s.report.json:269`; `trades-300s.report.json:269-270`).

### 3. Results by model version

#### Synthetic and simulated sanity checks
- **Online model on synthetic series:** random walk edge ≈0; AR(1) momentum +2.4%; mean reversion +5.0%; band 80.0–80.3% (`handoff/candle-prediction-agent.md:258-263`).
- **Global model on simulated tokens:** edge +5.1–5.6% at the open. This "only proves the pipeline works" (`handoff/candle-prediction-agent.md:299-302`).

#### Online model on real tokens
- **First version (v0 replay, 117 test tokens): poor.** Hit 28.4% vs 45.7% stated, edge −2.4%; trading candles 18.8% vs 52.1% (`handoff/candle-prediction-agent.md:274-276`).
- **After the 7-finding online-model review**, 300 held-out tokens: hit **79.3% vs 78.8%**, edge **0.0%**; trading **46.0% vs 45.1%**. Before the review it was 50.3% / 49.2%, edge −5.3%; trading 23.4% vs 51.9% (`handoff/candle-prediction-agent.md:281-286`).

#### v0 (first real-data global model, 1m only)
- 786 tokens, 28,884 rows (22,044 train), 33 boosting rounds, temperature 1.045.
- At the open: hit 81.5% vs 81.7%, band 88.1%, edge **+3.7%**, info gain 0.340 bits.
- Live replay on 117 tokens: +1.8% (all) / +2.0% (trading) (`handoff/candle-prediction-agent.md:303-306`).

#### v1 (1m only; installed 2026-10-08, commit `7333656` 2026-10-08 20:19:07)
- **Data:** 3,523 tokens (about 2.7 h of recording) and 154,038 rows: 115,338 train / 22,554 validation / 16,146 test. 54 rounds, temperature 1.128, 8.9 MB (`handoff/candle-prediction-agent.md:307-311, 822`).
- **Raw model on the test split:**

| f | Hit | Stated | 80% band | Band width | Error | Naive | Edge | Info gain (bits) |
|---|---|---|---|---|---|---|---|---|
| 0% | 85.3% | 85.2% | 91.9% | 19.6% | 7.42% | 7.80% | +4.9% | 0.615 |
| 20% | 89.4% | 89.8% | 92.3% | 16.0% | 5.57% | 5.76% | +3.3% | 0.548 |
| 40% | 92.3% | 92.5% | 92.9% | 12.3% | 4.38% | 4.52% | +3.0% | 0.458 |
| 60% | 95.7% | 94.6% | 94.9% | 8.7% | 2.90% | 2.84% | −2.2% | 0.355 |
| 80% | 97.8% | 96.7% | 95.9% | 5.3% | 1.83% | 1.83% | −0.4% | 0.284 |
| 95% | 99.3% | 98.6% | 98.0% | 2.1% | 0.59% | 0.57% | −3.0% | 0.181 |

(`handoff/candle-prediction-agent.md:313-320`)

- **Live replay, 300 test tokens** (`handoff/candle-prediction-agent.md:325-330`):
  - Global + online, all 2,214 candles: hit 86.6% vs 85.5% stated, edge **+7.0%**
  - Trading candles (709): 69.0% vs 64.8%, edge **+7.3%**
- **After the §8.4 calibration fixes:** all candles 86.6% vs 86.4%, edge **+7.5%**; trading 69.0% vs 67.8%, edge **+7.8%**. The live band covers 93.3% and states 91.9% (`handoff/candle-prediction-agent.md:595-601`).
- **v0 → v1:** edge at the open +3.7% → +4.9%; info gain 0.34 → 0.61 bits; live blended edge +1.8% → +7.0%. The test tokens differ, so "treat the size of the gain as approximate, not the direction" (`handoff/candle-prediction-agent.md:333-335`).

#### v2 (1m; installed 2026-10-09 ~01:00 UTC, commit `a08fbc4` 00:56:40)
- **Data:** 5,790 launches, 251,220 rows, from four recorder directories. 55 rounds, temperature 1.116 (`handoff/candle-prediction-agent.md:352-355`).
- **Compared with v1 on v2's test launches** (`handoff/candle-prediction-agent.md:360-367`):

| | v1 | v2 |
|---|---|---|
| Test log loss | 0.4891 | **0.4758** |
| Info gain at the open | 0.578 | **0.609** |
| Hit / stated at the open | 86.0% / 87.6% | 86.2% / 86.8% |
| Live trading hit / stated | 66.6% / 67.5% | 66.9% / 66.3% |
| Edge at the open | **+5.2%** | +3.9% |
| Live edge, all / trading | **+5.6% / +5.9%** | +4.0% / +4.2% |

- v2 was installed because it had the better log loss and calibration. Its point forecast was about 1.5 points worse, and this was *not* the median shrink: giving v2 v1's 0.8 shrink lowered its edge from 3.9% to 3.7%. v2's test set is "later and harder": its own live edge was +4.0%, against +7.5% for v1 on v1's test set (`handoff/candle-prediction-agent.md:369-375`).

#### v2-era models for 15s, 30s and 5m (installed 2026-10-09, commit `a8c6b13` 01:25:08)
Live replay on each model's own 300 test tokens, after the out-of-fold shrink refit (`handoff/candle-prediction-agent.md:406-419`):

| Candle | Launches / rows | Online-only edge | Global+online edge, all / trading | Trading hit vs stated | Raw model at open, hit vs stated |
|---|---|---|---|---|---|
| 15 s | 6,189 / 552k | −0.8% | +3.7% / +4.0% | 59.2% vs 59.7% | 90.8% vs 91.0% |
| 30 s | 6,035 / 360k | −0.5% | +4.2% / +4.5% | 63.5% vs 63.7% | 88.6% vs 89.2% |
| 1 m (v2) | 5,790 / 251k | ≈0 | +4.0% / +4.2% | 66.9% vs 66.3% | 86.2% vs 86.8% |
| 5 m | 3,657 / 75k | 0.0% | +12.0% / +12.1% | 74.0% vs 72.9% | 72.9% vs 76.4% |

The 5m model "has the least data" and its raw distribution was overconfident during the candle (80.6% hit vs 86.1% stated at f = 0.2).

#### v3 (currently installed for all four lengths; installed 07:50 UTC 2026-10-09, commit `b47a328` 07:52:39)
- **Training:** `--num-leaves 31 --min-leaf 2000` (smaller trees, at least 2,000 rows per leaf) on every curve recording: `raw`, `raw-slots`, `raw-slots-processed`, `raw-pumpswap`, `raw-eager` (`handoff/candle-prediction-agent.md:450-455`; `handoff/STATUS.md:74-80`).
- **v2 → v3 on v3's own test launches** (mostly `raw-eager`; `handoff/candle-prediction-agent.md:457-466`; `handoff/experiments/predictor-v3/compare-*.json`):

| Candle | Test log loss | Edge at open | Live edge all / trading | Trading hit vs stated, v3 (v2) |
|---|---|---|---|---|
| 15 s | 0.2899 → **0.2835** | +2.5% → **+3.7%** | +1.6/+1.8% → **+1.8/+1.9%** | 62.3% vs 60.1% (61.4% vs 60.1%) |
| 30 s | 0.3474 → **0.3386** | +4.4% → **+5.6%** | +4.5/+4.8% → +4.4/+4.7% | 65.9% vs 63.6% (64.4% vs 64.1%) |
| 1 m | 0.4253 → **0.4129** | +6.7% → **+9.1%** | +4.7/+5.0% → **+6.2/+6.5%** | 65.5% vs 66.0% (64.6% vs 65.6%) |
| 5 m | 1.1895 → **1.1418** | +5.1% → **+6.9%** | +4.6/+4.6% → **+6.5/+6.5%** | 63.3% vs 68.0% (62.1% vs 70.3%) |

All four passed the keep-better rule. The 1m point edge, v2's weak spot, "is back above v1's". The 30s model gained in log loss and at the open, but not in the live replay.

**Installed v3 headline metrics, from the report files:**

| | 15 s | 30 s | 1 m | 5 m |
|---|---|---|---|---|
| Launches (tokens) | 9,184 | 8,927 | 8,560 | 4,683 |
| Train / valid / test rows | 572,238 / 116,442 / 125,958 | 372,840 / 78,870 / 82,266 | 260,790 / 57,660 / 63,480 | 69,054 / 10,878 / 11,964 |
| Boosting rounds; temperature | 114; 1.041 | 97; 1.047 | 97; 1.055 | 87; 1.175 |
| Trained at (UTC) | 2026-10-09T06:54:01Z | 07:30:36Z | 06:27:59Z | 07:39:30Z |
| Test log loss | 0.2835 | 0.3386 | 0.4129 | 1.1418 |
| **At open:** hit vs stated | 92.4% vs 92.5% | 90.5% vs 90.8% | 87.1% vs 87.9% | **60.9% vs 70.6%** |
| At open: 80% band covers / states | 96.0% / 95.6% | 95.0% / 94.5% | 93.8% / 93.0% | 85.7% / 84.6% |
| At open: band width | 6.1% | 8.3% | 12.0% | 45.0% |
| At open: error vs naive (MAE) | 1.92% vs 1.99% | 2.73% vs 2.89% | 3.92% vs 4.32% | 15.35% vs 16.49% |
| At open: edge | +3.6% | +5.6% | +9.1% | +6.9% |
| At open: info gain (bits/row) | 0.363 | 0.410 | 0.487 | 1.158 |
| Edge at f = 0.2 / 0.4 / 0.6 / 0.8 / 0.95 | +3.3 / +2.9 / +1.8 / +0.3 / 0 | +4.8 / +3.0 / +2.4 / +1.1 / 0 | +6.0 / +2.0 / +0.8 / +0.9 / 0 | +1.9 / −1.4 / −2.4 / +1.8 / 0 |
| Live replay (300 tokens), online only: all edge; trading hit vs stated | −0.2%; 45.3% vs 42.7% | −0.2%; 44.9% vs 42.3% | −0.5%; 44.8% vs 43.7% | −0.0%; 41.3% vs 50.2% |
| Live global+online, all: n; hit vs stated; edge | 16,776; 91.5% vs 91.3%; +1.8% | 8,222; 89.6% vs 89.2%; +4.4% | 4,020; 86.0% vs 85.9%; +6.2% | 911; 61.3% vs 68.6%; +6.5% |
| Live global+online, trading: n; hit vs stated; band covers/states; MAE vs naive; edge | 2,480; 62.3% vs 60.1%; 83.8%/81.4%; 17.17% vs 17.49%; +1.9% | 1,632; 65.9% vs 63.6%; 85.7%/82.0%; 18.11% vs 19.01%; +4.7% | 1,146; 65.5% vs 66.0%; 86.0%/83.1%; 17.43% vs 18.64%; +6.5% | 878; 63.3% vs 68.0%; 87.6%/83.7%; 16.79% vs 17.96%; +6.5% |
| Data capture, median / mean (tokens measured) | 99.1% / 90.9% (8,321) | 99.2% / 90.9% (8,101) | 99.2% / 91.0% (7,778) | 97.8% / 90.7% (4,401) |
| Fitted median shrink at f = 0 … 0.95 | 1, 1, 0.9, 0.8, 0.5, 0 | 1, 1, 0.9, 0.8, 0.6, 0 | 1, 1, 1, 0.8, 0.7, 0 | 1, 1, 1, 1, 1, 0 |

(Sources: `tartar/models/trades-15s.report.json:87-146, 219-264, 288`; `trades-30s.report.json:87-148, 221-266, 290`; `trades-60s.report.json:87-146, 219-265, 288`; `trades-300s.report.json:87-148, 221-266, 290`; shrinks from the `median_shrink` blocks at lines 98/100.)

Notes on the table:
- The edge at f = 0.95 is exactly 0 because the shrink there is 0: the median is set to the current price.
- In the live replay, 15s/30s are about 2 points **under**confident on trading candles, and 5m is clearly **over**confident (`handoff/candle-prediction-agent.md:468-470`).

### 4. What improved accuracy (and what did not)

**Helped:**
- **The global model itself.** The online model alone gives about 0 edge at every timeframe. Adding the global model gives +1.8% to +6.5% live edge in v3 (report files above).
- **More data.**
  - v0 (786 tokens) → v1 (3,523): live edge +1.8% → +7.0%.
  - v2 → v3 (5,790 → 8,560 launches at 1m): test log loss lower at every length; 1m edge at the open +6.7% → +9.1%.
  - Keeping a token's data through short reconnects (instead of cutting it) was a big part of v1's data growth (`handoff/candle-prediction-agent.md:307-311, 175-182`).
- **Smaller trees, many rows per leaf.** Sweep on v2's data (`handoff/experiments/predictor_sweep.py`), validation / test log loss:
  - default 63 leaves / 100 rows: 0.5324 / 0.4629
  - 31 leaves / 1,500 rows: 0.5290 / **0.4583**
  - 31 leaves / 4,000 rows: **0.5286** / 0.4587

  About 1% better on test. Adopted for v3 (`handoff/candle-prediction-agent.md:434-446`).
- **Late-candle median shrink**, which pulls the predicted median toward the current price late in the candle.
  - v1, validation-fitted, test edge before → after: f = 0.6 −2.2 → −0.4; f = 0.8 −0.4 → +0.7; f = 0.95 −3.0 → 0.0 (`handoff/candle-prediction-agent.md:568-580`).
  - Then refitted **out of fold** (3 token-wise folds over train + validation, about 6× the rows). Total test point error: 750.39 vs 750.53 (v1 data); 1218.82 vs 1221.66 (v2 data).
  - 1m: edge at 60% elapsed −2.0% → −1.05%, at 80% −1.5% → −0.4%. 30s live: +3.7/+4.0% → +4.2/+4.5%. 5m at f = 0.2: +2.4% → +6.0% (`handoff/candle-prediction-agent.md:386-396, 413-416`; commits `85a94a9`, `0329d8e`).
- **Calibration fixes (§8.4).** The blend's global prior was raised from 0.8 to 0.95, chosen on 300 validation tokens: trading hit/stated 69.5%/69.8%, direction log loss 0.3086 bits. Band reporting now states the band's own mass (`handoff/candle-prediction-agent.md:581-594`; commit `6aad9de`).
- **Online-model review fixes:**
  - The Markov flat odds alone cut three-way log loss from 1.004 to 0.442 at 1m.
  - Online calibration went from 50.3%/49.2% (edge −5.3%) to 79.3%/78.8% (edge 0.0%) (`handoff/candle-prediction-agent.md:761-769, 281-286`).
- **Old-row weighting at 5m (preview only, nothing installed, 08:30 UTC).** Weighting the old recorder's training rows ×0.25 gave test log loss **1.0578** vs installed v3's 1.1081, hit/stated at the open 69.6% vs 70.3%, and live edge +14.8% vs +12.7% (`handoff/candle-prediction-agent.md:495-508`).

**Did not help / rejected:**
- **Fitting the median shrink on half of validation and scoring on the other half.** No method (per-fraction grid, one global factor, linear in f, bootstrap-bagged) beat "no shrink"; all lost 0.04–0.7% (`handoff/candle-prediction-agent.md:379-385`).
- **Fitting early stopping and temperature only on later-recording validation rows** (for 5m): test log loss 1.1418 → 1.1410, i.e. "changed nothing" (`handoff/candle-prediction-agent.md:490-491`).
- **Down-weighting old rows at 1m / 30s / 15s.** The old rows help there:
  - 1m test: ×1 0.5090 / ×0.25 0.5119 / ×0 0.5220
  - 30s test: 0.4219 / 0.4233 / 0.4318
  - 15s test: 0.3242 / 0.3251 / 0.3290

  Down-weighting is a 5m-only fix (`handoff/candle-prediction-agent.md:510-515`).
- **Re-ordering trades by slot/reserves** (a *slot* is Solana's ~270 ms block unit). Checked and not needed: on 74,438 trades, no 1-minute close changes (`handoff/candle-prediction-agent.md:816-821`).
- **The online ensemble's signals** never earn reliability, so they add no point accuracy (`handoff/candle-prediction-agent.md:288-291`).
- **Using the model as a trading signal** (profitability study). "v1 expected return in top 0.5%" lost **−43.3%** per trade (90% CI −66.7 … −14.6%). "The model is calibrated for direction and bands, not for the size of expected moves" (`handoff/profitability.md:66-80`).

### 5. The scam filter's role in the predictor

- **The scam filter's behavioural signals are also model inputs** (`RISK_FEATURES`): `top10_share`, `log_holders`, `creator_share`, `sniper_share`, `wash_share`, `trades_per_wallet`, `nonstandard_curve`, all computed by the same `WalletTracker` live and offline (`handoff/candle-prediction-agent.md:228-230, 635-636`).
  - In v1, `sniper_share`, `wash_share`, `creator_share` and `trades_per_wallet` each had about 2% of gain (`handoff/candle-prediction-agent.md:239-241`).
  - In v3 at 5m, `sniper_share` has 2.1% and `creator_share` 1.9% (`tartar/models/trades-300s.report.json:275-276`).
- **The risk level** (ok / caution / danger / scam) is shown beside the forecast. The old level barely ranked later collapses (AUC 0.57–0.59; AUC 0.5 = random, 1.0 = perfect ranking); after reweighting it reaches AUC 0.735.
- **P(rug)** is a separate LightGBM classifier judged 20 s after launch. A *rug* is a price ≥80% below the screen price 30 min later, without graduating.
  - Test AUC **0.913**, log loss 0.199 vs base rate 0.317, Brier 0.063, on 791 test launches with a 9.5% rug rate (`handoff/candle-prediction-agent.md:632-672`; `tartar/models/rug-20s.report.json:5-19`).
  - It is "shown, not used to skip". High P(rug) also means more moons: "a warning, not a trading signal" (`handoff/candle-prediction-agent.md:651-652, 677-679`).
- **Simulated-data models are never loaded for real tokens.** `--next-launch` screening picks a "clean" launch to watch (`handoff/candle-prediction-agent.md:625-631, 704-705`).
- Next step 5 ("Add P(rug) as a model feature or output") is half done: it shipped as an output. No source says it was added as a candle-model feature (`handoff/candle-prediction-agent.md:909-910`).

### 6. Open-problems list (predictor doc §12) and status

| # | Problem | Status |
|---|---|---|
| 1 | Incomplete or interrupted trade stream on the public RPC (median 93% / mean 84% capture per token in v1 data; disconnects every ~30 s) | Listed as open. The trade-order sub-item was checked and is **not needed**. The fix was a private RPC, but the user **declined for now** (2026-10-09 06:35 UTC); capture on `raw-eager` is median 100% / mean 97% (`handoff/STATUS.md:59-61`). The v3 reports show median ~98–99%, mean ~91% capture. (`handoff/candle-prediction-agent.md:807-821`) |
| 2 | Too little real data (v1 ~2.7 h, 3,523 launches) | Partly addressed: v3 uses 4,683–9,184 launches. Still open: calibration per token age and capture bucket was not reported (`handoff/candle-prediction-agent.md:822-824`) |
| 3 | Bands over-cover | **Resolved**: the band is calibrated to its stated mass; the excess is the "no further trade" mass. Small remaining live gap: 93.3% vs 91.9%, trading 86.5% vs 83.6% (`:825-828`) |
| 4 | In-candle median worse than "price now" | **Mostly resolved** by the shrink. The underlying downward location bias for very active tokens late in a candle remains (`:829-832`) |
| 5 | Blend underconfident on trading candles | **Mostly resolved**: prior 0.95, 69.0% vs 67.8% (`:833-834`). New: on `raw-clever` test launches the 1m blend is **under**confident again (69% hit vs 64% stated) (`:515-517`) |
| 6 | Scam risk level needs rework | **Done 2026-10-09** (P(rug) + reweighted level) (`:835-858`) |
| 7 | Graduated tokens only through DexScreener polls | **Done**: watch follows the PumpSwap pool. The PumpSwap model code exists (§8.2.3), "trained once data allows"; no `pumpswap-*` model is in `tartar/models/` (`:859-877, 519-540`) |
| 8 | Candle-only (OHLCV) model untrained (GeckoTerminal 429s) | **Open** (`:878-884`) |
| 9 | Only a 1m model | **Done**: 15s, 30s, 1m, 5m. Other lengths use the online model alone; the σ prior above 1m is "a guess" (`:885-889`) |
| 10 | GeckoTerminal live polling closes candles 75 s late | **Open** (`:890-891`) |

Also open: the **5m overconfidence** (§8.2.2c).
- At the open it states 70.6% and hits 60.9%.
- Diagnosis: the old recorder's rows are about 75% of 5m training rows. They had "no trade" at the open 78% of the time, vs 36–43% in later recordings.
- **Plan for v3.1:** 15s/30s/1m on every recording at full weight; 5m with the old-row weight chosen on validation from a grid (1, 0.5, 0.25, 0.1, 0) once `raw-clever` has more hours (`handoff/candle-prediction-agent.md:468-493, 514-515`).
- STATUS lists predictor v3.1 as a later step for the clever session (`handoff/STATUS.md:39-40`).

Next-steps experiments not yet reported as done (`handoff/candle-prediction-agent.md:902-908`): bin edges, a 0.99 fraction, per-age models, dropping noisy features, weighting evaluation by trading candles. Only the hyperparameter part has been done (the sweep).

### 7. The honest ceiling: how predictable are new-token candles?

- **High hit rates are mostly "flat" calls.** "High hit rates come mostly from correctly calling 'flat' on quiet tokens" (`handoff/candle-prediction-agent.md:336`). Only 42% of 1-minute candles of young tokens have any trade, and the median absolute 1-minute move on traded candles is about 13% (`:152-153`). The dominant feature is `p_idle`, i.e. whether anything trades at all.
- **On candles where the token is trading**, the v3 live blend hits 62–66%. This is a three-way call; the online-only model hits 41–45%. The point error is still about **17–18% of price at the open**, vs 17.5–19.0% for naive (`tartar/models/trades-*.report.json` live_at_open blocks).
- **The point forecast is only a few percent better than "no change":**
  - v3 live edge: +1.8% (15s), +4.4% (30s), +6.2% (1m), +6.5% (5m)
  - raw-model edge at the open: +3.6% to +9.1%
  - edge at f = 0.95: 0, and around 0 to ±2% from f = 0.6 on
- **Results depend on which launches are tested.** v1 reached +7.5% live on its test set, but v2's later test set was "harder" (+4.0%). 5m calibration drifts by recording period (−2 points at 00–02 UTC, −5 to −9 points at 04–08 UTC) (`handoff/candle-prediction-agent.md:374-375, 487-488`).
- **The online model, which works without a trained global model, has about 0 edge.** The README says: "Next-candle moves of young memecoins are mostly noise ... its confidence stays near 50% instead of inventing conviction". It also says the edge vs naive "is close to 0% on most tokens most of the time" (`README.md:198-203`).
- **Information gain over the base rate** is 0.36–0.49 bits per row at the open for 15s–1m, and 1.16 bits at 5m (v3 reports).
- **Moves skew down:** P(up | move) ≈ 0.38–0.41 (`handoff/candle-prediction-agent.md:799-800`).
- **Not tradable:** "No strategy tested is profitable at realistic costs ... Treat the dashboard's 'predicted close' and confidence as measurement, not as trade signals". The median round trip costs −3.5% (`handoff/profitability.md:9-13, 60-64`).

### 8. Timeline (git)

| Commit | Time | Change |
|---|---|---|
| `1db2ce7` | 2026-10-08 05:58 | Live next-candle predictor agent |
| `05ac2e8` | 06:28 | Global model + recording pipeline |
| `08aca15` | 18:49 | First real-data model + handoff |
| `7333656` / `7f6cf0e` | 20:19 | Online-model calibration fix, v1 installed |
| `6aad9de` | 23:43 | Band reporting, late-candle median, blend weight |
| `a08fbc4` | 2026-10-09 00:56 | v2 |
| `b5f9232` | 01:09 | Shrink study |
| `a8c6b13` | 01:25 | 15s / 30s / 5m models |
| `85a94a9` / `0329d8e` | 04:43 / 04:55 | Out-of-fold shrink |
| `e56036e` | 05:32 | PumpSwap model code |
| `07e60c1` | 07:13 | P(rug) |
| `b47a328` | 07:52 | v3 for all four lengths |
| `bd21636` / `2ee5eab` | 07:56 / 08:04 | 5m diagnosis |
| `fd2d6e2`, `ff27f16`, `643117d`, `4963238` | 08:08–09:00 | Old-row weighting previews (5m, 1m, 30s) |
| `6a6b1a8` | 12:55:43 | Predictor session moves to an "edge hunt" and the project overview (`handoff/STATUS.md:42-45`) |

**Doc staleness to note:** the doc's "Status in one screen" row still quotes v1's real-data result, and §15 still names v1 as the installed model. The v3 sections (§2 row "Global models", §8.2.2c) are current (`handoff/candle-prediction-agent.md:47-48, 960-962`).

## Open items
- 5m model overconfident on newer launches (states 70.6% at the open, hits 60.9%); fix planned as v3.1 with the old-recorder row weight chosen on validation from a grid (1, 0.5, 0.25, 0.1, 0) once raw-clever has more hours (handoff/candle-prediction-agent.md:468-508).
- Predictor v3.1 plan: retrain 15s/30s/1m on every recording at full weight, 5m with down-weighted old rows; listed as a later step for the clever session after the 11a evaluation (handoff/candle-prediction-agent.md:514-515; handoff/STATUS.md:39-40).
- 1m live blend underconfident on raw-clever trading candles (69% hit vs 64% stated); check the blend's 0.95 global prior on new-style data when v3.1 is trained (handoff/candle-prediction-agent.md:515-517).
- Open problem 1: lossy/interrupted public RPC stream (missed trades remain the problem; private RPC declined by the user for now) (handoff/candle-prediction-agent.md:807-821; handoff/STATUS.md:59-61).
- Open problem 2: more data; calibration per token age and per capture bucket not yet checked (handoff/candle-prediction-agent.md:822-824).
- Open problem 4 residue: a downward location bias of the continuous part for very active tokens late in a candle remains (handoff/candle-prediction-agent.md:829-832).
- Open problem 8: candle-only (OHLCV) model is untrained (GeckoTerminal HTTP 429 from this container) (handoff/candle-prediction-agent.md:878-884).
- Open problem 9 residue: the trades-domain sigma prior above 1m is a guess; timeframes other than 15s/30s/1m/5m use the online model alone (handoff/candle-prediction-agent.md:885-889).
- Open problem 10: GeckoTerminal live polling closes candles 75 s late (handoff/candle-prediction-agent.md:890-891).
- PumpSwap post-graduation model is coded but not trained or installed (handoff/candle-prediction-agent.md:519-540).
- Next-step experiments not yet reported: bin edges, a 0.99 fraction near the close, per-age models, dropping noisy features, weighting evaluation by trading candles; P(rug) as a candle-model feature (handoff/candle-prediction-agent.md:902-910).
- Remaining small live band gap: covers 93.3% vs states 91.9% (trading 86.5% vs 83.6%) (handoff/candle-prediction-agent.md:825-828).
- Handoff doc staleness: the 'Status in one screen' real-data row and section 15 still describe v1 as the installed model, while v3 is installed (handoff/candle-prediction-agent.md:48, 960-962).
