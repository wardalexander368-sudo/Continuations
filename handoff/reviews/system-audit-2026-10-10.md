# System audit, 2026-10-10 (~23:00 UTC)

Asked by AJ: "audit the full system and look for improvements". Scope: the paper agent (`tartar/autotrade/`,
`autotrade/`), the weekly search, collectors and workflows, tests, and the handoff docs. Settled questions
in project memory (closed lanes, the perps audit, dip rule closed, ToS decision) were not reopened.
Findings are ranked by how much they move profit or protect money. "Fixed here" items are in this
thread's bundle; everything touching `tartar/autotrade/` or `autotrade/` is a recommendation for the
`autotrade/` owner ("Continue TARTAR handoff session").

## Test suite: the real state

On main (13040f7) with every dependency installed: **281 pass, 1 skip, 0 fail** after the fix below.
Before it, 279 pass and 2 fail. The "43 failing" report came from an incomplete environment, not broken code:

* `solders` is imported by the Solana senders and two test files but was never declared in
  `pyproject.toml`, so `pip install -e .[dev,live]` leaves two test files erroring at collection.
  **Fixed here:** `solders>=0.21` added to the `live` extra.
* Two `tests/test_market.py` tests failed whenever `PUMPPORTAL_API_KEY` is set (it is, in project
  sessions), because `open_market` picks the PumpPortal feed from the environment. **Fixed here:** an
  autouse fixture in `tests/conftest.py` clears every live key (`PUMPPORTAL_API_KEY`, `TARTAR_WALLET_KEY`,
  `TARTAR_LIVE_APPROVED`, `HYPERLIQUID_*`, ...) for each test, so results no longer depend on the session
  and tests never see real keys.
* **No workflow ran the suite.** `hl-testnet.yml` runs three files on a few paths. **Fixed here:**
  `.github/workflows/tests.yml` runs the full suite on pushes and PRs that touch `tartar/`, `tests/` or
  `pyproject.toml` (bot data commits don't trigger it). It uses a sparse checkout (~150 MB instead of the
  ~1.4 GB working tree); verified locally that the sparse tree passes the whole suite.

## 1. Money and scoring (highest impact)

### 1a. At go-live the perps book would be five longs, not a hedged long-short book (recommendation, autotrade owner)
Live and dry twins are sized by `live.perps` (`PERP_DEFAULTS` in `perps.py`): `max_leg_usd` **$12** per
twin and `budget_usd` **$60** across all perps strategies. The broker takes intents in order, and
`XSMomentum.step` builds `new_w` as longs first, then shorts. The budget is shared across all positions, so the first five legs get twins and every other leg is skipped
for budget: **the live book would hold about five longs of `xs_momentum` (the first perps strategy in
the config) and no shorts.** Open wick-bounce twins use up the same $60. That is a directional long bet, not the market-neutral book that was backtested (+1.0 to +1.4%/wk),
and live sizing ignores `leg_usd / q` and the book volatility scale. The dry mirror will show this on the
first booking (Wednesday 2026-10-14).
**Fix:** size perps twins from the paper leg (`intent.notional_usd x live_fraction`) with a budget that
covers the whole book (both strategies, both sides), and make a week's legs all-or-nothing: if the book
can't be opened balanced (budget, the $10 minimum, a failed leg), open none and log why. Re-check against
the go-live sizing on the board ($2,000 account). Add a test that a week's twins are dollar-neutral.

### 1b. The dip strategy can halt the whole agent, including the perps forward tests (recommendation)
`risk.check_daily` sums realized + unrealized P&L of **all** registered strategies for the UTC day, and past
`daily_loss_cap_usd` ($1,000) sets `state.halted`, which blocks **every** new entry until someone runs
`resume` by hand. Today the dip strategy alone stands at about **-$572** (realized -$485, open -$88).
The dip rule is already closed for real money and is paper-only to finish its registered test. One bad
memecoin day would stop the Wednesday perps rebalance (paper and twins) and leave a hole in the
52-week momentum and vol-momentum tests, the strategies most likely to go live.
**Fix:** apply the daily cap per strategy (or per venue), not agent-wide; or count only strategies that
can trade live; and let a daily halt clear itself at the next UTC day, logged as a change. Keep `HALT`
(the file) as the agent-wide switch.

### 1c. Wick-bounce is scored at prices an hourly agent can't get (recommendation)
The rule enters at the wick hour's close and the agent books it there retroactively. A real twin can only
trade when the next run starts. Scheduled runs on GitHub start late: today's runs started 8 to 14 minutes
after their cron minute, and the 21:05 autotrade run never happened. On HL's own 1h candles (29 trades,
2026-03..10), entering one hour late moved the mean from **-137 to -236 bp/trade**. That's a small sample from a bad
period, but the move is large. A "pass" in 2027 could promote a rule the agent can't execute.
**Fix:** keep the registered statistic as is, and add a second, execution-realistic score as the dip
strategy already has (`execution.entry: "schedule"`): enter at the first run after the wick hour, priced
from 5-minute candles, and require that version to clear costs before promotion to live. The
same applies to any future intraday rule: hourly cron plus GitHub delays is the execution model.

### 1d. The dip strategy's paper entry assumes :07; runs actually start around :15 to :20 (minor)
`execution.run_minute: 5` and `run_lag_s: 120` model entry at :07. Observed starts are 8 to 14 minutes later,
and sometimes a run is dropped. The replay says a 30-minute delay costs about 0, so the effect is small. Measure
the real start time from `run.json` / the commit time and use its median.

### 1e. The weekly search re-tests the same 94 rules every week (minor)
`M` counts distinct rules ever tested, not looks. Re-running a fixed grid weekly on a sliding window is
repeated testing: a rule that narrowly fails can pass by chance on a later week. The 26-week paper
stage catches false positives, so the cost is wasted paper slots, not money. **Fix:** count looks
(rules x runs) in the Bonferroni `M`, or only re-test a rule once 26 new weeks have arrived. Separately, the
grid is the whole of "self-improvement" today. Once it's exhausted, the agent stops finding anything new.
Widening the family is a research question for the board, not a bug.

## 2. Go-live path on Hyperliquid (recommendations)

* **The Hyperliquid secrets never reach the agent.** `autotrade.yml` passes `TARTAR_LIVE_APPROVED`,
  `TARTAR_WALLET_KEY`, `PUMPPORTAL_API_KEY` and `JUPITER_API_KEY`, but not `HYPERLIQUID_AGENT_KEY` or
  `HYPERLIQUID_ACCOUNT`. `handoff/autotrade.md` tells the user to set them as secrets. Following the
  checklist would leave perps silently on paper. It fails safe, but go-live wouldn't happen. Add both to
  the workflow's `env` block in the go-live change, together with 1a. Unset secrets arrive empty, so this is
  safe to land early.
* Kept legs roll on without being resized. Over weeks, a kept twin's notional drifts with price and the
  book scale. Resize kept twins to the new target when the drift is more than about 20%.
* The account drawdown stop measures against config `leg_usd`, not the vol-scaled size (0.5x to 1.5x), so
  at 1.5x the 35% stop really fires at about 52% of deployed notional. Use the deployed notional.
* The open question in memory still stands: Hyperliquid's terms bar US persons, and GitHub runners are in
  US data centres. Settle it before real orders go out from Actions.

## 3. Workflows and data

* **The JLP check-in lost a run to a Jupiter 503** (paper-tests run 38085172068, 20:49 UTC). The
  optional cost quote raised after 6 retries and dropped the whole snapshot, so health is red on "JLP
  snapshots 18 h old". **Fixed here:** `jlp_paper.py snapshot` carries the last quote forward, flagged
  with `stale_from` and `error`, when the quote fails. Delta and HL marks are still recorded. The next
  scheduled run (00:40 UTC) should clear the red.
* **Disabled workflows still had their cron lines.** `recorder.yml` (every 2 h, 5.75 h runs, the
  always-on pattern) and `pumpflow-live.yml` were only disabled in GitHub's UI. A re-enable, a repo move
  or a fork would bring the cron straight back. **Fixed here:** the `schedule:` blocks are removed (manual
  runs only), with a comment pointing to the ToS review.
* **Repository weight.** `.git` is 766 MB, and `handoff/data/` holds 704 MB, mostly raw pump.fun recordings
  (`raw-clever` 332 MB, `raw-v3` 196 MB) from closed lanes. Every hourly job checks all of it out. That's
  slow, close to GitHub's 1 GB guidance, and part of the "burden" the ToS review warned about.
  **Recommendation:** use sparse checkouts in the hourly workflows (`autotrade`, `health`,
  `pumpflow-paper`, `hl-book`, `perps-ctx`). Each needs only `tartar/`, `autotrade/` and the
  `handoff/data`/`preregistration` paths it reads. Don't rewrite history, because AJ's Mac follows main
  with `--ff-only`.
* **Commit noise.** Main gets about 157 commits a day: 60 autotrade, 9 health, plus collectors. `health.yml`
  commits every hour even when nothing changed ("Health: red 2 red" repeats). Commit health only when its
  status or the list of red checks changes. `pumpflow-paper` polls hourly for a daily DefiLlama series;
  every 6 h would be enough.

## 4. Docs and the board

* `handoff/STATUS.md` is 1,377 lines. Its *Active* section still lists nine claims from threads that memory
  shows as done or retired (funding-spike, token-unlock, edge hunt E, agent-machinery, recorder, curve
  retrain, dip/jevtrader, handoff session...). Its *Protocol* still says "two sessions on different
  accounts" and "push straight to main", which contradicts AJ's bundle-to-coordinator push routine.
  **Recommendation (coordinator):** trim *Active* to the four live lanes in memory, replace the
  Protocol with the bundle routine, and move the Log older than 2026-10-10 to `handoff/log-archive.md`.
  This audit only adds a log line, to avoid clashing with other threads' edits.
* `pyproject.toml` still describes the project as a candle predictor for new Solana tokens. Update the
  description to the trading agent.

## What was checked and found sound
The live gate (`gate.py`: mode, matching approval secret, keys, kill switches; closes still allowed under a kill);
idempotent perp orders (client order ids, adopt-on-retry, orphan + halt on a failed close); the xs/vol
momentum step (signal at Monday close, entry at Tuesday close, no lookahead in universe or ranking,
funding sign and hour alignment); the weekly loss stop; the promote/demote/retire rules and their scorer
isolation (a scorer error can't move a strategy); the hourly cadence and concurrency (no self-restarting
jobs remain).
