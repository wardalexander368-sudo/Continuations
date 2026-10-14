# CDE source qualification follow-up - 2026-10-14

Two previously missing fee attachments are now acquired from the CFTC, with original PDF bytes and request receipts. They resolve the content of those notices, **not the current retail CFM bill**. A fresh REST schema retrieval still does not define funding-rate scaling or book-size units. Coinbase's printed funding example also contains a reproducible arithmetic inconsistency. The existing cost assumptions, frozen studies and strategy verdicts remain unchanged.

This is a bounded continuation of PR #14, `codex/cde-retail-evidence`, from `cb8006074b4a2c2bd85a206f8e32e28f5b8ca7a5`. It adds evidence to the [October 13 review](cde-retail-evidence-2026-10-13.md); the earlier report and receipts retain their original date. No account, order, quote refresh, backtest, collector or owner-book request was made for this follow-up.

## Fee attachments acquired

The [August filing](https://www.cftc.gov/filings/orgrules/rules08032613651.pdf), received August 3 and effective August 17, establishes US500 fees and changes block fees. Its shared table explicitly charges each contract on each side. **AVP and POP electronic fees are $0.10 for both non-professional and professional participants, $0.07 for market makers.** Their block fee changes from $0.05 to $0.01; block pricing is not substituted for ordinary electronic orders. Page 4's non-professional definition excludes fully automated order-generating systems. That condition does not establish this project's account classification; the two electronic columns are equal for these products. This is a dated exchange schedule, not proof of today's complete broker charge or the latest exhaustive schedule. [CFTC filing record](https://www.cftc.gov/IndustryOversight/IndustryFilings/TradingOrganizationRules/62316).

The [September Rule 305 filing](https://www.cftc.gov/filings/orgrules/rules09172627087.pdf), effective October 1, **deletes** the parenthetical limiting eligible participants to market makers or professional traders. The surviving clause concerns eligible participants' membership privileges under NFA Bylaw 1301 and says the exchange does not assess NFA fees. It does not specify a retail commission rate, prove this customer's eligibility, or establish that CFM's NFA line must be zero. Reading extracted text alone would incorrectly retain the deleted condition. [CFTC filing record](https://www.cftc.gov/IndustryOversight/IndustryFilings/TradingOrganizationRules/64179).

Both relevant table and redline pages were rendered and inspected. The old search-index headlines can now be replaced by verified attachment content for these two notices. Their acquisition does not settle later amendments, broker pass-through, minimums or volume-tier eligibility.

## Keep the billing layers separate

Coinbase's [US account guide](https://help.coinbase.com/en/coinbase/derivatives/us-derivatives-manage-account) identifies daily futures statements as the account's authoritative record. Confirmations contain contract quantities, product, price, commissions/fees and NFA entries; funding appears as individual cash lines. Its closing-balance equation includes realized trading PnL, commissions, NFA, funding and cash movements. This supports a future reconciliation specification, not a completed reconciliation: no private statement was accessed.

The [Coinbase app derivatives fee page](https://help.coinbase.com/en/coinbase/derivatives/derivatives-fees) explicitly excludes US futures and Coinbase Advanced and refers to Bermuda products. Its 0.25% perpetual fee cannot fill our US CFM cost field. The earlier 2024 introductory and 2025 launch rates remain historical advertising with different terms, not a current all-root fee equation.

Before a new cost comparison, retain effective date, exact product, customer category, broker/tier, route, per-fill/per-contract/per-side basis, minimum basis and component inclusion. Reconcile charges by economic component: an exchange or NFA amount already included in a bundled commission is not added again. An exchange-level non-assessment statement is not evidence that a broker's statement omits that component. Actual brokerage evidence must agree with the applicable terms; unknown components remain unknown.

## Funding example fails arithmetic verification

The [US examples page](https://help.coinbase.com/en/derivatives/perpetual-style-futures/examples) prints one contract, size 0.01 BTC, mark $100,000 and funding +0.010%, then reports a $1 debit. Interpreting the printed percentage normally:

`1 x 0.01 x 100,000 x (0.010 / 100) = $0.10`

The printed debit is ten times that result. Its $100,000-to-$101,000 price move also produces **$10**, not the page's $100 gain, at the stated contract size: `(101,000 - 100,000) x 0.01 x 1 = $10`. The printed inputs therefore imply **$9.90 before trading fees**, versus its reported $99. This diagnoses inconsistent inputs/output; it does not tell us which published input should change. It cannot determine REST encoding. An independent exact-rational calculation checks both errors.

## REST units still unresolved

An unauthenticated retrieval of the [official REST OpenAPI](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/advanced-trade-spec.yaml) succeeded at **05:28:57.611974-05:28:58.173590 UTC**, HTTP 200, **408,110 bytes**, SHA256 `e1edecbc619a505853dfa5b7457f5660f0053c596af39d949899bd7993bba4b2`. The research agent checked `FutureProductDetails.funding_rate`, `funding_interval` and `L2Level.size`: these string fields lack unit/scale descriptions. Raw schema bytes were not retained during its read-only assignment; this hash is an agent acquisition record, not a locally re-verifiable artifact. No duplicate request was made solely to save it.

The official [public product reference](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product), [public book reference](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-book) and [US futures API guide](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/guides/futures) did not provide the requested CDE REST mappings in this bounded check. Economic descriptions of hourly percentage funding do not specify whether a REST rate is a fraction or percentage points. Preserve outer/nested funding fields and raw book sizes separately. Do not turn them into cash funding or executable capacity using a guessed scale, SDK, WebSocket, FIX or international-market convention.

## Implications for optimization

This evidence improves cost-document provenance; it produces no new alpha observation. No claimed fee saving, profitable route or strategy survivor follows. Whole-contract constraints from the earlier timestamped quotes still describe those historical quotes only. The current 95-variant spot-proxy search's zero survivors is recorded in the separate [US forward evidence review](https://github.com/wardalexander368-sudo/Continuations/blob/b610e929ff3d9ba43293183090d6872950eb9ac9/handoff/reviews/us-forward-evidence-refresh-2026-10-14.md), not rerun or altered here.

The next admissible optimization comparison needs an explicitly dated applicable CFM fee equation, REST unit definitions, chronological executable quotes and complete fill/funding/account controls. Only then can an untouched paired experiment compare a fixed alternative after every cost, at a fixed readout. Frozen strategy registrations and numeric assumptions are not revised to fit these document findings. Profitability and novelty remain unestablished.

## Receipts and limits

Three direct public GETs (two PDFs and the examples page) returned HTTP 200 between **05:34:37.855961 and 05:34:38.587334 UTC**. Reads were capped at 2 MB per response with a 25-second timeout; no retries. Original bodies, byte counts, hashes and request times are in `handoff/data/cde-retail-evidence/2026-10-14/`. Other web-tool sources have parsed-page provenance only: original HTTP bodies/status/timing are unavailable. Schema retrieval has the separately identified agent-reported retention limit. Searches were non-exhaustive. Nothing establishes current fees for all study roots or full-account execution coverage.

Validation records separately cover saved-body hashes, exact arithmetic, independent source/redline review, allowed diff scope and the existing repository suite. Local render images and test logs remain in the Mac delivery, not the public repository. No profit claim is inferred from engineering checks.
