# Paper box execution evidence — 2026-10-13

The earlier source audit's partial-fill, incomplete-observation, clock and reconciliation concerns are now **REPRODUCED in synthetic offline execution**. Nineteen controlled cases produced 98 passing recorded outcomes/assertions. The account reconciliation detects the two tested valued residuals and auto-halts. No production occurrence, economic loss, latency advantage or profitability was measured.

Actual functions were imported from Continuations with exact module paths and SHA-256 checks. Executed base: `71f137fcc103050a24d75ca94fa7969117b65fe2`. The three relevant modules are byte-identical at the fresh public main `58df0c910c5f3526c5838bff088cb640a37ad41d`; the saved report, state, paper ledger and dry-live fill ledger are also unchanged. At the bounded remote-head check no `box-data` branch was advertised. This does not establish deployed server/account state.

| Evidence concern | Controlled execution and paired control | Consequence supported by this evidence |
|---|---|---|
| Positive partial sell | Full buy yields 0.9975 units. A 40% sell fills 0.399, leaves 0.5985 and removes the box position; full sell leaves zero. Both sell rows report the same modeled price return. | A sell row is insufficient evidence of complete liquidation or account cash PnL. Valued residual reconciliation detects $65.84 mismatch and auto-halts; the next step makes no client calls. |
| Later-completing partial buy | Initial 0.4 gross buy later reaches 1.0; sell uses cached 0.4 without an order lookup, leaving 0.5985. Initial zero-fill control performs a lookup and sells all 0.9975. | Positive partial quantity needs explicit completion/inventory accounting. The tested valued residual is detected and halted. |
| Unresolved quantity | Unknown buy quantity with a fresh order and 50 priced held units returns `ok=true`, lists unconfirmed BTCUSD and yields green health; an otherwise identical 3,700-second-old order yields red. | Pending quantity does not itself prevent a green match. Green does not establish verified complete holdings. |
| Unknown valuation | No book and 50 stray units with unavailable price yields green/no mismatch; the same units priced at 100 yield red/$5,000 mismatch. | Unknown valuation needs a separate unresolved state; the zero-price fallback can mask a quantity discrepancy in this fixture. Actual API incidence is unmeasured. |
| Incomplete observation | One-coin error, missing target candle, missing historical candle and empty candles each advance the shared cursor. Complete ETH still buys; BTC restoration 60 seconds later produces no candle retry, and the next hour evaluates only that hour. Complete no-signal control also produces no fill. | Absence of fills cannot distinguish no opportunity from incomplete observation. Record per-coin/hour coverage and disposition. No retrospective order creation is proposed. |
| Clock meaning | Two coins each incur three fake 20-second fetches, a 5-second submission and a 10-second wait. Logged latency remains 120 seconds; fake submission latency is 180/255 and fake fill latency 195/270. Zero-duration controls agree. | Current latency is nominal pass-start delay. Actual submission/fill clocks are required for a measured timing comparison. The specified exit deadline leaves 86,325/86,250 seconds after fake fills. |

The no-sell-fill control retains the position and inventory, emits no sell row and writes an auto-halt because no fill was returned; its fresh order is not counted as stuck. Direct `Box.check`/`sell` calls in the inventory probe isolate those functions; coverage/clock cases run `Box.step` but replace the client/candles with deterministic in-memory fixtures. `_fill`, reconciliation, hourly conversion and signal computation run as imported code. Partial-fill wait is zero; the clock probe replaces wait with an explicit fake duration. None of these fixture durations, grids, fee rates or fill distributions are market estimates.

## Accounting and comparison follow-up

Alpaca documents separate partial and terminal-filled states and recommends order updates to maintain state. A positive cumulative fill is therefore insufficient evidence of terminal completion. [Official order lifecycle](https://docs.alpaca.markets/us/docs/orders-at-alpaca)

Its crypto documentation denominates fees in the credited asset/fiat and exposes incurred fees through CFEE/FEE activities; the page also says same-day activity may omit fees until end-of-day posting. This supports retaining unresolved fee coverage. The fixed 0.25% fixture fee is not a measurement of this account. [Official crypto fees](https://docs.alpaca.markets/us/docs/crypto-trading)

Owner implementation follow-up should define terminal/partial/pending order handling, residual inventory, unknown valuation, per-coin observation states, actual timestamps and fee/account controls. Preserve frozen hourly registrations; evaluate complete registered policies separately from any future timing diagnostic. Different box/hourly stake, account, caps and exit reference prevent attributing account-dollar differences solely to latency.

Before outcomes, lock a separate paired comparison's window, eligibility, sizing, costs, exits and outage treatment. Match `(coin, signal_hour)` opportunities and retain one-sided fills, skips, errors, unknown coverage, partials and halts. Report full account cash/inventory outcomes and cluster uncertainty by crash episode. Nothing here reopens closed memecoin trading, authorizes a live route or proves a novel method; novelty and profitable strategy claims were not made.

## Receipts and reproducibility

Full JSON receipts and bounded source scripts are retained in the Mac-local `Box-Execution-Evidence-Package-20261013.zip`; these bulk artifacts are not committed in this documentation-only PR. Each JSON retains synthetic inputs, actual outputs, source checks and scope limits. The separate independent review checks fixture conservation and confounds. The initial partial-fill draft used stale synthetic sell timestamps; it was corrected to the sell/reconciliation clock before final review. Its exact hash-matching reconstruction is retained under local work, while only corrected receipts are packaged.

| Local receipt | SHA-256 |
|---|---|
| `Box-Partial-Fill-Probe-20261013.json` | `6a713adac793050d392271769c8b972a46ae757862d885ef6b12286b79f71e7b` |
| `Box-Reconciliation-Probe-20261013.json` | `01625c565fbb24bc4e1391fa61f76a219a701d3b1eb34ed182b2cd6f73f18209` |
| `Box-Coverage-Clock-Probe-20261013.json` | `8a0b83dacd9aabff86f854704ebe4a6f68c033cbcc93f6adf51f30bc99787e7c` |

| Local probe source | SHA-256 |
|---|---|
| `partial_fills.py` | `682cccfb3cc3ca60ee46ed6b2ed910bba43aa9babefa52d7efd3816d431e3fee` |
| `reconciliation.py` | `b96d5354e2bb9f558baa7a9731b6ef28e9c5eb00f29ed26eb1ada0f7e5eee12a` |
| `coverage_clock.py` | `cb6f2d01dd22aa65c581c6dbd4e78d9e69998cf46ebef6f82cf438f2ad07ed15` |

Run from this chat's folder with bytecode disabled and the existing research Python environment; use `reconciliation.py --repo <worktree> --scratch <new-local-scratch> --output <new-local-output>`. `partial_fills.py` uses `--source <worktree> --json <designated-output> --md <designated-output>`; `coverage_clock.py` uses its pinned source/output constants. Scripts deliberately constrain paths to this Mac and refuse changed source hashes; read them before adapting elsewhere. Preserve existing receipts before rerunning the latter two, which write their designated outputs. No owner module was changed or copied into a probe.

Network guards were active; all three final probes blocked explicit self-checks, and zero unexpected network calls occurred. No API keys, broker clients, real orders, funding, paid services or private account data were used. Source and owner state were unchanged. Independent inventory/cash conservation checks pass; the reconciliation probe's initially limited guard was strengthened and the same case receipts reproduced at fresh scratch paths. The earlier full pytest run at the identical executed base was 449 passed, one skipped and nine subtests passed. This documentation-only continuation did not rerun that full suite; the 19 existing box, Alpaca and frozen-registration tests passed in 0.68 seconds. The 98 diagnostic outcomes are separate from repository pytest.

Not checked: actual API behavior/partial-fill frequency, current deployed account/server, authentic fees/cash ledger, real outage frequency or missed trades, actual fill timestamps, price impact/slippage, AlpacaMirror close path, every repository test, strategy profitability or live eligibility. Latest-only startup/skipped-hour handling was observed; whether it is the owner's intended policy remains a policy question. No historical orders should be fabricated to fill evidence gaps.
