Snapshot of real pump.fun launches and trades recorded from the Solana chain
(`tartar record`, public RPC) on 2026-10-08, in the raw format described in
`tartar/data/rawlog.py`. Hourly files; the newest hour is a partial snapshot of
a file that was still being written. Copy into `data/raw/` to train:

    mkdir -p data/raw && cp handoff/data/raw/* data/raw/ && tartar train --raw data/raw

Capture is incomplete (median ~63% of each token's trades; see the handoff).
