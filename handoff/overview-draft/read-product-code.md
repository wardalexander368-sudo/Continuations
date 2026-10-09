<!-- read:product-code: workflow section summary as of 2026-10-09 12:56 UTC; 'verify-*' files are fact-checked, 'read-*' are not -->

## What TARTAR is and how the code is organized (as of 2026-10-09 12:56 UTC)

### 1. TARTAR in one paragraph
TARTAR is a Python command-line tool (package `tartar` 0.1.0, Python 3.10+, depends on numpy, httpx, websockets, rich and lightgbm; entry point `tartar = tartar.cli:main`; pyproject.toml:6-23). It runs a live agent that "watches the candle chart of any Solana token, including tokens launched minutes ago, and predicts each candle's closing price", and gives each prediction a confidence. The agent scores itself on every candle, so you can see whether the stated confidence matched what happened (README.md:3-6). Around that predictor the repo grew three more parts: a scam/risk filter, an offline data and training pipeline, and a set of tools that ask whether any of it makes money after costs (profit, decide, fast loop, review). The money answer so far is **no**: "No strategy tested is profitable at realistic costs on this data" (handoff/profitability.md:10-13; README.md:157-159).

Size: 44 Python files and about 9,900 lines in `tartar/`, plus about 2,700 lines in `tests/` (line counts with `wc`).

### 2. Terms used below
- **pump.fun launch / bonding curve**: a new token on pump.fun first trades against a formula-priced pool (a constant-product "curve" with virtual reserves; the standard curve holds 30 virtual SOL, tartar/feeds/pumpportal.py:25). The curve is the order book.
- **Graduation**: once about 85 SOL has been raised in the curve, the token moves to an AMM (tartar/model/engine.py:20-21). That AMM is **PumpSwap**, pump.fun's own pool program (tartar/feeds/pumpswap.py:1).
- **Candle**: price open/high/low/close over a fixed period (15s, 30s, 1m, 5m, ...).
- **Slot**: a Solana block position. The rawlog docstring says about 0.4 s per slot (tartar/data/rawlog.py:26-29); a later measurement found about 270 ms (handoff/STATUS.md:95).
- **bps**: basis points, 0.01%.
- **Edge**: how much smaller the forecast error is than the naive guess "close = last price" (handoff/candle-prediction-agent.md:31-33).
- **Band**: a range the close should land in 80% of the time.
- **Locked at open**: the forecast fixed when a candle opens; this is the forecast that gets scored (README.md:189-192).
- **Paper trading**: simulated fills only, with no real transactions.

### 3. The original goal
The user asked for "an agent that can watch a candle graph live, predict the next candle closing price on any new sol coin/token and live-output that result and its confidence of that result". They then said: "build the highest accuracy predictor that we can. That is this project's only job." Scam filtering was requested later (handoff/candle-prediction-agent.md:16-27). "Accuracy" has three operational parts (same doc :29-39):
1. Edge over the naive forecast.
2. Stated confidence equal to the realised hit rate, described as "non-negotiable: the system must never invent conviction".
3. An 80% band that really covers 80%.

All of these are measured on tokens launched after the training data. The README warns users to "Expect low confidence": next-candle moves of young memecoins are mostly noise (README.md:201-204).

### 4. Live data flow (`tartar watch`)
`feeds/* → Tick / Snapshot / Status → CandleAgent → CandleBook (candles) → Forecaster (FeatureEngine + WalletTracker + GlobalModel + online model) → Scoreboard + scam.assess → sinks (Dashboard / PlainPrinter / JsonLines)` (handoff/candle-prediction-agent.md:83-100).

**4.1 Feeds and source choice.** `market.open_market` looks the address up on GeckoTerminal and DexScreener at the same time, then picks a source. The valid sources are `auto, chain, pumpportal, pumpswap, dexscreener, gecko` (tartar/market.py:25). `auto` works like this (tartar/market.py:151-166):
- A pump.fun mint (address ends in "pump") still on its curve uses `chain`. It uses `pumpportal` instead if `PUMPPORTAL_API_KEY` is set.
- A graduated pump.fun token on PumpSwap uses `pumpswap`.
- Any other token with a DexScreener pair uses DexScreener, polled every 3 s (market.py:187).
- Otherwise it falls back to GeckoTerminal OHLCV polling. Candles from that source close 75 s after they end (market.py:193).

Prices are in SOL for chain, PumpPortal and PumpSwap, and in USD otherwise (market.py:170). The README lists only three of these steps; it omits the PumpSwap step (README.md:216-223).

The feed modules:
- `feeds/pumpchain.py` reads the pump.fun program's logs over a Solana RPC websocket (`logsSubscribe`). It is free and needs no key, and it decodes Create, Trade and Complete events (pumpchain.py:1-7). The program id is `6EF8rrec…F6P` (:32). The default endpoint is the public mainnet websocket (:35); `SOLANA_RPC_WS` overrides it (:70-72). The commitment level comes from `SOLANA_COMMITMENT`, default "confirmed" (:324).
- `feeds/pumpportal.py` is the optional PumpPortal websocket. Its per-token trade stream needs a funded key (README.md:214).
- `feeds/pumpswap.py` decodes PumpSwap Buy/Sell events. It derives a graduated token's canonical token/WSOL pool and holds the market-cap fee tiers, 1.25% down to 0.6% per side (pumpswap.py:1-14, :35).
- `feeds/dexscreener.py` polls price; DexScreener has no candle endpoint, and its rate limit is about 300 requests/min (dexscreener.py:1-7).
- `feeds/geckoterminal.py` provides pool lookup, OHLCV history, new pools and polling. It allows about 30 requests/min and can lag up to about 1 min (geckoterminal.py:1-4).
- `feeds/http.py` is a rate-limited JSON client; `feeds/base.py` defines the feed interface (`Status.kind` is connected, disconnected or graduated); `feeds/synthetic.py` is the demo feed.

**4.2 Warm-up.** Before going live, the model is warmed up on up to 1000 historical GeckoTerminal candles. This is a walk-forward run: each candle is predicted using only the candles before it. A token too new to be indexed starts cold (README.md:225-228).

**4.3 Candles.** `candles.py` holds `Tick`, `Candle` and `CandleBook`. The book builds a gap-free series from ticks and/or snapshots and closes a candle by the clock plus a grace period.

**4.4 Features.** `model/engine.py` (`FeatureEngine`) computes the same features live and offline (engine.py:1-5). There are 55 features: 39 base, 9 for the partly formed candle, and 7 risk features from scam.py (engine.py:23-48; scam.py:41-49; 55 entries in trades-60s.json). They cover price action, activity, order flow, wallets, the creator's wallet, lifecycle (age, curve progress) and the forming candle so far. The README says "about 50" (README.md:252-253).

**4.5 Models.** Two predictive distributions are blended (tartar/model/forecaster.py:144-165):
- **Global model** (`model/global_model.py`): one LightGBM multiclass model. Class 0 means "price doesn't move again"; the other 24 classes are bins of the volatility-scaled remaining move (global_model.py:1-7, :23-28). It is trained on snapshots at 0/20/40/60/80/95% through each candle (dataset.py:31) and calibrated with temperature scaling (train.py:46). Training rows mimic live conditions: about 30% are "late joins", where watching starts mid-life (dataset.py:374-375; README.md:266-275).
- **Online model**, learned per token while watching (README.md:277-301):
  - EWMA volatility (model/volatility.py).
  - An expert ensemble: random walk, drift, and ridge experts for momentum, order flow and a full ridge, with prior weights 0.4/0.15/0.15/0.15/0.15 (model/ensemble.py:122-129). The combined signal is scaled by a reliability slope that never exceeds 1.
  - An empirical error distribution and a mixture with a "no further trade" point mass (model/predictive.py).
  - Flat-candle odds (volatility.py `ActivityEstimator`).
  - Direction recalibration (predictive.py `DirectionCalibrator`).
  - An adaptive conformal band (forecaster.py:161-163).
- **Blend**: the global weight is σ(logit(prior) + discounted log-score difference), with prior 0.95 (forecaster.py:178, :233-235; handoff/candle-prediction-agent.md:544-547).

**4.6 Agent.** `CandleAgent` (agent.py:64-318) runs the loop:
- warm-up, then streaming
- each event is processed in full: close candles first, then apply the trade
- scam checks (RPC mint + RugCheck) refresh in the background
- candles seen only partly during a feed outage are never scored or learned from; after an outage the agent resyncs the way a mid-life join starts (agent.py:224-266)
- at graduation it switches to a PumpSwap global model if one is installed, otherwise it continues online-only (agent.py:225-236)

**4.7 Outputs.** Chosen in `cli._make_sinks` (cli.py:207-222):
- **Dashboard** (`dashboard.py`, refreshed every 0.25 s; class at :150):
  - header: symbol, risk level and P(rug)
  - candle chart on a log price scale, with the predicted close ◆ and its band ┊ (render_chart :29)
  - "Next close" panel: predicted close, direction confidence, 80% band, locked-at-open forecast, volatility
  - "Track record" panel: last 50 candles, this session, and the warm-up, plus the model mix
  - "Recent results" footer (last 7)
- **Plain log lines**: every 10 s by default.
- **JSON lines**: every 1 s. Event types are start, warmup, candle, forecast, prediction, result, status, summary (README.md:313-328), plus a `risk` event (README.md:36).
- Calls at or below 52% are labelled "≈ coin flip" (output.py:20).
- `scoreboard.py` keeps separate tallies for the warm-up and live candles and buckets stated confidence against realised hit rate (scoreboard.py:95-121).

### 5. Installed models (`tartar/models/`, loaded automatically for pump.fun tokens)

| File | Trained on | Trained at (UTC) | Live replay, global+online, all candles (hit / stated / edge) | Online only (edge) |
|---|---|---|---|---|
| trades-15s | 9,184 tokens (json:93) | 2026-10-09T06:54:01Z | 91.5% / 91.3% / +1.8% | −0.2% |
| trades-30s | 8,927 tokens (json:95) | 2026-10-09T07:30:36Z | 89.6% / 89.2% / +4.4% | −0.2% |
| trades-60s | 8,560 tokens (json:93) | 2026-10-09T06:27:59Z | 86.0% / 85.9% / +6.2% | −0.5% |
| trades-300s | 4,683 tokens (json:95) | 2026-10-09T07:39:30Z | 61.3% / 68.6% / +6.5% | −0.0% |
| rug-20s (P(rug)) | 5,267 launches (json:30) | 2026-10-09T07:10:57+00:00 | test AUC 0.913, log loss 0.199 (json:34-35) | — |

The live-replay figures come from `tartar/models/trades-*.report.json` (`live_at_open` blocks, e.g. trades-60s.report.json:244-262 and trades-300s.report.json:246-264). These are predictor v3, installed 07:50 UTC 10-09 (handoff/STATUS.md:74-80). Two caveats:
- The 5m model is overconfident on new launches: it states about 70% and hits 61-65% (STATUS.md:77-80).
- No `pumpswap-*` model and no `ohlcv-*` model is installed. The candle-only (OHLCV) model "is untrained" (handoff/candle-prediction-agent.md:878-884), so DexScreener and GeckoTerminal tokens run online-only.

P(rug) is the chance a launch falls ≥80% without graduating within 30 min, judged 20 s after launch. It is shown but never used to skip a launch (README.md:73-78; rug.py:1-15).

### 6. Offline pipeline
1. **Record.** `tartar record` uses `ChainRecorder`, which is free and reads the chain logs; `Recorder` is the PumpPortal variant (recorder.py:1-4). It records every launch for `--track-minutes` (default 60), with at most 3000 tokens tracked at once. `--pumpswap-hours N` also follows each graduated token's PumpSwap pool (cli.py:107-120; recorder.py:186-205).
2. **Raw logs.** These are hourly JSON-lines files, gzipped once done (`data/rawlog.py`). Event types: create, trade, migrate, track, untrack, session, graduate, swap, unwatch. Since 2026-10-09 events carry `slot`, and curves priced in a token other than SOL carry `quote` (rawlog.py:1-37).
3. **Dataset.** `data/dataset.py` rebuilds candles per token with the live feature code. It cuts each token's history at the first recorder disconnection and splits 70/15/15 by launch time (graduation time for PumpSwap tokens) (dataset.py:1-7, :76-84).
4. **Train.** `train.py`: LightGBM with early stopping, temperature fit, out-of-fold median shrink, and an honest report on the latest tokens, including a replay of the live forecaster (train.py:1).
5. **Install.** `tartar train` installs the new model only if its test log loss beats the installed one; `--force` overrides (cli.py:582-597). `tartar learn` records continuously and retrains in a subprocess, first after 3 h and then every 6 h (cli.py:197-203, :874-901).

Side tools:
- `data/collect.py` (`tartar collect`) downloads GeckoTerminal OHLCV histories for a candle-only model.
- `data/simulate.py` (`tartar simulate`) writes made-up pump.fun launches on real curve math, for pipeline tests only. Models trained on it load only in `demo` (README.md:344-347; simulate.py:1-7).

The training data is not in git: `/data/` and `*.jsonl` are git-ignored (.gitignore). Snapshots live in `handoff/data/`, described in handoff/data/README.md.

### 7. Risk, profit and decision side

| Module | What it does | Status |
|---|---|---|
| `scam.py` | Three evidence layers (scam.py:1-14). Behaviour, via `WalletTracker`: dev dump, sniped/bundled supply, top-10 holders, wash trading, few traders, odd curve, ≥90% collapse. The mint, via RPC: mint/freeze authority, Token-2022 extensions. Reputation: RugCheck plus `CreatorIndex` (creator rugs, serial launches, copycats). `assess` turns these into ok/caution/danger/scam (:256-372). | Built. `sniped`/`concentrated`/`dev_dumped` alone are only "caution" (scam.py:277-279). |
| `rug.py` | P(rug) LightGBM on 18 screen numbers, Platt-calibrated, time split 70/15/15 (rug.py:1-36). | Shipped 07:15 UTC 10-09 (STATUS.md:185-190). |
| `screen.py` | `watch --next-launch`: follows each launch for 20 s and skips it if it has fewer than 3 non-creator buyers, if `avoid` is set, or if it is priced in a token other than SOL (screen.py:53-118; README.md:64-71). | In use. |
| `market.py` | Not a trading module: it turns an address into a live feed plus warm-up history; `launch_market` handles brand-new launches (market.py:78-267). | In use. |
| `profit.py` (`tartar profit`) | Round trips on the recorded curves with every cost charged. Defaults: 0.1 SOL, 1.25% fee per side, 0.0002 SOL per transaction, 1 s latency (profit.py:1-30; cli.py:158-166). | Result: no strategy is profitable (README.md:157-159). |
| `decide.py` (`tartar decide`) | Buy-or-skip scorers (buy every launch, the screen, `FlagScorer`, `LightGBMScorer`, optionally Jev) at +20 s. Thresholds are chosen on validation; results are reported on test by net SOL (decide.py:1-9; cli.py:722-793). | Study tool. Launch buying is closed as a strategy (profitability.md:19). |
| `fastloop.py` (`tartar fast`) | Live or replay loop: screen, skip rules, scorer ("rules" or "jev"), **paper** fill matching `profit.round_trip`, JSON-lines journal. The policy refuses any mode except "paper" (fastloop.py:1-21, :115-117). | **Live loop retired** 2026-10-09 by the user; `--replay` remains a study tool (handoff/slow-loop.md:3-5; STATUS.md:67-71). |
| `jev.py` | Client for TypeSafe's Jev decision API: questions about the launch and its metadata, cached by mint, needs `TYPESAFE_API_KEY` (jev.py:1-24). | **Off**: "No Jev calls from TARTAR" (STATUS.md:50-51, :208-210). It showed no signal in three tests (STATUS.md:67-70). |
| `metadata.py` | Fetches launch metadata JSON through IPFS gateways and computes link features (metadata.py:1-11). | Used by the Jev metadata study. |
| `review.py` (`tartar review`) | The "slow loop": the journal plus counterfactual outcomes for every screened launch, scorer calibration, and the best threshold in hindsight (review.py:1-11). | Tied to the retired fast loop. |
| `scoreboard.py` | Track record of locked forecasts: is the stated confidence honest? | In use (agent, backtest). |
| `backtest.py` (`tartar backtest`) | Walk-forward run of the **online model only** on one token's history (backtest.py:12-24). | In use. |

Strategy families closed after costs (handoff/profitability.md:17-26 and §3.16 at :582-618):
- launch buying (including faster entry)
- the graduation run-up
- longer holds
- copy-trading
- graduated tokens on PumpSwap (pre-registered study, 264 pools, test means −19.6 / −22.5 / −38.1 / −3.4%)

Still open:
- established-memecoin dip buying: a forward test scored on 2026-10-30
- SOL-USD for the user's separate jevtrader project: TARTAR only supplies on-chain cost quotes of about 0.5 bps per fill (quotes, not fills); its sealed test ends 2026-10-23 (STATUS.md:166-181)

### 8. All CLI subcommands (`tartar/cli.py`, 15 in total)

| Command | Where | What it does |
|---|---|---|
| `watch <mint>` / `--next-launch` | cli.py:60-73, 289-337 | Live prediction (dashboard, plain or JSON). `--next-launch` screens new launches and watches the first that passes. Options: `--source`, `--history 500`, `--screen 20`, `--min-buyers 3`, `--allow-risky`, `--no-scam-check`, `-t`, `--band 0.8`, `--log`, `--candles`, `--no-model` |
| `new` | :75-79, 379-422 | Newest Solana pools from GeckoTerminal (`--safe` hides danger/scam), or a live stream of pump.fun launches from PumpPortal |
| `backtest` | :81-87, 425-454 | Walk-forward calibration table on a token's history or a CSV |
| `demo` | :89-94, 340-361 | Agent on a simulated pump.fun token at 20× speed, no network needed |
| `scan` | :96-99, 904-946 | One-off scam report; exit code 3 if danger or scam |
| `resolve` | :101-105, 457-479 | Shows the pool, source and history `watch` would use |
| `record` | :107-120, 493-514 | Records launches and trades (chain or PumpPortal); optional PumpSwap pools |
| `collect` | :122-127, 517-525 | Downloads GeckoTerminal OHLCV histories |
| `simulate` | :129-133, 528-533 | Writes simulated raw logs |
| `train` | :135-156, 544-679 | Trains, evaluates and installs (keep-better) the global model (`--raw`/`--ohlcv`), the PumpSwap model (`--pumpswap`) or P(rug) (`--rug`) |
| `profit` | :158-166, 682-719 | Net SOL of baselines and model-signal strategies after costs |
| `decide` | :168-178, 722-793 | Compares buy-or-skip scorers by net SOL (`--jev` optional) |
| `fast` | :180-187, 796-851 | Fast loop, live (records too) or `--replay`; paper only |
| `review` | :189-195, 854-871 | Review of the fast-loop journal with counterfactuals |
| `learn` | :197-203, 874-901 | Records continuously and retrains on a schedule |

The module docstring at cli.py:1 lists 13 commands; it omits `scan` and `learn`.

### 9. Module map by purpose
- **Entry / CLI**: `tartar/__init__.py` (version), `__main__.py`, `cli.py`
- **Live agent and outputs**: `agent.py`, `candles.py`, `clock.py` (real and simulated clocks), `dashboard.py`, `output.py`, `scoreboard.py`, `backtest.py`
- **Market resolution and feeds**: `market.py`, `feeds/base.py`, `feeds/http.py`, `feeds/pumpchain.py`, `feeds/pumpportal.py`, `feeds/pumpswap.py`, `feeds/dexscreener.py`, `feeds/geckoterminal.py`, `feeds/synthetic.py`
- **Prediction models**: `model/engine.py` (features), `model/forecaster.py` (blend, band, nowcast), `model/global_model.py`, `model/volatility.py`, `model/ensemble.py`, `model/features.py` (online experts' 10 features), `model/predictive.py`; trained files in `models/`
- **Offline data and training**: `data/recorder.py`, `data/rawlog.py`, `data/dataset.py`, `data/collect.py`, `data/simulate.py`, `train.py`
- **Risk**: `scam.py`, `screen.py`, `rug.py`, `metadata.py`
- **Profit and decisions**: `profit.py`, `decide.py`, `fastloop.py`, `review.py`, `jev.py`
- **Outside the package**:
  - `handoff/`: STATUS.md is the shared board; `candle-prediction-agent.md` covers the predictor; `profitability.md`, `slow-loop.md` and `jevtrader.md` are the other topic docs
  - `handoff/experiments/`: study scripts
  - `handoff/preregistration/`
  - `handoff/data/`: data snapshots
  - `handoff/code/`: a source snapshot that is now stale; a diff shows it lacks `rug.py`, `test_rug.py`, `test_pumpswap_model.py` and the rug model, and many files differ

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
| test_market.py | 10 | Source selection (chain/DexScreener/PumpPortal), pool→token, cold start, errors as notes |
| test_model.py | 9 | Online model on synthetic series: honest confidence on a random walk, finds real structure, dead tokens predict flat, nowcast, mixture quantiles, calibrator |
| test_pipeline.py | 13 | Raw logs, dataset, global model, train/serve feature parity |
| test_profit.py | 7 | Cost-aware trade simulation on recorded curves |
| test_pumpswap.py | 4 | PumpSwap decoding, canonical pools, live feed |
| test_pumpswap_model.py | 5 | Loading graduated tokens, train/serve parity, the agent's switch at graduation |
| test_review_fixes.py | 20 | Regression tests for defects found in the accuracy review |
| test_rug.py | 5 | AUC/Platt, train-save-load, screen-state parity, P(rug) on verdicts, labelled states |
| test_scam.py | 10 | Wallet behaviour, mint checks, RugCheck, creator history, launch screening |

There are 5 JSON fixtures of real transactions in `tests/data/`. Other docs give older test counts: "81 tests" (handoff/candle-prediction-agent.md:52, :127) and 134/135 tests in the STATUS log (STATUS.md:235, :247).

### 11. Places where docs and code disagree
- The README's "Data quality" section says the median capture is about 63% (README.md:232-235). STATUS later reports a median of 100% / mean of 97% on `raw-eager` (STATUS.md:61-63).
- The README still presents the fast loop and the Jev scorer as active (README.md:161-178). The user retired both (slow-loop.md:3-5).
- The README says "graduated tokens get their own model" (README.md:97-99), but none is installed.
- `open_market`'s docstring says pump tokens stream from PumpPortal, but the code defaults to the chain (market.py:92 vs :153).
- The profitability summary table still lists PumpSwap as "pre-registered" (profitability.md:24) even though §3.16 reports "no edge".

## Open items
- No PumpSwap global model is trained or installed yet. STATUS says to run `tartar train --raw <dirs> --pumpswap` after 11a (now evaluated), install it only if it beats online-only, and give the pumpswap domain its own flat-candle prior (handoff/STATUS.md:256-259). The README already implies the model exists (README.md:97-99).
- The candle-only OHLCV model is untrained (GeckoTerminal returned 429 from the container), so non-pump.fun tokens rely on the online model alone (handoff/candle-prediction-agent.md:878-884).
- The 5m v3 model is overconfident on new launches (states ~70%, hits 61-65%). The planned fix is to retrain with raw-clever and down-weight or drop old-recorder rows at 5m (handoff/STATUS.md:77-80).
- Documentation drift to fix:
- README data-quality capture figure (README.md:232-235)
- README fast-loop/Jev section not marked retired (README.md:161-178)
- README auto-source list missing the pumpswap step (README.md:216-223)
- cli.py docstring missing scan/learn (tartar/cli.py:1)
- open_market docstring says PumpPortal (tartar/market.py:92)
- profitability.md summary table row for PumpSwap still 'pre-registered' (handoff/profitability.md:24)
- predictor doc test count 81 (handoff/candle-prediction-agent.md:52)
- predictor doc open problem 7 still says the agent drops the global model at graduation and that there is no swap loader (handoff/candle-prediction-agent.md:870-876)
- handoff/code/ snapshot is stale relative to tartar/ and tests/ (missing rug.py, test_rug.py, test_pumpswap_model.py).
- Established-memecoin dip rule forward test: run established_cohort.py about once a day and score at >= 200 trades or on 2026-10-30 (handoff/STATUS.md:160-163).
- The user's jevtrader sealed test ends 2026-10-23 (results that evening); TARTAR only supplies on-chain SOL-USD cost quotes (~0.5 bps per fill, quotes not fills). Still open: cost samples at US hours, about 13-16 UTC (handoff/STATUS.md:166-184).
- Predictor session (since 2026-10-09 12:55 UTC) has claimed an edge hunt on untested strategy families and a project overview (handoff/OVERVIEW.md), with no results yet; it is recording data/raw_v3 (handoff/STATUS.md:42-46).
- GitHub write access blocker for the profitability session (403 on push, 10-09 ~03:40 UTC) is listed as unresolved (handoff/STATUS.md:53-56).
- The test count was taken by grep only; pytest was not run in this read-only pass, so pass/fail status is not verified.
