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

tartar demo                 # simulated memecoin, no network needed
tartar watch <TOKEN_MINT>   # watch a real token (mint or pool address)
tartar watch --next-launch  # wait for the next pump.fun launch and watch it
tartar new                  # list the newest Solana pools
```

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

All of these components are online and learned per token (`tartar/model/`):

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
   estimated from trade arrival rates, which pins the close to the current price.
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
responses, a local websocket server standing in for PumpPortal, source
selection, and the agent loop end to end.
