# Final scorer execution receipts

`final_scores.py` keeps the existing scorer commands, order, allowed dates, grace periods, and
verbatim primary/secondary score output. No registered calculation, criterion, frozen protocol byte,
collector, or Action schedule is changed. This is execution evidence, not evidence of profitability.

`SOURCE_LOCK.json` is an explicit **prospective-only** baseline captured on 2026-10-13, from
`a6da0ace5bf17cb53bf9cf65470e868070299d87`, with the execution wrapper/helper hashes captured after
these changes. It pins the exact named scorers, their local source dependencies, wrapper/helper,
and existing `FROZEN.sha256` manifest. It cannot establish that today's scorer bytes match the
bytes at historical registration. Receipts call that historical identity **unknown**, and record
the full commit that added each SPEC in the baseline's available Git history separately from the
full execution HEAD. A missing or shallow history is reported as unknown.

On an already-due run, the wrapper checks the baseline and all frozen pins before executing.
It writes one attempt receipt under `handoff/scoring/receipts/`, then records each subprocess in
the original order. It rechecks source/frozen bytes afterward and hashes declared local inputs
and temporary cache CSVs **before TemporaryDirectory cleanup**. Each receipt includes full stdout,
stderr, return codes, timeouts, execution errors, exact argv, UTC timing, selected date, allowed date
including grace, registered window metadata, Python/package versions, source hashes and frozen checks.
Receipts contain hashes/metadata of inputs, not input contents, environment contents, or credentials.

Unexpected/unavailable source or frozen provenance is `INVALID/PROTOCOL_DRIFT`, runs no scorer when
detected before execution, and creates no official RESULT. The baseline is never automatically
created or re-pinned. Any prospective replacement requires a separate reviewed change with its reason
and date; an observed mismatch is not permission to bless changed code. The lock itself is hashed
before/after execution so changing the baseline during a run also invalidates the attempt.

Nonzero primary **or informative secondary**, timeout, launch failure, explicit Coinbase
`gave up at` acquisition warning, or unavailable declared file hashing retains the attempt outside
preregistration and blocks official RESULT creation. The registration remains unscored and can retry
at its existing next invocation. A process killed with the wrapper leaves its last persisted receipt
as RUNNING; that is incomplete evidence, not a completed score. Exit zero creates `RESULT_RECORDED`
only after the checks; it does not mean the strategy succeeded. A registered `FAIL` output remains
a valid executed result and is preserved verbatim.

The inventory reads only the paths declared in the lock: two named snapshot JSONL files, the shallow
HL hourly candle CSV directory, or the run-owned shallow temporary CSV cache. It rejects symlink
components, nonregular files, files over 512 MiB, and directories with more than 128 matching files.
It never scans other repositories or performs extra HTTP requests. Raw input file hashes are exact
bytes; existing frozen-pin comparisons retain the manifest's CRLF normalization and also record raw
hashes. New runtime results/addenda are not frozen retroactively.

Limits remain explicit: the unmodified scorers have no HTTP-response acquisition manifest. HLP,
Hyperliquid momentum, and the funding/benchmark portions of JLP/pumpflow fetch into memory; those
response bodies cannot be hashed by this wrapper and acquisition provenance stays unknown. A CSV
hash proves the observed cached bytes, not complete venue coverage or successful acquisition of every
page. Unreported upstream gaps are not detectable here.
Before/after persistent input snapshots establish observed files, not every byte consumed if a
collector changes them concurrently. Source-match status is therefore explicitly prospective and
does not claim historical protocol identity or complete market-data coverage.

The wrapper's existing `--dry` lists due/scored states and writes no receipts or RESULT files. No
future scoring run was used to validate this change: tests use temporary fixtures and fake subprocesses.
Do not use `--today` to advance real registered scorers into future windows; only execute when due.

## Dated execution repair, 2026-10-13

The prospective source baseline includes two CDE execution repairs: `cde_forward.py` retains its
original `--final` boolean before rewriting `sys.argv` for `xs_coinbase.py`, and exhausted non-200/404
HTTP retries now raise instead of silently skipping a candle page. An explicit 404 is labeled
unavailable/coverage unknown and retains the existing unavailable-product handling. The fixed rule,
coin universe, request parameters, window, bootstrap, and 20 bp cost remain byte-for-byte unchanged
in those parts of the scorer. This repairs CLI/acquisition failure propagation; it is not a new
statistical rule and does not certify registration-time source identity or complete historical data.

A required shallow CSV directory with no matching files is incomplete input provenance and blocks
an official RESULT even if the scorer exits zero. A deliberate `inputs: []` declaration is recorded
as `no_declared_local_inputs`; its unsupported in-memory acquisition provenance remains unknown.
