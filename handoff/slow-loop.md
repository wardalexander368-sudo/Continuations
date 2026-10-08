# The fast loop and the slow loop

**Fast loop** (`tartar fast`, a long-running process, no Claude in it): for
every pump.fun launch on the chain stream it waits `screen_seconds`, builds
the launch state, applies the policy's skip rules, asks the scorer (TypeSafe
Jev, or plain rules), and **paper**-trades a yes on the live curve. It
records raw logs from the same connection and journals every screen,
decision, fill and exit to `data/journal/journal-YYYYMMDD.jsonl`.

**Slow loop** (Claude, every few hours): reviews what happened, changes the
policy file, and records why. The fast loop reloads `data/policy.json`
within 5 s of a change. Open positions keep the rule they were opened with.

## Running the fast loop

```bash
# paper trading with rules only (no key needed)
setsid nohup tartar fast --policy data/policy.json --journal data/journal --out data/raw --hours 20 \
  >> data/logs/fast.log 2>&1 < /dev/null &

# with Jev: TYPESAFE_API_KEY in the environment, then set "scorer": "jev" in data/policy.json
```

* Only one process should hold the chain websocket per container: the fast
  loop *is* the recorder (don't also run `tartar record`).
* Find it by executable name: `ps -eo pid,comm | awk '$2 == "tartar" {print $1}'`.
  Don't match on the command line: your own shell's command line contains
  the pattern, and the kill takes your shell down too. Stop it with SIGTERM;
  it closes positions at their last state and journals a `stop` summary.
* Replay on recorded data (seconds, no network): `tartar fast --replay data/raw
  --policy P --journal J`.

## The policy file (`data/policy.json`)

All fields are bounded (`tartar/fastloop.py: LIMITS`); `mode` must be
`"paper"`; an invalid edit is rejected and the last good policy stays (the
journal logs `policy_error`). Fields: `scorer` (`rules` | `jev`),
`screen_seconds`, `min_buyers`, `skip_levels`, `skip_flags`, `threshold`,
`hold_seconds`, `take_profit`, `stop_loss`, `size_sol`, `fee`,
`network_sol`, `exec_latency`, `scorer_timeout`, `max_open`,
`max_entries_per_hour`, `daily_loss_limit_sol`, `note`.

## One slow-loop cycle

1. `git pull`; read `handoff/STATUS.md`. Check the fast loop is alive
   (`ps …`, `tail data/logs/fast.log`); restart it if not.
2. `tartar review --hours 6 --markdown data/reviews/<UTC time>.md` (or
   without `--hours` for everything). Read:
   * **paper trades (as run)**: the result of the current policy;
   * **every screened launch, if bought**: the base rate;
   * **skipped: …** rows: did each skip rule remove losers (negative mean)
     or winners?
   * **scorer calibration**: does P(net > 0) rise with Jev's score? If not,
     Jev's score is noise for this question, whatever its threshold;
   * **latency**: Jev's median / p90 per call.
3. Change **at most one thing** per cycle, and only with evidence from at
   least ~300 new screened launches:
   * the threshold, toward the hindsight best, at most halfway (it's
     in-sample);
   * a skip flag in or out, when its "with" vs "without" gap is clear
     (intervals not overlapping);
   * the exit rule, only after checking it with `tartar decide` on the same
     data.
   Write the reason in the policy's `note`.
4. Every ~24 h of data: `tartar profit` and `tartar decide` on everything
   recorded (time split, thresholds on validation, results on test). Those
   are the out-of-sample checks; the review alone is not.
5. Commit the policy, the review Markdown and STATUS (log entry: what
   changed and why). **Don't commit `data/raw`** while it grows; copy whole
   finished hours to `handoff/data/raw/` when they're needed elsewhere.

## Guardrails

* Paper only. Real trading needs the user's explicit go-ahead and code
  that doesn't exist yet: a dedicated wallet, per-trade and per-day caps, a
  kill switch.
* Never raise `size_sol`, `max_open` or the loss limit to "make up" losses.
* If paper results are negative for 3 cycles in a row with the same
  scorer, say so plainly in STATUS. Don't keep tuning thresholds on noise.
