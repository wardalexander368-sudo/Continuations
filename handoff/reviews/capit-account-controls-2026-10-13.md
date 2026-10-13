# CAPIT chronological cash-account controls — 2026-10-13

The locked primary line (static-screened eight, hourly 120-minute entry proxy, 0.39% effective side cost) turns a hypothetical $1,500 into $1,653.29 over [2023-01-01, 2026-10-10). Its $153.29 gain is 10.22% on the account, or a 2.61% full-window CAGR equivalent. Peak original entry stakes are $600; minimum available cash is $892.00. It executes all 50 fixed candidate trades without a halt, cash rejection, or overlapping-coin rejection.

This is an exploratory diagnostic of history already used to select CAPIT, not an untouched test or evidence that a funded route earns this return. It fills the gap between summed trade returns and a chronological account with identical controls. No signal, registration, bot book, live rule, route, workflow or schedule changes.

## Fixed before the new outcomes

Protocol bytes were locked at 2026-10-13T03:31:39.023068+00:00 on main base `22062631c563fcad874c6ead29275f8f28b2a5c7`. The cohort is the existing 71 accepted hourly 60-minute CAPIT opportunities in 22 full-study episodes; the static eight-coin subset has 50 opportunities in 20 represented episodes. Later entry may reject these opportunities but cannot add new signals. Both delays, both side costs and both universes were specified before running this diagnostic; all eight lines are reported.

Each account begins with $1,500, debits a fixed $100 per accepted entry, holds 24 hours, permits one position per coin and at most $1,100 in original entry stakes. Unused cash earns zero; stakes do not scale with gains. All exits at a timestamp occur before entries. Simultaneous entries use the fixed study coin order, then original cohort identity, not price or outcome.

The loss-stop interpretation is cumulative net realized account P&L at or below −$250. The mean stop applies after at least five fully completed accepted UTC signal days when mean net return across all closed trades is below −3.8%. Diagnostic UTC signal days use the original signal candle's start-hour label `(T0 + signal_index + shift) // 24`; execution timestamps use candle closes. These are explicit diagnostic interpretations, not amendments or implementation of the adopted live rule. A stop permanently blocks new entries; already held positions keep their scheduled exits. Batch losses and held positions can carry total losses beyond $250. Reported drawdown is closed P&L only; intratrade mark-to-market losses are unknown.

Alpaca's official documentation charges crypto buy fees in received crypto and sell fees in received USD; the fixed tier-one taker assumption is 0.25%. [Official crypto fee documentation](https://docs.alpaca.markets/us/docs/crypto-fees). With fee f and residual price friction s = effective side budget − f:

`quantity = 100 / (entry_close * (1+s)) * (1-f)`

`exit_credit = quantity * exit_close * (1-s) * (1-f)`

`net_cash = exit_credit - 100`

These equations charge each fee once. The 0.39% and 0.50% budgets are model assumptions, not reconciled fee activities or measured historical Alpaca fills. Their multiplicative cash arithmetic differs from the earlier additive percentage-cost model: the screened-eight 60-minute result is $212.92 here versus $214.78 in the prior report. That difference does not overturn or replace the previous episode bootstrap analysis.

## Every specified line

| Universe | Entry proxy | Side budget | Executed | Net cash | Account return | Window CAGR equivalent | Closed-P&L drawdown | Control mean cash | Controls at least actual |
|---|---|---|---|---|---|---|---|---|---|
| study_11 | 60 min | 0.39% | 71 | $257.41 | 17.16% | 4.29% | $77.30 | $-78.13 | 0.00% |
| study_11 | 60 min | 0.50% | 71 | $241.25 | 16.08% | 4.03% | $80.42 | $-91.10 | 0.00% |
| study_11 | 120 min | 0.39% | 71 | $188.80 | 12.59% | 3.19% | $103.71 | $-77.85 | 0.03% |
| study_11 | 120 min | 0.50% | 71 | $172.78 | 11.52% | 2.93% | $107.00 | $-90.60 | 0.03% |
| snapshot_screened_8 | 60 min | 0.39% | 50 | $212.92 | 14.19% | 3.58% | $49.29 | $-55.77 | 0.00% |
| snapshot_screened_8 | 60 min | 0.50% | 50 | $201.47 | 13.43% | 3.40% | $51.38 | $-64.80 | 0.00% |
| snapshot_screened_8 | 120 min | 0.39% | 50 | $153.29 | 10.22% | 2.61% | $66.39 | $-55.72 | 0.01% |
| snapshot_screened_8 | 120 min | 0.50% | 50 | $141.96 | 9.46% | 2.43% | $68.66 | $-64.68 | 0.01% |

All actual lines accept every candidate, remain funded, stay within their original-stake cap, and never trigger either stop. Full-study peak stakes are $800; screened-eight peak stakes are $600. The extra hour of entry delay reduces screened-eight 0.39% cash gain from $212.92 to $153.29, a 28.0% reduction. Raising the side budget to 0.50% lowers its 120-minute gain to $141.96.

Episode 13 contributes $100.53, or 65.6% of primary net gain. The other episodes together contribute $52.76; this is a contribution decomposition, not a separately rerun account or holdout. Sparse and concentrated historical gains remain the central weakness.

## Full-account reference controls

Each of 10,000 draws independently shifts each original full-study episode by a common offset within ±360 hours. Every member retains its relative timing. The exact same 22-episode shift vector is used across all eight lines. Support requires finite positive entry and exit closes for every full-study member at both delays, includes zero/actual signal times, and never screens on return. Support counts range from 687 to 721; no actual opportunity is dropped for missing prices.

Shifted episodes can collide. Both signal and control accounts apply the same chronological coin-busy, cash, cap and stop logic. Therefore executed counts can differ. The primary control executes 45.9927 trades on average versus 50 actual; 1,301 controls halt on the mean rule, 8,699 do not halt, and none triggers the cumulative-loss stop. There are 39,886 halted-entry rejections and 187 coin-busy rejections across its 10,000 draws, with zero cash/cap rejections. These differences are reported rather than forcing equal fills after applying the rules.

Primary control net cash: mean −$55.72; 5th/median/95th reference quantiles −$140.67/−$54.15/$21.07. Actual exceeds the control mean by $209.01; one of 10,000 controls is at least actual. These are reference-distribution summaries, not a null p-value or a confidence interval for profitability. A shared shifted-history comparison does not restore untouched evidence, resolve strategy-selection bias, or simulate executable crash quotes.

The full output retains all 80,000 control-account records locally. The committed compact readout retains every scalar line, the primary actual cash trace, control summaries, support counts and hashes. The local readout retains all eight actual traces and every supported shift. Reproduce the full output offline with the existing verified cache; no repeated download is needed.

## Validation and limits

A bounded independent adversarial review found no material defect, reconstructed the shared shift matrix and control summaries, and checked funding/stop boundary cases. Its coverage and omissions are in `adversarial-review.md`; it did not independently regenerate the full accounts or verify real execution.

All 80,008 accounts reconcile starting cash plus net P&L to terminal cash, preserve cash nonnegativity and the original-stake cap, and account for every accepted/rejected candidate. A separate Fraction arithmetic calculation verifies every quantity, exit credit and cash transition for all eight actual lines. This checks arithmetic, not execution realism or causal validity.

An initial CI run exposed one test's dependency on sparse-excluded research data. The repaired test supplies local protocol bytes and still exercises the real cohort rejection guard; research code and outcomes are unchanged.

Focused tests cover received-asset fees, exit-before-entry ordering, busy/cash/cap rejection, stop overshoot, post-stop exits, completed-day mean stopping, joint endpoint support, non-evaluable actual prices, deterministic shared sampling, integer shifts, malformed JSON and changed protocol/cohort rejection. Full repository validation passed: 424 tests, one skipped and nine subtests (80.26 seconds). Deterministic replay is byte-identical; both are recorded in the accompanying verification receipt.

Remaining gaps: dynamic historical eligibility, true Alpaca crash fills/fees and asset rounding, intrahour liquidity and maximum mark-to-market risk, taxes/data/subscriptions, idle-cash yield, future registered score and unmatched-order stops. The zero-yield account's 2.61% primary CAGR equivalent is a cash hurdle, not a claim to outperform any particular available cash investment. Prior episode net confidence intervals still span zero. This diagnostic does not change eligibility, gate readiness or live funding authorization.

## Reproduction and provenance

From the repository:

```sh
PYTHONDONTWRITEBYTECODE=1 python handoff/experiments/edge-hunt/patterns/capit_account_controls.py \
  --cache /path/to/coinbase-hourly-20261013 \
  --cohort handoff/data/edge-hunt/capit-account-controls/2026-10-13/cohort.json \
  --protocol handoff/data/edge-hunt/capit-account-controls/2026-10-13/protocol.json \
  --output /path/outside-cache/full-account-controls.json
```

Protocol SHA-256: `de993555d9aeb0621eb06c4b5ceb2d5653050d2f086e3b0407a84f3355b16cd9`.
Cohort SHA-256: `3b8209549c3af7105440b322a151a32c5506f03aa662a81b13004e64a4b968e2`.
Cache manifest SHA-256: `dc9fc1a691933ef97584f61b8b62f95724d50157e22a00800b3796a40992d4e7`.
Shared shift matrix SHA-256 (little-endian int32): `ff049fc8d3004f059bad60a1aa66e9e0498d23efcfccd5a60620cec2e605d23f`.
Full output SHA-256: `8a52d9eb005c30ac33331fd24045c2b669326cd5706533efb25d893c911db5f0`.
Source analysis SHA-256: `a293b0ff5a2de8c1edf8b30e23971035a792f9c99b66d80abe1135e0056dce45`.
