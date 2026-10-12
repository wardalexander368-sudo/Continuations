<!-- read:profitability: workflow section summary as of 2026-10-09 12:56 UTC; 'verify-*' files are fact-checked, 'read-*' are not -->

## Profitability research: every strategy tested and its verdict
*(state as of 2026-10-09 12:56 UTC; HEAD `6a6b1a8`, 2026-10-09 12:55:43 +0000)*

### 1. Bottom line
- **No strategy tested makes money at realistic costs on this data.** Every one that looked good on the validation launches lost on the later (test) launches, or its 90% interval spans zero (`handoff/profitability.md:10-13`). The dashboard's "predicted close" and confidence are to be treated as measurement, not as trade signals (`handoff/profitability.md:12-13`).
- Closed families: buying pump.fun launches at any entry delay up to 10 min and any hold up to 45 min (`handoff/profitability.md:554-555`); faster entry; graduation run-up; copy-trading; trading graduated tokens in their first hour on PumpSwap (`handoff/profitability.md:617-618`).
- Still running: one pre-registered forward test (established-memecoin dip rule, scored 2026-10-30) and, outside TARTAR, the user's sealed jevtrader test (ends 2026-10-23). TARTAR's only part in jevtrader is an on-chain cost table (`handoff/profitability.md:24-26`, `handoff/jevtrader.md:14-15`).

**Terms used below:**
- **pump.fun bonding curve:** the automatic price formula a new token trades on at launch. **Graduation:** when the curve has raised about 85 SOL, the token moves to a normal trading pool on **PumpSwap**.
- **Slot:** one Solana block interval, about 0.27 s. **Bundle:** transactions placed in the same block as the token's creation, often by the creator.
- **bps:** basis points, 1 bps = 0.01%.
- **Validation / test:** earlier launches are used to choose a rule; later launches are used to report it once.
- **90% CI:** a 90% bootstrap interval, resampled over tokens or pools.
- **Excess:** a trade's return minus the return of entering the same pool at random times. It removes survivorship bias.
- **Pre-registration:** the rule and the success test are fixed and committed before any out-of-sample data exists.

### 2. How profit is measured, and the costs assumed
Simulator: `tartar/profit.py` / `tartar profit` (`handoff/profitability.md:28-57`).
- **Fills:** each trade fills on the real curve reserves, using the constant-product formula. The buy uses the last recorded trade before decision + latency. Entry and exit each pay their own price impact (`handoff/profitability.md:30-34`).
- **Default costs** (`handoff/profitability.md:35-38`):
  - 0.1 SOL per entry
  - **1.25% fee per side** (pump.fun protocol + creator)
  - 0.0002 SOL per transaction
  - **1.0 s** from decision to execution
- **Exits:** a fixed hold, with optional take-profit (TP) and stop-loss (SL). Exits whose price is unknown because of a recording cut are dropped (`handoff/profitability.md:39-50`).
- **Rules:** one position per token at a time. Thresholds are chosen on validation (70–85% of launches by time) and reported on test (the latest 15%). Intervals are bootstrapped by token (`handoff/profitability.md:51-55`).
- **Cost floor (§3.1):** the median trade returns **−3.5%**. That is 2 × 1.25% fee + 0.4% network on 0.1 SOL + about 0.3% impact per side. A strategy needs an average gross move above ~3.5% just to break even (`handoff/profitability.md:63-65`).
- **Base data for §3.2–3.8:** "v1 data", 3,523 launches over about 2.7 h of public-RPC recording (`handoff/profitability.md:59`). These results cover V1 launches only: 130 of 3,523 tokens lack create reserves (pump.fun V2) (`handoff/profitability.md:264-268`).

**Cost assumptions by study**

| Study | Size | Fee per side | Network / tip | Latency | Other |
|---|---|---|---|---|---|
| Launch studies §3.2–3.8, §3.14 | 0.1 SOL | 1.25% | 0.0002 SOL/tx | 1.0 s (sweeps 0 / 0.4 / 1 / 2 s, fees 0 / 0.5 / 1.25%) | `profitability.md:35-38`, `latency_sensitivity.py` |
| Slot entries §3.9 | 0.1 SOL (sensitivity 1 SOL) | 1.25% | 0.001 SOL tip on the buy; exits pay network only | k slots after the create | `profitability.md:295`, `slot_profit.py` docstring |
| Graduation run-up §3.10 | 0.1 SOL | 1.25% | a failed buy costs one tx | 1 s / 3 s | post-graduation exit at the final curve price less a 0 / 10 / 25% haircut (`profitability.md:331-334, 360`) |
| Copy-trading §3.15 | 0.1 SOL | 1.25% | 0.0002 SOL/tx | 1 s after receive (about 2.5 s after the block) | graduated exits at the final curve price less 10% (`copytrade.py` docstring) |
| Established memecoins §3.11 and dip pre-registration | $200 | 0.5% (assumed; later measured 0.30–1.25%) | $0.05/tx | next 5-min bar's open | impact = size / (liquidity/2) per side (`profitability.md:390-393`; `dip-rolling/SPEC.json:14-20`) |
| PumpSwap graduates §3.16 | 0.1 SOL (sensitivity 1 SOL) | tiered by market cap: 1.25% below ~420 SOL, 1.20% to ~1,150, then falling | 0.0002 SOL/tx | 1 s (sensitivity 3 s) | `pumpswap-graduated/SPEC.md:24-26` |
| SOL-USD §3.12 | $1,000 and $10,000 | Jupiter quotes (pool fees + impact included) | $0.05/tx | re-quotes at 1 / 2 / 4–5 s | compared with Coinbase's 90 bps taker fee (`profitability.md:446-455`) |

**Fees, measured**
- **pump.fun curve** (`fee_sample.py`; 212 trades from 800 recent transactions): SOL-quoted trades pay **0.95% protocol + 0.30% creator = 1.25% per side** (150 of 185). 35 paid 0%, probably special cases such as creator first buys. None paid the 2.5% creator fee. Curves quoted in tokens other than SOL vary from 0.30% to 1.95% and are skipped (`handoff/profitability.md:288-293`).
- **PumpSwap** (`pumpswap_fees.py`, 2026-10-09; from on-chain fee fields and 10,283 recorded swaps of at least 0.05 SOL): LP 0.20% + protocol 0.05% + a creator fee that falls as market cap rises.
  - Below ~420 SOL market cap: 0.02 + 0.93 + 0.30 = **1.25%**.
  - ~420–1,200 SOL: **1.20%**.
  - Then 1.05–1.10%, 1.00%, 0.95/0.90%, 0.80/0.75%, 0.60%.
  - About 500,000 SOL: **0.30%**.
  - A fresh graduate therefore costs about 2.5% per round trip, the same as the curve. The project had assumed 0.30% (`handoff/profitability.md:486-522`).

### 3. Verdict list

| # | Question | Method (one line) | Key numbers | Verdict | § |
|---|---|---|---|---|---|
| 1 | Does buying every launch pay? | buy when seen, hold 30/60/180 s, test launches | −3.6% / −4.3% / −5.2% mean net (525 trades); win 16–20% | closed, loses | 3.2 (`profitability.md:69-73`) |
| 2 | Is the v1 candle model's prediction a trade signal? | trade the top 0.5% by expected return or by P(up), hold 60 s | expected return: **−43.3%** [−66.7, −14.6] (38 trades); P(up): −7.0% (16); every row: −5.9% | closed, **harmful** | 3.2 (`:74-82`) |
| 3 | Net-return model | LightGBM on 57 features, labels = net round-trip return (Huber regression and P(net>0)) | Huber −3.0% to −3.9%; binary −4.8% to −16.8%; one cell +7.8% (31 trades; CI −12 … +30%; −12% on validation). Only 3–5% of rows profitable | closed | 3.3 (`:84-100`) |
| 4 | Latency: launch sniping | buy at launch + delay, 1,048 launches (valid + test) | 0 s: **+8.0%** [+4.6, +11.1] (15 s hold), not achievable; 0.4 s: −3.3%; 1.0 s: −2.9%; 1.0 s with 0% fee: −0.4% / +1.0% / 0.0% | closed: the profit belongs to same-block bots | 3.4 (`:102-116`) |
| 5 | Scam flags and a learned screen as trade filters | judge each launch on its first 20 s with causal creator history, buy at +20 s | `--next-launch` screen passes 139 of 3,523; test −4.7% vs −5.1%. Flagged launches lose more (odd_curve −12.5% vs −3.5%; concentrated −13.7% vs −5.4%; serial_rugger −12.7% vs −5.1%; dev_bag −8.0% vs −4.5%; sniped −7.5% vs −5.1%). Learned screen's best cell fell to −1.4% (45 trades) once cut exits were dropped | closed: skipping flags cuts losses but stays negative | 3.5 (`:118-155`) |
| 6 | `tartar decide` scorers (fair comparison) | flags picked on training launches only; thresholds on validation | 180 s hold: buy all −5.1% (488); screen −4.7% (22); **skip flags −1.8%** (150; CI −5.8 … +4.7); LightGBM −0.6% (27). 600 s hold, TP +100%, SL −30%: skip flags −1.1% (63; CI −10.5 … +9.3) | closed, not profitable | 3.6 (`:157-173`) |
| 7 | Jev (TypeSafe decision API) as a buy/skip scorer | one request per launch: a direct "beat ~3.5% costs?" question plus 4 name judgments; all 3,523 launches asked; median 243 ms per call | direct question **−9.2%** (41; CI −15.9 … −1.9) at 180 s, −24.2% (16) at 600 s. About 2× overconfident (mean answer 0.20 vs 10.5% actual). LightGBM + 4 judgments +5.4% (CI −23.7 … +36.8; validation −8.9%). Shadow replay over 5,598 launches: Spearman −0.03 … +0.03 | closed | 3.7 (`:182-224`) |
| 8 | Jev on launch metadata (feature discovery) | 15 yes/no questions + 2 scores on name, description and links; LightGBM feature sets A–D | test AUC: A 0.758; B (+ link features from code) **0.767**; C (+ Jev) 0.740; D 0.724. Adding Jev lowers test AUC. Best Jev item `explains` Spearman +0.083 vs description length +0.091 | closed: Jev adds no value | 3.8 (`:226-275`) |
| 9 | Slot / bundle entries | buys landing k slots after the create, first or last in the slot; 1,347 launches (964 priced at creation) | creation slot, first: **+6.8%** [+2.1, +12.1] (10 s hold), +5.4% (30 s). Creation slot, last: −5.6%. Slot +1 first: −5.3%. Slot +1 with no fee and no tip: −1.8% [−3.8, +0.1]. 1 SOL size: −9.2% | closed: only the creator's own bundle profits; a private RPC or Jito would not help | 3.9 (`:277-325`) |
| 10 | Graduation run-up on the curve | buy at X SOL raised, sell at 80 SOL or after 30 min; replayed through `FastLoop`, excluding only recorder downtime | first look **+5.8%** (75→80) came from two biases. Fair: 75→80 at 3 s with 10% haircut **+0.5%** [−0.6, +1.6] (53 signals); 50→80 −9.6%; about half of 75-SOL signals missed | closed, break-even at best | 3.10 (`:327-384`) |
| 11 | Full-stream re-check of the launch baseline | buy every launch at +20 s, hold 180 s, via `FastLoop` | **−6.94%** [−9.10, −4.52], 2,257 trades, win 11.4% | earlier results stand | 3.10 (`:378-384`) |
| 12 | Established memecoin rules (momentum / dip / breakout) | GeckoTerminal 5-min OHLCV, fixed grid, best per family on the first 60%, test on the last 40%, compared with random entries | mixed universe: dip excess **+2.1%** [+0.3, +4.3] (139 trades, 28 pools), +0.3% without the top 3 pools; momentum −0.9%; breakout −0.9%. Memecoins only: dip mean +7.4% but excess **+0.7%** [−1.5, +2.9] | closed for momentum and breakout; dip is weak and mostly survivorship | 3.11 (`:386-442`) |
| 13 | Dip rule, forward test | rolling pre-registration; daily cohorts of PumpSwap memecoins | cohort 1 = 12 pools; no out-of-sample result yet | **running**: scored at ≥ 200 trades or 2026-10-30 | 3.11 (`:426-438`) |
| 14 | SOL-USD costs for jevtrader | Jupiter round-trip quotes compared with the Coinbase book | ~**0.5 bps per fill** ($1k: 0.46–0.48; $10k: 0.15) vs Coinbase 90 bps taker (~181 bps round trip); quote decay drift-free 0.00 ± 0.03 bps | measured, **quotes not fills**; US hours and real fills open | 3.12 (`:444-484`) |
| 15 | PumpSwap fees | on-chain fee fields + recorded swaps | 1.20–1.25% per side on young tokens, tiered by market cap | measured | 3.13 (`:486-522`) |
| 16 | Longer holds (10–45 min) on screened launches | `FastLoop` replay over 9,591 launches; grid of 3 screens × 4 holds × 2 filters | best on validation −5.3% (695 trades); **test −12.5%** [−17.6, −7.6] (102); "+ ≥ 20 buyers" rules −36% to −67% | closed, loses | 3.14 (`:524-555`) |
| 17 | Copy-trading wallets whose buys paid off | follow buys 1 s after receive; wallets scored on a learning period; split 50/25/25% by time | test rule (2 min hold, score > +10%): **−21.0%** [−31.0, −10.5], 109 trades, win 22% | closed, loses | 3.15 (`:557-580`) |
| 18 | Graduated tokens on PumpSwap | pre-registered; 264 pools (158 validation / 106 test) | test: grad −19.6%, mom −22.5%, dip −38.1%, active −3.4%; buying every pool 30 s after graduation −25.2% | closed, no edge | 3.16 (`:582-618`) |
| 19 | Live paper trading (fast loop with Jev in shadow) | live paper run, 23:44–03:39 UTC in bursts | cycle 2: 68 paper trades, mean **−1.4%** (CI −9.2 … +7.8); buy every screened launch −9.2%; Jev shadow shows no signal | closed: fast loop retired; user turned Jev off 2026-10-09 06:35 UTC | `STATUS.md:50, 66-71, 266` |

### 4. Details worth keeping

**Launch entries at various delays (§3.2, §3.4, §3.5, §3.9, §3.14)**
- **At creation:** buying at the price right after the creator's first buy is very profitable. Being 0.4 s later is not (`profitability.md:111-116`).
- **Timestamps arrive late:** recorded receive times come a median **1.47 s** after the block (`profitability.md:279-280`; `STATUS.md:96`).
- **In slots:** only a transaction bundled with the creation earns money. After the creation slot the average launch drifts down even before costs, because the creator's bundle and same-slot snipers sell into later buyers (`profitability.md:311-321`).
- **Later screens and longer holds:** a 2- or 10-minute screen is worse than 20 s, and 10–45-minute holds lose (`profitability.md:540-547`).

**Scam filters as trade filters (§3.5–3.6)**
- Five flags mark worse trades: odd_curve, concentrated, serial_rugger, dev_bag and sniped.
- Avoiding them roughly halves the loss but never makes buying profitable (`profitability.md:142-144, 171-173`).
- A separate rug-prediction check is not a profit test. A learned P(rug) reaches AUC 0.93 (`candle-prediction-agent.md:837-857`), shipped at test AUC 0.913 (`STATUS.md:185-190`).

**Net-return model (§3.3)**
- The Huber model learns to pick quiet rows that lose about the cost floor. The classifier's picks are noise (`profitability.md:98-100`).

**Jev as a scorer (§3.7–3.8)**
- Three question designs were tried: the direct question, name judgments, and metadata judgments. Jev adds no predictive value. "What separates launches here is order flow and timing, not language" (`profitability.md:270-275`).
- Status: user decision 2026-10-09: **"No Jev calls from TARTAR"** (`STATUS.md:208-210`).

**Graduation run-up (§3.10)**
- Two biases explain the false edge:
  1. Fast graduations were dropped by a ≥3-candle filter.
  2. Length-biased censoring: tokens dropped for having a cut window averaged −33%.
- Lesson for every study: never decide inclusion with a window whose length depends on the token's fate (`profitability.md:340-350, 375-377`).

**Established memecoins (§3.11)**
- **Harness check:** on random-walk pools, 2 of 18 family tests came out "significant" (~11% vs the nominal 5%), so a single positive is not evidence (`profitability.md:403-405`).
- **Fees:** the study charged 0.5% per side. At measured PumpSwap fees the memecoin mean net falls by about 0.7 points per trade; the excess is unchanged (`profitability.md:521-522`).

**SOL-USD costs for jevtrader (§3.12)**
- **First window:** 33 samples 03:37–03:48 UTC, median 0.96 bps round trip including $0.05/tx (`profitability.md:448-450`; `jevtrader.md:36-48`).
- **Second window:** 04:33–05:33 UTC. $1k: 0.46 bps (p90 0.70, 120 samples). $10k: 0.15 bps (p90 0.33, 71 samples) (`profitability.md:457-463`).
- **Quote decay:** 178 samples. Median |change| 0.12 / 0.26 / 0.52 bps at 1 / 2 / 4 s; drift-free mean about 0 (`profitability.md:465-475`). Separately, 157 samples at 04:10–05:30 UTC show about 0.4 bps per fill when filling at the later quote (`profitability.md:451-453`).
- **European morning:** 06:43–09:55 UTC, 371 samples, 0.46 bps (p90 0.67) (`profitability.md:480-482`).
- **Practical figure:** "~0.5 bps expected, with ~1.3 bps at p90" at ~2 s latency; about 180× cheaper than Coinbase retail (`profitability.md:454-455, 476-477`).
- **Not priced:** MEV (front-running and sandwich attacks), failed transactions, and the USDC/USD basis (`profitability.md:458-459`).
- **jevtrader itself:** a paper-only Coinbase SOL-USD test that runs outside TARTAR. v1 is sealed: T0 2026-09-25 21:40Z, ends **2026-10-23 21:40Z**, results withheld until day 28 (`jevtrader.md:7-15`). No SOL-USD + Jev loop was built in TARTAR, on purpose (`jevtrader.md:99-103`).

**Latency and infrastructure**
- A private RPC or Jito-speed execution would not make launch buying profitable. It would only improve data quality (`profitability.md:316-318`).
- The user declined a private RPC on 2026-10-09 06:35 UTC. Public-RPC capture is median 100% / mean 97% on `raw-eager` (`STATUS.md:61-63`).

### 5. Pre-registered tests (exact rules as written)

**A. Established-dip v1: superseded, not to be scored**
- **File:** `handoff/preregistration/established-dip-2026-10-09.json`.
- **Registered:** `2026-10-09T02:04:13Z` (line 2); commit `53b9c55` at 02:04:55.
- **Universe:** "GeckoTerminal solana pools by 24h volume, pages 1-10; base not SOL/stable/LST; quote SOL or USDC; liquidity >= $100k; 24h volume >= $100k; age >= 2 days" (line 21).
- **Evaluation period:** "at least 7 days later" (line 426).
- **In-sample result:** excess +2.13% [+0.26, +4.28], mean net +3.48% [−0.43, +8.40], 139 trades (line 432).
- **Status:** "SUPERSEDED at 2026-10-09T02:19:26Z, before any out-of-sample data existed … mostly majors, wrapped assets, DeFi tokens, tokenized stocks and duplicate pools" (line 433).

**B. Established-dip v2: superseded**
- **File:** `established-dip-v2-2026-10-09.json`.
- **Registered:** `2026-10-09T02:19:26Z`; commit `46a69db` at 02:20:01.
- **Universe:** PumpSwap, SOL-quoted, one pool per token, liquidity ≥ $50k, volume ≥ $100k, age ≥ 2 days (line 22).
- **Status:** "SUPERSEDED at 2026-10-09T02:24:32Z … v2 included USDC / SOL (filter bug: stablecoin base) and only 10 pools" (line 125).

**C. Dip-rolling: RUNNING (the live forward test)** (`handoff/preregistration/dip-rolling/`)
- **Registration:** cohort 1 at `2026-10-09T02:24:32Z`, 12 PumpSwap pools (`cohort-2026-10-09T0224.json:2`); commit `89e228e` at 02:27:05. **Only cohort 1 exists in git.**
- **Design:** "rolling pre-registration: each cohort file registers pools that pass the mechanical universe rule at its registered_at; each cohort is scored only on bars after its own registered_at; results pool over cohorts" (`SPEC.json:2`).
- **Hypothesis:** "buying after a >5% drop over 1 hour and holding 4 hours beats random entries in the same pools, net of costs" (`SPEC.json:3`).
- **Rule** (`SPEC.json:4-13`):
  - family dip, lookback_bars 12, drop 0.05, hold_bars 48, bar_seconds 300 (12 bars = 1 h; 48 bars = 4 h)
  - entry "next bar open"
  - exit "close of bar t+48"
  - one position per pool
- **Costs** (`SPEC.json:14-20`): fee_per_side 0.005, size_usd 200, network_usd_per_tx 0.05, impact "size / (liquidity_usd / 2) per side".
- **Universe rule** (`SPEC.json:21`): "GeckoTerminal solana dex 'pumpswap' pools by 24h volume, pages 1-10; SOL-quoted; base not SOL/stable/LST; one pool per token (the busiest); liquidity >= $30k; 24h volume >= $100k; age >= 1 day."
- **When to score** (`SPEC.json:23`): "score when the pooled data reaches >= 200 trades or 21 days after the first cohort, whichever comes first". The handoff states that date as **2026-10-30** (`profitability.md:433-434`; `STATUS.md:163`).
- **Primary metric** (`SPEC.json:25`): "mean of (trade net return - mean net return of entering the same pool at every bar of the period with the same hold), over all trades; 90% CI by pool bootstrap".
- **Success** (`SPEC.json:26`): "primary excess > 0 with the 90% CI above 0, AND mean net return per trade > 0".
- **Fee addendum** (`ADDENDUM-2026-10-09-fees.md`, "~04:30 UTC"; commit `154013a` at 04:32:45):
  - Written before any out-of-sample result. SPEC.json, the rule and the success criteria are unchanged.
  - Cohort 1's measured fees: 0.30–1.20% per side, **mean 0.85%**; four of twelve pools pay 1.00% or more (`ADDENDUM:25-26`; `fees-measured.json`).
  - It adds a secondary line, not a success criterion: mean net at measured fees. "A reader should treat a SUCCESS whose secondary mean net is ≤ 0 as not profitable at real costs" (`ADDENDUM:36-41`).
- **Expected result:** "probably not", given the memecoin in-sample excess of +0.7% (`profitability.md:436-437`).
- **Procedure:** run `established_cohort.py` about once a day and commit at once. Then run `pumpswap_fees.py --cohort <file> --save …/fees-measured.json` (`ADDENDUM:42-45`). The next cohort is listed as "~02:24 UTC 10-10" (`STATUS.md:262`).

**D. Graduated tokens on PumpSwap (queue 11a): EVALUATED, CLOSED, no edge**
- **Registered:** `SPEC.md:3` says "Registered 2026-10-09 ~04:50 UTC … The git commit that adds this file is the registration time." The adding commit `87155f6` is dated **2026-10-09 04:35:57 +0000**.
- **Data:** recordings started at or after 2026-10-09 04:06 UTC. The development data `raw-pumpswap` is excluded (`SPEC.md:11-16`).
- **Fills:** constant product on the recorded reserves, tiered PumpSwap fee, 0.0002 SOL/tx, 0.1 SOL, 1 s latency (`SPEC.md:24-26`).
- **Rules** (one trade per pool per rule; holds 1 / 5 / 15 / 60 min) (`SPEC.md:27-31`):
  - `grad`: buy 5 / 30 / 60 / 300 s after graduation
  - `mom`: at 1 / 5 / 15 min, buy if up more than 20 / 50 / 100%
  - `dip`: buy if down more than 20 / 40 / 60%
  - `active`: at 15 / 30 / 60 min, buy if the pool had ≥ 10 / 50 swaps in the last 5 min
- **Selection:** the best rule per family with at least 20 trades on the first 60% of pools; reported once on the last 40% (`SPEC.md:32-34`).
- **When:** once, at **≥ 250 graduated SOL pools** (`SPEC.md:36-39`).
- **Success:** the test mean's lower bound is above zero at one-sided 1.25% (5% Bonferroni-split over the four families; Bonferroni splits the error allowance across several tests), bootstrap over pools. A pass must then be confirmed on a later recording (`SPEC.md:41-45`).
- **Result** (`RESULT-2026-10-09.md`: "Evaluated once, 2026-10-09 ~12:05 UTC"; commit `65bb508` dated 12:02:10 +0000):
  - Data: 264 pools (data committed in `382e827`).
  - Test means [90% CI], one-sided bound: grad (5 s, hold 60 s) −19.6% [−26.7, −12.4], bound −28.8%; mom (15 min, > 50%, hold 5 min) −22.5% [−45.1, −1.3], bound −53.1%; dip (15 min, > 60%, hold 60 min) −38.1%, bound −54.6%; active (30 min, ≥ 50 swaps, hold 60 s) −3.4% [−9.7, +1.9], bound −12.2%. Reference (every pool) −25.2% (`results/primary.txt:118-124`).
  - Sensitivity runs (3 s latency, 1 SOL) also show no pass (`profitability.md:601-603`).
  - Momentum was +18.3% on 23 validation trades, then −22.5% on 14 test trades (`profitability.md:613-614`).

### 6. Git history of the research branches
All five branches are fully merged into the current branch; `git log HEAD..origin/claude/<b>` is empty for each.

| Branch | Tip | Key commits |
|---|---|---|
| `claude/profitability-backtest` | `a7057aa` 2026-10-08 22:03 | `b7f99ba` 22:02 "Measure strategies by net SOL after fees, slippage and latency" (v1 expected return loses ~43%) |
| `claude/scam-filter-profit` | `57626ed` 2026-10-08 22:12 | "Validate scam flags as trade filters; drop exits after recording cuts" |
| `claude/decision-scorers` | `87ff399` 2026-10-08 22:21 | "Add launch decision scorers, including TypeSafe Jev, judged by net SOL" |
| `claude/slot-profit` | `2d9ca62` 2026-10-09 01:34 (merge) | `e10dbfa` 01:12 slot study; `e2b8de9` 01:34 graduation run-up "a false edge from two biases" |
| `claude/established-tokens` | `d452865` 2026-10-09 02:29 | `eaf8bdc` 01:58 harness; `53b9c55` 02:04 v1 pre-registration; `46a69db` 02:20 v2; `89e228e` 02:27 rolling cohort 1 |

**Later commits on the main line:**

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
| `65bb508` | 12:02 | 11a evaluated |

### 7. Stale or inconsistent statements in the sources
- **§1 summary table:** `profitability.md:24` still lists PumpSwap graduates as "pre-registered, evaluated at ≥ 250 pools". §3.16 (`:582-618`) records the evaluation and "no edge".
- **§4 plan:** `profitability.md:620-645` dates from 2026-10-08. It still says network access is blocked and recommends a private RPC. STATUS says the network was resolved 22:35 UTC (`STATUS.md:57`) and the private RPC was declined 2026-10-09 06:35 UTC (`STATUS.md:61`).
- **PumpSwap registration time:** given as "~04:50 UTC" in the text vs 04:35:57 in the commit. The evaluation is "~12:05 UTC" in RESULT vs commit time 12:02:10.
- **V1-only scope:** §3.2–3.8 results describe V1 launches only. The doc says to rerun them once V2 decoding lands (`profitability.md:264-268`). No source found records that rerun.

## Open items
- Dip-rolling forward test is RUNNING: only cohort 1 (registered 2026-10-09T02:24:32Z, 12 pools) exists; add a cohort about once a day with established_cohort.py and commit at once (next listed as ~02:24 UTC 2026-10-10, STATUS.md:262), then run pumpswap_fees.py --cohort <file> --save handoff/preregistration/dip-rolling/fees-measured.json (ADDENDUM:42-45).
- Score the dip pre-registration with established_prereg_eval.py at >= 200 pooled trades or 2026-10-30, whichever first (SPEC.json:23; profitability.md:433-434); report the registered RESULT line plus the secondary mean net at measured fees. Expected outcome per the doc: probably not.
- jevtrader v1 sealed test ends 2026-10-23 21:40Z (make results that evening, on the user's Mac); TARTAR must not unblind or disturb it. If an arm shows positive f*_X, the on-chain Jupiter path (paper first) is where TARTAR could help (jevtrader.md:14-15, 99-103).
- SOL-USD on-chain costs: US hours (13-16 UTC) not yet sampled; real fills unmeasured (paper only, no real-money code without the user); MEV, failed transactions and USDC/USD basis not priced; larger sizes open (profitability.md:458-459, 483-484; jevtrader.md:96-97).
- Edge hunt (predictor session, active since 2026-10-09 12:55 UTC): survey strategy families not on the closed list, pre-register the most promising and run on free data, no real money, no Jev (STATUS.md:42-46).
- Rerun sections 3.2-3.8 including pump.fun V2 launches (profitability.md:264-268); no source found recording that rerun.
- More data: after 24 h+ of recording, rerun tartar profit, tartar decide and the net-return experiment (profitability.md:625-632; STATUS.md queue item 2).
- In-sample odd_curve skip candidate from live cycle 2 (with -19.2%, n=100; without -5.3%) is to be checked with tartar decide before adoption (STATUS.md:266).
- Anything that ever passes must be confirmed on a later, separate recording before trading, even on paper (handoff/experiments/README.md; pumpswap-graduated/SPEC.md:44).
- Doc staleness: profitability.md section 1 row for PumpSwap graduates (line 24) and section 4 plan (lines 620-645: network blocked, private RPC) are out of date versus section 3.16 and STATUS.md:57,61.
- Known caveat: tokens that revive after the recorder stops following them (10 idle min) are valued at a stale price, so rare late winners may be missed (profitability.md:548-552).
