<!-- read:history: workflow section summary as of 2026-10-09 12:56 UTC; 'verify-*' files are fact-checked, 'read-*' are not -->

## Timeline, sessions, branches and how the work is coordinated (as of 2026-10-09 12:56 UTC)

**Sources:** `git log` (122 commits, 2026-10-08 05:20 UTC to 2026-10-09 12:55 UTC), `git for-each-ref refs/remotes` (11 remote refs), and `handoff/STATUS.md` (516 lines) as it stands at HEAD = origin/main = `6a6b1a8`. Each session is identified by the `Claude-Session:` trailer on its commits.

**Terms used below:**
- **Bonding curve:** the pump.fun pricing contract a new token trades on at launch.
- **Graduation:** the curve completes and the token moves to a **PumpSwap** pool, a regular exchange pool.
- **Slot:** one Solana block time, about 270 ms.
- **bps:** basis points, 0.01%.
- **Paper trading:** simulated trades with no money.
- **Pre-registration:** the rule and its test are written down before the evaluation data is looked at.
- **Fast-forward main:** move `main` to a branch's tip without a merge commit.
- **Claim:** a line in STATUS saying "I am working on X".

---

### 1. Timeline in phases

All times are UTC unless a source gives another zone.

| Phase | When | Who | What was built or learned (milestone commits) |
|---|---|---|---|
| 0. Repo created | 2026-10-08 00:20:54 -0500 (05:20 UTC) | StaticPush7217 (the human author) | `6452553` Initial commit |
| 1. Build the predictor | 10-08 05:58 to 21:21 | Predictor session | `1db2ce7` live next-candle close predictor (PumpPortal websocket, DexScreener, GeckoTerminal; online per-token model; dashboard). `05ac2e8` global LightGBM model and recording pipeline. `f09346d` reads pump.fun trades straight from the chain, because PumpPortal now needs a funded API key. `8ecceae` scam filtering (live risk level, launch screening, `scan`). `9d8ea8a` fixes from an accuracy review, plus a capture measurement (the free public RPC drops notifications; one busy token had 38% of its trades captured). `08aca15` handoff doc and v0 model: 786 launches, hit 81.5% vs stated 81.7%. `8c5b513` tolerates disconnects every 10–30 s. `7333656` online-model calibration fixed and **model v1** installed: 3,523 launches, 154k rows, 4.9% lower error than naive at the open, live blend 7.0% better than naive. `eb4470b` notes that main carries the work. |
| 2. Profitability and the shared board | 10-08 22:02 to 23:12 | Profitability session | `b7f99ba` `tartar profit` (net SOL after fees, slippage and latency): **no strategy profitable; trading v1's expected return loses ~43%/trade**. `a7057aa` **STATUS board created** (22:03:49). `57626ed` scam flags as filters. `87ff399` `tartar decide` scorers, including TypeSafe Jev. `e97c1a5` fast loop (paper) and slow-loop review. `22e5bd4` hands the fast loop to a Jev session. `c855def`/`ad02b27` Jev evaluated offline: no edge at 20 s. `58851a2` Jev shadow mode. Network opened 22:35 and the Jev key was set 22:40 (STATUS.md:58-60). |
| 3. Live paper fast loop with Jev in shadow | 10-08 23:44 to 10-09 05:52 | Jev session | `cd0df5a` claim. The container was suspended repeatedly: the loop died ~23:50, 00:10, 02:54, 03:24 and 03:33, and keepalives did not help (`24c7850`). `e290152` slow-loop cycle 1: 125 launches, 27 paper trades, mean −2.0%. `c171e4b` cycle 2: 352 launches, 68 paper trades, mean −1.4% (90% CI −9.2…+7.8%), **Jev shadow shows no signal**. The loop has been stopped since 03:39, pending the user. |
| 4. Data plumbing and predictor v2 | 10-08 23:33 to 10-09 01:58 | Predictor session | `6aad9de` predictor open problems 3–5 (band reporting, late-candle median shrink, blend prior 0.95; live edge +7.5%/+7.8%). `8265852` Solana slot recorded on every event. `3f57013` PumpSwap decoder. `79d1439` decodes quote-paired pump.fun V2 curves (curves priced in USDC, stocks and other tokens instead of SOL). `5cef977`/`c7c298d` slot latency. `a08fbc4` **predictor v2** (5,790 launches, 251k rows). `a8c6b13` 15s/30s/5m models. `1b2745e` records graduated tokens' PumpSwap trades. `01f3a15` `watch` continues through graduation. |
| 4b. Launch-buying strategies closed | 10-09 00:15 to 02:29 | Profitability session | `1811de3` Jev on metadata: no added value. `e10dbfa` entry speed in slots: **only the creation-slot bundle profits; launch buying closed**. `e2b8de9` graduation run-up: a false edge from two biases. `d452865` established memecoins: no reliable edge; the dip rule is pre-registered as a rolling forward test (cohort 1 at `89e228e`, 02:27). |
| 5. jevtrader link and SOL-USD costs | 10-09 03:35 to 05:34 | Profitability, then predictor session | `cb7b37d` read the user's jevtrader repo (sealed until 2026-10-23); on-chain SOL-USD costs **~0.5 bps/fill vs 90 bps at Coinbase (quotes)**. The profitability session's last commit is 03:49. `85a94a9`/`0329d8e` out-of-fold median shrink (predictor). `f8fee8e` second cost window, $10k size and quote decay. |
| 6. Research session | 10-09 04:07 to 06:01 | Research session, on its own branch | `154013a` **PumpSwap fees 1.20–1.25%/side** on young tokens (the project had assumed 0.30%). `87155f6` study 11a pre-registered. `c20ac05` longer holds: no edge. `1d0952e` Jev carve-out DRAFT. `a128873` copy-trading: no edge. `e56036e` PumpSwap model for `watch`. `fa05f96` scam flags validated (learned P(rug) AUC 0.93). `c70be54` handoff. |
| 7. User decisions, then the clever session | 10-09 06:23 to 12:02 | Clever session | `b145bfc` merges the research branch into main (135 tests). `86b3932` **user decisions at 06:35 UTC: Jev off, fast loop retired, no private RPC, clever session may land on main**. `07e60c1` **P(rug) shipped** (test AUC 0.913). `b47a328` **predictor v3** for all four candle lengths. `bd21636`, `2ee5eab`, `fd2d6e2`, `643117d` diagnose the 5m overconfidence. `aead3ef` SOL costs in the European morning. Hourly `raw-clever` data commits; `382e827` reaches 264 pools. `65bb508` **11a evaluated: no edge on PumpSwap**. |
| 8. Now | 10-09 12:55 | Predictor session | `6a6b1a8` claims the "edge hunt" and `handoff/OVERVIEW.md`. There were no commits between 12:02 and 12:55. |

**Caveat on times:** some early STATUS log times were estimates and were corrected later. One correction notes "the real clock was ~2 h behind them" (STATUS.md:489-490). The predictor session also corrected its own entries (STATUS.md:438).

---

### 2. Sessions, roles and branches

The STATUS header still says "Two Claude sessions on different accounts take turns" (STATUS.md:3). Commit trailers show **five** distinct sessions. Together they account for 112 commits; the remaining 10 are the initial commit and 9 merge commits without trailers.

| Label | Session ID | Commit window | Commits | Branch(es) | Role |
|---|---|---|---|---|---|
| **Predictor session** | session_01UeZ4ho5y38qR1iNxnShtwF | 10-08 05:58 to 10-09 12:55 | 44 | `claude/solana-candle-predictor-s95qjr` (identical to main at `6a6b1a8`) | Built the live candle predictor and models v0 to v2 plus 15s/30s/5m. Did the chain plumbing: slots, PumpSwap decoder and recording, V2 decoding, watch through graduation. Also the out-of-fold shrink and SOL cost windows. Now: edge hunt and OVERVIEW.md. Its account could push at 04:32 UTC (STATUS.md:56). |
| **Profitability session** | session_01U4x5qUJYMStcujpyLJgQ8N | 10-08 22:02 to 10-09 03:49 | 27 | `claude/profitability-backtest`, `scam-filter-profit`, `decision-scorers`, `fast-loop`, `jev-metadata`, `slot-profit`, `established-tokens` | Built `tartar profit` and created the STATUS board. Built the decision scorers, the fast and slow loops, and the Jev evaluations. Ran the slot-entry, graduation run-up and established-memecoin studies (the dip pre-registration). Read jevtrader and made the SOL-USD cost table. Got `403` on push at ~03:40 (STATUS.md:53-55). |
| **Jev session** | session_012ZRs9FUggpEkx65Rw7K7fU | 10-08 23:44 to 10-09 05:52 | 7 | `claude/jev-live` | Started by the profitability session at the user's request (STATUS.md:487-489). Ran the live paper fast loop (rules scorer, Jev in shadow) and slow-loop cycles 1 and 2. Retired by the user's 06:35 decision. |
| **Research session** | session_01YLnqLnTQzvD6HHUTvnNpVm | 10-09 04:07 to 06:01 | 15 | `claude/eager-archimedes-k8pn4q` | Work listed in phase 6 above, plus the `raw-eager` recording (04:06–06:00, 2,639 launches, 69 graduated SOL pools). It "may push only its branch" (STATUS.md:245-246); the clever session merged it into main (`b145bfc`). |
| **Clever session** | session_01R61Ym2543SdY4GEWPsLin6 | 10-09 06:23 to 12:02 (claim says since 06:19) | 19 | `claude/clever-pascal-p4m7ub` (no remote ref in this clone; it fast-forwards main) | Work listed in phase 7 above, plus the `raw-clever` recording from 06:23. |

**"Established-tokens" is a branch, not a separate session.** Its commits (`eaf8bdc` … `d452865`) carry the profitability session's ID.

**Remote branches** (`git for-each-ref`, all 11 are fully merged into `origin/main`, 0 commits ahead):

| Branch | Tip date | Tip subject |
|---|---|---|
| profitability-backtest | 10-08 22:03 | Add a shared status board… |
| scam-filter-profit | 10-08 22:12 | Validate scam flags… |
| decision-scorers | 10-08 22:21 | Add launch decision scorers… |
| fast-loop | 10-08 23:12 | Add Jev shadow mode… |
| jev-metadata | 10-09 00:19 | Merge origin/main… |
| slot-profit | 10-09 01:34 | Merge main: keep both sessions' log entries |
| established-tokens | 10-09 02:29 | Study established memecoins… |
| jev-live | 10-09 02:48 | Slow-loop cycle 1… |
| eager-archimedes-k8pn4q | 10-09 04:47 | STATUS: research session progress… (the later research commits reached main through `b145bfc`) |
| solana-candle-predictor-s95qjr | 10-09 12:55 | STATUS: claim edge hunt… |
| main | 10-09 12:55 | same as above (`6a6b1a8`) |

---

### 3. The board protocol, in brief (STATUS.md:12-31)

1. **Start of a turn:** fetch and pull `main`, read STATUS, then the topic document (`candle-prediction-agent.md` or `profitability.md`).
2. **Claim before working.** Write label, UTC start time, task and branch under *Active*, and push that straight to `main`. If someone else's claim is under 3 hours old, take a different task.
3. **Work on a branch** `claude/<topic>`. Push after every unit that passes `pytest`, because usage limits come with no warning.
4. **Land finished units on main:** merge main into the branch, run pytest, then fast-forward `main`. Never force-push main or rewrite another session's branch.
5. **Keep STATUS current as you go.** Move items between Queue, Active and Done, and add a Log entry. On a conflict, keep both sides' entries.
6. **Leaving:** push, land what passes tests, clear your Active line, and log exactly where you stopped.

**In practice (git history):**
- There are 14 merge commits, mostly "merge main into branch, keep both sessions' entries".
- Claims and releases are separate commits (`STATUS: claim …` / `… session free`).
- The research session could not land on main; the clever session merged it.
- Since 06:35 the user lets the clever session fast-forward main (STATUS.md:36, 240-241).

---

### 4. Current board state

#### Active claims

**1. Clever session** (since 2026-10-09 06:19 UTC, branch `claude/clever-pascal-p4m7ub`; STATUS.md:35-40)
- Recording for 11a since 06:23 (`data/raw-clever`, `--pumpswap-hours 4`).
- SOL cost sampler 06:44–10:00.
- Then, per its claim: 11a evaluation, predictor v3.1 (§8.2.2c plan), and SOL sampler 13–16 UTC.
- The claim text was last edited at 09:00 (`2a855bb`). It still says "250 expected ~12:10", but 11a was already evaluated (`65bb508`, 12:02).
- At 12:56 the claim is ~6.6 h old, which is past the protocol's 3-hour window.

**2. Predictor session** (since 2026-10-09 12:55 UTC, branch `claude/solana-candle-predictor-s95qjr`; STATUS.md:42-46)
- **Edge hunt:** survey strategy families not yet tested (against the closed list in profitability §1), pre-register the most promising, and run them on free data (no real money, no Jev).
- Write `handoff/OVERVIEW.md`, the user's request. It does not exist yet in the tree.
- Recording `data/raw_v3` in its container (`--pumpswap-hours 4 --track-minutes 120`).

#### Blockers (need the user)

- **Still open (not struck through): GitHub write access.** The profitability session got `403 Resource not accessible by integration` on push and on the API at ~03:40 UTC on 10-09. The fix is in the GitHub app settings: Claude → Configure → select TARTAR (STATUS.md:53-56). Later evidence that pushing works for other sessions:
  - predictor session at 04:32 (STATUS.md:56)
  - Jev session at 05:04, "Pushing works again" (STATUS.md:293)
  - research session (STATUS.md:297)
- **Resolved or decided:**
  - **Jev usage policy:** decided 06:35 UTC 10-09. Jev stays off in TARTAR, the fast loop is retired, and the carve-out draft was not adopted (STATUS.md:50-52).
  - **Network:** resolved 22:35 UTC 10-08.
  - **TypeSafe key:** resolved 22:40 UTC 10-08 as the `TYPESAFE_API_KEY` secret. Never ask for it in chat.
  - **Private RPC:** declined by the user at 06:35 UTC 10-09. Public RPC capture is median 100% / mean 97% on `raw-eager`. "Don't ask again unless a study needs it" (STATUS.md:58-63).

#### Queue, ranked by expected effect on profit (STATUS.md:65-190)

| # | Item | Status |
|---|---|---|
| 1 | Jev in the fast loop | **Closed 06:35 UTC 10-09 by the user's decision.** Jev showed no signal in 3 tests. `tartar fast --replay` stays useful for studies. |
| 2 | More data / predictor v3 | **v3 installed 07:50 UTC 10-09.** It beats the old models on log loss everywhere; live edge 1m +6.2% vs +4.7%, 5m +6.5% vs +4.6%. **Open:** the 5m model states ~70% at the open but hits 61–65% on newer launches, because old-recorder rows are 75% of its training data. Next: retrain with `raw-clever`, down-weighting old rows at 5m (the v3.1 plan). |
| 3 | Longer holds on screened tokens | **Done 04:45 UTC, no edge.** All 24 rules lose on validation; the chosen one makes −12.5% [−17.6, −7.6]/trade on test. |
| 4 | PumpSwap decoder | **Done 00:12 UTC 10-09** (checked on 43 mainnet trades). |
| 5 | Record slot numbers | **Done 00:50 UTC 10-09.** 24% of the first minute's buy SOL lands in the launch's own slot. Notifications arrive median 1.47 s after the block (p90 5.1 s); `processed` commitment gives 1.15 s / 2.0 s. |
| 6 | Predictor open problems 3–5 | **Done ~23:45 UTC 10-08.** v2 installed ~01:00 UTC 10-09. |
| 7 | Verify pump.fun fees | **Done 00:00 UTC 10-09:** 0.95% + 0.30% = 1.25%/side. |
| 8 | Jev feature discovery on metadata | **Done 00:20 UTC 10-09: no added value** (test AUC 0.767 → 0.740 with Jev features). |
| 9 | Decode pump.fun V2 | **Done 00:20 UTC 10-09:** ~15% of launches and ~19% of trades are quote-paired. |
| 10 | Entry latency in slots | **Done ~01:25 UTC 10-09.** Landing first in slot +1 loses 5.3% (−1.8% even with zero fees). **Launch buying closed.** |
| 11 | Next strategy families | (a) Graduation run-up: **done ~01:50, no edge.** Trading graduated tokens on PumpSwap: **pre-registered, evaluated 12:05 UTC on 264 pools, no edge** (test means −19.6 / −22.5 / −38.1 / −3.4% for grad / mom / dip / active). (b) Established memecoins: **no reliable edge.** The dip rule runs as a pre-registered forward test: add a cohort about daily and score at ≥ 200 trades or on 2026-10-30. (c) A liquid market such as SOL-USD, e.g. Jev on news: listed, not started. |
| 12 | The user's `jevtrader` cost table | First table 03:50 UTC; second window and quote decay 05:33–05:55. ~0.5 bps/fill (p90 ~1.3); $1k 0.46 bps, $10k 0.15 bps (quotes, not fills). The queue text still lists European and US hours as open. The European morning was run per `aead3ef` (06:43–09:55, 0.46 bps, p90 0.67), but the text was not updated. US hours 13–16 UTC remain, planned by the clever session. Real fills unmeasured. |
| 13 | Ship a calibrated P(rug) | **Done 07:15 UTC 10-09.** Test AUC 0.913 on the latest 791 launches. The risk level's AUC rose from 0.585 to 0.735, and screen picks are unchanged. |

**Done section** (STATUS.md:214-222):
- predictor v1, scam filtering, online-model fixes
- open problems 3–5
- out-of-fold median shrink
- `tartar profit` and the profitability findings

#### Rules that hold across sessions (STATUS.md:192-212)

- **Background processes die when a session goes idle.** The container suspends ~12 min after the last turn (5–7 min seen later), and the local proxy returns on a new port. Restart after any `ConnectionRefusedError` to 127.0.0.1.
- Judge every model and strategy by `tartar profit` on the **latest** launches. Pick thresholds on validation only, and quote 90% intervals by token.
- **No real-money trading code** without the user's explicit request.
- **No Jev calls from TARTAR** (user, 2026-10-09): no shadow mode, no `jev` scorer, no new batch asks. Cached answers may be read offline. Asking again "needs new evidence, not a new idea".
- Never trade the v1 model's expected return (~−43%/trade on test).
- **Other standing instructions in the board:**
  - Never unblind or disturb jevtrader (STATUS.md:169-171).
  - Never ask for the key in chat (STATUS.md:60).
  - For long-hold studies, replay through `FastLoop` (STATUS.md:368-369).
  - After adding a dip cohort, run `pumpswap_fees.py --cohort … --save …/fees-measured.json` (STATUS.md:301-302).

#### Log highlights (newest first; STATUS.md:224-516)

- **09:00 clever:** P(rug) and v3 done; 5m overconfidence diagnosed.
- **06:40 clever:** merged the research branch; relayed the user's decisions.
- **06:05 research:** handed off, with a list of unclaimed next steps.
- **05:52 Jev:** cycle 2, no signal; loop stopped.
- **05:36 predictor:** handed off.
- **05:20 research:** copy-trading closed; PumpSwap model added.
- **05:04 Jev:** pushing works again; loop not restarted.
- **04:50 research:** PumpSwap fees measured; 11a pre-registered.
- **03:49 profitability:** handed off; jevtrader read.
- **03:35 Jev:** keepalives ineffective; pushes 403.
- **03:17 Jev:** restarted with `--hours 17`, ending ~20:17.
- **02:47 Jev:** cycle 1.
- **02:29 profitability:** 11b done.
- Earlier entries go back to **~21:00 UTC 10-08**, when the profitability session set up the board.

---

### 5. Dated future events

| When | What | Source |
|---|---|---|
| 2026-10-09, 13–16 UTC | SOL-USD cost sampler at US hours (clever session's plan; queue 12) | STATUS.md:40, 182-183 |
| ~02:24 UTC 2026-10-10 | Next dip cohort (`established_cohort.py`; commit at once), then `pumpswap_fees.py --cohort` | STATUS.md:262-263. Only cohort 1 exists (registered 2026-10-09T02:24:32Z, 12 pools). |
| 2026-10-23 21:40Z | jevtrader v1 sealed test ends (T0 2026-09-25 21:40Z); `make results` that evening. After that, if the user shares results, compare each arm's break-even fee per fill (f*_X) with §3.12 | handoff/jevtrader.md:14-15; STATUS.md:168-169, 323-324 |
| 2026-10-30, or earlier at ≥ 200 trades | Score the pre-registered dip rule (21 days after cohort 1) with `established_prereg_eval.py` | STATUS.md:163; profitability.md:434; dip-rolling/SPEC.json |
| (historical, moot) ~20:17 UTC 10-09 | The Jev fast loop's planned end; the loop has been retired | STATUS.md:328 |

## Open items
- Predictor session (claimed 12:55 UTC 10-09): edge hunt — survey untested strategy families, pre-register the most promising, run on free data; write handoff/OVERVIEW.md (not yet in the tree).
- Clever session's remaining plan: predictor v3.1 (§8.2.2c: 15s/30s/1m on every recording at full weight, 5m with the old-row weight chosen on validation) to fix 5m overconfidence (~70% stated vs 61–65% hit); SOL cost sampler at US hours 13–16 UTC 10-09. Its Active text (last edited 09:00) is stale and its claim is >3 h old.
- Blocker still listed for the user: GitHub write access (403 for the profitability session at ~03:40 UTC 10-09); other sessions could push later, but it is not marked resolved.
- Dip-rule forward test: add a cohort about daily (next ~02:24 UTC 2026-10-10) with established_cohort.py, commit at once, then run pumpswap_fees.py --cohort <file> --save handoff/preregistration/dip-rolling/fees-measured.json; score at ≥ 200 trades or on 2026-10-30.
- jevtrader: sealed test ends 2026-10-23 21:40Z; if the user then shares results, compare each arm's f*_X with the on-chain cost table (§3.12). Never unblind or touch it before then.
- Unclaimed after 11a: train the PumpSwap model (`tartar train --raw <same dirs> --pumpswap`, install only if it helps) and give the pumpswap domain its own flat-candle prior.
- Queue 11(c): a liquid market like SOL-USD (e.g. Jev on news) is listed but not started; Jev calls are off in TARTAR by the user's decision.
- Queue 12: real fills remain unmeasured (no real-money code without the user); the queue text still lists the European window as open even though aead3ef ran it.
- Doc inconsistencies: profitability.md:24 still says PumpSwap graduated tokens will be 'evaluated at ≥ 250 pools'; the STATUS header still describes two sessions; the Done section lists only four items.
- Unverified candidate from Jev cycle 2: odd_curve as a skip flag (with −19.2%, n=100; without −5.3%), in-sample and without intervals; to check with `tartar decide` before use.
- Stale note: the profitability log suggested rerunning §3.5–3.8 on V2 launches once V2 decoding landed (it landed 00:20 UTC 10-09); no record of that rerun was found.
