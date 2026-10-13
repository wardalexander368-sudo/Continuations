# Research records and economic evidence controls — 2026-10-13

Alex requested implementation of the AI trading page/article review's improvements. This branch adds an offline research trial/access ledger and current research documentation. It reduces the risk of relabeling inspected outcomes as untouched, losing rejected attempts or confusing paper engineering with account profitability.

## Behavior

`handoff/experiments/research_evidence.py` appends strict, hash-chained JSONL events under a caller-selected path. Plans identify owner/proposer/model, lineage, hypothesis, economic mechanism, decision, stop/readout schedules, alternatives, cost model, controls, universe, regimes, readout schedule, availability windows and artifact hashes. Freeze/access/result/rejection events preserve chronology; outcome-informed changes require a child trial. First artifact access cannot reset across children. Fixed-rule monitoring remains allowed, while registered final results wait for the declared window to close.

Metrics keep opportunities, fills, sides, round trips, days and episodes separate. No completed round trips means inference is not estimable, while known account fees/losses or verified zero remain facts. Unknown P&L remains null. Cost receipts record source, validity, route, size, payer and inclusion; trader-paid top-level fees cannot silently opt out, and embedded subdivisions cannot be charged twice.

`research-governance.md` and `research-evidence-usage.md` describe implementation and limits. Mutable findings/plan/live-rule/box notes now reflect adopted v2, existing control reporting and conditional server economics. Historical registered verdicts are unchanged. The saved fixed-cost diagnostic remains explored history: $1.31–$1.52/month incremental ceiling under the saved $100/hourly-account assumptions, not a forecast or measured box saving. A paired CAPIT comparison protocol is a draft pending later complete evidence, not a new registered test.

## Validation and limits

Validation receipts are in the PR and implementation handoff. Synthetic tests include ledger corruption, truncation with an external anchor, lineage/UTC rules, schema failures, frozen monitoring, known account loss without completed trades and fee exclusion/double counting. Independent review reproduced and corrected three initial contract gaps.

A hash chain plus independent head detects supplied-record changes, not unlogged experiments or false attestations. The tool does not calculate account equity, verify fee authority, authenticate real fills or authorize orders. There is no network interface or scheduled collector. No frozen registration, strategy constant, archived engineering count or owner paper-book file is edited.

## Final validation receipt

Full repository suite: **526 passed, 1 skipped, 9 subtests passed** in 90.21s. Command: `python -m pytest -q -p no:cacheprovider` in an isolated Python3.12.6 virtual environment with the same47 package versions as the existing environment. LightGBM was imported before the suite to remove cold-import timing from the demo test. The original environment is unchanged. `git diff --check`, forbidden-path/public-diff scan and frozen/numeric-constant checks passed.
