# Resolant Labs — Second-Look Relay

Research date: October 11, 2026, America/Chicago. Strategy: **SLR-0.2**. Starting campaign balance: **$50**. Execution model: **PumpPortal Local**, with Lightning and Alpaca comparisons. Current mode: **paper research**.

**The deliverable is a new, precisely specified composite hypothesis and a working evidence/accounting kit. Consistent account doubling has not been demonstrated. Existing attention and second-wave ideas are prior art; worldwide “nobody has tried this” novelty cannot be certified from public research.**

## The proposed edge

Buy a surviving meme token when a different audience rediscovers it, that audience agrees on the exact token address, and apparently unrelated buyers begin converting the renewed attention into purchases while earlier selling is fading. Enter while its price is still near the base. Keep a portion of successful positions exposed to the ensuing demand wave.

The behavioral premise is that people notice, remember, check legitimacy, identify the right token, and acquire it at different speeds. Those delays may create a brief gap between new attention and completed demand. This is an inference to test, not a measured conversion probability. Social authors and wallet owners are separate populations; the strategy does not pretend to match a particular viewer to a buyer.

The specific proposed contribution is the joint requirement for **audience change + token-address consensus + buyer conversion + fading seller supply**, followed by exits measured against executable net proceeds. A plain volume spike, a token's cheap unit price, or an influencer's enthusiasm does not establish those conditions.

This operationalizes the useful part of “luck”: seek exposure to plausible demand cascades before they are exhausted, reject crowded or fabricated signals, limit failed attempts, and retain enough upside on the exceptional outcomes. Randomness alone does not create an edge; the experiment must show that conditioning on these events improves the outcome distribution.

## Why this candidate survived the research screen

| Research finding | Design consequence | Limit |
| --- | --- | --- |
| Qureshi and Zaman find differences between social engagement, raw post volume, bot activity, and future crypto performance [S01]. | Measure who is newly engaging rather than simply counting posts. | Their older, longer-horizon sample does not validate intraday Solana trading. |
| A recent pump.fun manipulation preprint documents wash activity, obscured creators, coordinated selling, copycats, and social manipulation [S02]. | Deduplicate funding/trading clusters; track creator-linked supply and exact mint identity. | Heuristics cannot prove that wallets are independent humans. |
| An existing open-source attention terminal already counts five-minute social spikes against age-aware baselines [S03]. | Attention spikes alone are prior art and serve as a comparison strategy. | Its observed attention half-life is chain/sample specific. |
| DEX Screener exposes profiles, boosts, takeover metadata, and market snapshots [S04]. | Collect observable arrival times and retain paid promotion as a separate label. | The feed is a selected visibility sample, not a complete launch or social census. |
| PumpPortal has different Local/Lightning fees and metered trade streams [S05–S06]. | Favor low turnover, shortlist before using paid streams, and price every extra exit. | Fees do not imply profitable fills or an informational advantage. |

## Exact SLR-0.2 entry rules

All conditions must pass at the first decision and again after **60 seconds**. An unknown required condition is a rejection. All measurements use only evidence available by the decision time.

| Condition | Frozen initial rule |
| --- | --- |
| Asset and venue | Spot Solana token on an explicitly supported route; US access, exact mint, and route eligibility verified. |
| Age | Mint is 6 hours–7 days old and has already migrated to a supported liquid pool. Pool age is never substituted for mint age. |
| Previous audience | A recorded earlier wave contained at least 20 distinct author clusters. |
| Genuine cooldown | At least 60 consecutive minutes after that wave with attention at or below 50% of its peak rate. |
| Renewed attention | At least 15 author clusters in the last 10 minutes, and at least 2× the rate in the immediately preceding 30-minute window. |
| Audience change | At least 60% of current author clusters did not participate in the previous wave; at least two identifiable communities outside the previous audience are now participating. |
| Address agreement | At least 80% of the observed current meme-family author clusters identify or link to this exact mint. Vague ticker mentions do not establish consensus. |
| Organic provenance | Original public posts and their sources are verified; paid-only pushes, undisclosed sponsorship, copied posts and unresolved coordination fail this gate. “Organic” remains an evidence-based heuristic. |
| Purchase conversion | At least eight distinct, apparently unrelated buyer clusters entered in the last complete 5-minute window. These are new to this mint, not newly created wallets. |
| Wallet maturity | A counted buyer wallet has at least 14 days of observed activity, at least 10 historical transactions and prior interaction with at least three other mints. |
| Cluster coverage | At least 80% of relevant buy notional has usable funding/trading provenance. Suspected related buying contributes no more than 20% of buy notional. |
| Net demand | Observed USD buy notional exceeds sell notional in the last complete 5-minute window. Transaction counts alone do not qualify. |
| Seller exhaustion | Sell notional is at most 60% of the preceding non-overlapping 5-minute window, which must have at least $50 of selling. |
| Price has not escaped | Net price change over the last 10 minutes is between −5% and +10%, measured on the same pool/quote basis. |
| Exit capacity | At least $25,000 reported liquidity plus a size-specific simulated buy/sell route. Liquidity custody and exit simulation verified. |
| Supply concentration | Ten largest owners excluding verified pool/program holdings control at most 35%; known creator-linked ownership at most 10%. |
| Token controls | Mint/freeze authorities disabled; unsupported transfer hooks, fees, delegates or other extensions absent. Recheck at the decision. |
| Cost | Same-state roundtrip loss is at most 6% of the position budget after all route fees, expected adverse execution, network/tips and allocated research costs. |
| Freshness | Final executable quote is no more than two seconds old. Relevant feature availability is no more than five minutes behind the event. |
| Capital | Sufficient SOL for the actual route, any account rent and metered-data requirement, with the campaign reserve intact. |

### Definitions that prevent false positives

An author cluster groups near-duplicate posts and evidence of shared promotion, using public material and a frozen classification method. A community is an observed public audience/network group, not a claim about a person's private identity. Missing access to the earlier audience history is missing data, not proof of a new audience.

Wallet clustering combines repeated synchronized trading, common non-service funding roots, shared bundles and transfer relationships. Funding paths may be examined up to two hops over the prior 24 hours, with historical co-trading retained. Known exchange, bridge, router and other service funders are excluded from common-owner grouping; sharing an exchange withdrawal source does not make two people the same owner. Unknown funders lower coverage rather than create confident independence.

Each wallet counts once per window regardless of purchase count. Wash-like round trips, bundled coordinated buys and creator-linked clusters are excluded from the eight-cluster conversion threshold. A seasoned wallet can still be controlled by a manipulator, so maturity is not a certification.

The social rate compares **the last complete 10 minutes** with **the immediately preceding, non-overlapping 30 minutes**, normalized to clusters per minute. A zero baseline never produces an infinite score: require a separately observed previous wave and a defined baseline floor of one cluster per 10 minutes. Freeze that convention in the enrichment adapter. Price and chain windows must end before the decision.

No artificial social engagement, promotional campaign, wash trading, spoof orders, wallet concealment, geographic circumvention, or coordinated pump is part of the strategy. It observes public behavior and buys/sells normally.

## Position and exit rules for the $50 campaign

The initial paper allocation is **$7 all-in**, or 14% of realized campaign equity. This is a research sizing assumption, not a fitted optimum. Hold at least **$5** outside positions; increase that reserve if actual SOL/rent requirements exceed it. Use one open position, no borrowing and no averaging down. Re-entry into the same mint waits 24 hours. Limit entries to three per rolling 24 hours.

Exit conditions are evaluated using estimated **net proceeds for the actual remaining quantity**, not a displayed chart price:

1. **Abort before capital recovery:** attempt a full exit when liquidation value falls to 80% of the original all-in allocation, the verified new-buyer flow stalls for two complete 5-minute windows, or usable pool liquidity falls 20%. Record failures and actual later recoveries. The 20% position stop is an instruction, not a guaranteed maximum loss.
2. **Recover capital:** when the full position's net liquidation value reaches twice the original allocation, simulate the partial sale and sell the smallest quantity whose net proceeds recover the original allocation plus expected remaining exit costs. Do not assume the recovery is exactly half the tokens; fixed fees and size-dependent impact matter.
3. **Keep the remaining upside:** trail the remainder at a 25% decline from its executable liquidation high. The additional exit costs remain part of total P&L. Exit earlier if the buyer/attention thesis breaks.
4. **Expire stalled trades:** after 90 minutes, exit if net position value is below 1.25× the original allocation and the demand thesis has not strengthened. Every remainder exits by six hours.
5. **Handle outages:** at most two bounded retries for a failed exit, followed by an explicit unresolved-position state and no new entries. Never book a pretend stop fill. A documented unsellable remainder is written off; an unresolved remainder keeps the campaign unconfirmed.

Stop new entries after a $5 realized session loss, with sessions measured in America/Chicago calendar days. Halt the campaign at $40 liquidatable equity, after 30 completed positions, or after 30 calendar days, whichever comes first. A gap can leave the balance below $40. A successful campaign requires **more than $100 realized, recoverable USD-equivalent**, after closing the positions and deducting all costs. Stop trading on target completion. Timeouts and idle campaigns count as failures to meet the doubling target.

## Verified fees and estimated $7 economics

PumpPortal Local charges **0.5% per trade**, Lightning **1% per trade**, before network and underlying pool fees [S05]. Pump's current bonding curve fee is **1.25%**; canonical PumpSwap fees depend on capitalization and pairing, while documented non-canonical pools charge **0.30%** [S07]. The strategy uses graduated pools; 1.25% is a conservative ordinary-pool comparison, not a claim that every graduated pool charges it. Custom pairings and holder-reward configurations need their own quoted fee checks.

Alpaca's first crypto fee tier is **0.15% maker / 0.25% taker** [S08]. Its listed assets include several established meme coins, but that does not provide arbitrary new-token execution [S09]. The main SLR universe therefore uses PumpPortal. An Alpaca adaptation must test a different listed-asset universe and is not validated by the Solana experiment.

The following is **fee arithmetic**, not performance. PumpPortal assumptions are 0.5% adverse execution per side, $0.02 network/tips per successful transaction and $0.05 allocated data per position. Alpaca assumptions are 0.25% adverse spread/execution per side, zero on-chain transfer cost for in-account trades and no allocated paid data. Those assumptions must be replaced with measured costs; failed attempts, extra exits, funding/conversion and withdrawal charges are additional. Rent is refundable locked capital, not automatically a permanent expense.

| Case | Gross coin-price increase needed to break even | Gross increase needed for 2× net position proceeds | Net proceeds if a $7 position's price rises 2× |
| --- | ---: | ---: | ---: |
| Local + conservative 1.25% pool | 1.060× | 2.117× | $13.23 |
| Lightning + conservative 1.25% pool | 1.071× | 2.139× | $13.09 |
| Local + independently verified 0.30% pool | 1.040× | 2.077× | $13.48 |
| Alpaca taker, supported listed asset | 1.010× | 2.020× | $13.86 |

The cost model uses percentage deductions from the respective trade notionals. It is an approximation. The fill ledger uses actual/quoted net account changes instead, so a fee already embedded in a route is never deducted twice. Exit-side fees can differ from entry-side fees.

For reproducibility, with budget B, entry fixed/data costs c, exit fixed costs d and percentage-cost retention factor k, the modeled net proceeds are `max(0, (B-c) × k × gross_price_multiple - d)`. All parameters are retained in `economics.py` and `results/economics.json`.

**Doubling a position is different from doubling the account.** A single $7 position rising 3× under the conservative Local assumptions returns about $19.85 and moves the $50 account to about $62.85. As a deliberately hypothetical path, four gross-3× winning positions and two filled net-20% losing positions, resized to 14% of current equity, end near $118.33. This shows what the arithmetic requires; it supplies no evidence that those outcomes occur at that frequency. A runner exit can produce a different total payoff from an all-at-once 3× sale.

## Profitability optimization and the falsification test

Optimize expected net logarithmic account growth subject to the drawdown/campaign constraints. The first question is whether the signal changes the distribution at all. Only then compare position fractions, confirmation delays, and exit methods. A high winning percentage is not sufficient if successful trades are small and occasional unsellable positions erase them.

Use a chronological development period followed by a frozen forward period. Keep a separate untouched final evaluation period. Every parameter revision increments the version and starts a later validation period; it cannot improve yesterday's reported result. Do not optimize many thresholds on this initial sample and then call it independent evidence.

| Experiment | What it tests | Evidence that would weaken the design |
| --- | --- | --- |
| Full SLR vs matched random eligible tokens | Whether the behavioral combination adds value beyond market luck | Similar or worse net outcomes after equal latency and cost assumptions |
| Full SLR vs plain attention spike and plain momentum | Whether the new conditions add value beyond existing approaches | No improvement in forward expectancy or campaign completion |
| Remove audience-change condition | Contribution of a genuinely new audience | No change in results or excessive dependence on classification mistakes |
| Remove address-consensus veto | Whether copycat fragmentation matters | The veto mainly excludes profitable events without reducing bad outcomes |
| Remove seller-exhaustion rule | Whether supply relief matters | No improvement, or entry arrives too late after a delayed rule |
| Local vs Lightning, matched episode and timing | Fee savings versus speed/fill reliability | Local's latency or failure rate outweighs its lower fee |
| Capital recovery + runner vs full liquidation | Whether preserving the upside outweighs the extra fee and reversal exposure | Lower net growth or worse failure rates |

Random controls must be chosen from the universe known at decision time, matched on age, liquidity, venue, narrative and market regime. Give them the same simulated execution delay, fee rules, safety eligibility, position availability and hold horizon. Record rejected candidates and their forward paths rather than keeping only successful selected tokens. Paid boosts remain labeled controls rather than evidence of organic attention.

Measure executable size-specific quotes, actual account debits/credits where applicable, rejected/no-route orders, latency, fees, rent, liquidity changes, all open/unsellable remnants, net expectancy, geometric account growth, maximum drawdown, campaign doubling/stop/timeout frequencies and opportunities per calendar day. Bootstrap complete day/narrative blocks to preserve correlated outcomes; treating 100 buyers of one meme as 100 independent experiments is invalid.

Initial promotion requirements are at least **150 forward closed positions across three market regimes** plus **30 non-overlapping complete campaigns**; the campaign requirement may demand substantially more than 150 positions. At least 80% of campaigns must double and the 95% Wilson lower confidence bound must exceed 70%. With 30 campaigns, 26 successes have a lower bound near 70.3%; these are admission thresholds, not guarantees of future consistency. Also require a positive block-bootstrap lower bound for net expectancy and superiority to the matched controls. A lost sell route or expired campaign stays in the denominator.

Remove the best three outcomes and report the effect, as well as halving winner payoffs, doubling measured costs, delaying execution and clustering losses. Sensitivity results in the kit use hypothetical IID full-position outcomes. They do not simulate the full exit path, timeouts in days or daily standdowns and cannot certify the strategy. They show that results change drastically when the assumed winner payoff falls; real return distributions must supply those inputs.

## Affordable data and implementation status

Use DEX Screener's documented public metadata/market endpoints for discovery, plus authorized public social observations and on-chain evidence for enrichment. Record first observed times: a metadata appearance is not necessarily its original publication time. Start with a small manual shortlist and charge research time separately when assessing commercial practicality.

PumpPortal creation/migration streams are free, while token/account trade streams are metered at 0.01 SOL per 10,000 events and require a linked funded wallet [S05–S06]. Do not subscribe to every token with a $50 account. X's published post-read unit price is $0.005 [S10], so 1,000 post reads cost $5 before additional user/community lookups. Broad paid social ingestion can consume the account's budget before a single trade. The zero-subscription/manual prototype must prove value before scaling ingestion.

The kit includes the fixed-universe DEX recorder, optional raw PumpPortal recorder, rule gate, fee/sensitivity engine, net-fill auditor and journals. Later increments add read-only buyer/quote/book evidence and an offline campaign controller with 100 engineering checks. It does **not** contain live order submission, automatic social inference, reliable owner identity detection, continuous scheduling, authenticated conversion/withdrawal adapters, matched-control execution or a completed forward-profitability study. No funded stream, private wallet, or trade was used.

## US route and records

PumpPortal's current published prohibited-locality list does not name the US; it still conditions access on applicable law and sanctions and may restrict availability [S11]. Pump's October 8 terms likewise impose eligibility and product-specific restrictions [S12]. This supports selecting normal spot execution as the research route, not a blanket legal clearance for every token or feature. Venue/account eligibility remains a gate; use no derivatives or geographic workarounds.

The SEC's February 2025 staff statement describes certain typical meme-coin transactions as outside federal securities registration, but expressly has no legal force and does not resolve every token's facts [S13]. Ignore tokens promising business income, stock rights or deceptive asset backing in this experiment. Alpaca crypto is available only in supported jurisdictions and for supported assets; confirm the current account-specific eligibility before adapting the strategy.

USD-equivalent research returns are before personal taxes. The IRS treats digital assets as property and requires relevant purchase/disposal, unit, basis and fair-market-value records [S14]. Preserve timestamps, mint/asset, quantities, fees, USD values, signatures and basis; moving SOL into another token is a transaction to record. Bank cash-out and tax reserves are separate from a trading-balance doubling claim.

## Source ledger

All sources checked October 11–12, 2026. Observations and computations are kept in the accompanying kit; no long source passages are reproduced.

- **S01:** Qureshi & Zaman, [Social Media Engagement and Cryptocurrency Performance](https://arxiv.org/abs/2209.02911), research paper. Related peer-reviewed full text: [PLOS/PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC10174546/).
- **S02:** Szwajcok et al., [Meme Coin Factories: Uncovering Large-Scale Manipulations on pump.fun](https://arxiv.org/abs/2609.10246), September 2026 preprint.
- **S03:** [marlowxbt/trace](https://github.com/marlowxbt/trace), original project documentation describing a pre-existing attention-spike detector.
- **S04:** [DEX Screener API reference](https://docs.dexscreener.com/api/reference), provider documentation.
- **S05:** [PumpPortal fees](https://pumpportal.fun/fees/), provider fee schedule.
- **S06:** [PumpPortal real-time data](https://pumpportal.fun/data-api/real-time/), provider websocket documentation.
- **S07:** [Pump fees](https://pump.fun/docs/fees), current schedule updated October 8, 2026.
- **S08:** [Alpaca crypto spot fees](https://docs.alpaca.markets/us/docs/crypto-fees), official fee schedule.
- **S09:** [Alpaca supported cryptocurrencies](https://alpaca.markets/support/what-cryptocurrencies-does-alpaca-currently-support), official asset list.
- **S10:** [X API pricing](https://docs.x.com/x-api/getting-started/pricing), official resource-based pricing.
- **S11:** [PumpPortal terms](https://pumpportal.fun/legal/), provider eligibility and access terms.
- **S12:** [Pump terms](https://pump.fun/docs/terms-and-conditions), updated October 8, 2026.
- **S13:** [SEC staff statement on meme coins](https://www.sec.gov/newsroom/speeches-statements/staff-statement-meme-coins), February 27, 2025.
- **S14:** [IRS digital assets](https://www.irs.gov/filing/digital-assets), official record/reporting guidance.
- **S15:** [Solana transaction fees](https://solana.com/docs/core/fees) and [token account creation costs](https://solana.com/docs/tokens/basics/create-token-account), official protocol documentation; quoted account sizes/rent vary and must be queried.
- **S16:** [PumpPortal Local trading API](https://pumpportal.fun/local-trading-api/trading-api/), supported route parameters. Reviewed as a future implementation reference; no order called.

## Initial observed market sample

A read-only 12-minute collection followed a universe frozen before future snapshots. Quote receipt times span **October 11, 2026 07:24:30 PM CDT to October 11, 2026 07:36:09 PM CDT**. This development sample predates the final rule freeze and is excluded from strategy proof.

| Measurement | Observed result |
| --- | ---: |
| Selected Solana tokens | 66 |
| Snapshot cycles / HTTP snapshot requests | 24 / 72 |
| Failed snapshot requests | 0 |
| Initial tokens with at least $25,000 reported liquidity | 15 |
| Tokens passing only pool-age/liquidity prefilter | 6 |
| Valid first/final prices on the same initial pool | 65 |
| Missing final same-pool price | 1 |
| Median first/final chart return | 0.00% |
| Lowest / highest first/final chart return | -75.53% / 247.15% |
| Tokens whose observed chart reached at least 2× | 1 |
| Verified complete strategy entries / closed positions | 0 / 0 |
| Demonstrated doubling campaigns | 0 |

The rising token was identified as a winner only after its future prices arrived. No evidence here establishes that SLR would have selected it, that its quoted price could have been sold at our size, or that the account captured its gain. The falling token likewise does not prove a filled protective exit. The source universe contains profile, boost and takeover selections, so its counts are not market-wide probabilities.

All 66 candidate records retain observed liquidity and explicitly reject missing social, funding, safety and executable-quote evidence. These rejections mean **insufficient evidence**, not that all 66 tokens are proven bad. Full raw snapshots, the fixed initial pool paths, source provenance, fee computations and decision reasons are preserved in the kit.

**Current evidence verdict: mechanism specified; fee arithmetic reproduced; software accounting checked; investment edge and consistent account doubling unconfirmed.**


## Research extension — October 11, 2026

The leading design remains **SLR-0.2, unvalidated**. A frozen alternative, **Capacity-Adjusted Revival (REV-0.1)**, was tested on a corrected public rejection corpus and is **not promoted**. Its rule set required a short-term rebound during a longer decline, a preceding quiet/negative 5-minute reading, at least 20% liquidity growth, limited price escape and a $7-size cost estimate. It produced **zero signals** in both chronological partitions. In the development-only diagnostic, 161 observations reached the rebound/decline conditions; none passed the extra 20% liquidity-growth requirement. There is no return distribution to optimize for that version.

The input corpus was verified against its published archive checksum and reduced to the fields used by our study without filtering source rows. It contains **716,762 observations, 18,237 rejection events and 4,635 mints** [S17]. The window is April 11–July 16, 2026, with a June collection gap. It is an observed follow-up frame, not all launches or all rejected tokens. Study development ends before June 3; the chronological holdout is June 24–July 16. This is retrospective analysis, not live forward execution.

| June 24–July 16 comparison | Result |
| --- | ---: |
| Plain rebound/momentum attempts in the selected rejection frame | 912 |
| Unique mints among those attempts | 571 |
| Usable entry/exit mark paths after the capacity recheck | 588 |
| Missing entry marks / failed entry-capacity checks / censored exits | 144 / 53 / 127 |
| Mean modeled net return among observed paths only | -13.00% |
| Mean with explicitly assumed zero recovery for censored exits | -22.46% |
| Matched attempts with both paths observed | 191 |
| Paired momentum / random mean modeled net return | -12.36% / -12.32% |
| Paired difference, percentage points | -0.042 |
| Descriptive day-block 95% interval for that difference | -4.50 to 4.97 points |
| Executable fills or validated doubling campaigns | 0 |

Costs use the current conservative Local case plus a balanced constant-product depth approximation. Signals are chosen before later observations; entry uses the next observed mark after the latency allowance. Stops use observed prices, including gaps, rather than pretend fills at the requested threshold. Timely exit marks must arrive within the bounded horizon. Controls use only observations available at the decision, with the same rejection reason, venue and liquidity bucket; they are not matched on unavailable social narrative or wallet identity. Repeated mints, incomplete pairs and observability selection remain. The interval is descriptive and does not fully handle cross-day mint correlation. These are costed **mark paths**, never captured trading returns or a funded $50 account.

**Decision:** do not promote indiscriminate short-term rebound entry from this frame. Do not loosen REV-0.1 on the inspected holdout and describe the result as independent validation. Any new hypothesis needs a new freeze and a later untouched period. A direct account replay, safety-qualified execution and attention/wallet controls are still outstanding.

A useful structural finding is that total USD pool liquidity can change mechanically as the price changes. In a balanced constant-product pool with unchanged LP capital and quote-asset USD value, USD liquidity scales with the square root of the token price. Our development diagnostic over 385,853 same-pool observation pairs had a median liquidity-change ratio divided by square-root price-change ratio of 1.000. This does not identify individual LP deposits. It reinforces the need to distinguish exit capacity from an independent demand signal; raw liquidity growth should not be counted as a second vote for the same price movement.

A separate external-paper audit reproduced its **+117.73% sum of trade percentages** and +0.038735 SOL size-weighted paper P&L from 190 published rows [S18]. Applying a hypothetical 14% account allocation to every reported return gives **$50 → $53.34** before further costs; removing the best three gives a 0.8504× account multiple. There are 57 overlapping reported position intervals, so this algebra does not replicate our single-position policy. The public rows do not supply a complete fee/fill/account ledger. This is a benchmark-interpretation correction, not an accusation against the author or evidence that SLR works.

Public unauthenticated Alpaca historical **bar** access was verified for DOGE, BONK, WIF and PEPE on September 30, 2026; source data and the original request-time caveat are retained [S19]. This provides another affordable comparison source for listed assets. It does not establish access to arbitrary new tokens or executable historical swap quotes.

The kit now includes the compact historical input, attribution/license/provenance, a frozen challenger specification, chronological replay, contemporaneous matched controls, paired comparisons, the published-return auditor and **35 passing engineering checks**. No live orders or paid streams were used. The highest-value next increment is buyer-provenance and social-evidence enrichment, followed by a genuinely new forward period.

- **S17:** Arati Uday Kamat, [RED-REJECT-2026-v2 corrected release v2.3](https://zenodo.org/records/22967373), September 25, 2026. CC-BY-4.0; source attribution retained in the kit.
- **S18:** Arati Uday Kamat, [Hour-Aware trading-study companion v1.3](https://zenodo.org/records/23017853), September 28, 2026. Paper returns audited as external data, not adopted as our strategy.
- **S19:** [Alpaca-py market-data documentation](https://alpaca.markets/sdks/python/market_data.html), official unauthenticated crypto-data guidance, checked October 11–12, 2026.

## PumpSwap size-specific capacity result

The read-only quote adapter now covers canonical SOL-paired PumpSwap pools. It uses the official SDK's live fee-tier arithmetic, effective quote reserve (`quote vault + virtual quote reserves`) and current fee buckets rather than inferring capacity from reported USD liquidity [S20–S22]. It verifies the PumpSwap program owner, exact base mint and canonical creator derivation before classifying a result. Every state request, response, slot and UTC receipt time is retained.

The final bounded pass at **2026-10-12 01:31:47 UTC** revisited the five PumpSwap pools in the frozen six-token pool-age/liquidity prefilter. All five assembled current processed state in 326 ms, stayed within the five-second exact-pair market-reference bound, and passed the 6% same-state roundtrip ceiling. Under the existing $7 cost convention, estimated recoverable value was $6.6065–$6.7111; route-only immediate roundtrip retention was 97.556%–99.097%. The first three attempts were rejected because complete state assembly took 2.97–3.13 seconds, above the frozen two-second rule. They remain in the evidence bundle.

This resolves a tooling dependency rather than a strategy test. The observations were about 55 minutes after discovery, no historical entry quote exists, and none has complete attention, buyer-cluster, custody, token-safety or 60-second confirmation evidence. `CAPACITY_PASS_ONLY` never becomes a paper fill. The single Raydium prefilter candidate, partial-exit quotes, transaction simulation/failure rates, priority fees and account-creation funding still need coverage. SLR-0.2 and its hash are unchanged.

- **S20:** [PumpSwap program documentation](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_SWAP_README.md), official pool layout, effective-reserve and SDK guidance, checked October 12, 2026.
- **S21:** [Pump fee-program documentation](https://github.com/pump-fun/pump-public-docs/blob/main/docs/FEE_PROGRAM_README.md) and [current fee schedule](https://pump.fun/docs/fees), official dynamic fee logic and published tiers, checked October 12, 2026.
- **S22:** [Solana `getMultipleAccounts`](https://solana.com/docs/rpc/http/getmultipleaccounts), official read-only RPC semantics. The adapter pins `@pump-fun/pump-swap-sdk` 2.1.0 with the registry integrity hash in `package-lock.json`.

## Buyer evidence and order-book challenger

Order-book knowledge adds a testable execution and supply-demand layer. On **Alpaca**, public bid/ask books and signed taker trades are accessible for DOGE/USD, BONK/USD, WIF/USD and PEPE/USD [S23]. On **PumpSwap**, the corresponding observable structure is the AMM curve plus actual wallet swap events; there is no native queue of resting orders to read. Curve depth is determined by already-observed reserves and cannot be counted as independent buyer evidence. Raydium routes need their pool type and initialized liquidity checked separately.

OB-0.1 was frozen at 2026-10-12 01:41:09 UTC before a 12-minute public development capture. It requires three distinct updates showing at least 60% nearby bid-notional share, positive sampled best-level OFI, at least $50 completed signed buys and 60% buy-side share in the previous minute, at most a 100-bps spread, enough nearby exit depth and a source age no greater than two seconds. It enters using a later observed fresh book, charges taker fees on the credited asset and tracks missing exits explicitly. The OFI mechanism has prior art in stock-market research [S24]; it is not established for our meme-coin campaign.

The capture returned **288 pair snapshots from 72 polls**, but only **111 distinct source updates** and **38 source-age-qualified snapshots**. It returned one signed DOGE sell and no signed buys in this bounded frame. Full book-plus-flow and persistent book-only rules generated no opportunities. The momentum control attempted one modeled $7 BONK entry, then lacked a fresh exit during the allowed window; it remains $43 conditional cash plus unresolved modeled inventory, rather than an invented stop fill or realized loss. No primary trigger existed for a paired random control, and the attention control lacked social data. This is not a completed campaign or an estimate of strategy superiority.

A useful falsification of naïve measurement is the discrepancy between nearby and all-level depth. BONK's median all-level bid share was **7.68%**, while within 100 bps of the midpoint it was **49.64%**; PEPE was **2.35% versus 50.04%**. Remote ask levels can make a balanced local market appear dominated by sellers. At $7, median modeled immediate roundtrip costs were 1.32% for DOGE, 1.85% for BONK, 1.32% for WIF and 1.47% for PEPE, including spread, the published 0.25% taker fee per side and an explicitly assumed 0.25% adverse allowance per side. Old source timestamps can reflect an unchanged latest book; they fail this conservative experiment's rule without proving a provider fault.

Buyer analysis used finalized transactions for the fixed PumpSwap pool `Fe7bpDYCs74GqiCUF14HwgUMToPKV1d9mDYVX5BTohFr`, mint `2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM`, and exact WSOL quote. The first 12 of 30 newest pool-referencing signatures contained **five buy and two sell events**, with five buy-event users. One user contributed **87.33% of decoded buy notional**. The remaining referenced transactions did not contain matching PumpSwap swap events; referencing the pool does not mean trading it [S25]. This subset is not complete flow, and event users are not identified independent people.

Seven of those transaction bodies used Solana v1. The original v0-only fetch errors were preserved and recovered by requesting `maxSupportedTransactionVersion: 1`, as required by current official guidance [S26]. Bounded pages establish at least ten earlier successful transactions for each buy user, but do not establish the required fourteen-day maturity, three other mints, new-to-mint status or independent funding roots. Those remain unknown. Log-only event extraction also needs CPI-event support and completeness auditing [S27]. Later wallet profiles are not inserted into past decisions.

**Current decision:** retain SLR-0.2 as an unvalidated hypothesis, keep OB-0.1 as a separate unpromoted challenger, and use nearby execution capacity as a rejection check. The next ablation must ask whether persistent depth and signed flow improve buyer-confirmed candidates after costs in a later untouched period. Whole-account net outcomes, opportunity frequency, standdowns, missing exits, state eligibility, funding/conversion costs and all controls must still be measured. No trade, maker queue fill, reliable doubling or universal novelty is claimed. The kit contains the complete bounded experiment and 49 engineering checks.

- **S23:** [Alpaca real-time crypto schemas](https://docs.alpaca.markets/us/docs/real-time-crypto-pricing-data) and [latest book API](https://docs.alpaca.markets/us/reference/cryptolatestorderbooks-1), checked October 12, 2026.
- **S24:** Cont, Kukanov and Stoikov, [The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402), stock-market order-flow prior art.
- **S25:** [Solana signatures](https://solana.com/docs/rpc/http/getsignaturesforaddress) and [transaction reads](https://solana.com/docs/rpc/http/gettransaction), checked October 12, 2026.
- **S26:** [Solana versioned transactions and v1 read compatibility](https://solana.com/docs/core/transactions/versioned-transactions), checked October 12, 2026.
- **S27:** [Solana Anchor events](https://solana.com/docs/programs/anchor-events) and [Anchor event decoding](https://www.anchor-lang.com/docs/features/events), successful transaction, program provenance and CPI guidance, checked October 12, 2026.

## Buyer-quality refinement and signed-flow falsification

The buyer enrichment adapter now supports both successful log and CPI events, checks the CPI event tag and exact PumpSwap program, deduplicates equivalent representations, and reconciles the exact event token account to its mint and owner [S27]. The same fixed twelve transactions contain seven swaps in both representations; counting each representation separately would double notional. No extra observation is introduced by this re-audit.

The five buyers' notional HHI is 0.76927, equivalent to **1.29993 equally sized buyers**. This describes quote-notional concentration rather than independent human ownership. It supports testing economically meaningful diversification as a later ablation, while leaving SLR-0.2 unchanged. The new history pass establishes fourteen-day earlier activity for **two of five** users. The other three remain unknown under a five-page bound. Other-mint balance evidence is present for all five, but it does not establish trades in three other mints. Four inspected incoming native transfers range from one to 6,238 lamports; none proves initial funding or an independent cluster. Post-event profile receipt times prevent retrospective eligibility promotion.

A separate challenger, **FLOW-0.2**, tests completed buy-side flow without the audience-change thesis. It requires at least $50 signed buys and 60% buy-side notional in one minute, cost-qualified top quotes, a later entry and one-hour liquidation attempt. The configuration was frozen before quote outcome analysis; FLOW-0.1 and its hash are retained. Version 0.2 clarifies the assumed two-second historical publication allowance and a maximum two seconds after that assumed availability. Actual historical arrival times are unavailable.

Complete public Alpaca data supplied **93 signed trades** and **249,457 quote rows**, including 6,336 overlaps across daily requests [S28]. October 9 is the development day; October 10 is a later chronological comparison. Development signals whose exits could enter the later day are purged. These are daily partial account illustrations, not completed thirty-day or forward campaigns.

All three closed development **quote paths** rose at their midpoint prices, yet lost money after crossing the ask/bid, the published 0.25% taker fee on credited assets and a separately assumed 0.25% adverse allowance per side: **−1.2541%, −1.5927%, −0.6450%** net. The conditional $50 account ends **$49.75595**. A rejected missing entry quote does not consume an actual-entry quota; the earlier implementation output is archived. The later day's DOGE entry lacks a quote within its bounded exit window and remains $43 conditional cash plus unresolved modeled $7 inventory. No forced loss, unsellability or recovered cash is inferred.

Matched random and momentum peers were unavailable under the frozen contemporaneous eligibility gates, so no paired superiority comparison exists. Social attention evidence remains absent. The replay assumes funded USD, zero funding/conversion cost and no additional broker charge; exact order increments, US-state/account eligibility, order acceptance, full depth and fills are still unverified. Current fee schedules were checked again [S05, S08] but exact historical charges are not proven.

**Decision:** do not promote simple signed-buy dominance from this test. Correct direction and a positive midpoint chart are insufficient when the move fails to pay its costs. Continue pursuing audience conversion, buyer quality and persistent nearby capacity, with later independent account-level comparisons. No reliable doubling, actual trade or maker queue fill is established. The kit contains the full evidence and **64 engineering checks**.

The newly located MemeTrans/MELT project is a cited risk-research lead. Its repository requires separate permission for commercial use under CC BY-NC 4.0; its dataset, feature pickle, code and predictions were not adopted [S29]. Original public-chain and Alpaca evidence remain available for continuing this project.

- **S28:** [Alpaca historical quotes](https://docs.alpaca.markets/us/reference/cryptoquotes-1) and [historical signed trades](https://docs.alpaca.markets/us/reference/cryptotrades-1), complete public-page retrieval with UTC receipts, checked October 12, 2026.
- **S29:** [MemeTrans/MELT paper](https://arxiv.org/abs/2602.13480) and [MELT repository/licence](https://github.com/git-disl/MELT), researched October 12, 2026; not imported or used as a strategy return dataset.

## Strict account audit and offline campaign controller

The October 12, 2026 UTC increment supplies `SLR-CONTROLLER-0.1`, a deterministic controller of paper receipt events. It times two full checks at least sixty seconds apart and requires refreshed dynamic inputs, rather than accepting an asserted confirmation flag. It checks one-position sizing and actual reserves, rolling/daily limits, same-mint cooldown, USD-basis cost accruals and rent locks/refunds, size-specific capital recovery, a runner, retries and calendar limits. Detailed input contracts and exceptions are in `Campaign_Controller.md`; interpretations and implementation hashes are in `campaign_preregistration.json`.

A quote produces an **exit request**, never a cash recovery. The initial attempt plus two failed retries leaves unresolved inventory and prevents entry. The six-hour rule supersedes an unfilled recovery intent. Missing ninety-minute valuation asks for a fresh quote; missing observations do not become a pretend stop. Overdue inventory is recorded at its actual later receipt. Local calendar days preserve Chicago wall time across DST, so the synthetic October 12 00:00 UTC timer example has 721 elapsed hours to its November 11 01:00 UTC deadline. This is not an observed thirty-day campaign.

Two synthetic adversarial cases falsified measurement in the old auditor. Binary floating arithmetic incorrectly labelled **12 of 99 exact-$100 cent-cost examples** as strictly above $100. A `1e-9` closing tolerance could erase a `0.000000001` token remainder and report a flat account. Decimal amounts and exact-zero closure now reject those false successes; failing inputs/output and old code are preserved. No genuine past SLR outcome changed, since no complete positions or campaigns had existed. The auditor remains a simplified net-fill ledger, with full lifecycle checks delegated to the controller.

Target verification requires flat inventory, no pending action or unpaid fee, exact reconciled recoverable cash strictly above $100 before the calendar deadline, and complete externally evidenced costs, funding and conversion. Locked rent is excluded until a verified refund. A later discovered expense revokes provisional success while entry remains stopped. These assertions are adapter inputs, not independently authenticated guarantees. Broker token-denominated fees need quantity reservation and actual activity reconciliation, while live SOL/rent FX, order increments, route acceptance, globally minimum partial-sale quantity, failure simulation and conversion/withdrawal evidence remain unconnected.

Fresh documentation received **2026-10-12 03:01:36.889 UTC** reaffirms the existing PumpPortal and Alpaca schedules [S05, S08]. Alpaca's page says fee activity can be posted at day end: no same-day activity does not establish zero cost. Solana documents refundable account storage balances [S30] and fees charged even for failed transactions [S31]. The controller requires explicit amounts and cost identities; no fee, rent, FX rate, failure rate or paid data charge was invented.

The existing **66 incomplete candidate records** still reject in a chronological controller replay. This is reuse of the prior sample, not sixty-six new opportunities. The conditional unspent budget is $50, without verified funding/conversion recovery. No new market capture, daily opportunity-rate estimate, forward campaign, observed calendar timeout or doubling was added. Random has no qualified SLR trigger to match, social attention remains missing, and earlier momentum/FLOW/OB results remain separately labelled. No matched net-account comparison can be reported.

The suite has **100 passing engineering checks**. Synthetic entries, large credit fixtures and future-dated timer events test accounting boundaries; none is an investment observation. SLR-0.2 and its investment-rule hash are unchanged and remain unvalidated. The next priority is verified other-mint swap history and funding ancestry, followed by social/quote integration and a later untouched buyer-plus-book comparison. Compare simpler full liquidation against a runner only when eligible complete net paths exist, with the same account constraints and all costs for controls.

- **S30:** [Solana accounts and refundable storage balance](https://solana.com/docs/core/accounts), checked October 12, 2026.
- **S31:** [Solana fee structure, including failed transactions](https://solana.com/docs/core/fees/fee-structure), checked October 12, 2026.

## Verified prior swaps and proposed model layer

Forty further finalized public transaction reads, received **2026-10-12 05:45:26.905815–05:49:22.619986 UTC**, extend the same fixed five-user history sample. Selection was frozen as evenly spaced chronological ranks among uninspected pre-target signatures, without using subsequent trade outcomes. Combined with twenty saved bodies, the audit verifies **thirteen deduplicated prior PumpSwap swaps** with exact base mint/account/owner, transaction signer and successful finalized event proof [S38]. Other venues and proxy users remain unknown; inner-failure cases require rollback alignment before counting.

Two users have verified swaps in at least three other mints; only one also has verified fourteen-day activity. Lower bounds are 3, 1, 1, 2 and 4 other mints for the five sorted users. The evidence establishes activity, not profitable judgment, independent funding or first-ever target participation. New profiles cannot be inserted into past decisions. No complete SLR entry, costed account path, matched comparison or doubled campaign was added.

The proposed numerical model layer starts with rule/logistic baselines, **CatBoost** and a simple **competing-risk survival model** [S32, S33]. Model targets are net recoverable payoff distributions and exit-event timing under a fixed policy, with missing routes and censored observations preserved. This is a recommendation to test, not evidence these models beat an LLM or our controls on memecoin returns. `ENTRY-MODEL-0.1` specifies future entry ablations and chronological evaluation; SLR-0.2 and its hash are unchanged. No model was installed or trained.

TabPFN v2 is a possible small-data comparator [S34, S37], with TCN and temporal graph approaches later as sequence and funding-relationship evidence improves [S35, S36]. The current TabPFN defaults have noncommercial weight terms, while v2 offers an attribution-based path. No paid/hosted inference or weight download occurred. LLMs remain useful for collecting, reviewing and building the system; a prediction score never replaces mandatory evidence and execution gates.

`Models_and_Entry_Window_Research.md` contains the detailed source/model matrix, all user identities, limitations and reproduction instructions. The kit now has **107 distinct engineering checks**; an interim duplicate-discovery count was corrected and retained. No benchmark paper, synthetic fixture or public wallet count is presented as a reliable doubling result.

The preferred complete Mac project copy is `~/Projects/CodexCoinHunt`; this session lacks that filesystem mount. The `CodexCoinHunt.zip` export and installer include detailed Codex/Claude handoff notes, while clearly marking Claude's unshared work as unreviewed. Northstar's separate five-minute prediction-error evaluation remains separate from this account-growth research.

- **S32:** [CatBoost, NeurIPS 2018](https://proceedings.neurips.cc/paper_files/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html).
- **S33:** [DeepHit competing-risk survival analysis, AAAI 2018](https://aaai.org/papers/11842-deephit-a-deep-learning-approach-to-survival-analysis-with-competing-risks/).
- **S34:** [TabPFN small-data study, Nature, January 8, 2025](https://www.nature.com/articles/s41586-024-08328-6).
- **S35:** [Temporal convolutional sequence modeling, 2018](https://arxiv.org/abs/1803.01271).
- **S36:** [Temporal Graph Networks, 2020](https://arxiv.org/abs/2006.10637).
- **S37:** [TabPFN implementation and weight terms](https://github.com/PriorLabs/TabPFN), checked October 12, 2026.
- **S38:** [Official PumpSwap IDL](https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump_amm.json), captured with content hash and UTC receipt October 12, 2026.

## Desktop continuity

The user requests continuation from the Mac after this bounded increment. `Mac_Desktop_Handoff.md` and the complete `CodexCoinHunt.zip` package preserve the available research context, source files, evidence, failed alternatives and prior versions. The copy installer verifies file hashes and has nine separate preservation/integrity checks. These checks are not investment observations. It defaults to the requested Mac project folder, manages `codex-research/current` and preserves earlier snapshots and unrelated Claude files.

OpenAI's official documentation, received **2026-10-12 06:13:27.735 UTC**, distinguishes cross-device conversation history from local-folder access [S39]. Open the conversation under the same account/workspace and attach the installed folder to a new local task. This cloud session has not installed the Mac copy or reviewed actual Claude chats, code or backtests. The written handoff records the project, while the original chat remains the source for verbatim conversation history.

- **S39:** [Projects and local folders](https://learn.chatgpt.com/docs/projects?surface=app), [cross-device troubleshooting](https://learn.chatgpt.com/docs/reference/troubleshooting) and [desktop history changes](https://learn.chatgpt.com/docs/whats-new), checked October 12, 2026.
