<!-- verify:profitability: workflow section summary as of 2026-10-09 12:56 UTC; 'verify-*' files are fact-checked, 'read-*' are not -->

## Profitability research: every strategy tested and its verdict
*(state as of HEAD `4a94b99`, 2026-10-09 13:21:06 +0000. Between `6a6b1a8` and `4a94b99` only STATUS.md changed in the cited docs, so STATUS line numbers below are for `4a94b99`.)*

### 1. Bottom line
- **No strategy tested makes money at realistic costs on this data.** Every one that looked good on the validation launches lost on the later (test) launches, or its 90% interval spans zero (`handoff/profitability.md:10-13`). Treat the dashboard's "predicted close" and confidence as measurement, not as trade signals (`:12-13`).
- **Closed families:**
  - buying pump.fun launches at any entry delay up to 10 min and any hold up to 45 min (`:554-555`)
  - faster entry
  - graduation run-up
  - copy-trading
  - trading graduated tokens in their first hour on PumpSwap (`:617-618`)
- **Still running:**
  - One pre-registered forward test: the established-memecoin dip rule, scored at ≥ 200 pooled trades or on 2026-10-30, whichever comes first (`dip-rolling/SPEC.json:23`; `profitability.md:433-434`).
  - The user's sealed jevtrader test, outside TARTAR, ending 2026-10-23 21:40Z (`handoff/jevtrader.md:14-15`). TARTAR's only part in it is an on-chain cost table (`jevtrader.md:32-51`; `STATUS.md:177-179`).
  - Since 12:55 UTC, an "edge hunt" in the predictor session, still in flight (`STATUS.md:42-51`).

**Terms used below:**
- **pump.fun bonding curve:** the automatic price formula a new token trades on at launch.
- **Graduation:** when the curve has raised about 85 SOL, the token moves to a normal trading pool on **PumpSwap**.
- **Slot:** one Solana block interval, about 0.27 s.
- **Bundle:** transactions placed in the same block as the token's creation, often by the creator.
- **bps:** basis points; 1 bps = 0.01%.
- **TP / SL:** take-profit and stop-loss exits.
- **LightGBM:** a decision-tree model.
- **AUC:** how well a score ranks good cases above bad ones; 0.5 is chance.
- **Spearman:** rank correlation.
- **Validation / test:** earlier launches are used to choose a rule; later launches are used to report it once.
- **90% CI:** a 90% bootstrap interval, resampled over tokens or pools.
- **Excess:** a trade's return minus the mean return of entering the same pool at *every* bar of the same period with the same hold. It controls for the pool's overall drift (survivorship), but not fully: picking pools by today's liquidity still favors dips that recovered (`profitability.md:397-400, 418-419`).
- **Pre-registration:** the rule and the success test are fixed and committed before any out-of-sample data exists.
- **Jev:** TypeSafe's decision API.
- **MEV:** front-running and sandwich attacks.

### 2. How profit is measured, and the costs assumed
Simulator: `tartar/profit.py` / `tartar profit` (`profitability.md:28-57`).
- **Fills:** each trade fills on the real curve reserves at the last recorded trade before decision + latency, using the constant-product formula. Entry and exit each pay their own price impact (`:30-34`).
- **Default costs** (`:35-38`):
  - 0.1 SOL per entry
  - **1.25% fee per side**
  - 0.0002 SOL per transaction
  - **1.0 s** from decision to execution
- **Exits:** a fixed hold with optional TP/SL.
  - Exits after a recording cut have an unknown price and are dropped.
  - Dropping them is near-unbiased only for short holds. Long holds must be replayed through `FastLoop`, excluding a trade only when the recorder was down (`:39-50`).
- **Rules:** one position per token at a time. Thresholds are chosen on validation (70–85% of launches by time) and reported on test (the latest 15%). Intervals are bootstrapped by token (`:51-55`).
- **Cost floor (§3.1):** the median trade returns **−3.5%**: 2 × 1.25% fee, plus 0.4% network on 0.1 SOL, plus about 0.3% impact per side. A strategy needs an average gross move above ~3.5% just to break even (`:63-65`).
- **Base data for §3.2–3.8:** "v1 data", 3,523 launches from about 2.7 h of public-RPC recording (`:59`). Later sections use other recordings, as listed per row.

**Cost assumptions by study**

| Study | Size | Fee per side | Network / tip | Latency | Source |
|---|---|---|---|---|---|
| Launch studies §3.2–3.8, §3.14 | 0.1 SOL | 1.25% | 0.0002 SOL/tx | 1.0 s. Sniping sweep: 0 / 0.4 / 1 / 2 s × fee 0 / 0.5 / 1.25% (only some cells published) | `profitability.md:35-38`; `latency_sensitivity.py:10-11` |
| Slot entries §3.9 | 0.1 SOL (sensitivity 1 SOL) | 1.25% | 0.000105 SOL network per tx, plus a 0.001 SOL tip on the buy; exits pay network only | k slots after the create | `profitability.md:295`; `slot_profit.py:15-20, 34-37` |
| Graduation run-up §3.10 | 0.1 SOL | 1.25% | a failed buy costs one tx | 1 s / 3 s | Post-graduation exits valued at the final curve price less a 0 / 10 / 25% haircut (`profitability.md:331-334, 357-360`) |
| Copy-trading §3.15 | 0.1 SOL | 1.25% | 0.0002 SOL/tx | 1 s after receive (≈2.5 s after the block) | Graduated exits at the final curve price less 10% (`copytrade.py:34`, docstring) |
| Established memecoins §3.11 and the dip pre-registration | $200 | 0.5% (assumed; measured later at 0.30–1.25% for memecoin pools, 0.30–1.20% for cohort 1) | $0.05/tx | next 5-min bar's open | Impact = size / (liquidity/2) per side, liquidity as registered (`profitability.md:390-393`; `SPEC.json:14-20`) |
| PumpSwap graduates §3.16 | 0.1 SOL (sensitivity 1 SOL) | Tiered by market cap: 1.25% below ~420 SOL, 1.20% to ~1,150, then falling | 0.0002 SOL/tx | 1 s (sensitivity 3 s) | `SPEC.md:24-26, 45`; tiers from `pumpswap_study.py` docstring and `profitability.md:495-504` |
| SOL-USD §3.12 | $1,000 and $10,000 | Jupiter quotes (pool fees and impact included) | $0.05/tx | re-quotes at 1 / 2 / 4–5 s | Compared with Coinbase's 90 bps taker fee (`profitability.md:446-455`) |

**Fees, measured**
- **pump.fun curve** (`fee_sample.py`; 212 trades from 800 recent transactions):
  - SOL-quoted trades pay **0.95% protocol + 0.30% creator = 1.25% per side** (150 of 185).
  - 35 paid 0%, probably special cases such as creator first buys.
  - None paid the 2.5% creator fee seen on some quote-paired curves (curves priced in a token other than SOL). Those curves vary from 0.30% to 1.95% and are skipped (`profitability.md:288-293`).
  - An earlier 89-trade check agrees (`STATUS.md:115`).
- **PumpSwap** (`pumpswap_fees.py`, 2026-10-09; from on-chain fee fields and 10,283 recorded swaps of at least 0.05 SOL):
  - Normally LP 0.20% + protocol 0.05% + a creator fee that falls as market cap rises.
  - The exception is right after graduation, below ~420 SOL market cap: LP 0.02 + protocol 0.93 + creator 0.30 = **1.25%**.
  - ~420–1,200 SOL: **1.20%**. Then 1.05–1.10%, 1.00%, 0.95/0.90%, 0.80/0.75%, 0.60%, and **0.30%** at about 500,000 SOL.
  - A fresh graduate therefore costs about 2.5% per round trip, the same as the curve. The project had assumed 0.30% (`profitability.md:486-522`).

### 3. Verdict list

| # | Question | Method (one line) | Key numbers | Verdict | § |
|---|---|---|---|---|---|
| 1 | Does buying every launch pay? | Buy when seen, hold 30/60/180 s; test launches | −3.6% / −4.3% / −5.2% mean net (525 trades); win 16–20%; **all three 90% CIs span zero** | closed, loses | 3.2 (`profitability.md:69-73`) |
| 2 | Is the v1 candle model's prediction a trade signal? | Trade the top 0.5% by expected return or by P(up), hold 60 s | Expected return **−43.3%** [−66.7, −14.6] (38 trades); P(up) −7.0% (16); every decision row −5.9% [−7.2, −4.7] | closed, **harmful** | 3.2 (`:74-82`) |
| 3 | Net-return model | LightGBM on 57 features; label = net round-trip return (Huber regression and P(net>0)) | Huber −3.0% to −3.9%. Binary −4.8% to −16.8% in 4 of 5 cells; the fifth is **+7.9%** (31 trades; CI −12 to +30%; −12% on validation). Only 3–5% of rows profitable | closed | 3.3 (`:84-100`) |
| 4 | Latency: launch sniping | Buy at launch receive time + delay; 1,048 launches (valid + test) | 0 s: **+8.0%** [+4.6, +11.1] (15 s hold), not achievable. 0.4 s: −3.3%. 1.0 s: −2.9%. 1.0 s at 0% fee: −0.4% / +1.0% / 0.0% | closed: the profit belongs to same-block bots | 3.4 (`:102-116`) |
| 5 | Scam flags and a learned screen as trade filters | Judge each launch on its first 20 s with causal creator history; buy at +20 s | `--next-launch` screen passes 139 of 3,523: test −4.7% vs −5.1%, validation −33% vs −7%. Flagged launches lose more (valid + test, flags hand-picked on that data): odd_curve −12.5% vs −3.5%; concentrated −13.7% vs −5.4%; serial_rugger −12.7% vs −5.1%; dev_bag −8.0% vs −4.5%; sniped −7.5% vs −5.1%. Learned screen's best cell fell to −1.4% (45 trades) once cut exits were dropped | closed: skipping flags cuts losses but stays negative | 3.5 (`:118-155`) |
| 6 | `tartar decide` scorers (fair comparison) | Flags picked on training launches only; thresholds on validation | 180 s hold: buy all −5.1% (488); screen −4.7% (22); **skip flags −1.8%** (150; CI −5.8 to +4.7); LightGBM −0.6% (27; CI −28 to +30). 600 s, TP +100%, SL −30%: skip flags −1.1% (63; CI −10.5 to +9.3). The chosen flags change with the exit rule (partly noise) | closed, not profitable | 3.6 (`:157-173`) |
| 7 | Jev as a buy/skip scorer | One request per launch: a direct "beat ~3.5% costs?" question plus 4 name judgments; all 3,523 launches; median 243 ms per call | Direct question **−9.2%** (41; CI −15.9 to −1.9) at 180 s; −24.2% (16) at 600 s. About 2× overconfident (mean answer 0.20 vs 10.5% actual). LightGBM + 4 judgments +5.4% (25; CI −23.7 to +36.8; validation −8.9%). Shadow replay over 5,598 launches: Spearman −0.03 to +0.03 | closed | 3.7 (`:182-224`) |
| 8 | Jev on launch metadata | 15 yes/no questions + 2 scores on name, description and links; LightGBM feature sets A–D | Test AUC: A 0.758; B (+ code link features) **0.767**; C (+ Jev) 0.740; D 0.724. Adding Jev lowers test AUC. Best Jev item `explains`: Spearman +0.083, vs description length +0.091. AUC ≠ profit | closed: Jev adds no value | 3.8 (`:226-275`) |
| 9 | Slot / bundle entries | Buys landing k slots after the create, first or last in the slot; 1,347 launches (964 priced at creation) | Creation slot, first: **+6.8%** [+2.1, +12.1] (10 s), +5.4% (30 s). Creation slot, last: −5.6%. Slot +1 first: −5.3%. Slot +1 with no fee and no tip: −1.8% [−3.8, +0.1]. 1 SOL size: −9.2% | closed: only the creator's own bundle profits; a private RPC or Jito would not help | 3.9 (`:277-325`) |
| 10 | Graduation run-up on the curve | Buy at X SOL raised; sell at 80 SOL or after 30 min; replayed through `FastLoop`, excluding only recorder downtime | First look **+5.8%** (75→80) came from two biases. Fair: 75→80 at 3 s with 10% haircut **+0.5%** [−0.6, +1.6] (53 signals); 50→80 −9.6%; about half of the 75-SOL signals missed | closed, break-even at best | 3.10 (`:327-384`) |
| 11 | Full-stream re-check of the launch baseline | Buy every launch at +20 s, hold 180 s, via `FastLoop` | **−6.94%** [−9.10, −4.52], 2,257 trades, win 11.4% | earlier results stand | 3.10 (`:378-384`) |
| 12 | Established memecoins (momentum / dip / breakout) | GeckoTerminal 5-min price data; fixed grid; best per family on the first 60%, test on the last 40%; compared with entering at every bar | Mixed universe (test Oct 4–9): dip excess **+2.1%** [+0.3, +4.3] (139 trades, 28 pools), +0.3% without the top 3 pools. Momentum excess −0.9% (mean net +0.5%). Breakout excess −0.9% (mean net −1.5%). Memecoins only: dip mean +7.4% but excess **+0.7%** [−1.5, +2.9] | Momentum and breakout: closed. Dip: weak, mostly survivorship | 3.11 (`:386-442`) |
| 13 | Dip rule, forward test | Rolling pre-registration; cohorts of PumpSwap memecoins about once a day | Only cohort 1 (12 pools) exists; no out-of-sample result yet | **running**: scored at ≥ 200 trades or 2026-10-30 | 3.11 (`:426-438`) |
| 14 | SOL-USD costs for jevtrader | Jupiter round-trip quotes compared with the Coinbase book | ~**0.5 bps per fill** ($1k: 0.46–0.48; $10k: 0.15) vs Coinbase's 90 bps taker (~181 bps round trip). Drift-free quote decay +0.00 to +0.01 ± 0.03 bps | measured; **quotes, not fills**. US hours and real fills open | 3.12 (`:444-484`) |
| 15 | PumpSwap fees | On-chain fee fields + recorded swaps | 1.20–1.25% per side on young tokens, tiered by market cap | measured | 3.13 (`:486-522`) |
| 16 | Longer holds (10–45 min) on screened launches | `FastLoop` replay over 9,591 launches; 3 screens × 4 holds × 2 filters | Best on validation −5.3% (695 trades); **test −12.5%** [−17.6, −7.6] (102). "+ ≥ 20 buyers" rules −36% to −67% on validation | closed, loses | 3.14 (`:524-555`) |
| 17 | Copy-trading wallets whose buys paid off | Follow buys 1 s after receive; wallets scored on a learning period; 50/25/25% split by time; 9,320 launches | Validation, follow every buy: −8.0% / −14.0% / −29.2% / −13.4%. Test rule (2 min hold, score > +10%): **−21.0%** [−31.0, −10.5], 109 trades, win 22% | closed, loses | 3.15 (`:557-580`) |
| 18 | Graduated tokens on PumpSwap | Pre-registered; 264 pools (158 validation / 106 test) | Test: grad −19.6%, mom −22.5%, dip −38.1%, active −3.4%. Buying every pool 30 s after graduation −25.2% (median −17%) | closed, no edge | 3.16 (`:582-618`) |
| 19 | Live paper trading (fast loop with Jev in shadow) | Live paper run, 23:44–03:39 UTC in bursts | Cycle 1: 27 paper trades, −2.0% (CI −15.3 to +16.4). Cycle 2: 68 paper trades, **−1.4%** (CI −9.2 to +7.8), win 6%; buying every screened launch −9.2%; Jev shadow shows no signal | closed: fast loop retired; Jev turned off by the user 2026-10-09 06:35 UTC | `STATUS.md:55, 72-76, 275, 339` |

### 4. Details worth keeping

**Launch entries at various delays (§3.2, §3.4, §3.5, §3.9, §3.14)**
- **At creation:** buying at the price right after the creator's first buy is very profitable; 0.4 s later is not (`profitability.md:111-116`).
- **Timestamps arrive late:** receive times come a median **1.47 s** after the block (`:279-280`; `STATUS.md:101`).
- **In slots:** only a buy bundled with the creation earns money. After the creation slot the average launch drifts down even before costs (`profitability.md:311-321`).
- **Later screens and longer holds:** a 2- or 10-minute screen is worse than 20 s, and 10–45-minute holds lose (`:540-547`).
- **Known caveat:** tokens that revive after the recorder stops following them are valued at a stale price (`:548-552`).

**Scam filters as trade filters (§3.5–3.6)**
- Five flags mark worse trades: odd_curve, concentrated, serial_rugger, dev_bag and sniped.
- Avoiding them roughly halves the loss but never makes buying profitable (`:142-144, 171-173`).
- The hand-picked five can't be graded fairly on valid + test (`:160-163`).
- 1,748 of 3,523 token windows end at a recording cut, so long holds have little clean data (`:153-155`).
- A rug-prediction model is not a profit test. A learned P(rug) reaches AUC 0.93 (`candle-prediction-agent.md:854-857`) and shipped at test AUC 0.913 (`STATUS.md:190-195`).

**Net-return model (§3.3)**
- The Huber model picks quiet rows that lose about the cost floor; the classifier's picks are noise (`profitability.md:98-100`).

**Jev (§3.7–3.8)**
- Three question designs were tried; none adds predictive value. "What separates launches here is order flow and timing, not language" (`:270-275`).
- User rule: **"No Jev calls from TARTAR"** (`STATUS.md:217-219`).

**Graduation run-up (§3.10)**
- Two biases:
  1. Fast graduations were dropped by a ≥3-candle filter.
  2. Length-biased censoring: tokens dropped for a cut window averaged −33%.
- Lesson: never decide inclusion with a window whose length depends on the token's fate (`profitability.md:340-350, 375-377`).

**Established memecoins (§3.11)**
- **Harness check:** 2 of 18 random-walk family tests came out "significant" (~11% vs the nominal 5%) (`:403-405`).
- **Dip robustness:** excess unchanged at 0.3% or 1% fees; test halves +2.7% / +2.1%; neighbouring settings all positive. Without the top 3 pools: +0.3% (`:416-419`).
- **Fees:** at measured PumpSwap fees the memecoin mean net falls by ~0.7 points per trade; the excess is unchanged (`:521-522`).

**SOL-USD costs for jevtrader (§3.12)**
- **First window:** 33 samples, 03:37–03:48 UTC; median 0.96 bps round trip including $0.05/tx; 0.48 bps per fill (`profitability.md:448-450`; `jevtrader.md:35-45`).
- **Second window:** 04:33–05:33 UTC (samples not committed). $1k: 0.46 bps (p90 0.70, 120 samples). $10k: 0.15 bps (p90 0.33, 71 samples) (`profitability.md:457-463`).
- **Quote decay:** 178 samples; median |change| 0.12 / 0.26 / 0.52 bps at 1 / 2 / 4 s; drift-free mean ≈ 0 (`:465-475`). A separate run of 157 samples (04:10–05:30 UTC) found ≈ 0.40–0.43 bps per fill when filling at the later quote (`jevtrader.md:68-76`).
- **European morning:** 06:43–09:55 UTC, 371 samples, 0.46 bps (p90 0.67) (`profitability.md:480-482`).
- **Price level:** on-chain prices sit ~2 bps above Coinbase's mid, which cancels over a round trip (`jevtrader.md:80-83`).
- **Planning figure:** "~0.5 bps expected, with ~1.3 bps at p90" at ~2 s latency; ~180× below Coinbase retail (`profitability.md:454-455, 476-477`).
- **Not priced:** MEV, failed transactions and the USDC/USD basis (`:458-459`).
- **jevtrader itself:**
  - A paper-only Coinbase SOL-USD test. v1 is sealed: T0 2026-09-25 21:40Z, ends **2026-10-23 21:40Z**, `make results` that evening, results withheld until day 28 (`jevtrader.md:7-15`).
  - TARTAR must never unblind or disturb it (`jevtrader.md:22-24`).
  - On day 28, any arm with f*_X (its break-even fee per fill) above ~1 bps per fill would clear on-chain costs (`jevtrader.md:49-51`).
  - No SOL-USD + Jev loop was built in TARTAR, on purpose (`jevtrader.md:99-103`).

**Latency and infrastructure**
- A private RPC or Jito would only improve data quality, not make launch buying profitable (`profitability.md:316-318`).
- The user declined a private RPC on 2026-10-09 06:35 UTC. The public RPC captures a median 100% / mean 97% of each token's trades on `raw-eager` (`STATUS.md:66-68`).

### 5. Pre-registered tests (exact rules as written)

**A. Established-dip v1: superseded, not to be scored**
- **File:** `handoff/preregistration/established-dip-2026-10-09.json`. 50 pools.
- **Registered:** `2026-10-09T02:04:13Z` (line 2); commit `53b9c55` at 02:04:55.
- **Universe:** "GeckoTerminal solana pools by 24h volume, pages 1-10; base not SOL/stable/LST; quote SOL or USDC; liquidity >= $100k; 24h volume >= $100k; age >= 2 days" (line 21).
- **Evaluation:** "at least 7 days later" (line 426).
- **In-sample result:** "first 45 pools …: excess +2.13% [+0.26, +4.28], mean net +3.48% [-0.43, +8.40], 139 trades; without the top 3 pools +0.28%" (line 432).
- **Status:** "SUPERSEDED at 2026-10-09T02:19:26Z, before any out-of-sample data existed … mostly majors, wrapped assets, DeFi tokens, tokenized stocks and duplicate pools" (line 433).

**B. Established-dip v2: superseded**
- **File:** `established-dip-v2-2026-10-09.json`.
- **Registered:** `2026-10-09T02:19:26Z`; commit `46a69db` at 02:20:01.
- **Universe:** PumpSwap, SOL-quoted, one pool per token, liquidity ≥ $50k, volume ≥ $100k, age ≥ 2 days (line 22).
- **Status:** "SUPERSEDED at 2026-10-09T02:24:32Z … v2 included USDC / SOL (filter bug: stablecoin base) and only 10 pools" (line 125).

**C. Dip-rolling: RUNNING, the live forward test** (`handoff/preregistration/dip-rolling/`)
- **Registration:** cohort 1 at `2026-10-09T02:24:32Z`, 12 PumpSwap pools (`cohort-2026-10-09T0224.json:2`); commit `89e228e` at 02:27:05. **Only cohort 1 exists in git.**
- **Design:** "rolling pre-registration: each cohort file registers pools that pass the mechanical universe rule at its registered_at; each cohort is scored only on bars after its own registered_at; results pool over cohorts (a token already in an earlier cohort is not re-added)" (`SPEC.json:2`).
- **Hypothesis:** "Short-term mean reversion in established pump.fun memecoins on PumpSwap: buying after a >5% drop over 1 hour and holding 4 hours beats random entries in the same pools, net of costs" (`SPEC.json:3`).
- **Rule** (`SPEC.json:4-13`):
  - family dip; lookback_bars 12; drop 0.05; hold_bars 48; bar_seconds 300
  - entry "next bar open"; exit "close of bar t+48"
  - one position per pool
- **Costs** (`SPEC.json:14-20`): fee_per_side 0.005; size_usd 200; network_usd_per_tx 0.05; impact "size / (liquidity_usd / 2) per side, liquidity as registered".
- **Universe rule** (`SPEC.json:21`): "GeckoTerminal solana dex 'pumpswap' pools by 24h volume, pages 1-10; SOL-quoted; base not SOL/stable/LST; one pool per token (the busiest); liquidity >= $30k; 24h volume >= $100k; age >= 1 day."
- **When to score** (`SPEC.json:23`): "score when the pooled data reaches >= 200 trades or 21 days after the first cohort, whichever comes first". The handoff gives the date as **2026-10-30** (`profitability.md:433-434`; `STATUS.md:168`).
- **Primary metric** (`SPEC.json:25`): "mean of (trade net return - mean net return of entering the same pool at every bar of the period with the same hold), over all trades; 90% CI by pool bootstrap".
- **Success** (`SPEC.json:26`): "primary excess > 0 with the 90% CI above 0, AND mean net return per trade > 0".
- **Fee addendum** (`ADDENDUM-2026-10-09-fees.md`, "~04:30 UTC"; commit `154013a` at 04:32:45):
  - Written before any out-of-sample result. The rule needs 62 five-minute bars, so no trade could exist yet. SPEC.json, the rule, the universe and the success criteria are unchanged (`ADDENDUM:3-5`).
  - Cohort 1, measured 04:27 UTC: 0.30–1.20% per side, **mean 0.85%**; four of twelve pools pay ≥ 1.00% (`ADDENDUM:25-26`; `fees-measured.json`).
  - It adds a secondary line, not a success criterion: mean net at measured fees. "A reader should treat a SUCCESS whose secondary mean net is ≤ 0 as not profitable at real costs" (`ADDENDUM:36-41`).
  - The fee measured at registration is used for all of a pool's trades, an approximation stated in advance (`ADDENDUM:44-45`).
- **Expected result:** "probably not", given the memecoin in-sample excess of +0.7% (`profitability.md:435-436`).
- **Procedure:**
  1. Run `established_cohort.py` about once a day and commit at once.
  2. Then run `pumpswap_fees.py --cohort <file> --save …/fees-measured.json` and commit both together (`ADDENDUM:42-45`).
  - The next cohort is listed as "~02:24 UTC 10-10" (`STATUS.md:271`).

**D. Graduated tokens on PumpSwap (queue 11a): EVALUATED, CLOSED, no edge**
- **Registered:** `SPEC.md:3` says "Registered 2026-10-09 ~04:50 UTC … The git commit that adds this file is the registration time." The adding commit `87155f6` (SPEC.md plus `pumpswap_study.py`) is dated **2026-10-09 04:35:57 +0000**. `pumpswap_study.py` has not changed since.
- **Data:** recordings started at or after 2026-10-09 04:06 UTC; the development data in `raw-pumpswap` is excluded (`SPEC.md:11-16`).
- **Fills:** constant product on the recorded reserves, tiered PumpSwap fee, 0.0002 SOL/tx, 0.1 SOL, 1 s latency (`SPEC.md:24-26`).
- **Rules** (one trade per pool per rule; holds 1 / 5 / 15 / 60 min) (`SPEC.md:27-31`):
  - `grad`: buy 5 / 30 / 60 / 300 s after graduation
  - `mom`: at 1 / 5 / 15 min, buy if up more than 20 / 50 / 100% since graduation
  - `dip`: same times, buy if down more than 20 / 40 / 60%
  - `active`: at 15 / 30 / 60 min, buy if the pool had at least 10 / 50 recorded swaps in the last 5 min
- **Selection:** the best rule per family with at least 20 trades on the first 60% of pools, reported once on the last 40% (`SPEC.md:32-34`).
- **When:** once, at **≥ 250 graduated SOL pools** (`SPEC.md:36-39`).
- **Success:** the test mean's lower bound is above zero at one-sided 1.25%, from a bootstrap over pools. That is 5% split over the four families (Bonferroni: dividing the error allowance across several tests). Any pass must be confirmed on a later, separate recording before trading, even on paper (`SPEC.md:41-45`).
- **Result** (`RESULT-2026-10-09.md`: "Evaluated once, 2026-10-09 ~12:05 UTC"; commit `65bb508` at 12:02:10 +0000; data commit `382e827` at 12:00:27):
  - 264 pools: 69 from `raw-eager` (04:06–06:00) and 195 from `raw-clever` (06:23–11:59) (`profitability.md:586-588`).
  - Test means [90% CI] and one-sided bounds:

    | Rule | Test mean [90% CI] | Bound |
    |---|---|---|
    | grad (5 s, hold 60 s) | −19.6% [−26.7, −12.4] | −28.8% |
    | mom (15 min, > 50%, hold 5 min) | −22.5% [−45.1, −1.3] | −53.1% |
    | dip (15 min, > 60%, hold 60 min) | −38.1% [−49.9, −26.5] | −54.6% |
    | active (30 min, ≥ 50 swaps, hold 60 s) | −3.4% [−9.7, +1.9] | −12.2% |
    | Reference: every pool | −25.2% | |

    (`results/primary.txt:118-124`)
  - Sensitivity:
    - 3 s latency: everything stays negative; the `active` choice becomes 15 min / 5 min hold, −14.5%.
    - 1 SOL: −24.9 / −27.5 / −36.7 / −4.9%.
    - No pass in any run (`profitability.md:601-603`).
  - Momentum was +18.3% on 23 validation trades, then −22.5% on 14 test trades (`:613-614`).

### 6. Git history of the research branches
All five branches are fully merged into HEAD (`4a94b99`); `git log HEAD..origin/claude/<b>` is empty for each.

| Branch | Tip | Key commits |
|---|---|---|
| `claude/profitability-backtest` | `a7057aa` 2026-10-08 22:03 | `b7f99ba` 22:02 "Measure strategies by net SOL after fees, slippage and latency" (v1 expected return loses ~43%) |
| `claude/scam-filter-profit` | `57626ed` 2026-10-08 22:12 | "Validate scam flags as trade filters; drop exits after recording cuts" |
| `claude/decision-scorers` | `87ff399` 2026-10-08 22:21 | "Add launch decision scorers, including TypeSafe Jev, judged by net SOL" |
| `claude/slot-profit` | `2d9ca62` 2026-10-09 01:34 (merge) | `e10dbfa` 01:12 slot study; `e2b8de9` 01:34 graduation run-up "a false edge from two biases" |
| `claude/established-tokens` | `d452865` 2026-10-09 02:29 | `eaf8bdc` 01:58 harness; `53b9c55` 02:04 v1 pre-registration; `46a69db` 02:20 v2; `89e228e` 02:27 rolling cohort 1 |

Later commits on main (all ancestors of `origin/main`):

| Commit | Time (2026-10-08/09 UTC) | What |
|---|---|---|
| `ad02b27` | 10-08 22:56 | Jev evaluation |
| `58851a2` | 10-08 23:12 | Jev shadow mode |
| `1811de3` | 10-09 00:15 | Jev metadata |
| `cb7b37d` | 03:49 | jevtrader cost table |
| `154013a` | 04:32 | PumpSwap fees + addendum |
| `87155f6` | 04:35 | PumpSwap pre-registration |
| `c20ac05` | 04:47 | Long holds |
| `a128873` | 05:03 | Copy-trading |
| `f8fee8e` | 05:34 | SOL costs, second window |
| `aead3ef` | 10:01 | SOL costs, European morning |
| `382e827` | 12:00 | 11a evaluation data (264 pools) |
| `65bb508` | 12:02 | 11a evaluated |
| `4a94b99` | 13:21 | STATUS: edge hunt in flight; weekly-limit rule (no profitability change) |

### 7. Stale or inconsistent statements in the sources
- **§1 summary table:** `profitability.md:24` still lists PumpSwap graduates as "pre-registered, evaluated at ≥ 250 pools". §3.16 (`:582-618`) records the evaluation and "no edge".
- **§4 plan** (`profitability.md:620-645`, from 2026-10-08):
  - It still says network access is blocked, recommends a private RPC and cites 93% capture.
  - STATUS says the network was resolved at 22:35 UTC (`STATUS.md:63`) and the private RPC was declined on 2026-10-09 06:35 UTC (`STATUS.md:66`).
- **Timestamps vs commits:** the PumpSwap registration is "~04:50 UTC" in the text but 04:35:57 in the commit. The evaluation is "~12:05 UTC" in RESULT but the commit time is 12:02:10.
- **LightGBM screen at 180 s:** −0.6% (27) in §3.6 (`:167`) but −0.0% (22) in §3.7's rerun table (`:198`).
- **"≥ 20 buyers" losses:** −36% to −67% in the table (`:538`) vs −35% to −67% in the text (`:545`).
- **V2 scope:**
  - The note in §3.8 says "all evaluations here" describe V1 launches; rerun "once V2 decoding lands" (`profitability.md:264-268`). The matching STATUS log says to rerun §3.5–3.8 (`STATUS.md:431`).
  - STATUS queue item 9 records V2 decoding as done at 00:20 UTC 10-09. The dropped launches were quote-paired curves (~15% of launches), which the loader now skips because they have no SOL price (`STATUS.md:123-138`).
  - No source records a rerun.

### 8. Open items
- **Dip-rolling:**
  - Add a cohort about once a day (next ~02:24 UTC 10-10; `STATUS.md:271`) and measure its fees (`ADDENDUM:42-45`).
  - Score with `established_prereg_eval.py` at ≥ 200 pooled trades or on 2026-10-30, whichever comes first. Report the registered line plus the secondary mean net at measured fees. Expected: probably not.
- **jevtrader:** the sealed test ends 2026-10-23 21:40Z. Do not unblind or disturb it. If an arm shows a positive f*_X, the on-chain Jupiter path (paper first) is where TARTAR could help (`jevtrader.md:14-15, 99-103`).
- **SOL-USD costs:**
  - US hours (13–16 UTC) are not sampled yet.
  - Real fills are unmeasured (paper only; no real-money code without the user).
  - MEV, failed transactions and the USDC/USD basis are not priced; larger sizes are open (`profitability.md:458-459, 483-484`; `jevtrader.md:96-97`).
- **Edge hunt:** in flight at 13:20 UTC. It covers five angles, to be saved as `handoff/edge-hunt.md`, which does not exist yet. No real money, no Jev (`STATUS.md:42-51`).
- **More data:** after 24 h+ of recording, rerun `tartar profit`, `tartar decide` and the net-return experiment (`profitability.md:631-632`; `STATUS.md:77-78`).
- **V2 rerun:** if wanted, rerun §3.5–3.8 on data decoded after the V2 fix (`STATUS.md:431`). No rerun is recorded.
- **odd_curve skip candidate:** from live cycle 2 (with −19.2%, n=100; without −5.3%; in-sample, no intervals). Check it with `tartar decide` before adopting it (`STATUS.md:275`).
- **Confirmation rule:** anything that ever passes must be confirmed on a later, separate recording before trading, even on paper (`handoff/experiments/README.md:18-20`; `pumpswap-graduated/SPEC.md:44`).
