# Resolant Labs — Memecoin strategy project tracker

Updated October 12, 2026 UTC / America/Chicago. Active specification: **Second-Look Relay, SLR-0.2**.

## Goal and current result

Develop a new composite behavioral strategy compatible with US spot trading through PumpPortal or a supported Alpaca account. Start each research campaign at $50 and measure more than $100 realized, recoverable USD-equivalent after all execution, data, funding and conversion costs, before personal taxes. Prioritize profitable account growth rather than a visually impressive token chart.

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
| Implement offline campaign controller | Complete core, adapters unconnected | Actual confirmation timing, entry limits, USD cost reserves, rent locks/refunds, exit requests, retries and calendar limits checked on supplied receipts. No continuous execution coverage. |
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
2. **Chain enrichment:** finalized PumpSwap log/CPI swap-event probes, exact event-account reconciliation and bounded prior-signature enrichment are implemented, including v1 reads and cross-representation deduplication. Extend verified prior trades in other mints, initial funding roots, service/creator links, complete participation history, mint safety and cluster error measurement. A distinct event wallet is not an independently verified buyer cluster.
3. **Executable quote adapter:** the read-only PumpSwap current-state adapter is implemented for canonical SOL-paired pools. Extend it to partial exits, Raydium/other supported routes, transaction simulation failures, rent/priority fees and decision-time collection. Public DEX marks alone remain insufficient.
4. **Campaign integration:** offline core now checks daily/rolling limits, timed confirmation, exit requests, USD-basis rent/cost accounting, retries, floor and local 30-day/30-trade limits. Connect independently evidenced fills, credited-token fee liabilities, live SOL/rent FX, partial-sale minimum quantities, actual funding/conversion and a reliable event source/clock. Supplied flags are not independently authenticated; absent receipts do not become timely exits.
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

## Buyer and order-book increment — October 11, 2026

**New challenger:** OB-0.1, frozen before a bounded prospective development capture, combines persistent nearby bid support, sampled order-flow imbalance and completed buy-side trades. It is not promoted; no qualifying signal appeared in the 12-minute window. SLR-0.2 and its hash remain unchanged. Full details, exact identities, code, raw evidence and rejected inputs are in `Orderbook_and_Buyer_Research.md` inside the kit.

| Completed test | Result |
| --- | --- |
| Public Alpaca `us` books and signed-trade access | Verified without account credentials; four listed USD pairs. |
| Bounded prospective collection | 2026-10-12 01:41:20–01:53:10 UTC receipts; 72 polls, 144 HTTP requests, zero HTTP errors. |
| Preserve repeated observations | 288 pair snapshots contain only 111 distinct source updates; they are not independent trials. |
| Apply frozen source-age gate | 38 snapshots pass two seconds; 250 fail. Old event time can mean unchanged book, not a proven feed fault. |
| Challenge all-level book imbalance | BONK's median all-level bid share 7.68%, versus 49.64% nearby; PEPE 2.35%, versus 50.04%. Remote asks distort the total. |
| Model $7 spread/depth and credited-asset fees | Median immediate costs: DOGE 1.32%, BONK 1.85%, WIF 1.32%, PEPE 1.47%, with separate adverse-execution assumptions. |
| Compare conditional paper account paths | Full and book-only rules have zero opportunities. Momentum has one censored modeled entry; $43 cash plus unresolved $7 allocation, with no loss/writeoff or account return asserted. Random has no primary trigger to match; social control unavailable. |
| Decode fixed PumpSwap transaction subset | Seven swap events in 12 retrieved transactions: five buys, two sells; five event users; one supplies 87.33% of observed buy notional. |
| Correct transaction-version visibility | Seven of 12 transaction bodies are v1; original errors retained and recovered with integer `maxSupportedTransactionVersion: 1`. |
| Check bounded prior wallet history | All five users have at least ten earlier successful transactions. Fourteen-day maturity, funding independence and first-time mint participation remain unknown. |
| Verify engineering invariants | 49 checks, including credited-token fees, multiple-level sweeps, insufficient depth, source-age checks, future-trade exclusion and successful exact-program events. |

**D20:** Keep venue semantics separate. PumpSwap's constant-product curve supplies size-specific depth but no resting bid/ask queue. Raydium needs pool-type-specific handling. Alpaca order books and taker trades describe that venue, not all Solana demand or identifiable buyers.

**D21:** Use nearby depth, distinct source updates and completed signed flow to test the book mechanism. All-level walls, repeated copies, or an API receipt timestamp alone do not prove new demand. Queue-aware maker outcomes require data beyond a touched price.

**D22:** Treat buyer concentration as measured only within the decoded subset. Five wallets cannot satisfy the eight apparently unrelated, seasoned, new-to-mint buyer requirement. The subset is not a complete five-minute flow; missing provenance remains unknown.

**D23:** Never silently omit new transaction formats. Current Solana v1 reads must opt in; account references and returned signatures do not establish swap activity. CPI-only events remain a parser gap.

**Next:** extend buyer funding/CPI evidence, implement a complete campaign controller, and freeze a later book-feature ablation against random, momentum and attention controls when those inputs exist. Obtain event-level book updates in an authorized runtime before studying cancellations, refill persistence or maker queues. No validated closed strategy positions or doubling campaigns have been added.

## Buyer quality and costed flow increment — October 11, 2026

Research proceeds autonomously within the continuing paper-only scope. **SLR-0.2 remains unchanged and unvalidated. FLOW-0.2 is not promoted.** Complete source evidence, version history, assumptions and results are in `Buyer_Quality_and_Flow_Research.md` inside the kit.

| Test | Result |
| --- | --- |
| Decode both event paths | All seven saved swaps appear in logs and CPI metadata; counted once. No new event was added. |
| Verify exact event accounts | Seven events reconcile to the target mint, event user and token account; a mint elsewhere in the transaction is insufficient. |
| Measure quote-notional diversity | Five buy users have HHI 0.76927 and 1.29993 equal-sized-user equivalents. This is not an independent-human count or a tuned threshold. |
| Extend wallet history | 42 fresh finalized RPC responses; two of five users establish fourteen-day prior activity. Others remain unknown within the page bound. |
| Preserve trade versus holding semantics | Other-mint balance records exist for all five, but trades in three other mints remain unverified. |
| Inspect prior transfer leads | Four incoming transfers of 1–6,238 lamports; no initial funder or independent cluster verified. Tiny payments are not treated as funding roots. |
| Freeze signed-flow challenger | FLOW-0.1 retained; FLOW-0.2 clarifies assumed publication and freshness clocks before outcome analysis. Current hash in `flow_preregistration.json`. |
| Retrieve complete historical source pages | 93 signed trades and 249,457 quote rows on October 9–10 plus bounded exit extensions; 28 complete quote pages. 6,336 cross-request overlaps retained. |
| Test money after costs | Three development quote paths all rise at midpoint but lose −1.2541%, −1.5927% and −0.6450% net; conditional $50 account ends $49.75595. |
| Keep later comparison unresolved | October 10 has one modeled $7 DOGE entry with censored exit; $43 cash plus open modeled inventory, no loss/writeoff or doubling claim. |
| Preserve unmatched controls | No eligible random/momentum peer under the frozen contemporaneous gates; no paired comparison. Social control remains unavailable. |
| Correct actual-entry accounting | A missing quote is a rejected attempt, not an actual entry quota used; earlier implementation output retained. |
| Inspect a new research dataset | MELT is a potential research lead, but its published noncommercial licence requires separate permission for commercial use. Dataset/code/predictions not adopted. |
| Verify implementation | 64 engineering checks; no test is investment evidence. |

**D24:** Prioritize economically meaningful buyer diversity over raw wallet count as an ablation hypothesis. Do not retrofit a new threshold to the five observed users or treat the 1.30 diversity diagnostic as independent people.

**D25:** Do not promote signed-buy dominance alone. These examples forecast direction correctly while costs consume the move. Two days and an unresolved later exit do not support reliable account growth, and stood-down controls cannot be compared as profitable peers.

**D26:** Avoid manufacture of buyer proof: log/CPI copies are one event; old token balances are not verified trades; zero current balance is not first-ever participation; tiny transfers and unlabelled service sources are not initial funding or independent ownership proof.

**D27:** Keep the MELT dataset out of this commercial strategy workflow under its current published licence. Continue using our own public-source evidence; no author contact or additional approval is required for that work.

**Next priority:** verified prior swap activity and meaningful funding ancestry, followed by the complete campaign controller and an untouched buyer-plus-book ablation. Keep calendar timeouts, missing exits, opportunity frequency, failed attempts and all real data/funding/conversion costs in the account objective. No validated strategy fill or doubling campaign has been added.

## Campaign-accounting increment — October 12, 2026 UTC

**Leading hypothesis unchanged:** SLR-0.2, SHA-256 `9bcd83ce0ec71cdae8c410c202bd5a75b1496679e5ddb94ccc7d300e57c3663f`. `SLR-CONTROLLER-0.1` is an offline policy/accounting implementation, not a promoted investment strategy. See `Campaign_Controller.md` in the kit for contracts, source receipt times and adapter gaps. Prior code, report/tracker and check outputs are retained.

| Increment | Tested result |
| --- | --- |
| Confirmation | Two evidence-complete, separately received observations at least 60 seconds apart; dynamic availability must advance. An operator flag or repackaged first record cannot replace the wait. |
| Campaign lifecycle | One position, 14% all-in sizing, actual gas reserve, rent lock/refund, daily losses, rolling entry limit, cooldown, partial recovery, runner, exit requests, retries and deadlines implemented on supplied events. |
| Stop/gap/failure behavior | A quote never creates a fill. Recorded recovery below a requested stop remains a larger loss; three failed exit attempts leave unresolved inventory. |
| Calendar and runtime gaps | Chicago local dates and calendar days include DST. Overdue inventory is recorded at the next actual receipt without inventing an earlier exit. |
| False-success correction | Legacy floats falsely reported >$100 for 12 of 99 synthetic exact-$100 cent-cost examples. A one-unit token residue could be falsely closed. Decimal decisions and exact-zero closing fix both. Original failing rows/output/hash and corrected results retained. |
| Known-fee accounting | Included costs, unpaid accruals and later settlement use economic identities to prevent double charging or omitted fees. Locked rent is excluded until evidenced refund. Later costs revoke provisional success. |
| Existing-evidence replay | Same 66 initial incomplete records still reject; zero new observations, fills or campaigns. Unspent $50 is an unfunded conditional budget, not verified recovered money. |
| Controls and opportunity frequency | No qualifying SLR opportunity to match; attention unavailable, earlier separate momentum results remain unpaired. No daily opportunity-rate estimate or strategy-superiority claim. |
| Verification | 100 passing engineering checks, including 34 controller checks and two new legacy-auditor regressions. Synthetic test paths are not investment observations. |

Documentation was freshly received at **2026-10-12 03:01:36.889 UTC**. PumpPortal Local/Lightning remain 0.5%/1%, with network/pool costs additional; Alpaca tier-one maker/taker remain 0.15%/0.25% on the credited asset. Alpaca's documentation says fee activity can post at day end; absence of same-day activity is not evidence of zero fees. Solana documents refundable account storage balances and charges network fees even on transaction failure. No rent/priority/FX amount or execution probability was guessed from those sources.

**D28:** Use decimal cash and exact token quantities for strict target and closure decisions; a tolerance must not manufacture a recovered campaign or erase dust.

**D29:** Enforce actual confirmation and local calendar limits through receipt events. Treat the controller as disconnected from continuous market monitoring until an event source and clock are actually present.

**D30:** Require complete net funding/conversion/cost reconciliation for any conditional target. Unpaid broker fees, locked rent, unresolved inventory and future threshold marks are not recovered cash. A later cost invalidates the provisional success without resetting the campaign.

**Next highest-value unresolved test:** verify successful historical swap instructions in at least three other mints for the fixed buyer sample, then meaningful initial funding/service ancestry. A balance is not a trade, a tiny transfer is not a root and later profile receipt cannot qualify a past decision. Connect those inputs with social evidence and fresh exact-size quotes before freezing a later buyer-plus-book ablation. Compare full liquidation and capital recovery/runner paths and apply the same campaign controller to eligible random, attention and momentum controls. No validated SLR closed position or doubling campaign has been added.

## Prior-trade proof and specialized model plan — October 12, 2026 UTC

Forty new finalized, read-only transaction responses arrived **05:45:26.905815–05:49:22.619986 UTC**, without errors. The same five event users were selected before retrieval using eight evenly spaced uninspected chronological signatures per user, all before their target events. Together with twenty existing bodies, sixty bodies contain **thirteen deduplicated earlier PumpSwap trades** under exact mint/account/owner/signer checks. Other venues/proxies remain unknown.

| User abbreviation; full identities in kit | Other mints traded, verified lower bound | Fourteen-day activity | Both conditions verified |
| --- | ---: | --- | --- |
| `3uzy…dej4` | 3 | Yes | Yes |
| `6KBt…aJfD` | 1 | Unknown | No |
| `8i8W…ttG` | 1 | Yes | No |
| `CSx2…eRFZ` | 2 | Unknown | No |
| `FXh9…Hcn` | 4 | Unknown | No |

Two users establish trades in at least three other mints; **only one** also establishes fourteen-day activity. These lower bounds are activity evidence, not proof of skill, independent ownership, first-ever target participation or a profitable entry. All new profile receipt times are later than the original target events; no historical eligibility is promoted. Independent funding clusters remain zero verified, and complete social/buyer-window/execution inputs remain missing. No new strategy fill, costed account path, paired control outcome or doubling was added.

The user asked which models should replace an LLM's numeric role. The proposed first comparison is rule/logistic baselines, **CatBoost** and a simple **competing-risk survival model**, predicting net-payoff distribution and exit timing. Later candidates are TabPFN v2, TCN and temporal graph models. This is a fit-for-task recommendation; no model was installed, trained or selected as a winner. `ENTRY-MODEL-0.1` freezes a future label/ablation plan at **06:00:00.724255 UTC**, with unchanged SLR-0.2 thresholds/hash and no new model performance claim.

**D31:** Prior balances or address references cannot certify trades. Require a successful authorized swap event, exact account/mint/owner, signing event user and pre-target time. Caught inner failures need rollback alignment; repeated log/CPI representations count once.

**D32:** Treat experienced activity as a feature to test, not “smart money” proof. One of five meets the two verified history conditions; absent proof in a bounded sample remains unknown.

**D33:** Keep LLMs for engineering/research assistance and compare specialized numeric models with simple baselines once valid net labels exist. Models cannot waive US, identity, cost, safety, quote, confirmation or campaign gates.

**D34:** Use explicit TabPFN v2 only as a possible commercial-project comparator with its attribution terms. The newer default weights' noncommercial terms do not authorize adoption here; no hosted inference, weight download or fee occurred.

**D35:** Retain shared handoff records for Codex and Claude, but do not claim knowledge of Claude's unshared chats, code or backtests. Keep Northstar forecast accuracy versus persistence distinct from memecoin realized-profit evaluation.

**Project-copy preference:** the user requests a detailed copy at `~/Projects/CodexCoinHunt`. That Mac directory is not mounted here. Maintain the complete `CodexCoinHunt.zip` export and safe installer, including code, evidence, reports, tests, prior versions, manifests and `.ai` handoff notes. Installation manages `codex-research/current` under the requested folder and preserves prior snapshots and existing Claude files. Do not claim the Mac copy has been written without actual access/import evidence.

**Checks:** 107 distinct engineering tests pass. The interim count of 115 included eight imported tests twice; the duplicate discovery was fixed and its output retained. Counts and synthetic fixtures are not investment validation.

**Next:** meaningful initial funding/service/creator ancestry and first-target-mint history, followed by social/quote integration for an untouched buyer-plus-capacity test. Compare depletion versus replenished selling where true event data exist, and all eligible matched controls after costs. No independent-cluster or model-profitability requirement has been relaxed.

## Mac continuity handoff — October 12, 2026 UTC

The current research increment is complete. `CodexCoinHunt.zip` carries the available code, public-source evidence, reports, results, tests, prior versions and shared Codex/Claude notes. `Mac_Desktop_Handoff.md` explains how to reopen this phone conversation on desktop and attach the installed project to a new local task. Official OpenAI project/history documentation was received at **06:13:27.735 UTC**; conversation history and local folder access are separate. Existing cloud tasks do not automatically acquire Mac file access.

The installer defaults to `~/Projects/CodexCoinHunt/codex-research/current`, verifies the archive's hashes and preserves unrelated root files. Recognized earlier copies move to snapshots; unrecognized existing copies stay untouched. Nine independent copy-integrity checks pass, including preservation of Claude files, corrupted/archive-path rejection and rollback of a failed copy switch. These are separate from the 107 research checks and are not market observations.

The Mac filesystem remains inaccessible from this cloud session, so installation on the Mac has not occurred. Claude's actual chats, repositories and backtests remain unreviewed. The handoff is a detailed project record, not a verbatim conversation export. No real orders, private keys, payments or package installation were involved.

**D36:** Use the same account/workspace to recover conversation history, and explicitly attach the installed folder for desktop file work. Preserve existing Claude material and require actual provenance before combining findings.

## Returning-buyer falsification and funding audit — October 12, 2026 UTC

**Material interpretation change:** four of the five fixed sampled buyers had earlier successful authorized buys in the exact same mint. They supplied **97.2101822278% of the original subset's buy quote notional**, including its largest buyer. These purchases cannot establish new-to-mint conversion. The one remaining buyer is unknown, with incomplete sampled history. The user previously verified as mature and active in three other mints is also a returning target buyer. No user in this cohort establishes maturity, diversified history and first-time entry together.

SLR-0.2 and its hash are unchanged; this rejects a misleading interpretation of the sampled demand rather than all possible SLR opportunities. No strategy entry, realized account path or doubling is added. Details and exact identities are in `Buyer_Participation_and_Funding_Research.md`.

| Bounded test | Result |
| --- | --- |
| Freeze selection before new bodies | `FUNDING-AUDIT-0.1`, 06:55:38.343949 UTC. Entire reported prior-24-hour window for the largest buyer; eight chronological ranks per other buyer, including failures. |
| Capture raw bodies | 47 selected wallet/signature pairs; 7 saved bodies reused, 40 further finalized read-only responses received 06:56:38.402367–07:02:37.675636 UTC. Zero response errors. |
| Preserve failures | 46 successful bodies and 1 failed transaction. Its recorded 9,000-lamport fee belongs to that historical transaction, not our paper account. |
| Establish prior exact participation | 14 deduplicated target swaps: 11 buys, 3 sells. Four users each have an earlier authorized buy; largest has 4 earlier buys and 1 sell. |
| Avoid false funding roots | Four incoming native payments: one below the frozen diagnostic materiality, three without a transaction-signing source. No material signed native receipt candidate, first funding root or independent cluster verified. |
| Resolve transient token identity | 17 closures credit buyers: 15 wrapped-SOL releases, 2 other-token storage balances. Initialization instructions recover accounts absent from both balance lists. Initial missing-identity labels/code retained and corrected. |
| Bound further requests | Zero second-hop reads because no qualifying native first-hop candidate exists. Carried-in quote tokens, earlier capital and service/creation provenance remain missing. |
| Challenge the mechanism | Future `PARTICIPATION-ABLATION-0.1`: new-to-mint conversion versus labelled returning-buyer accumulation; no tested payoff or promoted arm. |
| Verify implementation | 122 distinct research engineering checks, including 15 new checks. Prior 107/120 results retained. Installer checks remain separately nine. |

Current PumpPortal/Alpaca fees and Alpaca coverage documentation were refreshed October 12, 2026. Actual state/account authorization, this mint's acceptance, historical fee charges and fills remain unverified. No paid data, wallet funding, private key or order operation occurred. All new receipts are later than original events and cannot be backdated into eligibility. This is the same development cohort, not a new market census or independent forward test.

**D37:** First-time buyer conversion requires participation history. An earlier authorized exact-mint buy disproves it. Bounded absence and unsolicited positive inventory are not sufficient to prove or disprove an earlier buying decision.

**D38:** Preserve native-payment, token-close, fee-payer and owner roles separately. A transient WSOL account is not an independent funder. Missing initialization/balance identity stays unknown; unknown distinct sources do not establish independence and common services do not certify shared ownership.

**D39:** Apply demonstrated prior-participation rejection before costly ancestry enrichment. This is a data-acquisition priority, not a measured cost-saving return or a changed strategy threshold.

**D40:** Evaluate returning-buyer accumulation as an explicit competing mechanism on genuinely later untouched data, keeping full costs, the same campaign controller and eligible matched controls. Reused signatures, directional charts and passed fixtures do not supply net payoff labels.

**Next priority:** first-participation checks on later candidate cohorts, carried-in quote-token funding and service/creation evidence for candidates that remain eligible; then complete social/buyer windows and fresh size-specific exit capacity. Opportunity frequency, calendar campaign outcomes, actual fills/FX/conversion and matched random/attention/momentum account results remain unavailable. Maintain the updated detailed Mac export without claiming direct Mac installation.

## Quote-asset provenance and cash-origin refinement — October 12, 2026 UTC

The same original five buy bodies show three USDC/USDT disposals with routed WSOL, one other-mint disposal with routed WSOL, and one native-SOL quote-account input. This refines the “existing/recycled capital” explanation; all routes are not rotations out of another meme coin. Spent stablecoins are not proved fresh fiat, and retained target tokens are not recovered USD. The exact analysis is in `Quote_Asset_and_Capital_Origin_Research.md`.

**Measured accounting correction:** the stable-prefix `user_quote_raw` field is smaller than exact quote-account outflow in two `buy_exact_quote_in` variants. Complete official-IDL decoding now shows that `quote_amount_in` is their gross debit and `user_quote_amount_in` is curve input; the difference exactly equals LP + protocol + creator fees. For three `buy_v2` events, `user_quote_amount_in` is already gross debit. All five instruction-aware gross amounts match exact outflow. The prior event parser remains archived; `Pump_Event_Fee_Reconciliation_Research.md` has the complete correction.

| Increment | Result |
| --- | --- |
| Freeze quote-role audit | `QUOTE-PROVENANCE-0.1`, 08:22:27.696862 UTC; five original buys reused, no new trade-return sample. |
| Current source-role lookup | One finalized six-account response received 08:23:45.524501 UTC, slot 455979513. Three source token accounts are WSOL; their authorities are currently program-owned data accounts. Current state cannot establish historical ownership. |
| Preserve common roles | Two buyers share a route source and fee payer while disposing of their own USDC. These roles do not certify common ownership, initial funding or independent people. |
| Bound remaining participation test | Eight closest previously uninspected pre-target signatures frozen 08:26:34.933722 UTC, received 08:26:46.566006–08:27:59.086134 UTC: six successes, two failures, zero missing bodies. No prior target swap established; fifth user remains unknown. |
| Decode exact movement | Legacy WSOL program/mint/decimals, owner versus authority, transient identity, CPI execution order, pool discriminator and raw integer precision checked. Missing parsing/stack height stays unknown. |
| Freeze alternative feature comparison | `CAPITAL-ORIGIN-ABLATION-0.1`, 08:38:45.057240 UTC: cash-asset spending versus other-mint disposal versus native input, retaining all SLR gates and matched full-account controls. No evaluated payoffs. |
| Verify | 137 distinct engineering checks, fifteen new. Previous 122/135 outputs and reports retained. No fixture is profitability evidence. |

Only nine new public reads occurred: one account bundle plus eight historical bodies. The source packets retain UTC receipts, official USDC/USDT mint references and current PumpPortal/Alpaca fee/coverage checks. No price peg, free sponsorship, zero conversion cost or this mint's US/account/venue acceptance is assumed. Data/real order/private key/funding payments remain zero; the conditional $50 campaign is still unfunded.

**D41 (clarified):** Keep event fields, verified token transfers, native balances, storage locks/refunds and reconciled economic costs separate. Select gross/net fields by exact PumpSwap instruction semantics. A fee-aware quote or gross fill already contains the pool fee components; do not charge them twice.

**D42:** Trace original owned input assets through intermediary routes. A route vault, transfer authority, fee payer and beneficial owner are different roles. Current role receipt times cannot be backdated; shared intermediaries neither prove shared ownership nor independence.

**D43:** Treat cash spending and other-mint disposal as separate proposed features. Preserve unknown histories and all other strategy gates. Compare only on later untouched, fully costed account paths with eligible random, attention and momentum controls.

**Next:** trace original owned input accounts for still-eligible later candidates and establish complete social/buyer/quote windows. The fifth fixed buyer remains first-participation unknown and funding independence remains zero verified. No opportunity rate, calendar campaign outcome, matched net payoff, trained model, strategy closed position or doubled campaign has been added. SLR-0.2 and its hash remain unchanged.

## Social coverage and paid-visibility falsification — October 12, 2026 UTC

The fixed Claudia buyer episode now has exact paid-promotion chronology. The DEX Screener paid-order endpoint, received **2026-10-12 11:25:46.130612 UTC**, reports a **10-unit boost** paid at **2026-10-11 21:35:41.416 UTC**, plus approved token-profile and community-takeover payments. Six retained exact-pair responses show `boosts.active = 10` through **01:31:44.115 UTC**. The first sampled buy occurred at **01:42:16 UTC**, 631.885 seconds later. This verifies a paid-visibility confounder; it does not prove the boost caused buying or that all attention was paid.

`SOCIAL-COVERAGE-0.1` froze exact-mint, name/chain and project-domain queries before collection. Public AppView returned HTTP 403 twice and stopped at the fixed error bound. Zero successful source responses means **unknown coverage**, not zero posts or a quiet period. No previous wave, cooldown, author/community count, new-audience fraction, address consensus or organic-attention feature is promoted. The original episode cannot support the organic-audience premise.

Three DEX context reads succeeded at **11:25:46.111875–11:25:54.295894 UTC**. Ten exact-mint pair rows describe one token's venue context; they are not attention observations. Direct bounded top/latest absence and missing optional active-boost fields at those later receipts do not prove zero promotion. Exact paid orders and time-stamped active-pair observations carry the chronology.

`PROMOTION-HANDOFF-0.1` tests whether exact-mint attention and qualified buying persist after a conservatively verified promotion end. It excludes Claudia, begins with candidates first observed after **11:24:42.503671 UTC**, retains every SLR US/safety/cost/quote/buyer/campaign gate, and compares the same $50 account path against SLR, active-boost attention, plain attention, momentum and matched random controls. It is not promoted and has zero eligible signals, closes or campaigns.

**D44:** Reject the fixed episode as evidence of independently verified organic second-look attention. Paid visibility was active shortly before the observed buying; causal attribution remains unknown.

**D45:** A failed or incomplete social query never becomes a zero-attention observation. Missing history, pagination, post clocks, communities and paid status keep corresponding gates unknown.

**D46:** De-duplicate DEX context at exact chain and mint. Multiple pools and repeated list rows are not authors, communities or independent trials.

**D47:** Test paid-to-organic persistence only in a later untouched cohort. Require conservative promotion-end evidence, direct post coverage and all existing execution/account controls; do not retrofit this sample.

The implementation retains raw bodies, HTTP failures, UTC clocks, exact identity and stop conditions. Fifteen new adversarial tests bring the suite to **152 distinct engineering checks**. No new trade, fee-bearing data request, opportunity-rate estimate, matched net result, recovered USD outcome, strategy close or doubled campaign was added. `Social_Coverage_and_Paid_Visibility_Research.md` has the full chronology and reproduction commands.

**Next:** establish authorized continuous exact-mint social coverage, then prospectively join post, buyer, paid-visibility and exact-size quote clocks for a later cohort. Keep the first-participation and capital-origin ablations, and count every rejected/no-trade day, unsellable token, unresolved exit and calendar timeout.

## Complete PumpSwap event-fee reconciliation — October 12, 2026 UTC

The highest-value accounting gap from the prior pass is resolved. `PUMP-EVENT-FEE-RECONCILIATION-0.1` decodes the complete pinned official `BuyEvent`/`SellEvent` layout rather than only the stable 344-byte prefix. It requires exact byte consumption, exact known buy instruction semantics and de-duplicates log/CPI copies without treating them as separate observations.

Eight unique retained events decode with zero parse issues: five buys and three sells. All eight satisfy both their instruction-specific gross/net fee equation and intermediate LP equation. Seven show nominal 45 bps LP + protocol + creator components; one sell shows 50 bps because its creator/holder-reward component is 25 bps. All eight `buyback_fee` values are the configured integer subdivision of `protocol_fee`, not an extra user charge.

For the five original buys, instruction-aware gross debit matches exact quote-account outflow **5/5**. The old stable-prefix `user_quote_raw` matches **3/5** because its role changes for exact-quote instructions. The five gross debits total **10.255334171 SOL**. Proven returning buyers account for **97.2220091588%**, and the largest buyer for **87.3543408106%**. These revisions are descriptive and do not change prior eligibility, buyer independence or any return.

**D48:** Money accounting must select gross and net fields by exact `ix_name`, verify LP + protocol + creator decomposition, and reject unknown/truncated layouts. Field names alone are not a universal economic definition across instruction families.

**D49:** `buyback_fee`, holder rewards, cashback and creator-fee accumulators are routing/suballocation fields in this evidence, not amounts to blindly add to the user's debit. Prefer exact account movement or authenticated net fills and prevent duplicate fee charging.

**D50:** The official fee-aware PumpSwap SDK route quote already embeds pool economics. Continue applying PumpPortal service, network/priority, rent, data and conversion costs separately only when applicable and not already included.

Nine new tests bring the suite to **161 distinct passing engineering checks**. The forensic plan explicitly discloses that the discrepancies and exploratory event fields were inspected first; this is not preregistered or out-of-sample return evidence. No new market observation, qualified strategy entry, close, matched control outcome, opportunity-rate estimate or doubled campaign was added. SLR-0.2 and its hash remain unchanged.

**Next:** use the corrected gross-debit contract in future joined social/buyer/quote receipts. The dominant research dependency remains authorized continuous exact-mint social coverage and a later untouched, fully costed cohort; Raydium quotes, authenticated fills/FX/conversion and complete control outcomes also remain open.


## Mac repository continuation — October 12, 2026

Desktop v5 / research v11 is now verified locally in `~/Projects/CodexCoinHunt/continuations/codexcoinhunt`: 379 original source files, 161 research tests and nine installer tests. Earlier Mac receipts and the two bounded HTTP-403 social responses are retained; coverage is unknown and no additional empirical outcome is added. See `../MAC_CONTINUATION.md`, `../MAC_CONTINUITY.json` and `../../CONNECTED_PROJECTS.md`. Original release documents and historical local notes remain preserved. SLR-0.2 rules/hash and cloud D48–D50 are unchanged. Actual Northstar artifacts are still missing; forecasting and profit conclusions remain separate.
