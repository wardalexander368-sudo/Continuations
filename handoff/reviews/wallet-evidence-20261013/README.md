# Wallet evidence summary — 2026-10-13

Descriptive trader research requested by AJ. This review preserves evidence and accounting limits; it changes no trading implementation, live paper book, registration or workflow.

- **339,880 recorded wallet addresses**, 297,616 buyers, across 39 archived recorder files. Overlap handling retains 6,871,577 heuristic observations; it is not signature-level trade deduplication.
- **Seven fee-verified Claudia episode users:** five buys total 10.255334171 SOL. Largest buyer share 87.3543408106%; returning-buyer share 97.2220091588%. Incomplete histories do not establish lifetime PnL or human ownership.
- **One of 20 pinned paper mints matches the older archive**, with 3,931 historical wallet addresses. There is zero contemporaneous buyer coverage at the pinned entries/exits.
- **Bounded public snapshots:** 56 unauthenticated read-only requests for seven wallets; account state, token records and signature references remain point-in-time. Initial parsed responses are preserved, but original HTTP bytes were not retained; this acquisition limitation is disclosed.
- **Freshness:** main `71f137f` adds 66 rows to the unchanged pinned trade ledger prefix; all added rows are paper and shadow. No tracked Alpaca or box fill ledger establishes executions.

Read [analysis](Wallet-Analysis-Report.md), [coverage plan](Wallet-Market-Coverage-Plan.md), [independent review](Wallet-Independent-Review.md), [archive provenance](TarTrade-Wallet-Provenance.json), [33 archive checks](TarTrade-Wallet-Validation.json), [browser verification](Wallet-Browser-Verification.json), and [repository checks](Wallet-Repository-Checks.json). Small CSVs retain the exact seven-wallet summaries and 47 saved-body events.

The complete **offline HTML chart, all 339,880 wallet CSV rows, exact-mint/creator relation CSVs, parsed RPC receipts, JSONs and builders** are saved locally under `~/Projects/CodexCoinHunt/wallet-research/20261013-wallet-summary/` and in `Wallet-Research-Package-20261013.zip` in the calling chat's outputs. Bulk artifacts are not committed here. [Manifest](Wallet-Artifact-Manifest.json) hashes refer to that complete local package; public Markdown copies replace links to omitted bulk files with local-package references and consequently have different bytes.

Inputs are pinned to `abe8aca5748d2e351bbb7eb5cdefb061488f4633`. PR11 removed the closed recorder lane's raw files from current main; the reading checkout and Git history preserve these existing inputs. This study reused them without re-downloading or reopening collectors. The review branch was prepared from main `71f137fcc103050a24d75ca94fa7969117b65fe2`.

Validation: **449 passed, one skipped, nine subtests passed**, plus independent saved-body checks, 33 archive checks, hash comparisons and browser filter/detail checks. The in-app blob export event timed out, so that download completion is unverified; complete companion CSV files remain in the local package. SLR-0.2 stays unvalidated. No wallet profitability, predictive buyer signal or novel method is established.
