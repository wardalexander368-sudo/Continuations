# CAPIT box fixed-cost hurdle — 2026-10-13

The saved CAPIT account models' **60-minute versus 120-minute policy advantage supports only $1.31–$1.52/month of additional running cost at the locked $100 stakes**. The project's approximate **$5/month** box scenario exceeds that advantage in all four existing universe/cost pairs. This qualifies the economic case for faster execution: the historical model does not yet demonstrate that a dedicated $5/month box pays for itself at this stake.

This derives a new cost hurdle from the existing [chronological account diagnostic](https://github.com/wardalexander368-sudo/Continuations/blob/4e58a88fe96228f2bce1d2c0cf302ceb9aa0d40c/handoff/reviews/capit-account-controls-2026-10-13.md). It does not rerun accounts, tune a strategy, measure the box's fills, amend a registration or change the approved paper setup. Those original models use already explored history and fixed snapshot eligibility; the earlier episode-based net-return intervals still span zero.

## Every original timing pair

All eight original lines are retained as four paired comparisons. Each begins with $1,500 and debits $100 per accepted entry. Pair members have the same accepted opportunity IDs and counts; both entry and exit close indices shift by one hour, with a 24-hour hold. Consequently the difference compares complete entry/exit timing policies; it does not isolate a faster buy or pure latency.

| Universe / side-cost assumption | Paired trades | 60-minute net cash | 120-minute net cash | Policy difference | Monthly extra-cost hurdle | Difference less $5/month scenario |
|---|---:|---:|---:|---:|---:|---:|
| Study 11 / 0.39% | 71 | $257.41 | $188.80 | $68.62 | $1.52 | −$157.75 |
| Study 11 / 0.50% | 71 | $241.25 | $172.78 | $68.47 | $1.51 | −$157.90 |
| Snapshot-screened 8 / 0.39% | 50 | $212.92 | $153.29 | $59.63 | $1.32 | −$166.73 |
| Snapshot-screened 8 / 0.50% | 50 | $201.47 | $141.96 | $59.50 | $1.31 | −$166.86 |

The study window is **[2023-01-01, 2026-10-10)**: 1,378 days. Fix the equivalent-month convention at `12 × days / 365.25`, giving **45.2731006160 months**. Then:

`monthly incremental cost hurdle = (60-minute net cash − 120-minute net cash) / equivalent months`

`full-window additional cost scenario = $5 × equivalent months = $226.36550308`

This assumes the additional cost is incurred throughout the full window solely for the faster policy, with zero marginal baseline expense. It uses continuous equivalent months, not an acquired invoice, actual calendar billing or dated expense cash flows. Subtracting the cost is an ex-post scalar calculation; it does not replay cash funding, stops, holdings or drawdowns after monthly debits.

For the screened-eight/0.39% pair, the historical policy improvement is **$59.63**, about **$15.81/year** under the same fixed convention. Covering the $5/month scenario requires **$226.37** over this window—**$4.53 per paired trade**, versus the modeled **$1.19**. Subtracting that full-window expense from the faster line's $212.92 scalar gain leaves **−$13.44**, before other omitted costs. This is not a funded account result or a future annual forecast. No proportional stake/capital scaling is asserted.

## What changes in the next comparison

The adopted live rule remains $100 per trade. Its $200+ scaling discussion and the approved paper-box setup remain unchanged. This analysis supplies a measurable hurdle for the existing paired comparison: record the **actual marginal cost of the faster route**, including whether hosting is dedicated, shared or already paid. If the additional expense is zero, the recurring cost burden is zero; the model's break-even ceiling remains $1.31–$1.52/month. If it is $5/month, the existing model falls short. Shared research value may justify a paid paper server independently of trading profits; that value has not been priced here.

The original hourly proxies are not actual box (~90-second nominal polling) versus actual runner timing. The source audits already show that nominal pass latency differs from submission/fill latency and that complete partial-fill, inventory, fee and observation states are required. Prospective paired opportunities, complete account cash/inventory outcomes and actual timestamps must establish the real policy benefit. Carry this recurring expense into the account comparison once its amount, allocation and posting schedule are known. Data/subscriptions, taxes, idle-cash yield and other operating costs remain unquantified.

Cost-aware investment accounting has established prior art: the [SEC's July 2025 fee bulletin](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/updated) distinguishes recurring expenses from transaction fees and explains their effect on portfolio returns. A focused search also located the [2009 NBER monitoring/transaction-cost paper](https://www.nber.org/papers/w15010); only its indexed abstract metadata was acquired here, with the page open failing. These references support checking prior art; no novel method or claim that nobody has tried this diagnostic is made. They supply neither the project's server price nor a crypto timing effect.

## Freshness and verification

Fetched main **4e58a88fe96228f2bce1d2c0cf302ceb9aa0d40c** adds **40 paper/shadow rows** beyond the saved ed68 ledger, preserving its earlier prefix: **1,624 total**. The **17:23 UTC** report still has no US open/closed trades, gate **0/3 days and 0/8 trades**, and no priced random-entry control. No `box-data` branch was advertised by the bounded exact-ref check; deployment/account state remains unknown. No new executable crash cohort, exact-mint buyer or social coverage was acquired. The unchanged 21-coin cache ends exclusively October 10 UTC; only its manifest hash was rechecked, with no raw-cache scan/download.

Decimal arithmetic verifies public/local equality of relevant scalar outcomes for all eight lines and matching cohort/timestamp relationships for all four pairs. An independent Fraction calculation reproduces every policy difference, time convention and cost hurdle in four meaningful check groups. It also checks original protocol provenance and terminal-cash differences within the saved upstream floating-point residuals. Exact arithmetic on saved numbers does not make the historical fills or fee assumptions exact observations.

The relevant runtime/test/frozen/workflow bytes are unchanged from the previously executed base **71f137f**. Existing repository validation was **449 passed, one skipped and nine subtests**; this cost derivation changes no executed production code. The separate synthetic box evidence remains 19 cases/98 outcomes, with protective reconciliation halts in the tested valued-residual cases. No new real orders, accounts, funds, paid services, human messages or excluded repositories were involved.

Companion JSON retains the exact inputs, formulas, pair outcomes, source hashes and limits; the independent review and freshness receipt are saved separately. This result narrows the supported economic claim about the faster route and leaves profitability unvalidated.
