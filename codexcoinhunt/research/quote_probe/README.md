# Read-only PumpSwap quote probe

This probe uses the official `@pump-fun/pump-swap-sdk` package pinned in `package-lock.json`. It fetches processed pool, fee, mint and vault state; verifies the exact pool owner, base mint and canonical pool derivation; and asks the SDK for a size-specific buy and immediate full-exit quote. It never constructs, signs, simulates or sends a transaction. Processed state is used for a current quote; a later paper fill record still needs confirmed/finalized transaction evidence.

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm run probe -- ../results/new_quote_probe
```

The default candidate set is the five PumpSwap pools that passed only the pool-age and reported-liquidity prefilter in the frozen first sample. `SOLANA_RPC_URL` may select a different read-only RPC. `RPC_COMMITMENT` defaults to `processed`, `MAX_QUOTE_AGE_MS` defaults to 2,000, `MAX_MARKET_REFERENCE_AGE_MS` defaults to 5,000 and `POSITION_USD` defaults to 7.

Raw JSON-RPC and exact-pair DEX responses are stored with UTC request and receipt times. A quote fails closed on wrong owner, mint mismatch, noncanonical pool, unsupported quote mint, missing exact pair, a state-assembly window over the limit, or an all-in same-state roundtrip cost above 6%.

`CAPACITY_PASS_ONLY` establishes neither SLR entry eligibility nor a fill. The USD conversion comes from the exact DEX pair's displayed USD/native ratio. The all-in model retains the existing 0.5% Local charge on both sides, 0.5% adverse-execution allowance on both sides, $0.05 allocated data cost and $0.02 estimated fixed cost per transaction. It does not simulate account creation, priority fees, block contention or transaction failure. Rerun immediately before every paper decision; pool state and fee schedules can change.
