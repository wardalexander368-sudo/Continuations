# Paper campaign controller and strict account audit

Controller **SLR-CONTROLLER-0.1** adds offline accounting and timing enforcement to **SLR-0.2**, whose investment thresholds and configuration hash remain unchanged. It has no network, order, wallet, signing or credential functions. Quotes create paper intents; only separately supplied evidence-linked paper fills change cash or inventory. Nothing in this increment demonstrates an investment edge.

## Implemented contract

| Rule | Behavior |
| --- | --- |
| Confirmation | Two evidence-complete observations at least 60 seconds apart. Dynamic feature availability must advance; repackaged old inputs cannot confirm. Rejection, changed exact identity or a gap beyond the existing 300-second feature budget restarts the wait. |
| Identity and access | Match Solana 32-byte mint, venue, pool and route. Existing explicit US, venue and safety gates apply. Their external evidence is asserted, not authenticated by this program. |
| Sizing and funding | One open position or pending entry; all-in debit at most 14% of cash after unpaid-fee reserves. Fund rent separately and protect the greater of $5 and stated remaining gas needs. Recheck sizing when costs arrive before a fill. |
| Frequency | Three successful paper entries per rolling 24 hours; same-mint cooldown 24 hours. Failed entries incur their stated cost but consume neither quota nor cooldown. |
| Session loss | Stop entry at a $5 net realized loss per America/Chicago calendar day. Include realized partial-sale basis and cost accruals. Same-day gains can offset losses under this interpretation. |
| Risk exits | Request exit at 0.8× net liquidation value, two distinct consecutive complete five-minute buyer-stall windows, or a 20% comparable usable-liquidity decline. Require exact pool and the same declared liquidity metric; TVL and size-specific depth are not interchangeable. |
| Capital recovery | At 2× aggregate net position value, use fresh exact-size partial quotes to cover original cost, separate failed-exit costs and expected remaining exit costs. Choose the smallest qualifying supplied quantity; global token-lot minimum proof remains an adapter dependency. |
| Runner | Reconciled proceeds must actually meet the recovery target. Request a fresh quote for the remainder rather than subtracting full/partial quotes to invent its value. Trail a 25% decline from its subsequently observed net liquidation high. |
| Time limits | At 90 minutes, require fresh valuation for the conditional 1.25× exit unless the thesis is freshly evidenced as strengthened. Missing valuation causes a quote request. At six hours, request full exit and supersede unfilled recovery intents. Record overdue inventory without backdating a fill. |
| Retries | Initial attempt plus at most two retries, each with recorded cost. After three failures, retain unresolved inventory and block entry. Missing routes or observations do not automatically imply zero recovery. |
| Campaign | Halt entry at $40 fresh liquidatable equity, 30 closed positions or 30 local calendar days. Gaps can overrun the floor. The final permitted closed position may achieve the target. |
| Strict success | Flat inventory, no pending intent/unpaid fee, complete externally asserted cost/funding/conversion reconciliation, and strictly more than $100 before the calendar deadline. Exclude locked rent until an evidenced refund. A later cost revokes a provisional claim and preserves entry standdown while reconciling. |

Calendar days preserve Chicago wall time. A synthetic October 12 00:00 UTC start expires November 11 01:00 UTC, **721 elapsed hours** across the daylight-saving change. This fixture is not an observed month-long campaign. A controller cannot enforce a real fill deadline between absent receipts; a continuous event source and clock remain unconnected.

## Two repaired false-success cases

The old fill auditor used floating cash arithmetic and a `1e-9` token closing tolerance. In a synthetic sweep of 99 cent-cost examples whose exact final cash was $100, **12 falsely passed the strict >$100 target**. A second fixture sold `0.999999999` of one token; the remaining `0.000000001` token was incorrectly treated as closed and could also permit success.

`audit_ledger.py` now uses Decimal for amounts and threshold decisions and closes only exact zero. It retains the numeric JSON interface alongside exact cash/remainder strings. All 12 saved false positives fail correctly; dust stays open until sold or supported by a documented zero-recovery writeoff. Original rows, failing output and prior code hash are in `results/campaign_legacy_counterexamples.json`; corrected output is in `results/campaign_audit_20261012/legacy_corrections.json`. Prior code is archived under `versions/`.

These are manufactured boundary checks, not token observations, returns or proposed trades. No prior genuine SLR campaign changed: verified positions and doubling campaigns were already zero.

## Evidence and checks

Fresh documentation was retrieved **2026-10-12 03:01:35.849–03:01:36.889 UTC**; the raw response and receipt interval are retained in `data/campaign_sources_20261012/raw_web_evidence.json`. PumpPortal still publishes Local 0.5% and Lightning 1%, before slippage and excluding network/pool fees [S05]. Alpaca publishes first-tier maker 0.15% and taker 0.25%, charged on the received asset; its documentation says activity can post at day end [S08]. Missing same-day fee activity is therefore insufficient evidence of zero fees. The Alpaca adapter must reserve received-token fees in quantity, then reconcile actual activity; USD escrow alone cannot fund a token-denominated debit.

Solana documents refundable storage balances [S30] and network fees charged on failed transactions [S31]. Rent cannot simultaneously count as spendable gas and recovered cash; retries require both recorded costs and actual SOL funding. No priority-fee amount, rent estimate, FX rate or failure probability was invented.

**100 engineering checks pass:** previous 64, 34 controller tests and two auditor regressions. Initial failures and corrected results are preserved. One early failure was an obsolete valuation request displayed with a fresh exit decision; another was a fixture violating the actual same-mint cooldown. Neither justified loosening the strategy. Test functions and their synthetic fills are not independent investment observations.

The same **66 incomplete real candidate records** were replayed and all remain rejected. Their original 12-minute market capture was 00:24:28.095148–00:36:28.095713 UTC; the replayed endpoint decisions span only 00:36:02.827057–00:36:09.528366 UTC. No new observations, opportunities, forward campaigns or calendar timeouts were added. The unspent conditional budget is $50, without funding/conversion recovery verification. Random has no qualified opportunity to match, attention inputs are missing, and earlier separate momentum/FLOW/OB results remain unpaired. No matched account superiority or daily opportunity-rate estimate is available.

## Inputs and reproduction

Every receipt event requires distinct `event_id`, timezone-aware `at`, `kind` and `evidence`. Receipts are chronological; optional source time cannot be future information. Invalid rows fail atomically, and the raw input retains the rejected evidence. A malformed stream is incomplete until reconciled.

- `candidate`: the existing `record` feature schema and matching decision/receipt time. A qualifying second observation needs a complete `entry_quote`.
- Quotes: unique quote ID, exact identity `{chain,mint,venue,pool,route}`, evidence, source/availability times no older than two seconds, side, exact quantity, explicit complete costs and all-in USD debit or net USD credit. Entry also needs remaining gas, rent lock/account ID and named comparable usable-liquidity basis. Recovery needs fresh partial quotes and expected remaining exit cost.
- `fill`: explicit `mode:"paper"`, matching pending action and exact position identity, quantity, net cash amount after fees and complete-cost evidence. A sale can recover less than its quote. No quote alone creates a fill.
- `failure`: matching action, unique economic cost ID and explicit actual nonnegative USD cost. Missing cost never defaults to zero.
- `buyer_flow_window` and `liquidity`: exact identity, complete fresh windows or comparable named liquidity basis.
- `cost`, `cost_accrual`, `cost_settlement`: unique economic IDs; reserve unpaid estimated costs, then settle actual cash and adjust only the difference. Fees already in net fills cannot be counted again.
- `rent_refund`: exact locked account and evidenced USD-basis refund; closure costs/FX differences need separate reconciliation.
- `writeoff`: exact remaining position and documented zero recovery. An outage is insufficient.
- `settlement_check`: current net recoverable amount and explicit complete cost, funding/conversion and no-other-inventory verification. Open inventory, pending intent or unpaid fee blocks certification.
- `heartbeat`: evaluate elapsed rules at this receipt without fabricating earlier market data or execution.

Use decimal strings. Fee-included token quantities must already deduct credited-asset fees. Live SOL/rent FX accounting, broker token-fee liabilities, order increments, route acceptance, partial-sale minimum proof, transaction-failure simulation and actual conversion/withdrawal verification still need adapters. This cash book uses USD basis and does not authenticate external flags. It serves Solana SLR; Alpaca challengers retain their separate listed-asset coverage and identities.

Python 3.10+ and its standard library suffice, with a Chicago IANA timezone database. Choose new output folders:

```bash
python3 -m unittest discover -s tests -v
python3 campaign_research_pass.py --output results/new_existing_record_audit
python3 campaign_controller.py results/campaign_audit_20261012/input_events.jsonl \
  --started-at 2026-10-12T00:24:28.095148+00:00 \
  --campaign-id reproduced-incomplete-record-audit \
  --output results/new_controller_replay
```

These commands reuse evidence; they do not collect a new sample. Hashes, original implementation freeze and engineering corrections are in `campaign_preregistration.json`. SLR remains `9bcd83ce0ec71cdae8c410c202bd5a75b1496679e5ddb94ccc7d300e57c3663f`.

Next: verify other-mint swap history and meaningful funding ancestry, connect social/quote adapters, and compare buyer-plus-book mechanisms and full liquidation versus a runner in a later untouched period. Apply identical whole-account rules to matched random, attention and momentum controls and preserve missing/unmatched outcomes.

- **S05:** [PumpPortal fees](https://pumpportal.fun/fees/), checked October 12, 2026.
- **S08:** [Alpaca fees](https://docs.alpaca.markets/us/docs/crypto-fees), checked October 12, 2026.
- **S30:** [Solana accounts](https://solana.com/docs/core/accounts), checked October 12, 2026.
- **S31:** [Solana fee structure](https://solana.com/docs/core/fees/fee-structure), checked October 12, 2026.
