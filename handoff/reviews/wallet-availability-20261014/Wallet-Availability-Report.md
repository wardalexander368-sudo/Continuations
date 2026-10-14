# Wallet record availability - October 14, 2026

**57 of 77 pinned Claudia paper rows had no target-buy transaction body received by entry time.** At signal time, 60 of 77 had none. An event-time-only join would find earlier target buys for all 77 rows, so it would obscure this evidence-availability gap. These counts describe our incomplete saved sample; they do not prove missing market activity or actual look-ahead in the trading bot.

The new offline chart (in the complete Mac delivery) lets you switch between signal and entry cutoffs, paper rows and correlated signal keys, and saved strategy variants. [Paper-row CSV](paper-row-availability.csv), [signal-key CSV](signal-key-availability.csv), [source receipt](source-receipt.json) and [findings](findings.json) retain the underlying evidence.

## Results

| Cutoff | Counting unit | Total | No receipted target buys | Some receipted target buys |
|---|---|---:|---:|---:|
| Signal time | Paper rows | 77 | 60 | 17 |
| Entry time | Paper rows | 77 | 57 | 20 |
| Signal time | Correlated signal keys | 39 | 25 | 14 |
| By at least one retained entry | Correlated signal keys | 39 | 24 | 15 |

There are **20 exact-target buys among 47 saved unique events** attributed to the selected seven wallets. This is a small retrospective reconstruction, not complete wallet or pool history. The 77 paper rows share 39 signal keys; variants remain correlated. No confidence interval, independence test or performance estimate is calculated.

For each of the five selected observed buyers, our retained bodies describing its strictly earlier trade events were received **after** its observed purchase. All five have zero prior-event body receipts by their own buy timestamp, although four are retrospective returning buyers. The reconstruction can establish those historical relationships without establishing an entry-time buyer feature. It says nothing about what those wallet owners themselves knew.

## How the join works

The ledger is pinned to Continuations `abe8aca5748d2e351bbb7eb5cdefb061488f4633`, SHA256 `12518620583d753bdaa86408d246378cae1144269e239e6d00ebf85bb2bce4e7`. It has 1,511 paper rows; exact `trade.meta.mint` equality selects the 77 Claudia rows. A symbol or pool-valued asset is never substituted for a mint.

Existing saved-activity, cohort and coverage exports are checked against the wallet package manifest pinned at `69ef6d63fc8008488861b157e15b49042c3849d6`. The analyzer reads only seven named retained RPC files and these small exports; it does not scan the large recorder archive again. Event attribution and official-IDL decoding are inherited from that reviewed reconstruction, not independently re-decoded here.

For each event, the analyzer finds the earliest retained `received_at_utc` among successful finalized `getTransaction` bodies matching the requested and primary transaction signature. It requires explicit `meta.err = null` and the normalized transaction-signer proof. Duplicate event identities count once; conflicting identities fail. Normalized availability must match that earliest receipt. Event time and receipt time must both be at or before a paper cutoff for a record to be counted. For the selected-buyer prior-history check, the event timestamp is strictly earlier than its observed purchase. Chain timestamps have their saved resolution; same-timestamp instruction order is not inferred.

Missing or invalid cutoffs remain unknown; unrepresentable epochs, booleans, non-finite numbers and timezone-naive times are rejected. Unknown event/receipt timestamps remain separate from confirmed counts. The pinned inputs contain **zero timestamp issues**. These rules do not establish synchronized clocks or reconstruct a source's unretained HTTP bytes.

## What this changes in the research

**Transaction-body receipt is only an upper bound on potentially available input.** Feature computation time, feature publication and actual strategy consumption remain explicitly unknown. A later verified returner label, signer relationship or fee reconstruction cannot be inserted into an earlier decision merely because its chain event occurred earlier.

Future research needs both receipt/availability time and a versioned feature-computation/consumption record tied to the decision. Unknown history is not a first-time buyer; common infrastructure is not common human ownership; correlated paper variants are not independent trades. These requirements preserve the project's existing operating principles without changing the frozen SLR rule or reopening the closed memecoin-buying lane.

This seven-wallet RPC audit is distinct from the recorder archive. The archive's previously verified **zero contemporaneous paper-entry/exit coverage** remains unchanged. No fresh wallet snapshot, executable quote, complete acquisition cost basis, account control, realized PnL or profitable-wallet ranking is supplied. No optimization or novelty claim follows.

## Validation and reproduction

The independent reviewer reproduced the counts using integer-microsecond comparisons and separate grouping, checked the 1,511-row ledger selection, all 47 earliest-receipt matches and all five prior-history receipt counts. It checked 13 source/hash entries and nine output hashes. A reproduced oversized-integer timestamp exception was corrected; pinned results were unchanged. Direct malformed/valid timestamp probes and one offline rerun passed.

The dashboard reuses the existing Chart.js 4.5.1 runtime, embeds its data and removes only the source-map URL comment. Browser checks verify initial signal counts, entry counts, signal-key grouping and the `dip` variant filter; the original seven `dip` rows all have zero receipts at both cutoffs. No external runtime or market request is needed to render it.

The existing PR #12 source and tests have the same Git objects as the CDE worktree's freshly passing suite (**449 passed, one skipped, nine subtests**). This follow-up changes only descriptive review/data files. That suite validates unchanged repository code; separate arithmetic/source and browser checks validate this analysis and chart. No new broker audit or GitHub CI pass is asserted.

The local package includes the stdlib analyzer and existing source hashes. Reproduce with:

```sh
python3 analyzer.py --repo /path/to/Continuations \
  --package /path/to/20261013-wallet-summary --out /path/to/new-audit-output
```

This is a descriptive availability audit, not a strategy trial or profit result. The broad research goal remains active and unachieved.
