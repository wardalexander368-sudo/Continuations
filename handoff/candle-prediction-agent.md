# Handoff: TARTAR, the live next-candle predictor for new Solana tokens

> **Two sessions share this repo. Read `handoff/STATUS.md` first**: the
> protocol, who is active, and the ranked task queue.

This document lets a new Claude session continue the work without the previous
conversation. Everything here was true when it was written (2026-10-08, ~20:30
UTC). The code is in this repository; `handoff/archive/predictor-snapshot-2026-10-09/` holds a snapshot copy of
every source file. `handoff/data/` holds the real data recorded so far (the exact
snapshot v1 was trained on).

---

## 1. Goal

The user asked for:

> an agent that can watch a candle graph live, predict the next candle closing
> price on any new sol coin/token and live-output that result and its
> confidence of that result

and then:

> Do anything you need to do to build the highest accuracy predictor that we
> can. That is this project's only job.

Later they asked for **scam filtering**, which is built (section 9).

**What "accuracy" means here, operationally:**

1. The **predicted close** (the median of a predictive distribution) should have
   lower absolute log error than the naive "close = last price". We call the
   relative reduction **edge**.
2. The **stated confidence** should equal the realized hit rate (calibration).
   This is non-negotiable: the system must never invent conviction.
3. The **80% band** should contain the close 80% of the time.

Everything is measured on **tokens launched after the training data** (a time
split by launch), plus a candle-by-candle replay of the live forecaster.

## 2. Status in one screen

| Item | State |
|---|---|
| Repo / branch / PR | `StaticPush7217/TARTAR`. All work is on `main` (fast-forwarded from branch `claude/solana-candle-predictor-s95qjr`, PR #1) |
| Live agent (`tartar watch`) | Works end to end against real tokens (pump.fun via chain, others via DexScreener/GeckoTerminal) |
| Global models | **v3.1 installed** (2026-10-09, section 8.2.2d) for **15s, 30s, 1m and 5m** candles: `tartar/models/trades-{15s,30s,60s,300s}.*`, 7,700–15,500 real pump.fun launches (31 leaves, 2,000 rows per leaf). v3 is in 8.2.2c, v2 in 8.2.1–8.2.2, v1 (3,523 launches, 1m only) in 8.2 |
| Real-data result (v1, held-out later launches) | At candle open: hit 85.3% vs stated 85.2%, error **4.7% below naive**, 0.61 bits/row of information over the base rate; the 80% band covers 91.9% and states 91.3% (calibrated; the excess over 80% is the "no further trade" mass, section 8.2). Live replay (global + online): **edge +7.5%** on all candles, **+7.8%** on candles where the token is trading; hit 69.0% vs stated 67.8% there |
| Online-only fallback | Fixed by the online-model review (section 11.1): now calibrated on real tokens (hit 79.3% vs stated 78.8%; trading 46.0% vs 45.1%), edge 0 (was −5.3%, and 23% hit at 52% stated on trading candles) |
| Data recording | `tartar record --pumpswap-hours 4` in the active sessions' containers; finished hours are copied to `handoff/data/<recorder>/` (`handoff/data/README.md`; who records now: `handoff/STATUS.md` *Active*) |
| Biggest open problem | No longer capture: since 10-09 the recorder gets a median 100% / mean 97% of each token's trades from the public RPC (v1 data: 93% / 84%). Open: the 5m model's overconfidence at the candle open (8.2.2d) and the rest of section 12 |
| Tests | 140 passing (`pytest`, 2026-10-09) |
| Scam filtering | Built, live-tested and validated (section 9); **P(rug)** (9.1) ranks 30-min collapses at AUC 0.91 vs the level's 0.74 |
| Profitability | `tartar profit` (net SOL after fees, slippage, latency). **No strategy is profitable on the recorded data**; see `handoff/profitability.md` |

## 3. Running it

```bash
pip install -e ".[dev]"     # Python 3.10+; numpy, httpx, websockets, rich, lightgbm
pytest                      # 81 tests, ~1-3 min (one CLI training test is slow)

tartar demo                                   # simulated pump.fun token, offline
tartar watch <MINT>                           # dashboard; -o plain / -o json
tartar watch --next-launch                    # screens new launches, watches the first clean one
tartar scan <MINT>                            # scam report
tartar new [--safe]                           # newest pools (GeckoTerminal)

tartar record --hours 12                      # record launches + trades (chain, free)
tartar train --raw data/raw [-t 1m]           # train, evaluate, install (keeps the better model)
tartar learn                                  # record + retrain every 6h
tartar collect -t 1m && tartar train --ohlcv data/ohlcv/1m   # candle-only model (GeckoTerminal)
tartar simulate --tokens 500 --out data/sim   # synthetic raw logs (pipeline tests only)
tartar backtest <MINT> | --csv FILE           # online-model walk-forward on one token's history
tartar resolve <MINT>                         # which source/pool/history watch would use
```

Environment variables: `SOLANA_RPC_WS` (comma-separated websocket endpoints;
default the official public one), `SOLANA_RPC_HTTP` (for mint checks),
`PUMPPORTAL_API_KEY` (optional), `TARTAR_MODEL_DIR` (model directory override).

## 4. Architecture

```
            ┌───────────────────────── live ─────────────────────────┐
 feeds/  ── Tick / Snapshot / Status(kind) ──► CandleAgent (agent.py)
  pumpchain (Solana RPC logs, pump.fun)          │ CandleBook (candles.py): ticks → candles,
  pumpportal (optional, needs funded key)        │   gap-fill, close by clock + grace
  dexscreener (3s price polls)                   │ Forecaster (model/forecaster.py)
  geckoterminal (OHLCV polls + history)          │   ├─ FeatureEngine (model/engine.py)   ◄── same code offline
  synthetic (demo)                               │   ├─ WalletTracker (scam.py)           ◄── same code offline
                                                 │   ├─ GlobalModel (model/global_model.py, LightGBM)
                                                 │   └─ online model: vol, ensemble, residuals, activity, calibrator
                                                 │ Scoreboard (scoreboard.py): scores locked-at-open forecasts
                                                 │ scam.assess → risk level
                                                 └► sinks: Dashboard (dashboard.py), PlainPrinter/JsonLines (output.py)
            ┌──────────────────────── offline ───────────────────────┐
 data/recorder.py (ChainRecorder) ──► raw JSONL (data/rawlog.py) ──► data/dataset.py ──► train.py ──► tartar/models/
 data/collect.py (GeckoTerminal OHLCV) ───────────────────────────►      (FeatureEngine + WalletTracker rows)
 data/simulate.py (bonding-curve simulator, same raw format)
```

### Module map

| File | Purpose |
|---|---|
| `tartar/candles.py` | `Tick`, `Candle` (with trades, buys/sells, wallets, new traders, creator flow, liquidity), `CandleBook` (live candle assembly, gap fill, clock close), CSV loading |
| `tartar/agent.py` | `CandleAgent` main loop. Each event is processed fully (close candles first, then apply the trade to wallet state, which keeps features causal). Feed-outage handling (unobserved candles, resync like a mid-life join), risk reporting, `View` for outputs |
| `tartar/model/engine.py` | `FeatureEngine`: ~55 features (base + partial-candle + risk), identical live and offline |
| `tartar/model/forecaster.py` | `Forecaster`: blends the global and online distributions, ACI band (skips flat closes it covered; target adjusted for the flat share), signal reliability (shrunk toward 0, never above 1), direction calibration, `nowcast()` during the candle, `Forecast`/`Outcome`. Domain-specific priors (`domain="trades"` vs `"ohlcv"`) |
| `tartar/model/global_model.py` | `GlobalModel` (LightGBM multiclass distribution: class 0 = no further move + 24 z-bins), `BinnedDistribution`, vectorized CDF/quantiles, atomic save/load, `find_model`, `model_dir` |
| `tartar/model/predictive.py` | `ResidualDistribution` (kernel-smoothed empirical + unit-normal prior; location of few residuals partly reflected about 0), `Mixture` (point mass + continuous; quantiles), `DirectionCalibrator` (discounted logistic slope fit, prior at 1, capped at 1) |
| `tartar/model/volatility.py` | `prior_sigma(tf, domain)`, `VolatilityEstimator` (EWMA of Parkinson + close-to-close, traded candles only), `ActivityEstimator` (flat odds from a two-state Markov chain on traded/flat candles; within-candle arrivals gamma-mixed Poisson) |
| `tartar/model/ensemble.py`, `features.py` | Online experts (random walk, drift, 3 ridge regressions) mixed by an exponentially weighted forecaster; their 10 features |
| `tartar/scam.py` | `WalletTracker` (behavioural signals; also model features), `assess` → `ScamReport`, `static_checks` (RPC mint + RugCheck), `CreatorIndex` (creator history/copycats from recordings) |
| `tartar/screen.py` | `--next-launch` screening (`next_clean_launch`, `judge`) |
| `tartar/market.py` | Resolve an address → source, live feed, warm-up history; `launch_market` for brand-new launches |
| `tartar/feeds/pumpchain.py` | Decode pump.fun Create/Trade/Complete events from `logsSubscribe`; `stream_program_events`; `PumpChainFeed`; `capture_rate` |
| `tartar/feeds/{dexscreener,geckoterminal,pumpportal,http,synthetic,base}.py` | Other sources, HTTP client with rate limiting, feed interface (`Status.kind`: connected / disconnected / graduated) |
| `tartar/data/recorder.py` | `ChainRecorder` (default, free), `Recorder` (PumpPortal, needs key) |
| `tartar/data/rawlog.py` | Raw event format, hourly rotating writer (gz), reader |
| `tartar/data/dataset.py` | Load raw logs → tokens → candles → feature rows; time split; late-join view; masking |
| `tartar/data/collect.py` | GeckoTerminal OHLCV collector (candle-only domain) |
| `tartar/data/simulate.py` | Agent-based pump.fun simulator (real curve math, invented behaviour) |
| `tartar/train.py` | `train_global`, temperature fit, `evaluate_rows`, `replay`, `evaluate`, `test_log_loss` |
| `tartar/cli.py` | All commands |
| `tartar/dashboard.py`, `output.py` | Rich full-screen dashboard; plain and JSON-lines outputs; formatting |
| `tests/` | 81 tests: candles, model calibration, feeds (mocked HTTP, local websocket servers), market selection, agent loop, pipeline (incl. train/serve parity), scam, review regressions |

## 5. Data sources: what works, what doesn't

| Source | Used for | Finding |
|---|---|---|
| **Solana public RPC `logsSubscribe`** on pump.fun program `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` | Live pump.fun trades, launch discovery, recording | Free, no key, real time. Decoding verified: trade SOL equals the curve reserve change exactly. **But it drops notifications under load**: one busy token had 38% of its on-chain trades captured; median capture across 695 tokens of the first run was **63%**; across the 3,180 measurable tokens of the v1 data it is 93% median, 84% mean (most tokens have few trades; busy tokens lose the most). Notifications also arrive **out of execution order** (~25–38% of consecutive trades of a token out of sequence). publicnode's free websocket delivered even less (removed from defaults). A second simultaneous connection from this container is often refused (`1002 protocol error`). **During the second recording run (from 18:32 UTC on 2026-10-08) the server closed the one connection 187 times in 1.6 h, every 10–30 s** (`ConnectionClosedError: sent 1002 (protocol error) invalid status code; no close frame received`); the client reconnects in 1.3 s (median; max 1.7 s) and keeps going, losing ~4% of wall time. Pings are off (`ping_interval=None`) and the receive queue is unbounded (`max_queue=None`) |
| **pump.fun event layouts (2026-10-09)** | Decoding | Authoritative source: pump.fun's public IDL, github.com/pump-fun/pump-public-docs `idl/pump.json` and `idl/pump_amm.json`; the program's on-chain IDL account is stale. Every trade instruction (V1, V2, V3, multi-hop) emits the same append-only TradeEvent; read trailing fields only while bytes remain. **Each curve has a quote mint**: SOL (zero key) for most launches, but also USDC, tokenized stocks, wXMR or another pump coin. On those, every SOL field is 0 and the amounts are in raw quote units (decimals are not in the event). Verified on 488 mainnet transactions (2026-10-09; 0 decode errors): **~15% of new launches and ~19% of trades are on quote-paired curves**, and every new launch now uses `CreateV2` (Token-2022 mints). Until 2026-10-09 the decoder dropped all quote-paired trades, so in older data those launches look dead. 1,863 of the 5,550 creates in `handoff/data/raw` have no first buy: the quote-paired ones plus SOL launches whose creator did not buy at creation. Filter on `create.vsol` present, or on the new `quote` field. Routers and other launchpads emit their own events named TradeEvent (same discriminator) in the same transactions: only events emitted inside pump.fun's own program frame count (`program_data`). Very large V2 transactions can hit "Log truncated", and their events are then missing from the logs (recoverable only from `getTransaction` inner instructions). Fees on SOL curves: 0.95% protocol + 0.30% creator per side (checked on 89 real trades) |
| **PumpSwap** (`pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`) | Graduated pump.fun tokens (`tartar/feeds/pumpswap.py`, source `pumpswap`) | Buy/Sell events carry PRE-trade reserves and the pool, not the mint. The price uses effective quote reserves (vault + signed `virtual_quote_reserves`; boosted pools carry ~17.5 SOL of it). The canonical pool is derived offline from the mint. Checked on 43 mainnet trades: the derived pool matched every time, and post-trade base reserves equalled the vault balance exactly. Followed with a per-pool `logsSubscribe` |
| **Latency in slots (2026-10-09, `handoff/experiments/slot_latency.py`)** | Fast-loop timing | 40 min "confirmed" recording (1,347 launches, 74,509 trades; `handoff/data/raw-slots`). **24% of the first minute's buy SOL lands in the launch's own slot**, 31% within its first 5 slots. That is bundled sniping, the only edge `profitability.md` found. Slots are **~270 ms**. Our notification arrives a median **1.47 s** after the block (p10 0.81 s, p90 5.1 s; block times have 1 s resolution). A decision at launch + 20 s acts ~95 slots after the create. **"processed" commitment** (`SOLANA_COMMITMENT=processed`, 6 min sample) cut the median to **1.15 s** and p90 to **2.0 s**, at the cost of rare events from blocks that are later dropped |
| **PumpPortal** websocket | Was the original source | `subscribeTokenTrade` now **requires an API key funded with ≥0.02 SOL**. `subscribeNewToken` is still free. Supported if `PUMPPORTAL_API_KEY` is set |
| **DexScreener** API | Lookup; live price polls (3s) for non-pump tokens | Works. Volume and trade counts come from deltas of the h24 totals (exact only for tokens under 24h old) |
| **GeckoTerminal** API | Warm-up history (up to 1000 candles), fallback live polling, new pools | Works (500 BONK candles fetched), but this container's shared egress IP hits **HTTP 429** constantly, so OHLCV collection got only 1 token. Data can lag ~1 min |
| **RugCheck** API | Scam checks | Free. `/v1/tokens/{mint}/report` (full; 400 for some tokens, then falls back to `/report/summary`); new launches are often not indexed yet |
| Solana HTTP RPC `getAccountInfo` | Mint/freeze authority, Token-2022 extensions | Works on public RPC. `getTokenLargestAccounts` is rate-limited (429) on public mainnet; publicnode requires a token for indexed calls |
| BigQuery public Solana dataset | Considered | No credentials in this environment |

**pump.fun specifics learned from real data:**

- ~84% of tokens use the standard curve (virtual SOL = real SOL + 30, k = 32.19e9).
  The rest have non-standard or changing virtual reserves. `vSOL / vTokens` is
  always the true price, so curve progress uses **real SOL raised** (graduation at ≈85 SOL).
- The create transaction usually contains the creator's first buy; the recorder
  folds that buy into the `create` event.
- The TradeEvent carries the token's **creator**, so the creator is known on every trade.
- Most launches never get a buyer: only 42% of 1-minute candles of young tokens
  have any trade. The median absolute 1-minute move on candles with trades is ~13%.
- Bundled launches are common: 70–80% of supply bought in the first 5 seconds,
  followed by the creator selling 100% within 15 seconds. Copycat spam
  (same name or metadata several times a minute) is common too.

## 6. Data pipeline

**Raw log** (`tartar/data/rawlog.py`), JSON lines, hourly files, gzipped on rotation:

```
{"e":"create","t","mint","creator","name","symbol","uri","sol","tok","vsol","vtok","rsol"}
{"e":"trade","t","mint","side":"b|s","trader","sol","tok","vsol","vtok","rsol"}
{"e":"migrate"|"track"|"untrack","t","mint",...}
{"e":"session","t","state":"connected|disconnected|stopped"}
```

`t` is the receive time, which is what live candles use too. The recorder tracks
each launch for 90 minutes (idle cut after 20 minutes) in the current run.

**Dataset** (`tartar/data/dataset.py`):

- **Windows.** A token's data runs from its create to the first of: untrack,
  migrate, stop, a disconnect that lasted more than `max_gap` (10 s) before
  the next `connected`, or the last event before a `connected` that follows no
  recorded drop (an unclean kill leaves no stop event). Short reconnects only
  lose a few seconds of trades, comparable to the stream's usual drop rate, so
  they no longer end the window; cutting at every one of the server's 10–30 s
  disconnects had shrunk the usable data to almost nothing. Launches without a `track` event within 2s
  are skipped. Trades are de-duplicated on (mint, side, trader, sol, reserves),
  in case two recorders overlap.
- **Candles** are built with the live `CandleBook` from ticks; flat candles fill
  quiet periods.
- **Rows.** For every closed candle t, there are rows for predicting candle t+1's
  close at fractions f = 0, 0.2, 0.4, 0.6, 0.8 and 0.95 of t+1, using only trades
  before that moment.
- **Targets.** Class 0 means the price does not change again before the close.
  Otherwise the class is 1 + bin of z = ln(close / price_now) / (σ·√(1−f)),
  with 24 bins over edges ±0.15…±4.
- **Live conditions mimicked.**
  - The creator is hidden for 30% of tokens, and the launch time for 15%
    (deterministic hash).
  - 30% of tokens (with more than 12 candles) use a **late-join view**:
    candle-only history up to a random candle k, then trades with wallets
    tracked from scratch, creator unknown. This matches a live watch that warms
    up on GeckoTerminal history.
- **Dead stretches** (5+ flat candles) are subsampled to 10% and weighted ×10.
- **Split** by launch time: 70% train / 15% validation (early stopping and
  temperature) / 15% test.
- **Capture rate.** Each token gets a `capture` estimate (share of recorded
  trades whose pre-trade reserves match another recorded trade's post-trade
  reserves; order-insensitive).

**Train/serve parity is tested:** `tests/test_pipeline.py::test_train_serve_parity`
feeds the same ticks through `CandleBook + FeatureEngine + WalletTracker` the way
the agent does and asserts equality with the dataset rows (NaNs included).
`tests/test_review_fixes.py::test_replay_feeds_wallets_like_training` checks the
replay too.

## 7. Features

**Global model** (`FEATURES` in `tartar/model/engine.py`; NaN where unknown):

- Price action (σ = per-candle volatility): `r1 r2 r3` (lagged returns/σ),
  `r1_raw`, `mom5 mom15`, `log_sigma`, `vol_ratio` (fast/slow σ), `clv`, `body`,
  `range`, `upper_wick`, `lower_wick`, `ema_dev`, `ema_trend`, `drawdown` (from
  the all-time high), `rise` (from the all-time low).
- Activity: `log_volume`, `volume_z`, `log_trades`, `trade_trend`, `flat_streak`,
  `idle` (time since the last trade).
- Order flow: `count_imb`, `flow_imb`, `flow5`, `whale_share`.
- Wallets: `log_traders`, `new_trader_share`, `cum_traders`, `trader_growth`.
- Creator: `creator_known`, `creator_sell`, `creator_sold`, `creator_left`.
- Lifecycle: `age`, `n_candles`, `curve_progress` (real SOL / 85), `log_price`
  (≈ market cap for pump tokens).
- Forming candle: `f`, `x0` (move so far/σ), `p_trades`, `p_activity`,
  `p_flow_imb`, `p_range`, `p_new_traders`, `p_creator_sell`, `p_idle`.
- Holders/scam behaviour (`RISK_FEATURES`, from `WalletTracker`):
  `top10_share`, `log_holders`, `creator_share`, `sniper_share`, `wash_share`,
  `trades_per_wallet`, `nonstandard_curve`.

**Candle-only (OHLCV) model:** the `OHLCV_FEATURES` subset in `train.py`. It
drops the high/low inputs, because live candle-only tokens are built from 3s
polls whose ranges are about half the true range.

**Online model features** (`tartar/model/features.py`): 10 scale-free features
for the ridge experts.

**v1 feature importance (gain):** `p_idle` 31%, `curve_progress` 8%, `idle` 4%,
`range` 4%, `f` 3%, `log_price` 2%, `rise` 2%, `sniper_share` 2%, `age` 2%,
`wash_share` 2%, `log_volume` 2%, `creator_share` 2%, `trades_per_wallet` 2%.
(v0: `p_idle` 25%, `curve_progress` 6%, `idle` 5%.) Time since the last trade
dominates: whether anything else trades before the close is the first question.

## 8. Models tried, and results

### 8.1 Online per-token model

- **Components:** EWMA volatility (Parkinson + close-to-close), an ensemble of
  experts (random walk, drift, momentum ridge, order-flow ridge, full ridge)
  weighted by an exponentially weighted forecaster that starts on the random
  walk, an empirical residual distribution with a prior (Laplace at first,
  unit normal since 11.1), an adaptive-conformal (ACI) band, and flat odds.
  The synthetic table and the decisions below describe the first version;
  section 11.1 changed several parts.
- **Synthetic calibration** (1500 candles each; `tests/test_model.py`):

| Series | Before fixes (hit / stated) | After reliability slope + direction calibrator | Band coverage | Edge |
|---|---|---|---|---|
| Random walk | 50.8% / 53.1% | 48.0% / 51.2% | 80.0% | ≈0 |
| Fat tails | 51.7% / 53.3% | 52.4% / 51.5% | 80.3% | ≈0 |
| AR(1) +0.3 (momentum) | 58.6% / 57.7% | 58.7% / 56.2% | 80.0% | +2.4% |
| AR(1) −0.3 (mean reversion) | 61.6% / 60.0% | 61.3% / 60.3% | 80.1% | +5.0% |

- **Decisions this led to:**
  - The overconfidence on pure noise came from sampling noise in the residual
    median, which `max(p_up, p_down)` turns into false conviction. Fixed with
    the `DirectionCalibrator` (slope on log-odds, shrunk toward 1).
  - A signal **reliability slope** (realized move regressed on the raw signal)
    fades unproven signals.
  - The **zero-inflated activity model** replaced a Poisson model: bursty tokens
    were under-predicted as flat. On simulated data online-only went from 44.6%
    hit / 51.3% stated to 47.9% / 50.8%.
- **Real data, first version (v0 replay, 117 test tokens): poor.** Hit 28.4%
  vs 45.7% stated, edge −2.4%; on tokens trading in the previous candle,
  18.8% vs 52.1%.
- **Real data after the online-model review (section 11.1).** Online-only
  replay on the same 300 held-out test tokens of the v1 data, forecasts
  locked at the open, each row adding to the one above:

| Online model | All: hit / stated | All: 80% band | All: edge | Trading: hit / stated | Trading: 80% band | Trading: edge |
|---|---|---|---|---|---|---|
| Before the review | 50.3% / 49.2% | 90.9% | −5.3% | 23.4% / 51.9% | 74.9% | −5.5% |
| + Markov flat odds, bursty arrivals, ACI fix, traded-only σ, launch σ prior | 76.3% / 65.9% | 93.6% | −2.3% | 39.4% / 47.1% | 82.8% | −2.4% |
| + flat-odds priors measured on the training split | 79.2% / 79.0% | 91.4% | −1.3% | 45.6% / 45.7% | 82.1% | −1.3% |
| + direction-odds fixes (final) | **79.3% / 78.8%** | 92.4% | **0.0%** | **46.0% / 45.1%** | 85.0% | **0.0%** |

  The online model is now honest but adds no point accuracy on these
  short-lived tokens: the signal ensemble never earns reliability, so its
  median stays at the last price. It is the fallback for every source and
  timeframe without a trained global model.

### 8.2 Global distributional model (LightGBM)

- **Design:** one multiclass model, 25 classes (no move + 24 z-bins), with
  exponential tails and temperature scaling on validation. Parameters: lr 0.05,
  63 leaves, min 100 rows per leaf, feature and bagging fraction 0.8, L2 1,
  early stopping 100.
- **Simulated data** (400–600 simulated tokens; only proves the pipeline works):
  test edge at the candle open +5.1–5.6%, hit 54.8–56.2% vs stated 54.0–56.4%,
  80% band 80–81%. Live replay with the blend: +4.1–4.9% edge and calibrated;
  online-only −3.2%.
- **Real data, v0** (786 tokens, 28,884 rows, 22,044 train; 33 boosting rounds;
  temperature 1.045). At the open: hit 81.5% vs stated 81.7%, 80% band 88.1%,
  edge +3.7%, info gain 0.340 bits. Live replay (117 tokens): global + online
  edge +1.8% (all) / +2.0% (trading).
- **Real data, v1 (installed)**: 3,523 tokens, 154,038 rows (115,338 train /
  22,554 validation / 16,146 test from the latest 15% of launches); 54
  boosting rounds; temperature 1.128; 8.9 MB. The data grew because short
  reconnects no longer end a token's window (section 6) and because of a
  second recording run. Test split, raw global model:

| Candle elapsed | Hit | Stated | 80% band | Band width | Error | Naive | Edge | Info gain (bits/row, vs same-f prior) |
|---|---|---|---|---|---|---|---|---|
| 0% | 85.3% | 85.2% | 91.9% | 19.6% | 7.42% | 7.80% | **+4.9%** | 0.615 |
| 20% | 89.4% | 89.8% | 92.3% | 16.0% | 5.57% | 5.76% | +3.3% | 0.548 |
| 40% | 92.3% | 92.5% | 92.9% | 12.3% | 4.38% | 4.52% | +3.0% | 0.458 |
| 60% | 95.7% | 94.6% | 94.9% | 8.7% | 2.90% | 2.84% | −2.2% | 0.355 |
| 80% | 97.8% | 96.7% | 95.9% | 5.3% | 1.83% | 1.83% | −0.4% | 0.284 |
| 95% | 99.3% | 98.6% | 98.0% | 2.1% | 0.59% | 0.57% | −3.0% | 0.181 |

- **Live forecaster replayed on 300 test tokens** (v1 + the final online
  model; forecasts locked at the open):

| | Candles | Hit | Stated | 80% band | Edge |
|---|---|---|---|---|---|
| Online only, all | 2214 | 79.3% | 78.8% | 92.4% | 0.0% |
| Online only, trading | 709 | 46.0% | 45.1% | 85.0% | 0.0% |
| Global + online, all | 2214 | 86.6% | 85.5% | 93.5% | **+7.0%** |
| Global + online, trading | 709 | 69.0% | 64.8% | 87.5% | **+7.3%** |

- **Reading the results:**
  - v0 → v1 on comparable measures: edge at the open +3.7% → +4.9%; info
    gain 0.34 → 0.61 bits; live blended edge +1.8% → +7.0%. Different test
    tokens, so treat the size of the gain as approximate, not the direction.
  - High hit rates come mostly from correctly calling "flat" on quiet tokens.
  - The tables above are the first v1 report. Section 8.4 fixed the three
    weaknesses they showed (over-coverage, late-candle median, blend
    underconfidence) without retraining; the installed report is the updated one.
  - v0 was replaced with `--force` without the keep-better comparison, because
    v1 changes σ (volatility from traded candles only, launch prior), which
    shifts the features v0 was trained on.
- **Earlier experiment notes:**
  - The "active candles" subset was replaced by "trading" (the previous candle
    traded), because conditioning on the outcome biased hit rates against flat
    calls.
  - Keep-better install: a 3-round model was correctly rejected (log loss 1.90
    vs 1.71).

### 8.2.1 v2 (installed 2026-10-09)

Trained on every recording so far: 5,790 launches and 251,220 rows from four
recorder directories (`tartar train --raw a,b,c,d`): this session's recorder
14:06–21:50 UTC, the Jev session's fast loop 23:44–23:50, and the
slot-annotated runs 00:01–00:48. 55 rounds, temperature 1.116.

v1 and v2 compared on the same v2 test launches (the latest 15%, all recorded
after v1's training data):

| On v2's test launches | v1 | v2 |
|---|---|---|
| Test log loss | 0.4891 | **0.4758** |
| Information gain at the open (bits) | 0.578 | **0.609** |
| Hit / stated at the open | 86.0% / 87.6% | 86.2% / 86.8% |
| Live replay, trading candles, hit / stated | 66.6% / 67.5% | 66.9% / 66.3% |
| Error edge at the open | **+5.2%** | +3.9% |
| Live replay error edge, all / trading | **+5.6% / +5.9%** | +4.0% / +4.2% |

Installed by the keep-better rule (test log loss). v2 is the better
probabilistic forecaster and is better calibrated; v1's point forecast was
~1.5 points closer on these launches. **This is not the median shrink**
(checked 2026-10-09): giving v2 v1's 0.8 shrink at the open lowers its test
edge (3.9% → 3.7%). The two models simply differ on these launches. v2's test
set is later and harder than v1's: v2's own live edge is +4.0%, against +7.5%
for v1 on v1's test set.

**Median shrink study (2026-10-09, scripts in the predictor session's
scratchpad):**
- Fitted on half the validation tokens and scored on the other half, no
  method beat "no shrink": per-fraction grid, one global factor, linear in f
  and bootstrap-bagged all lost 0.04–0.7%, on both v1's and v2's data.
- On test, shrinking toward the current price late in the candle helps in
  both datasets: f = 0.6 from about −2% to ≈0, f = 0.8 from −0.5…−1.5% to ≈0.
  Validation found this for v1's data but not for v2's.
- The effect is real but small, and too noisy for validation alone to fit.
- **Resolved (2026-10-09):** `train_global` now fits s(f) on out-of-fold
  medians over the training split plus validation (`oof_medians`, 3
  token-wise folds), about 6× the rows. On test, total point error compared
  with validation-only fitting:
  - v1 data: 750.39 vs 750.53
  - v2 data: 1218.82 vs 1221.66

  It keeps s = 1 early in the candle and shrinks late. The four installed
  models were refitted this way without retraining. 1m: [1, 1, 0.9, 0.7,
  0.6, 0]; the test edge at 60% elapsed went from −2.0% to −1.05%, and at
  80% from −1.5% to −0.4%.

### 8.2.2 Models for 15s, 30s and 5m candles (installed 2026-10-09)

Same data, recorder directories and pipeline as v2 (`tartar train -t 15s|30s|5m`).
Until now only 1-minute candles had a global model; every other timeframe ran the
online model alone, whose point forecast is no better than "close = last price".
Live replay on 300 held-out test tokens, forecasts locked at the open (reports in
`tartar/models/trades-*.report.json`):

| Candle | Launches / rows | Online only: edge | Global + online: edge, all / trading | Trading candles: hit vs stated | Raw model at the open: hit vs stated |
|---|---|---|---|---|---|
| 15 s | 6,189 / 552k | −0.8% | **+3.7% / +4.0%** | 59.2% vs 59.7% | 90.8% vs 91.0% |
| 30 s | 6,035 / 360k | −0.5% | **+4.2% / +4.5%** | 63.5% vs 63.7% | 88.6% vs 89.2% |
| 1 m (v2) | 5,790 / 251k | ≈0 | +4.0% / +4.2% | 66.9% vs 66.3% | 86.2% vs 86.8% |
| 5 m | 3,657 / 75k | 0.0% | **+12.0% / +12.1%** | 74.0% vs 72.9% | 72.9% vs 76.4% |

Edges are after the out-of-fold shrink refit (§8.2.1). That moved 30s from
+3.7%/+4.0% to +4.2%/+4.5%, moved 15s by −0.1 pt, and fixed a noisy 0.2
shrink at 20% elapsed for 5m: its test edge there went from +2.4% to +6.0%.
The 5m model has the least data. Its raw distribution is overconfident during
the candle (e.g. 80.6% hit vs 86.1% stated at f = 0.2). The live blend at the
open is calibrated, but nowcasts during a 5m candle lean confident until more
data exists. Retrain it first when data grows.

**Flat-candle priors by timeframe.** The online model's flat odds now start
from values measured on the training split for each candle length (interpolated
in log time, `trades_flat_priors`):

| Candle | P(flat after traded) | P(flat after flat) |
|---|---|---|
| 15s | 0.372 | 0.980 |
| 30s | 0.422 | 0.974 |
| 60s | 0.487 | 0.965 |
| 300s | 0.610 | 0.943 |

### 8.2.2b Hyperparameters (sweep 2026-10-09)

`handoff/experiments/predictor_sweep.py` on v2's data (6,107 tokens, 264k rows, 1-minute candles,
same 70 / 15 / 15% split), choosing on validation log loss:

| leaves / min rows per leaf | 100 | 400 | 1,500 | 4,000 | 10,000 |
|---|---|---|---|---|---|
| 15 | 0.5296 / 0.4609 | 0.5294 / 0.4603 | 0.5288 / 0.4589 | 0.5292 / 0.4599 | 0.5312 / 0.4599 |
| 31 | 0.5300 / 0.4609 | 0.5292 / 0.4596 | 0.5290 / **0.4583** | **0.5286** / 0.4587 | 0.5317 / 0.4607 |
| 63 (default) | 0.5324 / 0.4629 | | | | |

(validation / test log loss). Fewer leaves and many more rows per leaf than the default are ~1%
better on test, flat between 1,500 and 4,000 rows. `tartar train --num-leaves 31 --min-leaf 2000`
for v3 (scale min rows with the data: these are ~0.6–1.5% of rows); defaults unchanged until a
model trained this way wins the keep-better check.

### 8.2.2c v3: more data, smaller trees (installed 2026-10-09, all four candle lengths)

`tartar train --raw <every curve recording> -t TF --num-leaves 31 --min-leaf 2000` on
`handoff/data/raw`, `raw-slots`, `raw-slots-processed`, `raw-pumpswap` and `raw-eager` (the new
recording with median 100% capture): 8,560 launches / 382k rows at 1m (v2: 5,790 / 251k), 9,184
at 15s, 8,927 at 30s and 4,683 at 5m. Each candidate was scored against the installed v2-era
model on **the candidate's own test launches** (the latest 15%, mostly `raw-eager`) with
`handoff/experiments/predictor_compare.py`; results in `handoff/experiments/predictor-v3/`.

| Candle | Test log loss, v2 → v3 | Edge at the open | Live replay edge, all / trading | Trading candles: hit vs stated, v3 (v2) |
|---|---|---|---|---|
| 15 s | 0.2899 → **0.2835** | +2.5% → **+3.7%** | +1.6 / +1.8% → **+1.8 / +1.9%** | 62.3% vs 60.1% (61.4% vs 60.1%) |
| 30 s | 0.3474 → **0.3386** | +4.4% → **+5.6%** | +4.5 / +4.8% → +4.4 / +4.7% | 65.9% vs 63.6% (64.4% vs 64.1%) |
| 1 m | 0.4253 → **0.4129** | +6.7% → **+9.1%** | +4.7 / +5.0% → **+6.2 / +6.5%** | 65.5% vs 66.0% (64.6% vs 65.6%) |
| 5 m | 1.1895 → **1.1418** | +5.1% → **+6.9%** | +4.6 / +4.6% → **+6.5 / +6.5%** | 63.3% vs 68.0% (62.1% vs 70.3%) |

All four installed by the keep-better rule (test log loss). The 1m point edge, v2's weak spot
(8.2.1), is back above v1's. 30s gains in log loss and at the open but not in the live replay.
The model files now record `num_leaves` / `min_data_in_leaf` in their metadata.

**Open: the 5m model is overconfident on these newer launches.** At the open it states 70.6%
and hits 60.9% (v2: 73.4% vs 59.9%), and the live blend's trading candles state 68.0% vs
63.3%. 15s and 30s lean the other way: ~2 points underconfident on trading candles.

Diagnosis (`v3`, 2026-10-09, corrected the same morning). The 5m model, scored per recording at
the open (`raw-clever` is new data it never saw):

| Recording | 5m tokens | "No trade" at the open | Hit vs stated | Edge |
|---|---|---|---|---|
| `raw` (old recorder, 10-08 14:06–10-09 03:39) | 3,325 | 78% | 87.4% vs 82.1% | +22.5% |
| `raw-slots` (00:01–00:42) | 332 | 37% | 68.4% vs 70.6% | +15.4% |
| `raw-pumpswap` (01:30–01:50) | 95 | 43% | 71.3% vs 72.6% | +23.6% |
| `raw-eager` (04:06–06:00) | 931 | 36% | 61.5% vs 70.4% | +9.1% |
| `raw-clever` (06:23–07:59, unseen) | 731 | 36% | 65.0% vs 69.8% | +15.1% |

The old recorder's rows are ~75% of 5m training rows and have a very different outcome mix: it
followed dead tokens for longer (median window 20 min vs ~11; 20-min idle cut plus many
reconnect cuts), so a 5m candle at its open was "no trade" 78% of the time vs 36–43% in every
later recording. Validation is ~95% later recordings, so the temperature was fitted on the right
kind of rows; it is the training mix that differs. Within the later recordings calibration also
drifts by period (−2 points at 00–02 UTC, −5 to −9 points at 04–08 UTC). At 1m the old and new
recordings agree (76% vs 77% empty candles) and the model is calibrated on the new launches
(87.1% vs 87.9%). Fitting early stopping and the temperature only on later-recording validation
rows changed nothing (test log loss 1.1418 → 1.1410). **Fix:** retrain once `raw-clever` has a
few hours (it records the same way as `raw-eager`), so most 5m training rows are new-style; try
down-weighting or dropping the old `raw` rows at 5m, and check calibration first.

**Preview (08:30 UTC, nothing installed):** 5m with `raw-clever` 06–07 added (5,414 tokens; the
time split makes training 91% old-recorder rows, validation and test 0%), old rows weighted in
training only:

| Old-recorder training rows | Validation log loss | Test log loss | Hit vs stated at open | Live replay edge |
|---|---|---|---|---|
| (installed v3) | | 1.1081 | 64.6% vs 69.9% | +12.7% |
| × 1 | 1.0879 | 1.0729 | 67.4% vs 69.1% | +13.9% |
| × 0.25 | 1.0711 | **1.0578** | 69.6% vs 70.3% | **+14.8%** |
| × 0 | **1.0674** | 1.0672 | 74.7% vs 72.8% | +9.2% |

Validation picks × 0 by a hair, test favours × 0.25, and × 0 loses a lot of point accuracy
(it trains on ~9% of the rows). Choose the weight on validation from a grid (1, 0.5, 0.25, 0.1, 0)
once `raw-clever` has more hours; script `handoff/experiments/predictor_old_weight.py`.

The same at **1m** (10,184 tokens; training 68% old rows): validation log loss × 1 0.4144,
× 0.25 0.4140, × 0 0.4197; test 0.5090 / 0.5119 / 0.5220 (installed v3: 0.5136). The old rows
help at 1m, and down-weighting is a 5m fix. **30s** agrees (validation 0.3540 / 0.3545 / 0.3611,
test 0.4219 / 0.4233 / 0.4318; installed 0.4255), and so does **15s** (validation 0.3240 / 0.3243 /
0.3271, test 0.3242 / 0.3251 / 0.3290; installed 0.3276). Plan for v3.1: 15s/30s/1m on every recording
at full weight; 5m with the old-row weight chosen on validation. Also on these `raw-clever` test launches, the 1m
live blend is **under**confident on trading candles: 69% hit vs 64% stated (all variants). Check
the blend's global prior (0.95, §8.4) on new-style data when v3.1 is trained.

### 8.2.2d v3.1: with `raw-clever` (installed 2026-10-09 ~13:35 UTC, all four candle lengths)

Every curve recording including `raw-clever` hours 06–11 (14,796 launches at 1m, 15,485 at 15s,
15,205 at 30s, 7,670 at 5m), 31 leaves / 2,000 rows per leaf. As planned in 8.2.2c: 15s, 30s and
1m at full weight (`tartar train`); 5m with the old recorder's training rows weighted on
validation (`predictor_old_weight.py 300 OUT 1,0.5,0.25,0.1,0`: validation log loss 0.9197 /
0.9054 / 0.8989 / 0.8926 / **0.8822**, so weight 0; test 0.9909 / 0.9792 / 0.9864 / 0.9922 /
0.9953). Each scored against installed v3 on its own test launches (the latest 15%, all
`raw-clever`, ~10:00–12:00 UTC): `handoff/experiments/predictor-v3/v31-*`.

| Candle | Test log loss, v3 → v3.1 | Edge at the open | Live replay edge, all / trading | Trading candles: hit vs stated, v3.1 (v3) |
|---|---|---|---|---|
| 15 s | 0.2815 → **0.2767** | +3.6% → **+3.8%** | +1.9 / +2.0% → **+2.2 / +2.4%** | 62.1% vs 60.2% (59.9% vs 58.8%) |
| 30 s | 0.3618 → **0.3539** | +6.8% → **+7.4%** | +5.8 / +6.1% → +5.7 / +6.0% | 63.1% vs 61.6% (61.4% vs 60.3%) |
| 1 m | 0.4339 → **0.4282** | +9.0% → **+10.3%** | +6.0 / +6.1% → **+8.0 / +8.2%** | 64.6% vs 64.3% (62.8% vs 63.2%) |
| 5 m | 1.0894 → **0.9953** | +13.0% → **+15.0%** | +8.1 / +8.2% → **+11.9 / +12.2%** | 73.8% vs 73.4% (68.1% vs 69.4%) |

All four installed (keep-better on test log loss). 5m at the open is still overconfident (hits
69.7%, states 75.5%; v3: 60.1% vs 72.4%), half the gap. Its trading candles are calibrated.
The 5m model was trained by the study script, not `tartar train` (which has no row weights):
its metadata says so (`old_recorder_weight: 0`, `note`).

### 8.2.2e v3.2: with every recording to hour 19 (trained 2026-10-09 ~20:15-22:30 UTC; **installed 23:15 UTC** at the user's go)

v3.1's recipe (8.2.2d) on every curve recording, adding the hours v3.1 never saw: `raw-clever`
12-15, `raw-clever2`, `raw-v3` and `raw-pred` (to 2026-10-09 19:59 UTC; one directory per
recorder, duplicate launches keep the longest copy). 31 leaves / 2,000 rows per leaf; the old
recorder's (`raw`) training rows weighted by w, w chosen on validation log loss (validation and
test hold no old rows). Script `handoff/experiments/predictor_v32.py`; results and the chosen
candidates (gzipped) in `handoff/experiments/predictor-v32/`. Test = the latest 15% of launches
(from ~17:00 UTC, 4,200-4,300 launches), which neither model trained on.

| Candle | Launches / rows | w (validation LL by w) | Test log loss, v3.1 → v3.2 | Edge at the open | Live replay edge, all / trading | Trading candles: hit vs stated, v3.2 (v3.1) |
|---|---|---|---|---|---|---|
| 15 s | 28,795 / 2.93M | 1 (only w tried) | 0.3214 → **0.3183** | +1.9% → **+2.1%** | +1.3 / +1.4% → **+1.5 / +1.7%** | 59.3% vs 60.9% (58.8% vs 59.8%) |
| 30 s | 28,500 / 1.94M | 1 (only w tried) | 0.3912 → **0.3870** | +3.1% → **+3.5%** | +3.4 / +3.7% → +3.5 / +3.7% | 62.3% vs 63.6% (61.2% vs 62.7%) |
| 1 m | 28,022 / 1.46M | **1** (0.4147 / 0.4162 / 0.4185 at 1 / 0.25 / 0) | 0.4712 → **0.4641** | +4.0% → +4.0% | +3.1 / +3.3% → **+3.7 / +4.0%** | 64.4% vs 66.5% (64.6% vs 65.4%) |
| 5 m | 13,833 / 258k | **0** (0.9728 / 0.9681 / 0.9629 / 0.9605 / 0.9589 at 1 / 0.5 / 0.25 / 0.1 / 0) | 1.1184 → **1.0779** | +6.1% → **+7.3%** | +7.4 / +7.7% → **+9.3 / +9.8%** | 68.3% vs 71.2% (68.5% vs 70.3%) |

Every length beats v3.1 on test log loss, so all four pass the keep-better rule. **Not installed:**
the predictor-strategy forward test's `evaluate` asserts the SHA-256 of `trades-60s`,
`trades-300s` and `rug-20s` (≤ 2026-10-12). To install after it is scored: `gunzip -c
handoff/experiments/predictor-v32/candidates/trades-<s>s.txt.gz > tartar/models/trades-<s>s.txt`
and copy the `.json` beside it (`.report.json` stays v3.1's; these were trained by the study
script, which writes no report). 15s and 30s were trained at w = 1 only (v3.1's choice at those
lengths; each fit there takes ~25-40 min and ~10 GB).

**Calibration flipped sign with the hour.** On hours 12-16 the blends were underconfident on
trading candles (8.4.1); on these test hours (17-19) the 1m and 5m blends are **over**confident
by 2-3 points, for v3.1 and v3.2 alike. It is the market-wide drift 8.4.1 describes, not a model
fault: no fixed correction would hold across both periods. At 5m the open forecast is now
calibrated (72.5% hit vs 72.7% stated; v3.1 on these launches 71.6% vs 71.4%).

### 8.2.3 A model for graduated tokens on PumpSwap (code 2026-10-09; trained once data allows)

`tartar watch` follows a token through graduation onto its PumpSwap pool, but until now it then
dropped the global model (trained on bonding curves) and ran the online model alone. Now:

- `tartar train --raw DIRS --pumpswap` trains a model for domain `pumpswap` (`pumpswap-60s.txt`
  etc.) from recordings made with `--pumpswap-hours` (`load_pumpswap_tokens`).
- At graduation the agent loads that model if it exists (`CandleAgent(after_graduation=...)`,
  wired in `watch`) and restarts its forecaster, as it already did: candles so far become history
  without trade detail, the creator counts as unknown, and the wallet tracker starts from
  scratch. Without the model, behaviour is unchanged.
- Training rows mimic exactly that restart. Each graduated token is its curve candles before
  the graduation candle (when its launch was recorded up to graduation) as history, then candles
  from one candle book over curve trades and pool swaps, as the agent's book (which outlives the
  restart) builds them. Only swaps reach the wallet tracker. Rows predict only candles that start
  after graduation. The time split uses graduation time. A pool's window ends when the recorder
  stops watching it (30 idle minutes, or `--pumpswap-hours`) or the recording is cut.
- `swap_tick` turns a recorded `swap` event into exactly the tick `PumpSwapFeed` yields live
  (tested on a mainnet transaction), and a parity test checks that the rows equal the features
  the agent computes after its restart.
- `pumpswap` counts as a trade domain wherever `trades` did (`TRADE_DOMAINS`): nowcast
  fractions and the volatility prior (still the curve's, refined online). **Flat priors are
  its own since 2026-10-09** (`_PUMPSWAP_FLAT_PRIORS`), measured on the training split of
  170–191 graduated SOL pools (`raw-pumpswap`, `raw-eager`, `raw-clever`), candles after
  graduation only:

  | Candle | P(flat after traded), curve → pool | P(flat after flat), curve → pool |
  |---|---|---|
  | 15s | 0.372 → 0.148 | 0.980 → 0.896 |
  | 30s | 0.422 → 0.144 | 0.974 → 0.875 |
  | 60s | 0.487 → 0.132 | 0.965 → 0.855 |
  | 300s | 0.610 → 0.147 | 0.943 → 0.753 |

  They apply when the forecaster restarts at graduation (it does whenever a model was on before
  or a PumpSwap model is found).

**First models (2026-10-09 15:00–17:20 UTC, handoff session): 15s, 30s and 1m installed, 5m not.**
`handoff/experiments/pumpswap_model.py handoff/data/raw-pumpswap,raw-eager,raw-clever,raw-v3 OUT`
(the raw logs parsed once for every candle length; `tartar train --pumpswap`'s dataset and split,
pools 70 / 15 / 15% by graduation time; num_leaves {15, 31, 63} × min_data_in_leaf {100, 400,
1500} chosen on validation log loss; then `evaluate`). **The install rule was written in the
script before any result was read:** on the test pools' live replay, global + online must beat
online-only on edge (all and trading candles), keep the trading-candle calibration gap within
2 points of online-only's, and carry positive information at the candle open. Outputs:
`handoff/experiments/pumpswap-model/`.

| Candle | Pools / rows | Chosen | Test pools | Online only, trading: hit vs stated, edge | Global + online, trading: hit vs stated, edge | All candles: edge, online → blend | Verdict |
|---|---|---|---|---|---|---|---|
| 15 s | 458 / 592k ¹ | 63 leaves, 1,500 | 68 (4,259) | 53.5% vs **48.7%**, −0.6% | **62.4% vs 62.6%**, **+2.1%** | −0.6% → **+1.9%** | **installed** (`pumpswap-15s`) |
| 30 s | 350 / 247k | 31 leaves, 400 | 52 (1,839 trading candles) | 64.5% vs **50.4%**, +0.3% | **73.8% vs 73.5%**, **+1.7%** | +0.3% → **+1.6%** | **installed** (`pumpswap-30s`) |
| 1 m | 348 / 136k | 15 leaves, 100 | 52 (993 trading candles) | 62.8% vs **49.2%**, −0.7% | **72.0% vs 72.0%**, **+0.9%** | −0.7% → **+0.8%** | **installed** (`pumpswap-60s`) |
| 5 m | 323 / 34k | 15 leaves, 400 | 48 (266) | 49.6% vs 45.4%, −0.5% | 62.4% vs 63.3%, −0.9% | −0.4% → −0.9% | not installed (edge) |

¹ 15s ran separately at 16:10 (the four-length run was OOM-killed building it), on the data then
on `main`: `raw-clever` through hour 15 and `raw-v3` through hour 14, so more pools and a later
test split than the other rows.

**5m retry (2026-10-10 00:40 UTC, retrain thread): installed** (`pumpswap-300s`). Same script and
install rule, `-t 5m`, on `raw-pumpswap`, `raw-eager`, `raw-clever`, `raw-clever2`, `raw-v3` and the
recorder Action's run 37986175087 (hours 20–23, `fetch_gha_raw.py`): **689 pools / 69k rows** (was
323 / 34k). Chosen on validation: 63 leaves, 1,500 rows per leaf (validation 1.1574). On 103 test
pools' live replay: online only, trading candles 51.5% hit vs 45.6% stated, edge −0.2%; **global +
online 65.9% vs 64.4%, edge +2.1%** (all candles 69.0% vs 67.6%, +2.1%). Every check passes (edge
all / trading, calibration, information at the open). Log and summary:
`handoff/experiments/pumpswap-model/run-5m-retry.log`, `summary-5m-retry.json`.

* **What 1m buys is honest confidence, not sharper prices.** After graduation the online model
  alone is badly *under*confident (on trading candles it states 49% and is right 63% of the time;
  why was not studied). The blend states what it hits. Its point
  forecast is barely better than "close = last price" (test edge +0.5% at the open, 0 near the
  close). At the open: hit 81.2% vs stated 80.1%, 1.14 bits per row over the base rate, band
  87.3% vs 85.6% stated. 30s is the same picture with a little more point edge (at the open:
  hit 83.8% vs 82.6% stated, edge +1.7%, 1.17 bits per row), and so is 15s (hit 79.0% vs 78.3%,
  edge +2.0%, 0.96 bits per row).
* 5m improves calibration too but loses point accuracy, so the rule keeps it out. With 48 test
  pools and 404 candles both numbers are noisy; retry with more pools.
* Hyperparameters barely matter here (1m validation 0.7592–0.7645 over the grid); small trees win
  on this little data. Top 1m features: `log_trades`, `log_price`, `p_idle`, `range`,
  `curve_progress`.
* The sweep trains with `shrink_folds=0` (the out-of-fold median shrink moves only the point
  forecast, not the log loss); the installed model has the default 3-fold shrink.

### 8.3 Blending

The global and online distributions are mixed with weight
σ(logit(p) + D), where D is the discounted (0.98) sum of per-candle log-score
differences, clipped to ±5. On simulated data the weight converges to ~0.96 for
the global model. The prior p was 0.8 and is **0.95** since 8.4.

### 8.4 Calibration and point-forecast fixes (open problems 3–5, queue item 6)

Diagnosed on the v1 validation and test splits (same model; no retraining).
Every choice was made on **validation** and checked once on test:

- **Band over-coverage is not miscalibration.**
  - At every f, on validation and test, the probability the model itself
    puts inside its band matches the realized coverage within ~1 point (test
    at the open: 91.3% stated, 91.9% realized).
  - On candles that move, the central 80% of the continuous part covers
    78–82% (its PIT is close to uniform).
  - The excess over 80% is the "no further trade" point mass: P(still) is
    0.79–0.94 on average, and when it exceeds 80% the band is the current
    price itself. No honest interval that contains the most likely outcome
    can cover less.
  - Fix: report what the band states next to what it covers. This is
    `Forecast.band_mass`, `Tally.band_stated`, `band_stated` in the train
    report and replay, a "band states" column in `tartar train`, "(stated …)"
    in plain output, and `band.stated` in JSON.
- **The late-candle median is shrunk toward the current price.**
  - The median left the current price on only 2–7% of late rows, mostly
    downward. It beat "price now" on validation at f = 0.6 and 0.8, lost on
    test, and lost on both at 0.95.
  - `fit_median_shrink` (train.py) chooses, per f on validation, how much of
    the median's move to keep. For v1: 0.8, 0.8, 1.0, 0.7, 0.4, 0.0 at
    f = 0, 0.2, 0.4, 0.6, 0.8, 0.95.
  - It is stored as `meta["median_shrink"]`, applied in `evaluate_rows` and in
    the live forecaster (interpolated in elapsed time, scaled by the global
    weight), and refitted at every training. The installed v1 metadata was
    updated in place.
  - Test edge by f, before → after: 0%: +4.9 → +4.7; 20%: +3.3 → +3.8;
    40%: +3.0 → +3.0; 60%: −2.2 → −0.4; 80%: −0.4 → +0.7; 95%: −3.0 → 0.0.
- **The blend's underconfidence came from the online component.**
  - The raw global model is calibrated on trading candles (test: 67.8% hit
    vs 68.3% stated).
  - Mixing in the online model, which is honest but adds no point accuracy,
    diluted it. Replays on 300 validation tokens, trading candles:

| Global prior | Hit / stated | Direction log loss (bits) |
|---|---|---|
| 0.80 | 70.2% / 66.9% | 0.3129 |
| 0.90 | 70.1% / 68.8% | 0.3098 |
| **0.95** | 69.5% / 69.8% | 0.3086 |
| 0.98 | 69.5% / 70.5% | 0.3081 |

  0.98 overshoots calibration for a 0.0005-bit gain, so 0.95 was chosen.
- **Live replay on the 300 test tokens, after all three changes** (before →
  after):
  - all candles: hit 86.6% vs stated 85.5% → 86.6% vs 86.4%; edge +7.0% →
    **+7.5%**
  - trading candles: hit 69.0% vs stated 64.8% → 69.0% vs 67.8%; edge +7.3%
    → **+7.8%**
  - live band (all candles): covers 93.3% and states 91.9%

### 8.4.1 The curve blends' trading-candle underconfidence (2026-10-09, handoff session)

STATUS item (b): on hours v3.1 never saw, every curve blend states less than it hits on trading
candles. `handoff/experiments/blend_calibration.py` replays the installed `trades-*` models on
`raw-clever` hours 12–15 plus `raw-v3` hour 16 (launches after v3.1's data; `train.replay`'s
masking), recording each open forecast's parts. `blend_calibration_sim.py` then re-simulates the
direction calibrator offline (exact: it matches the replay to 1e-15), so variants are compared on
the same forecasts.

**Where the gap is (1m, 28,576 trading candles, hit 68.1% vs stated 66.7%):**
* Not the flat-vs-move call: blended P(flat) 44.2% vs 43.3% observed, calibrated bin by bin.
* The up/down call: down calls hit 61.2% vs 58.5% stated, up calls 47.0% vs 49.8%. P(up | move)
  is too high in its middle range (0.45–0.60 stated → 3–6 points fewer ups).
* It moves with the hour: the gap is +3.5 / +0.7 / −0.1 / +2.1 / +1.5 points in hours 12–16 and
  follows how much more often tokens fell than forecast that hour (q_up bias +2.7 / +0.7 / 0.0 /
  +2.6 / +0.8). A single-token watcher can't see that market-wide drift.
* The global model's own P(up | move) is calibrated on average (0.345 vs 0.343). The per-token
  `DirectionCalibrator` moved it to 0.356: it can only temper (slope ≤ 1) and is fitted on one
  token's few moves, so on odds that are already calibrated across tokens it can only lower
  confidence on average.

**Variants** (gap = hit − stated on trading candles; selection hours 12–13, confirmation 14–16):

| Candle | Current: gap 12–13 / 14–16, log loss 14–16 | Calibrator on the online share only (`× (1 − w)`) | Calibrator may also sharpen (slope ≤ 1.5) |
|---|---|---|---|
| 15 s | +1.85 / +1.17, 0.7677 | **+1.29 / +0.41**, 0.7686 | +1.59 / +0.98, 0.7681 |
| 30 s | +1.79 / +0.34, 0.7409 | **+1.31 / −0.38**, 0.7415 | +1.62 / +0.21, 0.7412 |
| 1 m | +1.87 / +1.12, 0.6927 | **+1.47 / +0.69**, 0.6927 | +1.75 / +1.05, 0.6928 |
| 5 m | +2.91 / +3.01, 0.6470 | **+2.82 / +2.87**, 0.6468 | +2.88 / +2.96, 0.6469 |

**Installed:** on curves (`domain == "trades"`) the calibrator now corrects only the online
model's share of the blend (`weight × (1 − w)`; `Forecaster._predict`). It narrows the gap in
both splits at every length. Log loss is unchanged on the selection hours (±0.0003) and up to
0.0009 worse on the confirmation hours at 15s/30s, so the per-token tempering carried a little
information there. This is an honesty fix, not an accuracy gain. Hit rates, medians and bands
don't change (the calibrator touches only P(up | move)). Online-only forecasts and the
`pumpswap` domain are unchanged; its blends were already calibrated (8.2.3).

**What is left:** ~0.4–1.5 points at 15s–1m that follow the hour, and ~3 points at 5m. There the
global model's own odds are off on these hours: direction right 79.0% vs 77.4% stated; its
P(up | move) above 0.7 hit 96.6% vs 86.0% stated and 0.3–0.4 hit 28% vs 35%, while below 0.1 it
is over-sharp (12% vs 7%); flat mass is compressed toward the middle (0.3–0.9 stated → 4–6 points
more flats). That is for the next retrain on newer recordings (`raw-clever` 12–16, `raw-clever2`,
`raw-v3`), not for a correction fitted on six hours. Train it any time, but don't install over
`trades-60s`, `trades-300s` or `rug-20s` before the predictor-strategy forward test is evaluated
(≤ 2026-10-12): its `evaluate` asserts their SHA-256.

## 9. Scam filtering

- **Risk levels:** `ok`, `caution`, `danger`, `scam` (or `unknown`), each with
  reasons. Shown in the dashboard header, as plain lines, and as JSON `risk`
  events.
- **Behaviour** (`WalletTracker`, from trades):
  - creator sold ≥50% / ≥90% of their tokens (both caution since 2026-10-09; ≥90% was danger)
  - collapse ≥90% from the peak (scam)
  - top-10 wallets ≥50% of trader-held tokens (with 15+ holders; caution, ≥70% was danger)
  - creator holds ≥20% / ≥40%
  - ≥25% / ≥50% of bought tokens sniped in the first 5s (caution; ≥50% was danger)
  - ≥50% quick round trips (wash trading)
  - ≥8 trades per wallet
  - non-standard curve
- **Mint** (RPC): mint authority, freeze authority, permanent delegate,
  non-transferable, transfer hook, pausable, frozen by default, transfer fee.
- **Reputation:** RugCheck rugged flag, its danger/warn risks ("Mutable
  metadata" ignored), insider networks, top-10 holders excluding known
  AMM/locker/market accounts. From recorded data: the creator's other rugs
  (creator sold ≥50% of SOL in and price ≥80% down from peak), ≥4 other
  launches in a day, ≥2 other launches, and copycat name/metadata. The judged
  token is excluded from its own history.
- **`--next-launch` screening:** observe each launch for 20s; require 3+ buyers
  besides the creator; reject danger/scam, and the three flags above at their
  former danger thresholds (`Flag.bad_trade`, `ScamReport.avoid`): they mark
  worse trades (profitability §3.5), so the screen's choices are unchanged.
  Earlier note: in a live run it rejected 71
  launches before passing one (mostly zero buyers; several bundled rugs). The
  passed token's creator then dumped within 30s and the badge flipped to DANGER.
- **Validated 2026-10-09** (problem 6): the old level barely ranked later
  collapses (AUC 0.57–0.59). `dev_dumped`, `sniped` and `concentrated` go with
  *fewer* collapses (lift 0.3–0.6), so alone they are now a caution; the level's
  test AUC rose to 0.735 (9.1 below). The behavioural signals are also model
  inputs.

### 9.1 P(rug) (shipped 2026-10-09; `tartar/rug.py`)

A LightGBM classifier on the 18 numbers of a launch's state 20 s after launch
(`decide.NUMERIC`), predicting a **rug**: 30 min after the screen the price is
≥80% below the screen's and the token has not graduated. States come from a
fast-loop replay that screens every launch and buys none (causal creator
history), outcomes from the full raw stream; a launch is left out only when the
recorder was down in between. Split by time 70 / 15 / 15; validation drives
early stopping and a Platt recalibration (a 0.86, b −0.02).

`tartar train --raw DIRS --rug` → `tartar/models/rug-20s.{txt,json,report.json}`
(keep-better on test log loss). `watch --next-launch` prints P(rug) on every
verdict line and the watched token's risk line / dashboard header shows it
beside the level ("P(rug) 12% in 30 min (judged at +20 s)"). It is shown, not
used to skip.

Trained on every curve recording (raw, raw-slots, raw-slots-processed,
raw-pumpswap, raw-eager): 5,267 launches with a recorded outcome, test = the
latest 791 (rug rate 9.5%):

| | test |
|---|---|
| AUC | **0.913** (risk level: 0.735 now, 0.585 with the old weights) |
| Log loss | 0.199 (uncalibrated 0.202; base rate 0.317) |
| Brier | 0.063 |

| P(rug) band | share of test launches | observed rug | observed moon (2× or graduated) |
|---|---|---|---|
| < 5% | 72.6% | 1.0% | 0.9% |
| 5–15% | 5.8% | 10.9% | 4.3% |
| 15–30% | 5.6% | 27.3% | 6.8% |
| 30–50% | 9.2% | 34.2% | 8.2% |
| ≥ 50% | 6.8% | 50.0% | 13.0% |

By decile it is calibrated except the top one (56% predicted, 44% observed).
Top features: `nonstandard_curve` 45%, `raised_sol` 17%, then
`trades_per_wallet`, `sniper_share`, `holders`, `creator_launches` (4–5% each).
Launches that pass the `--next-launch` screen are rare (2.9% of test launches)
and rug often (30%, n = 23); P(rug) still ranks them (AUC 0.96, few rows).
**Forward test and retrain (13:50 UTC).** On the 7,075 `raw-clever` launches (06:23–12:59 UTC,
all after its training data) the shipped model kept AUC **0.924** (risk level 0.688), log loss
0.207 vs 0.354 for a constant, but it under-predicted the middle (5–15% band: 20.7% observed;
15–30%: 30.7%). Retrained with `raw-clever` included (12,342 launches; `tartar train --raw
<all six dirs> --rug`), it beat the shipped model on the latest 1,852 launches (log loss 0.1787 vs
0.1879) and was installed: AUC **0.935** (risk level 0.669), calibrated by decile (12% → 12%,
36% → 35%, 58% → 54%). Top features: `nonstandard_curve` 57%, `raised_sol` 12%,
`trades_per_wallet` 9%.

**Reading:** high P(rug) also means more moons. It measures how likely a
launch is to *move*, then collapse; it is a warning, not a trading signal (the
fast-loop studies already close launch buying, profitability §3.9, §3.14).

## 10. Key decisions and why

- **Calibration over conviction.** Direction confidence is recalibrated, bands
  use ACI, and the report always shows stated vs realized. The user should be
  able to trust the confidence number.
- **One distribution, not separate heads.** A single multiclass model with a
  point mass for "no move" plus bins gives a consistent median, band and
  direction from one object, and handles dead tokens naturally.
- **Same code offline and live** (`FeatureEngine`, `WalletTracker`,
  `CandleBook`), with a parity test, to prevent train/serve skew.
- **Late-join and masking in training** so the model works on tokens joined
  after launch.
- **Time split by launch**, and replaying the actual live forecaster, so
  reported numbers are what a user would see.
- **Chain over PumpPortal:** PumpPortal's trade stream became paid; the chain is
  free and carries the creator on every trade.
- **No automatic endpoint rotation:** publicnode's partial stream would silently
  corrupt candles.
- **No cutting data at reserve discontinuities:** with ~35–40% of trades missing
  on the public RPC, every busy token would be cut. Capture is reported
  instead; training and live see the same lossy stream, so they stay consistent.
- **Unobserved candles are never scored:** feed outages and graduation used to
  produce fake flat candles scored as hits.
- **Models trained on simulated data are never loaded for real tokens**
  (`meta.simulated`).
- **LightGBM text models with atomic saves and a size check**, and keep-better
  installs.
- **σ is the scale of a candle that trades.** Whether anything trades is
  modelled separately (the point mass / flat odds), so flat candles must not
  pull σ toward zero. Both the global model's z-bins and the online model use
  this σ.
- **Priors come from the training split of real data, never from the test
  split:** σ ≈ 0.25 per traded candle for pump.fun trade streams; flat odds
  0.5 after a traded candle, 0.95 after a flat one.
- **The direction calibrator and the reliability slope only temper, never
  amplify.** Early in a token's life a few lucky outcomes looked like skill and
  produced "UP 80%" calls that hit ~55%. The price is mild underconfidence
  where a real signal exists (open problem 5).
- **Short reconnects keep a token's data.** With the server dropping the
  connection every ~30 s, cutting at every reconnect left almost nothing;
  gaps up to 10 s lose fewer trades than the stream already drops.

## 11. Accuracy review (multi-agent) and what was fixed

A five-lens review ran (leakage, math, live pipeline, training/eval, online
model), with every finding adversarially verified. Fixed in commit `9d8ea8a`,
with regression tests in `tests/test_review_fixes.py`:

- Unclean recorder restarts are cut at the last event before each reconnect.
- Launches without `track` are skipped.
- The stream no longer rotates to publicnode.
- Feed outages produce unobserved candles and a mid-life resync.
- Graduation ends the chain feed; graduated tokens are routed to
  DexScreener/GeckoTerminal.
- GeckoTerminal grace is 75s.
- The quantile search is bracketed around x0 (big in-candle moves no longer
  clamp the band).
- No time left means no move; the global no-move probability is extrapolated
  past f = 0.95.
- The replay feeds wallets in live order.
- Atomic model saves; corrupt models are skipped.
- Info gain uses a per-fraction baseline.
- One `model_dir()` rule.
- The OHLCV model drops high/low features.

Rejected by verifiers: "DirectionCalibrator shrinks calibrated confident odds"
(effect ≤1 point, conservative), and "mid-life GeckoTerminal history creates fake
zero-trade candles".

The **online-model lens** could not run then (usage limit). It was re-run
separately (section 11.1).

### 11.1 Online-model review

A second review targeted the per-token online model, which is the whole
predictor for any source or timeframe without a trained global model, and part
of the blend otherwise. All **7 findings were confirmed** by adversarial
verifiers on real recorded data and synthetic series (0 rejected). All are fixed,
with regression tests in `tests/test_review_fixes.py` and `tests/test_model.py`:

1. **Flat odds had no memory (high).** P(flat) at the open was a slow EWMA of
   the overall flat share (prior 3%), blind to whether the token is trading
   now. After one quiet minute it said 22% flat where 88% were flat; after a
   revival it kept calling "flat" for dozens of candles. Fix: a two-state
   Markov chain, P(flat | last candle flat) and P(flat | last candle traded),
   EWMA halflife 25. Measured on the training split: 0.92–0.98 after flat,
   ~0.5 after traded at every age; those are the trades-domain priors
   (weight 4). The reviewer's patch alone cut 3-way log loss from 1.004 to
   0.442 at 1m.
2. **Within-candle arrivals assumed Poisson (high).** Bursty trades plus a
   zero-truncated mean rate made a short quiet start read as ~100% "no more
   trades" with a zero-width band (synthetic: stated 98–100% vs true 56–67%).
   Fix: a gamma-mixed (negative binomial) rate with dispersion from the
   observed count variance; once a candle has traded, the rate posterior uses
   the number of trades seen so far.
3. **ACI wind-up (high).** Flat closes always count as "in band", so during
   quiet spells α grew and after a revival the "80%" band covered almost
   nothing. Fix: skip the update when the close is flat and the band contained
   it; for moves, target miss rate (1 − coverage)/(1 − p_flat), capped at 1.
4. **σ collapsed on flat candles (medium).** Fix: only traded candles update
   σ. Retraining was required (v1).
5. **Startup σ prior too narrow (medium).** 3%/min with an outlier cap tied to
   it; real early traded candles move ~28%. Fix: `prior_sigma(tf, "trades")` ≈
   0.25, and no cap for the first 5 updates.
6. **Early up/down odds overconfident (medium).** On a pure random walk 11% of
   calls stated ≥60% and hit 52%; on real 1m tokens, calls ≥70% stated 80% and
   hit 62%. No single lever fixed it; together:
   - reliability slope shrunk toward 0 with 10 pseudo-candles, capped at 1
   - residual location: blend in the reflected CDF with weight k/(n+k), k = 20
   - unit-normal prior instead of Laplace (the Laplace cusp turned a
     0.18σ shift into 61%)
   - calibrator slope capped at 1

   The regression test bins calls instead of averaging them.
   60%+ calls on noise drop from 11.3% to under 5%.
7. **DirectionCalibrator fit biased low (low).** The linearized least squares
   settles near 0.83 on perfectly calibrated odds (sd 1). Fix: discounted
   logistic regression (Newton steps), same prior. The "no intercept" half of
   this finding was refuted: the residual distribution and the global model
   already carry the down-skew of pump.fun moves (P(up | move) ≈ 0.38–0.41).

The measured effect on held-out real tokens is the table in section 8.1. The
reviewers' scripts are in the session scratchpad (not persisted).

## 12. Open problems (ranked)

1. **Incomplete, interrupted trade stream.** The public RPC drops
   notifications (median 93% / mean 84% per token in the v1 data; 38% on one
   busy token; 63% median in the first run), delivers them out of order, and
   since the second run closes the connection every ~30 s.
   - Effects: volume, wallets, holder concentration, and sometimes the true
     close are wrong.
   - Fix: a private RPC websocket in `SOLANA_RPC_WS` (Helius, QuickNode,
     Triton), or `PUMPPORTAL_API_KEY` funded with ≥0.02 SOL. Then re-record and
     retrain, and compare capture (should be ~100%).
   - ~~Order trades within a candle by reserves, not receive time~~ **checked
     2026-10-09, not needed on the chain source:** on `handoff/data/raw-slots`
     (74,438 trades), receipt order never goes back a slot, and of 25,228
     consecutive same-slot pairs none chains only in swapped order (24,404 chain
     as received; the rest have a missed trade between them). No 1-minute close
     changes when trades are ordered by slot. Missed trades remain the problem.
2. **Too little real data.** v1 used ~2.7h (3,523 launches), and early stopping
   picks 54 rounds. Train on 12–48h, and check calibration per token age and
   per capture bucket.
3. ~~Bands over-cover~~ **resolved (8.4):** the band is calibrated against
   its stated probability; the excess over 80% is the "no further trade"
   mass. The live blend's band covers ~1.5–3 points more than it states
   (93.3% vs 91.9%; trading 86.5% vs 83.6%), a small remaining gap.
4. ~~In-candle median worse than "price now"~~ **mostly resolved (8.4):**
   validation-fitted shrink; test edge at f ≥ 0.6 is now −0.4% to +0.7%
   (was −3.0% to −0.4%). The underlying cause, a downward location bias of
   the continuous part for very active tokens late in a candle, remains.
5. ~~Blend underconfident on trading candles~~ **mostly resolved (8.4):**
   global prior 0.95; 69.0% hit vs 67.8% stated (was 64.8%).
6. ~~**Scam signals: the risk level needs rework**~~ **done 2026-10-09:** P(rug) shipped
   and the level reweighted (section 9.1). Original notes:
   (`handoff/experiments/scam_validation.py`). 3,659 launches from every
   recording before 10-09 02:00, judged at +20 s exactly as the fast loop
   judges them (causal creator history). Outcome 30 min later: **rug** = price
   down ≥ 80% (7.2% of launches), **moon** = doubled or graduated (2.8%); the
   median launch is flat (ratio 0.99, already dead).
   - **The displayed risk level barely ranks launches** (AUC 0.57). "danger"
     covers 69% of launches at about the base rate (P(rug) 7.8%); "ok" (17%,
     no flags) is mostly launches where nothing happened (P(rug) 0.2%, P(moon)
     0.2%); "scam" (0.7%, the `collapsed` flag) is 67% rug.
   - Flags that mark rugs: `odd_curve` (P(rug) 27.7%, lift 3.9, recall 89%),
     `few_traders` (lift 6.1, rare), `serial_launcher` (2.5), `serial_rugger`
     (2.5), `repeat_creator` (2.0), `wash_trading` (1.6), `dev_bag` (1.4).
   - Flags that mark *fewer* rugs: `sniped` (lift 0.28), `concentrated`
     (0.41), `dev_dumped` (0.55). They still mark worse *trades*
     (profitability §3.5), because the damage is done in the first seconds,
     but they don't predict a later collapse, and they push most launches to
     "danger".
   - **A learned P(rug)** (LightGBM on the 18 numeric screen features,
     trained on the first 70% of launches) reaches **AUC 0.93** on the rest,
     reasonably calibrated (top decile 52% predicted vs 45% observed; next
     24% vs 31%); mostly `nonstandard_curve` and `raised_sol`.
   - ~~Next: ship a calibrated P(rug) and re-weight the level~~ done (9.1).
7. ~~**Graduated tokens** only through DexScreener polls~~ **done 2026-10-09:**
   `tartar watch` follows a graduated pump.fun token trade by trade in its
   canonical PumpSwap pool. **Recording too (2026-10-09):**
   `tartar record --pumpswap-hours N` (and `tartar fast --pumpswap-hours N`)
   works as follows on each graduation:
   - It subscribes to the token's canonical pool on the same websocket.
   - It writes `graduate`, `swap` and `unwatch` events (format in
     `tartar/data/rawlog.py`).
   - Recording stops after N hours, or after 30 minutes without a trade.

   PumpSwap as a whole runs ~356 successful tx/s, which is why only
   graduated pools are followed. Still open: no loader or `tartar profit`
   support for swap events yet (queue item 11a, part 2). **Since 2026-10-09
   a `watch` continues through graduation:**
   - The chain feed closes its pump.fun connection and follows the token's
     PumpSwap pool.
   - The agent drops the global model, which covers bonding curves only, and
     the online model carries on.
   - Tokens quoted in another token still end at graduation.
8. **The candle-only (OHLCV) model is untrained.**
   - GeckoTerminal returns 429 from this container; collect from another IP.
   - Live DexScreener-polled candles differ from GeckoTerminal OHLC: ranges
     are ~45% narrower. High/low features are already dropped, but σ still uses
     Parkinson ranges.
   - Until it is trained, the (now calibrated) online model is the only
     predictor for those tokens.
9. ~~**Timeframes.** Only a 1m model exists~~ **done 2026-10-09:** 15s, 30s,
   1m and 5m models are installed (8.2.2). Other lengths still use the
   online model alone.
   - The trades-domain σ prior grows as (tf/60)^0.25 above 1m; that is a guess
     beyond the measured 15s and 60s.
10. **GeckoTerminal live polling closes candles 75s after their end**, so
    predictions for that source are locked late. Prefer DexScreener for live.

## 13. Next steps (in order)

1. **Get a complete stream.** Ask the user for a private RPC URL or a funded
   PumpPortal key, then run
   `SOLANA_RPC_WS=wss://... tartar record --hours 24`, and confirm that the
   capture line in `tartar train` reads ~100%.
2. **Record ≥24h, then train** (`tartar train --raw data/raw`). The
   keep-better check compares against v1 on the same test tokens.
3. ~~Fix the point forecast and calibration of the blend~~ (done, 8.4).
4. **Run experiments on the real test split, and adopt only what holds:**
   - hyperparameters (leaves 15–127, min rows per leaf 50–500, lr 0.03–0.1)
   - bin edges
   - an extra fraction near the close (0.99)
   - per-age models
   - dropping noisy features
   - Weight evaluation by "trading" candles, which matter to users.
5. **Validate scam flags** on recorded data (problem 6). Add P(rug) as a model
   feature or output.
6. **Reserve-ordered candle closes** (problem 1).
7. **Other timeframes and the OHLCV model** (problems 8–9).

## 14. Operational notes and gotchas

- **The container is ephemeral.**
  - `data/` is gitignored; the recorder writes to `data/raw`.
  - A snapshot of everything recorded is in `handoff/data/raw/`; copy it back
    to `data/raw` to train.
  - Restart recording after any container restart:
    `setsid nohup tartar record --out data/raw --hours 20 --track-minutes 90 --idle-minutes 20 >> data/logs/record.log 2>&1 < /dev/null &`
  - The current recorder was started at 18:32 UTC on 2026-10-08 with
    `--hours 20`. It logs every disconnect to `data/logs/record.log` (expect one
    every 10–30 s on the public RPC). Stop it with SIGTERM; SIGINT does not.
- **Never let LightGBM share busy cores.** It uses every core by default, and when anything else
  is CPU-bound (another training, a replay, pytest's fixtures) it slows down 10–50×: on 2026-10-09
  a sweep setting took 31 min instead of 2, and a 13 s test ran past 10 min. Run one LightGBM job
  at a time, or cap each with `OMP_NUM_THREADS` below the free cores (replays: `OMP_NUM_THREADS=1`;
  single-row predictions gain nothing from threads). The container has 4 cores and 15 GB.
- **Train into a scratch directory first, then install.** For example
  `tartar train --raw <snapshot> --out /tmp/m --force`, read the table, then
  copy `trades-60s.{txt,json,report.json}` into `tartar/models/`. Train on a
  copy of `data/raw`, not the live directory: the recorder appends to the
  current hour's file, so cut it at the last complete line.
- **A/B a code change on the same tokens.** Run `git worktree add --detach
  /tmp/old HEAD`, then run the same script from both trees. The script puts
  the tree first on `sys.path`, loads `load_trade_tokens(raw, 60)`, takes the
  last 15% of launches by `created` (the test split), and calls
  `tartar.train.replay(tokens[:300], 60, "trades", None)`. Section 8.1's
  table was made this way.
- **Always pass `domain="trades"`** to `Forecaster`/`FeatureEngine` for pump.fun
  trade streams. The default is `"ohlcv"`, and the domain now selects the σ and
  flat-odds priors. The parity tests would catch a mismatch.
- **`pgrep -f "tartar record"` matches your own shell.** Its command line
  contains the pattern, so `kill $(pgrep -f ...)` can kill the shell running it.
  Use `ps -eo pid,cmd | grep "[t]artar record --out" | grep python`.
- **Don't open extra RPC websocket connections while recording.** The public
  endpoint often refuses a second connection from the same IP.
- **The background GeckoTerminal collector died** with the worker restart; it
  only ever got 1 token because of 429s.
- **Session limits:** the multi-agent review hit a usage limit mid-run; keep
  workflows small.
- Network access must allow `pumpportal.fun`, `api.geckoterminal.com`,
  `api.dexscreener.com`, `api.mainnet-beta.solana.com` and `api.rugcheck.xyz`.
  The user enabled full access.
- Commits end with the session attribution lines; push to
  `claude/solana-candle-predictor-s95qjr`; `main` was fast-forwarded to it
  at the user's request, so PR #1 shows as merged. New work goes on a fresh
  branch from `main` and a new PR.

## 15. Full code

Every source file is in the repo (authoritative) and copied to
`handoff/archive/predictor-snapshot-2026-10-09/` with the same paths (`handoff/archive/predictor-snapshot-2026-10-09/tartar/...`,
`handoff/archive/predictor-snapshot-2026-10-09/tests/...`, `pyproject.toml`, `README.md`). Installed model:
`tartar/models/trades-60s.{txt,json,report.json}` (v1; the 8.9 MB `.txt` is not
duplicated under `handoff/archive/predictor-snapshot-2026-10-09/`). Size: ~7,850 lines of Python across 36
modules and 9 test files.
