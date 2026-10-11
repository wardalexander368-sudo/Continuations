# Gap review, 2026-10-11

AJ asked for "anything we may have missed". This is a fresh-eyes pass over the board, the reviews,
the pre-registrations, the agent and the scheduled jobs, made after the US-only rule (AJ, 10-11).
Paper only. Ranked by effect on the goal (a profitable strategy a US person can run).

| # | Gap | Evidence | Done / owner |
|---|---|---|---|
| 1 | **US spot costs were wrong.** Studies used 0.62%/side (Coinbase's old sub-$10k taker). Since 2026-09-16 Coinbase US Advanced entry fees are **0.50% maker / 0.90% taker**. Alpaca's crypto desk (US, API) is 0.15% / 0.25% plus wider spreads, about **0.39%/side** on the 11 study coins | Coinbase announcement as reported by securities.io and primexbt (2026-09-16); docs.alpaca.markets/docs/crypto-fees; spreads measured from both public books 2026-10-11 ~03:55 UTC (table below) | Addendum with secondary cost lines registered before the US-patterns window (`preregistration/us-patterns/ADDENDUM-2026-10-11-venue-costs.md`). Route choice: autotrade owner |
| 2 | **At Coinbase's real taker fee, neither registered US pattern would have passed its own study.** Both pass at Alpaca's cost or with Coinbase maker orders | Section A | Live route for these must be Alpaca or Coinbase post-only, not Coinbase taker. Autotrade owner |
| 3 | **A US route to altcoin perps is opening.** CFTC no-action letter 2026-05-29: Coinbase may give US customers Deribit's perps. Institutional now, retail "later this year". Deribit lists ~90 crypto perps (116 of its 134 perps added in 2026) | decrypt.co 2026-05-29; Deribit `get_instruments` | Momentum checked on Deribit's coin list (section B). Watch for retail launch: trading-skills lane |
| 4 | **Four registered tests had no final scorer scheduled** (vol-momentum, HLP hold, wick bounce, US patterns); the rest depend on Claude routines up to a year out | `list_triggers`: routines only for HL costs, jevtrader, dip, JLP, pumpflow, xs-momentum | `final-scores` Action (weekly) + `experiments/final_scores.py`; also covers the new Coinbase US-perp momentum test (`cde-vol-momentum`) |
| 5 | **The self-improvement search only explores Hyperliquid momentum**, which can never go live under the US-only rule | `tartar/autotrade/search.py` (one family, HL data) | Autotrade owner: add a US family (Coinbase/Alpaca spot, later Deribit's list) |
| 6 | **Board stale**: Active list from 10-10 23:30, Queue and Blockers from the pump.fun phase, nothing at the top saying where we stand | `handoff/STATUS.md` | "Where we stand" block at the top; Queue/Blockers marked as history |
| 7 | New US instruments not in any survey: Coinbase Derivatives **US500 perp** (2026-08-17, equity perps 0 bp maker / 1 bp taker promo), Kalshi's approved US BTC perp; Deribit also lists SPY/QQQ/gold/oil perps | securities.io; decrypt.co | Trading-skills lane |
| 8 | Health doesn't watch the HL 1h candle cache the wick test needs, or `hl-book.yml` / `autotrade-search.yml` | `autotrade/health.json` (9 checks) | Done by the autotrade owner (3d37766) |
| 9 | Dip rule: −5.95% [−9.64, −2.25] per trade, 9 variants still trade hourly | `autotrade/REPORT.md` | Scored 10-30 by routine; autotrade owner may retire early |
| 10 | **The wick test's 1h candle recording was broken**: `perps-ctx.yml` ran `wick_forward.py --update` without numpy and `|| true` hid the error, so `data/edge-hunt/hl-1h` has not grown since 2026-10-10 18:56 UTC; and `health.yml`'s sparse checkout left out that folder, so its new check showed a false red | git log of `hl-1h`; the update works locally once numpy is installed | Fixed (numpy installed, failure now a visible warning, sparse path added, `tests/test_workflow_deps.py`). HL keeps ~5,000 1h bars, so nothing was lost |
| 11 | **The US momentum candidate needs ~$1,000 legs** (~$8,000 gross) because Coinbase US perp contracts are $54-$2,627 each; its registration also ignores funding | Section C | Trading-skills lane and autotrade owner |

## A. US-spot patterns at real costs

`patterns.py` charges a fixed cost per trade (gross − 2 × cost) and picks each family's rule by the
largest train mean, so a different cost shifts every number by the same amount and never changes which rule
is chosen. Net at cost c = net at 0.62% + 2 × (0.62% − c); checked against the committed 0% and 0.42% runs
(e.g. CAPIT test 7.01% gross → 5.77% at 0.62%). Pass = train > 0 and validation > 0.

| Rule (chosen on train) | Gross train / val / test | Coinbase taker 0.91% | Coinbase maker 0.50% | Alpaca 0.39% |
|---|---|---|---|---|
| CAPIT Z=4 H=24 | +1.56 / +5.08 / +7.01 | train **−0.26: fails** | +0.56 / +4.08 / **+6.01** | +0.78 / +4.30 / **+6.23** |
| VOLSPIKE K=10 H=72 | +1.62 / +3.38 / +2.56 | train **−0.20: fails** | +0.62 / +2.38 / **+1.56** | +0.84 / +2.60 / **+1.78** |
| BREAKOUT N=168 H=72 | +1.33 / +1.23 / +0.14 | fails | +0.33 / +0.23 / −0.86 | +0.55 / +0.45 / **−0.64** |
| OVERSOLD X=15 H=24 | +0.78 / +0.97 / +1.55 | fails | −0.22: fails | 0.00: fails (borderline) |
| WICK, SQUEEZE | train < 0 at every cost above | fails | fails | fails |

Reading: no closed US-spot rule reopens at Alpaca's cost (breakout reaches test and loses there). The
two registered rules only make sense on a cheap route; maker-only fills on Coinbase are an upper bound
(capitulation buys resting at the bid face adverse selection). The test CIs still span zero at every
cost.

Spreads 2026-10-11 ~03:55 UTC, bps (Alpaca / Coinbase): BTC 1.7 / 0.0, ETH 2.0 / 0.4, SOL 9.1 / 0.9,
XRP 12.9 / 0.7, DOGE 32.6 / 3.5, ADA 29.5 / 3.3, AVAX 56.9 / 2.0, LINK 17.5 / 2.3, LTC 62.6 / 2.1,
BCH 60.1 / 3.6, DOT 22.4 / 0.8. One snapshot; Alpaca's alt spreads make it a BTC/ETH/SOL/XRP venue
first.

## B. Momentum on Deribit's coin list

`experiments/deribit_universe.py`, output `data/deribit-universe/report-2026-10-11.txt`. The agent's own
backtest (HL closes and funding, 20 bps/side) with the universe cut to the 84 coins that have a Deribit perp
and ≥ 60 days of HL history:

| Rule | All of HL | Deribit's list | ex best 5 (Deribit) | last 52 wks (HL / Deribit) |
|---|---|---|---|---|
| xs_momentum | +1.03%/wk | +1.03 [−0.51, +2.55] | −0.15 | +0.28 / +0.10 |
| vol_momentum | +1.42 | **+0.68 [−0.52, +1.81]** | −0.08 | +1.14 / **+1.19** |
| search winner (L21 q10) | +2.83 | +2.17 [+0.89, +3.65] | +0.96 | +1.77 / +1.56 |

The coin choice looks ahead (most of the list was added in 2026), and Deribit's own fees and Coinbase's
access fees are unknown, so this only says the momentum book is not dead on that list: the last year is as
good as on HL. If retail access opens, rerun on Deribit's own prices and fees before anything else.

## C. The US momentum candidate (cde-vol-momentum) at real contract sizes

Added after the trading-skills thread registered D3 on Coinbase's 23 US perps (`preregistration/cde-vol-momentum/`).
Books measured 2026-10-11 ~06:55 UTC (`experiments/cde_books.py`, `data/cde-books/books-2026-10-11.txt`):
spreads 2.4 bps (BTC) to 19 bps (AVAX), 24 h volume $23k (SHIB) to $35M (BTC). The registration's 20 bps per side
covers spread plus the published 0.02%+ fee on all but the thinnest. Two things it doesn't cover:

* **Contract sizes are lumpy.** One contract is $54 (SHIB) to $2,627 (NEAR); most are $250-$1,100. Rounding each
  leg to whole contracts, the share of the 23 coins that land within ±25% of an equal-weight leg is 6/23 at a
  $250 leg (12 round to zero), 12/23 at $500, 19/23 at $1,000, 22/23 at $2,000. So the book needs about **$1,000
  per leg (4+4 legs, ~$8,000 gross)** before it resembles the registered rule; below $500 a leg it can't be built.
* **Funding is ignored** in the registration (Coinbase US perps pay funding hourly). Paper results should add it
  once a funding history source is found, as the HL scorers do.

For the autotrade owner and the trading-skills lane: size the paper twin of this rule in whole contracts at
the intended account size, and report the rounding drag beside the registered number.
