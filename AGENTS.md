# AGENTS.md: rules for ChatGPT / Codex in this repo

You are the **ChatGPT lane** of the TarTrade project. Several Claude sessions also work here.
Claude reviews every pull request you open before anything reaches `main`. Read this file, then
`handoff/STATUS.md` (the board) and the topic document for your task (`handoff/autotrade.md` for the
trading agent, `handoff/edge-hunt.md` for research).

## Goal
Make the project profitable on venues a US person can use. Trust evidence: test before betting, count
every real cost (fees, spread, slippage, latency), and drop ideas that don't make money.

## Hard rules
1. **Never push to `main`.** Work only on a branch named `codex/<short-topic>`, made from the latest `main`,
   and open a pull request into `main`. One task per PR; keep PRs small.
2. **Never commit secrets.** This repository is PUBLIC. No API keys, wallet keys, seed phrases, tokens or
   `.env` files. Read keys from environment variables only.
3. **Paper only.** Do not add or enable anything that spends real money, signs real transactions, or sends
   orders to a live (non-paper) endpoint. Alpaca code must keep using the paper endpoint.
4. **US-only.** Live-intended strategies must use venues a US person may use. Hyperliquid and Jupiter are
   research only (`us_only: true` in config must stay on).
5. **Don't touch the live paper book.** The hourly bot commits these to `main`; never edit them:
   `autotrade/{state.json,journal.jsonl,trades.jsonl,equity.jsonl,REPORT.md,health.json,changes.jsonl,alpaca_fills.jsonl}`
   and `autotrade/HALT`.
6. **GitHub Actions:** no always-on, looping or self-restarting workflows, and no new schedules more often
   than hourly. Ask in the PR before adding or changing any workflow.
7. **Don't take claimed work.** Check *Active* in `handoff/STATUS.md`. Only work on what the ChatGPT lane
   holds there, or propose a new claim in your PR description.
8. **Pre-registered tests are frozen.** Don't edit anything under `handoff/preregistration/` except to add
   a clearly dated addendum file.

## Each PR must
* Pass `pytest` (`pip install -e .[dev]` or see `.github/workflows/tests.yml`); add tests for new code.
* Explain in the description: what changed, why it should make money or reduce risk, the evidence
  (backtest numbers after costs, sample size), and how you tested it.
* Add one line under the ChatGPT lane in `handoff/STATUS.md` *Active* saying what the PR does. Keep the
  edit small; other lanes edit that file too.

## Review
Claude reviews each PR and replies with requested changes or approval. Address review comments with new
commits on the same branch (no force-push). Approved PRs are merged into `main` by Claude.
