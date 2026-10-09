# The automated paper-trading agent (`tartar/autotrade`)

Built 2026-10-09 by the agent-machinery thread for the project goal "a fully automated trading
agent, focused on profitability and self improvement". **Paper, with dry live twins** (see *Going live*). It runs every 5 minutes on GitHub
Actions (`.github/workflows/autotrade.yml`, every 5 minutes since 2026-10-09 23:20 UTC; hourly before) without any Claude session and
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
   cost model. `LiveBroker` books the same and adds a live twin for promoted strategies (*Going live*).
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

## Going live: how a strategy gets from paper to real SOL

Built 2026-10-09 by the go-live thread. Code: `tartar/autotrade/execution.py` (routes),
`broker.py` (`LiveBroker`, `LIVE_DEFAULTS`, `preflight`), tests in `tests/test_autotrade_live.py`.
**Nothing has been signed or sent by the agent; real trading still needs the user's go.**

### The path, step by step

| Step | What happens | Who does it |
|---|---|---|
| 1. Paper | Every strategy starts on paper under its registered rule. | automatic |
| 2. Promoted | The lifecycle promotes it when its registered criteria pass on the agent's own paper book (`lifecycle.py`). The official forward-test scorer stays the authority; check it agrees. | automatic |
| 3. Dry twins | With `mode: dry_live` (the committed default), each new entry of a promoted strategy gets a **dry twin**: a Jupiter quote of the real buy at live size, then a quote of the sell at the paper exit, less network fees. Nothing is signed or sent. Shows what live fills would have been. | automatic |
| 4. Standing approval | The user sets `mode: live` and `live_approved_on: "YYYY-MM-DD"` in `autotrade/config.json`, and the same date as the GitHub Actions secret `TARTAR_LIVE_APPROVED`, plus a route key (below). `python -m tartar.autotrade preflight` must say `"ready": true`. | **the user, once** |
| 5. Live twins | From then on, every promoted strategy's new entries get a **real** twin, without further steps. A demoted or retired strategy stops getting new twins; its open twins still exit with the paper exit. | automatic |

### What a live twin is

The paper book never changes: the strategy keeps being scored on its registered rule and paper costs.
Each paper entry of a promoted strategy is mirrored by a real buy in SOL (size from `live` below),
and the twin is sold when the paper position closes. Each leg goes to `autotrade/fills.jsonl` with
the fill read from the confirmed transaction (SOL spent or received incl. network fee, tokens,
rent, signature, latency) and, at the close, the comparison with its paper twin:
`live_net_return_sol`, `live_net_return_usd`, `paper_net_return`, `live_minus_paper`. REPORT.md
has a *Live twins* section, and each closed trade carries it in `meta.live`.

### Route

`select_route`: Jupiter's Swap API with our own wallet when `TARTAR_WALLET_KEY` is set (no route fee;
the empty token account is closed after each sell, so rent comes back), else PumpPortal Lightning
when `PUMPPORTAL_API_KEY` is set (1% per side; needs `live.lightning_wallet`, the Lightning wallet's
public key, to read fills), else no live trading. `live.route` can pin one. Costs are the execution-cost
thread's (profitability §3.19), not re-measured. A dry run of the real Jupiter path, no key, nothing
sent: `python -m tartar.autotrade dry-swap MINT --sol 0.01` (on CATE 2026-10-09 23:20 UTC the buy built
and simulated cleanly; the quoted round trip was −0.40% before network fees).

### Limits (config `live`, defaults in `LIVE_DEFAULTS`), on top of the paper caps

| Setting | Default | Effect |
|---|---|---|
| `max_trade_sol` / `min_trade_sol` | 0.01 / 0.002 | size of one twin; smaller ones are skipped |
| `budget_sol` | 0.03 | SOL in open twins, all strategies together |
| `reserve_sol` | 0.01 | always left in the wallet for fees and rent |
| `daily_loss_cap_sol` | 0.01 | realized live loss in a UTC day: all live entries stop until `resume-live` |
| `max_trade_loss_pct` | 25% | one twin losing more: that strategy's live entries stop |
| `max_divergence_pct` × `divergence_streak` | 3 points × 3 | live fills worse than paper by more than 3 points three closes in a row: that strategy's live entries stop |
| `max_signal_age_s` | 900 | an entry whose reference price is older is not mirrored |

Also skipped: shadow variants, assets without a Solana mint (perps), shorts, a second twin on a mint
already held. Demoted strategies' twins are sized by `size_factor`. There is no stop-loss inside a
trade: exits follow the registered rule, so the per-trade limit acts after the close.

### Kill switches

* `autotrade/HALT`: everything stops opening (paper and live); exits still run.
* `autotrade/HALT_LIVE` (`python -m tartar.autotrade halt-live "reason"`): live entries stop, paper
  continues, live exits still sell. `resume-live` (or `resume-live STRATEGY`) clears live halts.
* The Actions variable `TARTAR_LIVE_KILL` (any value): same as `HALT_LIVE`, without a commit.
* Removing the `TARTAR_LIVE_APPROVED` secret: no live broker at all. Open twins then become
  **orphans** at their exit (`state.json` `live.orphans`, journal `live_orphan`): their tokens are
  still in the wallet and must be sold by hand. Prefer `HALT_LIVE`, which still sells.

A failed live sell also records an orphan and halts that strategy's live entries.

### Known gaps (decisions for the user)

1. **Cadence: resolved 2026-10-09 23:20 UTC.** The user chose a run every 5 minutes, so dip entries
   reach the broker within ~10 minutes of their bar, inside `max_signal_age_s` (900 s).
2. **Perps.** `xs_momentum`, `pumpflow` and other Hyperliquid rules have no live route. They need a
   Hyperliquid executor and an API wallet (taken by the edge-hunt E thread, 2026-10-09 23:16 UTC).
3. **Lightning** reads fills from chain for its custodial wallet, so `live.lightning_wallet` must be set
   before that route can be used; Jupiter needs only the key.
