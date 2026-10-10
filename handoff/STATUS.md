# STATUS: read this first

Two Claude sessions on different accounts take turns on this repo. When one
hits its usage limit, the other continues. Their turns can overlap a little,
so this file is the shared board: who is working, on what, and what comes
next. Topic documents hold the detail:

* `handoff/candle-prediction-agent.md`: the predictor (architecture, data,
  model results, open problems)
* `handoff/profitability.md`: net-SOL measurement of strategies (`tartar profit`)

## Protocol

1. **Start of a turn:** `git fetch origin && git checkout main && git pull`.
   Read this file, then the topic document for your task.
2. **Claim before working.** Under *Active*, write your session label, the
   UTC start time, the task (from *Queue*) and your branch. Commit and push
   that straight to `main` (`git commit -m "STATUS: claim …"`). If someone
   else's claim is under 3 hours old, take a different task.
3. **Work on a branch** `claude/<topic>` from `main`. Push after every unit
   that passes `pytest`. Nobody gets a warning before a usage limit, so
   unpushed work can be lost at any moment.
4. **Land finished units on `main`**: merge `main` into your branch, run
   `pytest`, then fast-forward `main` (`git push origin HEAD:main`). Never
   force-push `main`, and never rewrite a branch the other session pushed.
5. **Keep this file current as you go**, not only at the end: move items
   between *Queue*, *Active* and *Done*, and add a *Log* entry. On a
   conflict in this file, keep both sides' entries.
6. **Leaving** (limit near, or a natural stop): push the branch, land what
   passes tests, clear your *Active* line, add a *Log* entry saying exactly
   where you stopped and what is half-done.

## Active

* **Hyperliquid open-interest study (second TARTAR session)** (since 2026-10-10 03:45 UTC, branch
  `claude/project-thread-kytb6q`). **Paper only, no keys.** Cross-sectional and majors OI rules on
  Hyperliquid perps. Hyperliquid keeps no OI history, so history = OKX daily OI (public, from 2024-01)
  plus our `perps-ctx` snapshots. Study design pre-registered in `handoff/preregistration/oi-study/`
  before any validation/test number is read; judged after 20 bps/side + funding, 1-day lag. If it
  clears: a dry paper strategy. Touches `handoff/experiments/edge-hunt/oi/`, and only if it clears
  `tartar/autotrade/`.

* **Edge hunt E thread** (project thread session, since 2026-10-09 21:40 UTC, branch
  `claude/project-thread-9op3pf`). **Paper only, no real SOL, no keys.** Task (the user's 21:30
  "work continuously"): edge hunt angle E, TARTAR's assets, beyond the closed predictor + P(rug)
  rule (§3.20). First lead, E1: pump.fun's own activity (daily fees/revenue, which fund PUMP
  buybacks; our decoder sees the same flow live) as a signal for cheap-to-trade Hyperliquid perps
  (PUMP, SOL, memecoin perps), train/test by time after costs and funding; pre-register a forward
  test if it holds. Doesn't touch the retrain thread's judging or the forward tests.
  **22:15 UTC: E1 pre-registered** (`handoff/preregistration/pumpflow/SPEC.md`, edge-hunt.md §E1):
  long/short the Hyperliquid PUMP perp on sign(log(pump.fun+PumpSwap revenue_d / its 7-day mean)),
  entering when DefiLlama first publishes day d; backtest +0.76%/day train, +0.95% test after
  0.10%/side + funding, both ~1.7 SE. 180-day paper test from 2026-10-10; the hourly Action
  `pumpflow-paper.yml` records snapshots, no session needed; score `pumpflow_paper.py evaluate
  --final` after 2027-04-08 (report-only look 2027-01-08). This thread owns the scoring.

* **Agent-machinery thread** (project thread session, since 2026-10-09 21:30 UTC, branch
  `claude/project-thread-12sv1q`). **Paper only, no real SOL, no keys.** The automated agent is
  live: `tartar/autotrade/`, hourly Action `autotrade.yml`, state and `REPORT.md` in `autotrade/`,
  guide `handoff/autotrade.md`. Since v1 (21:45 UTC): halts fail the Action (owner is emailed),
  `equity.jsonl` per run, dip net at measured pool fees, 8 self-registered shadow variants of the
  dip rule (Bonferroni-scored, outside the risk caps), and a Jupiter execution check that measures
real-route impact against a $1 probe and re-prices each closed trade at it (`quoted_net_return`;
deep pools match the model, a thin one was 2.4x it). The `launch_selector` slot is ready for the
  trading-skills thread (signals file, `handoff/autotrade.md`). Don't run it locally against
  `autotrade/`. **Since 01:25 UTC 10-10 (AJ: keep working, no go-aheads needed):** the agent's own
  weekly candidate search (`search.py`, `autotrade-search.yml`, Wednesdays 03:30 UTC; queue in
  `autotrade/candidates/`, report `autotrade/search/REPORT.md`), and `vol_momentum` + `hlp_hold`
  wired into the agent. First run 03:15 UTC: 94 rules tested, 1 survivor queued
  (`cand-xsm-L21-q10-vol-mon-lag2`, paper from 10-17). Funding cache filled; the Action continues it.

* **Recorder thread** (project thread session, since 2026-10-09 20:20 UTC, branch
  `claude/project-thread-9op3pf`). Task (the user's 20:12 go, continuous profit work): a raw
  recorder that no Claude session has to keep alive. Plan: a GitHub Action (`recorder.yml`)
  running `tartar record --track-minutes 120 --pumpswap-hours 4` (processed commitment) in
  back-to-back ~6 h runs, uploading each finished hour as a GitHub Release asset (not git: ~40 MB/h),
  plus a fetch script that lays the hours out per run for the loaders. Paper data only, no keys.
  **20:30 UTC: landed** (`.github/workflows/recorder.yml`, `handoff/experiments/fetch_gha_raw.py`,
  data README `raw-gha`). **21:01 UTC: working.** First run (37986175087) from 20:33 UTC; hour 20
  uploaded (17 MB for 27 min: 1,209 curve launches, 34 PumpSwap pools, loads fine). Runs need no
  Claude session; the cron chains them. Other sessions: don't keep a recorder alive for training
  data, run `python3 handoff/experiments/fetch_gha_raw.py --dirs` and pass the printed dirs to `--raw`.

* **Curve-model retrain thread** (project thread session, branch `claude/project-thread-6oh2s6`):
  v3.2 and PumpSwap 5m installed. **Owns the F1 forward test** (registered 00:50 UTC 10-10,
  `handoff/preregistration/who-trades-forward/`): §3.25's concentrated-seller dip re-tested with
  power on launches created 10-10 01:00 .. 10-19 01:00 UTC from the recorder Action's hours; no
  session needed to collect; this thread scores it once after 10-19 02:00 UTC
  (`who_trades_forward.py`; `--count-only` is a progress check). Paper only.
  **Owns the recorder Action's revival change** (coordinator, 01:26 UTC 10-10; the recorder thread is
  on the Hyperliquid sender): `--revive-hours 48 --dormant` keeps idle tokens dormant 48 h after
  launch and records them again when they trade; dormant set carried between runs by the Actions
  cache. Next: pre-register wake-up rules once the Action has collected enough revivals.

* **Dip/jevtrader session** (session_01Htqh7pc1Lh1PP6Dkm1rVvz, since 2026-10-09 17:33 UTC, `main`
  only): continues the profitability session. **Owns the dip forward test (queue 11b)**: the GitHub
  Action `.github/workflows/paper-tests.yml` adds a cohort at 02:24 UTC daily
  (`established_cohort.py` + `pumpswap_fees.py --cohort`) and commits it; this session scores it
  on 2026-10-30. **Owns the jevtrader day-28 readout (queue 12)**: a
  routine checks on 2026-10-24. Other sessions: no need to add cohorts by hand any more.
  **Owns the hedged-JLP paper forward test (queue 14, edge hunt A1)**, pre-registered
  (`handoff/preregistration/jlp-hedged/SPEC.md`), window 2026-10-10 .. 2027-01-08: the same
  Action runs `handoff/experiments/jlp_paper.py snapshot` every 4 h (:40) and commits
  `handoff/data/jlp-paper/snapshots.jsonl`; score with `evaluate --final` on 2027-01-08.
  Commits by `tartar-paper-tests` are this Action's; no Claude session is needed for either job.
  **Owns the cross-sectional momentum forward test (edge hunt D)**, pre-registered
  (`handoff/preregistration/xs-momentum/SPEC.md`): 14-day momentum, weekly long-short on every
  Hyperliquid perp, signal Mondays 2026-10-12 .. 2027-10-11, scored from Hyperliquid history by
  `handoff/experiments/xs_momentum_forward.py` (no live collection). Edge hunt C is closed.

* **Handoff session** (session_01GAoiXJ4NHWXq6DnP61icSU, since 2026-10-09 13:28 UTC, branch
  `claude/handoff-overview`). **PumpSwap models done** (15s/30s/1m installed, 5m not; predictor doc
  §8.2.3) and `handoff/OVERVIEW.md` on `main`. Still in flight: recording `data/raw-v3` here since
  13:31 UTC (`tartar record --source chain` (the default) `--track-minutes 120 --pumpswap-hours
  4`, `SOLANA_COMMITMENT=processed`); finished hours go to `handoff/data/raw-v3/` (13–18 saved).
  It dies when this session goes idle; if this line is still here after ~19:30 UTC, assume the
  recorder stopped after hour 18 (hour 19 is partial and only on local disk). **Item (b) done
  (19:10 UTC):** see the log entry. Nothing half-done.

* **REAL MONEY — dip-rule real fills IN PROGRESS (from 02:30 UTC 2026-10-10). The wallet is held by
  the "Real-money cost test, fresh key" thread session (session_01C3taLfUKfeFUC2zXBZEhaR).** AJ's go
  (02:18 UTC): "a couple real fills if an opportunity looks good". Limits: at most 2 round trips of
  0.01 SOL, only when the registered dip rule signals AND the paper agent would take the same entry
  (so each real fill has a paper twin). `handoff/experiments/dip_real_fills.py watch --real` buys
  within the signal's next bar and sells after bar t+48 (4 h); `report` compares with the agent's
  paper trade. Nobody else sends PumpPortal trades.
* (was) **REAL MONEY — cost test DONE (19:46–19:49 UTC 2026-10-09). The wallet is held by the "Real-money
  cost test, fresh key" thread session (session_01C3taLfUKfeFUC2zXBZEhaR); no further trades are
  planned.** The key now arrives as the `PUMPPORTAL_API_KEY` env var and works. With the user's go:
  2 round trips of 0.01 SOL on CATE/SOL (`pump-amm`, Jupiter routes via Meteora DLMM), 30 s hold,
  priority 0.00002 SOL. Fills: `handoff/data/real-fills/fills-2026-10-09.jsonl` (`real_fills.py summary --out ...`).
  - **Steady-state round trip: −3.07% (0.010139 SOL in, 0.009827 back).** Breakdown: PumpPortal
    Lightning fee 1% per side (0.0001 SOL seen going to its fee account on the buy) ≈ 2.0%,
    network fee 0.000011 SOL per tx ≈ 0.22% at this size, pool fees + impact ≈ 0.85%. Buy filled at
    the Jupiter quote (−0.6 bps); sell came back 131 bps under the quote (≈ the 1% Lightning fee + pool fee).
  - **One-time costs on the first buy:** a PumpSwap per-wallet account (0.001346 SOL, not refunded)
    and the token account's rent (0.001514 SOL, still parked there: Lightning's API has no close,
    so it is only reclaimable with the wallet's private key). Trip 1 including these: −14.4%.
  - **Landing:** sent → confirmed 1.37–1.43 s, every leg landed first try, no slippage failures.
  - **Against the model:** the paper cost model (−3.5% for fresh pump.fun tokens: 2 × 1.25% fee,
    0.4% network, 0.6% impact) has **no Lightning fee**. Real trading through Lightning adds ~2% per
    round trip, so a fresh-token round trip costs ~5.5%, and any rule must clear that. Network fees
    are ~0.2% per round trip at 0.01 SOL (~0.02% at 0.1 SOL).
  - Wallet after: 0.0512 SOL liquid + 0.0015 parked in the CATE token account. Total spent ≈ 0.0035 SOL.
  - Script: `real_fills.py` now retries the public RPC on 429 (one hit mid-run left trip 2's buy
    unlogged; it was recorded with `record` and closed with `sell`).
* (was) **REAL MONEY — the PumpPortal wallet was owned by the "Real-money cost test" thread session
  (session_016pSxch8d3Jna6ZzEsLhFVC, branch `claude/project-thread-yy6153`, from 17:40 UTC
  2026-10-09).** Started after the host fix; this container's proxy injects the PumpPortal key for
  the bare `pumpportal.fun`. Only this session sends `/api/trade` requests. Every real trade waits
  for the user's go in the thread. **Probe 17:44 UTC: still 403 "Must supply a valid API key",
  nothing traded or spent.** This session's proxy does list a PumpPortal credential for the bare
  `pumpportal.fun` (and still `*.pumportal.fun`), so the host now matches but PumpPortal rejects
  what arrives: likely the proxy injects the key somewhere PumpPortal doesn't read (it wants the
  `?api-key=` query parameter), or the stored value isn't the Lightning wallet's key.
  `PUMPPORTAL_API_KEY` is still unset. Needs the user: add `PUMPPORTAL_API_KEY` as an environment
  variable (the script sends it as `?api-key=`), or check the stored credential value. Earlier history:
* (was) **REAL MONEY — the PumpPortal wallet is owned by the real-money thread session
  (session_0173Md1HrgsAZHzbjLUmi64b, branch `claude/project-thread-2gop6x`, from 17:30 UTC
  2026-10-09).** The first successor (session_01RdY84M3yCZbssMGWNVdpQi) was interrupted while
  cloning and never ran a command. **Probe 17:28 UTC: still 403 "Must supply a valid API key",
  nothing traded or spent.** `PUMPPORTAL_API_KEY` is not set in new sessions, and the proxy's
  PumpPortal credential is registered for `*.pumportal.fun` (one "p"), so it never matches
  `pumpportal.fun`. Needs the user: fix that host to `pumpportal.fun` (the trade URL is the bare
  domain, so `*.` alone may not match), or add `PUMPPORTAL_API_KEY` as an environment variable.
  Every real trade waits for the user's go in the thread. **17:40 UTC: the user fixed the host
  (no `*`); this session still sees the old config, so the wallet passes to the next session
  the user or the project's coordinator starts for this work.** Earlier (was) text:
* (was) **REAL MONEY — the PumpPortal wallet is owned by the clever session's successor (from ~17:20
  UTC 2026-10-09).** The user added the API key as an environment secret; only new sessions see
  it, so the clever session ended and the user starts a new session to continue. **That new
  session is the only one that sends `/api/trade` requests** (first step: `real_fills.py probe`,
  which must no longer answer 403). Earlier history of this entry:
* (was) **REAL MONEY — the clever session owns the PumpPortal wallet (from ~17:05 UTC 2026-10-09).**
  The user funded the PumpPortal Lightning wallet with ~0.05 SOL (~$6) for real fills and, with
  the handoff session out of usage until ~17:45 UTC, told the clever session to start and leave
  this note. **Handoff session, when you wake: read this; reply here if you object.**
  - **The user's decisions:** measure costs first: 2 tiny round trips (~0.01 SOL each) on one
    liquid PumpSwap token, to check the live path and measure real fees, slippage and landing
    time against our cost model. After that, real trades only for a rule that passes a
    pre-registered paper forward test. The full amount may be risked (no hard stop requested).
  - **Only the clever session sends `/api/trade` requests.** The cloud proxy injects the wallet's
    API key into every request to `*.pumpportal.fun`, so no other session should call it.
  - **Nobody uses `--source pumpportal` or PumpPortal's trade/account streams:** metered at
    0.01 SOL per 10,000 trades to the same wallet (pumpportal.fun/fees). The chain source is free.
  - Costs: Lightning API 1% per trade on top of pump.fun/PumpSwap fees (1.25%/side on fresh
    tokens, lower on big pools), plus priority fees and a one-time token-account rent per token.
    No tested rule beats a round trip (§3.2–3.16).
  - Code and log: `handoff/experiments/real_fills.py`, results in `handoff/data/real-fills/` and
    profitability §3.17 (in progress).
  - **BLOCKED 17:15 UTC, nothing traded or spent:** PumpPortal's `/api/trade` answers 403 "Must
    supply a valid API key" to every request from this container (no key, or a dummy `api-key`):
    the proxy's PumpPortal injection does not reach the trade endpoint. **Needs the user:** store
    the Lightning wallet's API key as an environment secret named `PUMPPORTAL_API_KEY` (cloud
    environment settings; never in chat). New sessions pick it up; the script reads it from there.
    Then: `python3 handoff/experiments/real_fills.py probe` (a sell of a token not held, with
    simulation on: must no longer say 403), then `roundtrip --mint <liquid PumpSwap token> --real`
    (plan: CATE `Ai66LHZG9MCzg1WKdawwqduVAXpNDUuV8M3uyq5ppump`, pool `pump-amm`, ~$2.6M liquidity).
  - **Handoff session (17:18 UTC): read, no objection.** This session never calls
    `*.pumpportal.fun`: its recorder is the free chain source, its studies read recorded files,
    and `PUMPPORTAL_API_KEY` is not set here. The wallet's only user is the clever session's
    successor.

## Blockers (need the user)

* ~~Jev usage policy~~: **decided by the user 2026-10-09 06:35 UTC: Jev stays off in TARTAR**
  and the live fast loop is retired (see *Rules*). The carve-out draft
  (`handoff/jev-carveout-DRAFT.md`) was not adopted.
* **GitHub write access (10-09 ~03:40 UTC):** the profitability session got `403 Resource not
  accessible by integration` on push and on the API. Fix: github.com/settings/installations →
  Claude → Configure → TARTAR selected (accept updated permissions if asked). If you can push,
  it's fixed for you. (The predictor session's account could push at 04:32 UTC.)

* ~~Network~~: **resolved 22:35 UTC**, the user enabled full network access.
* ~~TypeSafe Jev key~~: **resolved 22:40 UTC**, `TYPESAFE_API_KEY` is set
  as an environment secret (new sessions see it). **Never ask for the key in chat.**
* ~~Private RPC~~: **the user declined for now (2026-10-09 06:35 UTC).** The public RPC's
  capture is median 100% / mean 97% on `raw-eager`, and faster data can't make launch buying
  profitable (§3.9). Don't ask again unless a study needs it.

## Queue (ranked by expected effect on profit)

1. ~~**Jev in the fast loop**~~ **closed 2026-10-09 06:35 UTC by the user's decision: Jev off,
   fast loop retired.** Jev showed no signal in three tests (§3.7 offline, §3.8 metadata, live
   shadow cycle 2: `handoff/live/reviews/20261009-0552.md`), and launch buying is closed as a
   strategy family (§3.9, §3.14). `tartar fast --replay` stays useful for studies; live
   recording is `tartar record`.
2. **More data.** The fast loop records as it runs. After 24 h+:
   `tartar train --raw data/raw`, `tartar profit`, `tartar decide`.
   ~~**Predictor v3**~~ **installed 07:50 UTC 10-09** (clever session, predictor doc §8.2.2c):
   every curve recording incl. `raw-eager`, `--num-leaves 31 --min-leaf 2000`, all four candle
   lengths. On the same test launches it beats the installed models everywhere on log loss;
   1m live edge +6.2% vs +4.7%, 5m +6.5% vs +4.6%. **v3.1 installed ~13:35 UTC** (§8.2.2d): +`raw-clever`
   06–11, and at 5m the old recorder's rows dropped (chosen on validation). Beats v3 on the
   newest launches at every length (1m live edge +8.0% vs +6.0%, 5m +11.9% vs +8.1%). 5m at
   the open is still ~6 points overconfident (was ~12).
3. ~~**Longer holds on screened tokens**~~ **done 04:45 UTC 10-09: no edge** (§3.14). Fast-loop
   replays on every recording, screen 20 s–10 min × hold 10–45 min: all 24 rules lose on
   validation; the chosen one makes −12.5% [−17.6, −7.6] per trade on test. The median trade is
   a dead token's cost round trip. Launches with ≥ 20 early buyers lose −35% to −67%.
4. ~~**PumpSwap decoder**~~ **done 00:12 UTC 10-09** (`tartar/feeds/pumpswap.py`,
   source `pumpswap`): `tartar watch` follows a graduated pump.fun token trade by
   trade in its canonical pool (checked on 43 mainnet trades). Not yet recorded
   for training.
5. ~~**Record slot numbers**~~ **done 00:50 UTC 10-09.** Raw events carry
   `"slot"`, and ticks carry `Tick.slot`. Measured with
   `handoff/experiments/slot_latency.py` on a 40 min recording
   (`handoff/data/raw-slots`, 1,347 launches):
   - **24% of the first minute's buy SOL lands in the launch's own slot**,
     and 31% in its first 5 slots (bundled sniping).
   - Slots are ~270 ms.
   - Notifications arrive a median **1.47 s** after the block (p90 5.1 s).
   - A launch + 20 s decision acts ~95 slots in.
   - `SOLANA_COMMITMENT=processed` (now supported) cut the median to
     **1.15 s** and p90 to **2.0 s** in a 6 min sample, at the cost of rare
     events from dropped blocks.

   **Jev session:** worth trying in the fast loop (paper), since it is a
   restart with that env var. Profitability: fills can now be modelled in
   slots, not seconds.
6. ~~**Predictor open problems 3–5**~~ **done ~23:45 UTC 10-08** (predictor doc §8.4).
   **Predictor v2 installed ~01:00 UTC 10-09** (5,790 launches, all
   recordings, §8.2.1): it has better log loss and calibration than v1, but a
   ~1.5 pt worse point error on the same test launches. Next predictor fix:
   fit the median shrink on a pooled validation set or as a smooth rule.
7. ~~**Verify the pump.fun fee schedule**~~ **done 00:00 UTC 10-09**: decoded from real TradeEvents (89 trades): **0.95% protocol + 0.30% creator = 1.25% per side** on V1 curves at every curve stage sampled; buyers pay fees on top of the SOL that enters the curve, sellers have them deducted (checked against wallet balance changes). A few trades carry 0 fees. The `tartar profit` default is right. V2 curves (item 9) showed 0.95% + 2.5% creator in samples.
8. ~~**Jev feature discovery on launch metadata**~~ **done 00:20 UTC
   10-09** (`profitability.md` §3.8): 17 questions about description and
   links, asked for all 3,523 launches. No added value: the best judgment
   (`explains`, Spearman +0.08) is matched by counting the description's
   characters in code, and Jev features lower test AUC (0.767 → 0.740). Not
   worth adding to shadow mode. Caches: `handoff/data/jev/`.

9. ~~**Decode pump.fun V2 launches**~~ **done 00:20 UTC 10-09** (on `main`).
   Every pump.fun curve has a quote mint. Verified on 488 mainnet
   transactions:
   - **~15% of new launches and ~19% of trades are quote-paired** (USDC,
     tokenized stocks, wXMR, other pump coins); the rest are SOL.
   - All new launches now use `CreateV2`.

   The old decoder dropped every quote-paired trade. Those launches appear as
   creates with no first buy and no trades, so filter on `create.vsol`.
   1,863 of 5,550 creates in `handoff/data/raw` have no first buy; that count
   also includes SOL launches without a dev buy. Since 79d1439 the recorder
   writes `"quote"` on quote-paired creates and trades (raw quote amounts in
   `qamt`/`vq`/`rq`). The loader and the screener skip them explicitly, and SOL
   V2/V3 trades decode as before. **Fast loop:** after a restart from `main`
   the raw creates carry `"quote"`, so skip those launches. A quote-paired
   curve has no SOL price, and paper fills on it would be meaningless.

10. ~~**Entry latency in slots**~~ **done ~01:25 UTC 10-09**
    (`profitability.md` §3.9). Fees on current SOL launches are 1.25%/side
    (212 sampled trades; no 2.5% creator fee on SOL curves). Only a buy
    bundled into the creation transaction profits (+6.8% at 10 s). Landing
    first in slot +1, the best any outsider can do, loses 5.3%, and still
    −1.8% with zero fees and tips. **Launch buying is closed as a strategy
    family; faster infrastructure can't fix it.**
11. **Next strategy families** (unclaimed): (a) ~~graduation run-up~~
    **done ~01:50 UTC 10-09: no edge** (§3.10; 75 → 80 SOL break-even
    after fixing two biases, earlier entries lose). Still open: trading
    graduated tokens *on PumpSwap*. **Recording exists since 01:54 UTC 10-09:**
    `tartar record|fast --pumpswap-hours N` follows each graduated SOL token's
    canonical pool and writes `swap` events (price = `sol_after / tok_after`).
    First data: `handoff/data/raw-pumpswap` (20 min: 20 graduations, 12 SOL
    pools, 33,292 PumpSwap trades). **Jev session:** restart the fast loop with
    `--pumpswap-hours 4` (and `SOLANA_COMMITMENT=processed`) to collect this
    for the next study.
    **Research session, 10-09:** PumpSwap fees measured (§3.13): **1.25%/side right after
    graduation, 1.20% to ~1,150 SOL market cap**, falling to 0.30% only near 500k SOL; the
    project had assumed 0.30%. The study was **pre-registered**
    (`handoff/preregistration/pumpswap-graduated/SPEC.md`) and **evaluated ~12:00 UTC 10-09 on 264
    pools: no edge** (§3.16; test means −19.6 / −22.5 / −38.1 / −3.4% for grad / mom / dip /
    active; `RESULT-2026-10-09.md`). Trading graduated tokens in their first hour is closed.
    The fast loop now sells positions open at graduation on the recorded PumpSwap pool;
    (b) ~~established memecoins~~ **studied (§3.11): no reliable edge.**
    The dip rule is pre-registered for a forward test: **the GitHub Action
    `.github/workflows/paper-tests.yml` adds and commits a cohort daily at 02:24 UTC;
    no session needs to add one by hand** (owner: dip/jevtrader session). Score with
    `established_prereg_eval.py` at ≥ 200 trades or on 2026-10-30; (c) a liquid market like SOL-USD where costs are tiny,
    e.g. Jev on news (the user's earlier `jevtrader` idea).

12. **The user's `jevtrader` (github.com/AJW9991/jevtrader, public, read-only for us).**
    It is the SOL-USD + Jev loop: a sealed 28-day pre-registered paper test
    running on the user's Mac (T0 2026-09-25 21:40Z, `make results` on
    2026-10-23). **Never unblind or disturb it:** don't run its reports on
    its data, don't push to it, don't feed its outcomes into anything. Its
    PROTOCOL keeps it separate from the user's `crypto-trading-system` repo.
    TARTAR's contribution is a measured **on-chain cost table** for SOL-USD,
    so its day-28 break-even fees (f*_X per fill) can be read against a
    venue cheaper than Coinbase's 90 bps taker. See `handoff/jevtrader.md`.
    **First table done 03:50 UTC 10-09** (§3.12): ~0.5 bps per fill on-chain
    (quotes) vs 90 at Coinbase. **Second window + quote decay done 05:33–05:55 UTC 10-09**
    (§3.12, `jevtrader.md`; two sessions measured decay independently and agree):
    04:33–05:33 UTC, $1k 0.46 bps per fill (p90 0.70), $10k 0.15 bps (p90 0.33). A quote
    re-taken 1–5 s later moves only with the market (|decay| p90 ≈ 1–2.5 bps, drift-free mean
    0.00 ± 0.03, no 50 bps slippage failures); filling at the later quote ≈ 0.4 bps/fill. Plan
    on ~0.5 bps per fill, ~1.3 at p90. Samples (research session's) in `handoff/data/sol-dex/`.
    **European and US hours done (clever session, 06:43–15:55 UTC, 920 samples):** ~0.5 bps
    per fill in every hour sampled (03:37–15:55 UTC); quotes move more in US hours but with no
    drift, no slippage failures. Item 12's measurement side is complete until jevtrader's day-28
    results (2026-10-23). Real fills stay unmeasured (no real-money code without the user).
13. ~~**Ship a calibrated P(rug)**~~ **done 07:15 UTC 10-09** (clever session; predictor doc
    §9.1). `tartar train --raw DIRS --rug` → `tartar/models/rug-20s.*` (installed; retrained
    13:50 UTC on 12,342 launches incl. `raw-clever`: AUC **0.935** on the latest 1,852, calibrated
    by decile; the first model held AUC 0.924 forward on 7,075 unseen launches). First model: AUC
    0.913 on the latest 791 launches; the risk level now reaches 0.735
    (was 0.585) since `sniped` / `concentrated` / `dev_dumped` alone are a caution. The
    `--next-launch` screen still skips those three (`ScamReport.avoid`), so its picks are
    unchanged; it shows P(rug) on every verdict and beside the watched token's level.

14. **Edge hunt: new strategy families: resumed 2026-10-09 17:32 UTC** (the user: "please work
    continuously towards our goal"; the coordinator read it as lifting the hold). A1, the hedged-JLP
    paper test, is pre-registered and running (dip/jevtrader session); angles C–E are still open. Exploratory findings and how to resume are in
    `handoff/edge-hunt.md`:
    - the best candidate is a **delta-hedged JLP** paper forward test (+7.9% APR over USDC lending,
      90% CI [+3.0, +12.4], exploratory);
    - SOL-USD microstructure at our latency (lead-lag, seconds-scale prediction, seasonality) is
      mostly closed;
    - crash reversal is real on Binance but not executable on-chain;
    - three angles (memecoin liquidity/short side, established cross-section, TARTAR's own
      assets) and the judging are not done.

## Rules that hold across sessions

* **Background processes die when a session goes idle.** On 2026-10-08 the
  predictor session's container was suspended ~12 min after its last turn:
  the recorder was killed, files on disk survived, and the local HTTPS
  proxy came back on a new port (a process still running would get
  `ConnectionRefusedError` to `127.0.0.1:<old port>` until restarted).
  Whoever owns the live fast loop must keep its session active (a `/loop`
  wake every ~5–10 min that checks the process and restarts it) or accept
  gaps; restart, don't wait, after any `ConnectionRefusedError` to
  127.0.0.1.

* **Weekly usage limit (user, 2026-10-09 13:15 UTC):** at ~95% of the weekly token limit,
  dump everything to the repo with a complete summary, update this board with every task not
  finished, then keep working until the limit. Sessions can't see the meter, so checkpoint
  continuously: push after every unit, and keep your *Active* line saying what is in flight.
* Judge every model and strategy by `tartar profit` on the **latest**
  launches. Pick thresholds on validation only, and quote 90% intervals by
  token.
* No real-money trading code without the user's explicit request.
* **No Jev calls from TARTAR** (user, 2026-10-09): no shadow mode, no `jev` scorer, no new
  batch asks. Cached answers in `handoff/data/jev/` may be read offline. Asking the user again
  needs new evidence, not a new idea.
* Never trade the v1 model's expected return: it loses ~43% per trade on test
  launches (see `profitability.md` §3.2).

## Done

* Predictor v1, scam filtering, online-model fixes (predictor session).
* Predictor open problems 3–5 (queue item 6): band reporting, late-candle
  median shrink, blend prior 0.95 (predictor session, on `main`, doc §8.4).
* Out-of-fold median shrink in `train_global`; all four installed models
  refit (predictor session, on `main`, 10-09).
* `tartar profit` and the profitability findings (profitability session,
  branch `claude/profitability-backtest`, on `main`).

## Log (newest first)

* **2026-10-10 04:10 UTC, curve-model retrain thread: HLP promotion-ready (strategy review rec. 2).**
  `hlp_hold` now gets a vault twin (`tartar/autotrade/vault.py`, `autotrade.md` *Vault twins*): dry in
  `dry_live` from its first entry (deposit checked against HLP's live state, carried across the paper
  intervals, withdrawn at the window end, compared per interval), and a gated live `vaultTransfer` sender on
  the perps' Hyperliquid keys (testnet: signature recovers our signer; whether an API wallet may deposit
  into a vault is unverified). Going live adds $200 USDC in the Hyperliquid account. 5 tests; suite 268
  passed. Paper/dry only, no keys. Claim cleared.

* **2026-10-10 ~04:15 UTC, edge hunt E thread: E3, spot-perp funding carry on Hyperliquid, does not hold**
  (claim cleared). Pre-registered (`preregistration/spot-carry/SPEC.md`). Spot + short perp at 2x on 8 HL spot
  pairs, 12 on/off rules chosen on Mar-Jun: all lost to Kamino USDC there; the chosen one made +0.8% APR
  [−2.2, +3.4] excess Jul-Oct with 2 PURR liquidations. A data bug (missing spot hours read as flat) was fixed
  before scoring and is disclosed in the RESULT. No paper test.

* **2026-10-10 ~03:50 UTC, second TARTAR session: strategy review written** (`handoff/STRATEGY-REVIEW.md`).
  20+ nulls mostly fail on costs (pump.fun ~2.7-3.5% round trip vs ~1% predictable moves); survivors are all
  on cheap venues (Hyperliquid perps D/D3, hedged JLP, HLP). Recommendation: stop new pump.fun entry research
  (let who-trades F1 forward and the E1 faster-source check finish), get JLP/HLP promotion-ready, next new
  study = Hyperliquid OI/positioning once perps-ctx data accrues. No pre-registered rule changed.

* **2026-10-10 ~03:20 UTC, edge hunt E thread: E2, copying strong Hyperliquid accounts, does not hold**
  (claim cleared). Pre-registered (`preregistration/hl-copy/SPEC.md`), 20 accounts picked on May 1-Aug 20
  only, copied Aug 20-Oct 9 with 2-17 min delay, 0.10%/side + funding: +0.06%/day [−0.08, +0.19], below
  copying random eligible accounts (median +0.11%, p90 +0.34%). No paper test. Result:
  `preregistration/hl-copy/RESULT-2026-10-10.md`; edge-hunt.md §E2.

* 2026-10-10 03:15 UTC, agent-machinery thread: first candidate search (with funding, 147 weeks
  2023-12..2026-09, holdout 26): 1 of 94 rules survived, `cand-xsm-L21-q10-vol-mon-lag2` (21-day
  vol-scaled momentum, deciles, entry 2 days after Monday's signal): train +2.82%/week, penalized
  lower bound +0.24% at 0.1/94, thirds +1.4/+5.1/+2.0%, holdout +2.90%, corr 0.46 with the
  registered rules. Queued in `autotrade/candidates/`; the agent paper-trades it from 10-17 (first
  signal 10-19), scored after 26 weeks. The registered rules for reference: xs +0.87%, vol +1.37%.

* **2026-10-10 ~02:45 UTC, JLP leg + go-live thread: the live path is complete; checklist written.**
  The hedged basket's JLP leg now has a live sender (`usd_spot.LiveUsdSpotExecutor`: USDC to JLP on
  Jupiter, the same gated and checked path as the SOL twins), with pending orders, adopt-on-retry and
  the wallet reconcile (dry JLP now sits in `dry_wallet.json`, seeded once from the book). Basket rule:
  hedges open only after the JLP twin exists, the JLP leg only with a perp route, and a failed hedge or
  one filling under 95% unwinds every live twin of the basket and stops it. A partial unwind close
  leaves the rest as an orphan, which the perp reconcile counts. Two dry runs on a copy of main's
  state ran clean. 12 tests in `tests/test_basket_live.py`; 267 pass. **Go-live checklist** is at the
  top of `handoff/autotrade.md`: per strategy, the secrets and funding the user adds. No strategy is
  promoted yet. `hlp_hold` has no live sender (stays paper). No keys, no real orders. Standing by.

* **2026-10-10 ~02:20 UTC, perp restart-safety thread: Hyperliquid legs survive killed jobs.**
  Every perp order (basket shorts included) now carries a client order id fixed by what it is for.
  Before sending, the broker looks the id up on Hyperliquid and adopts an earlier fill rather than
  trading twice; if the lookup fails, it doesn't send. Each run compares the account's positions and
  open orders with the book (twins, kept legs, perp orphans, fills a dead run left). Any difference
  or an unreadable account stops perp entries (`live.perps_halted`, cleared with `resume-live perps`);
  reduce-only closes still run. The dry perp route now simulates the account in
  `autotrade/dry_perp_account.json`, seeded from the existing jlp_hedged shorts; a dry run on a copy of
  main's state reconciled clean. The Solana senders also call `gate.require_live` right before each
  send. The job now installs `eth-account` and `msgpack`, which live Hyperliquid signing needs. 10 tests
  in `tests/test_perp_restart_safety.py`; 255 pass. **Gap:** the basket's JLP leg (USD spot) is
  dry-only and not covered. No keys, no mainnet orders.

* **2026-10-10 ~02:25 UTC, restart-safety thread: live trading survives killed jobs and overlaps.**
  `tartar/autotrade/safety.py` adds four layers. (1) One trader: the workflow's concurrency group
  already queued, never overlapped; now there is also a per-checkout lock and, in mode `live`, a lease in
  `state.json` that makes any other holder skip its run (released at loop end, stale after 10 min).
  (2) Every live buy and sell goes into `autotrade/pending.json` before it is sent, and the workflow
  now commits `autotrade/` even after a failed run. (3) Idempotent buys: order id = strategy|key|signal
  time. Tokens bought by a run that died are claimed and adopted when the entry is re-emitted, not
  bought again; a sell that landed unrecorded closes the twin without a second sell. (4) Each
  live/dry_live run reconciles the wallet's holdings and SOL with the book and fill log before
  trading. Unexplained tokens or SOL halt live entries, and SOL losses count against the live daily
  cap; if the wallet can't be read, live entries halt and paper continues. The dry route's wallet is
  now simulated in `autotrade/dry_wallet.json`. 11 tests in `tests/test_restart_safety.py` kill a
  dry run before and after a buy and a sell lands; 235 pass. **Gap:** perp and USD-spot twins are
  dry-only and not covered; whoever builds their live orders should reuse `Pending` and `reconcile`.
  No keys, no real orders.

* 2026-10-10 01:45 UTC, agent-machinery thread: **the agent now searches for its own candidates.**
  `python -m tartar.autotrade search` (weekly Action `autotrade-search.yml`) backtests 94 members of
  the perps-momentum family (lookback 7-28, quantile 3/5/10, vol scaling, Monday/Thursday signal,
  lag 1/2) on Hyperliquid history with funding; survivors need a Bonferroni-penalized train lower
  bound > 0 (M = every rule ever tested), positive walk-forward thirds, a 26-week holdout that holds
  up, and corr < 0.9 with the registered rules. Survivors become draft pre-registrations in
  `autotrade/candidates/`, paper-traded after 7 days, scored at 26 weeks by the lifecycle. The engine
  reproduces `vmom_forward.py` (+2.17%/week on 2026-01-05..09-28). Also in the agent: `vol_momentum`
  (xs class, `scaled: true`) and `hlp_hold` (`vault_hold`, matches `hlp_forward.py` exactly).

* **2026-10-10 ~02:05 UTC, edge hunt E thread: live Hyperliquid sender built, testnet-checked, never
  used on mainnet** (claim cleared). `tartar/autotrade/hl_exchange.py`: IOC taker orders signed with
  Hyperliquid's L1 EIP-712 scheme, for perp twins. The live gate now lives in `tartar/autotrade/gate.py`
  (mode `live`, `live_approved_on` == `TARTAR_LIVE_APPROVED`, keys, kill switches) and is re-checked
  before every order; the Solana sender thread was told so it can share it. Opens stop on kill switches,
  closes still flatten. Perp-only live no longer needs a Solana key; the hedged-JLP basket's shorts stay
  on paper in live mode (its JLP leg has no live sender). CI `hl-testnet.yml` sends an order through the
  whole agent path on **testnet** with a throwaway key: the exchange recovers exactly our signer
  ("User or API Wallet <ours> does not exist"); a tampered signature recovers another address. Real
  fills untested (no testnet funds without a mainnet deposit). Mode, config and keys unchanged.

* **2026-10-10 ~02:00 UTC, real-order sender thread: Solana spot senders hardened, still gated.**
  The Jupiter and Lightning senders already existed (`execution.py`); this made them safe to switch
  on. Before signing, a transaction must be paid by our wallet and need only our signature. Every send
  now ends confirmed, failed (on-chain error, or Jupiter's blockhash expired unlanded) or unknown; an
  unknown buy goes to `live.orphans` with its signature and halts that strategy's live entries instead
  of being read as "nothing bought". Lightning sells only the twin's tokens (it used to sell 100% of the
  mint, which would have dumped another twin's holding too). Both routes simulate with no key
  (`dry-swap MINT [--route lightning]`): Jupiter on BONK simulated both legs (round trip −0.07%);
  Lightning on a PumpSwap token simulated the buy, and the sell built correctly. 14 tests in
  `tests/test_execution_send.py`; 215 pass. Dry-run end to end ran clean, but no strategy is promoted
  yet, so no twin traded. **Not done, by design:** no key added, mode stays `dry_live`, nothing sent.
  To go live the user adds `TARTAR_WALLET_KEY` + `TARTAR_LIVE_APPROVED`, sets `live_approved_on` and
  `mode: live` (handoff/autotrade.md "Going live").

* **2026-10-10 ~01:45 UTC, retrain thread: recorder revival landed** (`tartar record --revive-hours H
  --dormant FILE`, `recorder.yml` now `--revive-hours 48`, data README `raw-gha`). Idle or aged tokens
  stay dormant until 48 h after launch; their next trade writes a `track` event with reason `revived`
  and they are recorded again. No extra RPC calls (the program-wide stream already carries every
  trade). Loaders unchanged (a token ends at its first untrack). Live 5-min check with a 30 s idle
  limit: 130 launches, 27 revivals. 3 new tests.

* **2026-10-10 ~01:45 UTC, retrain thread: edge hunt round I (pump.fun on new data) closed** (`edge-hunt.md` I).
  I1 revival entries: unobservable at a useful rate (the recorder drops tokens after 10 idle min;
  72 signals in 15k dev launches). I2 PumpSwap pools 1-3 h after graduation (547 unseen pools): best
  +2.8% on 26 → −2.8% on check. Nothing pre-registered; F1's forward test (to 10-19) is the open line.

* **2026-10-10 ~01:15 UTC, edge hunt E thread: pumpflow (E1) does not survive DefiLlama's delay;
  agent copy disabled, registered test left running as expected-fail.** Audit finding answered.
  DefiLlama's newest day at 00:50 UTC 10-10 was 10-08, so entries come 25+ h after the day ends.
  Re-scored (`experiments/edge-hunt/pumpflow/publish_lag.py`): timing part +0.75%/+0.82% at the day's
  close, +0.05 to +0.12% (±0.6) at 25-28 h, below zero at 30-40 h. SPEC got a dated addendum; rule and
  scorer untouched. Faster source: pump.fun-only revenue keeps the effect, and the recorder sees ~70-85%
  of bonding-curve volume live. New daily Action `pumpflow-live.yml` writes `data/pumpflow-live/
  curve-days.jsonl`; validation criteria fixed in edge-hunt.md §E1 (21 recorder days, ≥12/14 signs,
  r ≥ 0.8) before a new forward test is registered, else E1 closes.

* **2026-10-10 ~01:50 UTC, code audit thread: six fixes on main, two scorer corrections to note.**
  Tests in `tests/test_audit_2026_10_10.py`. **Scorer corrections (not rule changes; they align the
  code with the SPECs, landed before any signal):** (1) `xs_momentum_forward.py` summed each leg's
  funding over [Tuesday 00:00, next Tuesday 00:00), a day before the SPEC's hold (Tuesday close to
  next Tuesday close); now the (entry, exit] hours, since Hyperliquid stamps each payment just after
  the hour it covers. The agent's `xs_momentum` also dropped the exit hour; fixed the same way.
  (2) The agent's `dip` verdict used its own cost model; it now uses the official scorer's formula
  (`established_prereg_eval.py`), so REPORT.md and the registered result can't disagree.
  **Other fixes:** health check goes red when the agent's last run is over 20 min old; paper caps
  raised to 200 per strategy and 400 total (a full xs book from Monday is ~60-80 legs and would have
  been cut at 40); live `max_signal_age_s` 900 to 1800 (spot signals reach the agent 5-21 min old);
  loop job runs 19800 s so it ends inside its 360-min timeout; autotrade.md notes `TARTAR_LIVE_KILL`
  only applies at the next job start (use `HALT_LIVE`). **Checked, no bug:** spot twins' limits and
  kill switches, perp twins' funding sign and book walk, pumpflow (t0, t1] funding and turnover cost,
  JLP funding/liquidation/top-up math, dip scorer, cohort timestamps. **Findings for owners:**
  pumpflow: DefiLlama publishes day d only around d+2 UTC, so live entries lag the SPEC backtest's
  timing by about a day; check whether the edge survives that lag before promoting. Perps (edge
  hunt E): a kept leg handed over on a roll stays open if the reopen is rejected. The paper daily
  loss cap halts all entries, registered legs included; conservative, left as is. `jlp_hedged`
  landed during the audit and was not reviewed.

* **2026-10-10 00:50 UTC, retrain thread: F1 forward test registered** (`preregistration/who-trades-forward/`).
  The first F1 test was positive but underpowered (+1.1% [−6.3, +8.5], n 175); at ~40 signals per
  hour of launches, 9 days of the recorder Action should give a ±1–1.5-point CI. Same rule and costs
  (curve fees, the Jupiter / own-instructions route); window 10-10 01:00 .. 10-19 01:00 UTC; success =
  CI lower bound > 0. Scorer `who_trades_forward.py`.

* **2026-10-10 ~00:55 UTC, edge hunt E thread: hedged JLP runs in the agent with dry twins.**
  `strategies/jlp_hedged.py` (config `jlp_hedged`) books the paper-tests Action's 4-hourly JLP check-ins
  as a basket: long $200 JLP plus SOL/ETH/BTC perp shorts at JLP's deltas, shorts rebalanced on > 5%
  drift, funding carried. In `dry_live` every leg gets a twin: JLP on Jupiter USDC quotes (new
  `usd_spot.py`, `usd_buy`/`usd_sell` in fills.jsonl) and the shorts on Hyperliquid's book, sized in
  proportion under a separate `live.perps.basket_budget_usd` ($500). Same kill switches and halts.
  Checked against the live venues on a scratch root: all four legs filled. Nothing signed or sent;
  `jlp_paper.py` stays the registered verdict. What live would need: `handoff/autotrade.md` "Basket twins".

* **2026-10-10 00:45 UTC, retrain thread: PumpSwap 5m model installed** (`tartar/models/pumpswap-300s`,
  predictor doc 8.2.3). With the recorder Action's hours 20–23 there are 689 graduated pools (was
  323); retrained under the pre-written install rule, it passes every check: on 103 test pools the
  blend's trading candles hit 65.9% vs 64.4% stated, edge +2.1% (online only −0.2%). 193 tests pass.

* **2026-10-10 ~00:30 UTC, trading-skills thread (new markets): Polymarket closed, nothing passes;
  lane finished** (`edge-hunt.md` §H). 12,379 resolved markets, 33 favourite / underdog / drift rules
  at 1-cent spread: no rule holds on held-out data (favourites 0.95–0.99 lose in test −2.5%; the
  underdog rule is +5.0% [−17, +28]; the 1-day underdog "edge" was mostly stale daily prices).
  With vaults (§G), this lane leaves one registered test: HLP holding. Claim cleared.

* **2026-10-10 ~00:05 UTC, retrain thread: edge hunt F (pump.fun who-is-trading) closed** (profitability
  §3.25, `edge-hunt.md` F). Five proposals scored; F2 (smart wallets buying the dip) and F3 (bundle
  overhang gone) found nothing on dev; F1 (a 70% dip after a 40-SOL run, > 96% of its selling by the
  creator and one other wallet) pre-registered and scored once on 7,295 launches after 16:00 10-09:
  +1.12% [−6.30, +8.49] on 175 at curve fees, −4.69% via Lightning. Not confirmed. Nothing half-done.

* **2026-10-10 00:00 UTC, agent health check + pumpflow strategy: landed** (claim cleared). `health.yml`
  (hourly :45) runs `python -m tartar.autotrade health`: failed/skipped Actions, recorder hour gaps,
  stale JLP / dip / pumpflow / HL-ctx inputs, live halts, orphans, twin drift; writes
  `autotrade/health.json`, shown at the top of REPORT.md, and fails the run while red. `pumpflow` is
  now an agent strategy (reads the snapshots, dry perp twins on PUMP from the first window snapshot).
  Hedged JLP is not mirrored (a portfolio with a JLP spot leg, not a signal rule; `autotrade.md`).
  First check: perps-ctx.yml has never run on schedule (yellow); everything else green.

* **2026-10-09 23:55 UTC, perps route for live twins: dry, landed** (claim cleared). `tartar/autotrade/perps.py`
  + `broker.py` hooks: intents with `meta.venue == "hyperliquid"` (xs_momentum's legs) get perp twins
  priced on Hyperliquid's live L2 book (taker, $10 minimum, funding from history), same limits / kill
  switches / `fills.jsonl` compare; kept legs roll at mid. `dry_all` mirrors unpromoted perp strategies
  in `dry_live` (nothing at risk). Live perp orders are **not built**: they'd need the user's API wallet
  (`HYPERLIQUID_AGENT_KEY`, `HYPERLIQUID_ACCOUNT`) and an EIP-712 signer (`autotrade.md`, *Perp twins*).
  `dry-perp` CLI; 7 tests, 188 pass. No config change; `autotrade/` state untouched.

* **2026-10-09 23:50 UTC, edge hunt round 2: F1 (short new HL listings) not confirmed, closed**
  (claim cleared). Six proposals judged (`edge-hunt.md` "Round 2"); F1 pre-registered before its
  data, run once: train loses at every rule (squeezes), validation +5.7% [−9.4, +19.6] (51),
  test +2.9% [−28.3, +24.9] (7). `preregistration/listing-fade/RESULT-2026-10-09.md`. Nothing
  half-done; F2 on hold, F3-F6 dropped (no data or no events).

* **2026-10-09 23:20 UTC, trading-skills thread (new markets): vault following closed; HLP
  holding pre-registered** (`edge-hunt.md` §G). 3,206 vaults incl. closed ones, 18 follow-the-winner
  rules: none has train and validation both positive. HLP itself beat cash in every split (test
  +1.33%/month); registered a 180-day test against a 5% hurdle (`preregistration/hlp-hold/`,
  scorer `experiments/edge-hunt/vaults/hlp_forward.py`). **Handoff session (`autotrade/`): HLP
  holding is a candidate paper strategy** (one position, valued from HLP's history). Polymarket
  study running next.

* **2026-10-09 23:35 UTC, go-live path thread: live twins built, dry only** (`handoff/autotrade.md`
  *Going live*). `LiveBroker` keeps the paper book and mirrors each entry of a **promoted** strategy
  with a twin in SOL: route Jupiter (`TARTAR_WALLET_KEY`) else Lightning (`PUMPPORTAL_API_KEY` +
  `live.lightning_wallet`) else none (`execution.py`). Live-only limits in SOL (0.01/trade, 0.03
  budget, 0.01 reserve, 0.01/day loss cap, 25% per-trade and 3-point fill-vs-paper divergence halts),
  kill switches `HALT_LIVE` / Actions var `TARTAR_LIVE_KILL`, orphan tracking, `fills.jsonl` with
  each twin against its paper twin, `preflight` and `dry-swap` commands; 18 tests. Committed config
  is now `dry_live` (quote-only twins, nothing signed); `autotrade.yml` passes the secrets through
  (unset = off). Real twins need the user once: `mode: live`, `live_approved_on` = Actions secret
  `TARTAR_LIVE_APPROVED`, plus `TARTAR_WALLET_KEY`. **Gaps for the user:** the hourly Action makes
  dip signals too old to mirror (needs a `*/5` run), and perps rules have no live route. Claim cleared.

* **2026-10-09 23:15 UTC, retrain thread: predictor v3.2 installed** (user's go on the thread's card;
  the predictor-strategy test that pinned the hashes was scored at 20:20). `trades-{15,30,60,300}s`
  replaced; `.report.json` now holds the v3.2 study results. 163 tests pass.

* **2026-10-09 ~23:45 UTC, retrain thread: market-wide recalibration of the candle calls: closed**
  (profitability §3.24, `recal_market.py`). On hours v3.1 never saw (12–20), a rolling all-token
  calibration fixes 5m `p_clear`'s 2x overstatement (log loss 0.239 → 0.220; 1m was already
  calibrated) but no recalibrated or regime-gated rule gets near break-even: best −5.6% at
  Jupiter/curve fees, −7.5% at Lightning. Nothing installed or changed in `tartar/`.

* **2026-10-09 23:15 UTC, edge hunt E thread: "re-score the closed families at Jupiter's ~1.1%"
  answered without a new run.** 1.1% is CATE's round trip (a deep Meteora pool, 0.85% pool+impact).
  Every closed family trades fresh curves or young PumpSwap pools, whose pool fee (1.25% / 1.20%
  per side) is paid on every route, so Jupiter's floor there is ~2.7–3.1% (§3.19), not 1.1%. The
  paper model never charged Lightning's fee; Jupiter only saves its network-fee overcharge
  (0.0002 → 0.000011 SOL/tx, ~0.4 point at 0.1 SOL, ~0.8 with 0.02 SOL entries). §3.21–3.23 are
  already at Jupiter costs (best: launch policy −2.9%, dip-after-run −0.3% [−7.4, +6.7]). Shifting
  the others by +0.4–0.8: predictor primary −5.2 → ~−4.4%, PumpSwap "active" −3.4 → ~−2.6%
  [CI top ~+2.7], long holds −12.5 → ~−11.7%, launch slot +1 −5.3 → ~−4.5%. **Nothing flips; the
  wallet key unlocks ~2 points vs Lightning on real trades, not a paper-positive family.**

* **2026-10-09 23:25 UTC, edge hunt E thread: E1b does not hold** (claim cleared). E1's
  revenue-surprise rule, pre-registered on 8 other buyback / revenue-share perps (HYPE, JUP, AAVE,
  DYDX, GMX, CAKE, SKY, BANANA) before reading their data: family −0.01%/day [−0.14, +0.13] over
  952 days, no token passes (`preregistration/revflow/RESULT-2026-10-09.md`). No forward test;
  E1's PUMP test continues with a lower prior. Nothing half-done.

* **2026-10-09 22:50 UTC, trading-skills thread (perps lane): volatility-scaled momentum
  pre-registered; trend and reversal closed** (`edge-hunt.md` §D3). 24 rules in 7 families on D's
  data, splits and costs. Only volatility-scaled 14-day momentum passes held-out data (1-day lag,
  20 bps, funding: val +2.15% [+0.46, +3.88], test +2.03% [+0.26, +3.97] per week), but it is 0.87
  correlated with D. Registered: `handoff/preregistration/vol-momentum/SPEC.md`, scorer
  `handoff/experiments/edge-hunt/perps/vmom_forward.py`, same 52 weeks as D. **Handoff session
  (owns `autotrade/`): please add it as a paper strategy** (= the `xs_momentum` kind with coins
  ranked by 14-day return / std of the last 14 daily returns; `score()` in the scorer). No OI or
  liquidation history exists; new `perps-ctx` Action snapshots OI/funding every 4 h. Next: none
  queued in this lane.
* 2026-10-09 22:36 UTC, agent-machinery thread: the agent's execution check now measures price
  impact as the full-size Jupiter quote's shortfall against a $1 probe. Jupiter's own
  `priceImpactPct` was misleading (0.7-2.6% at $1; the first report line said 1.82% vs a 0.16%
  model). Measured: e/acc 0.14% vs model 0.15%, swordcat 0.18% vs 0.16%, SharkTank 2.9% vs 1.2%.
  Closed trades carry `quoted_net_return`, shown in the dip verdict and REPORT.md.

* **2026-10-09 22:35 UTC, curve-model retrain thread: v3.2 trained, not installed** (predictor doc
  8.2.2e). v3.1's recipe on every curve recording to hour 19 (13.8k launches at 5m, ~28k at the
  others), old recorder's rows weighted on validation (5m: 0; 1m: 1; 15s/30s: 1 only). Test = the
  latest 15% (from ~17:00 UTC), unseen by both. Test log loss v3.1 → v3.2: 15s 0.3214 → 0.3183,
  30s 0.3912 → 0.3870, 1m 0.4712 → 0.4641, 5m 1.1184 → 1.0779; live replay edge (all) 15s
  +1.3 → +1.5%, 30s +3.4 → +3.5%, 1m +3.1 → +3.7%, 5m +7.4 → +9.3%. On hours 17-19 the 1m/5m
  blends are 2-3 points **over**confident on trading candles (both versions; hours 12-16 were
  under): market-wide drift, not fixable per model. Also **edge hunt judged** (`edge-hunt.md`
  *Judging*): the ranking stands; no unregistered proposal earns a slot. Nothing half-done.

* **2026-10-09 22:20 UTC, trading-skills thread: curve-triggered entries: no edge** (profitability
  §3.23). Level crossings (5–40 SOL raised) lose on every rule (chosen: −7.0% on test). Buying a
  70% dip after a 40-SOL run is break-even (dev −0.4%, test −0.3% [−7.4, +6.7]), the closest launch
  rule so far, not positive. Nothing to pre-register or plug into autotrade's launch slot. The
  launch-selection ideas from the coordinator's list are done (§3.21–3.23); metadata was §3.8.
  Claim cleared.

* **2026-10-09 22:10 UTC, trading-skills thread: picking movers from early flow: no edge**
  (profitability §3.22). Six feature groups (flow, buyers + wallet history, holder growth, curve
  shape, creator, name) at +20/+60 s with the new default exit at Jupiter costs: movers are
  predictable (AUC 0.84–0.90) but the predicted movers collapse (top picks −3% to −18% on test).
  Small creator buys (0.01–0.3 SOL, no sale) beat buying every launch in all 16 hours by 1–9
  points, but the dev-chosen rule makes −2.2% [−6.7, +2.4] on test. Nothing to pre-register.
  Next in this thread: entries triggered by curve levels (5–40 SOL raised) with the TP exit.

* **2026-10-09 21:05 UTC, trading-skills thread: exits, regime gating and execution: helps, still
  loses** (profitability §3.21; 22,363 screened launches, dev before 16:00, test 16:00–20:20 UTC).
  Two thirds of launches never offer a sale above cost after a +20 s entry (oracle median −3.45%),
  and the risk filters remove the ones that move (flags + P(rug) < 0.1: oracle +1.5%). On the live
  skip-flag policy, TP +100% / no stop beats the fixed 180 s hold by ~3 points on test (−3.7% vs
  −6.8%); stops always hurt. Jupiter + 0.02 SOL + the measured 0.000011 SOL network fee add ~1
  point: −2.88% [−4.11, −1.60] on test. (Corrected 21:55 UTC: the first numbers, −1.57%, kept
  early take-profits near recording ends; fixed in the scripts and §3.21.) Regime gates: no signal. Lightning also strands
  0.0015 SOL rent per new token (fresh launches ~7% per round trip at 0.1 SOL). Not worth a
  forward test. Scripts `exit_study.py`, `regime_gate.py`, `exit_tp_grid.py`. Nothing half-done;
  claim cleared.

* **2026-10-09 20:25 UTC, predictor-strategy thread: predictor v3.1 + P(rug) candle trading: no
  edge** (profitability §3.20, pre-registered). Primary 5m rule −5.15% [−11.85, +2.52] on 108 fresh
  trades (−7.07% at Lightning costs); 1m −4.92% [−6.63, −3.37] on 590. Data `handoff/data/raw-pred`
  17:33–20:20 UTC. Recorder stopped; nothing half-done; claim cleared.

* **2026-10-09 20:30 UTC, map + docs refresh thread: done** (docs only). OVERVIEW §4–6 now carry
  the real-fill result (−3.07% per round trip through Lightning, ~5.5% for a fresh token; Jupiter
  route ~1.1% per §3.19), the edge hunt as resumed (A1 and D forward tests, C closed), the 5 m
  predictor rule and the retrain claim; queue 11b says the Action adds dip cohorts. OVERVIEW §9
  links the TARTAR System Map page (claude.ai artifact, private to the user unless shared), now
  refreshed to this board. Not touched: `edge-hunt.md`'s *How far it got* table still shows C–E
  unstarted (C and D are done); left to the curve-retrain thread's edge-hunt judging. Nothing half-done.

* **2026-10-09 20:10 UTC, execution-cost thread: use Jupiter's Swap API with our own key**
  (profitability §3.19). Simulated real transactions for 6 tokens (no keys, nothing sent).
  PumpPortal Local charges 0.5% (−50 bps vs Jupiter), Jupiter Ultra 0.1%, Jupiter Metis 0, and
  Lightning 1%. A CATE round trip would drop from the measured −3.07% to ~−1.1% at 0.01 SOL, and a
  fresh curve token from ~5.5% to ~3.1%. With our own key we can also close token accounts and get
  the 0.0015 SOL rent back. `handoff/experiments/jupiter_fills.py` is ready (dry run tested).
  **Needs the user:** a wallet secret key as the environment secret `TARTAR_WALLET_KEY`
  (and optionally a free `JUPITER_API_KEY`). Then the wallet holder runs two 0.01 SOL round
  trips to confirm. Nothing half-done.

* **2026-10-09 19:44 UTC, predictor session (final dump at the user's weekly-limit request; no claim open):**
  Saved `handoff/data/raw-v3/20261009-12.jsonl.gz` (12:55–13:00 UTC, this container's recorder,
  which is no longer running) and the overview workflow's section drafts in `handoff/overview-draft/`
  (superseded by `OVERVIEW.md`). Edge-hunt findings A–B and scripts were committed earlier
  (`handoff/edge-hunt.md`, a243aaf). Other sessions have since resumed and extended them. Nothing of
  this session's is half-done or local-only.

* **2026-10-09 19:17 UTC, dip/jevtrader session: edge hunt C closed, D pre-registered**
  (`edge-hunt.md` §C–D). C: LP on graduated PumpSwap pools keeps a mean 0.67x of its SOL after
  1 h (194 pools); fees add ~0.2–2 points; fresh tokens have no short. D: on all 234 Hyperliquid
  perps (56 delisted), 14-day momentum chosen on train makes +1.50%/week on 2026 test weeks after
  costs and funding, 90% CI [−0.12, +3.31]; registered as a 52-week forward test (scorer checked on
  2026-07..09: +1.44%/week). The JLP and dip data now come from the `paper-tests` Action.

* **2026-10-09 19:10 UTC, handoff session: item (b), the curve blends' underconfidence**
  (predictor doc §8.4.1). Replayed every `trades-*` model on unseen hours 12–16. The flat-vs-move
  call is calibrated; the gap is in the up/down call and moves with the hour (1m: +3.5 / +0.7 /
  −0.1 / +2.1 / +1.5 points), following market-wide drift a single-token watcher can't see. One
  fixable part: the per-token `DirectionCalibrator` (temper-only) was re-tempering the global
  model's already calibrated odds. **Changed:** on curves it now corrects only the online share
  (`× (1 − w)`), chosen on hours 12–13 and confirmed on 14–16: trading gap 15s +1.17 → +0.41,
  30s +0.34 → −0.38, 1m +1.12 → +0.69, 5m +3.01 → +2.87; log loss ±0.0009 (honesty fix, not an
  accuracy gain). PumpSwap and online-only forecasts unchanged. 147 tests pass. **Next
  (done 22:35 UTC, 8.2.2e; install after 10-12): retrain the curve models on the newer recordings** (5m still ~3 points under;
  don't install over `trades-60s`, `trades-300s` or `rug-20s` before the predictor-strategy forward test is evaluated (≤ 2026-10-12): its `evaluate` asserts their SHA-256).
  Also: LightGBM slows 10–50× on shared cores, cap `OMP_NUM_THREADS` (predictor doc §14).

* **2026-10-09 17:46 UTC, same-slot entry thread: closed, not worth building** (profitability
  §3.18; 17,098 launches + 200 fetched blocks). §3.9's creation-slot edge comes from the
  creator's own bundle: one-off wallets buy in an unbroken run right after the create (83%,
  median 2 txs later) and realize +52%; entering first after the create loses 3.4% when nobody
  follows in that slot. An outsider can at best be first among the 492 repeat sniper bots
  (they land a median 132 txs later in the same block, on low fees): +2.0% [+1.3, +2.7] at
  0.1 SOL only if we beat all of them every time, −1.2% as a median-speed bot, negative with a
  p90 priority fee or 1 SOL size. Needs ~$1k/month shreds + co-location first. Nothing
  half-done; no `*.pumpportal.fun` calls.

* **2026-10-09 17:40 UTC, dip/jevtrader session:** edge hunt A1 pre-registered as a 90-day paper
  forward test: hedged JLP vs Kamino USDC (`preregistration/jlp-hedged/SPEC.md`,
  `experiments/jlp_paper.py`, 6 tests). Live check: JLP delta per JLP-$ SOL 0.441, ETH 0.077,
  BTC 0.124; $10k Jupiter quotes buy −9 to −11 bps, sell +23 to +25 bps vs NAV. Two pilot
  snapshots precede the window and are ignored by the scorer.

* **2026-10-09 17:18 UTC, handoff session: PumpSwap models done.** 15s, 30s and 1m installed
  (`tartar/models/pumpswap-{15s,30s,60s}`), 5m not; each judged by a rule fixed in
  `pumpswap_model.py` before results. On the test pools the blend's trading candles are
  calibrated (1m 72.0% hit vs 72.0% stated; 30s 73.8 vs 73.5; 15s 62.4 vs 62.6), where online-only
  states ~49–50% and hits 54–64%; edge +0.9 / +1.7 / +2.1% vs online −0.7 / +0.3 / −0.6%. 5m
  gains calibration but loses edge (48 test pools; retry with more data). The four-length run
  was OOM-killed building 15s (its event cache), so 15s ran alone on newer data (458 pools).
  Nothing half-done; the raw-v3 recorder is the only thing running here.

* **2026-10-09 ~17:20 UTC, clever session, ending for a restart** (the user put the PumpPortal
  key in the environment; this session can't see it): nothing traded or spent; the cost
  measurement is ready (`handoff/experiments/real_fills.py`, see the REAL MONEY entry). Synced
  with the handoff session at 16:06 (split accepted). **Half-done, unclaimed:** curve blend
  calibration, item (b): every curve blend under-states its trading-candle hit rate by 1.7–2.8
  points on unseen hours 12–15 (15s 62.7/61.0, 30s 65.8/63.8, 1m 69.1/67.4, 5m 73.9/71.1). On
  v3.1 validation the cause is neither the blend prior (0.95 → 0.995 closes only ~0.7 of 2.2
  points at 1m) nor the direction calibrator (off: +0.5). The raw 1m model on trading rows is
  under on validation (71.4/70.0) but over on test (68.5/70.6), so it is not one temperature
  either. Next: look at the flat-vs-move call (p_flat on trading candles); any change stays
  `domain == "trades"`. Item (a) needs nothing: the 5m raw model is calibrated on hours 12–15
  (74.8/73.4). `raw-clever2` hour 16 saved; recorder stopped with the container.

* **2026-10-09 16:20 UTC, handoff session:** the predictor session's *Active* entry is removed
  (it stopped ~13:25 UTC at its usage limit; its container and the unsaved overview draft are gone).
  Everything it had open is done or carried by the handoff session's line: OVERVIEW.md (landed),
  PumpSwap models (30s/1m installed, 5m not, 15s training), raw-v3 recording (hours 13–15 saved).
  The edge hunt stays on hold (`handoff/edge-hunt.md`).

* **2026-10-09 16:05 UTC, clever session, handing off** (session_01R61Ym2543SdY4GEWPsLin6, branch
  `claude/clever-pascal-p4m7ub`; everything is on `main`; no claim open, nothing half-done; its
  recorder and sampler are stopped):
  - **User decisions (06:35):** Jev off in TARTAR, live fast loop retired, no private RPC,
    this session may fast-forward `main`.
  - **Merged** the research session's unmerged branch into `main` (fixed `sol_dex_costs.py decay`,
    broken by the auto-merge).
  - **P(rug) shipped** (queue 13, §9.1): AUC 0.935 on the latest 1,852 launches, held 0.924 forward
    on 7,075 unseen ones; risk level reweighted (AUC 0.585 → ~0.7), `--next-launch` picks unchanged.
  - **Predictor v3.1 installed** at all four candle lengths (§8.2.2c–d); 5m drops the old
    recorder's rows (chosen on validation). 1m live edge +8.0%, 5m +11.9% on the newest launches.
  - **11a evaluated as pre-registered: no edge** (§3.16, 264 pools).
  - **`pumpswap` flat-candle priors** (§8.2.3).
  - **SOL-USD costs** in European and US hours: ~0.5 bps per fill in every hour (queue 12).
  - **Data:** `handoff/data/raw-clever` 06:23–16:00 UTC (~16,000 launches, 341 SOL pools),
    `handoff/data/sol-dex/costs-20261009-{day,us}.jsonl`.
  - **Open for others:** 5m model still ~6 points overconfident at the open (retrain as new-style
    data grows); the 1m/15s/30s live blends lean ~1–2 points underconfident on trading candles;
    dip cohort due ~02:24 UTC 10-10 (`established_cohort.py` + `pumpswap_fees.py`, see queue 11b);
    the handoff session holds the PumpSwap model and `OVERVIEW.md`.

* **2026-10-09 14:15 UTC, handoff session** (session_01GAoiXJ4NHWXq6DnP61icSU, branch
  `claude/handoff-overview`; started by the user to continue the predictor session after it hit
  its usage limit mid-handoff):
  - **`handoff/OVERVIEW.md` landed** (the user's request): the project in one document (what it
    does, predictor accuracy, P(rug), every closed strategy with its number, costs, what's open,
    the user's decisions, data, doc map). Profitability §1 now marks PumpSwap closed (§3.16).
  - raw-v3 recorder restarted here at 13:31 UTC; hour 13 saved.
  - **PumpSwap model** (`handoff/experiments/pumpswap_model.py`: raw logs parsed once for all
    four candle lengths, hyperparameters chosen on validation, install rule fixed in the
    docstring before results). **1m installed** (`tartar/models/pumpswap-60s`, 348 pools, on
    `main` 15:30 UTC): on 52 test pools the blend's trading candles hit 72.0% vs 72.0% stated,
    where online-only hits 62.8% vs 49.2% stated; edge +0.9% vs −0.7%. **5m not installed**
    (calibration better, edge worse: −0.9% vs −0.5%). 30s and 15s still training (predictor
    doc §8.2.3).
  - Tests: 140 pass on the merged branch.

* **2026-10-09 09:00 UTC, clever session (progress):** P(rug) shipped (queue 13) and predictor v3
  installed for all four candle lengths (queue 2), both on `main`. 5m v3 is overconfident on new
  launches; the cause is the old recorder's rows (20-min idle cut, very different outcome mix at
  5m), and a preview shows down-weighting them helps at 5m only (§8.2.2c). Nothing half-done;
  the recorder and SOL sampler run in this container (see *Active*).

* **2026-10-09 06:40 UTC, clever session** (session_01R61Ym2543SdY4GEWPsLin6, branch
  `claude/clever-pascal-p4m7ub`):
  - Merged the research session's branch (`claude/eager-archimedes-k8pn4q`) with `main` and landed
    it (135 tests). Conflicts were docs only (both sessions measured SOL quote decay; both kept,
    they agree). The auto-merge broke `sol_dex_costs.py decay` (`quote()` now returns a dict):
    fixed and smoke-tested. The predictor session's 04:33–05:33 cost samples were never committed;
    the docs now say so.
  - **User decisions (06:35 UTC):** Jev stays off in TARTAR and the live fast loop is retired
    (queue 1 closed; carve-out not adopted); no private RPC for now; this session may fast-forward
    `main` after each unit that passes pytest; keep working the queue while the 11a recorder runs.
  - Recorder for 11a running here since 06:24 UTC (`data/raw-clever`, `--pumpswap-hours 4`).

* **2026-10-09 06:05 UTC, research session, handing off** (branch
  `claude/eager-archimedes-k8pn4q`, everything pushed; **not on `main`: this session may push
  only its branch, so the user (or a session allowed to) must merge it**: `git merge
  origin/claude/eager-archimedes-k8pn4q`, pytest, fast-forward `main`). 134 tests pass.
  - Stopped my recorder and SOL sampler at 06:00. Data: `handoff/data/raw-eager/` (04:06–06:00,
    2,639 launches, 69 graduated SOL pools, ~211k PumpSwap swaps) and `handoff/data/sol-dex/`.
  - **11a is pre-registered but not evaluated:** it needs ≥ 250 graduated SOL pools; 69 exist.
    Any session: record more with `tartar record --out data/raw-<you> --pumpswap-hours 4`
    (~35 SOL pools/hour, so ~5.5 h more), copy finished hours to `handoff/data/raw-<you>/`,
    then run once `python3 handoff/experiments/pumpswap_study.py handoff/data/raw-eager
    handoff/data/raw-<you> --show-test` (plus `--latency 3` and `--size 1`), and write it up
    as profitability §3.16 whatever it shows. Don't compute returns on these pools before.
  - **After 11a:** `tartar train --raw <same dirs> --pumpswap` (the PumpSwap model; compare
    with online-only in its report, install only if it helps), and give the `pumpswap` domain
    its own flat-candle prior (old data: a traded candle is followed by a flat one 6% of the
    time on PumpSwap vs 45% on curves).
  - Unclaimed next steps, in order: (1) the 11a recording above; (2) predictor v3 with
    `--num-leaves 31 --min-leaf 2000` (queue 2); (3) ship P(rug) (queue 13); (4) the SOL
    sampler at European/US hours (queue 12); (5) dip cohort ~02:24 UTC 10-10, then
    `pumpswap_fees.py --cohort <file> --save .../fees-measured.json` (addendum).
  - For the user: the Jev carve-out draft (`handoff/jev-carveout-DRAFT.md`) awaits a decision.

* **2026-10-09 05:52 UTC, Jev session, slow-loop cycle 2:** Reviewed all live data (23:44–03:39 UTC in bursts, 352 screened launches with outcomes; `handoff/live/reviews/20261009-0552.md`). Paper trades: 68, mean **−1.4%** (90% CI −9.2 … +7.8%). Buying every screened launch: −9.2% (CI −13.0 … −4.8%). The skip flags remove losers (skipped: −13.5%). **Jev shadow: no signal.** Spearman with net is buy +0.02, copycat +0.07, low_effort +0.06, meme −0.07, scam_wording +0.08, and no quintile pattern is monotone. That agrees with the offline result (§3.7). Paper results are negative for the 2nd cycle in a row (CI spans 0). `odd_curve` looks like a skip candidate (with −19.2%, n=100; without −5.3%), but it's in-sample, without intervals. Check it with `tartar decide` before adding it. **No policy change.** The fast loop is **stopped** pending the user's Jev-policy decision and somewhere always-on to run it; no further cycles are scheduled.

* **2026-10-09 05:36 UTC, predictor session (handing off; no claim open, nothing half-done):**
  (1) The point forecast's median shrink is now fitted on out-of-fold training medians
  (3 token-wise folds) plus validation (`train.oof_medians`, `train_global(shrink_folds=3)`).
  It beats validation-only on both datasets (v1 750.39 vs 750.53, v2 1218.82 vs 1221.66).
  All four installed models were refit without retraining. (2) Queue item 12: a second
  60-min SOL-USD cost window plus $10k size and quote decay (`sol_dex_costs.py decay` /
  `decay-summary`). Results are in §3.12, `jevtrader.md` and item 12 above. On-chain costs
  are ~0.5 bps per fill, and latency adds noise, not cost. **Next session:** the same three
  as the 03:49 entry, with item 12 narrowed to the daytime windows. Also suggest the Jev
  session restart the fast loop (once the user rules on the Jev policy) with
  `--pumpswap-hours 4` and `SOLANA_COMMITMENT=processed` (follows graduations; events ~0.3 s earlier).

* **2026-10-09 05:20 UTC, research session:**
  - **Copy-trading closed (§3.15):** following wallets whose buys paid off earlier loses on
    test (−21.0% [−31.0, −10.5] per trade); copying any buy 2.5 s late loses 8–29%.
  - **New: a PumpSwap model for `watch` after graduation** (predictor doc §8.2.3; code and
    tests on this branch). `tartar train --raw DIRS --pumpswap` trains it from
    `--pumpswap-hours` recordings; the agent switches to it at graduation, else behaves as
    before. Training waits until the 11a evaluation has run (same pools).
  - Predictor hyperparameters: a sweep on v2's data (`predictor_sweep.py`) finds more
    regularized trees slightly better than the default (31 leaves / 1,500 rows per leaf: test
    log loss 0.4583 vs 0.4629). To be applied when v3 is trained on the new recording.
  - The new recording's capture is much better than the old: median 100%, mean 97% of each
    token's trades (old data: 93% / 84%).

* **2026-10-09 05:04 UTC, Jev session:** Pushing works again. Landed the unpushed commits and raw hours 02–03 (`handoff/data/raw/20261009-0{2,3}.jsonl.gz`; 03 covers 03:17–03:39). The fast loop has been down since 03:39 (container suspension). **Not restarted**: the new *Jev usage policy* blocker says the user's own protocol may forbid TARTAR's always-on Jev shadow calls. Waiting for the user to decide. The 05:50 cycle will review the data without restarting the loop.

* **2026-10-09 04:50 UTC, research session** (session_01YLnqLnTQzvD6HHUTvnNpVm, branch
  `claude/eager-archimedes-k8pn4q`; this session may push only that branch, so nothing here is
  on `main` until the user merges it). GitHub pushes work from this session.
  - **PumpSwap fees (§3.13):** LP 0.20% + protocol 0.05% + a creator fee falling with market
    cap; just-graduated pools pay 0.02 + 0.93 + 0.30 = **1.25%/side**, like the curve. The dip
    pre-registration charged 0.5%/side; cohort 1 pays 0.30–1.20% (mean 0.85%). A dated addendum
    adds a secondary line at measured fees (SPEC unchanged). **When adding a dip cohort, also
    run `pumpswap_fees.py --cohort <file> --save .../fees-measured.json`** (see the addendum).
  - **Queue 3 done, no edge (§3.14).**
  - **Queue 11a pre-registered** before its data was read; recorder running here
    (`data/raw-eager`, `--pumpswap-hours 4`, ~40 SOL pools/hour). Finished hours go to
    `handoff/data/raw-eager/`.
  - Fast loop: positions open at graduation are sold on the recorded PumpSwap pool at its fee
    (129 tests pass).
  - **Queue 12:** `sol_dex_costs.py` now re-quotes after 1/2/5 s (quote decay); a 16 h run
    started 04:10 UTC here (`data/sol-dex/`). First 5 samples: |decay| p90 ≈ 1–2.6 bps at
    1–5 s, no 50 bps slippage failures; fill at the later quote still ≈ 0.5 bps/fill.

* **2026-10-09 03:49 UTC, profitability session (handing off):** Read the user's `jevtrader`
  (now public) and wrote `handoff/jevtrader.md`: it IS the SOL-USD + Jev loop, sealed until
  2026-10-23. Never unblind or push to it. Measured on-chain SOL-USD costs for its day-28 fee
  arithmetic (§3.12): ~0.5 bps per fill via Jupiter vs 90 at Coinbase (quotes; quote decay
  not yet measured). Raised two blockers (Jev usage policy; GitHub write access, which blocked
  this session's last pushes). **State of the research:** launch-stage strategies are closed
  (§3.2–3.10). Established-memecoin rules show no reliable edge (§3.11), with a rolling
  pre-registered dip test running (add a cohort daily; score 2026-10-30). The most promising
  open thread is jevtrader's day-28 result read against on-chain costs. **Next session:** (1) add
  a dip cohort (`established_cohort.py`) and commit; (2) rerun the SOL cost sampler at another
  time of day and add a quote-decay measurement; (3) after 2026-10-23, if the user shares
  jevtrader's results, compare each arm's f*_X with §3.12.

* **2026-10-09 03:35 UTC, Jev session:** Keepalives don't work. The container suspends 5–7 min after a turn ends, even with check-ins every 5 min, and the loop died at 03:24 and 03:33. Stopped scheduling keepalives and asked the user. Pushes have returned 403 since 03:17; this entry and raw hour 02 are local only. 834 screens journaled so far. The 3-hourly cycle is still set for 05:50.

* **2026-10-09 03:17 UTC, Jev session:** The loop died again at 02:54. The user approved keepalive check-ins, so I restarted it (`--hours 17`, still ending ~20:17 UTC) and now schedule a check-in every ~9 min to keep the container awake. Saved raw hour `20261009-02` (02:47–02:54).

* **2026-10-09 02:47 UTC, Jev session, slow-loop cycle 1:** The fast loop died again at 00:10 (container suspended after my turn; the 10-min keepalive check-ins were blocked by the permission check, so the user was asked how to proceed). Restarted at 02:47. All data so far: 23:44–23:50 and 00:03–00:10 UTC, 125 screened launches with outcomes (`handoff/live/reviews/20261009-0247.md`; raw hour 00 saved to `handoff/data/raw/20261009-00.jsonl.gz`). Paper trades: 27, mean −2.0% (90% CI −15.3 … +16.4%); buying every screened launch: −2.4%. Jev shadow Spearmans: buy +0.12, low_effort +0.18, meme −0.16, copycat +0.04, scam_wording +0.02. With n=125 these are noise-level and their quintiles aren't monotone. **No policy change** (needs ~300 new launches). Note: `max_open` (10) skipped 203 screens in ~13 min. That's a capacity limit, not evidence; left as is.

* **2026-10-09 02:29 UTC, profitability session:** Item 11(b) is done (§3.11).
  Studied simple rules on GeckoTerminal 5-min data for liquid Solana pools.
  Momentum and breakouts lose. Dip-buying showed +2.1% excess over random
  entries on a mixed universe, but it is concentrated in 3 pools; on
  memecoins only it is +0.7% [−1.5, +2.9], and the +7.4% mean there is
  survivorship. Pre-registered the dip rule as a rolling forward test
  (`handoff/preregistration/dip-rolling/`, cohort 1 = 12 PumpSwap
  memecoins). **Please add a cohort about daily**
  (`established_cohort.py`, commit at once). Score on 2026-10-30 or at
  ≥ 200 trades. Also: a full-stream replay confirms the launch baseline
  (−6.9%/trade, §3.10).

* **2026-10-09 01:58 UTC, predictor session:** `tartar watch` now keeps going
  through graduation. The chain feed hands over to the token's PumpSwap pool,
  and the agent drops the bonding-curve model and continues with the online
  model. 128 tests pass. No claim open.

* **2026-10-09 01:54 UTC, predictor session:** PumpSwap recording for item
  11a is done, on `main` (126 tests):
  - Extra per-pool subscriptions run on the same websocket.
  - Each graduated SOL token's canonical pool is recorded for N hours.
  - Quote-paired graduations are marked `quote` and skipped; in the live run
    they were 8 of 20, mostly quoted in pump coin `pumpCmXq…`.

  A 20 min live run is in `handoff/data/raw-pumpswap`. Busy pools logged
  2,000–10,800 trades in their first minutes, with the first trade 4–46 slots
  after graduation. No claim open.

* **2026-10-09 ~01:50 UTC, profitability session** (time corrected): Graduation run-up (item
  11a): it first looked like +5.8%/trade, but that was two biases. Fast
  graduations were dropped by the ≥3-candle filter, and length-biased
  censoring dropped rugs. The fair replay through `FastLoop` (exclude only
  recorder downtime) gives break-even at best. Code kept: `load_trade_tokens(...,
  min_candles=0)` for trading studies; the fast loop has `runup_*` entries
  (off by default), skips quote-paired launches, cancels buys on completed
  curves, and values post-graduation exits with `graduation_haircut`.
  **Everyone: for long-hold studies, replay through `FastLoop`; don't use
  `load_trade_tokens` windows** (§3.10 lesson).

* **2026-10-09 01:26 UTC, predictor session:**
  - Installed global models for 15s, 30s and 5m candles, on the same ~5,800
    launches as v2. Live replay edge, all candles: +3.8%, +3.7% and +12.0%;
    the online model alone is about even with naive. Predictor doc §8.2.2.
  - Flat priors for the online model now depend on the candle length.
  - Median shrink study: no fitting method beats "none" under
    within-validation cross-validation. A late-candle shrink helps on test,
    but validation can't size it. v2's point gap is not the shrink (§8.2.1).
  - Next: record PumpSwap trades of graduating tokens (item 11a). PumpSwap
    runs ~356 successful tx/s program-wide, too much to record whole, so
    only graduated pools are recorded.

* **2026-10-09 ~01:25 UTC, profitability session** (time corrected): Queue item 10 is done
  (§3.9). Measured fees from 212 recent TradeEvents: 1.25%/side on SOL
  curves. Simulated entries in slots on the slot recording: only the
  creation-slot bundle profits, and every outside entry loses, even with no
  fees. Launch buying is closed; added queue item 11 (next strategy
  families). New scripts: `handoff/experiments/fee_sample.py` and
  `slot_profit.py`.

* **2026-10-09 ~01:00 UTC, predictor session** (time corrected):
  - `--raw` now takes several recorder directories (`A,B`), one timeline each.
  - Trained and installed predictor v2 on every recording: my recorder through
    21:50, the Jev fast-loop hour, and the slot runs. That is 5,790 launches,
    251k rows. Comparison with v1 is in the queue entry and predictor doc
    §8.2.1.
  - `handoff/data/raw` hours 20 and 21 completed from this container.

  120 tests pass. No claim open; nothing half-done.

* **2026-10-09 00:50 UTC, predictor session:** Queue items 7, 5, 4 and 9 are
  done, all on `main` (117 tests at last full run):
  - fees verified;
  - slots recorded, plus the latency numbers above;
  - PumpSwap feed for graduated tokens;
  - pump.fun quote-paired curves decoded and kept out of SOL data.

  Two research workflows (PumpSwap and pump.fun V2 layouts) verified
  everything against mainnet transactions. Their scripts, IDLs and samples are
  in this session's scratchpad only, so the key facts are in the predictor
  doc's §5 table. Slot recordings are in `handoff/data/raw-slots*`. No claim
  open; nothing half-done.

* **2026-10-09 00:20 UTC, profitability session:** Queue item 8 is done
  (§3.8): `tartar/metadata.py` fetches launch metadata (Pinata gateway;
  ipfs.io now refuses requests), and `tartar/jev.py` has question sets
  (`LAUNCH`, `METADATA`) with Score answers as level + uncertainty. Jev's
  metadata judgments add nothing beyond code features. Across §3.7–3.8, Jev
  shows no predictive value for which launches beat costs. Answers and
  metadata are cached in `handoff/data/jev/`. Scope: V1 launches only. The
  V2 launches with dropped trades (item 9) never enter the evaluation set;
  rerun §3.5–3.8 when V2 decoding lands. Earlier, at 00:03, I warned the
  Jev session that its container had likely been suspended (idle since
  23:45; first check-in 02:46) and that no live data was in git yet.

* **2026-10-09 00:15 UTC, predictor session:** Item 7 done (fees verified,
  see queue). Item 5 code landed on `main`: slots in raw events and ticks.
  The decoder now only accepts events emitted inside pump.fun's own program
  frame, because routers' events named TradeEvent share its discriminator.
  110 tests pass. Found the V2 gap (queue item 9). Two research workflows are
  decoding V2 and PumpSwap layouts against mainnet transactions. A 40-minute
  slot-annotated recording runs in this session's container for the latency
  measurement. Jev session: pull `main` and restart at an hour boundary when
  convenient to start recording slots.

* **2026-10-09 00:03 UTC, Jev session:** The fast loop died at ~23:50 when the container was suspended after my turn ended (ConnectionRefusedError to the local proxy). Restarted at 00:03 (`--hours 20`). Lost ~13 min of data. Saved the finished hour `handoff/data/raw/20261008-23.jsonl.gz` (23:44–23:50 only). Now checking in every ~10 min to keep the container awake, and archiving finished hours.

* **2026-10-08 ~23:45 UTC, predictor session** (times in this session's earlier entries were guesses; corrected against the clock): Finished queue item 6 and
  landed it on `main` (106 tests pass). Without retraining v1:
  - The 80% band was already calibrated against what it states. Reports now
    show the stated probability next to coverage.
  - The late-candle median is shrunk toward the current price, with factors
    fitted on validation and stored in model meta (refitted at each
    `tartar train`).
  - The global prior in the blend is 0.95.

  Live test edge is +7.5% / +7.8% (all / trading candles), and trading
  confidence is 67.8% stated vs 69.0% hit. Nothing is half-done. Free for
  another queue item.

* **2026-10-08 23:44 UTC, Jev session:** The user confirmed option 1: rules scorer, Jev in shadow, paper only. Started `tartar fast --hours 20` (policy = defaults + `shadow_jev: true`; copy in `handoff/live/policy.json`, since `/data/` is git-ignored). Slow-loop cycles every ~3 h; reviews go to `handoff/live/reviews/`.

* **2026-10-08 ~23:30 UTC, predictor session:** Back after a usage limit.
  Claimed queue item 6. The user asked this session to install the TypeSafe
  plugin too; `claude plugin install typesafe@typesafe-ai` was blocked by
  auto mode's safety check here as well (the user can run
  `/plugin install typesafe@typesafe-ai`). Read the skill directly; it is
  guidance only (read docs.typesafe.ai before Jev code). Dropped a
  dedicated-recorder job brief: the fast loop records. Since 23:40 this
  session's own recorder is off (container suspension killed it at 20:34
  and again later); its local raw data (14:06–20:34 and 21:42–~22:00 UTC)
  is beyond the `handoff/data/raw` snapshot only by ~30 min.

* **2026-10-08 23:35 UTC, profitability session:** Added Jev shadow mode to
  the fast loop and its review section. A replay over 5,598 recorded launches
  shows no rank correlation between any Jev answer and outcomes. The user's
  earlier project `AJW9991/jevtrader` (private) couldn't be attached: no
  GitHub access from this session. They were told how to grant it (Claude
  GitHub App on AJW9991, or add StaticPush7217 as a collaborator).

* **2026-10-08 23:10 UTC, profitability session:** The user asked to use the
  TypeSafe agent skill. Installing the plugin was blocked by the permission
  classifier (marketplace added; the user can run `/plugin install
  typesafe@typesafe-ai`). I followed the skill's guidance directly: read the
  live docs, rewrote `tartar/jev.py` to the documented API (one real call,
  243 ms median over 3,523 launches), and evaluated Jev in `tartar decide
  --jev` (§3.7): no edge. The user offered folders from earlier Jev trader
  attempts (data, tests, code); asked them to share as repos or a
  `prior/<name>/` branch.

* **2026-10-08 22:45 UTC, profitability session:** Built the fast loop
  (`tartar/fastloop.py`, `tartar fast`) and the slow loop's review
  (`tartar/review.py`, `tartar review`, `handoff/slow-loop.md`). One
  streaming launch-state builder now serves live and offline. Network
  opened at 22:35 and the live fast loop ran in this container (rules
  scorer, paper): it screened real launches and placed paper fills. The
  user added the Jev key. At their request I started a fresh **Jev
  session** to take over queue item 1, and stopped my own live loop so only
  one session owns it. Earlier log times in this file were estimates; the
  real clock was ~2 h behind them. Corrected.

* **2026-10-08 ~22:15 UTC, profitability session:** The user's "jev" API is
  TypeSafe's Jev decision model; they chose paper trading first and have a
  key. Built `tartar decide` + `tartar/decide.py` (causal launch states;
  rule, flag, LightGBM and Jev scorers; validation threshold, test report)
  and `tartar/jev.py`. Could not verify Jev's request format: docs and
  api.typesafe.ai are unreachable here, and an SDK download was refused by
  the permission classifier. Told the user to store the key as
  `TYPESAFE_API_KEY`. Fair flag test: −1.8% vs −5.1% per trade, still
  negative. Everything is on `main`.

* **2026-10-08 ~21:45 UTC, profitability session:** Finished the scam-filter
  study (§3.5): the existing screen and a learned 20 s screen do not make
  launch buying profitable; five flags reliably mark worse trades. Fixed a
  simulator flaw: exits after a recording cut used a stale price; they are
  now dropped (`TokenData.end_reason`, `Curve.cut`). Experiment scripts are
  in `handoff/experiments/`. The user then asked to use their "jev" API for
  split-second decisions; I asked what it is before building anything.

* **2026-10-08 ~21:00 UTC, profitability session**
  (https://claude.ai/code/session_01U4x5qUJYMStcujpyLJgQ8N): Added
  `tartar profit` and `handoff/profitability.md`. Result: no strategy is
  profitable at realistic costs on the recorded data. The only edge is
  same-block sniping, which a public RPC can't reach. Set up this board and
  landed everything on `main`. Recording is blocked by the network policy.
  Next for me: queue item 2 on the existing data.
