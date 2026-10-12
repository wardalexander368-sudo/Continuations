# Quote assets, routed capital and event versus account movement

October 12, 2026 UTC. Investment rules remain SLR-0.2, SHA-256 `9bcd83ce0ec71cdae8c410c202bd5a75b1496679e5ddb94ccc7d300e57c3663f`. No validated strategy entry, closed position, matched account payoff or doubling campaign is added.

## Main findings

The same five recorded buy transactions contain three **USDC/USDT disposals with routed WSOL**, one **other-mint disposal with routed WSOL**, and one **native-SOL input into the user's quote account**. This distinguishes asset movement from initial funding. Cash-like tokens can already be owned; spending them is not demonstrated fresh fiat. Other-token disposal is not proved profitable rotation. These are transaction-level observations and mechanisms to compare, not return labels.

Two buyers share both a fee payer and an incoming WSOL source account. The source token account is held by an authority whose current state is program-owned data; this is a routing intermediary, not an identified independent investor. Both buyers dispose of their own USDC in their original transaction. Shared route/payer roles do not certify common human ownership. The classification preserves unknown ultimate funding and zero verified independent clusters.

Event-reported quote amounts differ from verified quote-token transfer totals in **two of five buys**. The two larger totals are approximately **0.45% above the respective event amounts**. That observation falsifies using the event amount alone as complete quote outflow in these cases. It does not identify a particular fee recipient or prove that the event is invalid: event semantics, whole-account transfers and total economic cost are distinct measurements. Network fees, tips, storage deposits/refunds, intermediary conversions and off-ramp costs remain separate.

| Exact event user | Input-asset observation | Event quote, SOL units | Verified quote-account token outflow, SOL units | Difference, SOL units |
| --- | --- | ---: | ---: | ---: |
| `8i8WsSj27j998Z7fqjw4JLeBBo7FkAPfqoNKEhYzXttG` | 1,000 USDT disposed; routed WSOL | 8.918346999 | 8.958479563 | 0.040132564 |
| `3uzy6vZMwwgHRrbe86YYFKZj2XaQjWXijqcnV3T6dej4` | Native SOL supplies transient quote account | 0.742906918 | 0.746250000 | 0.003343082 |
| `6KBtrzj3Rxew41MD5ydL3AiB7WwTjLtFUKsSEf9yaJfD` | 3,641.394595 units of `J8PSdNP3QewKq2Z1JJJFDMaqF7KcaiJhR7gbr5KZpump` disposed | 0.221683792 | 0.221683792 | 0 |
| `FXh9XcdM38anfSjMjqvPsj7zk2ttzJbwtDCzDhR6YHcn` | 5 USDC disposed; shared payer/source | 0.044028572 | 0.044028572 | 0 |
| `CSx2gDhH9nw6vqknJkrHVCaWWDDr6sLbRvtJkiUieRFZ` | 32.360835 USDC disposed; shared payer/source | 0.284892244 | 0.284892244 | 0 |

All five have a positive exact-target net token balance change. That is retained inventory in the transaction, not verified independent demand or recoverable USD. Whole-account outflow counts token transfers from the exact quote account; account closure and native storage reserve are not token transfer expenses. No token unit is automatically valued at one USD or an executable SOL conversion price.

Exact target pool: `Fe7bpDYCs74GqiCUF14HwgUMToPKV1d9mDYVX5BTohFr`. Exact target mint: `2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM`. Quote mint: legacy-token WSOL `So11111111111111111111111111111111111111112`.

## Raw evidence, scope and clocks

`QUOTE-PROVENANCE-0.1` was frozen **2026-10-12 08:22:27.696862 UTC** for the same original five buys and their observed quote-source leads. No new trade outcome or chart return selected them. Original successful finalized bodies are reused. One fresh finalized `getMultipleAccounts` response for six source/authority addresses arrived **08:23:45.524501 UTC**, context slot **455979513**. All six decoded. This is current-at-receipt state, never original decision-time state.

Three source token accounts have exact WSOL identity. Their token authorities are currently owned by programs `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`, `TessVdML9pBGgG9yGks7o4HewRaXVAMuoVj4x83GLQH` and `goonuddtQRrWqqn5nFyczVKaie28f3kDkHWkHtURSLE`. The latter two are retained as exact IDs; no vendor identity or custody certification is adopted from third-party labels. Token-program ownership, token authority, router, payer and beneficial ownership remain distinct. PumpSwap pool fields require its exact account discriminator; generic program data is not decoded as a pool.

Shared source account: `5pVN5XZB8cYBjNLFrsBCPWkCQBan5K5Mq2dWGzwPgGJV`; token authority: `8ekCy2jHHUbW2yeNGFWYJT9Hm9FW7SvZcZK66dSZCDiF`. Shared transaction payer: `AgmLJBMDCqWynYnQiPCuj9ewsNNsBJXyzoUhD9LJzN51`. Unknown ownership remains unknown; these addresses do not verify a common person or initial funder.

A separately frozen check at **08:26:34.933722 UTC** selected eight closest uninspected prior-day signatures for the one buyer still without demonstrated earlier target participation, `CSx…eRFZ`, including failed signatures. Eight finalized responses arrived **08:26:46.566006–08:27:59.086134 UTC**: six successful bodies, two failed transactions, zero missing-body response errors. No earlier canonical target swap is established in these eight. First participation remains **unknown**, not newly verified. Four returning buyers remain demonstrated by the prior audit. Bounded successful reads and missing earlier events are not new market opportunities; failures are not trades.

Total new public reads: **nine**, including the single six-account response. Raw request/response objects and UTC clocks are in `data/quote_provenance_20261012/rpc.jsonl` and `participation_rpc.jsonl`. This pass is a bounded audit, not a continuous feed. Current source roles and later receipt times cannot be backdated into eligibility.

## What is implemented

`quote_asset_provenance.py` requires an exact successful finalized target buy, signing event user and matching quote mint/owner. It recovers transient token identity from initialization, checks exact Token Program/mint/decimals, keeps raw integer quantities, and interleaves outer/CPI instructions. Missing stack heights leave ancestry unknown. An unparsed quote-account instruction prevents a complete outflow comparison. Account ownership and transfer authority remain separate; a delegate need not be the token owner.

Owned asset changes aggregate all of a user's accounts in the exact mint, so internal account reshuffling does not masquerade as asset disposal. Conflicting decimals and unsupported identities stay unknown. Generic current token multisig data is not decoded as a token account. All records keep first funding, independent ownership, USD returns and full cost reconciliation unverified.

`audit_quote_participation.py` reproduces the additional eight-body check offline and rejects responses outside its frozen selection. `collect_quote_provenance.py` is a bounded read-only collector and refuses to overwrite existing evidence. Fifteen new adversarial checks cover transfer precision, roles, missing parsing, program identity, execution order and custody. The full suite has **137 distinct engineering checks**. Prior 122/135 outputs and previous reports remain preserved; no fixture demonstrates profitability.

## Alternative mechanisms and future evaluation

The broad “returning capital” story is refined into cash-asset spending, other-mint disposal, native-SOL input and unclassified origins. Three of these sampled buys use USDC/USDT, so they should not all be described as rotation out of another meme coin. A service route can serve independent users; an existing cash balance can be deployed without a new native SOL deposit. Ultimate capital provenance is still missing.

`CAPITAL-ORIGIN-ABLATION-0.1`, frozen **08:38:45.057240 UTC**, proposes comparing these origins in a later untouched period while preserving all SLR audience, first-participation, maturity, independence, safety, US eligibility, executable quote, cost, confirmation and campaign gates. Keep the earlier new-versus-returning buyer comparison. Compare the same $50 net-account controller and exit policy with eligible matched random, attention and momentum controls; count idle days, rejected attempts, unresolved/unsellable exits and calendar timeouts. Neither cash-origin nor rotation is promoted as a profitable strategy.

No matched net-account result, opportunity-frequency estimate, completed calendar campaign or observed doubling is available. The original sample and these retrospective enrichments remain development evidence. Account costs, FX, quote freshness, funding and conversion recovery, social coverage and full buyer windows are still missing. No model is trained, no win rate assumed and no chart peak booked.

## Sources, fees and US coverage

Issuer sources verify the exact mainnet USDC and USDT mints [S43, S44]. Solana documents that a WSOL token balance and its native lamports are different fields, with native syncing required [S42]. Token instructions and fee sponsorship distinguish sender/owner from transaction payer [S42]. These facts support role checks; they do not certify this user's venue eligibility or a redemption value.

PumpPortal Local/Lightning fees remain **0.5%/1%**, before slippage, excluding network/bonding-curve costs. Alpaca tier-one maker/taker remain **0.15%/0.25%**, charged on the credited asset, with possible day-end fee activity. These primary pages and Alpaca asset/account restrictions were refreshed October 12, 2026. No actual historical fee charge is inferred from today's schedule; no service fee is identified solely from the observed 0.45% differences. The target mint is not mapped to an Alpaca tradable pair; no order acceptance, state/account authorization or off-ramp recovery is inferred. No payment, subscription, wallet funding, private key or order API operation occurred.

## Reproduce

Use Python 3.10 or newer, from the expanded kit, with new output directories:

```bash
python3 quote_asset_provenance.py --data data/quote_provenance_20261012 --output results/quote_route_reaudit
python3 audit_quote_participation.py --data data/quote_provenance_20261012 --output results/quote_participation_reaudit
python3 -m unittest discover -s tests -v
```

Read `results/quote_provenance_final_20261012` and `results/quote_participation_reproduced_20261012` as canonical outputs. Original provisional quote output remains saved. Source references/UTC receipts retain official links; full webpage prose is not republished. Raw chain data remain verbatim.

Next trace the original owned input accounts for still-eligible later candidates, preserve service exclusions without asserting independence, and obtain complete attention/buyer/quote windows. Use exact net fill and cost evidence for money accounting, with event amounts as explicitly named diagnostics.

- S42: [Solana WSOL syncing](https://solana.com/docs/tokens/basics/sync-native), [token transfers](https://solana.com/docs/tokens/basics/transfer-tokens) and [fee sponsorship](https://solana.com/docs/payments/send-payments/payment-processing/fee-abstraction).
- S43: [Circle native USDC mints](https://help.circle.com/support/en/usdc-supported-blockchains-minting-redemption-faqs?id=kb_article_view&sysparm_article=KB0010590).
- S44: [Tether supported protocols and mainnet mint](https://tether.to/en/supported-protocols/).
- S05/S08: [PumpPortal fees](https://pumpportal.fun/fees/) and [Alpaca fees](https://docs.alpaca.markets/us/docs/crypto-fees).
