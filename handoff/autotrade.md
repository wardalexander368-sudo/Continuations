# The automated paper-trading agent (`tartar/autotrade`)

Built 2026-10-09 by the agent-machinery thread for the project goal "a fully automated trading
agent, focused on profitability and self improvement". **Paper only.** It runs hourly on GitHub
Actions (`.github/workflows/autotrade.yml`, :15 past each hour) without any Claude session and
commits its state to `autotrade/`. Read `autotrade/REPORT.md` for the current picture.

## What one run does

1. Loads `autotrade/config.json` and the book (`autotrade/state.json`).
2. The first time it sees a strategy (or variant), it logs a `registered` row in
   `autotrade/changes.jsonl` with the rule and the success criteria. This is its own
   pre-registration, written before any data for that strategy exists.
3. Steps every strategy that isn't halted. The strategy fetches its data and returns intents
   (open or close, at a price and time taken from market data). Strategies keep a cursor, so a
   bar is acted on once, and a late or missed run only delays fills.
4. Risk check on every open (`risk.py`): kill switch, max position, max open per strategy and in
   total, max gross. Closes always go through.
5. Fill (`broker.py`): `PaperBroker` books the intent at the reference price less the strategy's
   cost model. `LiveBroker` refuses unless every live condition holds (below).
6. Marks open positions. A day below `-daily_loss_cap_usd` (realized + unrealized) halts the
   agent. Three consecutive errors halt a strategy.
7. Lifecycle (`lifecycle.py`) scores each strategy's closed trades against its registered rule
   and moves it: paper → promoted / retired, promoted → demoted, demoted → promoted / retired.
   Every move is logged with its numbers.
8. Writes `REPORT.md`, `equity.jsonl` (one row per run), `journal.jsonl` (every fill, rejection
   and error) and `trades.jsonl`.

A run that newly halts the agent or a strategy fails the Action after committing, so GitHub emails
the repository owner.

## Strategies now

| Name | Rule | Scored |
|---|---|---|
| `dip` | `handoff/preregistration/dip-rolling/SPEC.json`, every cohort pool, 5-minute bars from GeckoTerminal; registered costs, plus a secondary figure at measured pool fees | at 200 trades or 21 days: excess over random entries CI > 0 and mean > 0 |
| `xs_momentum` | `handoff/preregistration/xs-momentum/SPEC.md`, Hyperliquid perps, booked each Wednesday for Tuesday's close; turnover costs + funding | at 52 weeks: mean weekly > 0 and block-bootstrap CI > 0 |
| `dip~drop=…~hold_bars=…` (8) | shadow variants of the dip rule (drop 3/5/8% × hold 2/4/8 h, minus the registered one) | same, with the CI widened for a family of 9 (Bonferroni); outside the risk caps |
| `launch_selector` | disabled slot (`kind: external`) | config `eval` |

Each strategy trades forward from its first run, with no back-filled trades. The official
forward-test scorers (`established_prereg_eval.py`, `xs_momentum_forward.py`) stay the authority for
the registered tests. The agent's verdicts score only its own paper book.

## Execution check (real route vs the cost model)

With `execution.quote_check` on, each fresh entry on a Solana token gets two Jupiter quotes of the
same token: the full USD size and a $1 probe. The measured impact is the full-size shortfall against
the probe (`jup_impact_measured_pct`). Jupiter's own `priceImpactPct` is kept as
`jup_reported_impact_pct` but not used, because it already reads 0.7-2.6% at $1 (checked
2026-10-09). At close, `quoted_net_return` re-prices the trade at the measured impact on both sides,
and the dip verdict and REPORT.md show it beside the registered figure. First check: deep pools
match the model (0.14% vs 0.15%, 0.18% vs 0.16%); a thin one was more than twice it (2.9% vs 1.2%).

## Adding a strategy

* **From another thread's signals:** set `enabled: true` on `launch_selector` (or copy it under a new
  name) and append JSON lines to its `signals` file, one per open or close (format in
  `strategies/external.py`). Copy the registered criteria into `eval`.
* **As code:** implement `step`, `marks`, `evaluate` (and optionally `describe`) as in
  `strategies/dip.py`, register the kind in `strategies/__init__.py`, add it to the config, and add a
  test with fake data (`tests/test_autotrade.py`).

## Operating it

* **Kill switch:** commit `autotrade/HALT` (its text is the reason). New entries stop; exits still run.
  Delete the file to resume. Locally: `python -m tartar.autotrade halt "reason"` / `resume`.
* **Resume a halted strategy:** `python -m tartar.autotrade resume NAME` (resets its error count).
* **Don't run it locally against `autotrade/`**: the Action owns that state. Use
  `--root /some/tmp/dir` (copy the config there).

## Going live (not done; needs the user's explicit go)

`LiveBroker` refuses unless: config `mode: live`, `live_approved_on` set to a date, the environment
variable `TARTAR_LIVE_APPROVED` equal to that date, `TARTAR_WALLET_KEY` present, and the strategy
`promoted`. Even then it raises "not wired yet". The remaining work is to build it on
`handoff/experiments/jupiter_fills.py` (Jupiter Swap API with our own key, profitability §3.19)
after a verified 0.01 SOL round trip. Perps (Hyperliquid) would need their own live path.
