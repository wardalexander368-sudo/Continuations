# The automated paper-trading agent (`tartar/autotrade`)

Built 2026-10-09 by the agent-machinery thread for the project goal "a fully automated trading
agent, focused on profitability and self improvement". **Paper, with dry live twins** (see *Going live*). It runs every 5 minutes on GitHub
Actions (`.github/workflows/autotrade.yml`, a job that loops the agent every 5 minutes for ~5.75 h, restarted every 2 h, since 2026-10-10 ~00:30 UTC; hourly before) without any Claude session and
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
| `pumpflow` | `handoff/preregistration/pumpflow/SPEC.md`: reads the pumpflow-paper Action's daily snapshots, long/short PUMP perp at each snapshot's mid, 0.10%/side on turnover + funding; dry perp twins | after 2027-04-08: ≥ 120 trades, block-bootstrap CI > 0, timing part > 0. **Disabled 2026-10-10:** DefiLlama's 25+ h publish delay leaves no backtest edge (edge-hunt.md E1 "publish delay") |
| `jlp_hedged` | `handoff/experiments/jlp_paper.py` (hedged JLP): reads the paper-tests Action's 4-hourly check-ins; long $200 JLP plus SOL/ETH/BTC perp shorts at JLP's deltas, shorts rebalanced when any is off by > 5% of the JLP leg (taker fee on the changed size) + funding; dry twins of all four legs | pending; `jlp_paper.py evaluate --final` after 2027-01-08 is the verdict |
| `vol_momentum` | `handoff/preregistration/vol-momentum/SPEC.md`: the `xs_momentum` class with `scaled: true` (14-day return / std of the last 14 daily returns), same days, costs and funding | at 52 weeks, as registered; `vmom_forward.py --final` stays the authority |
| `hlp_hold` | `handoff/preregistration/hlp-hold/SPEC.md`: $200 in HLP on paper, one closed trade per allTime history point (~14 days), no cost; `kind: vault_hold` | after 2027-04-10: annualised return minus 5% > 0 with block-bootstrap CI > 0 (matches `hlp_forward.py` exactly on 2025-07..2026-09) |
| `cand-xsm-…` | members of the perps-momentum family found by the agent's own search (below), from `autotrade/candidates/` | their file's `success` rule, at 26 weeks; shadow (outside the risk caps, no twins) |
| `dip~drop=…~hold_bars=…` (8) | shadow variants of the dip rule (drop 3/5/8% × hold 2/4/8 h, minus the registered one) | same, with the CI widened for a family of 9 (Bonferroni); outside the risk caps |
| `launch_selector` | disabled slot (`kind: external`) | config `eval` |

Each strategy trades forward from its first run, with no back-filled trades. The official
forward-test scorers (`established_prereg_eval.py`, `xs_momentum_forward.py`) stay the authority for
the registered tests. The agent's verdicts score only its own paper book.

The hedged-JLP test runs in the agent as a basket (`strategies/jlp_hedged.py`, added 2026-10-10) so it
gets dry twins like the signal rules, but its own recorder and scorer (`jlp_paper.py`) stay the record:
the agent's book leaves out the registered test's margin top-ups and 3x margin accounting.

## Self improvement: the weekly candidate search (`autotrade-search.yml`)

Wednesdays 03:30 UTC, `python -m tartar.autotrade search` (`tartar/autotrade/search.py`):

1. **Generates** the perps-momentum family on a grid: lookback 7/14/21/28 days × quantile 3/5/10 ×
   volatility scaling off/on × signal Monday/Thursday × execution lag 1/2 days = 96 rules, minus the two
   already registered (`xs_momentum`, `vol_momentum`), which are backtested for reference.
2. **Backtests** each on Hyperliquid's daily history, delisted perps included (`hl_data.py`: the
   edge-hunt `hl-daily` CSVs, read only, plus fresh candles), with the registered universe, 20 bps per
   side of turnover and actual funding (daily sums cached in `autotrade/search/funding_daily.csv`). The
   engine reproduces `vmom_forward.py` exactly (+2.17%/week on 2026-01-05..09-28, funding off).
3. **Judges**: the last 26 weeks are held out. A rule survives only if (a) on the train weeks its
   one-sided block-bootstrap lower bound at level 0.10/M is above 0, with M = every distinct rule the
   search has ever tested (Bonferroni, cumulative across runs); (b) its mean is positive in each third of
   the train weeks (walk-forward stability); (c) the holdout mean is positive and at least half the
   train mean; (d) its weekly returns correlate below 0.9 with each registered rule.
4. **Queues** up to 3 survivors a run (8 waiting or running at most) as draft pre-registrations,
   `autotrade/candidates/<name>.json` (rule, backtest numbers, success rule, start date). The commit
   that adds the file is the registration. After `WAIT_DAYS` (7) the agent adds it as a paper
   strategy (`runner.py` → `search.active_candidates`), and the normal lifecycle scores it at 26 weeks
   with the CI widened by Bonferroni over every candidate ever queued. To withdraw one, set its
   `status` to `withdrawn`.

`autotrade/search/REPORT.md` shows the latest run (top rules, why each failed); every tested rule and
its numbers are appended to `autotrade/search/tested.jsonl`. Promoted candidates are still shadow (no
twins); making one eligible for live twins is a deliberate config change.

## Health (`health.yml`, hourly)

`python -m tartar.autotrade health` (`health.py`) checks the repo's unattended jobs and writes
`autotrade/health.json`; the agent puts it at the top of REPORT.md (🔴 / 🟡 / 🟢, only the non-green items
listed). The Action **fails while anything is red**, so GitHub emails the repository owner.

| Check | Red when |
|---|---|
| Each Action (autotrade, recorder, paper-tests, pumpflow-paper, perps-ctx) | its latest finished run failed, or no run started within its cadence (skipped or stuck); never run = yellow |
| Recorder hours | any UTC hour from 2026-10-09 21:00 to two hours ago has no asset in its day's `raw-gha-*` release |
| Paper-test inputs | newest JLP snapshot > 9 h, dip cohort > 28 h, pumpflow snapshot > 54 h, HL OI/funding snapshot > 9 h old |
| Agent | any live orphan or live halt; twins whose last 10 closes have a median twin − paper below −3 points are yellow |

A health file more than 3 h old shows as at least yellow in REPORT.md (the health job itself may be stuck).

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

**Sending (both routes, `execution.py`).** Only a `live` broker with the approval matching builds a
signing executor. Before signing, `check_tx` refuses any transaction whose fee payer isn't our wallet
or that needs a second signer. A sent order ends confirmed (fill read from the chain), failed (error
on chain, or Jupiter's blockhash expired without it landing: nothing moved), or **unknown** (no answer
in time, or no reply from Lightning). The broker treats unknown as possibly filled: the leg goes to
`live.orphans` with its signature and the strategy's live entries halt until someone checks the
signature and runs `resume-live`. Lightning sells are sized to the twin ("100%" only when the twin is
all the wallet holds). `dry-swap MINT --route lightning` simulates the Lightning order via PumpPortal's
trade-local endpoint for a stand-in wallet. Checked 2026-10-10 01:50 UTC: Jupiter on BONK built and
simulated both legs; Lightning on a PumpSwap token built and simulated the buy, and the sell built
and failed only on the stand-in's missing token account (expected). Tests: `tests/test_execution_send.py`.

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

Also skipped on the SOL route: shadow variants, assets without a Solana mint, shorts, a second twin on
a mint already held. Perp strategies have their own route (next section). Demoted strategies' twins are sized by `size_factor`. There is no stop-loss inside a
trade: exits follow the registered rule, so the per-trade limit acts after the close.

### Perp twins (Hyperliquid)

Built 2026-10-09 by the edge hunt E thread: `tartar/autotrade/perps.py`, hooks in `broker.py`, tests in
`tests/test_autotrade_perps.py`. A strategy's intent with `meta["venue"] == "hyperliquid"` (xs_momentum's
legs, pumpflow, the hedged-JLP shorts) gets a **perp twin** instead of a SOL twin: a long or short
on Hyperliquid at a USD notional, with the same paper-book-unchanged design, kill switches and
`fills.jsonl` comparison (`perp_open`, `perp_close`; `compare.live_net_return_usd` against
`paper_net_return`, fees and funding broken out). REPORT.md shows them in their own table.

* **Dry (mode `dry_live`, now):** each leg is the order walked through Hyperliquid's live L2 book at that
  moment as a taker (size rounded to the coin's step, $10 minimum), plus the 0.045% taker fee; funding
  over the hold from Hyperliquid's history. Nothing is signed or sent, no account. Because nothing is at
  risk, `perps.dry_all` (default on) mirrors every non-shadow perp strategy, promoted or not, so
  xs_momentum's weekly legs start producing real-book fills from its next Wednesday.
  By hand: `python -m tartar.autotrade dry-perp PUMP --usd 12 --side -1` (2026-10-09 23:45 UTC: PUMP
  short round trip −0.11%, BTC long −0.09%: the 0.09% fee plus ~1-2 bps of spread at $12).
* **Kept legs:** a weekly rebalance that keeps a leg closes and reopens it on paper at no cost; the twin
  rolls instead (marked at the book's mid, `perp_roll_out` / `perp_roll_in`, no fee), as a real
  account would simply hold it.
* **Limits (config `live.perps`, defaults `perps.PERP_DEFAULTS`):** $12 per twin (min $10, Hyperliquid's
  minimum order), $60 notional across open perp twins, $6 daily realized loss cap (halts all live
  entries), 25% per-twin loss and 3 points × 3 closes divergence halts per strategy, reference prices
  up to 2 days old (weekly rules book a day late).
* **Live: built 2026-10-10, never used on mainnet.** `tartar/autotrade/hl_exchange.py`: immediate-or-cancel
  limit orders 1% through the mid (`live.perps.slippage`), size floored to the coin's step, $10 minimum,
  closes reduce-only, fees read back from `userFills`. Signed with Hyperliquid's L1 EIP-712 scheme
  (needs `pip install .[live]`: `eth-account`, `msgpack`). It sends only past the **live gate**
  (`tartar/autotrade/gate.py`, shared with the Solana senders): mode `live`, `live_approved_on` ==
  `TARTAR_LIVE_APPROVED`, and both `HYPERLIQUID_AGENT_KEY` and `HYPERLIQUID_ACCOUNT`; the gate is
  re-checked before every order, opens also stop on `HALT`/`HALT_LIVE`/`TARTAR_LIVE_KILL`, closes don't
  (so a halted agent can still flatten). A failed close becomes an orphan and halts the strategy, as for
  dry twins. A Solana key is no longer needed for perp-only live trading. Hedged-JLP basket shorts stay
  on paper in mode `live` because the JLP leg has no live sender (a hedge alone would be a bet).
  **Tested:** offline (`tests/test_autotrade_hl.py`) and on Hyperliquid **testnet** by the Action
  `hl-testnet.yml` with a throwaway key generated inside the test: an order sent through the whole agent
  path comes back "User or API Wallet <our address> does not exist", i.e. the exchange recovered exactly
  our signer (a tampered signature recovers a different address). Real fills were not tested: a fresh
  key has no testnet funds, and testnet USDC is only claimable by an address that has deposited on
  mainnet. **To go live, from the user:**
  1. a Hyperliquid account with USDC deposited (the trading account); eligibility to use Hyperliquid is
     the user's to check;
  2. an **API wallet** ("agent") created and approved in that account (Hyperliquid → API), its private
     key as the GitHub Actions secret **`HYPERLIQUID_AGENT_KEY`** (can trade, cannot withdraw);
  3. the trading account's address as the secret or variable **`HYPERLIQUID_ACCOUNT`**;
  4. optionally first: the same on testnet (claim test USDC from that account) and run `hl-testnet.yml`
     with `HYPERLIQUID_*` pointing at it to see real testnet fills;
  5. then `live_approved_on` + `TARTAR_LIVE_APPROVED` and mode `live`, the same go as for SOL twins.

### Basket twins: the hedged JLP (JLP on Jupiter + three Hyperliquid shorts)

Built 2026-10-10: `strategies/jlp_hedged.py`, `usd_spot.py`, basket sizing in `broker.py`
(`LiveBroker.usd_size`), tests in `tests/test_autotrade_jlp_hedged.py`. Every leg's intent carries
`meta.basket = "jlp"` and `meta.twin_usd`, the twin size that keeps the legs in proportion
(`twin_basket_usd` × each coin's share; $200 now, so about JLP $200, SOL short $88, BTC $25, ETH $15).

* **JLP leg** (`venue: jupiter_usd`): a USD spot twin. Dry: Jupiter's USDC→JLP quote at entry and JLP→USDC
  at exit, plus $0.003 network fee per leg (`usd_buy` / `usd_sell` in `fills.jsonl`, own table in
  REPORT.md). A failed exit quote becomes an orphan and halts the strategy, as for SOL twins.
* **Short legs** (`venue: hyperliquid`): ordinary perp twins (above), sized by `twin_usd` instead of
  `max_leg_usd`. Each rebalance closes and reopens the three shorts.
* **Limits:** basket legs count against `live.perps.basket_budget_usd` ($500), separate from the $60
  single-leg perp budget, and a basket leg is skipped rather than shrunk if the budget can't fit its
  full size. The perp daily loss cap, per-twin loss and divergence halts, `HALT`, `HALT_LIVE` and
  `TARTAR_LIVE_KILL` all apply to every leg.
* Checked 2026-10-10 against the live venues on a scratch root: all four dry legs filled (JLP $200 quote,
  SOL $87.48, BTC $23.93, ETH $15.18 after Hyperliquid's size rounding).
* **Going live would need, from the user:** `TARTAR_WALLET_KEY` with USDC in that Solana wallet for the
  JLP leg (and a little SOL for fees); a Hyperliquid account with USDC margin plus `HYPERLIQUID_AGENT_KEY`
  and `HYPERLIQUID_ACCOUNT` for the shorts (see Perp twins); roughly $330 of capital at the $200 twin
  size (JLP $200 plus about $43 of margin at 3x, more for a buffer). **On our side, not built:** a live
  USDC swap sender (Jupiter Swap API signed with the wallet key; the Hyperliquid sender now exists), and a
  leg-failure rule (if one leg of an entry or rebalance fails, unwind the others or halt) since a live
  basket with a missing hedge is directional. Mode `live` today skips both routes, so the basket stays on paper.

### Restarts and overlaps (`safety.py`)

* **One trader.** The workflow's concurrency group never cancels the running job, so the next one waits.
  A per-checkout lock stops two processes on one machine. In mode `live` a lease in `state.json`
  (holder = the GitHub run id, renewed every run, released when the loop ends, free after 10 min)
  makes any other holder skip its run.
* **Pending before sending.** Each live buy and sell is written to `autotrade/pending.json` before
  it is sent and removed once its fill is logged. A failed run still commits `autotrade/`.
* **No double buys.** A buy's order id is `strategy|key|signal time`. If a run dies after buying,
  the next run claims those tokens under that id, and when the strategy re-emits the entry the twin
  adopts them instead of buying again (unclaimed after 1 h: orphan + halt). If a run dies after a
  sell landed, the twin is closed as `sold_unrecorded` instead of being sold twice.
* **Reconcile before trading.** Every live or dry_live run first compares the wallet's holdings of
  every mint the fill log or a pending order names with the book (open twins, orphans, claims).
  Tokens nothing explains become an orphan and halt live entries. Missing tokens do the same, unless a
  pending sell explains them. A SOL drop since the last run that the book can't explain counts
  against the live daily loss cap and halts live entries. If the wallet can't be read, live entries
  halt and paper continues.
* **Perp and basket legs (Hyperliquid).** Every order carries a client order id fixed by what it is
  for: the entry (strategy, key, coin, side, signal time), or the position it closes. Before sending,
  the broker looks that id up on the venue. If an earlier order with it filled, that fill is adopted
  and nothing is sent; if the lookup fails, nothing is sent. Each run first compares the account's
  positions and open orders with the book: open twins, kept legs being handed over, perp orphans,
  plus orders a dead run filled that are waiting to be re-adopted (1 h, then orphan). Any difference,
  or an unreadable account, stops perp entries (`live.perps_halted`). Closes still run, reduce-only.
  `resume-live perps` clears the halt.
* The dry routes simulate the wallet (`autotrade/dry_wallet.json`) and the Hyperliquid account
  (`autotrade/dry_perp_account.json`), seeded from the twins already in the book, so all of this
  runs end to end in `dry_live`. `tests/test_restart_safety.py` and
  `tests/test_perp_restart_safety.py` kill runs before and after a buy, sell, perp open and perp close
  lands. The basket's JLP leg (USD spot) is dry-only and not covered yet.

### Kill switches

* `autotrade/HALT`: everything stops opening (paper and live); exits still run.
* `autotrade/HALT_LIVE` (`python -m tartar.autotrade halt-live "reason"`): live entries stop, paper
  continues, live exits still sell. `resume-live` (or `resume-live STRATEGY`) clears live halts.
* The Actions variable `TARTAR_LIVE_KILL` (any value): same as `HALT_LIVE`, without a commit.
  The loop job reads it (and the secrets) only when it starts, so it can take up to ~6 hours to
  bite; a committed `HALT_LIVE` is picked up by the next 5-minute iteration (each one pulls main).
* Removing the `TARTAR_LIVE_APPROVED` secret: no live broker at all. Open twins then become
  **orphans** at their exit (`state.json` `live.orphans`, journal `live_orphan`): their tokens are
  still in the wallet and must be sold by hand. Prefer `HALT_LIVE`, which still sells.

A failed live sell also records an orphan and halts that strategy's live entries.

### Known gaps (decisions for the user)

1. **Cadence: resolved 2026-10-10.** The user chose a run every 5 minutes as a self-looping job
   (GitHub's `*/5` cron fired once in 30 minutes), so dip entries
   reach the broker within ~10-20 minutes of their bar, inside `max_signal_age_s` (1800 s since the 2026-10-10 audit).
2. **Perps.** Dry perp twins exist (*Perp twins* above); real ones need the user's Hyperliquid API
   wallet (`HYPERLIQUID_AGENT_KEY`, `HYPERLIQUID_ACCOUNT`) and a live executor that isn't written yet.
3. **Lightning** reads fills from chain for its custodial wallet, so `live.lightning_wallet` must be set
   before that route can be used; Jupiter needs only the key.
