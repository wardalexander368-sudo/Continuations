# TARTAR: project overview

Written 2026-10-09 (~14:00 UTC) by the handoff session, at the user's request, from the repo as it
stood then. This is the short version for the user and for any new session. The detail lives in
the topic documents (*Where to read more* below); `handoff/STATUS.md` is the live task board.

## 1. What TARTAR is

A command-line agent that watches the candle chart of any Solana token, including pump.fun
tokens launched seconds ago, and predicts each candle's closing price **with a confidence that is
checked against what happens**. It reads pump.fun and PumpSwap trades straight from the chain on
the free public RPC, decodes them itself, and scores itself on every candle.

The user's brief, in order:

1. *"An agent that can watch a candle graph live, predict the next candle closing price on any
   new sol coin/token and live-output that result and its confidence."*
2. *"Build the highest accuracy predictor that we can."*
3. Scam filtering.
4. Find out whether any of it **makes money** after real costs, and look for an edge.

Items 1–3 are built and working. Item 4 has a clear answer so far: **no tested strategy makes
money** (section 4).

## 2. What it can do today

| Command | What it does |
|---|---|
| `tartar watch <mint>` | Live dashboard: predicted close, direction confidence, 80% band, track record. Follows a pump.fun token through graduation onto its PumpSwap pool. |
| `tartar watch --next-launch` | Waits for the next pump.fun launch that passes a 20-second screen, then watches it. Shows a risk level and P(rug). |
| `tartar scan <mint>` | One-off scam report (behaviour, mint authorities, Token-2022 extensions, RugCheck, creator history). |
| `tartar record` | Records every pump.fun launch and trade (and, with `--pumpswap-hours`, each graduated token's PumpSwap pool) to hourly gzip files. |
| `tartar train` | Trains the global model on recordings, tests it on later launches, and installs it only if it beats the installed one (`--rug` for P(rug), `--pumpswap` for graduated tokens). |
| `tartar profit`, `tartar decide` | Net SOL of strategies after fees, price impact, network fees and latency, with thresholds chosen on validation and results on the latest launches. |
| `tartar fast`, `tartar review` | A paper-trading fast loop and its review. **Retired by the user**; `tartar fast --replay` remains a study tool. |
| `tartar demo`, `tartar simulate` | Offline: simulated pump.fun launches with real bonding-curve math. |

140 tests (`pytest`), including a check that the features computed live equal the training rows
exactly.

## 3. How good the predictor is

Two forecasts are blended per token: a **global model** (LightGBM, a full distribution over the
rest of the candle, trained on thousands of recorded launches) and an **online model** learned
while watching. The blend weight follows whichever has predicted this token better.

Installed now: **v3.1** for 15 s, 30 s, 1 m and 5 m candles, trained on 7,700–15,500 real
pump.fun launches recorded from the chain on 2026-10-08/09. Scored on the latest 15% of launches,
which it never saw:

| Candle | Live edge vs "close = last price" (all / trading candles) | Trading candles: hit vs stated confidence |
|---|---|---|
| 15 s | +2.2% / +2.4% | 62.1% vs 60.2% |
| 30 s | +5.7% / +6.0% | 63.1% vs 61.6% |
| 1 m | +8.0% / +8.2% | 64.6% vs 64.3% |
| 5 m | +11.9% / +12.2% | 73.8% vs 73.4% |

The confidence is honest (it matches the hit rate within ~2 points), and the error is 2–12%
smaller than the naive forecast. Most next-candle moves of young memecoins are noise, so expect
modest confidence. One known gap: the 5 m model is still overconfident at the candle open (states
75.5%, hits 69.7%).

**After graduation** (the token trades on its PumpSwap pool), a separate **1 m PumpSwap model**
(348 graduated pools) takes over. On 52 later pools it makes the forecast honest: on trading
candles it states 72.0% and hits 72.0%, where the online model alone states 49% and hits 63%. Its
point forecast is barely better than naive (+0.9% edge). A 5 m version failed the install rule
(worse edge), so at other lengths the online model carries on alone after graduation.

**Scam filtering:** a live risk level (ok / caution / danger / scam) with reasons, plus a learned
**P(rug)**, the chance a launch collapses 80% within 30 minutes, judged on its first 20 seconds.
P(rug) held AUC 0.924 on 7,075 launches recorded after it was trained, against 0.69 for the
rule-based level, and the retrained model (12,342 launches) reaches 0.935.

## 4. Does it make money? No, not so far

Everything is judged by net SOL after every cost, on launches the strategy never saw, with 90%
intervals by token. Measured costs:

| Venue | Cost per side |
|---|---|
| pump.fun bonding curve | **1.25%** (0.95% protocol + 0.30% creator), measured from on-chain events |
| PumpSwap, young pools | **1.20–1.25%**, falling to 0.30% only near 500k SOL market cap (the project had assumed 0.30%) |
| SOL-USD on-chain via Jupiter | **~0.5 bps per fill** (p90 ~1.3), against 90 bps taker at Coinbase |

On pump.fun a round trip starts **~3.5% down** (fees, network, impact), and the typical launch is
dead within minutes. Every strategy family tested loses:

| Strategy family | Result on later launches |
|---|---|
| Buying launches: every launch, model signals, screens, scam flags, learned scorers, Jev | loses (e.g. −3.6% per trade buying every launch; the v1 model's "expected return" picks lose −43%) |
| Faster entry (slots, private RPC) | only a buy bundled into the creator's own transaction profits (+6.8%); the best outsider entry loses −5.3%, even with zero fees −1.8% |
| Graduation run-up on the curve | break-even at best, once two biases were removed |
| Longer holds (10–45 min) on screened launches | −12.5% per trade |
| Copy-trading wallets whose buys paid off | −21.0% per trade |
| Graduated tokens in their first hour on PumpSwap (pre-registered, 264 pools) | all four rule families lose (−3.4% to −38.1%) |
| Established memecoins: momentum, breakouts | lose; dip-buying shows no reliable edge and is in a forward test |
| Jev (TypeSafe) as a launch scorer or on metadata | no signal in three tests |

The one place on-chain costs are tiny is SOL-USD itself, which is what the user's separate
`jevtrader` test measures (section 5).

## 5. What is still open

| Item | State | When |
|---|---|---|
| **Dip-buying on established memecoins** | pre-registered rolling forward test; add a cohort about daily (`established_cohort.py`); next due ~02:24 UTC 10-10 | scored 2026-10-30 or at ≥ 200 trades |
| **jevtrader** (the user's SOL-USD + Jev paper test, its own repo) | sealed until day 28; TARTAR only supplies the on-chain cost table and never touches it | results 2026-10-23 |
| **Edge hunt** (new families) | **on hold by the user**. Best candidate so far: delta-hedged JLP, +7.9% APR over USDC lending, exploratory 90% CI [+3.0, +12.4]; worth a pre-registered 90-day paper forward test | when the user resumes it |
| **PumpSwap model** (predictions after graduation) | 1 m installed; 5 m failed its install rule; 30 s and 15 s in training (handoff session) | 10-09 |
| **More data** | recorders running in the active sessions; finished hours go to `handoff/data/` | ongoing |
| SOL-USD costs at US hours | clever session sampling 10–16 UTC | 10-09 |

## 6. Decisions the user has made

* **Paper only.** No real-money trading code without an explicit request.
* **Jev stays off in TARTAR** (2026-10-09): no shadow mode, no Jev scorer, no new asks. Cached
  answers may be read offline.
* **The live fast loop is retired.**
* **No private RPC for now.** The public RPC captures a median 100% of each token's trades on the
  current recorder, and faster data can't make launch buying pay (section 4).
* **jevtrader is sealed:** never unblind, run, push to, or feed from it.
* **Edge hunt on hold** until the user asks.
* **Weekly usage limit:** at ~95%, dump everything to the repo with a complete summary.

## 7. Data

All recordings are real chain data from the public RPC, in `handoff/data/` (hourly `.jsonl.gz`,
one directory per recorder):

| Directory | When (UTC) | Notes |
|---|---|---|
| `raw` | 10-08 14:06 – 10-09 03:39, in bursts | v1's data; older recorder (lower capture, longer idle cut) |
| `raw-slots`, `raw-slots-processed` | 10-09 00:01–00:48 | slot numbers on every event |
| `raw-pumpswap` | 10-09 01:30–01:50 | first PumpSwap recording |
| `raw-eager` | 10-09 04:06–06:00 | 2,639 launches, 69 graduated pools |
| `raw-clever` | 10-09 06:23 onward | ~1,900 launches and ~40 graduated pools per hour |
| `raw-v3` | 10-09 06:25–06:31, then 13:31 onward | 2-hour token tracking |

Also: `established/` (GeckoTerminal 5-minute data), `sol-dex/` (SOL-USD cost samples), `jev/`
(cached Jev answers), `edge-hunt/` (funding, lending and JLP histories).

## 8. How the work is organized

Several Claude sessions on two accounts take turns. `handoff/STATUS.md` is the shared board:
claim a task under *Active* before starting, work on a `claude/<topic>` branch, push after every
unit that passes `pytest`, land on `main` by fast-forward, and log where you stopped. Containers
suspend when a session goes idle, which kills background recorders, so finished hours are copied
into `handoff/data/` as they close.

## 9. Where to read more

| Document | What's in it |
|---|---|
| `handoff/STATUS.md` | live board: who is working on what, the ranked queue, rules, log |
| `handoff/candle-prediction-agent.md` | the predictor: architecture, data pipeline, features, every model version, scam filtering, open problems |
| `handoff/profitability.md` | every strategy test with its numbers (§1 is the summary table) |
| `handoff/edge-hunt.md` | the paused edge hunt: findings and how to resume |
| `handoff/jevtrader.md` | the user's jevtrader and TARTAR's SOL-USD cost table |
| `handoff/preregistration/` | pre-registered studies and their results |
| `handoff/experiments/` | the study scripts |
| `handoff/slow-loop.md` | the retired fast/slow loop |
| `README.md` | user guide for the tool |
