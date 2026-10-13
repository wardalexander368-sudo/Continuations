# CDE cost documentation addendum — 2026-10-13

Public documentation now supplies a dated exchange-fee component and explicit US funding economics. **Current CFM retail all-in charges, public book-size units and REST funding-rate encoding remain unknown.** This addendum adds no execution, account or profitability result.

The saved CDE schedule is effective **January 26, 2026**. For these roots, electronic exchange fees are **$0.10 per side per contract** for both professional and nonprofessional participants. Market-maker electronic pricing is $0.07 and requires a signed agreement; resting an order does not establish that status. These are dated exchange components. The latest applicable schedule and CFM’s complete retail charges remain unverified. [Official exchange schedule](https://assets.ctfassets.net/k3n74unfin40/sgInuF26edJX4v4nUlE29/87f18103cd35feede93f0bb92a5f1065/Fee_Schedule_1.26.2026.pdf).

| Study root | CDE symbol | Saved Advanced Trade API product ID |
| --- | --- | --- |
| BTC | BIP | BIP-20DEC30-CDE |
| ETH | ETP | ETP-20DEC30-CDE |
| SOL | SLP | SLP-20DEC30-CDE |
| XRP | XPP | XPP-20DEC30-CDE |
| DOGE | DOP | DOP-20DEC30-CDE |
| ADA | ADP | ADP-20DEC30-CDE |
| AVAX | AVP | AVP-20DEC30-CDE |
| LINK | LNP | LNP-20DEC30-CDE |
| LTC | LCP | LCP-20DEC30-CDE |
| BCH | BCP | BCP-20DEC30-CDE |
| DOT | POP | POP-20DEC30-CDE |

The mappings combine the dated schedule’s symbols with the previously saved public product/book responses from **2026-10-13 02:02:05.144767–02:02:07.075976 UTC**. They do not establish book-size units. A dated one-contract open/close exchange component of $0.20 equals 19.5503 bps of the saved AVAX $102.30 entry notional, or 17.4825 bps of DOT’s $114.40. This is a component-only diagnostic using old schedule charges and snapshot prices, not a current cost floor or total charge.

Coinbase’s **July 21, 2025** US CFM launch article advertised fees as low as 0.02%, inclusive of exchange, clearing and NFA charges, with a $0.15 minimum per contract for fixed costs. The article does not establish the current rate, per-side versus roundtrip minimum, or whether the minimum replaces or adds to a percentage charge. Its launch scope was BTC and ETH; it does not verify today’s all-eleven retail schedule. Adding its bundled charge to exchange/NFA components could count costs twice. [Official launch article](https://www.coinbase.com/blog/perpetual-futures-have-arrived-in-the-us).

For hour h, signed contracts Q_h (positive long), multiplier M in underlying coins per contract, futures mark P_h and hourly funding rate r_h expressed as a decimal fraction give:

`funding_cash_adjustment_h = -Q_h * M * P_h * r_h`

Cumulative funding requires quantities at applicable funding events, each final hourly rate and its matching mark. Funding is computed hourly; clearing and FCM posting need not occur hourly. [US overview](https://help.coinbase.com/en/coinbase/derivatives/us-perpetual-futures-overview), [CDE funding mechanism](https://help.coinbase.com/en/derivatives/perpetual-style-futures/funding-rate).

The Advanced Trade YAML declares `L2Level.size`, outer `FutureProductDetails.funding_rate` and nested `PerpetualProductDetails.funding_rate` as strings without unit descriptions. A raw interval of `3600s` does not specify the rate’s scale. The saved outer rate and blank nested rate remain distinct observations. No explicit mapping to these REST encodings was found in the sources examined; native CDE and Global/INTX/Deribit fields cannot be substituted by name alone. Keep raw sizes and rates unchanged; no capacity calculation or 24-hour rate extrapolation is supported. [Official schema](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/advanced-trade-spec.yaml), [public book reference](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-book).

Next evidence needed is a current, explicitly US CFM retail fee schedule tied to these contracts and a billed-component reconciliation; an explicit Coinbase definition of CDE REST book quantity and funding encoding; and matched entry/exit fills, hourly funding cashflows, timestamps and collateral policy. US statements expose commissions, NFA and funding separately, so reconciliation must determine bundling before subtraction. [US statement help](https://help.coinbase.com/en/coinbase/derivatives/us-derivatives-manage-account).

The [saved PDF](../data/cde-cost-documentation/2026-10-13/CDE-Exchange-Fee-Schedule-20260126.pdf) is 103,371 bytes, SHA-256 `cf38e39591dab66cb89c9f4601e8aa50486a3b99597a628555c9f64ce8e4a612`; both pages were visually checked by the coordinating agent. The 408,110-byte official YAML was read at **2026-10-13 04:14:28.101505 UTC**, SHA-256 `e1edecbc619a505853dfa5b7457f5660f0053c596af39d949899bd7993bba4b2`. Linked HTML pages were observed again around **04:21:39 UTC**; their raw bodies were not archived or hashed. The YAML bytes were hashed during the public read but were not archived in this repository. The latest-schedule page could not be read, and no newer schedule is asserted. The [source receipt](../data/cde-cost-documentation/2026-10-13/sources.json) records these limits and verifies all twelve saved public response hashes. No accounts, credentials, orders or private paths were accessed.
