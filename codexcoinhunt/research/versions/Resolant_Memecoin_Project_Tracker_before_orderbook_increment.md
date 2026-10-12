# Resolant Labs — Memecoin strategy project tracker

Updated October 11, 2026, America/Chicago. Active specification: **Second-Look Relay, SLR-0.2**.

## Goal and current result

Develop a new composite behavioral strategy compatible with US spot trading through PumpPortal or a supported Alpaca account. Start each research campaign at $50 and measure more than $100 realized, recoverable USD-equivalent after all execution/data costs, before personal taxes. Prioritize profitable account growth rather than a visually impressive token chart.

**Design and research tooling completed. Consistent >2× account performance is not established. Verified strategy positions: 0. Verified doubling campaigns: 0. No real orders placed or funded data stream used.**

The current tools support paper research and retrospective stress tests. Research development is authorized to continue. The tools do not autonomously trade or provide continuous tick-level market monitoring. The record retains hypotheses, failed tests and evidence gaps for subsequent updates.

## Completed work

| Task | Status | Evidence or result |
| --- | --- | --- |
| Define the target as account doubling | Complete | All costs and all starting capital included; open tokens do not satisfy the target. |
| Interpret “expressible in the US” | Complete, interpretation | Treat as executable from the US, with venue/token/account eligibility gates. |
| Research behavioral attention and prior art | Complete | Research papers and original attention-detector documentation recorded in source ledger. |
| Check novelty claim | Complete, limited | Attention and second-wave components already exist. The exact composite is a new research proposal; universal untried status is unverified. |
| Verify PumpPortal fees | Complete | Local 0.5%; Lightning 1%; pool/network costs additional. |
| Verify Alpaca fees and universe | Complete | First-tier maker 0.15%, taker 0.25%; listed assets only. |
| Check public US access conditions | Complete, limited | Provider terms reviewed; no blanket legal clearance inferred. |
| Define measurable mechanism | Complete | New audience + exact mint agreement + unrelated buyer conversion + fading selling. |
| Specify position/exit/campaign rules | Complete | $7 initial paper position, one position, capital recovery/runner exits, explicit stop/timeout rules. |
| Freeze versioned configuration | Complete | Current SHA-256 and timestamp in `preregistration.json`; original 0.1 retained in `versions/`. |
| Implement a market recorder | Complete | Fixed discovery universe followed prospectively, unsuccessful requests retained. |
| Collect first market sample | Complete | 66 tokens, 24 cycles, 72 snapshot requests; sample used for development only. |
| Implement optional PumpPortal recorder | Complete, unconnected | Raw events only; costs documented; metered subscriptions not invoked. |
| Implement conservative rule gate | Complete | Missing/future/stale inputs rejected; 66 initial records fail completeness. |
| Implement cost and sensitivity engine | Complete | Reproducible fee estimates; hypothetical outcomes explicitly separated from evidence. |
| Implement fill-accounting auditor | Complete | Partial exits, extra costs, unsellable remainders and position limits reconciled. |
| Prepare social, wallet, candidate and fill journals | Complete | Empty fill/social/wallet templates plus real liquidity-only candidate records. |
| Check engineering correctness | Complete | Final test result retained in kit; accounting/data-leakage checks are not strategy validation. |

## Decisions and their reasons

| ID | Decision | Reason |
| --- | --- | --- |
| D01 | Primary route: PumpPortal Local | Full new-token route coverage with lower service fee than Lightning. Speed/failure tradeoff still needs measurement. |
| D02 | Alpaca is a separate adaptation | Its supported listed assets cannot substitute for arbitrary Solana mint execution. |
| D03 | Focus on second-look conversion | Human recognition and action delays provide a plausible mechanism outside raw candle arithmetic. |
| D04 | Require audience change and exact mint consensus | Repeated promotion and copycat ambiguity can make attention look more useful than it is. |
| D05 | Require actual buyer conversion | Public post counts are not purchases or identifiable latent dollar demand. |
| D06 | Use apparently unrelated, seasoned buyer clusters | Reduce repeated/bundled activity and immediate funding-factory effects without claiming to identify people. |
| D07 | Target larger moves with few transactions | Percentage fees and fixed costs consume small scalps on $7 positions. |
| D08 | Preserve a runner after capital recovery | Retain exposure to rare large outcomes; compare against simpler liquidation before claiming it improves profits. |
| D09 | Keep every rejected/censored candidate | Avoid survivorship, selection and hindsight bias. |
| D10 | Paid social/data spending remains outside the initial run | Research costs could consume a material share of the $50 account. |
| D11 | Remain paper-only | Current research has no completed independently evidenced entries or positive forward expectancy. |
| D12 | Version 0.2 makes conventions explicit | Graduation, wallet maturity and zero-baseline definitions are now in configuration; initial sample remains excluded from proof. |

## Open hypotheses

| ID | Hypothesis | Current evidence | Next falsification |
| --- | --- | --- | --- |
| H01 | A new audience creates a measurable attention-to-buying lag before price escapes. | Plausible inference; no SLR forward test. | Compare price/flow response after new versus repeated audience events. |
| H02 | Exact-mint consensus reduces unsuccessful entries caused by copycats. | Manipulation/copycat research supports investigating it. | Compare full strategy with the consensus veto removed. |
| H03 | Declining earlier selling improves the payoff of a renewed demand wave. | Mechanism specified; not measured. | Same event with/without seller-exhaustion gate. |
| H04 | Buyer-cluster filtering separates independent demand from manufactured activity. | Literature documents the confounder. | Audit cluster errors and compare forward results at equal coverage. |
| H05 | Capital recovery plus a runner increases net logarithmic growth. | Arithmetic can support large outcomes; realized distribution unknown. | Matched, costed replay of full exit paths. |
| H06 | The joint trigger improves campaign doubling over simpler approaches. | Unconfirmed. | Untouched forward campaigns with matched random/attention/momentum controls. |

## Remaining work, in dependency order

1. **Social evidence adapter:** collect authorized, timestamped exact-mint and meme-family observations, classify author/community clusters and paid status, and retain original evidence references. Establish usable history before treating missing windows as quiet periods.
2. **Chain enrichment:** validate PumpPortal payloads, transaction signatures, finality and token decimals; obtain historical wallet/creator/pool evidence; exclude known service funding roots; quantify uncertain coverage and clustering errors.
3. **Executable quote adapter:** the read-only PumpSwap current-state adapter is implemented for canonical SOL-paired pools. Extend it to partial exits, Raydium/other supported routes, transaction simulation failures, rent/priority fees and decision-time collection. Public DEX marks alone remain insufficient.
4. **Campaign controller:** implement the specified daily/rolling-entry limits, complete 60-second confirmation, exit scheduler, rent/refund accounting, retries, campaign floor and 30-day/30-trade deadlines. Current scripts audit inputs and do not enforce that full lifecycle.
5. **Independent forward pilot:** log every opportunity, rejected candidate, control selection and no-trade day. Do not use the included initial market sample as evidence of a fitted edge.
6. **Payoff and cost study:** measure return tails, failure/unsellability frequency, manual latency, data cost and the Local/Lightning tradeoff. Optimize only on development data.
7. **Untouched evaluation:** at least 150 forward closed positions in three regimes and at least 30 non-overlapping complete campaigns; count timeouts, standdowns and missing exits. The campaign requirement may take more positions and time.
8. **Performance promotion:** require positive net expectancy confidence bounds, better performance than matched controls, at least 80% doubling campaigns and a 95% Wilson lower bound above 70%. These thresholds are evaluation criteria, not a promise of future results.

## Cost and evidence checkpoints

- Under conservative Local assumptions, a $7 position needs a 2.117× gross price multiple to return 2× net proceeds. A single gross-3× winner increases the whole $50 account only to roughly $62.85.
- The kit's sample had one token with an observed chart doubling. Its identity was not a validated SLR selection, and no captured trade return is booked.
- Reported initial pool liquidity and pool age leave only six coarse prefilter candidates, but mint age, social history, wallet independence, custody and executable quotes remain missing.
- The included campaign sensitivity table uses invented IID outcome probabilities. Its favorable rows are not a strategy win rate or forecast.
- Paid trade events cost 0.01 SOL per 10,000; broad social reads are material at the published X rate. Count those costs even on rejected candidates and quiet days.
- A filled 20% position stop would lose about $1.40 on a $7 allocation. An unsellable position can lose all $7, and the planned campaign floor can be overrun by a gap.

## How to update this record

Retain this tracker identity and append dated findings, decisions and completion evidence. Update the strategy report only when the specification or evidence changes. Archive the prior configuration/hash before every rule revision. Never overwrite raw observations, insert future evidence into a past decision, reset campaigns only after good events, or relabel engineering tests as investment validation.

An evidence-complete candidate is not automatically a live-trading authorization. This research remains separate from any existing Resolant/Northstar forecasting control or challenger until explicitly integrated.


## Research extension — October 11, 2026

**Leading design:** SLR-0.2 remains a hypothesis. **Challenger:** REV-0.1 is not promoted because the frozen rule set generated zero opportunities in either historical partition. No validated SLR/REV fills or account-doubling campaigns exist.

| Completed increment | Evidence |
| --- | --- |
| Read the current saved report, tracker and kit | Stored kit matched all 32 original manifest entries. |
| Retrieve corrected public rejection corpus | Archive checksum verified; 716,762 rows, 18,237 events, 4,635 mints. |
| Preserve a compact reproducible input | All source rows retained; 14 used fields, checksum, UTC source provenance, attribution and licence saved. |
| Freeze REV-0.1 before processing outcomes | Config/hash and retrospective date partitions retained. |
| Test revival and ordinary momentum | Zero revival signals; costed momentum paths fail to establish positive expectancy in the selected frame. |
| Build contemporaneous matched random controls | Future records and eventual returns do not determine eligibility; unmatched and incomplete comparisons retained. |
| Inspect the rule funnel on development data only | 161 rebound/decline observations before the liquidity-growth gate; zero pass the additional 20% growth gate. |
| Audit a published 190-trade benchmark | +117.73% is summed trade percentages; hypothetical 14% allocation yields $53.34 from $50 before further costs. |
| Check cheaper historical source access | Public Alpaca bar data retrieved without account keys for four listed meme coins. |
| Extend replay/anti-leakage checks | 31 checks pass, including next-observation entry, cost recheck, censored exits, stop gaps and future-control exclusion. |

**D13:** Do not use summed trade percentages as proof of account doubling. The external benchmark contains overlapping positions and lacks the complete account/fee ledger our target needs.

**D14:** Do not promote REV-0.1. Its additional liquidity-refill condition has no observed opportunities under the frozen rules. Keep this failed hypothesis instead of quietly loosening it on the inspected holdout.

**D15:** Treat liquidity capacity and price-driven liquidity changes separately. Price and total USD liquidity can reflect the same AMM mechanics. The next capacity overlay must use actual pool reserves/size-specific quotes and preserve the original buyer/attention thesis.

**D16:** Ordinary rebound/momentum in this observed rejection frame does not provide the desired edge. On the June 24–July 16 holdout, 588 usable modeled paths average −13.00%; missing entry marks, failed cost checks and censored exits are retained separately. Among 191 fully observed matched pairs, momentum and random controls both average roughly −12.3%; the descriptive interval for their difference spans zero. These are approximate mark-path results, not executable trades or a market-wide estimate.

**Highest-value next work:** enrich public buyer funding clusters, add the social evidence adapter and define a new untouched forward period. Extend the quote adapter to Raydium and capture a fresh quote at every paper decision. The newly accessible historical corpus is a development resource and cannot replace social/wallet proof or a funded account ledger. A full single-position campaign controller and safety-qualified account replay remain incomplete.

**No user decision is required for further read-only research.** Live orders, funded data access and private keys remain outside this experiment.

## Quote-capacity increment — October 11, 2026

The highest-priority execution gap is now partially resolved for canonical SOL-paired PumpSwap pools. A pinned read-only adapter around the official PumpSwap SDK retrieves pool, fee, mint and vault state, incorporates virtual quote reserves and unswept protocol/creator fee buckets, verifies the exact program owner/base mint/canonical derivation, and records every RPC request/response with UTC times. It cannot construct, sign, simulate or send a transaction.

Five PumpSwap pools from the frozen initial pool-age/liquidity prefilter were checked at 2026-10-12 01:31:47 UTC. The current processed-state bundle was assembled in 326 ms and its exact-pair USD reference was 3,334 ms old. All five passed the 6% same-state capacity ceiling with estimated all-in recoverable value of **$6.6065–$6.7111 from a $7 budget** (4.13%–5.62% loss). Route-only immediate roundtrip retention was 97.556%–99.097%. The one Raydium pool in that six-token shortlist remains untested by this adapter.

Three preceding attempts remain explicit rejects: their state windows were 3,057 ms, 3,125 ms and 2,970 ms. A read-only warm-up call before starting the quote-state clock eliminated connection setup from the measurement; it did not cache or omit the pool/config/vault reads. The passing result uses processed state for currency and retains confirmation/finality as a separate paper-fill requirement.

**D17:** Use the official fee-aware state quote rather than a total-liquidity proxy for PumpSwap capacity. Reported liquidity is useful for screening, but it cannot substitute for virtual reserves, fee buckets, fee tiers, exact mint/owner checks and quote freshness.

**D18:** A capacity pass is only a veto result. These five observations occurred roughly 55 minutes after initial discovery and have no complete SLR social, buyer, safety or entry-time evidence. They are not trades, return observations or support for account doubling.

**D19:** Warm the public RPC connection before starting the quote clock and retain failed stale attempts. If the subsequent state assembly exceeds two seconds, reject the candidate; do not redefine freshness around only the final response.
