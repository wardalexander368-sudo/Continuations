<!-- verify:product-code: workflow section summary as of 2026-10-09 12:56 UTC; 'verify-*' files are fact-checked, 'read-*' are not -->

## What TARTAR is and how the code is organized (as of 2026-10-09 12:56 UTC, commit 6a6b1a8)

### 1. TARTAR in one paragraph
TARTAR is a Python command-line tool (package `tartar` 0.1.0, Python 3.10+). It depends on numpy, httpx, websockets, rich and lightgbm, and its entry point is `tartar = tartar.cli:main` (pyproject.toml:6-23). It runs a live agent that "watches the candle chart of any Solana token, including tokens launched minutes ago, and predicts each candle's closing price", and it attaches a confidence to each prediction. The agent scores itself on every candle, so you can see whether the stated confidence matched what happened (README.md:3-6).

The repo grew three more parts around that predictor:
- a scam/risk filter
- an offline data and training pipeline
- tools that ask whether any of it makes money after costs (profit, decide, fast loop, review)

The money answer so far is **no**: "No strategy tested is profitable at realistic costs on this data" (handoff/profitability.md:10-13; README.md:157-159).

Size: 44 Python files and about 9,900 lines in `tartar/`, plus about 2,700 lines in `tests/` (line counts with `wc`).

### 2. Terms used below
- **pump.fun launch / bonding curve**: a new pump.fun token first trades against a pool priced by a formula: a constant-product "curve" with virtual reserves. The standard curve holds 30 virtual SOL (tartar/feeds/pumpportal.py:25). The curve is the order book.
- **Graduation**: once about 85 SOL has been raised in the curve, the token moves to an AMM, an automated pool (tartar/model/engine.py:20-21). That AMM is **PumpSwap**, pump.fun's own pool program (tartar/feeds/pumpswap.py:1).
- **Candle**: open/high/low/close price over a fixed period (15s, 30s, 1m, 5m, ...).
- **Slot**: a Solana block position. The rawlog docstring says about 0.4 s per slot (tartar/data/rawlog.py:26-29); a later measurement found about 270 ms (handoff/STATUS.md:95).
- **bps**: basis points, 0.01%.
- **Edge**: how much smaller the forecast error is than the naive guess "close = last price" (handoff/candle-prediction-agent.md:31-33).
- **Band**: a range the close should land in 80% of the time.
- **Locked at open**: the forecast fixed when a candle opens. This is the forecast that gets scored (README.md:189-192).
- **Walk-forward**: each candle is predicted using only the candles before it.
- **AUC**: how well a score ranks positives above negatives. 0.5 is chance, 1.0 is perfect.
- **Log loss**: a penalty on probabilistic forecasts; lower is better.
- **Paper trading**: simulated fills only, with no real transactions.

### 3. The original goal
The user asked for "an agent that can watch a candle graph live, predict the next candle closing price on any new sol coin/token and live-output that result and its confidence of that result". They then said: "Do anything you need to do to build the highest accuracy predictor that we can. That is this project's only job." Scam filtering was requested later (handoff/candle-prediction-agent.md:16-27).

"Accuracy" has three operational parts (same doc :29-39):
1. Edge over the naive forecast.
2. Stated confidence equal to the realised hit rate. This is "non-negotiable: the system must never invent conviction".
3. An 80% band that really covers 80%.

All three are measured on tokens launched after the training data, plus a candle-by-candle replay of the live forecaster. The README tells users to "Expect low confidence": next-candle moves of young memecoins are mostly noise (README.md:201-204).

### 4. Live data flow (`tartar watch`)
`feeds/* → Tick / Snapshot / Status → CandleAgent → CandleBook (candles) → Forecaster (FeatureEngine + WalletTracker + GlobalModel + online model) → Scoreboard + scam.assess → sinks (Dashboard / PlainPrinter / JsonLines)` (handoff/candle-prediction-agent.md:83-100).

**4.1 Feeds and source choice.** `market.open_market` looks the address up on GeckoTerminal and DexScreener at the same time, then picks a source. Valid sources: `auto, chain, pumpportal, pumpswap, dexscreener, gecko` (tartar/market.py:25).

`auto` works like this (tartar/market.py:147-166):
1. A pump.fun mint (address ends in "pump") still on its curve uses `chain`. "Still on its curve" means it was not found on a non-curve DEX, which includes a mint not listed anywhere. It uses `pumpportal` instead if `PUMPPORTAL_API_KEY` is set.
2. A graduated pump.fun token on PumpSwap uses `pumpswap`.
3. Any other token with a DexScreener pair uses DexScreener, polled every 3 s (market.py:187). This includes graduated tokens on other DEXes.
4. Otherwise it falls back to GeckoTerminal OHLCV polling. Candles from this source close 75 s after they end, unless `--grace` is set (market.py:193).

Prices are in SOL for chain, PumpPortal and PumpSwap, and in USD otherwise (market.py:170). The README lists only three steps and omits the PumpSwap step (README.md:216-223).

The feed modules:
- `feeds/pumpchain.py` reads the pump.fun program's logs over a Solana RPC websocket (`logsSubscribe`). It is free, needs no key, and decodes Create, Trade and Complete events (pumpchain.py:1-7).
  - Program id `6EF8rrec…F6P` (:32).
  - Default endpoint: the public mainnet websocket (:35); `SOLANA_RPC_WS` overrides it (:69-72).
  - Commitment level from `SOLANA_COMMITMENT`, default "confirmed" (:324).
- `feeds/pumpportal.py` is the optional PumpPortal websocket. Its per-token trade stream needs a key funded with SOL (README.md:214; ≥0.02 SOL per handoff/candle-prediction-agent.md:137). The module's own docstring still says it is free (pumpportal.py:1-5).
- `feeds/pumpswap.py` decodes PumpSwap Buy/Sell events and derives a graduated token's canonical token/WSOL pool (pumpswap.py:1-14). It also holds the measured fee tiers by market cap: 1.25% per side below 420 SOL, down to 0.6% below 100,000 SOL, and 0.30% above that (pumpswap.py:31-42).
- `feeds/dexscreener.py` polls price. DexScreener has no candle endpoint, and its limit is about 300 requests/min (dexscreener.py:1-7).
- `feeds/geckoterminal.py` provides pool lookup, OHLCV history, new pools and polling.
  - About 30 requests/min; data can lag up to about 1 min.
  - OHLCV only at 1m, 5m, 15m, 1h, 4h, 12h and 1d (geckoterminal.py:1-4, :18-26).
- Other feed files:
  - `feeds/http.py`: a rate-limited JSON client with retries.
  - `feeds/base.py`: the feed interface. `Status.kind` is connected, disconnected, gap or graduated (base.py:20-25).
  - `feeds/synthetic.py`: the demo feed.

**4.2 Warm-up.** Before going live, the model warms up walk-forward on historical GeckoTerminal candles: default 500 (`--history`), at most 1000 (README.md:225-228; cli.py:64). Several cases start cold:
- a token too new to be indexed
- a failed lookup
- a timeframe GeckoTerminal doesn't serve, such as 15s or 30s
- a SOL-priced source whose GeckoTerminal pool is not SOL-quoted

(market.py:199-218)

**4.3 Candles.** `candles.py` holds `Tick`, `Candle` and `CandleBook`. The book builds a gap-free series from ticks and/or snapshots. It closes a candle by the clock plus a grace period.

**4.4 Features.** `model/engine.py` (`FeatureEngine`) computes the same features live and offline (engine.py:1-5).
- There are 55 features: 39 base, 9 for the forming candle, and 7 risk features from scam.py (engine.py:23-48; scam.py:41-49). Each installed trades-*.json lists 55.
- They cover price action, activity, order flow, wallets, the creator's wallet, lifecycle (age, curve progress) and the forming candle so far.
- The README says "about 50" (README.md:252-253).

**4.5 Models.** Two predictive distributions are blended (tartar/model/forecaster.py:144-165).

**Global model** (`model/global_model.py`): one LightGBM multiclass model.
- Class 0 means "price doesn't move again". The other 24 classes are bins of the volatility-scaled remaining move (global_model.py:1-7, :22-28).
- For trade data it is trained on snapshots at 0/20/40/60/80/95% through each candle (dataset.py:1-7, :31). It is calibrated with temperature scaling (train.py:46).
- Training rows mimic live conditions. About 30% of tokens with more than 12 candles are "late joins", where watching starts mid-life. Some tokens hide their creator or launch time (dataset.py:374-375; README.md:266-275).

**Online model**, learned per token while watching (README.md:277-301):
- EWMA volatility (model/volatility.py).
- An expert ensemble: random walk, drift, and three ridge-regression experts (momentum, order flow, full) on 10 online features. Prior weights are 0.4/0.15/0.15/0.15/0.15 (model/ensemble.py:120-130). The combined signal is scaled by a reliability slope that never exceeds 1 (forecaster.py:220-230).
- An empirical error distribution and a mixture with a "no further trade" point mass (model/predictive.py).
- Flat-candle odds (volatility.py `ActivityEstimator`).
- Direction recalibration (predictive.py `DirectionCalibrator`).
- An adaptive conformal band (forecaster.py:161-163).

**Blend.** The global weight is σ(logit(prior) + discounted log-score difference), with prior 0.95, discount 0.98 and the difference clipped to ±5 (forecaster.py:178, :232-234; handoff/candle-prediction-agent.md:542-547).

**4.6 Agent.** `CandleAgent` (agent.py:64-318) runs the loop:
- Warm-up, then streaming.
- Each event is processed in full: close candles first, then apply the trade.
- Scam checks (RPC mint + RugCheck) refresh in the background: every 600 s, or every 60 s while RugCheck doesn't have the token yet (agent.py:164-171).
- Candles seen only partly during a feed outage longer than 10 s are never scored or learned from. After an outage the agent resyncs the way a mid-life join starts (agent.py:109-113, :224-278).
- At graduation it switches to a PumpSwap global model if one is installed; otherwise it continues online-only (agent.py:225-236).

**4.7 Outputs.** Chosen in `cli._make_sinks` (cli.py:207-222).
- **Dashboard** (`dashboard.py`, refreshed every 0.25 s; class at :150):
  - header: symbol, source, risk level and P(rug)
  - candle chart on a log price scale, with the predicted close ◆ and its band ┊ (render_chart :29)
  - "Next close" panel: predicted close, direction confidence, 80% band, locked-at-open forecast, volatility
  - "Track record" panel: last 50 live candles, this session and the warm-up, plus the model mix
  - "Recent results" footer (last 7)
- **Plain log lines**: every 10 s by default.
- **JSON lines**: every 1 s. Event types: start, warmup, candle, forecast, prediction, result, status, summary (README.md:313-328), plus a `risk` event (README.md:36; output.py:177-224).

Calls at or below 52% are labelled "≈ coin flip" (output.py:20). `scoreboard.py` keeps separate tallies for warm-up and live candles, and buckets stated confidence against the realised hit rate (scoreboard.py:95-121).

### 5. Installed models (`tartar/models/`)
These load automatically for pump.fun tokens streamed trade by trade (chain/PumpPortal), at 15s, 30s, 1m and 5m only. Other candle lengths run online-only (handoff/candle-prediction-agent.md:885-887).

The replay figures below come from the `live_at_open` blocks of `tartar/models/trades-*.report.json` (e.g. trades-60s.report.json:219-262, trades-300s.report.json:221-264). They replay the live forecaster over 300 recorded test tokens, the latest launches. They are not live sessions.

"All candles" is dominated by candles with no trades, which are easy to call flat. The "trading candles" columns are the harder test.

| File | Trained on | Trained at (UTC) | Replay, global+online, all candles (hit / stated / edge) | Replay, trading candles (hit / stated / edge) | Online only, all (edge) |
|---|---|---|---|---|---|
| trades-15s | 9,184 tokens (json:93) | 2026-10-09T06:54:01Z | 91.5% / 91.3% / +1.8% (n=16,776) | 62.3% / 60.1% / +1.9% (n=2,480) | −0.2% |
| trades-30s | 8,927 tokens (json:95) | 2026-10-09T07:30:36Z | 89.6% / 89.2% / +4.4% (n=8,222) | 65.9% / 63.6% / +4.7% (n=1,632) | −0.2% |
| trades-60s | 8,560 tokens (json:93) | 2026-10-09T06:27:59Z | 86.0% / 85.9% / +6.2% (n=4,020) | 65.5% / 66.0% / +6.5% (n=1,146) | −0.5% |
| trades-300s | 4,683 tokens (json:95) | 2026-10-09T07:39:30Z | 61.3% / 68.6% / +6.5% (n=911) | 63.3% / 68.0% / +6.5% (n=878) | −0.0% |
| rug-20s (P(rug)) | 5,267 launches (json:30) | 2026-10-09T07:10:57+00:00 | test (latest 791 launches, rug rate 9.5%): AUC 0.913, log loss 0.199 (json:34-35) | — | — |

These are predictor v3, installed 07:50 UTC 10-09 (handoff/STATUS.md:74-80). Caveats:
- **5m is overconfident on new launches.**
  - At the open it states 70.6% and hits 60.9%; per STATUS it states ~70% and hits 61-65%.
  - Cause, per the corrected diagnosis: the training mix. Old-recorder rows are ~75% of 5m training rows and were "no trade" at the open 78% of the time, vs 36-43% in later recordings (STATUS.md:77-80; handoff/candle-prediction-agent.md:466-491).
- 15s and 30s are about 2 points underconfident on trading candles. On newer raw-clever launches the 1m blend is underconfident on trading candles: 69% hit vs 64% stated (candle-prediction-agent.md:464-466, :515-517).
- No `pumpswap-*` model and no `ohlcv-*` model is installed. The candle-only (OHLCV) model "is untrained" (handoff/candle-prediction-agent.md:878-884), so DexScreener and GeckoTerminal tokens run online-only.

**P(rug)** is the chance that, 30 min after a 20 s screen, the price is ≥80% below the screen price and the token has not graduated (README.md:73-78; rug.py:1-15).
- It is shown, never used to skip a launch.
- The top decile over-predicts: 56% predicted vs 44% observed.
- High P(rug) also means more "moons". The doc calls it a warning, not a trading signal.
- The reweighted risk level ranks at AUC 0.735, up from 0.585 (handoff/candle-prediction-agent.md:654-680).

### 6. Offline pipeline
1. **Record.** `tartar record` uses `ChainRecorder`, which is free and reads the chain logs; `Recorder` is the PumpPortal variant (recorder.py:1-4).
   - It records every launch for `--track-minutes` (default 60), or until 10 idle minutes pass.
   - At most 3000 tokens are tracked at once (CLI default).
   - `--pumpswap-hours N` also follows each graduated token's PumpSwap pool, for N hours or until 30 idle minutes pass (cli.py:107-120; recorder.py:186-205).
2. **Raw logs.** Hourly JSON-lines files, gzipped once done (`data/rawlog.py`).
   - Event types: create, trade, migrate, track, untrack, session, graduate, swap, unwatch.
   - Since 2026-10-09, chain-recorder create/trade/migrate events carry `slot`, and curves priced in a token other than SOL carry `quote` (rawlog.py:1-37).
3. **Dataset.** `data/dataset.py` rebuilds candles per token with the live feature code.
   - It cuts each token's history at the first recorder interruption (rawlog.py:36-37). Reconnects within 10 s don't count (dataset.py:205-240).
   - It splits 70/15/15 by launch time, or graduation time for PumpSwap tokens (dataset.py:76-84).
4. **Train.** `train.py` runs LightGBM with early stopping, a temperature fit and an out-of-fold median shrink. It then writes an honest report on the latest tokens, including a replay of the live forecaster (train.py:1, :79-140, :292).
5. **Install.** `tartar train` installs the new model only if its log loss on the new dataset's test tokens beats the installed model's; `--force` overrides (cli.py:582-597).
   - CLI defaults are 63 leaves / 100 rows per leaf, while v3 was trained with 31 / 2,000 (cli.py:142-143; STATUS.md:75-76).
   - `tartar learn` records continuously and retrains in a subprocess, first after 3 h and then every 6 h. It trains one timeframe (default 1m) with the default settings and records without `--pumpswap-hours` (cli.py:197-203, :874-901).

Side tools:
- `data/collect.py` (`tartar collect`) downloads GeckoTerminal OHLCV histories for a candle-only model.
- `data/simulate.py` (`tartar simulate`) writes made-up pump.fun launches on real curve math, for pipeline tests only. Models trained on it load only in `demo` (README.md:344-347; simulate.py:1-7; global_model.py:151-166).

Training data is not in git: `/data/` and `*.jsonl` are git-ignored (.gitignore:8-9). Snapshots live in `handoff/data/` (described in handoff/data/README.md).

Data capture is now high. The v3 1m training data shows a median 99.2% and mean 91.0% of each token's trades captured, over 7,778 tokens (trades-60s.report.json:127-132).

### 7. Risk, profit and decision side

| Module | What it does | Status |
|---|---|---|
| `scam.py` | Three evidence layers (scam.py:1-14). **Behaviour**, via `WalletTracker`: dev dump, sniped/bundled supply, top-10 holders, wash trading, few traders, odd curve, ≥90% collapse. **The mint**, via RPC: mint/freeze authority, Token-2022 extensions. **Reputation**: RugCheck plus `CreatorIndex` (creator rugs, serial launches, copycats). `assess` turns these into ok/caution/danger/scam, or unknown when there is no evidence (:256-372). | Built. `sniped`/`concentrated`/`dev_dumped` alone are only "caution" (scam.py:276-279). |
| `rug.py` | P(rug): LightGBM on 18 screen numbers, Platt-calibrated, time split 70/15/15 (rug.py:1-36). | Shipped 07:15 UTC 10-09 (STATUS.md:185-190). |
| `screen.py` | `watch --next-launch` follows each launch for 20 s and skips it if any of these hold (screen.py:53-118; README.md:64-71): fewer than 3 non-creator buyers; `avoid` set (danger/scam, or sniped ≥50%, top-10 ≥70%, creator sold ≥90%); priced in a token other than SOL. The screen's `assess` has no RPC mint or RugCheck data (static=None), only trades and creator history. Few launches pass: 2.9% of test launches, and 30% of those rugged (n=23) (candle-prediction-agent.md:672-674). | In use. |
| `market.py` | Not a trading module: turns an address into a live feed plus warm-up history; `launch_market` handles brand-new launches (market.py:78-267). | In use. |
| `profit.py` (`tartar profit`) | Round trips on the recorded curves with every cost charged, including price impact. Defaults: 0.1 SOL, 1.25% fee per side, 0.0002 SOL per transaction, 1 s latency (profit.py:1-30; cli.py:158-166). | Result: no strategy is profitable (README.md:157-159). |
| `decide.py` (`tartar decide`) | Buy-or-skip scorers at +20 s with a 180 s hold by default: buy every launch, the screen, `FlagScorer`, `LightGBMScorer`, optionally Jev. Thresholds are chosen on validation; results are reported on test by net SOL (decide.py:1-9; cli.py:722-793). | Study tool. Launch buying is closed as a strategy (profitability.md:19). |
| `fastloop.py` (`tartar fast`) | Live or replay loop: screen, skip rules, scorer ("rules" or "jev"), **paper** fill matching `profit.round_trip`, JSON-lines journal. The policy refuses any mode except "paper" (fastloop.py:1-21, :115-117). | **Live loop retired** 2026-10-09 by the user; `--replay` remains a study tool (handoff/slow-loop.md:3-5; STATUS.md:67-71). |
| `jev.py` | Client for TypeSafe's Jev decision API: questions about the launch and its metadata, cached by mint. Uses `TYPESAFE_API_KEY` if set; in a Claude cloud environment the proxy can add credentials (jev.py:1-24). | **Off**: "No Jev calls from TARTAR" (STATUS.md:50-51, :208-210). No signal in three tests (STATUS.md:67-70). |
| `metadata.py` | Fetches launch metadata JSON through IPFS gateways and computes link features (metadata.py:1-11). | Used by the Jev metadata study. |
| `review.py` (`tartar review`) | The "slow loop": the journal plus counterfactual outcomes for every screened launch, scorer calibration, and the best threshold in hindsight (in-sample) (review.py:1-11). | Tied to the retired fast loop. |
| `scoreboard.py` | Track record of locked forecasts: is the stated confidence honest? | In use (agent, backtest). |
| `backtest.py` (`tartar backtest`) | Walk-forward run of the **online model only** on one token's history (backtest.py:12-24). | In use. |

Strategy families closed after costs (handoff/profitability.md:17-26 and §3.16 at :582-618):
- launch buying, including faster entry
- the graduation run-up: break-even at best
- longer holds
- copy-trading
- graduated tokens in their first hour on PumpSwap: a pre-registered study of 264 pools found no edge. Test means were −19.6 / −22.5 / −38.1 / −3.4% for the grad / mom / dip / active families, on small test samples of 106 / 14 / 26 / 27 trades.

Still open:
- **Established-memecoin dip buying**: a rolling forward test. Add a cohort about daily; score at ≥200 trades or on 2026-10-30 (STATUS.md:160-163).
- **SOL-USD for the user's separate jevtrader project.** TARTAR only supplies on-chain cost quotes of about 0.5 bps per fill. These are quotes, not fills; MEV, failed transactions and the USDC/USD basis are not priced (profitability.md:444-481).
  - jevtrader's sealed test ends 2026-10-23 (STATUS.md:166-181).
  - The European morning has been sampled (0.46 bps/fill); US hours are still open.

### 8. All CLI subcommands (`tartar/cli.py`, 15 in total)

| Command | Where | What it does |
|---|---|---|
| `watch <mint>` / `--next-launch` | cli.py:60-73, 289-337 | Live prediction (dashboard, plain or JSON). `--next-launch` screens new launches and watches the first that passes. Options: `--source`, `--history 500`, `--poll`, `--grace`, `--screen 20`, `--min-buyers 3`, `--allow-risky`, `--no-scam-check`, `--creators`, `-t`, `--band 0.8`, `-o`, `--every`, `--log`, `--candles`, `--model-dir`, `--no-model` |
| `new` | :75-79, 379-422 | Newest Solana pools from GeckoTerminal (`--safe` hides danger/scam), or a live stream of pump.fun launches from PumpPortal |
| `backtest` | :81-87, 425-454 | Walk-forward calibration table (online model only) on a token's history or a CSV |
| `demo` | :89-94, 340-361 | Agent on a simulated pump.fun token at 20× speed, no network needed |
| `scan` | :96-99, 904-946 | One-off scam report; exit code 3 if danger or scam |
| `resolve` | :101-105, 457-479 | Shows the pool, source and history `watch` would use |
| `record` | :107-120, 493-514 | Records launches and trades (chain or PumpPortal); optional PumpSwap pools |
| `collect` | :122-127, 517-525 | Downloads GeckoTerminal OHLCV histories |
| `simulate` | :129-133, 528-533 | Writes simulated raw logs |
| `train` | :135-156, 544-679 | Trains, evaluates and installs (keep-better) a model: the global model (`--raw`/`--ohlcv`), the PumpSwap model (`--pumpswap`) or P(rug) (`--rug`) |
| `profit` | :158-166, 682-719 | Net SOL of baselines and model-signal strategies after costs |
| `decide` | :168-178, 722-793 | Compares buy-or-skip scorers by net SOL (`--jev` optional; Jev is now off by user decision) |
| `fast` | :180-187, 796-851 | Fast loop, live (records too) or `--replay`; paper only. The live loop is retired |
| `review` | :189-195, 854-871 | Review of the fast-loop journal with counterfactuals |
| `learn` | :197-203, 874-901 | Records continuously and retrains on a schedule |

The module docstring at cli.py:1 lists 13 commands; it omits `scan` and `learn`.

### 9. Module map by purpose
- **Entry / CLI**: `tartar/__init__.py` (version), `__main__.py`, `cli.py`.
- **Live agent and outputs**: `agent.py`, `candles.py`, `clock.py` (real and simulated clocks), `dashboard.py`, `output.py`, `scoreboard.py`, `backtest.py`.
- **Market resolution and feeds**: `market.py`, `feeds/base.py`, `feeds/http.py`, `feeds/pumpchain.py`, `feeds/pumpportal.py`, `feeds/pumpswap.py`, `feeds/dexscreener.py`, `feeds/geckoterminal.py`, `feeds/synthetic.py`.
- **Prediction models**: `model/engine.py` (features), `model/forecaster.py` (blend, band, nowcast), `model/global_model.py` (also `find_model`; `$TARTAR_MODEL_DIR` overrides the model folder), `model/volatility.py`, `model/ensemble.py`, `model/features.py` (the online experts' 10 features), `model/predictive.py`. Trained files are in `models/`.
- **Offline data and training**: `data/recorder.py`, `data/rawlog.py`, `data/dataset.py`, `data/collect.py`, `data/simulate.py`, `train.py`.
- **Risk**: `scam.py`, `screen.py`, `rug.py`, `metadata.py`.
- **Profit and decisions**: `profit.py`, `decide.py`, `fastloop.py`, `review.py`, `jev.py`.
- **Outside the package**:
  - `handoff/`: STATUS.md is the shared board. `candle-prediction-agent.md` covers the predictor. `profitability.md`, `slow-loop.md` and `jevtrader.md` are the other topic docs. `jev-carveout-DRAFT.md` was not adopted. `OVERVIEW.md` is claimed but not yet written (STATUS.md:45).
  - `handoff/experiments/`: study scripts, plus `predictor-v3/` results.
  - `handoff/preregistration/`.
  - `handoff/live/`: the fast loop's policy copy and slow-loop reviews.
  - `handoff/data/`: data snapshots.
  - `handoff/code/`: a source snapshot that is now stale. A diff shows it lacks `rug.py`, `test_rug.py`, `test_pumpswap_model.py` and the rug model; 15 source files and 2 test files differ.

### 10. Tests (`tests/`, 140 test functions by grep count, not run here)

| File | Tests | Purpose |
|---|---|---|
| conftest.py | 0 | Fixtures: fake GeckoTerminal and DexScreener routes on a mock HTTP transport |
| test_agent.py | 5 | Agent loop end to end (demo, JSON and plain outputs), snapshot feeds, flat candles closed by clock, error propagation, history failure is not fatal |
| test_candles.py | 9 | Timeframe parsing, candle assembly, gap fill, grace-period close, late ticks, snapshots, CSV |
| test_chain_events.py | 10 | pump.fun log decoding: event attribution to the emitting program, slot numbers |
| test_decide.py | 9 | Causal launch states, scorer evaluation, caching, Jev client |
| test_fastloop.py | 14 | Policy, paper broker, deciders, journal, and the review |
| test_feeds.py | 10 | GeckoTerminal/DexScreener parsing and polling, HTTP retries, PumpPortal against local websocket servers |
| test_market.py | 10 | Source selection (chain/DexScreener/PumpPortal), pool→token, cold start, missing Gecko timeframe, errors as notes |
| test_model.py | 9 | Online model on synthetic series: honest confidence on a random walk, finds real structure, dead tokens predict flat, nowcast, mixture quantiles, calibrator |
| test_pipeline.py | 13 | Raw logs, dataset, global model, train/serve feature parity |
| test_profit.py | 7 | Cost-aware trade simulation on recorded curves |
| test_pumpswap.py | 4 | PumpSwap decoding, canonical pools, live feed |
| test_pumpswap_model.py | 5 | Loading graduated tokens, train/serve parity, the agent's switch at graduation |
| test_review_fixes.py | 20 | Regression tests for defects found in the accuracy review |
| test_rug.py | 5 | AUC/Platt, train-save-load, screen-state parity, P(rug) on verdicts, labelled states |
| test_scam.py | 10 | Wallet behaviour, mint checks, RugCheck, creator history, launch screening |

There are 5 JSON fixtures of real transactions in `tests/data/`. No tests are parametrized, so 140 is the case count. Older docs give older counts: "81 tests" (handoff/candle-prediction-agent.md:52, :60, :127) and 134/135 tests in the STATUS log (STATUS.md:235, :247).

### 11. Places where docs and code disagree
- **Data capture.** The README's "Data quality" section says median capture is about 63% (README.md:232-235). That was the first run only. STATUS later reports a median of 100% / mean of 97% on `raw-eager` (STATUS.md:61-63), and the v3 report shows 99.2% / 91.0% (trades-60s.report.json:127-132).
- **Fast loop and Jev.** The README still presents both as active (README.md:161-178). The user retired both (slow-loop.md:3-5).
- **Graduated-token model.** The README says "graduated tokens get their own model" (README.md:97-99), but none is installed.
- **Source lists.**
  - `open_market`'s docstring says pump tokens stream from PumpPortal, but the code defaults to the chain (market.py:92 vs :153).
  - The README `--source` option row lists only auto/pumpportal/dexscreener/gecko (README.md:138).
  - `pumpportal.py`'s docstring says PumpPortal is free for curve trades (pumpportal.py:1-5), while README.md:214 and candle-prediction-agent.md:137 say it needs a funded key.
- **Profitability doc.**
  - The summary table still lists PumpSwap as "pre-registered" (profitability.md:24), though §3.16 reports "no edge".
  - §4 is stale: it asks for a PumpSwap decoder and network access (profitability.md:620-645).
- **Predictor doc.**
  - The status row still names a private RPC as the fix for the biggest open problem (candle-prediction-agent.md:51); the user declined one.
  - Problem 7 still says the agent drops the global model at graduation and that there is no swap loader (candle-prediction-agent.md:870-876).
- **STATUS queue 12** still lists European hours as open (STATUS.md:182-184), though they were sampled (profitability.md:476-479).
- **Domain for direct PumpSwap watches** (from reading the code; not tested). `MarketInfo.domain` treats only solana-rpc, pumpportal and simulated feeds as trade data (market.py:26, :47-50). A token opened directly on PumpSwap is therefore looked up and modelled as "ohlcv". A token that graduates while being watched switches to the "pumpswap" trade domain (agent.py:226-232). The predictor doc says pumpswap counts as a trade domain wherever trades did (candle-prediction-agent.md:539-540).

### Open items
- **PumpSwap global model.** None is trained or installed yet. STATUS says to run `tartar train --raw <dirs> --pumpswap` after 11a (now evaluated), install it only if it beats online-only, and give the pumpswap domain its own flat-candle prior (handoff/STATUS.md:256-259). The README already implies the model exists (README.md:97-99).
- **OHLCV model.** The candle-only model is untrained because GeckoTerminal returned 429 from the container. Non-pump.fun tokens rely on the online model alone (handoff/candle-prediction-agent.md:878-884).
- **Predictor v3.1** is held by the clever session's active claim (STATUS.md:35-40).
  - 5m fix: down-weight or drop old-recorder rows, with the weight chosen on validation from 1/0.5/0.25/0.1/0.
  - 15s/30s/1m: retrain on every recording at full weight.
  - Also check the blend prior (1m underconfident on raw-clever) (handoff/candle-prediction-agent.md:493-517; STATUS.md:77-80).
- **Documentation drift to fix:**
  - README data-quality capture figure (README.md:232-235)
  - README fast-loop/Jev section not marked retired (README.md:161-178)
  - README auto-source list missing the pumpswap step (README.md:216-223) and the `--source` option row (README.md:138)
  - cli.py docstring missing scan/learn (tartar/cli.py:1)
  - open_market docstring says PumpPortal (tartar/market.py:92)
  - pumpportal.py docstring says free (tartar/feeds/pumpportal.py:1-5)
  - profitability.md table row for PumpSwap still "pre-registered" (handoff/profitability.md:24), and §4 stale (:620-645)
  - predictor doc test count 81 (handoff/candle-prediction-agent.md:52), status row (:51), and open problem 7 (:870-876)
  - STATUS queue 12 European hours (STATUS.md:182-184)
  - handoff/code/ snapshot stale relative to tartar/ and tests/
- **Established-memecoin dip rule forward test.** Run established_cohort.py about once a day; score at ≥200 trades or on 2026-10-30 (handoff/STATUS.md:160-163).
- **jevtrader.** The user's sealed test ends 2026-10-23 (results that evening). TARTAR only supplies on-chain SOL-USD cost quotes (~0.5 bps per fill; quotes, not fills). Still open: cost samples at US hours, about 13-16 UTC, which are in the clever session's claim (handoff/STATUS.md:35-40, :166-184; profitability.md:480-481).
- **Predictor session** (since 2026-10-09 12:55 UTC) has claimed an edge hunt on untested strategy families and a project overview (handoff/OVERVIEW.md, not yet present). No results yet. It is recording `data/raw_v3` (handoff/STATUS.md:42-46).
- **GitHub write access.** The blocker for the profitability session's account (403 on push, 10-09 ~03:40 UTC) is still listed (handoff/STATUS.md:53-56). Later entries say pushing works from the research session (04:50 UTC) and the Jev session (05:04 UTC) (STATUS.md:293, :295-296), and commits were pushed through 12:55 UTC.
- **Tests.** The count was taken by grep only; pytest was not run in this read-only pass, so pass/fail status is not verified.
