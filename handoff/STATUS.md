# STATUS: read this first

> **WHERE WE STAND (2026-10-12 ~22:00 UTC, full overview; update this block, don't append to it).**
> * **Rule:** only US-expressible strategies can go live (AJ, 10-11). Hyperliquid and Jupiter are paper research only.
> * **Nothing is profitable yet on a venue a US person can use.** US candidates in paper from 10-12: `us_capit`
>   (capitulation bounce; also `us_capit_fast`, `us_capit~wide`), `us_volspike`, mirrored to an Alpaca **paper**
>   account, and `cde_vol_momentum` on Coinbase's US perps (+0.39%/wk test, CI includes zero; needs ~$8k).
> * **US costs:** Coinbase 0.90% taker / 0.50% maker since 2026-09-16; Alpaca ~0.39%/side (the first live US
>   route if one is approved). Details `reviews/gap-review-2026-10-11.md`.
> * **Live rule ADOPTED** (AJ, 10-12 22:45 UTC): `live-rule-us.md` v2, us_capit only, on coins whose measured Alpaca
>   cost is at most 0.50%/side, $100/trade, $250 stop. Gate progress: REPORT line "Live rule gate". Real money still
>   needs AJ to fund an Alpaca live account and a live route built after that; neither exists.
> * **Every finding (Claude and Codex) in one table:** `findings.md`. Check it before proposing an idea.
> * **Plan:** `plan-2026-10-12.md` (section G is the order of work). **Map of the repo:** `README.md` and `handoff/README.md`.
> * **Paper tests running:** see *Active*. Every registered test is scored by a routine and/or the weekly
>   `final-scores` Action (`experiments/final_scores.py`), which writes `RESULT-auto-<date>.md` when one is due.
> * **History** (pump.fun phase Queue/Blockers, older Log, *Recent results*): `archive/STATUS-history-to-2026-10-10.md`.

Claude threads in the TarTrade project work in parallel lanes; AJ's ChatGPT (Codex) works in its own lane
under `AGENTS.md`. This file is the shared board: who is working, on what, and what comes next. Topic
documents hold the detail; `handoff/README.md` lists them all.

## Protocol

Every Claude session is a thread in the TarTrade project; the coordinator (the project's channel
session) is the only one that pushes to `main` (AJ, 2026-10-10 20:47 UTC).

1. **Start:** `git fetch origin && git checkout -B <your branch> origin/main`. Read this file and
   project memory, then the topic document for your task.
2. **Claim before working:** say so in your thread; the coordinator records it under *Active*. Don't
   take work another lane holds.
3. **Finish a step:** rebase on `origin/main`, run `pytest`, write a git bundle to
   `/mnt/project-files/handoff-bundles/<lane>-<UTC time>.bundle` (state its base and head commits), and
   message the coordinator with the path and merge notes. Don't push `main` yourself.
4. **The coordinator** secrets-scans and pushes the bundle (the repo is PUBLIC: never commit keys), then
   tells the thread it landed. Merge rule: keep `main`'s side for the live paper book files
   (`autotrade/{state.json,journal.jsonl,trades.jsonl,equity.jsonl,REPORT.md,health.json,changes.jsonl,alpaca_fills.jsonl}`);
   keep both sides in this file.
5. **Log** each landed step with one entry under *Log* (newest first). Keep edits here small: other
   threads append too.
6. **Actions:** no always-on or self-restarting jobs (`handoff/reviews/tos-check-2026-10-10.md`).
   Real SOL or real orders need AJ's go in words.

## Active

Lanes as of 2026-10-12 (all paper only). Owner thread names are the project's thread titles.

* **Full project overview and alignment (from 2026-10-12 ~21:30 UTC):** one findings ledger (`findings.md`), board,
  plan and topic docs brought into line. Done when it lands; then the ledger is kept by whoever lands a result.
* **Live rule (thread "Full project overview and alignment"):** v2 adopted 10-12; owns `tartar/autotrade/live_gate.py`
  (gate line in REPORT, Alpaca cost health check). Next step needs AJ: fund an Alpaca live account when the gate is met.

* **ChatGPT lane (Codex, thread "ChatGPT lane with Claude review", from 2026-10-12):** AJ's ChatGPT works only on
  `codex/*` branches and opens PRs into `main`; rules in `AGENTS.md`. Claude reviews each PR before it lands;
  approved PRs land on main through the coordinator's bundle push. A twice-daily routine (01:07/13:07 UTC) checks for new
  `codex/*` work; open Codex PRs are watched.
  Proposed claim: CAPIT chronological cash-account controls on the existing fixed cohort; locked costs/delays/stops and matched full-account references (`codex/capit-account-controls`; review `reviews/capit-account-controls-2026-10-13.md`).
  Landed 2026-10-13 (reviewed by Claude): PR #4 US paper-evidence audit (`reviews/us-paper-evidence-2026-10-13.md`;
  its gate-input defects fixed in `live_gate.py` in the same landing), PR #5 CAPIT replication + whole-episode
  robustness (`reviews/capit-robustness-2026-10-13.md`), PR #6 CDE contract sizing (`reviews/cde-capit-economics-2026-10-13.md`).
  Landed 2026-10-12 (reviewed by Claude): the CodexCoinHunt import under `codexcoinhunt/` (paper-only memecoin
  research archive, not wired into the agent; `handoff/codexcoinhunt.md`, review `reviews/codex-review-2026-10-12.md`)
  and the connected-project map `CONNECTED_PROJECTS.md`. Suggested next claims: `plan-2026-10-12.md` section E.
  Proposed claim 2026-10-13: CAPIT feed-coverage diagnostic (`reviews/capit-feed-integrity-2026-10-13.md`); synthetic missing-data/cursor evidence only; owner implementation unchanged.
  Proposed claim 2026-10-13: CDE cost-documentation addendum (`reviews/cde-cost-documentation-2026-10-13.md`); dated exchange fees, retail/REST units unresolved; docs only.
  Proposed claim 2026-10-13: paper box evidence audit, synthetic execution evidence and prospective comparison protocol (`reviews/box-evidence-audit-2026-10-13.md`, `reviews/box-execution-evidence-2026-10-13.md`, `codex/box-evidence-audit`); docs only, 19 offline cases/98 diagnostic outcomes, tested valued residuals caught and halted; no production occurrence or profitability claim; Alpaca/agent owner implementation unchanged. Historical fixed-cost hurdle: $1.31–$1.52/month incremental model advantage at $100 stakes (`reviews/box-fixed-cost-hurdle-2026-10-13.md`); actual box economics remain unmeasured.
* **Continue TARTAR handoff session:** owns `autotrade/` and `tartar/autotrade/` (the hourly agent).
  Agent spec pass done 10-11 (separate hl/us risk books, error-halt retry, per-book drawdown stops). Next: plan A1, A2.
* **Alpaca paper route (thread "Alpaca paper trading route"):** owns `tartar/autotrade/alpaca.py`. `us_capit` and
  `us_volspike` entries/exits also go as market orders to an Alpaca **paper** account (paper endpoint only; no live
  Alpaca route), fills in `autotrade/alpaca_fills.jsonl` and trade meta `alpaca` (measured cost per side vs the
  assumed 0.39%). AJ's paper key secrets work (key check passed 10-11 17:20 UTC); `us_capit_fast` is mirrored too.
* **Real-money cost test, fresh key:** holds the wallet (0.0466 SOL, no spending). Work done and on `main`.
* **Improve the agent's trading skills:** intraday hunt done; wick-bounce pre-registered (paper from 10-12).
* **Continue Jev cost handoff session:** scheduled scoring routines: 10-14 HL cost rescore, 10-24 jevtrader
  readout, 10-30 dip forward test, 2027-01-08 hedged JLP, 2027-04-09 pumpflow, 2027-10-21 momentum. Each
  hands a bundle to the coordinator.
* **Collectors (no session needed):** `paper-tests.yml` (JLP every 4 h, dip cohort daily),
  `pumpflow-paper.yml`, `perps-ctx.yml` (OI/funding + HL 1h candles), `hl-book.yml`, `health.yml`,
  weekly `autotrade-search.yml`. `recorder.yml` and `pumpflow-live.yml` are off (manual runs only).
* **F1 who-trades forward test: CLOSED** (2026-10-10 23:40 UTC, coordinator). It needs pump.fun data from the
  recorder, which is off since the 2026-10-10 terms decision, and pump.fun launch trading is a closed lane. Reopen
  only if a compliant collector is approved. No job or routine scores it.
* **Pumpflow forward test (E1): still collecting; scoring owned by "Continue Jev cost handoff session"
  (one-shot routine 2027-04-09 06:00 UTC).** It does not depend on the disabled
  `pumpflow-live`: `pumpflow-paper.yml` records DefiLlama's daily revenue plus the HL PUMP mid (one small commit a
  day) and is running. Scored after 2027-04-08 with `pumpflow_paper.py evaluate --final`. Expect a fail: at
  DefiLlama's ~25 h publish delay the backtest has no edge (`edge-hunt.md` E1 "publish delay"); the agent's
  `pumpflow` strategy is disabled for that reason.
* **Done threads (no lane):** Codex review and project layout (10-12), Trade timing and exits, What we may have
  missed, Lightweight agent optimizations, Full system audit, Check collectors against terms, Move project into
  Continuations, Import old account's memory.

## Rules that hold across sessions

* **US-only** (AJ, 10-11): only venues a US person may use can go live. Hyperliquid and Jupiter stay paper research
  (`us_only: true` in `autotrade/config.json`).
* **Paper only.** Real orders, real SOL or a funded live account need AJ's go in words. One session holds the
  wallet at a time (now: "Real-money cost test, fresh key", no spending).
* **Pre-registered tests are frozen** (`preregistration/FROZEN.sha256`); add a dated `ADDENDUM-*` file instead.
* **No always-on or self-restarting Actions**; nothing scheduled more often than hourly
  (`reviews/tos-check-2026-10-10.md`).
* **Lightweight work** (AJ, 10-11): small cheap steps; big data pulls or grids only where a task needs them.
* **Count every real cost** (fees, spread, slippage, latency) and judge results in account dollars.
* **No Jev calls from TARTAR** (AJ, 10-09; Jev stays off). Cached answers in `handoff/data/jev/` may be read offline.
* **Weekly usage limit:** near the limit, checkpoint everything to the repo and leave each unfinished task on this
  board.
* Pump.fun-phase rules (the live fast loop, `tartar profit` on latest launches, the v1 model) are in
  `archive/STATUS-history-to-2026-10-10.md`; that lane is closed.

## Log (newest first)

* **2026-10-13 ~06:30 UTC, thread "Perfect trading system vs ours": AJ "approved for all"** (the review's three gaps).
  (1) Hourly Alpaca account-vs-book check: `alpaca.reconcile`, state `alpaca.reconcile`, health "Alpaca account vs book"
  (red on any mismatch or an order open >1 h), REPORT line. (2) US ETF capitulation study: **fails** (validation 2017-21
  negative; `findings.md` §3). (3) Always-on box software `tartar/autotrade/box.py` + setup `box.md` (paper, second Alpaca
  paper account, results on branch `box-data`); AJ is setting up the server.

* **2026-10-13 ~05:45 UTC, thread "Perfect trading system vs ours": ideal small-US system vs ours** (`reviews/perfect-system-2026-10-13.md`).
  Machinery is close to ideal; the gap is edges (one candidate, ~6 events/yr). Top gaps: test US stocks/ETFs on Alpaca
  (commission-free; added to `findings.md` §7), reconcile the Alpaca paper account with the book each run. No code changed.

* **2026-10-13 ~01:30 UTC, thread "Tune the agent for profitability": Coinbase US perp book at us_capit fills**
  (`tartar/autotrade/cde_book.py`, config `cde_book` on `us_capit`, `us_capit_fast`). Each fresh entry/exit records the
  same coin's -20DEC30-CDE top of book (half-spread, contract size) in the trade meta; the score shows the median
  half-spread. Tests whether perps beat Alpaca's ~0.39%/side in crash hours. Reporting only; fees not included. All 11
  coins have a perp, but contracts are ~$500-1,000 (SOL 5 coins, XRP 500), so a $100 stake can't use them.

* **2026-10-13 ~01:00 UTC, thread "Tune the agent for profitability": random-entry control in the paper score** (plan
  A2 live part, live rule item 6). `coinbase_pattern.py` prices each signal's control (mean return of entering the
  same coin at every hour within ±15 days, same delay and hold) once that window closes, and the score shows the
  excess over it with a CI by entry day; REPORT adds a "Random-entry control" line under the gate. Reporting only.

* **2026-10-12 ~23:00 UTC, overview thread: live rule v2 adopted, gate built** (AJ: "approved, move forward when
  ready"). `tartar/autotrade/live_gate.py` reads the Alpaca paper fills: REPORT shows the gate (crash days, trades,
  mean net, median cost, coin screen) and health goes yellow above 0.50%/side measured cost, red above 0.60% (plan
  A1 and A3). Paper only; no live route.

* **2026-10-12 ~22:30 UTC, overview thread: live rule DRAFT v2** (`live-rule-us.md`, not adopted; AJ asked for a
  redraft that fits the overview). Adds a standing eligibility checklist, a per-coin Alpaca cost screen (AVAX, BCH,
  LTC books ~0.55%/side), a gate judged on Alpaca paper fills, stops in account dollars, and scaling that needs the
  account up in dollars and a positive excess over random entries. Still us_capit only, $100/trade, $250 stop.

* **2026-10-12 ~22:00 UTC, full overview thread** (`findings.md`). Every idea Claude or Codex tested is in one
  ledger with its status, after-cost evidence and source. Claude's and Codex's numbers agree (Alpaca, PumpPortal
  and PumpSwap costs; memecoin entries no better than random). Fixed: the plan's scoring calendar (now matches
  `final_scores.py`, incl. cde 2027-10-19), its done privacy item, stale thread names and lanes here, the stale
  status header in `edge-hunt.md`, the agent's strategy table in `autotrade.md`. Plan section G sets the order:
  AJ's live-rule decision, then A1/A2, no new research lanes until a trigger fires.

* **2026-10-12 ~19:50 UTC, Codex review and layout thread** (`reviews/codex-review-2026-10-12.md`, `plan-2026-10-12.md`).
  Codex's CodexCoinHunt import landed as a separate archive (SLR-0.2 has zero verified trades; not wired in).
  Frozen preregistrations pinned by SHA-256 (`tests/test_prereg_frozen.py`). Retired docs and old board history
  moved to `archive/`; repo maps in `README.md` and `handoff/README.md`.

* **2026-10-12 ~00:20 UTC, overall-review thread: draft live rule for US strategies** (`live-rule-us.md`, not
  adopted). Only `us_capit` eligible; start gate after 3 paper crash days; $100/trade, $250 loss stop; scale after
  10 live crash days. Needs AJ's go, a funded Alpaca live account and a live route (not built).

* **2026-10-11 ~20:40 UTC, overall-review thread** (`reviews/overall-2026-10-11.md`). No US registration can
  clear its CI bar in 52 weeks (too few independent events), so AJ needs a go-live-small rule. CAPIT holds on 10
  extra US coins (+4.52%/trade, CI spans zero, mostly the same crash days); VOLSPIKE does not (−0.30%). New paper
  research line `us_capit~wide` (shadow, no twin, no Alpaca mirror); `coinbase_pattern` passes `shadow` to its trades.

* **2026-10-11 ~19:40 UTC, trade-timing thread: timing and exits on the US strategies** (`reviews/timing-2026-10-11.md`).
  Exits stay as registered (24 exit variants and 8 CDE holding/lag/day variants, none survives). Capitulation
  bounces fade with delay: +4.11%/trade at 15 min, +2.97% at the registered 30, +1.93% at the ~90 min a
  next-run order gets. New paper research line `us_capit_fast` (`delay_bars: 1`) beside the unchanged `us_capit`.
* **2026-10-11 ~17:54 UTC, handoff session (`autotrade/`): book stops also pause that book's
  shadow variants and search candidates** (by their legs' venue), so a candidate builds no paper record while its
  book is stopped.
* **2026-10-11 ~17:48 UTC, handoff session (`autotrade/`): spec pass 7 (book stops stay in their book).**
  A 35% perps-book drawdown used to write `HALT`, stopping every strategy: a research Hyperliquid drawdown would
  have frozen the registered US tests mid-window. Each book's stop now blocks only that book's new entries
  (`state.book_halts`, shown in health; `resume book:hl` / `book:us`). `HALT` stays the manual kill switch.
* **2026-10-11 ~17:46 UTC, handoff session (`autotrade/`): spec pass 6 (REPORT.md easier to read).** The eight
  dip research variants now sit in a collapsed section, so the report opens on health, the US book line and the
  main strategy table.
* **2026-10-11 ~17:40 UTC, handoff session (`autotrade/`): spec pass 5 (health sees strategy failures).**
  A strategy halted by repeated errors, or erroring, never showed in health: only live halts and orphans did.
  Health now goes red for a halted strategy and yellow for one with errors, with the last error text.
* **2026-10-11 ~17:36 UTC, handoff session (`autotrade/`): spec pass 4 (US perps marks, capital note).**
  `cde_vol_momentum` marked its legs at yesterday's daily close, so its 12% weekly loss limit could react up to a
  day late; it now marks at Coinbase's last trade (ticker), falling back to the daily close. `handoff/autotrade.md`
  gives the US book's worst-case capital at registered sizes (~$4.4k spot for the two pattern rules, $1k a side
  for cde).
* **2026-10-11 ~17:34 UTC, handoff session (`autotrade/`): spec pass 3 (lifecycle for weekly books), paper only.**
  The demote/retire rules judged momentum books per leg: a 25% drawdown of one leg's notional (a $60 loss on a
  $1,000-a-side book of $250 legs) would have demoted a promoted book on an ordinary bad week, and a 30-leg
  rolling CI is really ~4 correlated weeks. Books (`week` + `leg_usd` trades) are now judged per week against the
  side budget: 13-week rolling CI, 35% drawdown (as the account stop), retire after 26 demoted weeks. Per-trade
  strategies are unchanged; registered verdicts are unchanged.
* **2026-10-11 ~17:28 UTC, handoff session (`autotrade/`): spec pass 2 (US book risk), paper only.** The
  perps risk layer counted `cde_vol_momentum` (US) in the Hyperliquid book: its sizing followed HL's weekly vol and
  an HL drawdown could have halted on US losses (and vice versa), while the weekly 12% loss limit skipped Coinbase
  legs entirely. Now two books (`perp_risk.BOOKS`: hl, us), each with its own vol target and 35% drawdown stop;
  the weekly loss limit covers Coinbase legs too (no funding).
* **2026-10-11 ~17:23 UTC, handoff session (`autotrade/`): spec pass 1 (reliability + reporting), paper only.**
  (a) A strategy halted by 3 straight errors now retries itself every 6 h (`risk.error_retry_hours`) and resumes
  on a clean step; before, one 3-hour Coinbase or Hyperliquid outage froze a registered test until someone typed
  `resume` (steps book retroactively, so nothing is lost). (b) Weekly book legs are capped by their side budget,
  not the $250 position cap: Coinbase's 23-coin universe makes 3-coin quintiles ($333 legs) that would have been
  refused, leaving a half book. (c) `coinbase_pattern`: a delisted pair (404) no longer errors both rules; an exit
  waits for its own candle instead of using a stale price. (d) REPORT.md: a "US book at a glance" line, a Venue
  column, US-usable strategies listed first; the daily-cap note now says it is per strategy.
* **2026-10-11 ~16:50 UTC, Alpaca thread: Alpaca paper mirror built** (`tartar/autotrade/alpaca.py`,
  config `alpaca_paper`, `tests/test_autotrade_alpaca.py`). Off until the two GitHub secrets exist; a key must open an
  active paper account (`PA...`) or nothing is sent. The key added to the cloud session's environment got 401 from
  the paper endpoint, so it was not verified.
* **2026-10-11 ~08:40 UTC, trading-skills thread: US500 trend closed; US lane stands down**
  (`edge-hunt.md` §N). 8 trend-timing rules on the S&P 500 (1950-2026) all lose to holding in train.
  US paper tests from 2026-10-12: cde-vol-momentum and the two us-patterns rules. Nothing half-done.

* **2026-10-11 ~07:30 UTC, trading-skills thread: Kalshi closed, nothing passes** (`edge-hunt.md` §M).
  16,342 settled sports/weather/economics markets, 24 favourite/longshot rules bought at the ask with
  Kalshi's fee: every band loses in train; the 0.95-0.99 favourites were +1.5% in 2025 only. With §L
  (D3 on Coinbase US perps, registered) and §K (two US-spot patterns, registered), the US lane has
  three paper tests from 2026-10-12 and nothing else.

* **2026-10-11 ~07:10 UTC, trading-skills thread: cde-vol-momentum addendum (funding, whole contracts)**
  before the window. Primary unchanged; secondary lines from `experiments/edge-hunt/perps/cde_rounding.py`:
  HL funding as a stand-in costs ~0.04%/week; rounding to whole Coinbase contracts builds 80% of the book
  at $1,000 a leg and adds noise as large as the edge (test +0.12%/week at $1k a leg, +0.30% at $5k, vs
  +0.39% unrounded). A live version needs ~$1,000+ a leg (~$8k gross).

* **2026-10-11 ~07:01 UTC, handoff session (`autotrade/`): the weekly search now hunts US-tradable rules**
  (gap review finding). New family **cde**: the same 95-rule momentum grid on Coinbase's US-perp coins
  (cde-vol-momentum's 23 coins, Coinbase daily history from 2021, $1M volume floor, 20 bp/side, no funding),
  one shared Bonferroni M (189), cde survivors queue first and paper-trade via `xs_momentum` `data: coinbase`
  (paper in every mode). Engine reproduces the registered cde study (train +0.51%/wk, val +1.08%). First run:
  no survivor (best penalized bound −0.20%). US-spot live route set to Alpaca or Coinbase post-only (Coinbase
  taker fails both rules' train); venue_costs now the addendum's lines (taker 0.91, maker 0.50, Alpaca 0.39).
  The registered cde-vol-momentum rule also paper-trades in the agent as `cde_vol_momentum` ($1,000 a leg).

* **2026-10-11 ~04:15 UTC, gap-review thread: what we missed** (`handoff/reviews/gap-review-2026-10-11.md`,
  paper only). (1) Coinbase US fees are 0.90% taker / 0.50% maker since 09-16, not 0.62%; Alpaca ~0.39%/side.
  At Coinbase taker cost neither registered US pattern passes its own study; addendum with real-cost lines
  registered before the 10-12 window. (2) Coinbase may route US customers to Deribit's ~90 crypto perps
  (CFTC 05-29; retail pending): vol-momentum on that coin list +0.68%/wk (last 52 wks +1.19). (3) Four tests
  had no final scorer: weekly `final-scores` Action added. (4) **For the autotrade owner:** the search only
  explores HL momentum (can't go live). Board: "where we stand" block at top.

* **2026-10-11 ~04:00 UTC, trading-skills thread (US-tradable lane): momentum on Coinbase US perps
  pre-registered** (`edge-hunt.md` §L). Coinbase's US perpetual-style futures cover 23 crypto coins,
  so long-short momentum is US-tradable. The registered D3 rule on those coins, Coinbase history
  2020-26 at 20 bps/side: train +0.51%/week, validation +1.08%, test +0.39% [−1.05, +1.94] (90).
  52-week paper test from 2026-10-12 (`preregistration/cde-vol-momentum/`, scorer
  `experiments/edge-hunt/perps/cde_forward.py`, free). Long-only spot momentum = holding everything.
  **Handoff session (`autotrade/`): candidate US paper strategy** (weekly, like vol-momentum). Kalshi next.

* **2026-10-11 ~03:55 UTC, handoff session (`autotrade/`): the two US-spot rules paper-trade in the agent**
  (strategies `us_capit`, `us_volspike`, kind `coinbase_pattern`, from 2026-10-12, $200 a trade). Same signals,
  timing and costs as the registration (exact parity with `patterns.run` on 2026-05..10: 3/3 and 27/27 trades).
  Paper book pays the registered 0.62%/side; `venue_costs` also reports Coinbase now (0.92%/side, fees raised
  2026-09-16) and Alpaca (0.39%/side). Coinbase-venue positions never get a live or Solana twin. Live US spot
  route scoped for Alpaca (cheaper, has a paper endpoint) and Coinbase in `handoff/autotrade.md`; nothing
  built, no keys. Health now also watches hl-book.yml, autotrade-search.yml and the HL 1h candle cache.

* **2026-10-11 ~03:30 UTC, trading-skills thread (chart patterns, US spot): two weak rules
  pre-registered** (`edge-hunt.md` §K). 24 long-only rules on 11 Coinbase coins, entered 30 min after
  the hourly close, 0.62%/side. Capitulation bounce (test +5.8%/trade [−1.5, +11.4], 28) and
  volume-spike follow-through (+1.3% [−1.9, +4.5], 87) registered for 52 weeks from 2026-10-12
  (`preregistration/us-patterns/`, scorer `experiments/edge-hunt/patterns/pattern_forward.py`).
  Wick bounce, breakouts, RSI oversold and squeezes fail at US costs. **Handoff session
  (`autotrade/`): two candidate US-spot paper strategies** (hourly checks; reproduce the scorer).

* **2026-10-11 ~02:50 UTC, agent optimizations thread: drags measured, one live-only fix owed** (`handoff/reviews/drags-2026-10-11.md`). Dip fetch capped at 600 s a run and health commits only on change (d53c531). Wick-bounce entering ~20 min late: +17 bp/trade [-4, +39] on 409 trades, so late entry is no drag; hourly runs start 14-26 min late but no strategy loses to it; maker orders would save ~$1/week at go-live size (not built). **Go-live item (jlp_hedged):** the live JLP rebalance must resize each short by the difference, not close and reopen it (now ~7.7 bps of the basket per rebalance live vs ~0.4 on paper). Paper only, no keys.

* **2026-10-11 ~02:40 UTC, handoff session (`autotrade/`): US-only venues** (AJ: "We only want US-expressible
  options"). Hyperliquid and Jupiter bar US users, so `us_only` blocks them in mode live; their strategies stay
  on paper as research (AJ's choice). Pump.fun/PumpPortal stay. A US version of momentum (long top quintile
  on spot, BTC-hedged on Coinbase's US perp) nets ~+0.05%/wk, negative without the best 5 weeks: the edge is
  in the short leg (`autotrade.md` "US-only venues").

* Older entries (2026-10-10 and earlier), the pump.fun-phase Queue, Blockers, Done and *Recent results* are in
  `handoff/archive/STATUS-history-to-2026-10-10.md`.
