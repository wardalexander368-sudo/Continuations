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

## Scam filtering

Most new launches are scams or dead on arrival, and they move differently from
organic tokens. Every watched token gets a live **risk level** (ok, caution,
danger or scam) with its reasons. It appears in the dashboard header, as a
line in plain output, and as a `risk` event in JSON. Three kinds of evidence
feed it:

* **Behaviour**, from the token's own trades:
  * the creator selling their tokens
  * supply sniped in the first seconds (bundled launches)
  * the top 10 wallets holding most of the supply
  * the creator's remaining bag
  * wash trading (quick buy/sell round trips by the same wallets)
  * a handful of wallets doing all the trading
  * a non-standard bonding curve
  * a collapse of 90% or more from the peak
* **The mint**, via Solana RPC:
  * mint or freeze authority not revoked
  * dangerous Token-2022 extensions: permanent delegate, transfer hook,
    transfer fees, pausable, frozen by default, non-transferable
* **Reputation**:
  * [RugCheck](https://rugcheck.xyz)'s report: its risks, insider-wallet
    networks, rugged flag, and holders (pools and lockers excluded)
  * the creator's record in your recordings: past rugs and serial launches
  * copycat launches that reuse a name or metadata

```bash
tartar scan <TOKEN_MINT>             # one-off report (exit code 3 if danger/scam)
tartar watch --next-launch           # watches the first launch that passes screening
tartar new --safe                    # newest pools with scam-flagged ones hidden
```

`--next-launch` follows each new launch for 20 seconds (`--screen`). It skips
launches with fewer than 3 real buyers (`--min-buyers`), and any flagged danger
or scam (`--allow-risky` to keep them). The behavioural signals are also inputs
to the global model, so a dev dump or a bundled launch shapes the price
prediction as well as the warning.

## Getting the most accurate predictions: train the global model

A model (`tartar/models/trades-60s`, trained on 5,790 real pump.fun
launches) ships with the repo and is used automatically for 1-minute candles of
pump.fun tokens. Without a trained model, the agent learns each token from
scratch while it watches.
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
| `--no-scam-check` | skip the RugCheck/mint lookups (behavioural flags still shown) |

## Does it make money? `tartar profit`

Accuracy is not profit. `tartar profit` replays trades on the recorded
bonding curves with every cost charged: the pump.fun fee on both sides (1.25%
by default), price impact on the curve, network fees, and the delay between a
decision and its execution (1 s by default). It reports net SOL per trade for
baseline strategies and for trading on the model's predictions, with
thresholds chosen on earlier launches and results measured on the latest ones.

```bash
tartar profit                          # defaults: 0.1 SOL, 1.25% fee/side, 1 s latency
tartar profit --latency 0.4 --fee 0.5  # what if execution were faster or cheaper?
```

On the recorded data so far, **no strategy is profitable** after costs, and
buying where the model's expected return is highest loses heavily. See
`handoff/profitability.md`.

## Fast loop and slow loop: `tartar fast`, `tartar review`

The **fast loop** decides on every new launch within seconds. It waits a
few seconds after each launch, applies skip rules, asks a scorer (TypeSafe's
Jev with `TYPESAFE_API_KEY`, or plain rules), and **paper**-trades a yes on
the live bonding curve. Every decision goes to a journal. The **slow loop**
(a person or Claude, every few hours) runs `tartar review`, which compares
the paper results with what every screened launch would have earned, and
edits the policy file. The fast loop reloads the policy when it changes.

```bash
tartar fast                             # live, paper only; also records raw data
tartar fast --replay data/raw           # the same loop over recorded data
tartar review --hours 6                 # results, counterfactuals, scorer calibration
```

The policy (`data/policy.json`) is bounded and paper-only by construction.
See `handoff/slow-loop.md`.

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
| Solana RPC (`logsSubscribe` on the pump.fun program) | every pump.fun launch and trade, decoded straight from the chain; live watch, launch screening, recording | real time | none (public endpoints; set `SOLANA_RPC_WS` to use your own) |
| [DexScreener](https://docs.dexscreener.com) API | token/pair lookup; price polled every 3s for all other tokens | a few seconds | none |
| [GeckoTerminal](https://www.geckoterminal.com/dex-api) API | historical OHLCV for warm-up; fallback live polling; new pools list | up to ~1 min | none (30 req/min) |
| [RugCheck](https://rugcheck.xyz) API | scam checks | — | none |
| [PumpPortal](https://pumpportal.fun) websocket | optional alternative for pump.fun trades | real time | its per-token trade stream needs `PUMPPORTAL_API_KEY` funded with SOL |

`--source auto` (the default) picks a source like this:

1. A pump.fun mint still on its bonding curve, or not yet listed anywhere, is
   read straight from the chain (`--source chain`; PumpPortal instead if
   `PUMPPORTAL_API_KEY` is set). Prices are in SOL.
2. Any other token with a DexScreener pair uses DexScreener. Prices are in USD.
3. Otherwise it falls back to GeckoTerminal polling. Use `-t 5m` or longer with
   this source because of its lag.

Before going live, the model warms up on up to 1000 historical candles from
GeckoTerminal, as a walk-forward run in which every candle is predicted using
only the candles before it. That gives each token a real track record from the
start. A token too new to be indexed starts cold and learns as candles close.

`tartar resolve <mint>` shows which pool, source and history `watch` would use.

**Data quality.** The free public Solana RPC drops a share of websocket
notifications under load. In our recordings, a median of about 63% of a token's
trades arrived, and less for the busiest tokens. Prices stay exact, because
every trade carries the curve's state, but volume, trade counts and wallet
statistics are undercounted, and a candle's close can miss its last trade.
Training and live use the same stream, so they stay consistent, and
`tartar train` reports the capture rate. For complete data, point
`SOLANA_RPC_WS` at a private RPC websocket (Helius, QuickNode, Triton, …) or set
a funded `PUMPPORTAL_API_KEY`.

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
   few candles are enough. Only candles that traded update it, and it starts
   from a prior that fits the source (about 25% per candle for a pump.fun
   launch watched trade by trade). Everything else is measured in units of this
   volatility.
2. **Signal**: an ensemble of experts: random walk, drift (trend), momentum,
   order flow (candle shape, volume surge, buy/sell imbalance), and a full
   ridge regression. Experts are weighted by how well each has predicted this
   token recently, starting with most of the weight on the random walk. The
   result is then scaled by a reliability slope fitted on realized moves. It
   starts at zero and never exceeds one, so a signal counts only once it has
   proven itself and is never amplified.
3. **Uncertainty**: the empirical distribution of the model's own past errors
   on this token, kernel-smoothed and shrunk toward a normal prior while there
   is little data (a lopsided handful of errors is not read as direction). The
   band uses adaptive conformal inference to hold its target coverage.
4. **Flat odds**: the chance that nothing trades in the rest of the candle,
   which pins the close to the current price. Quiet spells and busy ones
   persist, so the odds of a flat candle depend on whether the last one traded,
   and trades within a candle arrive in bursts (a gamma-mixed Poisson rate).
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
