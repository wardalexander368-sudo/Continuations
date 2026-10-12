# Second-Look Relay research kit

Latest increment: complete official-IDL event decoding explains the two formerly unknown approximately 0.45% quote-account differences as LP + protocol + creator fees under instruction-dependent field semantics. Instruction-aware gross debit matches exact outflow in all five fixed buys. The suite has **161 distinct passing engineering checks**. See `Pump_Event_Fee_Reconciliation_Research.md`; this accounting correction adds no strategy return, and continuous social coverage plus live fill/FX adapters remain unconnected.

SLR-0.2 is a paper-only strategy specification and evidence recorder for a $50 memecoin experiment. Its hypothesis is that a new audience can rediscover a surviving meme while original sellers are exhausting their supply. Exact token-address agreement and observed, apparently unrelated buyers must confirm that the attention can reach this particular token.

**Profitability, a reliable $50-to-over-$100 result, and universal novelty are not established.** The engineering checks cover accounting and data leakage, not an investment edge. Read `Resolant_Second_Look_Strategy.md` before interpreting any output.

## Run on a Mac

Core tools use Python 3.10 or newer and the standard library. No wallet or API key is needed for the DEX Screener sample, fee arithmetic, entry gate, or journal reconciliation.

From this extracted folder:

```bash
python3 economics.py --output results
python3 -m unittest discover -s tests -v
python3 collect_market.py --output data/new_session --minutes 30 --interval 30
python3 summarize_sample.py data/new_session --output results/new_session
python3 screen.py journal/observed_features.jsonl --output journal/decisions.jsonl
python3 audit_ledger.py journal/fills.csv --output results/ledger_audit.json
```

Use a new session directory every time. The collector freezes its universe before following future prices, preserves unsuccessful HTTP requests and missing pairs, and stores raw API responses. DEX Screener discovery is visibility biased and its buy counts do not establish independent people or wallets.

`screen.py` requires evidence references and the time each feature became available. Missing social, wallet, safety, or quote information causes rejection. `PAPER_ELIGIBLE` means the supplied feature assertions meet the thresholds; the program does not verify the external evidence or send an order.

The provided `journal/observed_features.jsonl` contains genuine liquidity observations from the initial sample, with unavailable inputs omitted. Every record is rejected for insufficient evidence. Do not turn those omissions into invented favorable values.

## Optional PumpPortal raw data

`collect_pumpportal.py` uses one websocket connection and stores raw events with receipt times. It requires the optional `websockets` package and an API key configured locally through the `PUMPPORTAL_API_KEY` environment variable. Never paste a private key into this project or into chat.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install websockets
python3 collect_pumpportal.py --output data/pumpportal_discovery.jsonl --minutes 30
```

Add `--mints-file shortlist.txt` only when choosing to use the provider's metered token-trade stream. The published rate is 0.01 SOL per 10,000 trade events, and a linked wallet balance of at least 0.02 SOL is required for those subscriptions. The recorder's message limit is not a guarantee of zero charges: provider billing state can span sessions. None of these paid streams were invoked during this research session.

The kit deliberately preserves raw provider fields. A production adapter still needs schema validation, de-duplication by transaction signature/instruction, token-decimal checks, finalized-chain reconciliation, exchange/service-funder exclusions, and funding-cluster analysis. It is not a finished autonomous trading bot.

## Feature records

Each record has `mint`, an ISO 8601 timezone-aware `decision_at`, and a `features` object. Each feature is an object with `value`, `available_at`, and `evidence`. Example shape:

```json
{
  "mint": "EXACT_MINT_ADDRESS",
  "decision_at": "2026-10-12T00:00:00Z",
  "features": {
    "liquidity_usd": {
      "value": 30000,
      "available_at": "2026-10-11T23:59:59Z",
      "evidence": "raw-session.jsonl:record-42"
    }
  }
}
```

That intentionally incomplete example is rejected. Obtain the rest from timestamped source evidence; do not populate them from the synthetic test fixture. Boolean verification flags are operator assertions, not certifications of safety or legality.

## Fill journal

`journal/fills.csv` starts empty. Each event needs a unique ID, timezone-aware timestamp, event kind, position ID, mint, token quantity, **net** USD cash change, and evidence reference. Buy cash changes are negative; sell cash changes are positive. Fees already included in a fill must not be added again. Record non-fill expenses separately as `cost` rows. Use `writeoff` for documented unsellable remainders, with zero cash recovery.

The ledger rejects overlapping positions, repeated settlements, excessive position sizes, and overselling. Open tokens do not count as successful account doubling. Convert net SOL proceeds and gas balances at executable conversion amounts, reconcile funded rent and any eventual refunds separately, and retain the external evidence. The ledger is a fill-accounting auditor, not an exit scheduler or a US tax return.

The offline controller now checks daily/campaign rules on supplied events. Social ingestion, buyer provenance, authenticated fill/cost inputs, matched-control execution, block-bootstrap analysis and additional venue adapters remain research tasks. It does not provide continuous monitoring.

## What the outputs mean

- `economics.json`: fee estimates with explicitly assumed slippage, fixed transaction costs, and allocated data costs.
- `hypothetical_sensitivity.csv`: exact probability arithmetic under invented IID outcome assumptions; **not measured win rates or a backtest**.
- `first_market_sample.csv`: frozen-pool observed chart paths, including missing endpoints; **not filled returns**.
- `ledger_audit.json`: reconciled input fills; the initial result has zero fills and no demonstrated account growth.
- `preregistration.json`: strategy hash and freeze time. A changed rule set requires a new version and a new untouched forward period.
- `journal/decisions.jsonl`: evidence-based eligibility decisions, including every missing input.

All research results are measured in USD-equivalent after execution/data costs and before personal taxes. The target requires realized, recoverable cash; chart peaks, the sum of percentage returns, and paper fills invented from candle highs do not satisfy it.


## Historical challenger and benchmark audit

A corrected public corpus with 716,762 rows is included as `data/red_reject_compact.csv.gz`, with licence, attribution and transformation checksums. It is an observed rejection-follow-up frame, not all tokens. Read `SOURCE_ATTRIBUTION.md` and the source completeness statement before interpreting it.

```bash
python3 revival_study.py data/red_reject_compact.csv.gz --compact data/red_reject_compact.csv.gz --output results/revival_study
python3 audit_published.py data/source_probe_20261012/companion_source/data/trades.csv --output results/published_benchmark_audit.json
```

`REV-0.1` produced zero signals and is not promoted. The historical momentum comparisons are fee/depth-adjusted **mark-path** stress tests. Entries use later observations; missing, stale and capacity-failing entries and censored exits remain explicit. Matched controls use the contemporaneously known universe. Ordinary momentum and random controls showed no positive edge in the paired observed-path subset. The paired day-block intervals are descriptive: repeated mints, incomplete pairs and missing social/custody/fill evidence remain.

The external benchmark audit shows why summing return percentages is not a funded-account result. Hypothetical fixed-fraction compounding is labelled algebra, and overlapping original position intervals are reported. These results do not replace a full $50 campaign controller or forward test.

## Current PumpSwap capacity probe

`quote_probe/` is a pinned, read-only adapter around the official PumpSwap SDK. It captures every RPC request and response, exact-pair market reference and UTC request/receipt time. The final bounded pass (`results/quote_probe_20261012_pass6`) checked the five PumpSwap pools from the frozen initial pool-age/liquidity prefilter. All five had the correct program owner, exact base mint and canonical pool derivation. Processed pool, fee, mint and vault state was assembled in 326 ms; the exact-pair USD reference was 3,334 ms old.

The route-only immediate roundtrip retained 97.556%–99.097% of the pool input. After the existing $7 budget model adds Local charges, two 0.5% adverse-execution allowances, $0.05 data allocation and $0.02 fixed cost per side, recoverable value was $6.6065–$6.7111, an estimated 4.13%–5.62% same-state cost. All five pass the 6% capacity gate only. Earlier 2.97–3.13 second attempts remain as rejected stale quotes; a warm read before starting the quote clock reduced connection setup latency without removing any state reads.

These observations occurred about 55 minutes after the initial candidate snapshot and are neither historical entry-time quotes nor fills. They do not restore the missing social, wallet, safety and 60-second confirmation evidence. Raydium support, transaction simulation/failure measurement and a true quote at each future paper decision remain open. The suite now contains 35 engineering checks.

## Buyer and order-book research

Read `Orderbook_and_Buyer_Research.md` for the frozen OB-0.1 challenger, source/receipt clocks, actual opportunity frequency, costs, partial wallet-history evidence and limitations. Its 12-minute public Alpaca `us` capture contains 288 repeated pair snapshots, not 288 independent tests. The full and book-only policies produced zero opportunities; the momentum replay has one censored entry, no filled account return.

```bash
python3 collect_orderbook.py --output data/new_book_capture --minutes 12 --interval 10
python3 orderbook_study.py data/new_book_capture/raw.jsonl --output results/new_book_capture
python3 buyer_probe.py --output data/new_buyer_probe --transactions 12
python3 wallet_history_probe.py data/new_buyer_probe
python3 amm_depth.py results/quote_probe_20261012_pass6/quote_results.json --output results/new_depth_diagnostic.json
```

The new collectors use public read-only endpoints without credentials or fees paid to data providers. Use new output directories. The buyer parser reads successful finalized PumpSwap events under the exact executing program/pool, with `maxSupportedTransactionVersion: 1`; it still needs CPI-event support, first-funding roots, complete mint participation and other-mint history. `recover_buyer_versions.py` reproduces the one-time correction of the preserved initial v0 failures, and refuses to repeat that correction on an already recovered folder.

`orderbook_study.py` computes nearby depth, a sampled OFI proxy, signed flow, credited-asset fees and displayed-book sweeps. It does not infer customer identities, order cancellation intent, queue priority or maker fills. Pending modeled inventory is neither a realized loss nor a completed account result. Snapshot-age rejection is conservative; an old source-update timestamp can mean an unchanged latest book. AMM curve depth is deterministic reserve arithmetic, not human bid walls. The offline controller now checks calendar limits on supplied receipts; a continuous event source remains unconnected.

The suite now has 49 engineering checks. No real orders, paid subscription, wallet funding or private key access occurred.

## Buyer quality and signed-flow challenge

`Buyer_Quality_and_Flow_Research.md` records the current increment. The enhanced buyer collector now checks log/CPI event representations without double counting, verifies exact event-account balances, and supports deeper bounded history retrieval. Two sampled buyers establish the fourteen-day age requirement; funding independence, first-time mint participation and trades in three other mints remain unverified. Balance records and tiny incoming transfers are preserved without upgrading them into those claims.

```bash
python3 buyer_enrichment.py audit data/buyer_probe_20261012 --output results/new_buyer_audit
python3 buyer_enrichment.py history data/buyer_probe_20261012 --output data/new_deep_history --max-pages 5
python3 flow_study.py --trades data/alpaca_flow_access_20261012 --quotes data/alpaca_flow_quotes_20261012 --output results/new_flow_replay
```

FLOW-0.2 is not promoted. Its October 9 conditional account ends at $49.75595 after three observed top-quote paths; all three midpoints rise but net returns are negative. October 10 retains an unresolved modeled entry and no forced recovery. Complete pages, original hashes, publication assumptions, temporal purging, unmatched controls and the earlier entry-count correction are retained. The model has no captured fills or completed thirty-day campaigns. It is a challenger test, not a replacement for the full SLR scheduler or its missing social/funding proof.

The suite now has 64 engineering checks. The public MELT dataset was assessed but not imported because its licence requires separate permission for commercial use. Continuing research uses independently collected public evidence.

## Offline campaign-accounting increment

`campaign_controller.py` checks timed confirmation, actual reserves, rent/cost events, rolling/daily entry limits, exit requests, bounded retries and local calendar deadlines. It never creates a fill from a quote or an exit threshold. `audit_ledger.py` now uses decimal cash/quantities and exact-zero closure; synthetic regression evidence preserves 12 strict-$100 rounding false positives and one dust false close from the old implementation.

```bash
python3 campaign_research_pass.py --output results/new_existing_record_audit
python3 campaign_controller.py results/campaign_audit_20261012/input_events.jsonl \
  --started-at 2026-10-12T00:24:28.095148+00:00 \
  --campaign-id reproduced-incomplete-record-audit \
  --output results/new_controller_replay
```

Use new output directories. These commands replay the same 66 incomplete records; all still reject, with no new market observation or completed campaign. The conditional $50 budget is unfunded and unverified for conversion/withdrawal. No matched control or daily opportunity-frequency estimate is created. Original failing cases, corrected output, prior code and full check output are retained; test fixtures are never profitability evidence.

Read `Campaign_Controller.md` for exact event fields, fee/rent/deadline conventions and remaining authentic-input, broker token-fee, FX, partial-exit and runtime dependencies. This is a paper research tool, not an autonomous trading bot.

## Prior-trade proof and proposed models

`buyer_trade_history.py` verifies authorized earlier PumpSwap trade events with exact signer/account/mint/owner and pre-target time. Forty new finalized reads, together with twenty older bodies, verify thirteen distinct prior trades. Two of five users establish three other mints traded; one also establishes fourteen-day activity. This does not prove independent people, profitable skill, first-time participation or a valid entry. Post-event receipt times prevent retrospective promotion.

```bash
python3 buyer_trade_history.py data/buyer_history_deep_20261012 \
  --additional-rpc data/buyer_trade_history_20261012/rpc.jsonl \
  --output results/new_prior_swap_audit --maximum 8
```

This command reuses saved evidence without requests. New bounded collection instead uses `--collect` and a new output folder. The completed collection has raw receipts and its original frozen selection; the refined offline audit has its own output. No trade, paid data, keys or account outcome were generated.

`entry_model_preregistration.json` is a future model/label/ablation plan, not an executable revised strategy. Start with simple baselines, CatBoost and competing-risk survival modeling; later compare TabPFN v2, TCN and temporal graphs. No trained model or validated net-label dataset exists yet. See `Models_and_Entry_Window_Research.md` for source evidence, current weight terms, chronology and missing inputs.

The complete `CodexCoinHunt` export also contains shared project/handoff notes. The intended Mac directory is `~/Projects/CodexCoinHunt`; the cloud session cannot write there directly. The installer preserves existing files and prior imported versions. Claude's unshared chats/code/findings are not included or presumed reviewed.

## Returning-buyer and native-funding audit

`Buyer_Participation_and_Funding_Research.md` documents FUNDING-AUDIT-0.1: forty new finalized bodies, forty-seven selected signature/wallet pairs and fourteen prior target swaps. Four sampled buyers accounting for 97.2101822278% of the original buy notional already bought this exact mint. The remaining buyer is unknown; no one has full new/seasoned/independent buyer proof. This is the same development cohort, not a fresh opportunity or net-return sample.

`buyer_funding_audit.py` performs an offline read-only audit with exact program/signer/time checks, preserving failed transactions, payment roles and transient token initialization/closure identity. Seventeen closures include fifteen WSOL releases and two other-token storage balances; none is promoted to an independent funder. No material signed native receipt candidate, initial funder or independent cluster is established.

```bash
python3 buyer_funding_audit.py --data data/buyer_funding_20261012 --output results/funding_reaudit_new_directory
python3 -m unittest discover -s tests -v
```

The suite now contains 122 distinct engineering checks. Prior reports/results/code and source receipts are retained. `participation_preregistration.json` freezes a future new-versus-returning buyer comparison with the same full costs, eligibility, campaign controller and matched controls; there are no new payoff labels or doubled campaigns. The collector refuses to overwrite existing raw evidence. Treat missing histories, carried-in quote capital and funding/service/creation links as explicit gaps.

## Quote assets and capital-origin roles

`Quote_Asset_and_Capital_Origin_Research.md` records QUOTE-PROVENANCE-0.1. The same five buys comprise three USDC/USDT disposals with routed WSOL, one other-mint disposal and one native-SOL quote input. The later complete-event audit explains two stable-prefix/outflow differences through exact instruction semantics and LP + protocol + creator fields; it does not book profit or invent a PumpPortal charge. Route sources, token owners, transfer authorities and fee payers remain separate. Current source roles cannot be backdated into eligibility, and neither common intermediaries nor distinct unknown addresses certify people.

```bash
python3 quote_asset_provenance.py --data data/quote_provenance_20261012 --output results/quote_route_reaudit
python3 audit_quote_participation.py --data data/quote_provenance_20261012 --output results/quote_participation_reaudit
python3 -m unittest discover -s tests -v
```

Nine new public reads are retained: one six-account bundle plus eight historical bodies for the fifth buyer. Six of those bodies succeed and two fail, with first participation still unknown. No money, order or private-key operation occurred. The historical 137-check state remains retained. `capital_origin_preregistration.json` specifies a later untouched comparison with unchanged SLR gates, full costs and matched account controls.

## Complete PumpSwap event-fee reconciliation

`pump_event_fee_reconciliation.py` uses the pinned official Pump AMM IDL to decode every retained event through its exact byte length. It selects gross and net quote fields by exact buy instruction, verifies LP + protocol + creator decomposition, recognizes buyback as a protocol-fee suballocation, and joins the five original buys to exact quote-account outflow.

```bash
python3 pump_event_fee_reconciliation.py --root . \
  --output results/fee_reconciliation_reproduction
python3 -m unittest discover -s tests -v
```

The five gross buy debits total 10.255334171 SOL. Instruction-aware gross matches account outflow five of five; the old stable-prefix `user_quote_raw` matches only the three `buy_v2` events. Do not add fee components again to a fee-aware SDK quote, gross debit or net fill. The correction has zero new entries, closes, matched account results or campaigns.

## Social coverage and paid visibility

`SOCIAL-COVERAGE-0.1` froze exact-address and project searches before collection. The public social endpoint returned HTTP 403 twice, so the result is unknown coverage—not zero posts or a quiet period. Raw errors, request/receipt clocks, queries and the stop condition are retained.

The exact-token paid-order endpoint reports a 10-unit boost paid about four hours six minutes before the first sampled buy. Six earlier exact-pair receipts show it active until 10 minutes 31.885 seconds before that buy. Paid visibility is a verified confounder and the fixed sample cannot support organic rediscovery. This does not prove causation or paid-only attention.

```bash
python3 social_evidence.py \
  --data data/social_evidence_20261012 \
  --output results/social_reaudit_new_directory
python3 -m unittest discover -s tests -v
```

`PROMOTION-HANDOFF-0.1` freezes a later-cohort test after a conservatively verified promotion end. It retains all SLR/campaign gates and matched controls, has no eligible signals or payoffs, and is not promoted. No new trade, opportunity rate, recovered-cash result, matched net comparison or doubling campaign was added.
