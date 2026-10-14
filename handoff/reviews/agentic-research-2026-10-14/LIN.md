# Independent review: Stephanie Lin, Real Bubbles, Synthetic Traders

Reviewed 2026-10-14. Source: `content.pdf`, SHA-256 `a9d9164cb6e04e4b67f163063f2cb543f9bb7db03f86ca2de739355d64dd946f`, 5,720,677 bytes, 82 PDF pages. This review covers the full substantive text, limitations, references, and all eight appendix simulations. Page references below are **PDF pages**, including the Harvard repository cover sheet; the printed thesis page is one less. Examples: Table 1 is PDF p.40 / printed p.39; the appendix begins PDF p.67 / printed p.66.

The thesis is an authentic Harvard undergraduate thesis, not a peer-reviewed trading-performance paper. Its most useful contribution to CoinHunt is a **falsifiable interaction hypothesis: the interpretation of volume may depend on the composition and concentration of participants**. It supplies no verified real-market edge, implementable profitable rule, calibrated crypto execution model, or way to identify intelligent wallets.

## 1. Identity, provenance, and reading scope

Harvard DASH identifies Stephanie Lin as author and dates the repository item 2025-05-22; it describes the document as a 2025 bachelor's thesis in Engineering and Applied Sciences. The thesis's own title page is dated March 2025 and says it was presented to Applied Mathematics for a BA with Honors (PDF p.2). Harvard SEAS independently lists Lin and this title among its 2025 theses. These publication and title-page dates have different meanings and should both be retained, without treating either as a replication date. Sources: [Harvard DASH record](https://dash.harvard.edu/items/930ce41e-91f2-43c9-8ebc-25a696cc32d3), [Harvard SEAS thesis list](https://seas.harvard.edu/applied-mathematics/undergraduate-program/research-opportunities/senior-thesis).

The earlier handle printed in the PDF, `https://dash.harvard.edu/handle/1/42719538`, returned a cache-miss error in this session's browser tool; the current item record and SEAS list were retrievable. This is a retrieval limitation, not evidence against identity. No GitHub or additional source/code acquisition was performed.

Full page-marked text was read from `source-1-full.txt`. PDF pages 26-29, 34-37, 40, 43, 46, 49, 54-55, 57-58, and 67-82 were rendered with bundled Poppler. I visually inspected pages 26-29, 34-37, 40, 43, 49, 54-55, 57-58, and every appendix page 67-82. Page 46's marginal-effect equation was read in the extracted text. Renders are in `lin-renders/`. No embedded code or instructions were executed. These are research notes, not edits to an operating policy or registered study.

## 2. What the experiment actually contains

| Component | Reported setup and page | Consequence for interpretation |
|---|---|---|
| Population and horizon | 40 agents, 5 synthetic stocks initially priced at $1,000, 15 trading rounds per ordinary simulation (p.17); eight simulations in the reported composition comparison (pp.33,39). | Tiny market, short horizon; 600 stock-round rows do not represent 600 independent market experiments. A round has no documented conversion into a real holding period. |
| Archetypes | Fundamentalist, contrarian, momentum, noise, and social personas (pp.18-20). Fundamentalist + contrarian are grouped as rationalists in the analysis. Figure 2 shows shares 0%, 5%, 10%, 20%, 40%, 60%, 80%, and 100% (p.34). | Rationality is a prompt assignment, not an independently measured property or an observable wallet label. Altering the aggregate rationalist share changes a bundle of personas. |
| Information | Each agent sees the market context, price history, forum activity, prior decisions, and relevant news; persistent conversation history provides continuity (pp.17-18). Agents are not told others' archetypes (p.18). | This is not realistic heterogeneous information arrival, exact-mint social coverage, or an authenticated account history. All agents share a common model family and environmental framing. |
| Fundamentals and news | No explicit real fundamental-value changes or real fundamental news shocks; synthetic gossip, order-flow impact, and random price noise drive prices (pp.21-22). Yet the appendix plots changing fundamental-price paths (e.g., pp.67,69,77), and p.25 mentions small noise representing changes to fundamental value. | The distinction between a true fundamental, an agent estimate, and an externally perturbed fundamental needs an executable specification. It cannot be assumed from the word fundamental. |
| Initial capital | $100,000 initial capital plus $5,000 salary: $105,000 total cash before allocation; exactly $100,000 is allocated equally across stocks, leaving approximately $5,000 cash for round 1 (pp.22-23). | With 40 agents this starts from $4.2 million including $4 million in the five stocks. End wealth must be adjusted for external transfers. |
| Ongoing capital | Salary from round 2, dynamically linked to a weighted average of prior three-round P&L; performance scaling is made more aggressive and capped to widen outcome distributions (pp.22-23). | Funding rewards depend on prior measured success. Wealth dispersion and ranking combine trading outcomes and researcher-designed transfers; they are not pure investment returns. The exact formula, cap, and cash-flow ledger are absent from the PDF. |
| Constraints | No short selling, no selling unowned stock, and no buying beyond available capital (pp.24-25). | Asymmetric ability to express pessimism is built in. Outcomes are conditional on these constraints; they cannot establish what enabling shorts would do. |
| Clearing | Aggregate signed demand determines impact; actual order sizes are recalculated at the impacted price, then ownership, P&L, and salary are updated (pp.23-25). An implicit market maker is acknowledged as a limitation (p.59). | No explicit order-book depth, spreads, maker capital/inventory, complete settlement equations, or fills at a particular trade size are supplied. Cash/share conservation cannot be verified from the prose. |
| Model/runtime | A move to gpt4omini and concurrency of 15 is described (p.31); average runtime for 40 agents/5 stocks/15 rounds is 1h45m-3h (p.33). | Model revision, sampling settings, prompts, run costs, seeds, and failure incidence matter for reproducibility. They are not a reason to buy or run an LLM market simulator for our project. |
| Technical failure behavior | After three failed calls, return a default action; failed upvotes may become random upvotes; active-thread failures can terminate a thread and start another, losing context (pp.31-32). | Missing model output is replaced by behavior, potentially changing the treatment and social network. Error rates by persona/round and sensitivity analyses are required before calling the patterns behavioral evidence. |
| Checkpoints | Save/reload rounds, resume after failure, extend existing simulations, or reuse/selectively change configurations (p.33). | Useful engineering patterns, but extensions and changed configurations require a declared lineage. Extending only promising paths creates selection bias. |

The main text includes examples outside a clean eight-run naming scheme: p.53 refers to Simulation 18; pp.56-57 describe a further 80%-rationalist bubble example labeled Sim-11; p.57 refers to Simulation 7 while the next caption says Sim-8 (p.58). These may be exploratory runs or caption errors. The mapping of all attempted runs to the eight analyzed runs is not supplied, so the total search/selection budget is unknown. Do not assume the eight reported runs were the only attempts.

## 3. Equations and the reported statistical evidence

### Price formation

The revised model states (PDF p.27):

`impact(q) = sign(q) * lambda * sqrt(abs(q))`, with an example `lambda = 0.01`.

The earlier clearing explanation instead states `impact = aggregate_demand * lambda` (p.24). The calibration subsection immediately after the square-root discussion returns to the linear formulas `impact = q * lambda` and `P_new = P * (1 + impact)` (p.28), with examples such as 100 net shares and lambda 0.005 giving a 50% increase, and 200 shares with lambda 0.01 giving a 200% increase (p.29). These formulas are visually present, not extraction artifacts. The linear example of -205 shares giving -0.205 (p.28) implicitly uses another lambda (0.001). The PDF does not pin which rule/parameterization generated which analyzed run.

Even a properly specified square-root function is not an executable crypto cost model: lambda has units tied to the chosen quantity scale, and there is no documented calibration to our pool reserves, venue depth, participation rate, token decimals, actual quote size, or latency. A raw net-share square root cannot be imported into Solana AMM or Alpaca assumptions. For unrestricted q, neither stated percentage-impact rule guarantees a positive price; whether the implementation clamps or otherwise prevents invalid prices is not documented.

The noise description on p.26 states a uniform distribution from `noise_level` to `2 * noise_level`, then describes approximately +/-1-2% variation and about 68% of changes in that range. It does not specify the sign-generating process, and a uniform interval alone does not supply a Gaussian 68% interpretation. It also says agents do not currently receive a base salary, while pp.22-23 describe an initial salary and dynamic subsequent salary. These ambiguities need code/configuration and cash-flow evidence; they should not be silently repaired by guessing.

### Regression 1: next price level

The displayed specification on p.37 is:

`P_(i,t+1) = alpha + b1*V_it + b2*R_i + b3*(V_it*R_i) + error_it`.

Table 1 (p.40) additionally contains a lagged price term that is absent from that displayed equation. The table values are:

| Term | Coefficient | Reported standard error |
|---|---:|---:|
| price_lag | 1.009 | 0.017 |
| volume | -0.212 | 0.078 |
| rationalist share | 4.945 | 8.952 |
| volume * rationalist share | 0.644 | 0.172 |
| constant | -18.815 | 14.731 |

N = 560. The prose says pooled OLS, standard errors clustered by simulation x stock, no fixed effects (p.39). The reported conditional volume slope is `-0.212 + 0.644*R`, crossing zero near R = 0.329. That is a property of this estimated synthetic model, not a threshold for the percentage of real intelligent buyers. The outcome is price level conditional on a lag, not net executable investment return.

### Regression 2: next absolute price change

The text explains construction of within-stock/simulation lag and lead variables and calls price changes a proxy for returns (p.42). Table 2 (p.43), unlike the abbreviated equation on p.37, contains all lower-order interactions:

`deltaP_(t+1) = a + bD*deltaP_t + bV*V_t + bR*R + bDV*deltaP_t*V_t + bDR*deltaP_t*R + bVR*V_t*R + bDVR*deltaP_t*V_t*R + error`.

| Term | Coefficient | Reported standard error |
|---|---:|---:|
| delta price | 0.711 | 0.122 |
| volume | -0.157 | 0.070 |
| delta price * volume | -0.001 | 0.001 |
| rationalist share | 12.458 | 6.654 |
| delta price * rationalist share | -1.681 | 0.150 |
| volume * rationalist share | 0.459 | 0.148 |
| three-way interaction | -0.002 | 0.001 |
| constant | 0.033 | 3.011 |

N = 520; clustering again simulation x stock. The triple interaction is marked only at the 10% significance level; rounded coefficients/SEs are not enough to reproduce exact p-values. No held-out forecasting results, multiplicity correction, or trading-cost-adjusted strategy test is supplied.

Using the table's rounded estimates, the conditional volume slope is:

`d E[deltaP_next] / d V = -0.157 - 0.001*deltaP + 0.459*R - 0.002*deltaP*R`.

The momentum slope is a different derivative:

`d E[deltaP_next] / d deltaP = 0.711 - 0.001*V - 1.681*R - 0.002*V*R`.

Thus a positive conditional volume slope does **not** establish positive momentum. For example, at R = 1 and V = 200, the second derivative is -1.570, a reversion association. The thesis itself gives that example on p.47. The broad wording about rationalist high-volume conviction supporting trend continuation (pp.48,62) should not be substituted for the actual conditional model. Its p.47 examples discuss +/-100% price changes while the model is described in price-change space; an executable definition and unit declaration are needed before interpreting these numerical examples.

### Regression 3: volume versus rationalist share

The reported linear correlation is 0.0071 (p.48). Table 3 (p.49) gives volume on rationalist share: slope 2.049, SE 11.824; intercept 71.586, SE 6.218; N = 600.

The permitted conclusion is that this sample finds little linear association at the reported precision. Near-zero correlation and an insignificant linear slope do **not** establish independence, no confounding, genuine causality of interactions, or no nonlinear association. Those stronger claims are made in pp.48-49 and p.62 but are not demonstrated by the calculations.

### Sample dependence and model-selection caveats

The reported sample sizes are consistent with 8 simulations * 5 stocks * 15 rounds = 600 rows; one lost lead per panel gives 560, two differences/leads give 520. This arithmetic is a consistency check, not an audit of inaccessible regression rows. There are 40 stock/simulation panels, but stocks within a simulation share the same agents, budgets, news/forum environment, and cross-asset allocation. Clustering only by simulation x stock does not address arbitrary dependence across those five panels inside a simulation. With only eight independently realized market runs, treating the effective experimental information as 600 independent trials would be materially wrong.

There is no documented set of repeated independent seeds for each composition. Market composition may have been configured by the researcher, but volume is endogenous to the same mechanism that creates prices, and a treatment bundles multiple persona changes. Neither the regression nor held-constant configuration prose identifies a causal effect in real markets. The claim on p.39 that fixed effects are unnecessary because there is no unobserved run-specific heterogeneity is too strong: stochastic realized paths, agent responses, and failure/recovery history can differ even with identical configured parameters. Replication, run-level uncertainty and specified counterfactuals are needed.

Several models, interactions, scenarios and narrative examples are inspected. There is no prospective primary endpoint, complete attempted-run ledger, correction for the search family, or untouched external market cohort. This is exploratory evidence; its significant stars do not validate an investable hypothesis.

## 4. What the figures and appendix establish, and what they do not

Figure 2 (p.34) shows smaller market/fundamental error in the more rationalist-labeled runs; lower rationalist shares produce much larger errors by round 15. Approximate end-of-run values read from the plot are roughly 8-12% for 60-100%, around 16-18% for 20-40%, about 23% for 10%, about 55% for 5%, and about 72% for 0%. These are visual approximations of eight individual trajectories, not cross-run confidence intervals or a calibrated law. The relation is not perfectly monotone (20% and 40% cross), and the graph does not identify a market-wide trading return.

The capital-density figures (pp.35-37 and each odd appendix page) show marked-to-market **net worth** at round 15. This cannot be called realized trading profit: it combines initial holdings, changing marks, remaining inventory and a P&L-linked salary mechanism. The plotted curves are normalized density estimates by archetype, with unequal and sometimes tiny archetype populations; a narrow density peak is not itself a measurement of aggregate ownership concentration. At 5% rationalists, there are only two rationalist agents in a 40-agent run. No bootstrap/replication uncertainty or terminal liquidation-cost adjustment is provided.

The forum examples (pp.54-55, Figures 7-8) show similar language and influence-compatible behavior, but not a measured causal effect of social exposure. Section 5.1 explicitly says natural-language data were not systematically quantified/analyzed (pp.58-59). Same-base-model style, repeated shared context, prompts, and technical random-upvote fallbacks are competing explanations. Semantic similarity alone is not evidence of coordination, wallet identity, or intelligence.

The eight appendix sections have six plots each: capital distribution, fundamental prices, price divergence, mean percent error (MPE), market prices, and cumulative upvotes. Exact page coverage:

| Appendix run | PDF pages | Figures | Main visual observations |
|---|---|---|---|
| 1 | 67-68 | 11-16 | Only fundamentalist/contrarian wealth groups shown; market/fundamental differences mostly modest, end MPE about 8%; wealth still far above starting $105k, illustrating why transfer adjustment is necessary. |
| 2 | 69-70 | 17-22 | Four wealth groups shown; mostly moderate divergence, end MPE about 9%; fundamentalists/contrarians dominate raw upvote totals. |
| 3 | 71-72 | 23-28 | Four wealth groups shown; oscillating rather than persistently directional paths, end MPE about 12%. The main-text Sim-3 forum examples include social agents although this run's appendix wealth legend omits a social curve; naming/population alignment needs underlying metadata. |
| 4 | 73-74 | 29-34 | Five wealth groups; several positive price divergences, end MPE about 18%; raw contrarian upvotes highest. |
| 5 | 75-76 | 35-40 | Five wealth groups; FNCE declines while CSMR rises, MPE peaks near 23% then falls to about 16%; noise group raw upvotes highest. |
| 6 | 77-78 | 41-46 | Several declining stocks with partial recovery; MPE peaks near 30% then ends near 23%. The fundamental-price paths differ visibly from most other appendix runs, consistent with some changed or newly realized exogenous path, not enough metadata to decide which. |
| 7 | 79-80 | 47-52 | No fundamentalist wealth curve shown; only two contrarians if the 5% description applies. Three severe price declines while FNCE and CSMR are relatively supported; MPE rises to about 55%. |
| 8 | 81-82 | 53-58 | Momentum/noise/social wealth groups; three stocks fall severely while CSMR roughly doubles and FNCE stays elevated; MPE rises to about 72%. The result is both bubbles and crashes, not uniform upward price inflation. |

The displayed upvotes are cumulative raw totals by type, without a population/post/exposure-normalized denominator. Varying the count of agents of a type changes its opportunity to receive upvotes. These are not controlled measures of individual credibility. The label MPE lacks an explicit formula; its nonnegative behavior alongside both upward and downward divergence requires a clear signed-versus-absolute error definition before quantitative reuse.

Section 3.5 says calibration details are in the appendix (p.27), but the appendix is predominantly these plots, not a source/configuration table or machine-readable results. Specific unreproduced items include full persona and system prompts, exact model versions/sampling settings, random seeds and news schedules, all five archetype counts per run, supply/market-maker accounting, trade clearing equations, exact impact/noise functions, cash-flow/salary formula, failed-action frequency and replacement policy, raw order/fill records, exact regression formulas/dtypes/units and code, data-selection/attempt ledger, and terminal inventory liquidation.

The thesis's cited Frazzini and Pedersen (2014) reference is *Betting Against Beta* (p.64), yet the prose attributes a volume-conditioned momentum-versus-reversion result to it (pp.14,38-39). The authors' [primary publication summary](https://www.aqr.com/insights/research/journal-article/betting-against-beta) describes leverage constraints and low/high-beta returns. Treat the thesis's volume attribution as needing a source-passage check, not an independently verified result. This review did not fetch or audit every referenced primary paper. The literature review itself makes clear that volume/turnover, disagreement, momentum and reversal were studied long before this thesis (pp.12-15); do not claim those hypotheses are newly invented here or by us.

## 5. Practical implications for CoinHunt and our US-only money objective

The following map uses the project constraints and historical concentration example supplied in the parent chat, not a new audit of production wallets, accounts or frozen studies. Existing engineering work may already implement parts of these controls; integration should verify coverage and add only missing pieces.

### Highest priority: preserve the difference between evidence and interpretation

1. **Keep an explicit claim type and evidence level.** A mechanism simulation can motivate a question. A historical association, costed backtest, paper fill, full-account net return and replicated live result are different claims. Every result should name its market, independent event count, observation/decision/execution times, quote basis, costs, unresolved sources, account boundary, selection history and replication status. Source authenticity does not raise the empirical level of its claims.
2. **Do not label wallets rational, smart, informed or successful from balances, repeated participation, or a few swaps.** The thesis assigns personas ex ante and knows who its synthetic agents are. We observe addresses and incomplete activity. A returning buyer is not necessarily an independent person, profitable trader, early informed buyer, or supporter who will keep buying. Pools, routers, exchange wallets, funding links and self-transfers need separately evidenced classification; uncertain linkage needs uncertainty bounds, not confident identities.
3. **Treat source/acquisition failures as missing evidence.** The thesis's default trades and random upvotes preserve simulator uptime by altering behavior. Our collectors, scorers and readiness gates should preserve FAILED/INCOMPLETE and original gaps, with receipts and bounded retry; they must not fabricate a no-signal, zero volume, no social activity, or a complete trade because a request failed. A model can abstain; technical fallback is not market evidence.
4. **Maintain full cash-flow and inventory accounting.** For a declared account boundary, dollar trading P&L starts from `ending marked/liquidated wealth - starting wealth - net external contributions`, with every fee/cost accounted for once. Marked wealth is not realized profit and unresolved inventory blocks a complete realized-P&L claim. Paper/proxy commission remains labeled. The already reported correction that buyback fees subdivide protocol fees must remain respected; this thesis does not justify re-adding embedded costs.

### High priority: observable participant composition before each decision

Our previously reported corrected example has 8 unique decoded events (5 buys, 3 sells), gross buy volume 10.255334171 SOL, returning buyers contributing 97.2220091588% and the largest buyer 87.3543408106%. These historical chat figures are not independently reverified in this review. They illustrate the question: does a high-volume signal reflect broad new demand or a very small returning participant set? Five buy events from one mint are descriptive evidence, not a training set that can validate this hypothesis or identify an optimal threshold.

Add or verify a point-in-time feature schema, all keyed by exact mint, pool/venue, transaction/instruction identity and decision cutoff:

- **Known returning-buyer share:** gross buy debit attributable to wallets with a documented earlier exact-mint buy / all observed gross buy debit in the window. State the lookback start and left-censoring; unknown history is not proof of newness.
- **Observed newcomer breadth:** count of distinct wallets first observed buying in the bounded available history, plus its coverage qualifier. This is not a count of new people. Separately report known wallets and unknown classifications.
- **Concentration:** top-one/top-five buy-volume shares, `HHI = sum(s_w^2)`, and effective buyer count `1/HHI` where the denominator is valid. Report both wallet-count and cash-weighted summaries; label gross demand versus net same-window inventory flow. Do not combine buy and sell notional as if it were independent external demand.
- **Chronology:** lag from each wallet's first known exact-mint activity to the signal; earlier accumulation versus same-window round trips; confirmed buy/sell sequences; no use of transactions observed only after the decision. Capture event time, first observation time, finality/confirmation, parser version and completeness.
- **Dependence sensitivity:** leave out the largest buyer, collapse only evidenced related-wallet groups, and bound results under unknown linkage. Store these as prespecified diagnostics rather than optimize until a backtest looks good. A withdrawal of one concentrated buyer is a liquidity/exposure scenario, not proof of coordinated manipulation.
- **Liquidity and capacity:** executable entry and exit quotes at the intended size and time, quote age, pool depth/reserves and route, failed quotes, and estimated impact under adverse concentration scenarios. A token's high turnover does not imply capacity to exit our own position.

### High priority: measure social propagation without inventing causality

For already-authorized exact-mint social coverage, preserve first-observed timestamps, original authors/posts, quotes/reposts, parent links, and content fingerprints. Distinguish unique originating claims from copied messages, raw count from author diversity, and exposure denominators from engagement totals. A ticker-only mention should not silently join an exact mint. If a post was observed only after a buy, it cannot be used as a predictor of that buy even if its displayed creation time is earlier.

Test low-cost deterministic duplication/temporal measures before paying for LLM sentiment or simulations. Shared boilerplate, a common news release or a common language model can create similar text without coordination. Missing social coverage is unknown, not negative sentiment or no promotion. Use lagged associations and explicit controls; causal influence needs stronger identification than co-occurrence. Full continuous exact-mint coverage remains a prerequisite for the untouched-cohort question already identified by the project.

### Preserve venue, money and experiment constraints

A synthetic long-only equity market is not proof that a Solana memecoin strategy is US-usable or fundable at our stake. Keep venue eligibility, executable route, rounding, available capacity, account control, dollar loss limits and user live authorization as independent gates. Memecoin buyer composition can remain research when those prerequisites fail. No suggested interaction or simulation overrides the adopted US rule or promotes SLR-0.2 into a validated strategy.

Rank ideas by the cost and time required to reach a credible **net, US-expressible** decision at the user's attainable stake. A paid multi-hour LLM sandbox that produces another interesting chart is lower priority than resolving an existing missing quote, incomplete buyer chronology, cost ambiguity or account-control gap. Preserve current frozen registrations, algorithms, thresholds, windows, source identities and main-review authority. New hypotheses require separate prospective records; no retroactive tuning of a registered cohort.

## 6. Falsifiable proposals, not strategy changes or performance claims

### Proposal A: does composition explain anything beyond volume, price and liquidity?

**Hypothesis:** conditional on predecision price action, total volume, token age, market conditions and executable liquidity, concentrated returning-buyer demand has a different association with later net executable outcomes from broad observed-newcomer demand. A possible directional hypothesis is less continuation / more downside for high concentration, but the paper does not establish that direction in crypto. Choose and record the direction before the untouched evaluation; do not choose it after inspecting outcomes.

**Inputs:** a genuinely untouched exact-mint cohort with continuous social coverage; chronological buys/sells and history-coverage qualifiers; predecision quotes and full route costs; the existing matched full-account controls. No historical wallet outcome or social post that was unavailable at the decision can enter a feature. Avoid selecting only tokens or wallets with surviving data or profitable later outcomes.

**Design:** compare a fixed volume/price/liquidity baseline against one preregistered added composition interaction. Pick one primary executable-horizon outcome and one prospectively justified specification; track every alternative tried. Do not import the thesis's 33% rationalist threshold or regression coefficients. Define missing-input failure disposition, sample-size/power requirements, quote staleness rules, costs, hold/exit handling, matching variables and success/stop criteria before acquiring the holdout.

**Independent unit and uncertainty:** token/event/launch-day clusters, with explicit handling of common market shocks and repeated wallets across events; do not count multiple swaps, mentions or wallets within one event as independent trades. Use chronological training/validation and untouched evaluation. Bootstrap/block or other dependence-aware inference must match the unit; account for the total model-search family. Estimate uncertainty in incremental net performance and downside/capacity, not just in a synthetic price slope.

**Falsification:** no meaningful incremental out-of-sample value at executable costs; the sign reverses across fresh cohorts; the effect disappears when the largest buyer is removed; gains are explained by cheaper/better liquidity, later information or one event; missingness dominates; or performance cannot be distinguished from matched controls at the declared precision. Any of these defeats promotion. Insufficient observations remain INCOMPLETE/inconclusive, not evidence of absence or positive edge.

### Proposal B: does original social breadth add information beyond repetition?

**Hypothesis:** unique, independently originated exact-mint mentions observed before the decision have different predictive value from a burst dominated by repeated content or a few authors, conditional on market volume, participant concentration and liquidity.

**Design:** use only already-authorized covered data; deterministic fingerprints and a fixed near-duplicate rule; preserve original/repost lineage, clocks and denominator. Compare a simple count baseline with one prespecified novelty/diversity measure. Include common-news and author/template controls. Analyze lag and missingness explicitly. No social relationship is inferred from wallets without independently evidenced mapping.

**Falsification:** apparent benefit disappears with original-author normalization, synchronized-news controls, strict first-observed clocks, a fresh chronological cohort, or a concentration/liquidity baseline. A causal claim is rejected unless a defensible identification design exists. This could improve evidence triage even if it produces no tradeable edge.

### Proposal C: concentration-aware execution stress, before another signal search

**Question:** if the largest observed buyer stops or sells, can the intended stake still be unwound under an observed or conservatively stressed quote curve? Separate plausible risk scenarios from claims about that wallet's intentions.

**Design:** offline sensitivity on already saved public-safe route/quote evidence, no orders. Use actual AMM or venue economics, fee-family semantics and size/latency; do not use the thesis's uncalibrated lambda. Clearly label extrapolations, absent depth and incomplete holdings. Unknown executable coverage prevents a capacity claim.

**Falsification:** the strategy's supposed improvement vanishes at feasible stake, a single-wallet scenario makes expected net value negative or exceeds the approved loss budget, or no defensible quote evidence exists. This can disqualify a candidate; it does not prove the remaining candidates profitable.

### Proposal D: simulator as a later engineering test fixture only

If a concrete unresolved mechanism eventually warrants simulation, start with a cheap deterministic sandbox whose cash, inventory, external funding, fees, counterparty and observations are explicit. Compare zero-salary/fixed-inflow/performance-linked-inflow ablations; forum-on/off; fixed versus varied personas; and alternative execution mechanisms using declared independent seeds. Record all attempted scenarios, model/configuration hashes, checkpoints and failures. Keep the same realized exogenous inputs across intended treatment comparisons where appropriate, and retain independent replications.

A future LLM variant may test narrative sensitivity, but only after a bounded cost justification and with schema-validated outputs, hard risk constraints, no trading permissions, and failure/abstention receipts. No default trade or random social action can be passed off as a fresh decision. Simulator patterns test assumptions and engineering resilience; real-market holdout evidence is still required for edge claims. No such simulator is requested or run in this review.

## 7. Candidate principles to retain for future work

1. State what the observation can measure before naming a market mechanism; addresses and simulations do not reveal human intelligence.
2. Condition volume research on observable breadth, concentration, history quality and execution capacity; do not equate activity with independent demand.
3. Every feature belongs to the information set actually available at the decision, with event and first-observed clocks retained separately.
4. A credible interaction requires a declared economic story and fresh falsification, not an attractive sign or significance star.
5. Count independent events and experimental replications, not rows, agents, swaps, or posts.
6. Near-zero correlation and insignificant coefficients do not prove independence, causality or equality.
7. Report wealth net of external cash flows and all costs; retained positions and proxy commission are labeled, never converted into realized profit.
8. Technical failure is evidence about coverage and process, never permission to fabricate a market observation or action.
9. Reproducibility includes exact formulas/units, configurations, source identities, attempted-run selection, runtime/model versions and failure handling.
10. Protect frozen claims while creating separate prospective hypotheses; do not reset the sample or extend a horizon because a promising result needs more time.
11. Spend the next research dollar on the smallest evidence gap that can change a US-usable net-money decision; novelty and architectural complexity are not progress measures.
12. User permission to retain useful principles is not authority for this reviewer to rewrite frozen studies, main, accounts or other agents' policies. Integration must mark adopted principles versus suggested work explicitly.

## 8. Claims explicitly rejected and unverified scope

Reject: this thesis proves high volume is bullish or bearish in crypto; a 33% smart-wallet threshold works; returning buyers are rationalists; a large balance or repeated swaps proves wallet profit; more capable LLMs make money; coherent agent explanations validate their economic optimality; simulated bubble/crash resemblance validates real-market causality; salary-augmented end wealth is alpha; significant pooled regressions are a costed strategy; near-zero correlation removes confounding; raw upvotes identify credibility; or this is novel prior art-free alpha.

Not checked or available: executable thesis code, exact per-run datasets/configuration, a replication of the regressions, all primary references, the simulator's counterparty solvency and settlement, actual wallet/account profit, current source/coverage state, venue availability or regulatory eligibility, live broker behavior, holdout profitability, or production deployment. No market scan, scoring, trade, order, account access, GitHub source acquisition, CTS access, frozen-file edit, main change or policy adoption was performed.
