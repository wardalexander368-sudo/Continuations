# CDE contract economics for CAPIT — 2026-10-13

The lower-cost Coinbase US futures path remains a measurement opportunity, not a demonstrated improvement to CAPIT. In this public snapshot, **none of the eleven study coins permits even one whole contract within the adopted $100 notional stake**. One contract represents $102.30–$823.95 of exposure. The eight coins in the existing Alpaca snapshot screen also all exceed $100; their smallest contract is DOT at $114.40. These are price-dependent observations, not permanent exclusions.

This review does not change the adopted Alpaca rule, registered strategy, live gate, bot book, collectors or schedules. The new analyzer is offline. No account data, credentials or orders were requested. The original 21-coin cache was reused; it was not downloaded again.

## What was measured

Twelve unauthenticated GETs captured one public futures product list and eleven top-of-book responses between **2026-10-13 02:02:05.144767 and 02:02:07.075976 UTC**. All returned HTTP 200. The product list returned 100 records and explicitly reported `has_next: false`; exactly one `20DEC30-CDE` product matched each fixed study root. Mapping uses `contract_root_unit`, as the existing collector does. The collector's IDs are correct; an earlier guessed `BTC-20DEC30-CDE` lookup was not evidence of a collector defect.

Every raw response is saved with its hash, byte count, request start/completion times and server Date. All twelve body hashes and byte counts were verified against their receipts. Book timestamps lagged receipt by at most **1.624175 seconds**. This was a short sequence of snapshots, not simultaneous market data or a CAPIT entry/exit cohort.

One-contract exposure is `best ask × contract_size`. Half-spread is `(ask − bid) / (ask + bid) × 10,000`. Margins below are the product metadata's published **long overnight fraction × one-contract ask exposure**, rounded here for readability; they are not account buying power or a sufficient collateral reserve.

| Root | Product ID | Coins per contract | One-contract ask exposure | Half-spread, bps | Published overnight margin diagnostic |
|---|---|---:|---:|---:|---:|
| BTC | BIP-20DEC30-CDE | 0.01 | $823.95 | 0.61 | $173.24 |
| ETH | ETP-20DEC30-CDE | 0.1 | $246.30 | 2.03 | $59.42 |
| SOL | SLP-20DEC30-CDE | 5 | $526.35 | 1.43 | $192.64 |
| XRP | XPP-20DEC30-CDE | 500 | $676.50 | 1.48 | $252.59 |
| DOGE | DOP-20DEC30-CDE | 5,000 | $413.95 | 3.62 | $215.31 |
| ADA | ADP-20DEC30-CDE | 1,000 | $232.50 | 4.30 | $65.39 |
| AVAX | AVP-20DEC30-CDE | 10 | $102.30 | 9.78 | $33.36 |
| LINK | LNP-20DEC30-CDE | 50 | $633.15 | 2.37 | $203.40 |
| LTC | LCP-20DEC30-CDE | 5 | $305.95 | 3.27 | $112.59 |
| BCH | BCP-20DEC30-CDE | 1 | $266.10 | 4.70 | $112.39 |
| DOT | POP-20DEC30-CDE | 100 | $114.40 | 8.75 | $50.55 |

At $100 notional the exact whole-contract floor is zero for every row. A BTC contract has about $82.46 of published intraday margin, but still exposes $823.95 to price changes and has a $173.24 published overnight margin diagnostic. Calling $100 of collateral a $100 trade would silently change the risk rule. Coinbase distinguishes notional from margin and requires whole contracts. [US futures introduction](https://help.coinbase.com/en/coinbase/derivatives/us-derivatives-intro), [margin documentation](https://help.coinbase.com/en/coinbase/derivatives/us-derivatives-leverage-margin).

The unweighted median half-spread across eleven quotes is 3.2696 bps. This describes visible prices in this snapshot. It does not establish fillable depth, the spread during a crash, paired entry/exit costs or total retail charges. For example, AVAX could fit a single contract within $100 only at an ask of $10.00 or less, before any other order restriction; DOT's corresponding price is $1.00. The analyzer does not simulate orders or select a different stake.

## Cost and evidence gaps

| Component | Current evidence | Treatment |
|---|---|---|
| Bid/ask prices and multiplier | Saved public book and metadata | Exact exposure and quoted crossing arithmetic only |
| Book quantity | Raw sizes returned; official schema does not specify their unit | Preserve `raw_size`; no contract or dollar capacity claim |
| Retail commission, exchange/clearing/regulatory charges | Exact account-specific all-in amount and bundling not verified | Unknown, not zero and not an assumed 0.02% |
| Funding for CAPIT's 24-hour hold | Point API values and an hourly economic funding mechanism | No carry projection; raw field scale/period is undocumented |
| Perpetual basis and execution delay | No matched CDE entry/exit cohort | Do not transfer spot returns directly to perps |
| Margin, liquidation and capital | Published long margin fractions only | No account reserve, liquidation or account-dollar profitability claim |

The official developer guide states an introductory **0.05%** US futures beta fee, but does not establish this account's current complete charges. Coinbase's account help separates commissions, NFA fees and funding. Neither a promotional fee nor an exchange fee component can be treated as a verified retail all-in rate. [US derivatives guide](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/guides/futures), [account and statement help](https://help.coinbase.com/en/coinbase/derivatives/us-derivatives-manage-account).

The economic funding payment is calculated hourly as a percentage of notional. The REST schema leaves `funding_rate` as an undescribed string, including both the outer futures field and nested perpetual field. The same schema does not specify the unit of book `size`. The analyzer preserves both funding locations and raw sizes with units marked unknown; it does not multiply a point funding value by 24. [CDE funding mechanism](https://help.coinbase.com/en/derivatives/perpetual-style-futures/funding-rate), [official API schema](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/advanced-trade-spec.yaml), [public book reference](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-book).

All eleven metadata records also combine ticker/expiry-name `2030-12` with `contract_expiry: 2089-12-30T16:00:00Z` and `contract_expiry_type: EXPIRING`. These conflicting representations are preserved. No contract life is inferred from the ticker or silently corrected.

## What would resolve the opportunity

The existing owner's CDE snapshots at CAPIT fills are useful starting observations. They currently preserve neither the multiplier nor the exchange book timestamp in each saved fill snapshot, use the strategy context time as `at`, and can precede risk acceptance/paper execution. Their half-spread median also excludes fees. This review supplies evidence to the owner rather than editing that claimed implementation.

For each eligible crash entry, pair the actual contract identity, multiplier, book timestamp, request completion and exposure with the later exit. Confirm quantity units before claiming capacity; reconcile billed charges once with their component/bundled meanings; and use actual funding cashflows over the held period. A 24-hour hold also needs the applicable overnight margin and a defined collateral/liquidation buffer. A changed whole-contract stake requires its own explicit risk policy.

For a long position, the useful cash-P&L comparison is contract quantity times multiplier times **exit fill price minus entry fill price**, less reconciled billed charges, net funding paid and other incremental costs. Bid/ask observations give a price-only crossing model before fills are known. Spread and price impact already appear in actual fill prices and must not be subtracted again. Spot backtest returns plus a cheaper fee assumption cannot answer that comparison. Account capital, losses and the $250 stop must then be judged in dollars under the proposed contract sizing.

Historical CAPIT remains a candidate: the previous episode analysis found positive excess over shifted entries, while every absolute-net interval crossed zero. This snapshot supplies no new profitability outcome or forward crash day.

## Replay and validation

The offline CLI accepts the saved list, a directory of `ROOT-book.json` files and optional request receipts:

```sh
python handoff/experiments/edge-hunt/cde_contract_economics.py \
  handoff/data/cde-capit-economics/2026-10-13/products.json \
  handoff/data/cde-capit-economics/2026-10-13 \
  --target-notional 100 \
  --products-receipt handoff/data/cde-capit-economics/2026-10-13/products.receipt.json
```

`analysis.json` contains exact Decimal arithmetic; `verification.json` links all response hashes. Missing/ambiguous product mappings, malformed data and invalid books produce explicit errors and a nonzero CLI exit. A provided book product ID must match; an absent ID remains unknown rather than independently attested. All eleven actual snapshot IDs were present and independently matched. `status: ok` means arithmetic succeeded, not that arbitrary inputs are authenticated, fresh or permission to order. Margin, missing observations and invalid inputs are never silently filled with zero.

Independent review checked all twelve response hashes and byte counts, all eleven identities and timestamps, and exact Fraction arithmetic for exposure, floors, spreads, crossing loss and margins. It reproduced a duplicate-JSON-key flaw in the new analyzer: a second multiplier could turn an $800 contract into an apparent $80 fit. The parser now rejects duplicate keys and nonstandard NaN/Infinity constants throughout inputs. The same reproduction now fails closed; none of the actual responses contained that defect. Regression tests cover this false-fit path and CLI error handling.

The full repository suite passed **356 tests, with 1 existing skip**, including 29 new analyzer cases, in 88.57 seconds on the unchanged main base `f599384b476d9cbded1b090bbce4d08347b61055`. Replay from the public saved inputs is byte-identical to `analysis.json` (SHA-256 `f5bcaeb42c69f326ffe859a4f893a63b70de2e949f827f9fe49d99adfed02914`). An initial fresh-environment collection failure was caused by missing existing optional test dependencies; those were installed before the successful full run. No private account fees, funds, margin adequacy, funding cashflows, crash-time fills or profitability were checked.
