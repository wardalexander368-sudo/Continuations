Snapshot of real pump.fun launches and trades recorded from the Solana chain
(`tartar record`, public RPC) on 2026-10-08, in the raw format described in
`tartar/data/rawlog.py`. Hourly files; the newest hour is a partial snapshot of
a file that was still being written. Copy into `data/raw/` to train:

    mkdir -p data/raw && cp handoff/data/raw/* data/raw/ && tartar train --raw data/raw

The hours up to 20:06 UTC are the data v1 was trained on. Since 2026-10-09, `20261008-20` runs to 20:34 and `20261008-21` adds 21:42–21:50 from the same recorder; `20261008-23` is the Jev session's fast loop (23:44–23:50). v1 was trained on: two recording runs (14:06–15:13 and 18:32–20:06 UTC), 5,565
launches, 213,490 trades, 3,523 usable tokens at 1-minute candles.

Capture is incomplete (median 93%, mean 84% of each token's trades; 63% median
in the first run; see the handoff), and the second run reconnects every ~30 s.

## `raw-slots/` and `raw-slots-processed/` (predictor session, 2026-10-09)

Two later recordings from the predictor session's container, kept in their own
directories (one recorder per directory: the loader reads each directory as one
timeline).

- `raw-slots/20261009-00.jsonl.gz`: 00:01–00:42 UTC, "confirmed" commitment,
  1,347 launches and 74,509 trades.
- `raw-slots-processed/20261009-00.jsonl.gz`: 00:42–00:48 UTC, "processed"
  commitment, 304 launches and 9,594 trades.

Every create, trade and migrate event carries `"slot"`. Both recordings ran the
decoder from before 2026-10-09 00:20. Quote-paired curves (not SOL) therefore
appear as creates without a first buy, and their trades are missing. Filter on
`create.vsol`. Analyse with
`python3 handoff/experiments/slot_latency.py handoff/data/raw-slots`.

## `raw-pumpswap/` (predictor session, 2026-10-09 01:30–01:50 UTC)

The first recording with `tartar record --pumpswap-hours 2`: 698 launches,
44,286 bonding-curve trades, 20 graduations and 33,292 PumpSwap trades.

- 12 graduated SOL pools were followed. Busy ones logged 2,000–10,800 trades
  in their first minutes, with the first trade 4–46 slots after graduation.
- The other 8 graduations were quote-paired curves (another pump coin or a
  tokenized stock), whose pools are not token/WSOL. They recorded no swaps,
  because the recorder at that time subscribed to the WSOL pool. Since commit
  "Skip quote-paired graduations" it marks them `quote` and does not watch
  them.

Event formats are in `tartar/data/rawlog.py`. Price after a swap =
`sol_after / tok_after` (SOL per token).

## `raw-eager/` (research session, from 2026-10-09 04:06 UTC)

`tartar record --out data/raw-eager --pumpswap-hours 4 --hours 20` in the research session's
container ("confirmed" commitment, current decoder: quote-paired launches and graduations are
marked `quote`). Hourly files are added as each hour finishes; one recorder, one timeline.

- `20261009-04`: 04:06–04:59 UTC, 1,272 launches, 95,177 curve trades, 35 graduations,
  91,817 PumpSwap swaps.
- `20261009-05`: 05:00–05:59 UTC, 1,360 launches, 110,936 curve trades, 35 graduations,
  118,839 PumpSwap swaps.
- `20261009-06`: 06:00:00–06:00:17 UTC (the recorder was stopped at the handoff; no
  `stopped` event, so loaders end the recording at its last event).

In all, 69 graduated SOL pools. Capture: a median 100% / mean 97% of each launch's curve
trades (the training loader's estimate); for one PumpSwap pool checked against the chain
(`pumpswap_capture.py`), 138 of 143 swaps (96.5%).

This is the **evaluation data of the pre-registered PumpSwap study**
(`handoff/preregistration/pumpswap-graduated/SPEC.md`): don't compute returns on its PumpSwap
pools before that evaluation is run and logged.

## `sol-dex/` (research session, 2026-10-09)

`costs-20261009.jsonl`: 216 samples of `handoff/experiments/sol_dex_costs.py sample` (Jupiter
$1,000 round-trip quotes, re-quoted after 1/2/5 s, with Coinbase's book), 04:09–06:00 UTC.
`python3 handoff/experiments/sol_dex_costs.py summary --out handoff/data/sol-dex/costs-20261009.jsonl`.

`costs-20261009-day.jsonl` (clever session): 371 more samples the same way, 06:43–09:55 UTC
(European morning); `costs-20261009-us.jsonl`: 549 more, 10:56–15:55 UTC (European
afternoon and US hours). `*.jsonl` is git-ignored repo-wide, so add sample files with `git add -f`
(the predictor session's 04:33–05:33 samples were lost that way).

## `raw-clever/` (clever session, from 2026-10-09 06:23 UTC)

`tartar record --out data/raw-clever --pumpswap-hours 4 --hours 20` in the clever session's
container, made the same way as `raw-eager` ("confirmed" commitment, current decoder), as
evaluation data for the pre-registered PumpSwap study (queue 11a). One recorder, one timeline;
hourly files are added as each hour finishes. **Don't compute returns on its PumpSwap pools
before the 11a evaluation** (`handoff/preregistration/pumpswap-graduated/SPEC.md`).

- `20261009-06`: 06:23–06:59 UTC, 770 launches, 67,525 curve trades, 17 graduated SOL pools,
  44,917 PumpSwap swaps.
- `20261009-07`: 07:00–07:59 UTC, 1,211 launches, 122,948 curve trades, 28 graduated SOL pools,
  91,560 PumpSwap swaps.
- `20261009-08`: 08:00–08:59 UTC, 1,375 launches, 106,040 curve trades, 36 graduated SOL pools,
  313,920 PumpSwap swaps; two 2 s reconnects (08:17, 08:44).
- `20261009-09`: 09:00–09:59 UTC, 1,213 launches, 112,705 curve trades, 30 graduated SOL pools,
  290,045 PumpSwap swaps.
- `20261009-10`: 10:00–10:59 UTC, 1,401 launches, 117,357 curve trades, 43 graduated SOL pools,
  335,026 PumpSwap swaps.
- `20261009-11`: 11:00–11:59 UTC, 1,598 launches, 129,674 curve trades, 41 graduated SOL pools,
  322,285 PumpSwap swaps. With this hour the 11a evaluation data holds 264 graduated SOL pools
  (69 `raw-eager` + 195 `raw-clever`), past the pre-registered 250; the evaluation ran on
  exactly these files (hours 06–11).
- `20261009-12`: 12:00–12:59 UTC, 1,878 launches, 175,442 curve trades, 41 graduated SOL pools,
  217,503 PumpSwap swaps (after the 11a evaluation; for training and later studies).
- `20261009-13`: 13:00–13:59 UTC, 2,065 launches, 205,918 curve trades, 39 graduated SOL pools,
  288,918 PumpSwap swaps.
- `20261009-14`: 14:00–14:59 UTC, 2,020 launches, 336,007 curve trades, 53 graduated SOL pools,
  329,821 PumpSwap swaps. The public RPC dropped the connection 47 times this hour (gaps 1.2–3.7 s,
  all under the loaders' 10 s cut): ~70 s of missed trades, about 2%.
- `20261009-15`: 15:00–15:59 UTC, 2,203 launches, 392,898 curve trades, 54 graduated SOL pools,
  271,059 PumpSwap swaps; 35 short reconnects. **The recording ends here** (stopped 16:00:39 at
  the clever session's handoff; the 39 s tail of hour 16 was not kept, so loaders end it at hour
  15's last event). In all: 06:23–16:00 UTC, ~16,000 launches, 341 graduated SOL pools.

## `raw-v3/` (predictor session, 2026-10-09 from 06:25 UTC)

`tartar record --track-minutes 120 --pumpswap-hours 4` with `SOLANA_COMMITMENT=processed`
(each launch followed for up to 2 h, each graduated SOL token's PumpSwap pool for 4 h).
One recorder, one directory. `20261009-06` covers only 06:25–06:31 UTC: the container was
suspended and the recorder died. The predictor session restarted it at 12:55 UTC, but that
container was lost at ~13:25 before any hour was saved. The handoff session restarted it at
13:31 UTC with the same flags. Later hours are copied here as they finish. Use them alongside
`raw-eager`/`raw-clever` for the predictor (queue 2) and the edge-hunt studies; the two
recorders overlap in time, and the loaders keep one copy of each token.

- `20261009-13`: 13:31–13:59 UTC, 1,064 launches, 87,485 curve trades, 16 graduated SOL pools,
  30,463 PumpSwap swaps.
- `20261009-14`: 14:00–14:59 UTC, 2,026 launches, 332,768 curve trades, 51 graduated SOL pools,
  239,033 PumpSwap swaps.
- `20261009-15`: 15:00–15:59 UTC, 2,203 launches, 396,534 curve trades, 53 graduated SOL pools,
  236,229 PumpSwap swaps.
- `20261009-16`: 16:00–16:59 UTC, 1,945 launches, 130,561 curve trades, 57 graduated SOL pools,
  315,333 PumpSwap swaps.
