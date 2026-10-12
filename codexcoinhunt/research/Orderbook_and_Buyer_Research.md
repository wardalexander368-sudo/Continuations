# Order-book and buyer evidence — OB-0.1

Research received October 12, 2026 UTC (October 11, America/Chicago). Paper only. SLR-0.2 remains the leading unvalidated design; its rules and hash are unchanged.

## Venue meaning

| Route | Observable structure | Useful information | Limit |
| --- | --- | --- | --- |
| Canonical PumpSwap via PumpPortal | Constant-product pool with virtual reserves and accrued fee buckets | Size-specific recoverable exits, curve capacity, finalized wallet swap events | No native resting bid/ask queue or cancelable bid walls; curve depth is derived from existing reserves. |
| Raydium | Pool-type dependent; CPMM/CLMM and route configuration need separate handling | Quote ladder and initialized tick liquidity where applicable | Do not apply plain constant-product math to whole CLMM TVL or infer an order book from a venue label. |
| Alpaca `us` listed USD pair | Public resting bids/asks and signed taker trades | Spread, nearby depth, sampled OFI, trade confirmation | Data/eligibility are venue and account specific; no public wallet identities; polled snapshots omit intrapoll events. |

## Frozen experiment

OB-0.1 was frozen at 2026-10-12T01:41:09.657957+00:00, SHA-256 `800d2694bb0e82baa7d53c2cd5f609fb382fe0821bde86bc242c633cbb7f0934` before the bounded capture. Its hypothesis is that persistent nearby bid support plus completed buy-side volume filters unexecuted enthusiasm. The 12-minute observation period is prospective development data, not an independent validation campaign.

Rules: a source-age limit of 2 seconds; spread at most 100 bps; at least $70 of depth on both sides within 100 bps of midpoint; bid-notional share at least 60% on three distinct source updates; positive sampled best-level OFI; at least $50 signed buys and a 60% buy share in the past 60 seconds; price at most 0.5% above its trailing 60-second baseline. Enter at the next observed fresh book at least 5 seconds later and within 30 seconds; evaluate a 60-second exit with a 30-second grace period. Missing exits are censored. No maker fill or stop-price fill is invented.

Compare with persistent book-only entry, positive 60-second momentum, and a contemporaneously cost-qualified random instrument when the main rule has an opportunity. The attention control remains unavailable because no valid social history exists. Instrument identity is `alpaca_us` plus the exact USD pair; exchange symbols are never joined to arbitrary Solana mints.

## Received evidence

Capture: 2026-10-12T01:41:20.679428+00:00 through 2026-10-12T01:53:10.414140+00:00. 72 polls, 144 HTTP requests, zero HTTP errors, 288 pair snapshots and 111 distinct source updates. Only 38 snapshots meet the source-age rule; 250 fail it. Older timestamps can mean an unchanged latest book, so this is a conservative research eligibility failure and does not prove feed malfunction. There was one distinct signed trade, a DOGE sell; no signed buys were returned in this bounded observation frame.

| Exact pair | Fresh / 72 | Median source age | Median spread | Median all-level bid share | Median nearby bid share | Median modeled roundtrip cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DOGE/USD | 5 | 28.28s | 32.71 bps | 48.27% | 56.84% | 1.32% |
| BONK/USD | 12 | 14.64s | 87.08 bps | 7.68% | 49.64% | 1.85% |
| WIF/USD | 10 | 12.00s | 33.03 bps | 48.97% | 56.75% | 1.32% |
| PEPE/USD | 11 | 11.93s | 47.85 bps | 2.35% | 50.04% | 1.47% |

The cost diagnostic sweeps all needed ask and bid levels for a $7 budget, charges the published 0.25% taker fee in the received token on buying and received USD on selling, and includes a separately assumed 0.25% adverse allowance each side. The contemporaneous diagnostic is calculable on old source snapshots but they remain ineligible as fresh entries. Free unauthenticated data incurred no payment. The model assumes already-funded USD, zero funding/conversion cost and no extra broker charges; those costs and exact asset order increments remain unverified. No recoverable live USD result is claimed.

## Account-path result

| Policy | Rule opportunities | Modeled entry attempts | Cash / unresolved inventory | Interpretation |
| --- | ---: | ---: | --- | --- |
| Book + signed flow | 0 | 0 | $50; none | No opportunity. |
| Persistent book-only | 0 | 0 | $50; none | No opportunity. |
| Momentum | 6 repeated decisions | 1 | $43 cash plus unresolved modeled $7 allocation | No fresh exit in the allowed window; paused, not written off or called an unsellable token. |
| Matched random | 0 matched triggers | 0 | $50; none | No primary opportunity to match. |
| Attention | unavailable | 0 | not run | Missing social data, not a zero-return control. |

The balances are a conditional displayed-book replay, not orders or captured paper fills. There is no fully observed strategy trade, meaningful paired return comparison, completed 30-day campaign or validated doubling. The absence of a signal in 12 minutes does not falsify the long-run hypothesis.

## Buyer subset

The fixed PumpSwap pool `Fe7bpDYCs74GqiCUF14HwgUMToPKV1d9mDYVX5BTohFr`, mint `2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM`, WSOL quote `So11111111111111111111111111111111111111112`, was selected from the earlier fixed prefilter without subsequent-return ranking. Owner and base/quote identities were checked on finalized state. Thirty newest pool-referencing signatures span 112 seconds; the first 12 were retrieved. Seven are v1, four v0 and one legacy. The initial v0-only request failed on seven v1 bodies; integer `maxSupportedTransactionVersion: 1` recovered them, with every original error preserved.

Seven matching successful swap events were decoded: five buys from five event users, two sells. One user accounts for 87.33% of observed buy quote notional (10.211858525 SOL total including the event-reported user payment). The remaining five referenced transactions include fee sweeps and guarded callers without a matching PumpSwap swap event. A pool mention is not a trade. This subset is not the complete five-minute flow or a population of independent humans; log-only extraction also does not support CPI-only events yet.

Each of the five buy users has at least ten earlier successful transactions in a bounded 100-signature page. The pages establish 0.84–5.01 days of observed activity lower bounds; they do not establish wallet birth or rule out older history. Fourteen-day maturity, at least three other mints, first participation in this mint, common funding roots, service-funder labels and cluster independence remain unknown. Profiles became available after these swaps and are not inserted into past decision inputs. SLR remains rejected for missing evidence.

## Decisions and next useful tests

1. Use nearby depth and actual size-specific exits as cost/capacity checks. All-level totals include remote asks; for BONK, the all-versus-near bid-share discrepancy reached 58.66 percentage points, and for PEPE 47.99 points. That measurement distinction is supported; predictive superiority is not.
2. Keep completed buyer demand as the candidate mechanism. Test signed flow plus persistent/replenishing book depth against the same rule without book features on a later untouched period. Total book imbalance alone is not promoted.
3. Use event/receipt clocks, source-update deduplication, current transaction-version compatibility and exact mint/venue identity before estimating edge. Never treat a missing body, missing exit or account reference as observed trading behavior.
4. Extend buyer provenance and CPI decoding; implement a continuous event-feed adapter in a user-authorized environment for cancellations and depth refill, plus queue-aware maker replay. A top-level bid can disappear, and a touched maker limit does not guarantee our queue fill.
5. Maker/taker fee differential is 10 bps per leg at tier 1, roughly $0.014 for two $7 legs. Queue losses and adverse selection could exceed that saving; no maker profitability claim is made.

## Primary sources

- [Alpaca real-time crypto schemas](https://docs.alpaca.markets/us/docs/real-time-crypto-pricing-data), [latest book endpoint](https://docs.alpaca.markets/us/reference/cryptolatestorderbooks-1), [fees](https://docs.alpaca.markets/us/docs/crypto-fees), and [asset coverage](https://alpaca.markets/support/what-cryptocurrencies-does-alpaca-currently-support), checked October 12, 2026.
- [Cont, Kukanov and Stoikov: The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402), research on US stocks; order-flow prior art, not meme-coin evidence.
- [PumpSwap official structure](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_SWAP_README.md), [Solana signatures](https://solana.com/docs/rpc/http/getsignaturesforaddress), [transaction reads](https://solana.com/docs/rpc/http/gettransaction), [v1 compatibility](https://solana.com/docs/core/transactions/versioned-transactions), and [event provenance](https://solana.com/docs/programs/anchor-events), checked October 12, 2026.

