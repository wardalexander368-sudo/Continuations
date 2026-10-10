# Pre-registration: edge hunt F1, a deep dip sold by one or two wallets (paper)

Registered 2026-10-10 ~00:00 UTC by the retrain thread (project thread session, branch
`claude/project-thread-6oh2s6`). The commit that adds this file is the registration. **No launch
created at or after 16:00 UTC 2026-10-09 has been scored by this rule or any of its variants.**
Paper only; nothing traded.

## Where it came from (dev only, seen before this rule was fixed)
`handoff/experiments/who_trades.py` on every screened SOL launch of `raw-eager`, `raw-clever`,
`raw-clever2`, `raw-v3`, `raw-pred` created before 16:00 UTC 10-09 (15,068 launches; output
`handoff/data/exit-study/who-trades-dev.txt`). 144 variants were looked at (4 dip definitions x 4
exits x 8 who-sold / who-bought splits, plus 16 overhang rules). Chosen on dev's first 60% and
checked on its last 40%:

| | choose (first 60%) | check (last 40%) |
|---|---|---|
| this rule | +4.17% [-2.03, +10.32], n 282 | +3.51% [-5.32, +12.53], n 140 |
| the same dips, no concentration filter | -0.51% [-4.25, +3.57], n 565 | -1.61% [-6.52, +3.04], n 342 |

Mechanism: after a big run, a 70% drawdown that one or two wallets (the creator and the top seller)
caused is a single holder exiting; the same drawdown spread over many sellers is interest dying.
Many variants were looked at, so expect the true edge to be smaller than this.

## Rule (`SPEC.json`; `who_trades.py --test`)
* **Signal:** within 30 min of a SOL launch's create, the first trade at which the price is >= 70%
  below its running peak, once the curve's real SOL at that peak was >= 40.
* **Filter:** of the sell SOL between that peak and the signal, the creator and the single largest
  other seller together sold > 96%.
* **Trade:** buy 0.02 SOL 1 s after the signal on the recorded curve; sell at +30% (take profit) or
  after 180 s, whichever is first. Costs: 1.25% per side (curve fees; Jupiter or our own instructions,
  profitability §3.19), 0.000011 SOL per transaction. A position open at graduation is valued at the
  last curve price less 10%. A trade counts only if the recording covers its full 180 s.

## Test data
Every screened SOL launch in the same five recordings created at or after 16:00 UTC 2026-10-09
(through `raw-pred` hour 20), plus any later hours added to `handoff/data/` by the time of scoring.

## Primary statistic and success
Mean net return per trade with a 90% bootstrap CI (2,000 resamples, one trade per launch).
**Success: the CI's lower bound > 0.** Anything else is a fail. Secondary (not a criterion): the same
trades at Lightning costs (+1%/side, 1.4 s).
