# CAPIT feed-coverage diagnostic - 2026-10-13 UTC

Recoverable missing Coinbase observations can advance CAPIT's shared signal cursor without a strategy error.
Restoring complete candles on the next run does not reconsider the skipped signal. This is reproduced
conditional behavior at `223a27fae671ee0a8757433d6c7359c83ce3c300`, not evidence of a production outage, missed executable trade or profit.
The work stays within the existing candidate's evidence integrity. The agent owner retains implementation.

## Observed comparisons

The offline helper runs the real Coinbase response conversion and CAPIT `step` against two synthetic coins.
It uses deterministic gentle price variation followed by a 40% crash, registered two-bar delay and 24-hour hold.
Each step uses empty positions to isolate signal discovery; intents are never filled. Original cursor is 500199,
first eligible signal hour is 500200, and the recovery run is one hour later with complete restored candles.
The comparison from the original cursor has the same recovery data, independently cleared cache and no positions.

| Input case | First open intents | First cursor | Recovery opens | Recovery cursor | Original-cursor-only signal |
|---|---|---:|---:|---:|---|
| complete | BTC, ETH | 500200 | 0 | 500201 | none |
| transient_404 | ETH | 500200 | 0 | 500201 | BTC:500200 |
| transient_200_empty | ETH | 500200 | 0 | 500201 | BTC:500200 |
| missing_entry_bar | ETH | 500200 | 0 | 500201 | BTC:500200 |
| no_signal | none | 500200 | 0 | 500201 | none |
| intentional_unavailable | ETH | 500200 | 0 | 500201 | none |

The complete case yields both coins initially. In each transient case ETH remains observed, BTC is absent,
and normal continuation emits no new intent after restoration. The original-cursor comparison emits both
original keys. The difference identifies discarded information; it says nothing about a late fill price.
No-signal and persistent-unavailability controls produce no extra key, so normal quiet or unavailable data
is not automatically labelled a lost signal. A 404 alone cannot establish either delisting or transient failure.

All six recent constructed states with zero strategy errors are green under real `health.check_agent`.
The positive control with one constructed strategy error is yellow. This diagnostic does not run the other
global health checks. The saved `health.INPUTS` inventory covers five other input families; none is a named
Coinbase/CAPIT candle-coverage check. A green strategy check therefore cannot distinguish these coverage cases.

An independent read-only refuter also exercised real `runner.run_once`, `Risk.record_ok`, ledger/report
persistence and `health.run`, intercepting filesystem operations into a strictly synthetic in-memory tree
and providing synthetic successful workflow/input checks. Complete data opened two paper positions; 404,
empty 200 and entry-bar-gap cases opened only ETH. All had zero runner/strategy errors and green synthetic
global health before and after recovery; restored data opened zero additional positions. That check confirms
the path through persistence; its artificial unrelated inputs are not evidence of actual workflow health.

## Mechanism and owner handoff

* `coinbase_pattern.py:154-155` intentionally turns HTTP 404 into no candles for delisted pairs.
* `coinbase_pattern.py:184-202` calculates each coin's signals and explicitly skips missing entry candles.
* `coinbase_pattern.py:218` advances one shared `done_hour` after all coins, including empty responses.
* `runner.py:145-154` records an error only on an exception; these paths return normally.
* `health.py:43-49,160-202` checks other input families, recent runs and errors; no per-coin CAPIT coverage
  receipt is evaluated there.

The delisting exemption and entry-candle skip are documented existing behavior, including a delisting test.
This review does not prescribe replaying historical orders or backfilling an untouched forward book.
The existing agent owner should decide a coverage contract: distinguish valid no signal, intentional
unavailability and incomplete observation; retain per-coin/time coverage and omitted-reason evidence;
and surface unresolved observations in readiness reporting. Any retry policy must preserve chronological
execution semantics, original timing rules, position identity and the distinction between hindsight and fills.

Absent saved fills cannot establish complete observation, zero fees or zero opportunities. Missingness could
bias results in either direction. No return or expected dollar-loss estimate is attached to this fixture.
CAPIT remains unvalidated; the empirical dependency is untouched crash observations with paired executable
quotes/fills, reconciled costs and matched controls. No new strategy family, schedule or live route is added.

## Replay, verification and limits

From the repository root, using its test environment:

```sh
PYTHONDONTWRITEBYTECODE=1 python handoff/experiments/capit_feed_integrity.py
python -m pytest -q tests/test_capit_feed_integrity.py tests/test_autotrade_coinbase.py
```

The helper writes JSON to stdout and optionally an explicitly requested artifact path outside every
`autotrade` directory. It reads no bot book, account, keys or data cache; injected HTTP is entirely synthetic.
Tests exercise wire-field conversion, HTTP/body/gap distinctions, controls, positive health error detection,
no client/book access, cache/sleep restoration on success and exceptions, and a sparse code-only CLI checkout.
The tests pin this diagnostic's fidelity at the reviewed baseline, not a desired permanent trading behavior.

Focused verification: 20 passed, including existing Coinbase regressions. Full repository suite:
**409 passed, 1 skipped, 9 subtests passed in 80.50s (0:01:20)**. CLI stdout and saved readout are byte-identical. The
[readout](../data/capit-feed-integrity/2026-10-13/readout.json) and
[verification receipt](../data/capit-feed-integrity/2026-10-13/verification.json) preserve hashes and scope.
No production omissions, actual HTTP causes, official scorer outcomes, costs, profit, real accounts,
mirrors, orders, schedules, frozen registrations or claimed implementation changes were checked or made.
