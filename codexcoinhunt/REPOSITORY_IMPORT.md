# CodexCoinHunt repository import

Imported October 12, 2026 at Alex's request into `wardalexander368-sudo/Continuations`, on `codex/codexcoinhunt-import-20261012`.

This folder contains the complete available CodexCoinHunt desktop release v5: source code, public raw evidence, reports, journals, tests, failed hypotheses, source attribution, prior versions, shared notes and the Mac installer. The original 379-file project manifest and its manifest file are preserved. The research subtree matches research-kit v11 byte for byte. `REPOSITORY_IMPORT.json` records archive identities and hashes. The additional import files sit outside those original manifest entries.

The nested Git attributes disable line-ending conversion so the original manifest hashes survive checkouts on different computers. Original CSV/attribution CRLF and historical document endings are retained as evidence bytes.

Start with `PROJECT_HANDOFF.md` and `research/Resolant_Memecoin_Project_Tracker.md`. For repository collaboration, the root `../AGENTS.md` and `../handoff/STATUS.md` apply: use `codex/*` branches, propose an unclaimed task in the PR, and leave merging to Claude. The nested source documents record the project's history; their references to earlier cloud storage and unreviewed Claude work describe that earlier release.

## Current research result

Second-Look Relay (SLR-0.2) remains unvalidated. Campaigns begin with $50 and target strictly more than $100 realized, recoverable USD-equivalent after execution, data, funding and conversion costs, before personal taxes. Verified SLR closed positions and doubling campaigns remain zero. Configuration SHA-256: `9bcd83ce0ec71cdae8c410c202bd5a75b1496679e5ddb94ccc7d300e57c3663f`.

The latest completed increment reconciles eight unique PumpSwap events, five buy outflows, exact LP/protocol/creator fees and instruction-dependent gross/net fields. Four buyers already traded the exact target and supply 97.2220091588% of corrected gross buy debit. The fixed Claudia episode has a paid-visibility confounder; failed social requests leave coverage unknown. No return is inferred from those corrections.

This import does not integrate SLR into TARTAR or its paper book. Existing repository results and CodexCoinHunt results have different universes, horizons, cost conventions and observation coverage. They must be reconciled before combining evidence. Closed repository research lanes remain closed.

## Verify the imported tools

The research tests require Python 3.10+ and the standard library. From the repository root:

```bash
(cd codexcoinhunt/research && python3 -m unittest discover -s tests -v)
(cd codexcoinhunt && python3 -m unittest discover -s installer_tests -v)
python3 -m pytest -q
```

The first two commands cover 161 research checks and nine installer checks. Root pytest covers the existing TARTAR suite and is configured separately. The current GitHub Actions sparse checkout/path filter does not include this new subtree; this PR changes no workflows. Run the two explicit subtree commands during review.

Import validation passed all 161 research checks, nine installer checks and 313 root pytest checks, with one root skip. The isolated proxy-using runtime needed the optional `httpx[socks]` dependency; initial missing-`socksio` failures were resolved by installing it in that environment. No existing code was changed. Results are retained in `IMPORT_VALIDATION.json`.

## Desktop continuation

Check out this branch in the Mac's repository clone to read all files without downloading another ZIP. Open the repository as a local project and use `codexcoinhunt/` as the research folder. A Git checkout and the earlier installer-managed `~/Projects/CodexCoinHunt/codex-research/current` are separate copies; preserve local edits when migrating. Future accepted changes arrive by pulling the repository.

This is the complete available project record, not a verbatim conversation export. Original third-party archives not duplicated in the source release remain documented by provenance and compact licensed input; no missing original is invented here.

## Pending research increment

Before this import, source research examined Bluesky's public Jetstream as an alternative to the failed AppView search. The official v2 live tail uses `xrpc.v1.json` and `network.bsky.jetstream.subscribeEvents`; live-tail access requires no authentication, while archival replay uses authenticated HTTP calls. The wire includes create/update/delete operations and inclusive replay cursors. `createdAt` in a post is explicitly client-declared. These properties require as-of availability, version/deletion history and coverage-gap handling before attention-to-buying comparisons.

Primary sources checked October 12, 2026: [Jetstream protocol documentation](https://bsky.network/docs/jetstream/), [official SDK](https://github.com/bluesky-social/bsky/blob/main/packages/jetstream/README.md), [post schema](https://github.com/bluesky-social/atproto/blob/main/lexicons/app/bsky/feed/post.json). No live stream capture, new social observation, collector, new statistical test or payoff was completed in this pending increment. It is a lead for a separately claimed, bounded, paper-only test. Continuous history, paid-status verification, author/community provenance, first-participation evidence, executable quotes, full costs and matched random/attention/momentum account paths remain required.
