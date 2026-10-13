# CAPIT test portability repair — 2026-10-13

The first GitHub run failed one new test: `test_changed_cohort_cli_fails_before_loading_cache`. The workflow uses sparse checkout and includes `handoff/experiments/` but excludes `handoff/data/`. The test attempted to open the committed dated protocol from that excluded directory, so the CLI failed before reaching the cohort guard. Initial CI: 1 failed, 423 passed, 1 skipped and nine subtests in 104.37 seconds.

The test now writes syntactically valid protocol bytes in its temporary directory and sets only the expected protocol digest to those bytes' SHA-256. It invokes the real CLI, keeps the production cohort digest unchanged, and requires exit code 2, the cohort-mismatch error and no output. The separate test still covers changed-protocol rejection. No research implementation, locked inputs, model outcomes or workflow changed.

A read-only explorer independently confirmed the sparse-checkout cause and endorsed this isolation of the actual cohort guard. All 29 focused tests pass after the repair. Final local and GitHub run results are recorded in the delivery/verification receipts.
