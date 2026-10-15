# Improvement backlog from the three research sources

Dated 2026-10-14. These are scoped items and acceptance criteria, not claims that all are implemented or approved for production. P0 closes existing integrity/evidence blockers; P1 improves reusable controls; P2 needs fresh data or a component-specific hypothesis. No new acquisition, order, paid tool, frozen edit or automatic strategy reset follows from this list.

| ID | Priority | Improvement | Target | Current status | Acceptance evidence |
|---|---|---|---|---|---|
| I01 | P0 | Retain scorer attempts | PR16 workflow | Proposed; blocked on public-egress approval | Success/failure/input/publication receipts survive runner; replay does not erase failed attempt. |
| I02 | P0 | Reject false scoring completion | PR16 wrappers | Implemented on branch; independent review+CI528 | Empty/unestimable data cannot publish; valid FAIL can; retry/atomic uncertainty retained. |
| I03 | P0 | Keep first-observation gaps | PR17 coverage | Implemented on branch; owner policy consequence | Late/backfilled/legacy gaps cannot qualify original cohort; no silent reset. |
| I04 | P0 | Close fills and value inventory | PR17 gate/reconcile | Implemented on branch; CI534 | Partial/undersold/nonfinite/unknown holdings cannot pass; valid finite baseline still passes. |
| I05 | P0 | Resolve applicable fees and units | CDE/Alpaca evidence | Evidence dependency | Current account/product fee basis, minimums, funding rate/interval/book units and actual paid fees evidenced. |
| I06 | P0 | Qualify one complete cohort | Existing US candidate research | Missing fresh evidence | Real first-observed opportunity universe, quote/fill/account controls and attainable independent sample exist. |
| I07 | P1 | Claim-to-source ledger | CLAIMS.json and future intake sidecars | Document template delivered | Every relied-on numerical/architecture claim has source/version/locator/status and contradiction record. |
| I08 | P1 | Track version drift | SOURCES.json + review triggers | Documented; no new collector | Pinned versions remain distinct; denominator changes trigger re-review, not silent replacement. |
| I09 | P1 | Separate evidence dimensions | Candidate card | Planning template delivered | No scalar grade conflates runnable/licensed/eligible with cost-qualified or statistically validated. |
| I10 | P1 | Denominator and failure card | Existing trial/evidence ledger sidecar | Planned extension; reuse PR15 | Candidates/signals/fills/trips/days/clusters/missing/late/excluded counted with reasons. |
| I11 | P1 | Structured available-at fields | Coverage/input contract | Partial PR17; general extension planned | Event/published/observed/confirmed/computed/usable clocks checked against cutoff and revisions. |
| I12 | P1 | Authoritative-state boundary | Own accounting/agent interface | Policy delivered; runtime interface future | Generated narratives cannot mutate cash/inventory/risk or bypass unknown states. |
| I13 | P1 | Outcome-time memory filtering | Local evidence retrieval | Not implemented | A historical decision cannot retrieve later outcome/reflection; availability test includes revised summaries. |
| I14 | P1 | Version summaries and corrections | Knowledge/memory entries | Principles retained; no RAG build | Lessons link immutable receipts, status, scope, known-at/superseded time and revalidation trigger. |
| I15 | P1 | Typed action lifecycle | Paper adapter/evidence contracts | Partial PR17; complete general contract future | Request/ack/partial/cancel/reject/timeout/fill/account paths have causal IDs and clocks. |
| I16 | P1 | Finite derived arithmetic | Accounting/cost/control boundaries | PR17 repaired; broader checks scoped | Aggregates, products, sums and conversions fail unknown on overflow, not just finite scalar inputs. |
| I17 | P1 | Fee-once hierarchy | Existing PR15 controls | Implemented on branch; real receipts missing | Embedded LP/protocol/creator/buyback subdivisions never become duplicate charges; service costs explicit. |
| I18 | P1 | Fundability before returns | PR18 static preflight | Implemented on branch | Actual source minimum/units and candidate capital pass before adapter; source defaults not venue rules. |
| I19 | P1 | Executable size and passive fills | Quote/order lifecycle evidence | Missing for full passive grid | Intended-size quotes, order lifecycle, partials and paid-fee evidence; OHLC is insufficient. |
| I20 | P1 | Measure opportunity latency | Own observation/decision receipts | Planned only when needed | Latency distribution/quote age fits declared horizon; no borrowed generic millisecond claims. |
| I21 | P1 | Full-account matching | Existing CAPIT controls / own screens | Code partial; untouched evidence missing | Controls share opportunities/capital/constraints and retained cash/inventory; known losses not discarded. |
| I22 | P1 | External flow accounting | Account ledger/research analysis | Protocol requirement | Deposits, withdrawals, rewards/salaries separated from investment return; conservation reconciled. |
| I23 | P1 | Exposure/style attribution | Future controlled comparison | Not run | Hold/cash/beta/exposure-matched comparisons separate selection from market drift; disclose risk mismatch. |
| I24 | P1 | Independent-event uncertainty | Protocol and result cards | Planned protocol qualification | Cluster shared wallets/mints/days/news; no pseudo-replication of swaps/posts or panels. |
| I25 | P1 | Chronological splits and overlap | Existing frozen plans/future candidates | Preserve old; new protocol explicit | Leakage, revisions, fitting windows and overlapping outcomes handled before fresh evaluation. |
| I26 | P1 | Search/adaptation lineage | Existing PR15/18 ledgers | Implemented partial; no new ledger | Every candidate/retry/prompt/baseline revision counted; complete grid and failed/blocked variants retained. |
| I27 | P1 | Power and stop rules | Future prospective protocol | Not fixed until feasible cohort known | MDE/independent-event target/readout/multiplicity/stop criteria justified with permitted dev evidence. |
| I28 | P2 | Regime coverage | Descriptive research reporting | Future; no adaptive filter | Regimes defined using available past data; no full-sample clustering or post-loss retuning. |
| I29 | P2 | Risk/return tradeoffs | Full-account report | Existing metrics + planned additions | Drawdown duration/tail/capacity and precision accompany net return; no sparse CVaR certainty. |
| I30 | P1 | Source-rule fidelity | PR18 profile/adapter reviews | Implemented partial | Exact equations/defaults/omissions and replication/adaptation status auditable; no silent clamps. |
| I31 | P1 | License and US route fit | Existing source triage/preflight | Implemented on branch | Actual license bytes/attribution/product/account rights confirmed separately; unknown stays blocked. |
| I32 | P1 | Research operating-cost receipts | Own run receipts/sidecar | Not generally implemented | Calls/tokens/retries/time/inference/hardware/data costs metered or unknown; no vendor estimates as actuals. |
| I33 | P2 | Equal-budget component ablation | Any proposed LLM/multi-agent component | Conditional future only | Same information/resources and no-component baseline isolate incremental contribution after costs. |
| I34 | P2 | Pretraining contamination diagnostic | Future historical LLM trial | Conditional future; not run | Identity/date masking and fresh data tests prespecified; masking is not proof of no memorization. |
| I35 | P2 | Buyer breadth/concentration | Exact-mint saved evidence | One explored episode; feature validation proposed | Verified gross-debit shares/HHI/effective address count with coverage; no smart-wallet label. |
| I36 | P2 | Buyer chronology/link uncertainty | Buyer histories | Coverage dependency | Returning/first-observed/history-unknown separated; only evidenced address links, with bounds. |
| I37 | P2 | Original social breadth | Exact-mint social evidence | Continuous coverage absent | Original/repost/duplicate/author denominators and first-observed clocks; no inferred wallet identity. |
| I38 | P2 | Composition-by-volume hypothesis | COMPOSITION-VOLUME-PROPOSAL.md | Planning only; no return screen | One added interaction vs fixed price/volume/liquidity baseline; untouched cohort and full economic prerequisites. |
| I39 | P1 | Missingness/selection sensitivity | All candidates | Protocol requirement | Failed/late/delisted/unavailable cases retained; no survivorship-only favorable cohort. |
| I40 | P1 | Adverse-path engineering tests | Existing controls/CI | 918 combined tests passed | Meaningful causal/accounting counterexamples and positive controls; tests do not count as market events. |
| I41 | P2 | Govern adapted components | Future mutable model/memory | Policy only; no online updates | Mutable fields, trigger, lookback, rollback and execution/cost invariants fixed and reviewable. |
| I42 | P1 | Independent review and integration | Existing codex PRs | Seven reviewed together locally; Claude gate remains | Exact-head tests/receipts and conflict resolution retain owner/frozen paths; no self-approved main merge. |
| I43 | P1 | Quiet evidence-driven follow-up | Existing heartbeat/baton | Existing cadence retained | Advance only on material new input; respect shared acquisition/screen/storage caps and no duplicate collector. |
| I44 | P1 | Retain rejection and correction knowledge | Saved triage/claims/lesson notes | Documented; negative screen preserved | Unchanged failed claims not revisited under aliases; superseded claims remain traceable. |
| I45 | P1 | Evaluate decision value | Project planning | Charter delivered | Next task names uncertainty reduced, data prerequisite and cheapest discriminating check; no activity quota. |

## Work sequence

1. Finish review/integration and durable attempt retention without changing strategy math or owner books. The PR16 workflow proposal remains unapplied pending explicit egress authorization. PR17 lifetime-incomplete coverage needs the owner to understand the consequence; it is not an excuse for a reset.
2. Use existing source/attempt ledgers, this source review and the candidate sidecar to choose one concrete unresolved evidence question. Resolve fees/units/quotes/account coverage for an existing US candidate before a new architecture build. A blocker may justify deferral rather than more collection.
3. Validate deterministic descriptive features and chronology only where already-permitted saved data can answer a declared question. Keep the one selected historical buyer episode explored.
4. Plan one feasible untouched comparison with an independently reviewed protocol and power/readout schedule. The composition proposal is a future research candidate, not a re-opened memecoin trading lane.
5. Consider an LLM/retrieval/coordination component only after a fixed equal-resource ablation can measure its incremental value.

## Deferred work

No immediate large RAG database, model training/RL, online self-modification, full synthetic market world, autonomous trading debate, leverage, subscriptions or additional always-on sources. Those designs remain possible future tools if a measured bottleneck and feasible controlled comparison justify them. There is no evidence here that complexity or the quoted literature returns will improve our account.
