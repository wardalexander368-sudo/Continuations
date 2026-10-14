# Wallet analysis — 2026-10-13 UTC

The selected Claudia episode contains **five buyers and two sellers**. The largest buyer contributes **87.3543408106%** of the exact **10.255334171 SOL** gross buy volume; four verified returning buyers contribute **97.2220091588%**. This strengthens the concentration warning. It does not establish profitable traders, independent human buyers or a validated trading strategy.

The interactive chart separates three views: verified historical swaps, archived recorder observations related to our paper-traded mints, and a bounded current public-account snapshot. Their times and evidence standards differ, so their populations and amounts are not added together.

A freshness check at **2026-10-13 12:59 UTC** compares the pinned ledger with current main `71f137f`: its original 1,511 rows are an unchanged prefix, followed by **66 additional rows, all paper and all shadow**. Current main has 1,577 paper rows and no tracked Alpaca or box fill ledger. The chart's archive relations remain tied to the original ledger hash; these additions do not establish executions or fill the missing buyer coverage. [Freshness receipt](Wallet-Trade-Freshness-20261013.json) preserves both hashes.

## Seven-wallet comparison

Target mint: `2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM` (Claudia). Target pool: `Fe7bpDYCs74GqiCUF14HwgUMToPKV1d9mDYVX5BTohFr`.

Selected swaps span **2026-10-12 01:42:16–01:42:44 UTC**, a 28-second retained sample. “Gross buy / net sell” covers this sample only, in SOL. Prior buys/sells come from the expanded saved-body reconstruction before each buyer’s target transaction. Current quantities come from separate finalized RPC reads collected **2026-10-13 05:17:03–05:19:24 UTC**; methods and wallets were not sampled atomically.

| Wallet | Selected role | Selected gross buy / net sell SOL | Prior target participation | Expanded prior target buys / sells | Current native SOL | Current Claudia tokens | Current USDC | Current USDT |
|---|---|---:|---|---:|---:|---:|---:|---:|
| [8i8WsSj…XttG](https://solscan.io/account/8i8WsSj27j998Z7fqjw4JLeBBo7FkAPfqoNKEhYzXttG) | buyer | 8.958479563 / 0 | Verified returning | 4 / 1 | 0.134556075 | 1597749.824471 | 0 | 4000 |
| [3uzy6vZ…dej4](https://solscan.io/account/3uzy6vZMwwgHRrbe86YYFKZj2XaQjWXijqcnV3T6dej4) | buyer | 0.74625 / 0 | Verified returning | 1 / 0 | 0.12045418 | 28697.35244 | 272.411438 | 0.006245 |
| [CSx2gDh…eRFZ](https://solscan.io/account/CSx2gDhH9nw6vqknJkrHVCaWWDDr6sLbRvtJkiUieRFZ) | buyer | 0.284892244 / 0 | Unknown | 0 / 0 | 0.002516775 | 92609.85904 | 0 | 0 |
| [6KBtrzj…aJfD](https://solscan.io/account/6KBtrzj3Rxew41MD5ydL3AiB7WwTjLtFUKsSEf9yaJfD) | buyer | 0.221683792 / 0 | Verified returning | 3 / 1 | 0.042001527 | 0 | 0.116516 | 0 |
| [FXh9Xcd…YHcn](https://solscan.io/account/FXh9XcdM38anfSjMjqvPsj7zk2ttzJbwtDCzDhR6YHcn) | buyer | 0.044028572 / 0 | Verified returning | 7 / 1 | 0 | 0 | 0.001872 | 0 |
| [5jRkuL1…Ap4r](https://solscan.io/account/5jRkuL1fHtxEUY4qssGhN5dintEj8twpSP63eyyvAp4r) | seller | 0 / 0.753913509 | Unknown | Unknown | 0 | 0 | 1841.82504 | 0 |
| [GzpXnH3…kNWs](https://solscan.io/account/GzpXnH3XbmSt98yF1FLyge5njcjViXJTwiLjp8XfkNWs) | seller | 0 / 0.225930645 | Unknown | Unknown | 0.016995717 | 0 | 0 | 0 |

The two selected sellers provide **0.979844154 SOL** in net target sell proceeds. The eighth event in the official fee audit sells another mint to fund 6KBtrzj’s target buy; it is excluded from target sell and round-trip counts. No selected buyer’s zero sell count proves it held indefinitely. A current zero target quantity does not prove a verified exit or liquidation, and a higher current quantity does not identify when or how additional inventory arrived. Current stablecoin quantities are not a complete net-worth estimate or a dollar valuation.

## What the buyer evidence adds

The reconstruction scans **120 unique saved transaction bodies**: 117 successful and three failed. Exact owner and transaction-signer evidence attributes **47 unique PumpSwap events** to these seven wallets. **45** have full fee decoding under the pinned current IDL; two older event formats keep their quote economics unknown.

The scan reproduces the original events and adds **four earlier target buys**, one for 6KBtrzj and three for FXh9Xcd. Expanded prior target history is **15 buys and three sells**, and expanded prior other-mint history is **21 trade events**. These are selected, incomplete historical records, gathered after the observed entries. They cannot establish what an entry-time strategy knew.

CSx2gDh now has verified successful trades in a third other mint, but its observed activity-age lower bound remains **2.533576 days**. Its prior Claudia participation remains unknown. Only 3uzy6vZ verifies both at least 14 days of prior activity and successful trading in at least three other mints. The observed ages are lower bounds, not wallet creation dates; absence of older saved records does not identify a first-time buyer.

Observed activity-age lower bounds are 15.414873 days for 8i8WsSj, 265.314132 for 3uzy6vZ, 2.533576 for CSx2gDh, 3.126956 for 6KBtrzj and 7.122512 for FXh9Xcd. Verified other-mint breadth is respectively 1, 3, 3, 1 and 4. Sellers’ signer-verified prior target histories are unknown.

The 47-event CSV is disjoint by event identifier. The all-saved JSON and its canonical/prior/additional views overlap: do not add them as independent populations.

## Funding and infrastructure relations

| Buyer | Observed funding in the selected buy transaction | Actual transaction fee payer |
|---|---|---|
| 8i8WsSj…XttG | Disposal of 1,000 USDT with routed WSOL | The buyer |
| 3uzy6vZ…dej4 | Native SOL supplied to the quote account | The buyer |
| CSx2gDh…eRFZ | Net owned disposal of 32.360835 USDC with routed WSOL | AgmLJBM…JzN51 |
| 6KBtrzj…aJfD | Disposal of another mint; 0.221683792 SOL proceeds equal the target gross debit | The buyer |
| FXh9Xcd…YHcn | Disposal of 5 USDC with routed WSOL | AgmLJBM…JzN51 |

CSx2gDh, FXh9Xcd and selected seller 5jRkuL1 share fee payer `AgmLJBMDCqWynYnQiPCuj9ewsNNsBJXyzoUhD9LJzN51`. CSx2gDh and FXh9Xcd also share a recorded routing source. These identify common infrastructure, not common human ownership or independent buyers. Ultimate initial funders remain unverified.

The largest buyer’s native SOL drops by only **0.000019324 SOL** in its selected transaction while its routed buy spends **8.958479563 SOL**. Stablecoin routing explains why native-account changes alone cannot recover trade size or PnL. Pool LP, protocol and creator economics are embedded once in verified gross buy/net sell values. Buyback fee is a protocol-fee subdivision, not an extra trader charge. Whole-transaction network fees retain their actual payer. Published PumpPortal service fees are not assumed to have applied to these observed wallets.

## Archived traders in relation to our paper trades

The bounded archive comprises **39 compressed recorder files**, **692,923,061 compressed bytes**, **8,690,542 raw rows** and **8,549,875 wallet activity observations before deduplication**. These observations include overlapping recorder copies. Across **31,177 activity mints**, the summary covers **339,880 wallet addresses**, including **297,616** with recorded buys. Fingerprinting retains **6,871,577 heuristic events** and removes **1,678,298 duplicate observations**. These are wallet addresses, not identified human traders. The archive covers receipt times **2026-10-08 14:06:02.881–2026-10-09 20:19:55.920 UTC**. Receipt times are not chain block times.

The relation to our saved trade data uses the exact chain mint in `trade.meta.mint`, matched to `raw.mint`. A symbol or pool-valued `asset` field is not substituted for a mint. The pinned ledger has **1,511 paper rows**; **1,507** carry exact mints across **20 mints**, and **four** missing-mint rows remain unmatched. Dip/shadow variants are correlated paper rows, not distinct real executions. **Only one of the 20 exact paper mints overlaps the archive**, covering **58 of the 1,507 mint-bearing paper rows** and **3,931 historical wallet addresses**. Those 58 rows include correlated shadow variants; they are not 58 independent real executions. The other 19 paper mints have no recorded overlap in these source files; that absence is a coverage limitation, not proof of no buyers.

The one overlapping mint is `8TiMkgvsrat9tM2esko8zVTt99LZLpefUM4SnZaziXaQ` (paper pool `cb4GFRgEitfu5qtxfRMiqzsaVPwgbD3HEor4cs2jFpn`). It has **17,870 heuristic events**, **3,809 recorded buyers** and **3,094 recorded sellers** in the archive. Its retained activity ends **2026-10-09 06:00:17 UTC**, while its first paper entry is **2026-10-11 06:20:00 UTC**, over 48 hours later. Its largest buyer represents approximately **4.7386%** and its top five approximately **8.2329%** of recorder buy-SOL flow. Those shares are not comparable to the 28-second, account-verified Claudia sample as a risk or performance test.

| Observed archive behavior | Wallet addresses |
|---|---:|
| Recorded buys and sells | 228,412 |
| Recorded buys only | 69,204 |
| Recorded sells only | 42,264 |

“Only” describes this saved window. These are not long-term investor classifications. The creator export contains **38,447 recorded creator/mint associations**; **11,032** creator addresses have no activity rows in the main wallet summary. Exact creator-address equality with a recorded trader is an address relationship, not a developer identity or intent judgment.

The seven verified-episode addresses were also matched against the full archive:

| Selected wallet with observed archive activity | Heuristic recorded buys / sells | Recorded mint breadth | Archive receipt window UTC |
|---|---:|---:|---|
| CSx2gDh…eRFZ | 1 / 0 | 1 | 2026-10-09 17:34:15.305328 |
| GzpXnH3…kNWs | 19 / 7 | 4 | 2026-10-09 01:32:28.804059–16:45:32.253659 |

The other five selected addresses were not observed as traders in this bounded archive; their archive activity metrics stay unknown. Neither observed address overlaps a paper mint in this archive. These recorder-address matches do not add signer/base-owner proof, establish a returning Claudia buyer or upgrade historical entry eligibility. [Seven-address archive link export](TarTrade-Verified-Wallet-Archive-Links.csv).

The recorder ends before the first saved paper entry. Therefore the archive provides **zero contemporaneous paper-entry/exit coverage**. It identifies historical participants in assets later paper-traded, not buyers observed at our fills. No actual execution ledger or full wallet cost basis is recovered by this join.

Heuristic deduplication ignores receipt time and retains economic fields plus available slot, quote and program fields. The archive lacks transaction signatures and instruction/event identities, so fingerprints may falsely merge distinct events or split copies with missing fields. Deduplicated counts remain heuristic observations, not an exact count of unique chain trades. Recorder `sol` is curve/pool quote flow; swap `paid` is a recorded trader quote amount, not account-verified all-in gross debit/credit. Neither establishes net PnL. Non-SOL quote-paired rows are kept separate from SOL sums; missing numeric fields remain unknown. Network, priority, rent and service costs are not present in these recorder amounts.

## Current-account coverage and limits

The current token queries returned **498 token-account records** across the seven addresses. Counts include zero-balance and potentially unsolicited assets; they are not a portfolio quality score. The public snapshot uses **56 bounded requests**: seven balances, seven account-role queries, 14 owner-token-account queries covering both classic SPL Token and Token-2022, seven latest-50 signature pages, and 21 selected successful transaction bodies. All 56 parsed responses were saved. The **350 signature references** are address references, not 350 proven signed trades. Failed-reference counts are not a trader failure rate. [Solana signature-reference semantics](https://solana.com/docs/rpc/http/getsignaturesforaddress).

Five Token-2022 account displays differ from raw amount divided by decimals. Both representations are preserved; the specific mint extension configuration was not verified. Claudia, USDC, USDT and WSOL quantities agree under both representations. [Solana scaled UI amounts](https://solana.com/docs/tokens/extensions/scaled-ui-amount).

Original HTTP response bytes were omitted from this acquisition. Parsed payloads, transport-time byte hashes and a hash of the saved receipt file are retained. Common JSON re-encoding reproduced 48 of the 56 acquisition response hashes; eight could not be reconstructed by the independent reviewer. This limits byte-level acquisition auditability without invalidating the reproduced parsed amounts. Future collector code preserves raw response bytes in base64; it does not retroactively repair this snapshot. [Independent review](Wallet-Independent-Review.md).

Complete wallet history, complete pool history, acquisition cost basis, human ownership, all-asset value, realized PnL and win rate remain **unknown**. No profitable-wallet ranking is produced from partial swaps or current balances.

## Deliverables and provenance

- Interactive wallet chart (`Wallet-Summary-Chart.html`, complete local package).
- [Verified wallet summary](Verified-Wallet-Summary.csv), [47 saved events](Verified-Wallet-Events.csv), verified cohort and proof paths (`Verified-Wallet-Cohort.json`, complete local package), and saved-activity detail (`Verified-Wallet-Saved-Activity.json`, complete local package).
- All 339,880 archived wallet addresses (`TarTrade-Wallet-Summary.csv`, complete local package), wallet-by-paper-mint detail (`TarTrade-Wallet-Paper-Mint-Relations.csv`, complete local package), creator-by-mint detail (`TarTrade-Wallet-Creator-Mint-Relations.csv`, complete local package), [archived coverage and source hashes](TarTrade-Wallet-Provenance.json), and archived chart data (`TarTrade-Wallet-Dashboard-Data.json`, complete local package), and [archive consistency validation](TarTrade-Wallet-Validation.json).
- [Current account summary](Wallet-Public-Summary.csv), normalized public snapshot (`Wallet-Public-Enrichment.json`, complete local package), and saved parsed RPC receipts (`Wallet-Public-RPC-Receipts.jsonl`, complete local package).
- Verified source manifest and coverage (`Verified-Wallet-Coverage.json`, complete local package), independent checks (`Verified-Wallet-Independent-Checks.json`, complete local package), and [market evidence plan](Wallet-Market-Coverage-Plan.md).

Repository reading inputs are pinned to `abe8aca5748d2e351bbb7eb5cdefb061488f4633`. Newer repository paper rows are outside this dated analysis. The verified reconstruction hashes **24 source files**, including retained public RPC bodies and the pinned official IDL, SHA-256 `b7d8c57a4d9c4dd0109a9ab893052352333252d4eedced10ac091d4d66cab89b`. Repository copies, snapshots and prior views do not create additional observations. Fee-verified amounts and normalized native RPC quantities are retained as exact decimal strings in JSON and CSV. Archive sums preserve recorder floating-point precision; they are not integer-account reconciliations. Rounded chart labels are presentation values. Engineering validation and independent reconstruction check evidence integrity, not profitability.
