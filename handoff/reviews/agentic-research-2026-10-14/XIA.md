# Xia et al. review: evidence principles and concrete CoinHunt implications

Reviewed supplied **Agentic Trading: When LLM Agents Meet Financial Markets**, Xia et al., arXiv **2605.19337v1**, 59 PDF pages. Page references below are PDF pages, which match the printed page numbers. This is a paper review and an internal consistency audit, not an independent replication of the surveyed studies.

## Source and verification boundary

- Supplied file: `2605.19337v1.pdf`.
- Supplied extraction metadata: 11,271,491 bytes; SHA256 `14f40887163808b36333f3539b0279d4497971e7a85408a62437b34f9c5c40ec`; 59 pages. The metadata was supplied by the parent extraction, not independently rehashed here.
- Primary version page checked: <https://arxiv.org/abs/2605.19337v1>. It identifies the title/authors, v1 submitted **2026-05-19**, and a later v2 dated **2026-10-04**. This review stays with the supplied v1; it does not silently incorporate v2. The primary page's abstract matches the supplied audit-oriented 77/19 account. No remote PDF was downloaded, so byte identity with the current arXiv PDF was not independently checked.
- Read the substantive text across PDF pp. 1-47 and the remaining appendix flow/table on pp. 48-49; inspected the bibliography for cited mechanisms and source references. S1-S3, the actual study-by-field registry and adjudication sheets, are described but are **not present as full machine-readable/per-study ledgers in this supplied PDF**. They were not retrieved. No surveyed GitHub repository was fetched or run.
- Used bundled Poppler to render and visually inspect PDF pp. **5, 24, 33, 35, 38, 39, 45, 46, 49**. The apparent mixing of callout text and body text in the plain-text extraction is reading-order interference; these rendered pages are clean and separable. Table C.24's row issue below is visible in the PDF, not merely an extraction artifact.
- Artifacts here are work notes and rendered pages only. No project repository, private account, order route, CTS path, or memory file was read or changed for this review.

### Explicit version-drift caveat

The **19-study findings below belong to the supplied v1**, not current literature-wide rates or pooled v2 claims. The [v2 abstract](https://arxiv.org/abs/2605.19337v2) reports 185 included studies and 80 empirical systems, materially changing the survey's framing.

A bounded [official v2 HTML](https://arxiv.org/html/2605.19337v2) spot-check found that Table 4 preserves the initial 19-study counts, adds 61 extension studies and reports pooled coverage. Different retrieval/coding procedures prevent interpreting cohort differences as a temporal improvement trend. V2 also clarifies that the 15-record audit used a legacy 41-record frame and includes seven now-narrative-only records; it is not representative reliability evidence for the current empirical cohort. The authoritative-state/context separation, MR-1-MR-7 guidance and frozen cost/execution update governance persist. The memory section retains the post-hoc-retrieval warning; the exact phrase “Outcome Embargo” was not found in parsed HTML, so persistence of that detailed v1 callout is unverified. This was a limited spot-check, not a second full review; do not pool its counts with v1 or carry v1's sparse-reporting percentages forward as current prevalence.

## Main lesson and its evidential strength

The useful conclusion is **protocol incomparability**: sophisticated agent architecture does not establish an executable, net-positive trading result. The paper explicitly presents A-C-A (Architecture, Capability, Adaptation) as an exploratory organizing lens, not a validated taxonomy, winning architecture, or trading edge (pp. 3-6, 41-44). Its strongest empirical contribution is a description of what the sampled primary studies report, rather than evidence that LLM agents outperform conventional trading.

This is an audit-oriented evidence map rather than an exhaustive systematic review. Search sources are ACM Digital Library, IEEE Xplore, arXiv, SSRN and Google Scholar plus citation chaining; the formal window is 2022-01-01 to **2026-03-09** (pp. 4, 43-44). Consequently, its field-wide claims are bounded by a curated, time-specific sample and conservative extraction rules. The later upload date does not extend the registry cutoff.

## The denominators that must stay separate

| Quantity | Paper's number | Meaning and page |
|---|---:|---|
| Deduplicated candidate registry | 92 | The candidate pool, not all available literature; pp. 4-5, 48 |
| Final excluded | 15 | Outside finance/trading/portfolio/risk-management scope; pp. 5, 47-49 |
| Included evidence map | 77 | Primary evidence plus useful background/context; pp. 4-5 |
| Primary empirical subset | 19 | Action Output **and** Closed-Loop Evaluation, plus an eligible empirical evaluation type; pp. 4-5 |
| Included background/context | 58 | Finance-relevant context that does not meet the primary boundary; pp. 4-5, 47-49 |
| Earlier double-screened raw sample | 182 | An older screening-boundary quality check, predating the canonical 92; not the extraction denominator; p. 5 |
| Extraction-level audit sample | 15 | Fixed-seed primary-study audit, seed 20260426; not 15 additional studies; pp. 5-6 |
| Illustrative A-C-A reclassification set | Claimed 20 | Separate, author-curated notes spanning primary/background/boundary works; visible table actually has 19 rows; pp. 43-45 |

**Action Output** includes orders, position changes or portfolio allocations. **Closed-Loop Evaluation** includes backtests and simulations, and the eligibility language also accepts benchmarks and live evaluations (p. 4). Therefore, passing the paper's primary boundary is weaker than demonstrated real brokerage execution. An allocation backtest can qualify while lacking an adequate price/fill/cost protocol. A primary-study count cannot be read as a count of funded live deployments.

Finance-relevant prediction models, analysis tools, general benchmarks and signals without evaluated actions can remain useful background. They are not failed trading systems simply because they are outside the primary denominator. Conversely, a useful NLP or engineering component is not evidence of a complete trading loop. Examples and exclusion logic are on pp. 47-49, particularly Table D.25.

## Protocol coding, headline counts and limitations

Within the fixed primary **n=19**, the paper reports (pp. 1, 3, 41, 43, 46):

| Extractable reporting field | Count | Recalculated share |
|---|---:|---:|
| Time-consistent split protocol | 2 | 10.5% |
| Explicit transaction-cost model | 1 | 5.3% |
| Universe/survivorship handling | 1 | 5.3% |
| Execution timing/semantics | 11 | 57.9% |
| Artifacts beyond narrative description | 4 | 21.1% |

Missing or unclear reporting is coded **NR/Unknown**, not imputed as an absent implementation (p. 5; reading note p. 43). These percentages measure extractability under this review, not the true prevalence of leakage, costs or safeguards in every system. The p. 46 figure also warns that applicability varies: an execution-only study may receive an exogenous universe rather than select one. The `1/19` universe statistic therefore is not a clean prevalence estimate among only studies that require universe construction.

The PDF does not expose the full 19-row, field-by-field ledger, so this review could check arithmetic and concordance of summaries but could not independently reproduce the coding of each paper. It is not possible from this supplied PDF alone to establish which exact single study carries each positive cost/universe field or to resolve all section-level tag differences.

The paper's reliability statement should not be overread. Table 4 reports **100% agreement after adjudication** for 15 extraction-audit studies and refers field-dependent agreement details to S3 (pp. 5-6). Adjudicated agreement is not a reported pre-adjudication inter-rater reliability statistic. The older 182-record screen is expressly not evidence that extraction fields, R tiers or A-C-A classes are reliable. Appendix C's taxonomy examples are initially coded by one author and reconciled by the authors, without external validation (p. 44).

The corpus is also predominantly recent and provisional: 18/19 primary studies are dated 2024-2026, and 17/19 are coded non-peer-reviewed versus 2/19 peer-reviewed (p. 43). These are the authors' registry metadata, not a current independent venue-status verification.

## Reproducibility tiers: what they do and do not mean

Table B.23, visually checked on p. 45, defines:

| Tier | Operational meaning in the paper | Count /19 |
|---|---|---:|
| R0 | No runnable artifacts: no public repo, broken/404 repo, or missing essential files preventing a run | 15 (78.9%) |
| R1 | Public accessible code exists, but key dependencies, data access or evaluation pieces are missing; not runnable | 1 (5.3%) |
| R2 | Complete code, accessible/documented data, evaluation scripts; still may lack a pinned environment, full documentation or an end-to-end pipeline | 3 (15.8%) |
| R3 | Complete code with pinned environment, snapshots/access instructions, documentation and an end-to-end evaluation pipeline | 0 |

The R0/R1 criteria partially overlap in missing essential/key components, so copying the ordinal tags without an explicit adjudication rule would create ambiguity. Preserve the underlying artifact facts and reasons, not just a single level. R2/R3 are package/reproduction descriptions, not proof of statistical validity, lawful reuse, source safety, net returns or out-of-sample edge. A runnable codebase may still implement an unfunded parameter grid or an invalid fill model.

For our GitHub triage, retain independent dimensions: repository identity and pinned commit; actual license and reuse status; artifact availability; environment completeness; data access rights and date coverage; action/market compatibility; execution semantics; cost assumptions; screenability; and result validity. A paper PDF's arXiv distribution license is not a license to reuse an associated code repository. The supplied PDF metadata's nonexclusive arXiv distribution license does not solve repository licensing.

The paper says S1-S3 and LaTeX are submitted with the manuscript and an anonymized repository is to be released upon acceptance, subject to policy (pp. 42-43). That is an availability promise, not a verified released ledger or reproduction package in this review.

## Useful concrete designs, with their evidence status

### 1. Separate authoritative state from generative context

PDF p. 10 distinguishes a deterministic state store (positions, balances, open orders, risk limits) from transient LLM context. Its proposal is that the LLM reads this state while the environment/OMS/EMS updates it. Page 12 adds a hierarchy in which authoritative internal state overrides noisy external material. This is a concrete architecture recommendation; the survey does not establish its measured alpha benefit.

**Application:** an LLM may propose or explain a candidate, but cannot create a fill, override an unknown fee, repair inventory by narrative, or convert missing coverage into a complete cohort. The account and execution reconciliation ledger must be authoritative and machine checked. Private credentials and trading authority are separate from read-only research, and nothing in the paper authorizes enlarging that authority.

### 2. Represent information availability, not merely event/publication time

Publication time can precede availability to a trading pipeline; disclosures can be revised (p. 7). Text/price/visual inputs have different update rates and processing delays (p. 8). Macro inputs should use unrevised release-time values; full-sample regime clustering can leak future regimes (p. 22). Scheduled events and shocks require different information treatment (p. 23).

**Application:** attach `event_at`, `published_at`, `first_observed_at`, `available_at`, revision/version and source timestamp quality to relevant evidence. Store the actual acquisition failure and lateness, rather than backfilling a retrospective item into the original decision context. A useful falsification test is to perturb availability by realistic lag and verify that a signal never appears before its own receipt. This is a proposed extension/check, not evidence that all these fields already exist.

### 3. Enforce outcome embargoes in episodic retrieval

PDF p. 10 defines an episode as state, action, eventual outcome, and the time the outcome becomes observable. Pages 10-12 warn against retrieving a post-event explanation into an earlier decision. Page 20 extends point-in-time governance to factor libraries and performance metadata: only facts known at decision time are eligible.

**Application:** an append-only research log and a live decision-time retrieval view are different objects. A failed backtest or later profitable outcome may be retained forever for auditing, while being ineligible to answer a historical query before its observation time. Filtering must cover labels, summaries, embeddings and performance-based ranking, not just raw news dates. Consolidated summaries should retain an immutable pointer to the underlying evidence and be checked for added future facts (p. 35).

### 4. Use a typed decision-to-execution lifecycle

The reasoning I/O contract consumes timestamped observations, eligible memory and read-only portfolio state; outputs are candidate actions plus uncertainty/validity information (p. 13). The action I/O contract converts intent into orders with side, size, limit price and time-in-force, while modeling **Rejection, PartialFill, Timeout** (p. 16). Target weights are not executable orders; price, timing, liquidity and order constraints determine the execution gap (p. 17).

**Application:** maintain explicit statuses for proposal, eligibility, preflight, scheduled decision, order intent, acknowledged order, partial fill, filled quantity, cancel, rejection, expiry/timeout and account reconciliation. A `BUY` string, a paper position or an OHLC touch cannot imply a passive fill. Match timestamps, quantities, clock domains, commissions and finite inventory all the way through. The paper supports designing/reporting these contracts, not claiming our broker integration has been exercised.

### 5. Freeze the conversion from a signal into an economic outcome

The proposed alpha-to-trade contract asks whether signal frequency matches latency, whether returns survive turnover/costs, and whether liquidity supports the assumed capital (p. 18). Its inference economics require model version, pricing date, token budget, tools and breakeven net economics, rather than a stale vendor price (p. 40). Execution testing should vary fees, spread, slippage and impact (pp. 17, 38-40).

**Application:** declare the instrument and whole-order constraints, cash, account type, funding/borrow treatment, execution policy, fee basis/minimum and cost components before scoring. Unknown units or billing cannot be silently replaced by a plausible default. Separate a gross diagnostic from a cost-qualified score. Count a fee once; distinguish per-contract/per-side/minimum/bundled components. This follows the methodological lesson; the paper provides no current CFM fee schedule or REST field-unit mapping.

### 6. Treat search, reflection and adaptation as additional trials

Code generation/backtest feedback mines the validation set; MCTS/evolution adds multiple-testing risk (pp. 15, 19-20). The paper recommends explicit hypothesis/node/search budgets and an untouched final test. It says reflection limits and formula originality do not themselves supply false-discovery guarantees (p. 20). Reflection should be bounded and cannot use OOS outcomes to decide when to stop (p. 37). Update governance must list mutable prompts/memory/retrieval indices/weights, triggers, lookback windows, rollback and frozen cost/execution semantics (pp. 34-38).

**Application:** a rejected candidate, failed prompt, retry, parameter setting, changed baseline, altered fee assumption and post-result rule revision all need lineage. Daily attempt caps are useful budget controls but do not establish statistical power or multiplicity correction. Source-code novelty, AST distance and a plausible story are not financial novelty. Log the complete intended grid, including unfunded/not-screenable members, instead of reporting only surviving screens. A new goal or model must not be smuggled into a registered evaluation.

### 7. Use agents where attribution can be tested

Multi-agent systems can decompose work; their extra performance is not established once compute, information and protocol are controlled (pp. 29-35, 42). The paper recommends role/permission logs, message and tool budgets, proposed/vetoed-action contribution logs, role/channel ablations and cross-play. Consensus is not correctness (p. 37). Its fast/slow cascaded controller is explicitly a synthesis recommendation, not a newly validated contribution (p. 15).

**Application:** use agents for bounded source extraction, adversarial arithmetic/protocol review and evidence triage. Require any claimed predictive gain from LLM/coordination to beat the same data, capital, cost and compute baseline with the LLM/extra role removed. Deterministic risk gates belong outside the explanatory model (pp. 25-26). Do not build more live agent roles merely because the survey illustrates them.

## Minimum reporting checklist as an implementable evidence card

The paper's MR-1-MR-7 checklist is on **p. 38**; the applicability matrix and rationale are on **p. 39**. Treat this as an author-proposed checklist. It is not a community standard or a license to relax our own controls. Notably, artifacts are marked Recommended for all study types, and multi-agent/adaptation reporting is Optional/contextual for end-to-end systems. We may choose stricter completion requirements for claims we intend to rely on.

| Checklist | Evidence our card should require | Applicability nuance |
|---|---|---|
| MR-1: Data/universe | Tradable universe and point-in-time inclusion rules; source/version; publication, observation and revision times; survivorship/delisting/failure coverage | Mandatory in the paper for end-to-end and components; universe selection may be exogenous for execution algorithms |
| MR-2: Time split | Exact train/dev/validation/test dates; freeze dates; purge/embargo; chronological/rolling rules; complete search and selection budgets | Mandatory across all three study types; validation is not the final test |
| MR-3: Action semantics | Signal/target/order type; units; decision/order/fill times; price formation; constraints; invalid/partial/timeout outcomes | Mandatory for end-to-end and execution, not a prediction-only component |
| MR-4: Execution/cost | Frequency; executable-side quote; order model; fees/spread/slippage/impact/financing; capacity and latency; fill-rate/shortfall where relevant; sensitivity | Mandatory for trading-profit/execution claims; do not penalize an analysis component for having no trades, but do not promote it to trading evidence |
| MR-5: Leakage audit | Feature fitting, revisions, hindsight text, labels, embeddings, retrieval outcomes, future universe and timing; explicit NR/Unknown reasons | Mandatory for end-to-end in the paper; recommended elsewhere; stricter internal policy can be declared |
| MR-6: Artifacts/logs | Source commit/license; env; snapshots; formulas; seed; data/query receipts; decision/order/fill/account links; immutable source pointers; pricing/compute cost; update trigger/window/rollback | Package availability is separate from independent replay; hash chains are not independent registrations |
| MR-7: Agent/adaptation | Roles, tool authority, message schemas/budgets, shared state, consensus/abstain rules, complete update lineage; matched-budget ablation/cross-play if claiming coordination gain | Require when making a coordination or self-improvement claim, even though matrix marks optional applicability |

Suggested independent status columns: `scope_eligible`, `action_closed_loop`, `protocol_completeness`, `artifact_replay_level`, `license_status`, `execution_coverage`, `account_match_status`, `economic_qualification`, `prospective_status`, and `decision`. None should be derived from a single aggregate rank. Every failure or unknown needs a reason and source locator. A denominator card should state the eligible cohort, observation window, attempted/missing/late cases, exclusions and which conclusion the denominator supports.

## Existing controls versus material gaps

The following current-code descriptions were supplied by the parent during this review; I did **not** independently inspect these branches. They are **proposed/unmerged branch controls**, not production assurances.

| Paper lesson | Controls already represented | Concrete remaining evidence/work |
|---|---|---|
| Complete trial/search lineage | PR15 `research_evidence.py` / `edge-hunt/patterns/capit_account_controls.py`: offline append-only trial/access/result/rejection records, strict protocols and hash-anchored chains; PR18 daily two-attempt/dedupe guard | Avoid rebuilding another ledger. Add a machine-readable MR/evidence/denominator card only if fields are missing; record trials and invalid outcomes across the full predeclared grid. Preserve the distinction between a local hash chain and an independently signed/time-anchored registry. |
| Freeze protocol and retrospective access | PR16 `final_scores.py` / `scoring_receipts.py`: prospective-only 14-source lock (12 underlying, 2 engineering), 37 frozen pins, finite reports, atomic results/retries, all eight legacy formats | Scheduled scoring-receipt retention remains unresolved. A passing scorer implementation is not a retained prospective observation. Demonstrate receipt retention and evidence availability without later backfilling missing history. |
| Information-availability timing | PR17 `observation_coverage.py`: per-coin/hour first-observed versus event time, permanent missing/late markers | Need untouched real-time cohort evidence, exact-mint continuous social coverage and buyer-use proof. Later observation cannot erase an original late/missing state. Check whether revisions, embeddings and summaries use the same availability boundary. |
| Intent/order/fill/account separation | PR17 `live_gate.py`: complete matched quantity/clock/finite-inventory evidence; PR18 preflight does not infer passive fills from OHLC | Full-account controls still lack the untouched real US cohort. No current complete executed order/fill/account trail or real-cost confirmation follows from the gate's existence. Test rejection, partial fill, timeout and data-gap cases with fixtures, then demand actual observation before a live claim. |
| Economics at feasible size | PR15/PR18 fee-once, cash/account known-loss controls; offline own-screen controls | Actual fees remain unknown. Resolve dated applicable charges, funding units/timing and execution coverage before allowing a cost-qualified score. Include inference/tool cost when an LLM is in the strategy, and avoid treating initial margin as exposure or gross return as deployable net profit. |
| Reusable source triage | PR18 `github_strategy_discovery.py`: pinned source and actual-license triage, unknown licenses blocked; shared 24h budget of 24 GET / 16 MiB; preflight | Do not fetch more snapshots to satisfy this paper. Retain R-tier-like facts as separate columns, reuse the frozen evidence, and reject/suspend work when required artifacts, licenses, capital or execution semantics are absent. A paper's GitHub link is a lead, not a reproduction. |
| Report failed/unscreenable work | One explored daily BTC 50/50 adaptation fails hold after costs; pytrader's full grid is unfunded and NOT_SCREENABLE | Keep both outcomes visible. Do not turn the daily BTC failure into proof all LLM strategies fail, or the unfunded grid into empirical losses. Define the next experiment by the bottleneck it resolves, not by the number of repos/papers consumed. |

The primary gap is **evidence acquisition and economic qualification**, not a missing architectural vocabulary. The proposed branches already address many of the reporting failures the paper identifies. Completing branch review/merge/retention checks and gathering one untouched, feasible, cost-qualified cohort has greater decision value than adding another multi-agent runtime or source-discovery lane.

## Goal alignment suggested by this paper

This paper supports retaining the long-term goal of a US-expressible, feasible, demonstrably incremental trading edge, while changing the near-term objective to **finish one auditable falsification/qualification path**. It gives no evidence for a fixed dollar return, a 2-5x target, a new perpetual strategy, or a claim that “agentic” means profitable.

Proposed order, subject to the parent's synthesis and the user's actual priorities:

1. **Close evidence and economics blockers already identified.** Preserve prospective receipts; choose one declared instrument/cohort and capital constraint; resolve applicable costs/units and what execution/account evidence will actually be available. If a requirement is unavailable, record not-screenable/blocked status and stop spending on that candidate.
2. **Freeze one complete baseline and comparison.** Use the same source coverage, chronology, capital, action constraints and conservative cost model; define what incremental contribution an LLM would need to show. The baseline may be hold/no-trade or a simple deterministic rule, selected before outcomes.
3. **Run a bounded prospective comparison only when screenable and authorized.** Include all attempts and no-trade/invalid/missing cases. Keep full cohort/account matching and no backfilled timestamp repairs. Offline/paper evidence and live execution remain separate labels.
4. **Promote complexity only against a predeclared bottleneck.** Outcome-embargo retrieval or agent-role ablations are useful if the strategy actually uses those mechanisms; they are unnecessary work if today's blocker is fees, passive-fill semantics, source observation or capital feasibility.
5. **Retain negative results as progress.** A failed after-cost baseline comparison or a credible not-screenable determination is a useful research outcome. It should reduce future search, not invite unlogged retries until a favorable result appears.

Suggested success measure: number of candidate claims whose status changed for a documented reason (screenable, falsified, passed a prespecified gate, or stopped), coupled with retained chronological and economic evidence. Paper count, architectural features, source count and test count are supporting engineering measures rather than edge measures.

## Snapshot consistency audit

### Checks that passed

- `92 = 77 + 15`; `77 = 19 + 58` (Table 3, p. 5; Figure D.17, p. 48).
- All listed primary-field percentages match the fixed denominator 19 when rounded to one decimal.
- R-tier counts `15 + 1 + 3 + 0 = 19`; R2+ is `3/19 = 15.8%` (Table B.23, p. 45). The p. 46 chart agrees.
- Figure B.16's evaluation bars are backtest 11, live 3, simulation 2, benchmark 3, narrative-only 0 and unknown 0; the nonzero bars sum to 19 (p. 46). These are reported evaluation labels, not independently verified deployment facts.
- Figure B.16's split bars are other 2 and unknown 17, with walk-forward and rolling both zero; that matches 2 extractable split protocols, but **does not establish that those two are walk-forward tests** (p. 46).
- Table D.25 gives representative, not complete, exclusions/boundary examples (p. 49). Four displayed out-of-scope examples cannot be used to recount the claimed 15 final exclusions.

### Reproduced visible inconsistency: illustrative reclassification count

Table C.24's caption says 20 works, as do pp. 43-44. Visually counted rows on p. 45 are: FinBERT, FinGPT, FinLlama, AlphaAgent, FinAgent, Alpha2, RAG-Fintech, RAPTOR, AgentGuard, FinRS, TradingAgents, TradingGroup, FINCON, FinMem, MetaGPT, FinRL-DeepSeek, Reflexion, Hashimoto, FinEvo: **19 rows**. Appendix C's temporal note says 17/20 (85%) are from 2024-2026 (p. 44); the displayed rows contain **15/19 (78.9%)** in that period. FinBERT (2019), FinGPT (2023), FinMem (2023), Reflexion (2023) are the four earlier rows. A missing row could change the intended set but cannot establish the printed numbers from the supplied table. The manual row transcription and arithmetic are saved in `xia-count-audit.json`.

This affects the illustrative taxonomy notes, **not** proof that the separate n=19 primary registry is wrong. Do not conflate the coincidental 19 displayed reclassification rows with the primary 19; the former includes obvious background works.

### Apparent ambiguity: coordination counts

PDF p. 33 says nine of the 19 primary studies addressed coordination mechanisms. The p. 35 multi-agent summary says the section-level primary count is N=12; p. 30 also refers to N=12. Both statements are visually present. A distinction between “addressed coordination mechanisms” and a broader section-mapped set could reconcile them, but the PDF does not supply the relevant membership mapping. Treat this as **unresolved denominator ambiguity**, not a proven error in the headline registry.

### Apparent inconsistency: eligibility and completeness shorthand

The explicit canonical primary boundary on p. 4 is Action Output plus Closed-Loop Evaluation. Missing protocol fields are separately NR/Unknown on p. 5; indeed, 18/19 primary studies lack an extractable explicit cost model. The portfolio callout on p. 24, however, says studies that fail to report specific I/O contracts **or cost models** are graded BG (Conceptual). If applied as a general eligibility rule, that would conflict with the main boundary and headline cost statistic. It might instead mean a stricter section-specific evidential use, but that narrower mapping is not exposed. Our registry should **not** copy this shorthand: preserve scope/evidence role independently from completeness and claim permission.

### Other cautions, not recountable defects

- Tables 13-15 use protocol-tag language in captions even where displayed rows are broad paradigm/design comparisons rather than the full study-by-field audit (pp. 21, 24, 27). They cannot reconstruct S2.
- Table 16 is titled a learning-paradigm performance comparison, but surrounding text explicitly calls it conceptual and reports zero SFT primary studies (pp. 28-30). Its qualitative speed/adaptability entries are not measured comparative performance results.
- Table 7 calls latency labels author-reported and points to S2, but the PDF gives qualitative Low/Med/High entries without a recoverable benchmarking protocol (p. 9). Do not use these labels as operational latency budgets.
- Section 12 has four primary studies across consolidation 2, meta-learning-like adaptation 1 and reflection 1 (pp. 37-38), while the text states no study explicitly implements a finance-specific meta-learning algorithm such as MAML (p. 36). The word “like” matters; it does not establish one MAML trading study.
- Paper-wide “none explicitly risk-focused as a primary contribution” and issue-level N=0 statements mean absence of a coded main contribution, not that no primary agent has risk controls or leakage concerns (pp. 27, 39-40).

## Claims to reject in downstream synthesis

- “77 studies prove LLM trading works.” Only 19 meet a minimal action/closed-loop boundary; the evidence map does not estimate an aggregate alpha.
- “Only one paper uses transaction costs.” The supported claim is that only one of the sampled primary studies has an extractable explicit model under this coding.
- “Three live studies validate deployment.” The figure reports three live-labeled evaluations; actual account, instrument, fill and cost coverage was not independently audited here.
- “R2/R3 proves profitable, safe or licensed.” These are artifact/package tiers.
- “A-C-A is the optimal architecture” or “more agents/reflection improve returns.” The authors repeatedly qualify these as lenses/designs requiring controlled attribution.
- “A trace explains the true cause of a trade.” Rationale observability is not faithfulness; bind claims to actual source snapshots and execution records (pp. 1, 16, 18, 26).
- “Outcome-aware memory or a small reflection budget solves overfitting.” Temporal filtering and bounded search help experimental discipline; they do not give statistical guarantees.
- “This paper supplies current fees, market capacity, Coinbase REST units, US account eligibility or live permission.” It does not.
- “We should loosen existing frozen protocols because reporting is weak in the literature.” The paper argues for stronger evidence; it does not authorize a change to our registrations or implementation scope.

## What remains unchecked

No full S1-S3 registry or raw agreement sheet; no individual 19-study coding replication; no re-execution of surveyed systems; no license/API/account verification for cited projects; no legal/regulatory interpretation; no complete v2 review or snapshot comparison; no independent review of the parent-supplied CoinHunt branch descriptions. The findings above are therefore either directly supported by the supplied v1 PDF, clearly identified internal consistency checks, the expressly bounded v2 HTML spot-check, or explicitly proposed applications to the parent-reported current controls.
