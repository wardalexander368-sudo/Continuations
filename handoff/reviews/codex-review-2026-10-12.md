# Review of everything Codex added, 2026-10-12

AJ asked (2026-10-12 19:08 UTC) for a review of everything Codex (ChatGPT) has added to this repository, to find
what can improve the project. Reviewed by Claude, thread "Codex review and project layout".

## What Codex added

One branch, `codex/codexcoinhunt-import-20261012` (3 commits, 441 files, ~71k lines, ~47 MB; no PR opened).
Nothing from Codex had reached `main` before this review. Contents:

* `codexcoinhunt/`: AJ's CodexCoinHunt project, a paper-only Solana memecoin study. Its strategy, SLR-0.2
  ("Second-Look Relay"), buys pump.fun/PumpSwap tokens on a second wave of attention and aims to turn $50 into
  more than $100 after all costs. Code (stdlib Python plus a small Node quote probe), raw public evidence,
  results, preregistrations, 161 tests, a Mac installer, and earlier versions.
* `CONNECTED_PROJECTS.md/.json`, `handoff/codexcoinhunt.md`, `handoff/northstar.md`, `handoff/connected-external.md`:
  a map of AJ's other projects (links only, no code).
* One line in `README.md` and two lines under the ChatGPT lane in `handoff/STATUS.md`.

## Checks

* Tests: the subtree's 161 research checks and 9 installer checks pass; the repo's `pytest` passes (313 passed,
  1 skipped) with the import in place. Root `pytest` does not collect the subtree (testpaths = `tests`).
* Secrets: none found. `collect_pumpportal.py` reads `PUMPPORTAL_API_KEY` from the environment. Long base58
  strings are public transaction signatures and wallet addresses.
* Rules: paper only, no order route, no workflow change, no edit to the paper book or to frozen preregistrations.
* Privacy (AJ to decide): 16 files contain AJ's Mac home path, which includes a full name. The branch is already
  public on GitHub, so merging does not expose anything new; removing it would mean rewriting those files.
* Size: ~47 MB (a 28 MB compressed CSV). The objects are already in the repository via the pushed branch.

**Verdict: land it as a separate research archive** (merged as-is with a merge commit). It is AJ's own work,
self-contained and harmless to the agent. It is **not** wired into the agent or the paper book.

## Can SLR-0.2 make us money?

Not now. Its own record says zero verified positions, zero doubled campaigns and zero trained models; every
challenger it ran (revival, order book, signed flow) lost after costs or never fired. It also sits in a lane this
project closed on evidence: buying pump.fun tokens costs ~3-5.5% a round trip (`profitability.md`, real-cost
tests 10-09/10), and the dip rule lost -5.2%/trade in paper. Reopening needs a forward result that beats those
costs, which CodexCoinHunt does not have.

## What we can reuse

1. **Pin frozen configurations by hash.** CodexCoinHunt records a SHA-256 for its frozen strategy config. We now do
   the same for `handoff/preregistration/` (`FROZEN.sha256`, `tests/test_prereg_frozen.py`), so an edit to a frozen
   protocol fails CI instead of relying on review. Done in this review.
2. **Matched random controls.** Every CodexCoinHunt arm is judged against random entries under the same rules. Our
   dip scorer already reports "excess over random entries"; the US registrations do not. Adding a random-entry
   control to `us_capit` scoring (same coins, same hold, random hours) tells a real bounce from market drift with
   few crash days. Plan item A2.
3. **Measured cost beats modelled cost; count each fee once.** Their PumpSwap audit found fees double-counted when
   event fields and SDK quotes were added together. Our PumpSwap decoder already handles the instruction-specific
   fields (`tartar/feeds/pumpswap.py` lines 13-14) and `pumpswap_fees.py` derives fees from reserves, so no fix is
   needed. The lesson for the US book is to judge cost from Alpaca paper fills, not the assumed 0.39%. Plan item A1.
4. **Unknown is not zero.** A failed data fetch is recorded as a gap, never as "no activity". Worth keeping in mind for
   collectors; no current bug found.
5. **Account return, not summed trade percentages.** Their audit of a published track record found that +117.7% of summed
   trade returns did not mean the account doubled: at a 14% stake per trade, $50 compounded to about $53.34. Our REPORT already shows USD P&L per strategy; the live-rule gate
   should be judged in account dollars too. Plan item A3.

Not reused: the Bluesky social feed idea needs a continuous collector (barred on GitHub Actions) and serves the
closed memecoin lane; DexScreener paid-boost data serves the same lane; Northstar has no source in the repository.
