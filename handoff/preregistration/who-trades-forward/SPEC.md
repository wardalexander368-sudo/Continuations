# Pre-registration: F1 forward, a powered paper test of the concentrated-seller dip (paper)

Registered 2026-10-10 ~00:50 UTC by the retrain thread. The commit that adds this file is the
registration. Window: launches created **2026-10-10 01:00 UTC to 2026-10-19 01:00 UTC** (9 days),
none of which exists yet. Paper only; nothing traded.

## Why a second test
The first registration (`handoff/preregistration/who-trades/`) was **not confirmed**: +1.12%
[-6.30, +8.49] on 175 trades at curve fees. Its point estimate is positive and its filter kept its
direction out of sample (+3.8 points over all such dips), but 175 trades can't resolve a ~1% edge.
That test showed ~40 signals per hour of launches, so 9 days of the recorder Action's data should
give several thousand trades, enough for a CI of about ±1-1.5 points. This test asks the same
question with enough power; it does not reuse any launch the first test scored.

## Rule
Identical to `handoff/preregistration/who-trades/SPEC.md` (every constant in `SPEC.json` here):
70% dip from the running peak within 30 min of a SOL launch's create, once the peak's real SOL was
>= 40; the creator and the single largest other seller sold > 96% of the sell SOL from that peak to
the signal; buy 0.02 SOL 1 s later; sell at +30% or after 180 s; 1.25% per side (curve fees, the
Jupiter / own-instructions route), 0.000011 SOL per transaction; a trade counts only if the
recording covers its full 180 s.

## Data and scoring
The recorder Action's hours (`.github/workflows/recorder.yml`, GitHub Releases `raw-gha-YYYYMMDD`),
one directory per run, launches deduped by mint. Scored once after 2026-10-19 02:00 UTC with
`python3 handoff/experiments/who_trades_forward.py` (fetch, extract, `who_trades.py --test`). Hours
the Action failed to record are simply absent; no launch is dropped for any other reason.

## Primary statistic and success
Mean net return per trade, 90% bootstrap CI (2,000 resamples, one trade per launch). **Success: the
CI's lower bound > 0.** Anything else is a fail. Secondary (not a criterion): the same trades at
Lightning costs (+1%/side, 1.4 s), and every dip signal without the filter.
