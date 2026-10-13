# Paper box evidence audit — 2026-10-13

Reviewed Continuations at `71f137fcc103050a24d75ca94fa7969117b65fe2` through saved Git source. This advances the account-evidence review after Claude merged PR7/8/9 and added paper reconciliation, the box and the ETF study in PR10. This records the initial documentation-only source audit; its runtime implications below were **SUSPECTED-NOT-REPRODUCED at that stage**. The dated [execution evidence continuation](box-execution-evidence-2026-10-13.md) subsequently reproduced partial-fill, coverage, clock and reconciliation behavior in 19 synthetic cases with controls and protective halts. Read that continuation for current classifications and limits. No broker calls, credentials, live orders or owner implementation changes occurred.

The saved `autotrade/REPORT.md:3,15–18,24–26` at 12:31 UTC has zero US trades, 0/3 crash days and 0/8 qualifying trades; no priced random-entry control. Reconciliation reports matches for an empty account with zero symbols (`autotrade/state.json:6–12`; `autotrade/REPORT.md:65`). Main contains no `autotrade/alpaca_fills.jsonl` or box fill/state files. Its four existing `fills.jsonl` rows are unchanged dry-live JLP events. The ETF screen failed its stated bar: validation net -0.76%, excess -0.74%, and test excess interval [-0.54%, +3.43%]. These ETF figures come from `handoff/experiments/edge-hunt/equities/RESULT-2026-10-13.txt:54–57`; the study was not independently rerun. Absence of box files in this main snapshot does not establish the deployed box or its separate `box-data` branch state.

| Priority | Verified source fact | Evidence implication |
|---|---|---|
| 1 | `_fill` accepts positive partial quantity even if status is not filled (`tartar/autotrade/alpaca.py:118`); box retains the first buy quantity and deletes the whole position after a positive partial sell (`tartar/autotrade/box.py:149,156,168,174,176`). | **SUSPECTED-NOT-REPRODUCED:** a later fill or residual inventory could be omitted; actual partial fills and resulting errors were not reproduced. |
| 2 | Pass-start `now` is reused after candle fetches and order waits; `latency_s` is pass start minus signal close (`tartar/autotrade/box.py:129,138,145,148,229`). | This is nominal polling delay, not measured submission or fill latency. Broker fill timestamps are absent. |
| 3 | Latest hour only; coin exceptions and missing observations can still advance the shared cursor (`tartar/autotrade/box.py:114,117,121,123`; `tartar/autotrade/strategies/coinbase_pattern.py:54,77`). | Existing fills alone cannot distinguish no signal from incomplete observation. **SUSPECTED-NOT-REPRODUCED:** actual outage omissions were not reproduced. |
| 4 | Unconfirmed buys can be excluded while `ok` stays true; missing valuation can fall back to zero (`tartar/autotrade/alpaca.py:268,279,282,285,295,326`). Box reconciliation follows entries (`tartar/autotrade/box.py:120,125`). | A match is weaker than verified complete inventory and valuation. **SUSPECTED-NOT-REPRODUCED:** false matches or pre-check orders were not reproduced. |
| 5 | Box defaults $100/11 positions and requires a second paper account (`handoff/box.md:11–13,55`); hourly CAPIT uses $200 and shares its account/risk constraints with other hourly strategies. Exits use different entry references (`tartar/autotrade/box.py:148,215`; `autotrade/config.json:5,150,166`; `tartar/autotrade/strategies/coinbase_pattern.py:203`). | Dollar outcomes compare different complete policies; they do not isolate latency. |
| 6 | Net return is the price ratio multiplied by `(1 - fee)^2`, then less one; sell rows omit actual fill time, terminal status and returned order ID (`tartar/autotrade/box.py:173,174`). | This is not complete account cash PnL. Actual fees, quantities, residual assets and cash are required. |

Existing `tests/test_autotrade_box.py:39–95` cases cover full fills, no signal, halts and paper-key rejection; the source audit did not find partial-fill, missing-hour, elapsed-clock or paired-performance cases in that test file. It did not audit every repository test. Full repository validation was run separately at the exact reviewed base `71f137f`: 449 passed, one skipped, nine subtests passed. This documentation-only work did not rerun the suite. A passing suite does not reproduce the suspected failures above.

## Prospective comparison protocol

Preserve registered hourly lines. Before outcomes, specify a separate box comparison's window, coin list, stake, capital, caps, fees, exits and outage treatment; record deployment times and code/config hashes. Match eligible opportunities by `(coin, signal_hour)`, retaining paired fills, one-sided fills, skips, exceptions, unknown coverage, unconfirmed orders and partials. Absent fills do not mean absent opportunity.

Existing signal-close, pass-time, nominal-latency, entry/exit, buy-ID, quantity, price and status fields support only their documented scope. Owners must retain actual submission/fill timestamps, terminal states, complete filled quantities, fee activities, cash and residual inventory prospectively; these cannot be manufactured retrospectively. Report paired net dollars per eligible signal and complete account outcomes, including exposure, outages and halts; cluster uncertainty by crash episode. Compare the complete 24-hour policies as primary. A common-exit timing diagnostic must be specified separately.

The appropriate next implementation belongs to the Alpaca paper-route and TARTAR agent owners. Pending, partial, unvalued or unreconciled cases remain unresolved. US venue/account eligibility and the existing live gate remain separate requirements; this paper review authorizes no live route or recorder relaunch. This audit establishes evidence gaps, not a profitable strategy, a realized latency gain or a novel method.

## Provenance and limits

SHA-256 below covers exact Git blob bytes at the reviewed base, not fresh network receipts. The saved local source audit used for this review has SHA-256 `775192d932476888ae26d0040f35465876e53325b7759a56e6e28300c505cd28`.

| Source | SHA-256 |
|---|---|
| `tartar/autotrade/box.py` | `68a97c86809a393730b147f84d247eb2b8d334b7630aeccf4c2218bfcee8bbd7` |
| `tartar/autotrade/alpaca.py` | `38c522f66cb144ebcc75677a801dd2a1a67ec9589decfe80a10133d3c52e837d` |
| `tartar/autotrade/strategies/coinbase_pattern.py` | `fc621f5caf915c3c953607224057d24b0a19f9247c41da5b0ed540330d12fed6` |
| `autotrade/config.json` | `4a47e329a1e6fa6707084e4891931316c80e0f09d9483b1a6fdd489b1224711a` |
| `autotrade/REPORT.md` | `4dfa14f53df3adf595058f418434163a7dc8cfbc5d10c6909a2f4f40953ebbcd` |
| `autotrade/state.json` | `722056b29ab94da4e7df3200d7fc50c9b40d9a3819e614eda4a63d0928095e1d` |
| `autotrade/fills.jsonl` | `339ef661563e7b2177575fe7e1eb2063cfca194d4956160cdc2aaa416a118eb2` |
| `tests/test_autotrade_box.py` | `024e269c94691a3883cfd95245e8addb86deb97272689e94ca332c1c03c691c7` |
| `handoff/box.md` | `be655c9457b7f19059110bc45e68062f8c6d2fa9e1e116922403e06be969cb7f` |
| `handoff/experiments/edge-hunt/equities/RESULT-2026-10-13.txt` | `3d47839610aa786c8cc0a1b21b40f10afaccf4fadc9b45c9bfdac1a6f957fb82` |

Not checked: broker/API behavior, credentials, current deployed account or box state, actual partial fills, outages, elapsed execution clocks, real fees, slippage/queue behavior, full account cash PnL, ETF rerun or every repository test. This initial source audit did not execute runtime cases; the linked continuation subsequently did so with synthetic inputs. No production failure or economic advantage was established; no frozen registration, implementation, workflow or live book was changed.
