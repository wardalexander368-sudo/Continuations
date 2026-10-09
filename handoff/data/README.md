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
