Snapshot of real pump.fun launches and trades recorded from the Solana chain
(`tartar record`, public RPC) on 2026-10-08, in the raw format described in
`tartar/data/rawlog.py`. Hourly files; the newest hour is a partial snapshot of
a file that was still being written. Copy into `data/raw/` to train:

    mkdir -p data/raw && cp handoff/data/raw/* data/raw/ && tartar train --raw data/raw

This is exactly the data the installed v1 model (`tartar/models/trades-60s`)
was trained on: two recording runs (14:06–15:13 and 18:32–20:06 UTC), 5,565
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
