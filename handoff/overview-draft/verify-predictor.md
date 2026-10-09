<!-- verify:predictor: workflow section summary as of 2026-10-09 12:56 UTC; 'verify-*' files are fact-checked, 'read-*' are not -->

## The candle predictor: accuracy, models and what was tried

*(As of 2026-10-09 12:56 UTC, repo HEAD `6a6b1a8` at 12:55:43. Sources: `handoff/candle-prediction-agent.md` (the "predictor doc"), `tartar/models/*.report.json`, `handoff/experiments/predictor-v3/compare-*.json`, `handoff/STATUS.md`, `tartar/train.py`, `handoff/profitability.md`, `README.md`, and git history.)*

### 1. What the predictor is and what "accuracy" means here

The user asked for an agent that watches a live **candle** chart of a new Solana token and predicts the **next candle's closing price**, with an honest confidence. A *candle* is one time bucket (15 s, 30 s, 1 min or 5 min) summarised by its open, high, low and close prices. The user later added: "Do anything you need to do to build the highest accuracy predictor that we can. That is this project's only job" (`handoff/candle-prediction-agent.md:16-25`).

The doc defines accuracy in three parts (`handoff/candle-prediction-agent.md:29-39`):
1. **Point error and "edge".** The predicted close is the median of a predicted probability distribution. Its absolute log error is compared with the **naive baseline "close = current price"** (`naive = |ln(close/price_now)|`). *Edge* is the relative reduction in error: `1 − MAE/naive_MAE`, where MAE is the mean absolute error (`tartar/train.py:234-235, 255`). For example, +5% means the error is 5% smaller than naive. It does **not** mean a 5% return.
2. **Calibration.** The stated confidence should equal the realised hit rate: "the system must never invent conviction". The hit rate scores a three-way call (up, down or flat versus the reference price). The stated confidence is the largest of the three probabilities (`tartar/train.py:227-233, 248-249`).
3. **Band coverage.** The 80% band should contain the close 80% of the time. Reports also show `band_stated`, the probability the model itself puts inside the band (`tartar/train.py:224-226, 251`).

Other metrics:
- **Log loss.** A score for the whole predicted distribution; lower is better. The **keep-better rule** uses it: a new model is installed only if its log loss on the test launches is lower than the installed model's (`tartar/train.py:329-334`; `handoff/candle-prediction-agent.md:347-348, 369, 464`).
- **Information gain** in bits per row over the label frequencies at the same point of the candle, taken from the training split. Knowing how much of the candle has elapsed therefore earns nothing (`tartar/train.py:258-261, 294-298`).

**How it is evaluated:**
- Always on **tokens launched after the training data** (split by launch time: 70% train, 15% validation, 15% test).
- Plus a **candle-by-candle replay of the live forecaster** on the first 300 test tokens, with forecasts locked at the candle open (`handoff/candle-prediction-agent.md:38-39, 199-200`; `tartar/train.py:311-312`).
- Rows are weighted: dead stretches of 5+ flat candles are subsampled to 10% and weighted ×10.
- Training and evaluation imitate live conditions. The creator is hidden for 30% of tokens and the launch time for 15%. 30% of tokens get a "late-join" view, as if the watch started mid-life (`handoff/candle-prediction-agent.md:191-198`).

The model predicts at several points within a candle: f = 0, 0.2, 0.4, 0.6, 0.8 and 0.95 of the candle elapsed. f = 0 is "at the open"; later points are in-candle "nowcasts" (`handoff/candle-prediction-agent.md:109, 185-187`).

A **"trading" candle** is one where the previous candle traded, which is known when the forecast is made. This subset replaced "active candles", because filtering on the outcome biased hit rates (`handoff/candle-prediction-agent.md:344-346`; `tartar/train.py:269-271`).

**Baselines compared against:**
- naive "close = current price"
- the **online-only model** (the per-token fallback)
- the same-f base rate (for information gain)
- the previously installed model, scored on the same test launches (keep-better rule). Exception: v0 was replaced by v1 with `--force`, without that comparison (`handoff/candle-prediction-agent.md:340-342`).

### 2. The models

- **Online per-token model** (`handoff/candle-prediction-agent.md:247-291, 761-800`). Components:
  - EWMA volatility (an average weighted toward recent candles)
  - an ensemble of experts: random walk, drift and three ridge regressions
  - an empirical residual distribution
  - an adaptive-conformal (ACI) band, which widens or narrows itself to hit its coverage target
  - flat-candle odds from a two-state Markov chain (the chance of a flat candle depends on whether the last one traded)

  It adds **no point accuracy**: "its median stays at the last price". It is the fallback wherever no global model exists. It was calibrated on v1's 1m replay. In v3's 5m replay, however, it is **overconfident**: all candles 40.1% hit vs 51.8% stated; trading 41.3% vs 50.2% (`tartar/models/trades-300s.report.json:222-243`).
- **Global distributional model** (`handoff/candle-prediction-agent.md:295-298`).
  - One LightGBM model (gradient-boosted decision trees) with 25 classes: class 0 means "no further move before the close", plus 24 bins of the volatility-scaled move (edges ±0.15…±4).
  - Exponential tails, plus **temperature scaling**: one factor fitted on validation that softens or sharpens all probabilities.
  - 55 features (`handoff/candle-prediction-agent.md:213-230`; `tartar/models/trades-60s.report.json:5-61`): price action, activity, order flow, wallets, creator behaviour, forming-candle features and scam/holder features.
  - Lifecycle features include `curve_progress` = real SOL raised / 85, i.e. progress toward **graduation**. Graduation is when a pump.fun token leaves its **bonding curve** (the automatic price formula) for a PumpSwap pool.
- **Blend.** The live forecaster mixes the global and online distributions with weight σ(logit(p) + D). D is the discounted (0.98) sum of per-candle log-score differences, clipped to ±5. The prior p was 0.8 and has been **0.95** since §8.4 (`handoff/candle-prediction-agent.md:544-547`).
- **Most important feature:** `p_idle` (time since the last trade in the forming candle). "Whether anything else trades before the close is the first question" (`handoff/candle-prediction-agent.md:239-243`).
  - v1: 31% of gain.
  - v3: 45.5% at 15s, 43.8% at 30s, 39.1% at 1m, 22.2% at 5m.
  - `curve_progress` is second at 30s (7.8%), 1m (10.35%) and 5m (17.6%). At 15s, `range` (8.6%) and `idle` (5.9%) rank above it (5.65%) (`tartar/models/trades-15s.report.json:267-270`; `trades-30s.report.json:269-270`; `trades-60s.report.json:267-268`; `trades-300s.report.json:269-270`).

### 3. Results by model version

#### Synthetic and simulated sanity checks
- **Online model on synthetic series** (first version): random walk edge ≈0; AR(1) momentum +2.4%; mean reversion +5.0%; band 80.0–80.3% (`handoff/candle-prediction-agent.md:254-263`).
- **Global model on simulated tokens:** edge +5.1–5.6% at the open. This "only proves the pipeline works" (`handoff/candle-prediction-agent.md:299-302`).

#### Online model on real tokens
- **First version (v0 replay, 117 test tokens): poor.** Hit 28.4% vs 45.7% stated, edge −2.4%; trading candles 18.8% vs 52.1% (`handoff/candle-prediction-agent.md:274-276`).
- **After the 7-finding online-model review** (300 held-out v1 test tokens):
  - Before the review: 50.3% hit vs 49.2% stated, edge −5.3%; trading 23.4% vs 51.9%.
  - After: hit **79.3% vs 78.8%**, edge **0.0%**; trading **46.0% vs 45.1%** (`handoff/candle-prediction-agent.md:281-286`).

#### v0 (first real-data global model, 1m only)
- 786 tokens, 28,884 rows (22,044 train), 33 boosting rounds, temperature 1.045.
- At the open: hit 81.5% vs 81.7%, band 88.1%, edge **+3.7%**, information gain 0.340 bits.
- Live replay on 117 tokens: +1.8% (all) / +2.0% (trading) (`handoff/candle-prediction-agent.md:303-306`).

#### v1 (1m only; installed 2026-10-08, commit `7333656`, 20:19:07)
- **Data:** 3,523 tokens (about 2.7 h of recording) and 154,038 rows: 115,338 train / 22,554 validation / 16,146 test. 54 rounds, temperature 1.128, 8.9 MB. The data grew for two reasons: short reconnects no longer ended a token's window, and a second recording run was added (`handoff/candle-prediction-agent.md:307-311, 822`).
- **Raw model on the test split (first report):**

| f | Hit | Stated | 80% band | Band width | Error | Naive | Edge | Info gain (bits) |
|---|---|---|---|---|---|---|---|---|
| 0% | 85.3% | 85.2% | 91.9% | 19.6% | 7.42% | 7.80% | +4.9% | 0.615 |
| 20% | 89.4% | 89.8% | 92.3% | 16.0% | 5.57% | 5.76% | +3.3% | 0.548 |
| 40% | 92.3% | 92.5% | 92.9% | 12.3% | 4.38% | 4.52% | +3.0% | 0.458 |
| 60% | 95.7% | 94.6% | 94.9% | 8.7% | 2.90% | 2.84% | −2.2% | 0.355 |
| 80% | 97.8% | 96.7% | 95.9% | 5.3% | 1.83% | 1.83% | −0.4% | 0.284 |
| 95% | 99.3% | 98.6% | 98.0% | 2.1% | 0.59% | 0.57% | −3.0% | 0.181 |

(`handoff/candle-prediction-agent.md:313-320`. After the §8.4 shrink, the edge at the open became +4.7%: `:48, 579-580`.)

- **Live replay, 300 test tokens** (`handoff/candle-prediction-agent.md:325-330`):
  - global + online, all 2,214 candles: hit 86.6% vs 85.5% stated, edge **+7.0%**
  - trading candles (709): 69.0% vs 64.8%, edge **+7.3%**
- **After the §8.4 calibration fixes** (`handoff/candle-prediction-agent.md:595-601`):
  - all candles: 86.6% vs 86.4%, edge **+7.5%**
  - trading candles: 69.0% vs 67.8%, edge **+7.8%**
  - live band covers 93.3% and states 91.9%
- **v0 → v1:** edge at the open +3.7% → +4.9%; information gain 0.34 → 0.61 bits; live blended edge +1.8% → +7.0%. The test tokens differ, so "treat the size of the gain as approximate, not the direction". v1 also changed how volatility is measured and came with the online-model fixes, so the gain is not from data alone (`handoff/candle-prediction-agent.md:333-342`).

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

- v2 was installed by the keep-better rule, which looks at **test log loss only**. It was also better calibrated, but its point forecast was ~1.5 points worse on these launches.
- The gap is *not* the median shrink: giving v2 v1's 0.8 shrink lowered its edge from 3.9% to 3.7%.
- v2's test set is "later and harder": v2's own live edge was +4.0%, against +7.5% for v1 on v1's test set (`handoff/candle-prediction-agent.md:369-375`).

#### v2-era models for 15s, 30s and 5m (installed 2026-10-09, commit `a8c6b13` 01:25:08)
Live replay on each model's own 300 test tokens, after the out-of-fold shrink refit (`handoff/candle-prediction-agent.md:406-419`):

| Candle | Launches / rows | Online-only edge | Global+online edge, all / trading | Trading hit vs stated | Raw model at open, hit vs stated |
|---|---|---|---|---|---|
| 15 s | 6,189 / 552k | −0.8% | +3.7% / +4.0% | 59.2% vs 59.7% | 90.8% vs 91.0% |
| 30 s | 6,035 / 360k | −0.5% | +4.2% / +4.5% | 63.5% vs 63.7% | 88.6% vs 89.2% |
| 1 m (v2) | 5,790 / 251k | ≈0 | +4.0% / +4.2% | 66.9% vs 66.3% | 86.2% vs 86.8% |
| 5 m | 3,657 / 75k | 0.0% | +12.0% / +12.1% | 74.0% vs 72.9% | 72.9% vs 76.4% |

The 5m model "has the least data", and its raw distribution was overconfident during the candle (80.6% hit vs 86.1% stated at f = 0.2).

**Do not compare this table directly with the v3 numbers below:** they use different, newer test launches. On v3's test launches the same v2-era models score +1.6% (15s) and +4.6% (5m) live edge, not +3.7% and +12.0% (`handoff/experiments/predictor-v3/compare-15s.json`, `compare-300s.json`).

#### v3 (installed for all four lengths; installed 07:50 UTC 2026-10-09, commit `b47a328` 07:52:39)
- **Training:** `--num-leaves 31 --min-leaf 2000` (smaller trees, at least 2,000 rows per leaf) on every bonding-curve recording: `raw`, `raw-slots`, `raw-slots-processed`, `raw-pumpswap`, `raw-eager`. These settings are recorded in each model's `.json` metadata (`handoff/candle-prediction-agent.md:450-455`; `handoff/STATUS.md:74-80`).
- **v2 → v3 on v3's own test launches** (mostly `raw-eager`; `handoff/candle-prediction-agent.md:457-466`; `handoff/experiments/predictor-v3/compare-*.json`):

| Candle | Test log loss | Edge at open | Live edge all / trading | Trading hit vs stated, v3 (v2) |
|---|---|---|---|---|
| 15 s | 0.2899 → **0.2835** | +2.5% → **+3.7%** (3.65%) | +1.6/+1.8% → **+1.8/+1.9%** | 62.3% vs 60.1% (61.4% vs 60.1%) |
| 30 s | 0.3474 → **0.3386** | +4.4% → **+5.6%** | +4.5/+4.8% → +4.4/+4.7% | 65.9% vs 63.6% (64.4% vs 64.1%) |
| 1 m | 0.4253 → **0.4129** | +6.7% → **+9.1%** | +4.7/+5.0% → **+6.2/+6.5%** | 65.5% vs 66.0% (64.6% vs 65.6%) |
| 5 m | 1.1895 → **1.1418** | +5.1% → **+6.9%** | +4.6/+4.6% → **+6.5/+6.5%** | 63.3% vs 68.0% (62.1% vs 70.3%) |

- All four passed the keep-better rule.
- The 1m point edge, v2's weak spot, "is back above v1's".
- The 30s model gained in log loss and at the open, but not in the live replay.
- v3 changed two things at once, more data and smaller trees, and the doc does not separate their effects.

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
| Live replay (300 tokens), online only: all edge; trading hit vs stated | −0.2%; 45.3% vs 42.7% | −0.2%; 44.9% vs 42.3% | −0.5%; 44.8% vs 43.7% | −0.0%; 41.3% vs 50.2% (all: 40.1% vs 51.8%) |
| Live global+online, all: n; hit vs stated; edge | 16,776; 91.5% vs 91.3%; +1.8% | 8,222; 89.6% vs 89.2%; +4.4% | 4,020; 86.0% vs 85.9%; +6.2% | 911; 61.3% vs 68.6%; +6.5% |
| Live global+online, trading: n; hit vs stated; band covers/states; MAE vs naive; edge | 2,480; 62.3% vs 60.1%; 83.8%/81.4%; 17.17% vs 17.49%; +1.9% | 1,632; 65.9% vs 63.6%; 85.7%/82.0%; 18.11% vs 19.01%; +4.7% | 1,146; 65.5% vs 66.0%; 86.0%/83.1%; 17.43% vs 18.64%; +6.5% | 878; 63.3% vs 68.0%; 87.6%/83.7%; 16.79% vs 17.96%; +6.5% |
| Data capture, median / mean (tokens measured) | 99.1% / 90.9% (8,321) | 99.2% / 90.9% (8,101) | 99.2% / 91.0% (7,778) | 97.8% / 90.7% (4,401) |
| Fitted median shrink at f = 0 … 0.95 | 1, 1, 0.9, 0.8, 0.5, 0 | 1, 1, 0.9, 0.8, 0.6, 0 | 1, 1, 1, 0.8, 0.7, 0 | 1, 1, 1, 1, 1, 0 |

(Sources: `tartar/models/trades-15s.report.json:87-146, 219-264, 288`; `trades-30s.report.json:87-148, 221-266, 290`; `trades-60s.report.json:87-146, 219-265, 288`; `trades-300s.report.json:87-148, 221-266, 290`; shrinks from the `median_shrink` blocks at lines 98/100.)

Notes on the table:
- The edge at f = 0.95 is 0 because the shrink there is 0, so the median equals the current price. This is inferred from the table: MAE equals naive MAE there.
- "Data capture" is the share of recorded trades whose predecessor trade was also recorded (1.0 = complete stream).
- In the live replay, 15s and 30s are about 2 points **under**confident on trading candles, and 5m is clearly **over**confident (`handoff/candle-prediction-agent.md:468-470`).
- The 5m figures rest on a small sample: 1,994 test rows per fraction and 911 live candles.
- Information gain is not comparable across candle lengths. 5m candles are rarely flat, so their outcomes are more spread out and the base rate is weaker.

### 4. What improved accuracy (and what did not)

**Helped:**
- **The global model itself.** The online model alone gives about 0 edge at every timeframe. Adding the global model gives +1.8% to +6.5% live edge in v3 (report files above).
- **More data plus model changes, with caveats.**
  - v0 (786 tokens) → v1 (3,523): live edge +1.8% → +7.0%. v1 also changed how volatility is measured and came with the online fixes, and the test tokens differ (`handoff/candle-prediction-agent.md:333-342`).
  - v1 → v2 (5,790 launches): better log loss, but a ~1.5-point *worse* point edge on the same launches (`:360-375`).
  - v2 → v3 (5,790 → 8,560 launches at 1m, plus smaller trees): log loss lower at every length; 1m edge at the open +6.7% → +9.1% (`:457-466`).
- **Smaller trees, many rows per leaf.** Sweep on v2's data (6,107 tokens / 264k rows; `handoff/experiments/predictor_sweep.py`), validation / test log loss:
  - default 63 leaves / 100 rows: 0.5324 / 0.4629
  - 31 leaves / 1,500 rows: 0.5290 / **0.4583**
  - 31 leaves / 4,000 rows: **0.5286** / 0.4587

  About 1% better on test. 31 leaves / 2,000 rows was adopted for v3 (`handoff/candle-prediction-agent.md:434-446`).
- **Late-candle median shrink.** This pulls the predicted median toward the current price late in the candle.
  - v1, fitted on validation, test edge before → after (`handoff/candle-prediction-agent.md:568-580`):
    - f = 0: +4.9 → +4.7
    - f = 0.2: +3.3 → +3.8
    - f = 0.6: −2.2 → −0.4
    - f = 0.8: −0.4 → +0.7
    - f = 0.95: −3.0 → 0.0
  - It was then refitted **out of fold**: 3 folds split by token over train + validation, so each median is predicted by a model that did not see that token. That gives about 6× the rows. Total test point error: 750.39 vs 750.53 (v1 data); 1218.82 vs 1221.66 (v2 data).
  - Effects: 1m edge at 60% elapsed −2.0% → −1.05% and at 80% −1.5% → −0.4%; 30s live edge +3.7/+4.0% → +4.2/+4.5%; 5m edge at f = 0.2 +2.4% → +6.0% (`handoff/candle-prediction-agent.md:386-396, 413-416`; commits `85a94a9`, `0329d8e`).
- **Calibration fixes (§8.4).** The blend's global prior was raised from 0.8 to 0.95, chosen on 300 validation tokens: trading hit/stated 69.5%/69.8%, direction log loss 0.3086 bits. Band reporting now states the band's own mass (`handoff/candle-prediction-agent.md:581-594`; commit `6aad9de`).
- **Online-model review fixes:**
  - The reviewer's Markov flat-odds patch alone cut three-way log loss from 1.004 to 0.442 at 1m.
  - Online calibration went from 50.3%/49.2% (edge −5.3%) to 79.3%/78.8% (edge 0.0%) (`handoff/candle-prediction-agent.md:761-769, 281-286`).

**Promising but not adopted:**
- **Old-row weighting at 5m** (preview, 08:30 UTC, nothing installed). The preview's own test launches add `raw-clever` (5,414 tokens) and differ from v3's report. On them, installed v3 scores test log loss 1.1081, hit 64.6% vs 69.9% stated at the open, live edge +12.7%. Results by old-row weight:
  - ×1: log loss 1.0729
  - ×0.25: log loss **1.0578**, hit/stated 69.6%/70.3%, live edge +14.8%
  - ×0: best on validation (1.0674 vs 1.0711 for ×0.25), but it trains on ~9% of the rows and live edge falls to +9.2%

  The weight is to be chosen **on validation** from a grid once `raw-clever` has more hours (`handoff/candle-prediction-agent.md:495-508`).

**Did not help / rejected:**
- **Fitting the median shrink on half of validation and scoring on the other half.** No method (per-fraction grid, one global factor, linear in f, bootstrap-bagged) beat "no shrink"; all lost 0.04–0.7% (`handoff/candle-prediction-agent.md:379-385`).
- **Fitting early stopping and temperature only on later-recording validation rows** (5m): test log loss 1.1418 → 1.1410, i.e. it "changed nothing" (`handoff/candle-prediction-agent.md:490-491`).
- **Down-weighting old rows at 1m, 30s and 15s.** The old rows help there. Test log loss at weight ×1 / ×0.25 / ×0:
  - 1m: 0.5090 / 0.5119 / 0.5220
  - 30s: 0.4219 / 0.4233 / 0.4318
  - 15s: 0.3242 / 0.3251 / 0.3290

  Down-weighting is a 5m-only fix (`handoff/candle-prediction-agent.md:510-515`; the 15s line was added in commit `aead3ef`, 10:01 UTC).
- **Re-ordering trades by slot or reserves.** A *slot* is Solana's ~270 ms block unit. Checked on `raw-slots` (74,438 trades) and not needed: no 1-minute close changes (`handoff/candle-prediction-agent.md:816-821`).
- **The online ensemble's signals** never earn reliability, so they add no point accuracy (`handoff/candle-prediction-agent.md:288-291`).
- **Using the model as a trading signal** (backtest on recorded v1 data with modelled costs, not real fills). Trading the top 0.5% of "v1 expected return" with a 60 s exit lost **−43.3%** per trade (38 test trades; 90% CI −66.7 … −14.6%). "The model is calibrated for direction and bands, not for the size of expected moves" (`handoff/profitability.md:67-82`).

### 5. The scam filter's role in the predictor

- **The scam filter's behavioural signals are also model inputs** (`RISK_FEATURES`): `top10_share`, `log_holders`, `creator_share`, `sniper_share`, `wash_share`, `trades_per_wallet` and `nonstandard_curve`. The same `WalletTracker` computes them live and offline (`handoff/candle-prediction-agent.md:228-230, 635-636`).
  - In v1, `sniper_share`, `wash_share`, `creator_share` and `trades_per_wallet` each had about 2% of gain (`handoff/candle-prediction-agent.md:239-241`).
  - In v3 at 5m, `sniper_share` has 2.1% and `creator_share` 1.9% (`tartar/models/trades-300s.report.json:275-276`). At 1m each is ~1.1–1.3%.
- **The risk level** (ok / caution / danger / scam) is shown beside the forecast.
  - The old level barely ranked later collapses: AUC 0.57–0.59. AUC measures ranking: 0.5 is random, 1.0 is perfect.
  - After reweighting it reaches AUC 0.735 (`handoff/candle-prediction-agent.md:632-636`).
- **P(rug)** is a separate LightGBM classifier, judged 20 s after launch. A *rug* means that 30 min after that point the price is ≥80% below the price at the 20 s judgement and the token has not graduated.
  - Test results: AUC **0.913**; log loss 0.199 vs 0.317 for the base rate; Brier score (mean squared probability error) 0.063. Measured on 791 test launches with a 9.5% rug rate (`handoff/candle-prediction-agent.md:640-662`; `tartar/models/rug-20s.report.json:5-19`).
  - It is calibrated by decile except the top one (56% predicted, 44% observed).
  - It is "shown, not used to skip". High P(rug) also means more moons: "a warning, not a trading signal" (`handoff/candle-prediction-agent.md:651-652, 672, 677-679`).
- **Models trained on simulated data are never loaded for real tokens.** `--next-launch` screening picks a "clean" launch to watch (`handoff/candle-prediction-agent.md:625-631, 704-705`).
- Next step 5 ("Add P(rug) as a model feature or output") is half done: it shipped as an output. The v3 feature list does not include it (`handoff/candle-prediction-agent.md:909-910`; `tartar/models/trades-60s.report.json:5-61`).

### 6. Open-problems list (predictor doc §12) and status

| # | Problem | Status |
|---|---|---|
| 1 | Incomplete or interrupted trade stream from the public RPC (the free Solana node service): median 93% / mean 84% capture per token in v1 data; disconnects every ~30 s | **Open.** The trade-order sub-item was checked and is **not needed**. The proposed fix, a private RPC, was **declined by the user for now** (2026-10-09 06:35 UTC). Capture on `raw-eager` is median 100% / mean 97% (`handoff/STATUS.md:61-63`). The v3 reports show median 97.8–99.2% and mean ~91% capture (`handoff/candle-prediction-agent.md:807-821`) |
| 2 | Too little real data (v1: ~2.7 h, 3,523 launches) | **Partly addressed:** v3 uses 4,683–9,184 launches. Still unchecked: calibration by token age and by capture bucket (`:822-824`) |
| 3 | Bands over-cover | **Resolved:** the band matches its stated mass; the excess over 80% is the "no further trade" probability. A small live gap remains: 93.3% vs 91.9%, trading 86.5% vs 83.6% (`:825-828`) |
| 4 | In-candle median worse than "price now" | **Mostly resolved** by the shrink. A downward location bias for very active tokens late in a candle remains (`:829-832`) |
| 5 | Blend underconfident on trading candles | **Mostly resolved:** prior 0.95, 69.0% vs 67.8% (`:833-834`). New: on `raw-clever` test launches the 1m blend is **under**confident again (69% hit vs 64% stated) (`:515-517`) |
| 6 | Scam risk level needs rework | **Done 2026-10-09** (P(rug) plus reweighted level) (`:835-858`) |
| 7 | Graduated tokens only through DexScreener polls | **Done:** watch follows the PumpSwap pool. The PumpSwap model is coded (§8.2.3) and "trained once data allows"; no `pumpswap-*` model is in `tartar/models/` (`:859-877, 519-540`). Its stated prerequisite, the 11a evaluation, ran at 12:05 UTC on 264 pools, but no model has been trained since (`handoff/STATUS.md:149-150, 286`) |
| 8 | Candle-only (OHLCV) model untrained (GeckoTerminal returns HTTP 429, "too many requests") | **Open** (`:878-884`) |
| 9 | Only a 1m model | **Done:** 15s, 30s, 1m, 5m. Other lengths use the online model alone; the volatility prior above 1m is "a guess" (`:885-889`) |
| 10 | GeckoTerminal live polling closes candles 75 s late | **Open** (`:890-891`) |

Also open: the **5m overconfidence** (§8.2.2c).
- At the open it states 70.6% and hits 60.9%. The live blend's trading candles state 68.0% and hit 63.3%.
- **Diagnosis:** the old recorder's rows are about 75% of 5m training rows. At the open of a 5m candle they had "no trade" 78% of the time, vs 36–43% in later recordings.
- **Plan for v3.1:** train 15s/30s/1m on every recording at full weight. Train 5m with the old-row weight chosen on validation from a grid (1, 0.5, 0.25, 0.1, 0) once `raw-clever` has more hours (`handoff/candle-prediction-agent.md:468-493, 506-515`).
- Also check the blend's 0.95 prior on new-style data (`:515-517`).
- STATUS lists predictor v3.1 as a later step for the clever session (`handoff/STATUS.md:39-40`).

Next-step experiments not yet reported as done (`handoff/candle-prediction-agent.md:902-908`): bin edges, a 0.99 fraction near the close, per-age models, dropping noisy features, and weighting evaluation by trading candles. The hyperparameter item is only partly done: the sweep covered leaves (15/31/63) and minimum rows per leaf (100–10,000), but not the learning rate or 127 leaves.

### 7. The honest ceiling: how predictable are new-token candles?

- **High hit rates are mostly "flat" calls.** "High hit rates come mostly from correctly calling 'flat' on quiet tokens" (`handoff/candle-prediction-agent.md:336`).
  - Only 42% of 1-minute candles of young tokens have any trade.
  - The median absolute 1-minute move on traded candles is about 13% (`:152-153`).
  - The dominant feature, `p_idle`, measures whether anything trades at all.
- **On candles where the token is trading:**
  - The v3 live blend hits 62–66% on this three-way call; the online-only model hits 41–45%.
  - The point error is still **16.8–18.1%** at the open, vs 17.5–19.0% for naive (mean absolute log error ×100; `tartar/models/trades-*.report.json` `live_at_open` blocks).
- **The point forecast is only a few percent better than "no change":**
  - v3 live edge: +1.8% (15s), +4.4% (30s), +6.2% (1m), +6.5% (5m).
  - Raw-model edge at the open: +3.6% to +9.1%.
  - Edge from f = 0.6 to 0.8: between −2.4% and +2.4%; at f = 0.95 it is exactly 0.
- **Results depend on which launches are tested:**
  - v1 reached +7.5% live on its test set; v2's later test set was "harder" (+4.0%) (`handoff/candle-prediction-agent.md:374-375`).
  - 5m open edge by recording ranges from +9.1% (`raw-eager`) to +22.5% (old recorder) and +23.6% (`raw-pumpswap`). 5m calibration drifts by period: −2 points at 00–02 UTC, −5 to −9 points at 04–08 UTC (`:475-488`).
  - On the newer test launches of the weighting preview (with `raw-clever`), installed v3's test log loss is 0.5136 at 1m, 0.4255 at 30s and 0.3276 at 15s. On v3's own test launches it is 0.4129, 0.3386 and 0.2835 (`:501, 510-514`).
- **Without a trained global model there is about 0 edge.** The online model never beats naive (`handoff/candle-prediction-agent.md:288-291`). The README tells users to "Expect low confidence. Next-candle moves of young memecoins are mostly noise". It also says the dashboard's per-token "edge vs naive" "is close to 0% on most tokens most of the time" (`README.md:198-204`).
- **Information gain over the base rate:** 0.36–0.49 bits per row at the open for 15s–1m, and 1.16 bits at 5m (v3 reports). This is not comparable across lengths.
- **Moves skew down:** P(up | move) ≈ 0.38–0.41 (`handoff/candle-prediction-agent.md:799-800`).
- **Not tradable.** "No strategy tested is profitable at realistic costs ... Treat the dashboard's 'predicted close' and confidence as measurement, not as trade signals." On recorded data, the median simulated round trip returns −3.5% after fees and price impact. These are backtests, not real fills (`handoff/profitability.md:9-13, 61-65`).

### 8. Timeline (git)

| Commit | Time (UTC) | Change |
|---|---|---|
| `1db2ce7` | 2026-10-08 05:58 | Live next-candle predictor agent |
| `05ac2e8` | 06:28 | Global model + recording pipeline |
| `9d8ea8a` | 18:43 | Accuracy-review fixes; stream capture measured |
| `08aca15` | 18:49 | First real-data model + handoff |
| `7333656` / `7f6cf0e` | 20:19 | Online-model calibration fix, v1 installed |
| `6aad9de` | 23:43 | Band reporting, late-candle median, blend weight |
| `a08fbc4` | 2026-10-09 00:56 | v2 |
| `b5f9232` | 01:09 | Shrink study |
| `a8c6b13` | 01:25 | 15s / 30s / 5m models |
| `85a94a9` / `0329d8e` | 04:43 / 04:55 | Out-of-fold shrink |
| `e56036e` | 05:32 | PumpSwap model code |
| `fa05f96` | 05:39 | Scam flags validated; tree-size flags for `tartar train` |
| `07e60c1` | 07:13 | P(rug) |
| `b47a328` | 07:52 | v3 for all four lengths |
| `bd21636` / `2ee5eab` | 07:56 / 08:04 | 5m diagnosis |
| `fd2d6e2`, `ff27f16`, `643117d`, `4963238`, `aead3ef` | 08:08–10:01 | Old-row weighting previews (5m, 1m, 30s, 15s) |
| `6a6b1a8` | 12:55:43 | Predictor session moves to an "edge hunt" and the project overview (`handoff/STATUS.md:42-45`) |

**Doc staleness to note:** several parts of the predictor doc still describe the v1 era:
- line 7: "true when written 2026-10-08 ~20:30 UTC"
- line 48: the "Status in one screen" real-data row quotes v1's result
- line 51: the biggest open problem says "fix with a private RPC", which the user has since declined
- lines 899-900: next step 2 still compares against v1
- lines 960-962: §15 names v1 as the installed model

The v3 sections are current: the §2 "Global models" row (line 47) and §8.2.2c (`handoff/candle-prediction-agent.md:7-8, 47-52, 899-900, 960-962`).
