# Returning buyers, capital provenance and first participation

Research increment completed October 12, 2026 UTC. SLR-0.2 remains unchanged, SHA-256 `9bcd83ce0ec71cdae8c410c202bd5a75b1496679e5ddb94ccc7d300e57c3663f`. No validated entry, closed strategy position, recoverable account result or doubled campaign was added.

## Finding that changes the interpretation

Four of the five fixed sample buyers had already made an authorized successful trade in the **same exact mint** before the original sampled purchase. All four have an earlier verified buy, not merely a token balance. They supplied **97.2101822278%** of the original subset's buy quote notional. The largest buyer, supplying 87.33%, made four earlier buys and one sell in the audited prior-day window. The only user previously verified to satisfy both fourteen-day activity and three other mints also has an earlier target-mint buy.

This falsifies interpreting this five-wallet subset as new-buyer conversion. It does not falsify every possible Second-Look Relay opportunity or prove manipulation. It also does not estimate a market-wide proportion: this is the same selected development cohort and an incomplete original trade-flow window. The remaining user's history is sampled, with first participation **unknown**. Zero users in this cohort now have verified maturity, other-mint trading and first-time target participation together.

| Exact event user | Prior verified target buys / sells | First participation at original event | Selected signatures | Original share implication |
| --- | ---: | --- | ---: | --- |
| `3uzy6vZMwwgHRrbe86YYFKZj2XaQjWXijqcnV3T6dej4` | 1 / 0 | Falsified | 8 of 42 reported prior-day references | Returning buyer |
| `6KBtrzj3Rxew41MD5ydL3AiB7WwTjLtFUKsSEf9yaJfD` | 2 / 1 | Falsified | 8 of 72 | Returning buyer |
| `8i8WsSj27j998Z7fqjw4JLeBBo7FkAPfqoNKEhYzXttG` | 4 / 1 | Falsified | All 15 reported references | Largest observed buyer is returning |
| `CSx2gDhH9nw6vqknJkrHVCaWWDDr6sLbRvtJkiUieRFZ` | 0 / 0 observed | Unknown | 8 of 141 | Remaining 2.7898177722% is not verified new demand |
| `FXh9XcdM38anfSjMjqvPsj7zk2ttzJbwtDCzDhR6YHcn` | 4 / 1 | Falsified | 8 of 96 | Returning buyer |

Exact pool: `Fe7bpDYCs74GqiCUF14HwgUMToPKV1d9mDYVX5BTohFr`. Exact mint: `2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM`. Quote: WSOL `So11111111111111111111111111111111111111112`. The historical event's creator-fee role is `DRqWUscn7tCkNCjuSrAEqaT2crKgsoePcPxHV569uii7`; it is not certified as the mint-creation signer or a human identity.

## Frozen selection and receipts

`FUNDING-AUDIT-0.1` was frozen at **2026-10-12 06:55:38.343949 UTC**, before retrieving additional bodies. It selects all reported prior-24-hour references for the largest buyer, then eight evenly spaced chronological ranks per other buyer, including failed transactions. Original signature pages precede the start of each audited window. Public-provider pagination is a reported-window boundary, not a guarantee of complete archival history or all associated token-account references.

There are **47 selected wallet/signature pairs**. Seven saved bodies are reused; **40 further finalized read-only responses** arrived **06:56:38.402367–07:02:37.675636 UTC**, with zero response errors. Forty-six selected transactions succeeded and one failed. That failed historical transaction records a 9,000-lamport network fee; it is neither a buy nor a cost paid by our unfunded paper campaign. Fourteen deduplicated earlier target swaps—eleven buys and three sells—pass the exact program, pool, mint, owner, signer and strictly prior-time checks. Log/CPI copies count once.

New receipt times remain later than original decisions. The audit can disprove a retrospective first-entry claim, but it cannot create historical eligibility or a timely paper fill. No new token discovery or independent forward sample was collected.

## Funding and account-closure interpretation

The diagnostic threshold for a direct native receipt is frozen at the greater of **0.01 SOL or 5% of that user's sampled buy quote notional**. This is an audit materiality convention, not a revision of SLR investment parameters. All observed payment instructions remain in raw evidence regardless of threshold.

Four incoming System Program payments appear: one is below the threshold; three come from sources that are not transaction signers. No material signed external native receipt candidate is established. Program/PDA sources, tiny payments and unknown distinct addresses do not certify independent owners. Zero first-funding roots, independent clusters or service exclusions are verified. The pre-authorized bounded second-hop reads are not used because there is no qualifying first-hop candidate. The absence of a native payment does not establish that the wallet was never funded: carried-in SOL, WSOL, other token assets, longer history and other routes remain untraced.

Seventeen token-account closures credit sampled wallets. Fifteen are verified **wrapped-SOL releases** and two release other token storage balances. Some accounts are initialized and closed inside one transaction, so neither end-of-transaction token balance list contains them. Exact Token Program initialization instructions recover the transient mint/owner identity. The initial parser incorrectly described sixteen missing-identity closures as storage releases; that output/code is preserved, and the final audit corrects the labels. Unknown or conflicting identities now stay unknown.

Closing a token account returns its lamports; WSOL can be closed while retaining a token balance to reclaim underlying SOL [S40]. Such a token account is not a separate outside investor. The sender, fee payer, owner, close authority and creator-fee recipient are different roles. Pump creator-fee collection is permissionless, so observing a collector is not proof of creator ownership [S41]. This audit makes no identity accusation or independent-person certification.

## Challenge to the mechanism

The competing explanation is **returning traders deploying existing or recycled capital**, rather than newly converted audiences. These possibilities can generate similar buy counts and flow imbalance. An earlier authorized trade is decisive evidence against first-time entry; a positive balance alone could be unsolicited and does not prove an earlier buying decision. Bounded absence remains unknown.

`PARTICIPATION-ABLATION-0.1` freezes a future comparison at **2026-10-12 07:06:34.595598 UTC**: new-to-mint conversion versus explicitly labelled returning-buyer accumulation, with raw activity as an ablation. Keep the same remaining wallet provenance, US eligibility, safety, exact-size quote, confirmation and campaign rules. Use the same full net-account controller and exit policy, plus eligible contemporaneous matched random, attention and momentum controls. These arms are proposals, not trained models or promoted strategies. This inspected cohort supplies no payoff evaluation for the comparison.

Opportunity frequency, calendar timeouts, complete social/buyer windows, authentic fills, unsellability and conversion recovery remain missing. No matched net account comparison is available. Preserve standdowns, rejected inputs and unresolved exits rather than assigning imaginary returns. Prior FLOW and order-book losses/censoring remain separate evidence.

## Costs and US execution

Official fees were refreshed October 12, 2026: PumpPortal Local 0.5% and Lightning 1% before slippage, plus network/bonding-curve costs [S05]. Alpaca tier-one maker/taker fees remain 0.15%/0.25%, charged on the credited asset, with possible day-end activity posting [S08]. Public Alpaca documentation describes supported pairs and US-region/account restrictions; its asset API requires credentials. This exact Solana mint is not mapped to an Alpaca tradable asset, and no account/state authorization or executable order acceptance is inferred. Historical fees are not reconstructed from today's schedule. No money, private keys, paid subscription or order API was used.

## Reproduce and continue

From the expanded kit with Python 3.10 or newer:

```bash
python3 buyer_funding_audit.py --data data/buyer_funding_20261012 --output results/funding_reaudit_new_directory
python3 -m unittest discover -s tests -v
```

The final suite has **122 distinct research engineering checks**, including fifteen new provenance/participation checks. Synthetic checks are not investment observations. The prior 107-check release, the interim 120-check output and the initial closure classification are retained. Do not rerun `collect_buyer_funding.py` on its existing evidence directory; the saved plan and raw responses are sufficient for offline reproduction.

Priority changes: reject demonstrated returning buyers before costly independence enrichment; treat absence as unknown. Trace carried-in quote-token capital and known service/creation roles for still-eligible future candidates. Establish complete social and buyer windows and later exact-size quotes, then evaluate the preregistered participation/capacity comparison on genuinely later untouched account paths.

Evidence: `data/buyer_funding_20261012/plan.json`, `rpc.jsonl` and primary-source packets; `results/buyer_funding_reconciled_20261012/summary.json` and `transaction_audits.jsonl`; `participation_preregistration.json`; `versions/` and the initial audit outputs. UTC source receipts and full identities are retained.

- S40: [Official account closure and WSOL semantics](https://solana.com/docs/tokens/basics/close-account).
- S41: [Official creator-fee collection roles](https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/COLLECT_CREATOR_FEE.md).
- S25: [Signature references](https://solana.com/docs/rpc/http/getsignaturesforaddress) and [transaction reads](https://solana.com/docs/rpc/http/gettransaction).
- S05/S08: [PumpPortal fees](https://pumpportal.fun/fees/) and [Alpaca fees](https://docs.alpaca.markets/us/docs/crypto-fees).
