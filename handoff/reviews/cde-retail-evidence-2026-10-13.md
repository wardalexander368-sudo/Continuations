# CDE retail cost and $100 contract follow-up — 2026-10-13

The two smallest contracts in the saved eleven-root study still exceed the **$100 target notional** at the refreshed displayed asks: **AVAX $102.80** and **DOT $119.80**. This refresh covers only those two roots. Historical retail-fee statements have different dates and terms; later exchange-fee notice metadata also exists. **Current US CFM all-in fees remain unresolved.** No strategy, frozen assumption or trading implementation changes follow from this evidence.

Source base: Continuations `ed68abdcd9beab6083022246956d9a74a25f6d8f`. Four bounded unauthenticated public GETs completed between **13:49:08.377928 and 13:49:09.043650 UTC**. All returned HTTP 200; their original bytes and individual receipts are retained. This is a displayed-quote diagnostic, with no account request or order.

## Whole-contract sizing

| Root / product | Contract multiplier | Bid / ask | One contract at ask | Prior saved notional | Whole contracts at $100 | Ask boundary for one contract |
|---|---:|---:|---:|---:|---:|---:|
| AVAX / AVP-20DEC30-CDE | 10 AVAX | $10.27 / $10.28 | $102.80 | $102.30 | 0 | $10.00 |
| DOT / POP-20DEC30-CDE | 100 DOT | $1.196 / $1.198 | $119.80 | $114.40 | 0 | $1.00 |

Exposure is `ask × multiplier`; the sizing rule is `floor(100 / exposure)`. Initial collateral is a different quantity and cannot substitute for notional. Reaching the one-contract boundary from these asks would require a **2.7237354% AVAX** or **16.5275459% DOT** price decline. These are arithmetic boundaries, not forecasts or trading signals. No current result for the other nine roots is asserted. The prior rows belong to the earlier dated [contract study](https://github.com/wardalexander368-sudo/Continuations/blob/ed68abdcd9beab6083022246956d9a74a25f6d8f/handoff/reviews/cde-capit-economics-2026-10-13.md).

The reported book timestamps are **13:49:08.519251 UTC (AVAX)** and **13:49:07.505795 UTC (DOT)**. Local receipt completion minus reported book time is **0.212097 / 1.537855 seconds**; this uses unsynchronized local/server clocks and does not establish executable freshness. Midpoint half-spreads are **4.86618 / 8.35422 bp**, with hypothetical immediate ask-to-bid losses of **$0.10 / $0.20 per contract**, before all other costs. Displayed prices and raw size strings do not guarantee available quantity, fills, slippage or crash-hour liquidity.

## Retail-fee dating and applicability

| Official source | Dated observation | Applicability limit |
|---|---|---|
| [CFM introductory pricing](https://www.coinbase.com/blog/coinbase-advanced-now-offers-a-fee-upgrade-program-for-high-volume-traders), 2024-02-01 | 0.05% per contract per side; $0.20 minimum; relevant exchange/NFA charges included; subject to change | Historical introductory terms, not a verified current rate |
| [US perpetual-style launch](https://www.coinbase.com/blog/perpetual-futures-have-arrived-in-the-us), 2025-07-21 | BTC/ETH launch advertised rates as low as 0.02%, bundled exchange/clearing/NFA charges and a $0.15 per-contract minimum | Does not verify the current rate for all eleven roots, the $0.15 side/roundtrip basis or a complete billing equation |
| [CDE notice index](https://www.coinbase.com/derivatives/market-notices) | R2026-46: published Aug 3, effective Aug 17, fee-schedule modifications. R2026-59: published Sep 17, effective Oct 1, Rule 305 fees modifications | Search-index metadata only; attachments, changed amounts and study-root applicability were not acquired |

These observations explain the apparent 0.05%/0.02% conflict through their dates and terms. They do not supply a current cost floor. The saved January 26, 2026 exchange PDF remains a dated source; it is **not verified as the latest applicable schedule**. Later notice headlines do not establish that every study-root fee changed. The generic [Advanced VIP page](https://www.coinbase.com/advanced-vip) displayed another tier table but lacked adequate US CFM scope and dating; it is not substituted into the model. Bundled historical charges must be reconciled before adding exchange, clearing or NFA amounts separately, to avoid counting a charge twice.

Fee research used parsed official sources around **13:46–13:51 UTC**. Original web-tool HTTP bodies and per-request timestamps were unavailable. Three direct public HTML reads returned **403**; no current complete schedule or notice-attachment bytes were acquired. Source URLs, locators, paraphrases and failed-read receipts are retained with these acquisition limits. No account fee tier or private billing record was accessed.

## Units and coverage remain open

Both fresh products report outer `funding_rate = "-0.000012"`, `funding_interval = "3600s"`, and an empty nested perpetual rate. The bounded official-source search did not explicitly define these CDE Advanced Trade REST rate encodings or `L2Level.size` units. Hourly percentage economics in [US funding help](https://help.coinbase.com/en/derivatives/perpetual-style-futures/funding-rate) do not map those REST strings to percentage points versus fractions or to cash-posting frequency. Preserve outer/nested rates and raw sizes separately; no funding projection or capacity conversion follows. The current raw schema fetch failed; the earlier schema hash is not a fresh receipt.

Product expiry fields remain contradictory (`2030-12` name, `2089-12-30` expiry, `EXPIRING` type). No contract lifetime is inferred. Native FIX/SBE, Global/INTX, WebSocket or SDK types are not substituted for an explicit REST field mapping.

The latest checked public main paper ledger has **1,584 rows**, up seven from 1,577 with the old prefix unchanged; every new row is paper/shadow. The saved **13:30 UTC report** has no US open or closed trade and gate progress **0/3 days, 0/8 trades**. This does not establish complete broker/account fills or deployment state. The existing 21-coin Coinbase cache remains retrospective, ending exclusively October 10 UTC; it was not downloaded again. No new exact-mint buyer or continuous social coverage was acquired.

## Verification and next evidence

The unchanged Decimal analyzer has SHA256 `f6b672a60f07c7c4e200371737e5b9fa5fa948b3dcf1c51735fb4cfc056a80c1`. Its imported scope was restricted in memory to AVAX/DOT; no source/model bytes changed. An independent Fraction-based review passed **eight check groups**: four response hashes/byte counts and receipt consistency, product identities, sizing/boundaries, spread arithmetic, timestamp arithmetic, prior two-row comparison, analyzer provenance and limitation review. It did not rehash the older raw bodies or assess executable liquidity.

Before comparing CDE against Alpaca costs, obtain a dated applicable US CFM contract/tier schedule, explicit side/minimum treatment, billed-component reconciliation and official REST units. Prospective evidence still needs untouched paired chronological signals, executable quotes, fills, costs, funding cash postings and complete account controls. This is evidence qualification for the existing lane, **not a new strategy, novelty claim or profitability result**. Frozen registrations, owner books and workflows remain unchanged.

Companion files contain the quote analysis, independent review, fee/unit source records, four original public responses and receipts, and paper-ledger aggregate freshness. Validation and delivery hashes are recorded separately after packaging.
