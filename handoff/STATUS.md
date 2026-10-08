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

_(nobody)_ The profitability session's last task (Jev harness) is landed on `main`; see the log.

## Blockers (need the user)

* **Network:** in the profitability session's environment, the proxy refuses
  `api.mainnet-beta.solana.com` and `api.dexscreener.com` (HTTP 403), so it
  cannot record. The user can allow them under the environment's Network
  access setting. If your environment can reach them, **you** should run the
  recorder (see the predictor handoff, section 14) and commit the new
  `data/raw/*.jsonl.gz` hours to `handoff/data/raw/` (each hour is a few MB;
  keep every file under 50 MB).
* **TypeSafe Jev key:** the user has one. They were told to add it as
  `TYPESAFE_API_KEY` (Network secrets or an environment variable) and to
  allow `api.typesafe.ai`. **Never ask for the key in chat.** A new session
  picks it up.
* **Private RPC:** the public RPC misses ~7% of a typical token's trades, more
  for busy ones, and adds delay. A Helius, QuickNode or Triton websocket in
  `SOLANA_RPC_WS` fixes both. Ask the user.

## Queue (ranked by expected effect on profit)

1. **More data.** Record 24 h or more (needs network). Then retrain
   (`tartar train --raw data/raw`) and rerun `tartar profit`. Every other item
   is limited by the 2.7 h recorded so far.
2. **Run TypeSafe Jev through `tartar decide`** (user request). "jev" is
   TypeSafe AI's decision model (state + typed questions → calibrated
   probabilities), not Jito. The user chose **paper trading first**.
   * If `TYPESAFE_API_KEY` is set and `api.typesafe.ai` is reachable: first
     check `build_request` / `parse_probability` in `tartar/jev.py` against
     TypeSafe's OpenAPI spec (docs.typesafe.ai). They are unverified. Then run
     `tartar decide` (and with `--hold 600 --take-profit 100 --stop-loss 30`).
     About 1,056 calls (validation + test launches), cached.
   * Report test results next to the other scorers, plus Jev's latency.
     Latency matters: the only edge found (§3.4) closes within ~0.4 s, so a
     network round trip per decision only fits the slower +20 s decision.
   * If Jev beats the baselines on test launches: build a live **paper
     trading** mode (`tartar paper`?) that screens real launches, asks the
     scorer, and logs simulated fills from the chain stream. It needs
     network access for the Solana RPC. No real money without the user's
     explicit go-ahead.
   * Also record **slot numbers** with each event, so latency can be
     measured in slots, not receive time.
3. **Longer holds on screened tokens** (10–90 min) once data exists.
   Costs are fixed per trip, so longer moves have a better chance of
   clearing them.
4. **PumpSwap decoder** for graduated tokens (program
   `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`), so the recorder follows
   tokens after migration.
5. **Predictor open problems 3–5** (bands over-cover, in-candle median,
   underconfidence): accuracy items with no measured profit effect yet.
6. **Verify the pump.fun fee schedule** used as the 1.25%/side default in
   `tartar/profit.py`.

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

* **2026-10-09 ~00:30 UTC, profitability session:** The user's "jev" API is
  TypeSafe's Jev decision model; they chose paper trading first and have a
  key. Built `tartar decide` + `tartar/decide.py` (causal launch states;
  rule, flag, LightGBM and Jev scorers; validation threshold, test report)
  and `tartar/jev.py`. Could not verify Jev's request format: docs and
  api.typesafe.ai are unreachable here, and an SDK download was refused by
  the permission classifier. Told the user to store the key as
  `TYPESAFE_API_KEY`. Fair flag test: −1.8% vs −5.1% per trade, still
  negative. Everything is on `main`.

* **2026-10-08 ~23:40 UTC, profitability session:** Finished the scam-filter
  study (§3.5): the existing screen and a learned 20 s screen do not make
  launch buying profitable; five flags reliably mark worse trades. Fixed a
  simulator flaw: exits after a recording cut used a stale price; they are
  now dropped (`TokenData.end_reason`, `Curve.cut`). Experiment scripts are
  in `handoff/experiments/`. The user then asked to use their "jev" API for
  split-second decisions; I asked what it is before building anything.

* **2026-10-08 ~22:45 UTC, profitability session**
  (https://claude.ai/code/session_01U4x5qUJYMStcujpyLJgQ8N): Added
  `tartar profit` and `handoff/profitability.md`. Result: no strategy is
  profitable at realistic costs on the recorded data. The only edge is
  same-block sniping, which a public RPC can't reach. Set up this board and
  landed everything on `main`. Recording is blocked by the network policy.
  Next for me: queue item 2 on the existing data.
