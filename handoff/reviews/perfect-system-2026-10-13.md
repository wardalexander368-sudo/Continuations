# The perfect trading system for us, and how ours compares (2026-10-13)

AJ (2026-10-13 05:25 UTC): "Come up with what you think the perfect trading system would look like and compare it
to what we have." Written by thread "Perfect trading system vs ours" from the repo as of `906695f`; no new
backtests. "Perfect" here means the ideal for **our** situation: a US person, a small stake ($100-$1,500), venues a
US person may use, an hourly GitHub runner with no always-on jobs, and AJ's word before any real money. A fund's
stack would differ; that is noted at the end.

## Headline

**Our machinery is close to the ideal for a small US account; what we lack is edges.** Validation, cost
accounting, risk limits, kill switches and the live gate are what a careful small trader would build, and in places
stricter. The perfect system's defining feature is several independent edges that each clear their real cost and
fire often enough to tell luck from skill. We have one candidate (`us_capit`) that fires on ~6 crash days a year,
on a venue that charges ~0.39%/side, which caps stage 1 at about +$25-50 a year (`live-rule-us.md` §7). Closing
that gap matters more than any amount of engineering.

## What the perfect small US system looks like

1. **Edges that are structural and cheap to trade.** Each one has a reason to exist (someone pays to transact:
   forced sellers, liquidity demand, risk transfer), works on a horizon long enough to clear its venue's cost, and
   fires dozens of times a year on independent occasions.
2. **Several of them, not correlated.** So the book has enough events per year to judge each edge and the account
   is not one bet on one kind of day.
3. **The cheapest venue for each edge.** Costs decide almost every result here (`findings.md` bottom line), so the
   venue is part of the edge.
4. **Honest validation.** Every idea logged, pre-registered before its forward window, a family-wide multiple-testing
   bar, out-of-sample universes, random-entry controls, measured (not assumed) costs, and judgement in account
   dollars.
5. **Execution that matches the signal's timing.** Orders go out within the window the backtest assumed, priced
   against the live book, with every fill measured against the model.
6. **Risk limits that cannot be skipped.** Per-trade and total exposure caps, dollar loss stops, a kill switch, and a
   broker check every run that the account holds exactly what the book says.
7. **Monitoring that reaches a human.** A red signal in minutes for a broken job, a stuck position or a cost drift.
8. **Self-improvement that adds evidence, not parameters.** New ideas enter as new registrations; nothing retunes
   itself on a handful of live trades.
9. **Capital that follows evidence.** Small stakes until the edge is shown on real fills, then staged increases with
   a human sign-off, sized well under Kelly.

## Component by component

| # | Component | What we have (repo) | Gap to the ideal | Worth closing now? |
|---|---|---|---|---|
| 1 | **Edge discovery** | Ledger of every idea tested by Claude and Codex (`handoff/findings.md`); dozens closed after costs. One US candidate, `us_capit` (`tartar/autotrade/strategies/coinbase_pattern.py`); `us_volspike` and `cde_vol_momentum` collect paper with low priors. | **The big gap.** One edge, ~6 events a year, on a 0.39%/side venue. Every search so far has been crypto (plus S&P trend timing, closed). The one cheap US venue never tested is US stocks and ETFs on Alpaca: no commission and ~1-5 bp spreads on liquid names, about a tenth of Alpaca crypto's cost, with hundreds of names giving more independent events. | **Yes: one cheap study** (top gap 1 below). |
| 2 | **Validation and overfitting control** | Frozen pre-registrations (`handoff/preregistration/FROZEN.sha256`, `tests/test_prereg_frozen.py`); out-of-sample universe check (`wide_coins.py`, volspike failed it); random-entry control offline (`handoff/experiments/edge-hunt/patterns/random_entry.py`) and live (`coinbase_pattern.py` CONTROL, REPORT line); Bonferroni-style family bar in the search (`tartar/autotrade/search.py` `judge`); Codex replication of CAPIT by whole episode (`reviews/capit-robustness-2026-10-13.md`). | Essentially none in method. The limit is sample size: no US registration can clear its 90% bar inside 52 weeks, and 60% of CAPIT's modelled gain is one episode. Nothing in code fixes that; only more events (gap 1) does. | No further work. |
| 3 | **Execution and costs** | Paper book with registered cost model plus venue-cost columns (`config.json` `venue_costs`); Alpaca **paper** mirror with measured fills (`tartar/autotrade/alpaca.py`, paper URL only, line 21); Coinbase US perp book recorded at capit fills (`cde_book.py`); per-coin cost screen (`live-rule-us.md` §3). Hourly runner (`.github/workflows/autotrade.yml` cron `5 * * * *`), market orders. | **Latency.** CAPIT earns +4.11%/trade at a 15-min entry, +2.97% at 30 min, +1.93% at the ~90 min an hourly run gets (`reviews/timing-2026-10-11.md`): the runner gives up about a third of the edge. The ideal reacts within minutes. Limit orders and perps would cut cost further. | Already on file as AJ calls: the ~$5/mo always-on box (live rule §6 says revisit at $200+/trade; `us_capit_fast` vs `us_capit` on paper measures the gap), Alpaca limit orders live, Coinbase perps (needs a bigger stake). **Nothing new to raise.** |
| 4 | **Risk and kill switches** | Kill switch file `autotrade/HALT` and caps (`tartar/autotrade/risk.py`); daily loss cap; separate hl/us books with drawdown and weekly stops (`perp_risk.py`); error halts with 6 h retry; one gate for anything signed with real keys (`tartar/autotrade/gate.py`); live rule stops in account dollars ($250 loss, mean, cost, unmatched order writes HALT). | The live rule's stops exist on paper only: the "unmatched order or stuck position writes HALT" check is not code yet, because the live route isn't built. The Alpaca mirror reads one position at close (`alpaca.py` line 90) but never compares the whole account with the book. | **Yes, small** (top gap 2): rehearse the reconciliation on the paper account now, so it is proven before money. |
| 5 | **Monitoring** | Hourly health checks that fail the Action while anything is red, so GitHub emails AJ (`.github/workflows/health.yml` line 3, `tartar/autotrade/health.py`); REPORT with gate line, random-entry line and US book summary; `changes.jsonl` for every lifecycle or risk move. | Alerts are hourly and email-only; the ideal is minutes. At $100 a trade with 24 h holds, an hour is fine. | No. |
| 6 | **Self-improvement** | Lifecycle statuses on registered criteria (`tartar/autotrade/lifecycle.py` `decide`); weekly candidate search over HL and Coinbase-perp momentum families with a family-wide bar (`search.py`, `autotrade-search.yml`); quarterly regime check (`agent_regime.py`, from January 2027). | The search only covers momentum families; it never proposes US spot event rules. Widening it would mean grids on ~6 events a year, which is overfitting, so the right "improvement" is new registrations from new venues (gap 1), not a wider search. | No. |
| 7 | **Capital and scaling** | Live rule v2: $100/trade, max $1,100 open, staged doubling needing 10 live crash days, mean > +1%, account up in dollars, positive random-entry excess and AJ's word (`live-rule-us.md` §5-6). Gate tracked hourly (`tartar/autotrade/live_gate.py`). | None in design; it is what the ideal does at this evidence level. The gap is the outcome: at this stake and frequency it is a real-fills test, not income, and the gate will take months. | No (AJ chose to wait for the gate on 10-13). |
| 8 | **Infrastructure and safety of the repo** | Public repo with keys only in environment secrets; no always-on Actions (`reviews/tos-check-2026-10-10.md`); tests in CI (`tests.yml`); bundle push routine with secrets scan. | One data source per strategy (Coinbase candles for capit): if it is down on a crash day the signal is missed. Health would show the failed run, not the missed trade. | Not now; worth a fallback price source when money is live. |

## Top gaps worth closing

1. **Test the cheapest US venue we have not touched: US stocks and ETFs on Alpaca.** Same account and paper
   endpoint we already use, no commission, spreads near 1-5 bp on liquid names, so edges far too small for crypto's
   0.39%/side could pay. Daily bars suit the hourly runner (orders at the open or close need no fast reaction), and
   hundreds of names give more independent events than 11 coins. The idea is not closed: `findings.md` closed S&P
   *trend timing*, not short-horizon mean reversion. Honest prior: moderate to low, because equity reversal effects
   are well known and crowded. Smallest step: one pre-registered study of a capitulation-style rule (a large drop on
   high volume, hold 1-5 days) on liquid US ETFs and large caps, with a random-entry control and a 5 bp/side cost,
   added to `findings.md` §7 meanwhile. Snags to check first: the free data feed (Alpaca's IEX bars are partial
   volume), and the pattern-day-trader rule on margin accounts under $25k (multi-day holds avoid it).
2. **Reconcile the Alpaca paper account with the book every run.** List the account's positions and open orders,
   compare with the mirrored paper positions, and turn health red on any mismatch (in live mode the same check would
   write `HALT`, as live rule §5 requires). A small change inside `alpaca.py`'s owner lane; it proves the
   stop that guards real money while the stakes are still zero.
3. **Let the paper book answer the latency question; don't re-decide it.** `us_capit_fast` against `us_capit` on
   the Alpaca paper fills already measures what an always-on box would add. The box stays a pending AJ call with
   its existing trigger (live rule §6, `reviews/agent-surge-2026-10-13.md`).

## Where a bigger setup would differ

With a larger account or a firm: co-located, event-driven execution and maker rebates instead of hourly market
orders; many venues and shorting; dedicated data feeds with redundancy; a dozen-plus uncorrelated strategies sized
by volatility and a risk team watching intraday. Most of that pays only when stakes are large enough that a basis
point is worth an engineer's time; at $100 a trade, none of it is.
