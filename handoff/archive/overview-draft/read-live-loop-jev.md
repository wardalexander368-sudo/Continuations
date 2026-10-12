<!-- read:live-loop-jev: workflow section summary as of 2026-10-09 12:56 UTC; 'verify-*' files are fact-checked, 'read-*' are not -->

## The live fast/slow loop, Jev and jevtrader (as of 2026-10-09 12:56 UTC)

**Bottom line:** The live paper-trading loop ran in short bursts from 2026-10-08 23:44 UTC to about 03:39 UTC on 10-09. It produced two slow-loop reviews. Both showed negative paper results, and Jev's shadow answers showed no signal. The loop has been **stopped since about 03:39 UTC**. On **2026-10-09 06:35 UTC** the user **retired it and turned Jev off in TARTAR**. jevtrader is the user's own separate experiment. It is sealed, and TARTAR may only read it and supply an on-chain cost table for it.

### Terms used here
- **Paper trading:** simulated trades. No transaction is ever sent.
- **pump.fun launch:** a new memecoin. It first trades on a **bonding curve**, an automated price formula that sets the price from the SOL put in.
- **Graduation:** the point where the curve completes. The token then stops trading on pump.fun and moves to a **PumpSwap** pool (`tartar/fastloop.py:98-102`).
- **Slot:** one Solana block, about 270 ms (`handoff/STATUS.md:95`).
- **bps:** basis points, hundredths of a percent.
- **Spearman:** a rank correlation from −1 to +1. Near 0 means the answer does not order the outcomes.
- **Quintile:** one fifth of the launches, sorted by an answer.
- **90% CI:** the range the true mean likely sits in.
- **p90:** the value 90% of cases stay under.
- **Shadow mode:** Jev is asked, and its answers are logged but never acted on.

### What Jev is
- Jev is **TypeSafe's "Jev" decision model**, which jevtrader.md calls "TypeSafe System One" (`handoff/jevtrader.md:8`).
- TARTAR's client sends a POST to `https://api.typesafe.ai/v1/systemone` with model `jev-latest`. It asks typed yes/no ("noul") questions and gets back a probability for each (`tartar/jev.py:3-6, 40-41`).
- **Credentials:** the client uses `TYPESAFE_API_KEY` as a Bearer token if it is set. Otherwise, in the Claude cloud environment, **the proxy adds the credentials** (`tartar/jev.py:20-22, 279`). The carve-out draft notes that this proxy injects the *shared* key (`handoff/jev-carveout-DRAFT.md:37-38`).
- The user added the key as an environment secret at 22:40 UTC on 10-08. Rule: "Never ask for the key in chat" (`handoff/STATUS.md:59-60`).
- **How Jev is asked:** code first turns the launch's numbers into phrases, because Jev is weak with raw numbers (`tartar/jev.py:10-11, 73-87`). One request then asks five questions (`tartar/jev.py:90-119`):
  - `buy`: will buying now and selling after 3 minutes beat about 3.5% in costs?
  - `copycat`, `low_effort`, `meme` and `scam_wording`: four judgments about the name and symbol.
- **Earlier offline result:** across 3,523 launches the median call took 243 ms (p90 284 ms). Jev's direct answer **lost −9.2% per trade on test launches (41 trades; CI −15.9 … −1.9%)**. It was overconfident by about 2× (`handoff/profitability.md:190, 199, 203-207`). A shadow replay over 5,598 recorded launches gave Spearman between −0.03 and +0.03 for all five questions (`handoff/profitability.md:221-222`).

### What the fast loop does for each launch (`tartar fast`, no Claude involved)
Source for the main flow: `tartar/fastloop.py:1-21`, `handoff/slow-loop.md:7-12`.

1. **Wait** `screen_seconds` (20 s) after the launch appears.
2. **Build the launch's state** with `decide.LaunchStateBuilder`. This is the same code the offline evaluation uses (`tartar/decide.py:56-60`).
3. **Apply the skip rules:** minimum buyers, risk levels and flags (`tartar/fastloop.py:139-147`). Then apply the caps: `max_open`, `max_entries_per_hour` and the daily loss limit (`tartar/fastloop.py:630-641`).
4. **Ask the scorer.** The `rules` scorer returns a constant 1.0, so every launch that passes the skips and caps is bought (`tartar/fastloop.py:510`). The `jev` scorer would act on Jev's `buy` answer (`tartar/fastloop.py:693-702`).
5. **Paper-trade the "buy".** The simulated fill uses the live bonding-curve reserves after the execution latency. It exits by the policy's rule and mirrors `profit.round_trip` exactly (`tartar/fastloop.py:6-8, 18-20`). Positions still open at graduation are sold on the recorded PumpSwap pool (`handoff/STATUS.md:307`).
6. **Get Jev's shadow answers.** With `shadow_jev: true`, every screened launch goes to Jev in worker threads. The answers are journaled as `shadow` records and never acted on (`tartar/fastloop.py:290-329, 615-616, 705-713`).
7. **Journal everything** to `data/journal/journal-YYYYMMDD.jsonl`: every screen, decision, fill, cancel and exit, plus `start` and `stop`. The fast loop also writes the raw chain logs, so it doubles as the recorder (`handoff/slow-loop.md:10-12, 31-32`).

Safety and control:
- **Paper only:** `Policy.validate` refuses any mode except `"paper"` (`tartar/fastloop.py:15-16, 116-117`).
- The loop reloads the policy file within about 5 s of a change. An invalid edit is rejected and logged as `policy_error`. Open positions keep the rule they were opened with (`handoff/slow-loop.md:15-16, 42-44`; `tartar/fastloop.py:150-174`).
- Every field has hard bounds in `LIMITS` (`tartar/fastloop.py:43-62`).

### What the slow loop does (Claude, every few hours)
Source: `handoff/slow-loop.md:14-16, 50-89`.
- Each cycle: check that the fast loop is alive, then run `tartar review`.
- **`tartar review`** reads the journal and the raw trades. It computes what *every* screened launch would have earned if bought (the "counterfactual"). From that it reports (`tartar/review.py:1-12, 55-161`):
  - the paper result;
  - whether the skip rules removed losers;
  - flag gaps;
  - each Jev shadow question's Spearman and its P(net > 0) by quintile;
  - for a varying scorer, its calibration and a hindsight-best threshold, marked in-sample.
- **Rules for changing the policy:**
  - change **at most one thing per cycle**;
  - change it only with evidence from **about 300 new screened launches**;
  - move a threshold at most halfway toward the hindsight best.
- **Guardrails:**
  - paper only;
  - never raise `size_sol`, `max_open` or the loss limit to make up losses;
  - after 3 negative cycles in a row with the same scorer, say so plainly.
- Planned cadence: about every 3 h. Reviews go to `handoff/live/reviews/` (`handoff/STATUS.md:451-452`).
- (`tartar/scoreboard.py` is not part of this loop. It tracks whether the predictor's locked-in forecasts state honest confidence (`tartar/scoreboard.py:1`).)

### The policy as run (`handoff/live/policy.json`)
This file is a copy, because `data/` is git-ignored (`handoff/STATUS.md:452`). It was never changed after the 10-08 start.

| Field | Value |
|---|---|
| mode / scorer | `paper` / `rules` |
| screen_seconds | 20.0 |
| min_buyers, skip_levels | 0, [] |
| skip_flags | concentrated, sniped, dev_bag |
| threshold | 0.5 |
| hold_seconds; take profit / stop loss | 180 s; none / none |
| size_sol | 0.1 |
| fee | 0.0125 (1.25% per side) |
| network_sol | 0.0002 |
| exec_latency | 1.0 s |
| scorer_timeout | 2.0 s |
| max_open | 10 |
| max_entries_per_hour | 60 |
| daily_loss_limit_sol | 1.0 |
| shadow_jev | **true** |

The policy's note reads: "2026-10-08 Jev session: rules scorer with Jev in shadow (user choice). Offline eval (profitability.md 3.7) found no Jev edge; shadow tests it on fresh launches." (`handoff/live/policy.json:1-26`). The file still says `shadow_jev: true`. That only records the policy as run; the loop is not running.

### Timeline of the live loop
| When (UTC) | What happened | Source |
|---|---|---|
| 10-08 22:45 | Profitability session built the fast loop, `tartar review` and slow-loop.md. It ran the loop briefly (rules, paper), then handed it to a new **Jev session** | `handoff/STATUS.md:481-491` |
| 10-08 23:35 | Shadow mode added (commit 58851a2 is dated 23:12) | `handoff/STATUS.md:464-466` |
| 10-08 23:44 | User confirmed "option 1: rules scorer, Jev in shadow, paper only". `tartar fast --hours 20` started | `handoff/STATUS.md:451-452`; commit cd0df5a |
| about 23:50 | Loop died when the container was suspended (ConnectionRefusedError to the local proxy). Restarted 00:03; about 13 min lost | `handoff/STATUS.md:436` |
| 00:10 | Died again. The 10-min keepalive check-ins were blocked by the permission check | `handoff/STATUS.md:330` |
| 02:47 | Restarted; **slow-loop cycle 1** | `handoff/STATUS.md:330`; commit e290152 |
| 02:54 → 03:17 | Died again. The user approved keepalive check-ins, and the loop was restarted at 03:17 with `--hours 17` | `handoff/STATUS.md:328` |
| 03:24, 03:33 | Died twice more. "Keepalives don't work": the container suspends 5–7 min after a turn ends. Pushes returned 403 from 03:17. 834 screens journaled by then | `handoff/STATUS.md:326` |
| 05:04 | "Down since 03:39". **Not restarted** because of the new Jev usage-policy blocker | `handoff/STATUS.md:293` |
| 05:52 | **Cycle 2.** No policy change. Loop **stopped**, pending the user's Jev-policy decision and somewhere always-on to run it. No further cycles scheduled | `handoff/STATUS.md:266`; commit c171e4b |
| 06:35 | **User decision:** Jev stays off in TARTAR, the live fast loop is retired, and the carve-out is not adopted | `handoff/STATUS.md:50-52, 67-71, 239-240`; `handoff/slow-loop.md:3-5` |

The raw hours saved from the loop are `handoff/data/raw/20261008-23`, `20261009-00`, `-02` and `-03` (`.jsonl.gz`) (`handoff/STATUS.md:293, 328, 330, 436`).

Standing rule from this episode: background processes die when a session goes idle (`handoff/STATUS.md:194-202`).

### Review findings (all paper; counterfactual = "if bought")

**Cycle 1** (`handoff/live/reviews/20261009-0247.md`)
- Period: 23:44 → 00:10 UTC. Live data covered only 23:44–23:50 and 00:03–00:10 (`handoff/STATUS.md:330`).
- Events: 415 screens, 86 decisions, 415 shadow answers, 41 fills, 45 cancels, 27 exits. Skips: flags 126, `max_open` 203 (lines 5-7).
- Rules scorer: 0 errors, buy share 1.0.

| | n | mean net | 90% CI | win |
|---|---|---|---|---|
| paper trades | 27 | −2.02% | −15.29 … +16.40% | 4% |
| every screened launch | 125 | −2.43% | −10.54 … +6.97% | 15% |
| not bought | 98 | −2.55% | | 18% |
| skipped: flags | 64 | −0.36% | | 22% |
| skipped: max_open | 34 | −6.68% | | 12% |

- Jev shadow on 125 launches (base P(net > 0) 15%): Spearman buy **+0.118**, copycat +0.038, low_effort +0.178, meme −0.158, scam_wording +0.018 (lines 29-37).
- Verdict: noise-level at n=125, and the quintiles are not monotone. **No policy change** (about 300 launches needed). The 203 `max_open` skips in about 13 min were judged a capacity limit, not evidence (`handoff/STATUS.md:330`).

**Cycle 2** (`handoff/live/reviews/20261009-0552.md`)
- Period: all live data, 23:44 → 03:39 UTC.
- Events: 903 screens, 165 decisions, 901 shadow answers, 117 fills, 48 cancels, 68 exits, 6 starts. Skips: flags 418, `max_open` 320 (lines 5-7).

| | n | mean net | 90% CI | win |
|---|---|---|---|---|
| paper trades | 68 | **−1.39%** | −9.21 … +7.75% | 6% |
| every screened launch | 352 | −9.24% | −13.04 … −4.83% | 11% |
| not bought | 284 | −11.12% | | 12% |
| skipped: flags | 212 | **−13.49%** | −19.00 … −7.64% | 13% |
| skipped: max_open | 72 | −4.12% | | 8% |

- Flag gaps, with vs without (lines 21-31):
  - dev_bag −16.99% (128) vs −4.80%
  - sniped −11.69% vs −7.64%
  - **odd_curve −19.16% (100) vs −5.30%**
  - serial_launcher −30.47% (21) vs −7.89%
  - concentrated −15.77% (26) vs −8.72%
- Jev shadow on 352 launches (base 11%): Spearman buy **+0.015**, copycat +0.069, low_effort +0.059, meme −0.068, scam_wording +0.084 (lines 33-41).
- Verdict, as written in `handoff/STATUS.md:266`:
  - "**Jev shadow: no signal**"; no quintile pattern is monotone, which agrees with §3.7;
  - the skip flags remove losers;
  - paper results were negative for the **2nd cycle in a row** (the CI spans 0);
  - `odd_curve` looks like a skip candidate, but the evidence is in-sample, with no intervals given, and it should be checked with `tartar decide` first;
  - **no policy change**.
- The header's "5 change(s)" probably counts loop restarts, not edits: the review counts `start` records as policy changes (`tartar/review.py:60, 65`), and there were 6 starts. This is an inference from the code.
- Queue item 1 closed on this basis. Jev showed no signal in three tests (§3.7 offline, §3.8 metadata, live shadow cycle 2), and launch buying is closed as a strategy family (§3.9, §3.14) (`handoff/STATUS.md:67-71`).

### Current state and rules
- The live loop is **retired and not running**. `tartar fast --replay` stays as a study tool, and live recording is done with `tartar record` (`handoff/slow-loop.md:3-5`; `handoff/STATUS.md:70-71`).
- **No Jev calls from TARTAR** (user, 2026-10-09): no shadow mode, no `jev` scorer and no new batch asks (`handoff/STATUS.md:208-210`).
  - Cached answers in `handoff/data/jev/` may be read offline.
  - "Asking the user again needs new evidence, not a new idea."
- The current Active edge hunt is explicitly "no real money, no Jev" (`handoff/STATUS.md:45`).

### The Jev usage-policy blocker (now decided)
- **Raised at 03:49 UTC on 10-09** by the profitability session (`handoff/STATUS.md:317`).
- **The issue:** jevtrader's PROTOCOL places it under the user's personal JEV protocol. That protocol's §5 "Never" list includes "any always-on hook that makes a model call" and "`jev ask` as a decision instrument". jevtrader is a signed carve-out, as a measurement. TARTAR's uses are **not covered by that carve-out**: shadow mode, `tartar decide --jev` and the `jev` scorer (`handoff/jevtrader.md:25-30`).
- **The draft:** the research session drafted `handoff/jev-carveout-DRAFT.md` (commit 1d0952e, 04:59 UTC). It proposed:
  - paper only, measurement only, and separation from other repos;
  - its own key and its own send ledger;
  - a spend tripwire of $0.25/day;
  - a pinned model and at most one retry;
  - the `jev` scorer not covered.
  Several of these were marked "Not built yet" (`handoff/jev-carveout-DRAFT.md:26-52`).
- **Outcome:** the blocker is struck through in STATUS. The user decided at 06:35 UTC: Jev stays off, and the draft was **NOT ADOPTED** (`handoff/STATUS.md:50-52`; `handoff/jev-carveout-DRAFT.md:3-4`).

### jevtrader: what it is
Source: `handoff/jevtrader.md`.
- **Where:** `github.com/AJW9991/jevtrader`, the user's own repo. Public since 2026-10-09; read by TARTAR at commit 9ce9b7b (lines 3-4).
- **What it measures:** a **paper-only, forward-only measurement** of a "two models at two speeds" loop on **Coinbase SOL-USD** (lines 7-12).
  - **Every minute**, Jev answers five fixed questions from a roughly 10-word state.
  - **Nightly**, Claude proposes a rewrite of the `action` question, and a person applies it.
  - **Arms:** A = frozen wording, B = nightly rewrite, C = a no-model rule, and in v2 D = the wording's own table.
  - It runs on the user's Mac under launchd, and its data stays there.
- **v1 (sealed, running):** T0 2026-09-25 21:40Z; it **ends 2026-10-23 21:40Z**, with `make results` that evening. Results are **withheld until day 28 by design** (lines 14-15). This is the "sealed 28-day pre-registered paper test" (`handoff/STATUS.md:166-170`).
- **v2 (drafted, pre-registered in `PREREG-v2.md`):** decision cadences of 15/60/240 minutes, several products, and a break-even fee per fill `f*_X = 90·E_X(0)/(E_X(0)−E_X(90))` (lines 16-19).

### What TARTAR may and may not do with jevtrader
**May not** (`handoff/jevtrader.md:21-30`; `handoff/STATUS.md:169-171`):
- unblind or disturb it;
- run its reports on its data (TARTAR does not have the data anyway);
- push to it;
- feed its outcomes or proposals into anything;
- propose changes to its sealed documents;
- link it with the user's `crypto-trading-system` repo, which its PROTOCOL keeps separate.

**May** (`handoff/jevtrader.md:3, 32-103`; `handoff/STATUS.md:172-184, 324`):
- read it: clone it anonymously, read-only;
- provide an **on-chain SOL-USD cost table** so its day-28 break-even fees can be read against a cheaper venue;
- after 2026-10-23, compare each arm's f*_X with §3.12, if the user shares the results.

**Deliberately not done:** TARTAR built no SOL-USD + Jev loop, because a duplicate would add nothing before day 28 (`handoff/jevtrader.md:99-103`).

**The cost table so far** (quotes, not fills; Jupiter $1,000 round trips):
| Window (10-09, UTC) | Per fill, median | p90 | Source |
|---|---|---|---|
| 03:37–03:48, 33 samples | **0.48 bps** | 0.68 | `handoff/jevtrader.md:35-42` |
| 04:33–05:33, $1,000, 120 samples | 0.46 bps | 0.70 | `handoff/jevtrader.md:53-56` |
| 04:33–05:33, $10,000, 71 samples | 0.15 bps | 0.33 | `handoff/jevtrader.md:53-56` |
| 06:43–09:55, 371 samples | 0.46 bps | 0.67 | `handoff/jevtrader.md:89-94` |

- For comparison, a Coinbase retail round trip at 90 bps taker costs about 181 bps.
- **Quote decay:** a quote re-taken 1–5 s later moves only with the market. Filling at the later quote costs about 0.40–0.43 bps per fill, with no 50 bps slippage failures (`handoff/jevtrader.md:68-87`).
- **Planning figure:** about 0.5 bps expected per fill, about 1.3 bps at p90. That is below jevtrader's smallest non-zero fee column of 2 bps (line 60).
- **Caveats** (lines 62-66, 96-97):
  - quotes are not fills;
  - MEV and sandwich attacks, failed transactions and the USDC/USD basis are not priced;
  - US hours (13–16 UTC), larger sizes and real fills are still unsampled.


## Open items
- jevtrader v1 ends 2026-10-23 21:40Z ('make results' that evening). If the user shares the results, compare each arm's break-even fee per fill (f*_X) with the on-chain cost table in profitability §3.12 (handoff/jevtrader.md:14-15; handoff/STATUS.md:324).
- SOL-USD on-chain cost sampling for jevtrader still lacks US hours (13-16 UTC) and larger sizes. Real fills stay unmeasured, because there is no real-money code without the user (handoff/jevtrader.md:96-97; handoff/STATUS.md:182-184).
- The Jev usage-policy blocker is closed by the user's 06:35 UTC decision (Jev off). Reopening it needs new evidence, not a new idea (handoff/STATUS.md:50-52, 208-210).
- The cycle-2 candidate skip flag odd_curve (-19.2% with vs -5.3% without, in-sample, no intervals) was never checked with tartar decide. This is now moot for the live loop, which is retired (handoff/STATUS.md:266).
- Only two slow-loop cycles ran, both negative; a third cycle was never run (handoff/STATUS.md:266).
- handoff/live/policy.json still reads shadow_jev: true with the 10-08 note. It records the policy as run, not a live setting, and conflicts on its face with the 'No Jev calls' rule if anyone restarts from it (handoff/live/policy.json:25-26; handoff/STATUS.md:208-210).
- Timestamp inconsistencies in the sources: STATUS gives the user decision as 06:35 UTC, but commit 86b3932 recording it is dated 2026-10-09T06:25:14+00:00. The loop's last death is given as 03:33 (handoff/STATUS.md:326) and as 'down since 03:39' (handoff/STATUS.md:293). Shadow mode is logged at 23:35 (handoff/STATUS.md:464), while commit 58851a2 is dated 23:12.
- jevtrader v2 is drafted and pre-registered (PREREG-v2.md) but described only as drafted; it has not started (handoff/jevtrader.md:16-19).
- The GitHub write-access blocker (403 on push; it affected the Jev session from 03:17 UTC) is still listed under Blockers. The Jev session reported that pushing worked again at 05:04 (handoff/STATUS.md:53-56, 293, 326).
