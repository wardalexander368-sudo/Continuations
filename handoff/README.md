# handoff/: what each document is

The board is [`STATUS.md`](STATUS.md): read it first. Every finding is in [`findings.md`](findings.md). The plan is [`plan-2026-10-12.md`](plan-2026-10-12.md).
The repository map is in the top-level [`README.md`](../README.md).

## Current topic documents

| Document | What it covers |
|---|---|
| [`STATUS.md`](STATUS.md) | The board: where we stand, active lanes, recent log |
| [`findings.md`](findings.md) | **Findings ledger:** every idea Claude or Codex tested, status, evidence after costs, where it lives |
| [`research/OPERATING-PRINCIPLES.md`](research/OPERATING-PRINCIPLES.md) | Retained research rules; evidence, chronology, accounting and bounded complexity |
| [`research/IMPROVEMENT-BACKLOG.md`](research/IMPROVEMENT-BACKLOG.md) | Prioritized research changes and acceptance evidence; planning card and composition proposal alongside |
| [`reviews/agentic-research-2026-10-14/REPORT.md`](reviews/agentic-research-2026-10-14/REPORT.md) | Full three-PDF review, source corrections, version limits and project comparison |
| [`plan-2026-10-12.md`](plan-2026-10-12.md) | Implementation plan, in order, with owners |
| [`autotrade.md`](autotrade.md) | The hourly paper-trading agent (`tartar/autotrade/`), its strategies and risk books |
| [`edge-hunt.md`](edge-hunt.md) | Every strategy family tested, with results (§K-§N are the US work) |
| [`live-rule-us.md`](live-rule-us.md) | v2 sizing/cost-measurement rule for `us_capit`, adopted 2026-10-12, SUSPENDED by AJ 2026-10-15; authorizes nothing |
| [`hl-costs.md`](hl-costs.md) | Hyperliquid execution costs from the `hl-book` collector |
| [`profitability.md`](profitability.md) | `tartar profit` and the pump.fun-phase cost findings |
| [`candle-prediction-agent.md`](candle-prediction-agent.md) | The candle predictor (`tartar watch`) |
| [`jevtrader.md`](jevtrader.md) | AJ's separate jevtrader and how it relates |
| [`codexcoinhunt.md`](codexcoinhunt.md) | The CodexCoinHunt import (ChatGPT lane), `../codexcoinhunt/` |
| [`northstar.md`](northstar.md), [`connected-external.md`](connected-external.md) | Codex's notes on AJ's other projects (links only) |

## Folders

| Folder | What it holds |
|---|---|
| `preregistration/` | Frozen test protocols. Never edit; add a dated `ADDENDUM-*` file. `FROZEN.sha256` pins them (`tests/test_prereg_frozen.py`) |
| `reviews/` | Dated reviews and audits; the newest are `codex-review-2026-10-12.md` and `overall-2026-10-11.md` |
| `experiments/` | Research and scoring scripts; some are run by the Actions (`final_scores.py`, `pumpflow_paper.py`, `jlp_paper.py`, `edge-hunt/perps/*`) |
| `data/` | Research data and collector output (`data/README.md`) |
| `live/` | The retired fast loop's policy and reviews (10-09) |
| `archive/` | Retired documents and board history; nothing there is current |

Scripts and data stay in `handoff/` because frozen registrations and workflows name these paths.
