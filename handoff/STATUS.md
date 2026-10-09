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

* **Same-slot entry thread** (project thread session, since 2026-10-09 17:35 UTC, branch
  `claude/project-thread-12sv1q`). **Paper and analysis only, never `*.pumpportal.fun`.** Task:
  §3.9's only winning launch buy is inside the creation slot. Is that entry reachable for an
  outsider (who the same-slot buyers are, where in the slot they land, the latency and landing
  cost to get there) and does it stay profitable after real fees, on all slot-annotated
  recordings (~20k launches, not 1,347)?

* **Dip/jevtrader session** (session_01Htqh7pc1Lh1PP6Dkm1rVvz, since 2026-10-09 17:33 UTC, `main`
  only): continues the profitability session. **Owns the dip forward test (queue 11b)**: a daily
  routine adds a cohort at 02:24 UTC (`established_cohort.py` + `pumpswap_fees.py --cohort`) and
  scores it on 2026-10-30 or at 200 trades. **Owns the jevtrader day-28 readout (queue 12)**: a
  routine checks on 2026-10-24. Other sessions: no need to add cohorts by hand any more.

* **Predictor-strategy thread** (session continuing session_01YLnqLnTQzvD6HHUTvnNpVm, since 2026-10-09
  17:33 UTC, branch `claude/project-thread-mwc92g`). The user asked for continuous work toward profit
  (17:32 UTC), which lifts the edge-hunt hold for this lane. **Task:** can predictor v3.1's live edge
  plus P(rug) become a rule that is profitable after measured fees (1.25%/side on curves)? Pre-register,
  paper-test on unseen launches, report net with n and 90% CI. No real SOL; stays off in-block
  launch entry (the handoff thread's lead).

* **Handoff session** (session_01GAoiXJ4NHWXq6DnP61icSU, since 2026-10-09 13:28 UTC, branch
  `claude/handoff-overview`). **PumpSwap models done** (15s/30s/1m installed, 5m not; predictor doc
  §8.2.3) and `handoff/OVERVIEW.md` on `main`. Still in flight: recording `data/raw-v3` here since
  13:31 UTC (`tartar record --source chain` (the default) `--track-minutes 120 --pumpswap-hours
  4`, `SOLANA_COMMITMENT=processed`); finished hours go to `handoff/data/raw-v3/` (13–16 so far).
  It dies when this session goes idle. **Now (17:21 UTC): item (b), the curve blends'
  1.7–2.8 point underconfidence on trading candles** (unclaimed after the clever session's
  17:20 notes): decompose the gap into the flat-vs-move call and the up/down call on unseen
  hours; any change stays `domain == "trades"`.

* **REAL MONEY — the PumpPortal wallet is owned by the real-money thread session
  (session_0173Md1HrgsAZHzbjLUmi64b, branch `claude/project-thread-2gop6x`, from 17:30 UTC
  2026-10-09).** The first successor (session_01RdY84M3yCZbssMGWNVdpQi) was interrupted while
  cloning and never ran a command. **Probe 17:28 UTC: still 403 "Must supply a valid API key",
  nothing traded or spent.** `PUMPPORTAL_API_KEY` is not set in new sessions, and the proxy's
  PumpPortal credential is registered for `*.pumportal.fun` (one "p"), so it never matches
  `pumpportal.fun`. Needs the user: fix that host to `pumpportal.fun` (the trade URL is the bare
  domain, so `*.` alone may not match), or add `PUMPPORTAL_API_KEY` as an environment variable.
  Every real trade waits for the user's go in the thread. Earlier (was) text:
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
    The dip rule is pre-registered for a forward test: **any session, about
    once a day: `python3 handoff/experiments/established_cohort.py`, then
    commit and push the new cohort file at once.** Score with
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

14. **Edge hunt: new strategy families: ON HOLD by the user (2026-10-09 ~13:25 UTC).**
    Resume only when the user asks. Exploratory findings and how to resume are in
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
