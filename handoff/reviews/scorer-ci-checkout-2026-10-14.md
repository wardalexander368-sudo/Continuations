# Scorer CI checkout repair — 2026-10-14

The pushed scorer-provenance head `2dfbaf8e27d89467477fb7f7231553302698f61e` failed [GitHub run 38486164261](https://github.com/wardalexander368-sudo/Continuations/actions/runs/38486164261). Its test step finished with **477 passed, 1 failed, 1 skipped, 9 subtests passed**. The source-baseline test failed closed with `FileNotFoundError: 'scoring'`: the existing sparse checkout omitted `handoff/scoring/SOURCE_LOCK.json`.

PR16 requests Claude review of one added checkout path, `/handoff/scoring/`, in `.github/workflows/tests.yml`. The request was posted in the PR before editing the workflow, following AGENTS rule 6. The patch makes the checked-in baseline available to the existing test. It changes no trigger, schedule, permission, runner, dependency-install command, test command, or final-scoring workflow.

An offline archive of the exact failed head and its original checkout paths reproduced the same failure (**1 failed**). Adding the proposed path and workflow reproduced **1 passed**, across all eight named registrations without executing their scorers. The source lock and all 14 pinned execution source hashes are unchanged. No registration or paper-book file changed. The companion JSON retains run metadata, reproduction timestamps, and hashes.

The earlier local full-suite result, **478 passed, 1 skipped, 9 subtests passed**, remains a dated local result. This follow-up is not a new strategy test, does not establish historical executable identity or complete HTTP acquisition, and makes no profitability claim. Full GitHub validation of the follow-up commit is required before describing PR16 as ready; its outcome is saved separately after pushing.
