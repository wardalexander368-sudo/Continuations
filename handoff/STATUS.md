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

* **Jev session** (started 2026-10-08 ~22:45 UTC by the profitability session at the user's request; it has `TYPESAFE_API_KEY` and full network): verify Jev's wire format, run Jev through `tartar decide`, run the fast loop live with Jev, and run the slow loop. See *Queue* item 1.

## Blockers (need the user)

* ~~Network~~: **resolved 22:35 UTC**, the user enabled full network access.
* ~~TypeSafe Jev key~~: **resolved 22:40 UTC**, `TYPESAFE_API_KEY` is set
  as an environment secret (new sessions see it). **Never ask for the key in chat.**
* **Private RPC:** the public RPC misses ~7% of a typical token's trades, more
  for busy ones, and adds delay. A Helius, QuickNode or Triton websocket in
  `SOLANA_RPC_WS` fixes both. Ask the user.

## Queue (ranked by expected effect on profit)

1. **Jev in the fast loop** (user request: Jev = fast loop, Claude = slow
   loop; paper trading first). Procedure: `handoff/slow-loop.md`.
   1. Verify `tartar/jev.py` against TypeSafe's real API (docs.typesafe.ai,
      OpenAPI spec). `build_request` / `parse_probability` were written
      blind. Make one real call; fix the format; keep the tests passing.
   2. `tartar decide` with the key set: Jev is scored on the ~1,056
      validation and test launches (cached in `data/jev-scores.jsonl`).
      Compare with the other scorers and note Jev's latency.
   3. Run the fast loop live with `"scorer": "jev"` (paper). It also
      records raw data, which is queue item 2.
   4. Slow-loop cycles every few hours (`tartar review`), one policy change
      at a time, with the reason in the policy note and the log.
2. **More data.** The fast loop records as it runs. After 24 h+:
   `tartar train --raw data/raw`, `tartar profit`, `tartar decide`.
3. **Longer holds on screened tokens** (10–90 min) once data exists.
4. **PumpSwap decoder** for graduated tokens (program
   `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`).
5. **Record slot numbers** with each event, to measure latency in slots.
6. **Predictor open problems 3–5** (accuracy only).
7. **Verify the pump.fun fee schedule** (1.25%/side default).

## Rules that hold across sessions

* Judge every model and strategy by `tartar profit` on the **latest**
  launches. Pick thresholds on validation only, and quote 90% intervals by
  token.
* No real-money trading code without the user's explicit request.
* Never trade the v1 model's expected return: it loses ~43% per trade on test
  launches (see `profitability.md` §3.2).

## Done

* Predictor v1, scam filtering, online-model fixes (predictor session).
* `tartar profit` and the profitability findings (profitability session,
  branch `claude/profitability-backtest`, on `main`).

## Log (newest first)

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
