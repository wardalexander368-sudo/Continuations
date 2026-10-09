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

* **Jev session** (session_012ZRs9FUggpEkx65Rw7K7fU, live since 2026-10-08 23:44 UTC): owns the **live fast loop + slow loop** (queue item 1, steps 3–4). User chose `"scorer": "rules"` with `"shadow_jev": true` (paper). Fast loop runs `--hours 20` in this container (ends ~19:44 UTC 10-09). Tracked copies of the policy and reviews: `handoff/live/`. Branch `claude/jev-live`.





## Blockers (need the user)

* ~~Network~~: **resolved 22:35 UTC**, the user enabled full network access.
* ~~TypeSafe Jev key~~: **resolved 22:40 UTC**, `TYPESAFE_API_KEY` is set
  as an environment secret (new sessions see it). **Never ask for the key in chat.**
* **Private RPC:** the public RPC misses ~7% of a typical token's trades, more
  for busy ones, and adds delay. A Helius, QuickNode or Triton websocket in
  `SOLANA_RPC_WS` fixes both. Ask the user. Note (§3.9): it improves
  data quality only. It won't make launch buying profitable.

## Queue (ranked by expected effect on profit)

1. **Jev in the fast loop** (user request: Jev = fast loop, Claude = slow
   loop; paper trading first). Procedure: `handoff/slow-loop.md`.
   1. ~~Verify `tartar/jev.py`~~ **done 23:05 UTC**: it matches
      docs.typesafe.ai/api and follows the TypeSafe agent skill (read
      `github.com/typesafe-ai/skills` → `skills/typesafe-ai/SKILL.md` and
      `docs.typesafe.ai/llms.txt` before changing Jev code; the user asked
      for this). The proxy supplies credentials (no env var needed).
   2. ~~`tartar decide --jev`~~ **done**: Jev finds no edge (direct answer
      −9.2% on test, overconfident ~2×; name judgments weak). See
      `profitability.md` §3.7.
   3. Run the fast loop live (paper). Use `"scorer": "rules"` (Jev's direct
      answer lost more than buying everything) **and add Jev shadow mode**:
      ask Jev about every screened launch and journal the answers without
      acting on them, so `tartar review` can test them on fresh launches.
      Shadow mode is built: set `"shadow_jev": true` in data/policy.json.
      The fast loop also records raw data (queue item 2).
   4. Slow-loop cycles every few hours (`tartar review`), one policy change
      at a time, with the reason in the policy note and the log.
2. **More data.** The fast loop records as it runs. After 24 h+:
   `tartar train --raw data/raw`, `tartar profit`, `tartar decide`.
3. **Longer holds on screened tokens** (10–90 min) once data exists.
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
    for the next study;
    (b) ~~established memecoins~~ **studied (§3.11): no reliable edge.**
    The dip rule is pre-registered for a forward test: **any session, about
    once a day: `python3 handoff/experiments/established_cohort.py`, then
    commit and push the new cohort file at once.** Score with
    `established_prereg_eval.py` at ≥ 200 trades or on 2026-10-30; (c) a liquid market like SOL-USD where costs are tiny,
    e.g. Jev on news (the user's earlier `jevtrader` idea).

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

* Judge every model and strategy by `tartar profit` on the **latest**
  launches. Pick thresholds on validation only, and quote 90% intervals by
  token.
* No real-money trading code without the user's explicit request.
* Never trade the v1 model's expected return: it loses ~43% per trade on test
  launches (see `profitability.md` §3.2).

## Done

* Predictor v1, scam filtering, online-model fixes (predictor session).
* Predictor open problems 3–5 (queue item 6): band reporting, late-candle
  median shrink, blend prior 0.95 (predictor session, on `main`, doc §8.4).
* `tartar profit` and the profitability findings (profitability session,
  branch `claude/profitability-backtest`, on `main`).

## Log (newest first)

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
