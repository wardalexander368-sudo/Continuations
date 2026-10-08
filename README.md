# TARTAR

A live agent that watches the candle chart of any Solana token, including tokens
launched minutes ago, and predicts each candle's closing price. Every prediction
comes with a confidence you can check: the agent scores itself on every candle
and shows whether its stated confidence matched what actually happened.

```
╭─ Next close ─────────────────────────────────────────────╮
│          candle 05:59  closes in 0:41 ▰▰▰▰▱▱▱▱▱▱▱▱▱▱     │
│       price now 0.0₇4126 SOL  -12.00% vs prev close      │
│ predicted close 0.0₇4136 SOL ▼ -11.80%                   │
│      confidence DOWN 93%   ▲7% ▼93% ▬0%                  │
│        80% band 0.0₇3985 – 0.0₇4286                      │
│  locked at open 0.0₇4703 ▲ UP 50% (≈ coin flip)          │
│      volatility 3.64%/candle · signal +0.02σ             │
╰──────────────────────────────────────────────────────────╯
```

## Quick start

```bash
pip install -e .            # Python 3.10+

tartar demo                 # simulated pump.fun token, no network needed
tartar watch <TOKEN_MINT>   # watch a real token (mint or pool address)
tartar watch --next-launch  # wait for the next pump.fun launch and watch it
tartar new                  # list the newest Solana pools
```

## Getting the most accurate predictions: train the global model

Out of the box, the agent learns each token from scratch while it watches.
Accuracy improves a lot with a **global model** trained on thousands of real
launches. It learns patterns that repeat across tokens, which a single young
token can't show. Collecting the data and training take three commands:

```bash
tartar record --hours 12          # record every pump.fun launch and its trades
tartar train --raw data/raw       # train, evaluate on later launches, install
tartar watch <TOKEN_MINT>         # now uses the global model automatically
```

Or let it run unattended. `learn` records continuously and retrains every few
hours; a new model is only installed if it beats the current one on the newest
launches:

```bash
tartar learn --first-train-hours 3 --retrain-hours 6
```

More data makes a better model. A few hours (several hundred launches) gives a
first model; a day or more is better. For tokens that aren't streamed from
PumpPortal (DexScreener/GeckoTerminal sources), train a candle-only model with
`tartar collect -t 1m` then `tartar train --ohlcv data/ohlcv/1m`.

`tartar train` prints an honest report on tokens launched after everything it
trained on:

* error versus the naive "close = current price", direction hit rate against
  stated confidence, and band coverage, at the candle open and at points during
  the candle
* the live forecaster replayed candle by candle on those tokens, with and
  without the global model
* the most useful features

The full report is saved next to the model as `.report.json`.

`watch` opens a full-screen dashboard with the candle chart, the predicted close
(◆) and its band (┊) next to the forming candle, the current prediction, the track
record, and recent results. Press Ctrl+C to stop; a summary is printed on exit.

Useful options:

| option | meaning |
|---|---|
| `-t 1m` | candle size: `15s`, `30s`, `1m`, `5m`, `15m`, `1h`, … (default `1m`) |
| `--band 0.8` | coverage of the prediction band (default 80%) |
| `-o plain` / `-o json` | log lines or JSON lines instead of the dashboard |
| `--log preds.jsonl` | also append every event to a JSON-lines file |
| `--source auto\|pumpportal\|dexscreener\|gecko` | force a data source |
| `--history 500` | historical candles to warm up on (max 1000) |
| `--candles N` | stop after N candles |

## What the numbers mean

* **Predicted close**: the median of the predicted distribution of the candle's
  closing price. Half the time the close should land above it, half below.
* **Confidence**: the probability that the predicted direction (up, down or
  flat versus the previous close) is right. Calls at 52% or below are labelled
  *≈ coin flip*. A flat call means nothing is likely to trade at all.
* **Band**: a range the close should land in 80% of the time (`--band`). Its
  width is adjusted online so that it really does cover 80% on this token.
* **Locked at open**: the forecast made when the candle opened, using only the
  closed candles before it. Every locked forecast is scored when its candle
  closes. The live estimate above it is refreshed as trades come in during the
  candle and becomes more certain as the close approaches.
* **Track record**: for the last 50 candles, this session, and the warm-up on
  history:
  * *direction hit* compared with *stated conf.*: these should match if the
    confidence is honest.
  * *in band*: should be close to 80%.
  * *edge vs naive*: how much smaller the error is than predicting "the close
    equals the last close". It is close to 0% on most tokens most of the time.

**Expect low confidence.** Next-candle moves of young memecoins are mostly
noise. When the model can't beat a coin flip on a token, its confidence stays
near 50% instead of inventing conviction. Use this as a tool for measuring and
watching price action, not as trading advice.

## Data sources

| source | used for | latency | key |
|---|---|---|---|
| [PumpPortal](https://pumpportal.fun) websocket | every trade on pump.fun bonding-curve tokens, plus new launches | real time | none (set `PUMPPORTAL_API_KEY` if your account needs one, e.g. for PumpSwap trades) |
| [DexScreener](https://docs.dexscreener.com) API | token/pair lookup; price polled every 3s for all other tokens | a few seconds | none |
| [GeckoTerminal](https://www.geckoterminal.com/dex-api) API | historical OHLCV for warm-up; fallback live polling; new pools list | up to ~1 min | none (30 req/min) |

`--source auto` (the default) picks a source like this:

1. A pump.fun mint still on its bonding curve, or not yet listed anywhere, uses
   PumpPortal. Prices are in SOL.
2. Any other token with a DexScreener pair uses DexScreener. Prices are in USD.
3. Otherwise it falls back to GeckoTerminal polling. Use `-t 5m` or longer with
   this source because of its lag.

Before going live, the model warms up on up to 1000 historical candles from
GeckoTerminal, as a walk-forward run in which every candle is predicted using
only the candles before it. That gives each token a real track record from the
start. A token too new to be indexed starts cold and learns as candles close.

`tartar resolve <mint>` shows which pool, source and history `watch` would use.

## How the prediction works

Two predictive distributions are blended. The weight follows each one's recent
log score on the token being watched, so whichever predicts this token better
takes over.

**Global model** (`tartar/model/global_model.py`, trained by `tartar train`): a
LightGBM classifier that outputs a full distribution for the rest of the
candle. That is the probability the price doesn't move again, plus the
probabilities of the remaining move landing in 24 volatility-scaled bins. The
median, band and direction odds all come from that one distribution. It sees
about 50 features (`tartar/model/engine.py`):

* price action: returns, momentum, candle shape, EMAs, drawdown from the
  all-time high
* activity: trade counts and volume against the token's normal, quiet streaks,
  time since the last trade
* order flow: buy/sell count and SOL imbalance, whale share
* wallets: unique and first-time traders, holder growth
* the creator (dev) wallet: sells this candle, total sold, share of the bag left
* lifecycle: token age, bonding-curve progress, market cap
* the forming candle so far: elapsed time, move, trades, flow, range, new
  wallets, dev sells

It is trained on snapshots taken at the open and at 20/40/60/80/95% through each
candle, so the live estimate is a model prediction at every moment. Training
also mimics live conditions. For some tokens the creator or launch time is
hidden. For about 30%, the model "starts watching" mid-life: only candle history
before that point (like the GeckoTerminal warm-up), then trades with wallets
tracked from scratch. That way the model still works on tokens you join after
launch. The same
code computes features in training and live, and a test checks they match
exactly. The model's probabilities are calibrated with temperature scaling on
held-out tokens.

**Online model**, learned per token while watching (`tartar/model/`):

1. **Volatility**: an EWMA of per-candle log-return variance that blends
   close-to-close moves with the high/low range (the Parkinson estimator), so a
   few candles are enough. Everything else is measured in units of this volatility.
2. **Signal**: an ensemble of experts: random walk, drift (trend), momentum,
   order flow (candle shape, volume surge, buy/sell imbalance), and a full
   ridge regression. Experts are weighted by how well each has predicted this
   token recently, starting with most of the weight on the random walk. The
   result is then scaled by a reliability slope fitted on realized moves, so a
   signal that hasn't proven itself fades to zero.
3. **Uncertainty**: the empirical distribution of the model's own past errors
   on this token, kernel-smoothed and shrunk toward a fat-tailed Laplace prior
   while there is little data. The band uses adaptive conformal inference to
   hold its target coverage.
4. **Flat odds**: the chance that nothing trades in the rest of the candle,
   which pins the close to the current price. Trade arrivals are modelled as
   bursty (quiet spells, then busy ones).
5. **Calibration**: up/down probabilities are recalibrated against realized
   directions, so a 60% call is right about 60% of the time.

During a candle, the live estimate combines the price so far with the signal
and uncertainty for the remaining fraction of the candle.

Check the calibration on a token's history:

```bash
tartar backtest <TOKEN_MINT> -t 1m
tartar backtest --csv candles.csv -t 5m   # timestamp,open,high,low,close[,volume]
```

## JSON output

`-o json` (or `--log FILE`) emits one object per line:

```json
{"type": "prediction", "ts": 1759903181.2, "candle_start": 1759903140, "candle_end": 1759903200,
 "elapsed": 0.69, "prev_close": 4.703e-08, "price_now": 4.126e-08, "predicted_close": 4.136e-08,
 "change_pct": -12.06, "direction": "down", "confidence": 0.93, "p_up": 0.07, "p_down": 0.93, "p_flat": 0.0,
 "band": {"coverage": 0.8, "low": 3.985e-08, "high": 4.286e-08}, "volatility_pct": 3.64, "signal_sigma": 0.02}
{"type": "result", "candle_start": 1759903080, "predicted_close": 4.796e-08, "actual_close": 4.689e-08,
 "prev_close": 4.781e-08, "error_pct": -2.23, "direction": "up", "confidence": 0.5, "actual_direction": "down",
 "hit": false, "in_band": true, "band": {"coverage": 0.8, "low": 4.402e-08, "high": 5.216e-08}}
```

Other event types are `start`, `warmup`, `candle` (each closed OHLCV candle),
`forecast` (the locked forecast for the next candle), `status` and `summary`.

## Development

```bash
pip install -e ".[dev]"
pytest
```

The tests cover candle assembly, model calibration on synthetic series (random
walk, momentum, mean reversion, dead tokens), API parsing against mocked
responses, local websocket servers standing in for PumpPortal (live feed and
recorder), source selection, the agent loop end to end, and the training
pipeline. That includes the check that features computed live equal the
training rows exactly.

`tartar simulate` writes pump.fun-style launches (real bonding-curve math,
invented trader behaviour) in the recorder's format, for exercising the pipeline
without network access. Models trained on simulated data are only ever loaded
by `tartar demo`, never for real tokens.
