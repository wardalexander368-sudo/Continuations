<!-- read:data: workflow section summary as of 2026-10-09 12:56 UTC; 'verify-*' files are fact-checked, 'read-*' are not -->

## Data, experiments and reproducibility (as of 2026-10-09 12:56 UTC)

### Terms used below
- **pump.fun launch / bonding curve**: a new Solana token starts on pump.fun's built-in price curve. Price rises as SOL is paid in.
- **Graduation**: when a curve has raised about 85 SOL, it completes and the token moves to a **PumpSwap** pool, which is an automated market maker (AMM).
- **Slot**: one Solana block slot, about 270 ms (`handoff/STATUS.md:96`).
- **Commitment**: how final a block must be before the RPC sends its events to us. "confirmed" is the default; "processed" is faster but sometimes includes blocks that are later dropped.
- **Quote-paired curve**: a curve priced in another token (such as USDC or another pump coin) instead of SOL. Recordings made with the old decoder have no trades for these curves.
- **Capture**: the share of a token's real trades the free public RPC actually delivered.
- **bps**: basis points, 0.01%.
- **Log loss**: the probabilistic error of a model's predicted distribution. Lower is better.
- **Edge**: how much smaller the error is than the naive guess "the close equals the current price".
- **Keep-better rule**: `tartar train` installs a new model only if its test log loss is lower than the installed model's.
- **Pre-registration**: the study's rules and success criteria are committed to git before any of its results are computed.
- **Jev**: TypeSafe's decision API. The user has since turned it off for TARTAR.

### 1. Where data lives
- **`handoff/data/`** holds 247M in 9 subdirectories (`du -sh`). Every file is tracked in git, with one exception: three `sol-dex/*.jsonl` files are ignored by the repo-wide `*.jsonl` rule (`.gitignore:7`; `git status --ignored`). The data README says to add sample files with `git add -f` (`handoff/data/README.md:75-76`).
- **`data/`** holds 75M locally and is untracked (`/data/` in `.gitignore:8`). It is what this container's recorders and tools write to. The predictor doc warns that "the container is ephemeral" (`handoff/candle-prediction-agent.md:915-919`).
- Recorder output is hourly JSON-lines files, gzipped when the hour rotates. Events are `create`, `trade`, `migrate`, `track`/`untrack` and `session`. Since 2026-10-09 there are also `slot` fields and the PumpSwap events `graduate`, `swap` and `unwatch` (format in `tartar/data/rawlog.py`; `handoff/candle-prediction-agent.md:196-205`).
- **One recorder per directory.** The loader reads each directory as one timeline (`handoff/data/README.md:16-18`). To train on several recorders, pass them comma-separated: `--raw A,B` (`tartar/cli.py:136`).

### 2. Dataset table (tracked snapshot in `handoff/data/`)
Date ranges come from the file names. Precise times come from the docs.

| Name | What it contains | Period (UTC) | Files / size | Tracked? | Produced by |
|---|---|---|---|---|---|
| `raw/` | pump.fun launches and trades over the public RPC, old decoder. Capture: median 93%, mean 84% per token; the second run reconnects every ~30 s (README:11-12). v1 was trained on the 14:06–15:13 and 18:32–20:06 runs only: 5,565 launches, 213,490 trades, 3,523 usable tokens at 1-minute candles (README:8-9) | Files 20261008-14 to 20261009-03. Two sources. The predictor session's recorder: 10-08 14:06–15:13, 18:32–20:34 and 21:42–21:50. The Jev session's fast loop: 23:44–23:50, 00:03–00:10, 02:47–02:54 and 03:17–03:39 (README:8; STATUS.md:330, 293, 436) | 10 files, 26M | tracked | `tartar record` and `tartar fast` (the fast loop records as it runs) |
| `raw-slots/` | "confirmed" commitment with `slot` on every event: 1,347 launches, 74,509 trades. Old decoder, so quote-paired curves appear as creates with no first buy; filter on `create.vsol` (README:20-28) | 20261009-00 (00:01–00:42) | 1 file, 5.6M | tracked | predictor session, `tartar record` |
| `raw-slots-processed/` | "processed" commitment: 304 launches, 9,594 trades (README:22-23) | 20261009-00 (00:42–00:48) | 1 file, 748K | tracked | predictor session |
| `raw-pumpswap/` | First `--pumpswap-hours 2` recording: 698 launches, 44,286 curve trades, 20 graduations, 33,292 PumpSwap trades. 12 graduated SOL pools were followed; the 8 quote-paired graduations recorded no swaps (README:31-42) | 20261009-01 (01:30–01:50) | 1 file, 6.4M | tracked | predictor session |
| `raw-eager/` | `tartar record --out data/raw-eager --pumpswap-hours 4 --hours 20`, "confirmed" commitment, current decoder. Hour 04: 1,272 launches, 95,177 curve trades, 35 graduations, 91,817 swaps. Hour 05: 1,360 / 110,936 / 35 / 118,839. Hour 06 is a 17-second stub. 69 graduated SOL pools in all. Capture: median 100%, mean 97%. One pool checked against the chain: 138 of 143 swaps captured (96.5%) (README:49-62). This is evaluation data for the 11a study (README:64-66) | 20261009-04 to -06 (04:06–06:00:17) | 3 files, 34M | tracked | research session |
| `raw-clever/` | Recorded the same way as raw-eager. Hours 06–11 hold 195 graduated SOL pools. Summing the README's hourly figures gives 7,568 launches, 656,249 curve trades and 1,397,753 PumpSwap swaps. Two 2 s reconnects in hour 08. Together with raw-eager: **264 graduated SOL pools, the exact 11a evaluation set** (README:78-99) | 20261009-06 to -11 (06:23–11:59) | 6 files, 169M | tracked | clever session |
| `sol-dex/` | Jupiter $1,000 round-trip **quotes, not fills**, re-quoted after 1/2/5 s, with Coinbase's book. Tracked: `costs-20261009.jsonl` (216 samples, 04:09–06:00, research session) and `costs-20261009-day.jsonl` (371 samples, 06:43–09:55, clever session) (README:70-75). **Untracked (git-ignored):** `costs-20261009-0433.jsonl` (120 samples, 04:33–05:32), `costs10k-20261009-0456.jsonl` (71 samples, $10k size), `decay-20261009-0433.jsonl` (178 samples) | 20261009 | 5 files, 624K | 2 of 5 tracked | `handoff/experiments/sol_dex_costs.py sample` |
| `established/` | `ohlcv-2026-10-09.tar.gz`: GeckoTerminal 5-minute USD OHLCV for liquid Solana pools, described as a "tar of both collections" (profitability.md:400). It holds 62 pool JSON files. Reading the files, candles run 2026-09-24 02:00 to 2026-10-09 02:20 UTC and were fetched ~01:56–02:05 on 10-09 (my reading, not stated in the docs) | 2026-10-09 (name) | 1 file, 4.3M | tracked | `established_collect.py` |
| `jev/` | Cached Jev answers and launch metadata behind profitability §3.7–3.8: `metadata.jsonl.gz` (3,228 rows), `jev-answers.jsonl.gz` (5,583 rows), `jev-metadata.jsonl.gz` (3,523 rows); row counts are mine (jev/README.md:3-14). These cover the v1-era launches | no dates in names | 4 files, 816K | tracked | `tartar decide --jev`, `jev_metadata_ask.py` |

My own scan of `raw/` matches the README periods. Per file (first event to last event):

| File | Time span | Creates | Trades |
|---|---|---|---|
| 20261008-14 | 14:06:02–14:59:59 | 864 | 28,956 |
| 20261008-15 | 15:00–15:13:25 | 173 | 4,101 |
| 20261008-18 | 18:32:14–18:59:59 | 1,207 | 27,865 |
| 20261008-19 | 19:00–19:59:59 | 3,021 | 140,547 |
| 20261008-20 | 20:00–20:34:18 | 1,558 | 66,002 |
| 20261008-21 | 21:42:44–21:50:49 | 337 | 17,279 |
| 20261008-23 | 23:44:29–23:50:17 | 181 | 5,262 |
| 20261009-00 | 00:03:11–00:10:17 | 256 | 8,770 |
| 20261009-02 | 02:47:10–02:54:20 | 187 | 10,769 |
| 20261009-03 | 03:17:11–03:39:49 | 430 | 23,865 |
| **Total** | | **8,214** | **333,416** |

**Local-only `data/` (untracked, 75M):**

| Path | Contents |
|---|---|
| `data/raw/` (6 files, 38M) | The predictor session's original recorder output for 10-08 hours 14, 15, 18, 19, 20 and 21. Hours 14, 18 and 19 are byte-identical to the snapshot. Hours 15, 20 and 21 are uncompressed `.jsonl`. |
| `data/raw_slots/`, `data/raw_processed/`, `data/raw_swap/` | Byte-identical originals of `raw-slots`, `raw-slots-processed` and `raw-pumpswap`. |
| `data/raw_v3/` (3 files, 15M) | This container's live recorder: `tartar record --out data/raw_v3 --hours 20 --track-minutes 120 --pumpswap-hours 4`, started 12:55 UTC (STATUS.md:46; `data/logs/record-v3b.log`). It holds `20261009-06.jsonl` (an 06:25–06:31 run that died with ConnectionRefusedError, per `data/logs/record-v3.log`), `20261009-12.jsonl.gz`, and `20261009-13.jsonl`, which is still being written. **No copy exists in `handoff/`.** |
| `data/sol-dex/` | The same three untracked cost and decay files. |
| `data/models-real/` | The v0 1m model from 2026-10-08 18:44. Per `data/logs/train-real-1.log`: 786 tokens, 28,884 rows, 33 rounds, temperature 1.045, capture median 63%. |
| `data/ohlcv/1m/` | One token: the GeckoTerminal collector hit HTTP 429 (rate limiting) (candle-prediction-agent.md, §5 and §14). |
| `data/logs/` | 12 logs. |

`raw-eager` and `raw-clever` were recorded in other sessions' containers and exist here only as the snapshot.

### 3. Experiments (`handoff/experiments/`, 27 scripts plus `predictor-v3/`)
The README (`handoff/experiments/README.md:1-20`, last changed in commit 1811de3 at 2026-10-09 00:15) covers only the first 8 v1-era scripts. They are run from the repo root after copying the raw snapshot into `data/raw`, in this order:
1. `mkdir -p /tmp/tartar-exp`
2. `build_dataset.py`, which caches `/tmp/tartar-exp/ds60.pkl`
3. the scripts that take `ds60.pkl`

The README's rule: thresholds are chosen on validation launches and reported on test launches, and anything that looks profitable must be confirmed on later recordings. Every other script documents its usage in its own docstring.

| Script | Question it answers | How to run | Status / result |
|---|---|---|---|
| `build_dataset.py` | Builds the 60 s feature dataset from `data/raw` | `python3 handoff/experiments/build_dataset.py` | Prerequisite for §3.3–3.5 |
| `net_return_model.py` | Can LightGBM trained on net round-trip returns pick profitable rows? Also tests the v1 expected return as a signal | `... net_return_model.py /tmp/tartar-exp/ds60.pkl` | §3.3: no. The Huber model loses −3.0 to −3.9% per trade; the binary model's picks are noise (profitability.md:90-100) |
| `latency_sensitivity.py` | How do latency and fee change launch sniping? | `... latency_sensitivity.py ds60.pkl` | §3.4: +8.0% at 0 s latency (not achievable); −3.3% at 0.4 s (profitability.md:106) |
| `screen_launches.py` | Do scam flags and the `--next-launch` screen help as trade filters? (writes `screen_rows_20.pkl`) | `... screen_launches.py ds60.pkl 20` | §3.5: the screen passes 3.9% of launches and doesn't help; five flags mark worse trades |
| `screen_model.py` | Does a learned 20 s screen work? | `... screen_model.py ds60.pkl 20` | §3.5: nothing holds on test |
| `jev_calibration.py` | Do Jev's answers match outcomes? (needs `data/jev-answers.jsonl`) | `python3 handoff/experiments/jev_calibration.py` | §3.7: the direct "buy" answer is overconfident by about 2×; no edge |
| `jev_metadata_ask.py` | Fetches launch metadata and asks Jev (network, cached) | `python3 handoff/experiments/jev_metadata_ask.py` | §3.8. **Jev calls are now forbidden** (STATUS rules) |
| `jev_metadata_features.py` | Feature sets A–D: do Jev's metadata answers add value? | `python3 handoff/experiments/jev_metadata_features.py` | §3.8: test AUC falls 0.767 → 0.740 with Jev; no value |
| `slot_latency.py` | Latency in slots: same-slot buy share, notification delay | `... slot_latency.py data/raw_slots [--block-times 60]` (README:29 uses `handoff/data/raw-slots`) | 24% of first-minute buy SOL lands in the launch slot; notification delay median 1.47 s (1.15 s with "processed") (STATUS.md:93-104) |
| `slot_profit.py` | How fast must a launch buy land to profit? | `... slot_profit.py handoff/data/raw-slots [--size --fee --tip]` | §3.9: only a buy bundled into the creation slot profits (+6.8% at 10 s hold). Slot +1 first loses −5.3%. Launch buying is closed |
| `fee_sample.py` | pump.fun fee rates from TradeEvents | `... fee_sample.py [--tx 150]` | §3.9: 0.95% + 0.30% = 1.25% per side (212 trades) |
| `graduation_runup.py` | Buy the run-up to graduation on the curve | `... graduation_runup.py [dirs] [--latency 1.0]` | §3.10: +5.8% at first, which turned out to be two biases |
| `graduation_runup_replay.py` | The same, replayed through FastLoop on the full stream | `... graduation_runup_replay.py [dirs]` | §3.10: 75→80 SOL at +0.5% [−0.6, +1.6] (3 s, 10% haircut). Break-even, no edge |
| `established_collect.py` | Collect 5-minute OHLCV for liquid memecoin pools (GeckoTerminal) | `... established_collect.py [--out data/established] [--pages 10] [--history 2]` | Data for §3.11 |
| `established_rules.py` | Momentum, dip and breakout rules vs a survivorship-neutral baseline | `... established_rules.py [--dir data/established] [--fee 0.005] [--size 200]` | §3.11: dip excess +2.1% on the mixed universe (concentrated in 3 pools); memecoins +0.7% [−1.5, +2.9]. No reliable edge |
| `established_cohort.py` | Adds a cohort to the rolling dip pre-registration | `python3 handoff/experiments/established_cohort.py` (about daily; commit at once) | Only cohort-2026-10-09T0224 exists (12 pools) |
| `established_prereg_eval.py` | Scores the dip pre-registration | `... established_prereg_eval.py [handoff/preregistration/dip-rolling]` | Not yet run. Due at ≥ 200 trades or on 2026-10-30 |
| `sol_dex_costs.py` | On-chain SOL-USD round-trip cost and quote decay (for jevtrader) | `... sol_dex_costs.py sample\|summary\|decay\|decay-summary [--out ...]` | §3.12: about 0.5 bps per fill (quotes, not fills). US hours still open |
| `pumpswap_fees.py` | PumpSwap fee per side, from recorded swaps or over RPC | `... pumpswap_fees.py handoff/data/raw-pumpswap`, `--cohort FILE [--save ...]`, `--pools` | §3.13: 1.25% per side for fresh graduates, 1.20% to ~1,150 SOL market cap |
| `pumpswap_capture.py` | How many of a pool's swaps the recorder caught | `... pumpswap_capture.py RAW_DIR POOL[:SLOTS]` | 138 of 143 (96.5%) for one pool (README:61-62) |
| `pumpswap_study.py` | Do simple rules on graduated pools beat costs? (queue 11a) | `... pumpswap_study.py handoff/data/raw-eager handoff/data/raw-clever --show-test` (plus `--latency 3`, `--size 1`) | §3.16, pre-registered, run 12:05 UTC on 264 pools: **no edge**. Test −19.6 / −22.5 / −38.1 / −3.4% (grad / mom / dip / active); `preregistration/pumpswap-graduated/results/` |
| `long_holds.py` | Holds of 10–45 min on screened launches (queue 3) | `... long_holds.py [--latency 1] DIR...` | §3.14: test −12.5% [−17.6, −7.6] |
| `copytrade.py` | Copy wallets whose buys paid off | `... copytrade.py DIR...` or `--learn ... --apply ...` | §3.15: test −21.0% [−31.0, −10.5] |
| `scam_validation.py` | Do risk levels and flags predict a collapse? Trains P(rug), the probability a launch collapses | `... scam_validation.py DIR... [--screen 20] [--horizon 1800]` | Predictor doc §9: the old level reached AUC 0.57–0.59; reweighted 0.735; P(rug) 0.913 |
| `predictor_sweep.py` | Hyperparameter sweep for the global model | `... predictor_sweep.py RAW_DIRS [-t 1m] [--grid small\|full]` | §8.2.2b: 31 leaves / 1,500 rows per leaf gives test 0.4583 vs default 0.4629. Adopted as 31 / 2000 for v3 |
| `predictor_compare.py` | Installed model vs a candidate on the candidate's test tokens, with a 300-token live replay | `... predictor_compare.py TF CANDIDATE_DIR --raw DIRS [--installed DIR]` | §8.2.2c; outputs in `predictor-v3/compare-{15s,30s,60s,300s}.json` |
| `predictor_old_weight.py` | v3.1: weight given to the old recorder's training rows | `... predictor_old_weight.py SECONDS OUT_DIR 1,0.5,0.25,0.1,0` | §8.2.2c preview, nothing installed (see §5) |

`predictor-v3/` holds the test log loss comparisons, installed v2-era model → v3 candidate:

| Candle | Test log loss | Edge at the open |
|---|---|---|
| 15s | 0.2899 → 0.2835 | +2.5% → +3.7% |
| 30s | 0.3474 → 0.3386 | +4.4% → +5.6% |
| 60s | 0.4253 → 0.4129 | +6.7% → +9.1% |
| 300s | 1.1895 → 1.1418 | +5.1% → +6.9% |

Live replay edge, all candles: 15s 1.6% → 1.8%; 30s 4.5% → 4.4%; 1m 4.7% → 6.2%; 5m 4.6% → 6.5% (`candle-prediction-agent.md:458-461`).

Related records:
- `handoff/preregistration/` holds the dip-rolling SPEC, its fee addendum and `fees-measured.json`, plus the PumpSwap SPEC, RESULT and results.
- `handoff/live/` holds the fast-loop `policy.json` (paper only, rules scorer, `shadow_jev: true`) and two slow-loop reviews (20261009-0247, 20261009-0552).

### 4. What `handoff/code/` is
- It is a **snapshot copy of every source file**: README, pyproject, `tartar/` and `tests/`, 73 files, 784K. The repo itself is authoritative (`candle-prediction-agent.md:8-9, 958-961`).
- It was last updated in commit **0329d8e at 2026-10-09 04:55:16 UTC**, so it is behind `tartar/`. `diff -rq` shows:
  - 13 source files differ: agent, cli, dashboard, data/dataset, decide, fastloop, feeds/pumpswap, model/forecaster, model/volatility, output, scam, screen and train.
  - `tartar/rug.py` exists only in the repo.
  - `tests/test_rug.py` and `tests/test_pumpswap_model.py` exist only in the repo; `test_fastloop` and `test_scam` differ.
  - The snapshot's model metadata is **v2-era**, with no `.txt` model files:
    - 60s: 5,790 tokens, trained 00:53:55Z
    - 15s: 6,189 tokens, 01:16:42Z
    - 30s: 6,035 tokens, 01:12:56Z
    - 300s: 3,657 tokens, 01:14:25Z
  - The snapshot has no `rug-20s.*` files.
- In short, it does not contain P(rug), the v3 models, or the latest code from 05:00 onward.

### 5. Installed models (`tartar/models/`, 30M, all tracked)

| File | Candle | Launches | Train / valid rows | Trained (UTC) | Iterations | Temperature | Test log loss | `.txt` size |
|---|---|---|---|---|---|---|---|---|
| trades-15s | 15 s | 9,184 | 572,238 / 116,442 | 2026-10-09T06:54:01Z | 114 | 1.041 | 0.2835 | 10.2 MB |
| trades-30s | 30 s | 8,927 | 372,840 / 78,870 | 07:30:36Z | 97 | 1.047 | 0.3386 | 8.6 MB |
| trades-60s | 1 min | 8,560 | 260,790 / 57,660 (382k total rows with 63,480 test) | 06:27:59Z | 97 | 1.055 | 0.4129 | 8.4 MB |
| trades-300s | 5 min | 4,683 | 69,054 / 10,878 | 07:39:30Z | 87 | 1.175 | 1.1418 | 3.5 MB |
| rug-20s | P(rug) at 20 s | 5,267 | launches from 2026-10-08 14:06 to 2026-10-09 05:30 (my conversion of the metadata timestamps) | 2026-10-09T07:10:57 | 78 | Platt (0.861, −0.017) | 0.199; AUC 0.913 | 138 KB |

- The four `trades-*` models are **predictor v3**: LightGBM with 31 leaves and 2,000 minimum rows per leaf, 55 features, and 25 output classes ("no further move" plus 24 volatility-scaled bins).
  - The report files give data capture of median ~0.98–0.99 and mean ~0.91 on the training data.
  - They were installed in commit b47a328 at 07:52:39 UTC by the keep-better rule.
  - **How they were made** (`candle-prediction-agent.md:450-455`): `tartar train --raw <every curve recording> -t TF --num-leaves 31 --min-leaf 2000`, run on `handoff/data/raw`, `raw-slots`, `raw-slots-processed`, `raw-pumpswap` and `raw-eager`, then checked with `predictor_compare.py`.
- **P(rug)** was made with `tartar train --raw DIRS --rug` on the same five recordings (`candle-prediction-agent.md:648, 654-655`), commit 07e60c1 at 07:13:49.
  - Test set: the latest 791 launches, rug rate 9.5%, AUC 0.913, log loss 0.199.
  - It is shown to the user, not used to skip launches.
- **Not installed:**
  - The PumpSwap model (`tartar train --raw DIRS --pumpswap`; the code exists, `candle-prediction-agent.md:519-525`).
  - The OHLCV (candle-only) model (`tartar collect -t 1m && tartar train --ohlcv data/ohlcv/1m`).
  - v3.1.
- Model history:
  - v0: 786 tokens. A local copy is in `data/models-real`.
  - v1: 3,523 tokens, 1m only.
  - v2: 5,790 launches.
- **Known weakness: the 5m v3 model is overconfident on new launches.** At the open it states 70.6% and hits 60.9%. The cause is the old recorder's rows, which are ~75% of 5m training rows and have a different outcome mix (`candle-prediction-agent.md:468-494`).
  - A preview at 08:30 tried down-weighting those rows. On validation, weight 0 was best (log loss 1.0674). On test, weight 0.25 was best (1.0578) vs the installed model's 1.1081. Nothing was installed.
  - The v3.1 plan: train 15s, 30s and 1m on every recording at full weight, and choose the 5m old-row weight on validation (`candle-prediction-agent.md:495-516`).

### 6. Rebuilding the dataset and retraining (commands as the docs give them)
```bash
# raw snapshot -> training (handoff/data/README.md:6)
mkdir -p data/raw && cp handoff/data/raw/* data/raw/ && tartar train --raw data/raw
# several recorders, one timeline each (cli.py:136; candle-prediction-agent.md:353)
tartar train --raw A,B,C -t 15s|30s|1m|5m
# v3 settings (candle-prediction-agent.md:450)
tartar train --raw <every curve recording> -t TF --num-leaves 31 --min-leaf 2000
# train into scratch first, read the table, then copy trades-60s.{txt,json,report.json} into tartar/models/ (candle-prediction-agent.md:925-928)
tartar train --raw <snapshot> --out /tmp/m --force
# compare a candidate with the installed model on the same test tokens
python3 handoff/experiments/predictor_compare.py TIMEFRAME CANDIDATE_DIR --raw DIR[,DIR...] [--installed DIR]
# P(rug); PumpSwap model (after 11a)
tartar train --raw DIRS --rug
tartar train --raw <same dirs> --pumpswap        # STATUS.md:256
# Jev caches (offline only)
for f in metadata jev-answers jev-metadata; do gunzip -c handoff/data/jev/$f.jsonl.gz > data/$f.jsonl; done
# v1-era experiments and profit (experiments/README.md:7-15; profitability.md:650)
mkdir -p /tmp/tartar-exp && python3 handoff/experiments/build_dataset.py   # then the §3.3-3.8 scripts
cp handoff/data/raw/*.gz data/raw/ && tartar profit
# 11a evaluation (RESULT-2026-10-09.md)
python3 handoff/experiments/pumpswap_study.py handoff/data/raw-eager handoff/data/raw-clever --show-test
# new recording (STATUS.md 06:05 entry)
tartar record --out data/raw-<you> --pumpswap-hours 4
```
The model files store `trained_at`, `train_seconds`, row counts and hyperparameters, so a retrain can be checked against them. For example, the 15s model took 1,365.9 s to train.

### 7. Reproducibility caveats found
- **`handoff/data/raw` is no longer v1's exact training snapshot.** It now includes 20:06–20:34, 21:42–21:50 and the Jev fast-loop hours (README:8). Yet two docs still describe it as v1's snapshot: profitability §5 (`cp handoff/data/raw/*.gz` "the v1 snapshot", profitability.md:650) and the predictor doc header (line 9-10). The v1-era scripts (§3.2–3.8, all reporting 3,523 launches) would now read more data. No doc gives a command to cut the data at 20:06.
- The experiments README is out of date: it lists 8 of 27 scripts. Its scripts hardcode `data/raw` and `/tmp/tartar-exp`.
- Data from the old decoder (`raw`, `raw-slots*`, `raw-pumpswap`) shows quote-paired curves as creates with no trades. Filter on `create.vsol`. Jev-era results describe V1 launches only, and profitability.md:267 asks for a rerun "once V2 decoding lands". No rerun is recorded.
- **Docs say the predictor session's 04:33–05:33 SOL samples were lost or not committed** (README:75-76; profitability.md:458). In fact the three files sit untracked in `handoff/data/sol-dex/` in this container. Their line counts (120, 71, 178) match the §3.12 sample counts.
- jevtrader.md:34-36 cites a first window of 33 samples at 03:37–03:48. By my timestamp check, no file in `sol-dex/` covers that window.
- The README embargo on computing returns for the raw-eager and raw-clever PumpSwap pools (README:64-66, 83-84) was conditional on the 11a evaluation. That evaluation ran at 12:05 UTC (RESULT-2026-10-09.md). The profitability.md §1 table (line 24) still lists that family as "pre-registered, evaluated at ≥ 250 pools", while §3.16 reports the result: no edge.
- `jev_metadata_ask.py` needs network calls to Jev, which the user has forbidden. Only the cached answers in `handoff/data/jev/` may be used.

## Open items
- The three predictor-session SOL cost and decay sample files (costs-20261009-0433.jsonl, costs10k-20261009-0456.jsonl, decay-20261009-0433.jsonl) exist in handoff/data/sol-dex/ but are untracked because *.jsonl is git-ignored. They need 'git add -f' and a correction to the 'lost' notes in handoff/data/README.md:75-76 and profitability.md:458.
- data/raw_v3 (the recorder running here since 12:55 UTC, --pumpswap-hours 4 --track-minutes 120) is local-only. Finished hours need copying to handoff/data/ and committing before the container is lost; the 20261009-06.jsonl fragment is from a run that died at 06:31.
- Predictor v3.1 is not done: retrain 15s/30s/1m on every recording at full weight, choose the 5m old-row weight on validation from the grid 1, 0.5, 0.25, 0.1, 0 (predictor_old_weight.py) now that raw-clever covers hours 06-11, and check the 1m blend's global prior of 0.95, which is underconfident on new-style data (candle-prediction-agent.md:507-517).
- The PumpSwap model ('tartar train --raw <same dirs> --pumpswap') and a pumpswap-specific flat-candle prior are still to do. 11a has now been evaluated, so the precondition is met (STATUS.md:256-258).
- The OHLCV (candle-only) model is untrained because GeckoTerminal returns HTTP 429 from this container; data/ohlcv/1m has 1 token.
- The SOL-USD cost sampler at US hours (13-16 UTC) is still open (profitability.md:483).
- Dip-rolling pre-registration: add a cohort about daily (next due ~02:24 UTC 2026-10-10) and run 'pumpswap_fees.py --cohort <file> --save .../fees-measured.json'. Score with established_prereg_eval.py at >= 200 trades or on 2026-10-30.
- handoff/code/ is stale (snapshot from commit 0329d8e, 2026-10-09 04:55 UTC): it lacks rug.py, the v3/P(rug) model metadata, test_rug.py and test_pumpswap_model.py. It needs a refresh or a note that it is stale.
- Stale docs: handoff/experiments/README.md lists 8 of 27 scripts; profitability.md:650 and candle-prediction-agent.md:9-10 still call handoff/data/raw the exact v1 snapshot; profitability.md:24 still lists PumpSwap graduated tokens as awaiting evaluation; candle-prediction-agent.md:961 still names v1 as the installed model; the data README's 11a return embargo is still worded as pending.
- No documented way to recreate v1's exact training subset: no doc gives a command to cut handoff/data/raw at 20:06 UTC on 2026-10-08, so §3.2-3.8's 3,523-launch numbers are not directly reproducible from the current directory.
- §3.5-3.8 (screens, flags, Jev) describe V1 launches only, and profitability.md:267 asks for a rerun once V2 decoding lands. No rerun is recorded.
- No file in handoff/data/sol-dex covers the first SOL cost window (03:37-03:48 UTC, 33 samples) cited in jevtrader.md:34-36 (my check of the files' timestamps).
