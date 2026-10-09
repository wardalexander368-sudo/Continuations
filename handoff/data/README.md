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

## `sol-dex/` (research session, 2026-10-09)

`costs-20261009.jsonl`: 216 samples of `handoff/experiments/sol_dex_costs.py sample` (Jupiter
$1,000 round-trip quotes, re-quoted after 1/2/5 s, with Coinbase's book), 04:09–06:00 UTC.
`python3 handoff/experiments/sol_dex_costs.py summary --out handoff/data/sol-dex/costs-20261009.jsonl`.

This is the **evaluation data of the pre-registered PumpSwap study**
(`handoff/preregistration/pumpswap-graduated/SPEC.md`): don't compute returns on its PumpSwap
pools before that evaluation is run and logged.

## `raw-clever/` (clever session, from 2026-10-09 06:23 UTC)

`tartar record --out data/raw-clever --pumpswap-hours 4 --hours 20` in the clever session's
container, made the same way as `raw-eager` ("confirmed" commitment, current decoder), as
evaluation data for the pre-registered PumpSwap study (queue 11a). One recorder, one timeline;
hourly files are added as each hour finishes. **Don't compute returns on its PumpSwap pools
before the 11a evaluation** (`handoff/preregistration/pumpswap-graduated/SPEC.md`).

- `20261009-06`: 06:23–06:59 UTC, 770 launches, 67,525 curve trades, 17 graduated SOL pools,
  44,917 PumpSwap swaps.
