# CAPIT: replicated history and whole-episode robustness, 2026-10-13

CAPIT remains the strongest current US candidate, but this check does not establish profitability. Its excess over nearby same-coin entries remains positive after preserving shared crash episodes. Every net-return interval still spans zero. At fixed $100 stakes, the full-history model earns $259.69 on the 11 study coins or $214.78 on the eight-coin snapshot screen, with most gains supplied by one episode.

This is a diagnostic of previously explored history, 2023-01-01 through 2026-10-10 exclusive. It is not an untouched forward test. CAPIT Z=4, hold=24 hours, entry/exit indexes, both cost assumptions, both universes, 72-hour episode grouping and control/bootstrap procedures were fixed before viewing the new results. The protocol SHA-256 is `84a0bd1aadd944a5e8a9fbc865a6c770cb404f1f01ff8dad1e035a96a1115aed`.

All four prespecified lines follow. Percentages are per trade; intervals are 90% whole-episode bootstrap intervals. Dollars sum fixed $100 trade stakes over the full history and are model dollars, rather than an executable account return.

| Universe | Cost/side | Trades / represented episodes | Mean net [CI] | Excess over local controls [CI] | Model net dollars | Peak open notional |
|---|---:|---:|---:|---:|---:|---:|
| Study 11 | 0.39% | 71 / 22 | +3.66% [−0.27, +7.67] | +4.86% [+0.95, +8.97] | $259.69 | $800 |
| Study 11 | 0.50% | 71 / 22 | +3.44% [−0.49, +7.45] | +4.86% [+0.95, +8.97] | $244.07 | $800 |
| Snapshot-screened 8 | 0.39% | 50 / 20 | +4.30% [−0.14, +8.68] | +5.52% [+1.05, +9.97] | $214.78 | $600 |
| Snapshot-screened 8 | 0.50% | 50 / 20 | +4.08% [−0.36, +8.46] | +5.52% [+1.05, +9.97] | $203.78 | $600 |

The screened eight exclude AVAX, BCH and LTC using the already-known October 11 spread snapshot. This applies a current static screen to old history; it does not reconstruct historical eligibility or establish that these coins meet future measured-cost requirements. Both universes retain the fixed 22-episode resampling universe and the same full-11 control support. All 10,000 bootstrap draws were defined in each actual line, including the subset with two empty episodes. Costs cancel in paired excess because each control pays the same assumed cost as its signal trade. A positive excess over negative-return controls can coexist with uncertain absolute net profitability.

The February 3, 2025 episode contributes $162.18, or 62.45% of the full-11 model gain at 0.39%/side; it contributes $128.45, or 59.81%, for the screened eight. Removing that whole episode produces the weakest residual means: full-11 net +1.55%, excess +2.69%; screened-eight net +1.96%, excess +3.13%. These are residual means, not new confidence intervals. They show that the point estimate is not wholly supplied by that episode, while the concentration remains substantial. Every episode deletion is retained in the machine-readable readout; none was selected to improve the reported result.

The cache was rebuilt once from Coinbase's free Exchange API after Claude identified the original 21-coin reconstruction route. All **2,331 planned chunks** validated; **2,353 raw/normalized/metadata file hashes** were verified before analysis. The full run issued 2,330 requests and reused one validated pilot chunk. Normalized files preserve hourly close and volume in Unix-hour keys, compatible with `wide_coins.py`. Raw responses, request metadata, missing-hour intervals and hashes remain in the local research cache. The manifest SHA-256 is `dc9fc1a691933ef97584f61b8b62f95724d50157e22a00800b3796a40992d4e7`.

Complete acquisition means every requested chunk was processed; it does not mean uninterrupted candles. XRP has 4,662 absent hours, PEPE 16,395, and the other coins 13–89 each. Missing hours remain missing. Coinbase documents a maximum of 300 candles per request and warns that intervals without ticks may have no candle. The cause of each absent interval was not independently established. [Official candle API specification](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles).

The existing `wide_coins.py` and `random_entry.py` ran offline against the verified cache. Their reported results reproduce Claude's published numbers at the recorded precision:

| Existing analysis | Reproduced result at 0.39%/side |
|---|---|
| CAPIT, study 11 | 71 trades / 25 days; net +3.66%; local excess +4.85% [+0.98, +8.73] by day |
| CAPIT, extra 10 | 48 trades / 17 days; net +4.52%; local excess +6.00% [−0.17, +11.79] by day |
| VOLSPIKE, extra 10 | 292 trades / 241 days; net −0.30%; local excess −0.25% [−1.40, +0.99] by day |

The original cache bytes and original stdout were unavailable, so this establishes numerical replication at published precision, not byte identity with Claude's original acquisition. The ten extra coins remain a transfer check on coins sharing many of the same market shocks, rather than new independent time evidence. The robustness diagnostic itself analyzes only the fixed study 11 and screened eight.

Episode membership chains consecutive accepted signal hours separated by at most 72 hours across all study coins. Each episode's control shifts every coin/time offset together within ±360 hours. Valid finite positive entry and exit endpoints determine the support; zero shift and other actual signals remain in the pool. Exact enumeration supplies the control mean. There is no return filter. Bootstrap resampling uses episode sums/counts to preserve trade weighting, 10,000 draws and seed 1. Episodes can still share market regimes; this grouping does not prove statistical independence. Shifted episodes may overlap, so the controls are mean-return diagnostics, rather than a runnable competing account.

Reproduce from the repository root with the normal development dependencies and `httpx` available. Use a new cache directory for acquisition, or resume this downloader's existing cache. A completed verified cache needs no further API download. Use an output path outside the cache:

```sh
python handoff/experiments/edge-hunt/patterns/rebuild_capit_cache.py --cache CACHE_DIR
python handoff/experiments/edge-hunt/patterns/wide_coins.py CACHE_DIR
python handoff/experiments/edge-hunt/patterns/random_entry.py CACHE_DIR
python handoff/experiments/edge-hunt/patterns/capit_robustness.py --cache CACHE_DIR --output RESULT.json
```

The downloader is resumable and rate-spaced, validates raw candles, stores failed-request evidence, and refuses an analysis-ready manifest when chunks are missing or malformed. The scorer checks normalized hashes and completeness metadata, leaves missing prices unfilled and performs no fetching or orders. Future API responses may differ; the published normalized hashes identify this exact acquisition. The full raw cache is retained locally. The repository readout (`handoff/data/edge-hunt/capit-robustness/2026-10-13.json`) records the protocol, source and full-output hashes, coverage, individual accepted trades, control expectations, episode support hashes, all four summaries and every whole-episode deletion. Baseline stdout and `verification-2026-10-13.json` are alongside it.

Initial analysis ran at protocol base `8c107e75cc361d140f578fc1dde6b60ee4ac3bd8`, with the exact pinned signal-source file hash. Main subsequently added the forward REPORT control and Coinbase US-perp book recording. Their changes leave the `signals` function and COINS/RULES/WIN source identical; the source receipt pins that comparison. The replay after incorporating main was byte-identical (full-output SHA-256 `a293b0ff5a2de8c1edf8b30e23971035a792f9c99b66d80abe1135e0056dce45`).

Interpretation remains limited by hourly entry timing (close of h+1; exit h+25), rather than registered 30-minute entry or actual fill latency; additive fixed costs; the static screen; explored history; and concentrated crash exposure. Model dollars omit intratrade stops, account funding limits, idle-capital opportunity cost and live execution. Peak open notional is not a sufficient starting-cash estimate. These results support continued paper evaluation of CAPIT and continue to weaken VOLSPIKE's transfer case. They do not justify changing the registered verdict, trading route, account funding or stake limits.

Validation before the new readout: **361 tests passed, 1 skipped, 9 subtests passed in 81.86 seconds**, including 24 diagnostic tests and 13 downloader tests. Independent synthetic review checked common shift support, timestamps, trade-weighted bootstrap, empty subset episodes, whole-episode deletion, dollars/concurrency and nine malformed-cache cases, with no reproduced deviation from the fixed protocol. The readout received a separate arithmetic/concentration review. Final validation after incorporating main: **364 passed, 1 skipped, 9 subtests passed in 79.88 seconds**; see the accompanying verification receipt. No extra API requests were made for either baseline or the replay.

The next evidence comes from future crash signals with timing, simulated and eventually authorized real costs accounted for across all eligible signals. Main's forward control is now complete. The owners still need to resolve the reproduced gate-input integrity failures before relying on a met gate. The newer CDE book collector can test a possible cost lever; this diagnostic does not add an unplanned cheap-perp cost line, assume retail fees, or relax the adopted $100 stake. CoinHunt remains a separate unvalidated archive; no sealed Jev outcomes or Crypto Trading System material were accessed.
