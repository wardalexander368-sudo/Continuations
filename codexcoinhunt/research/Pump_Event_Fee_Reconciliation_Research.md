# PumpSwap complete-event fee and exact-debit reconciliation

October 12, 2026 UTC. This is a post-observation forensic correction on the same fixed Claudia transactions. It is not a new opportunity, entry, payoff observation, matched comparison or strategy revision. SLR-0.2 remains unchanged at SHA-256 `9bcd83ce0ec71cdae8c410c202bd5a75b1496679e5ddb94ccc7d300e57c3663f`.

## Material correction

The two previously unexplained approximately 0.45% gaps are fully explained by the complete official `BuyEvent` fields. They were not unknown extra costs. The stable-prefix parser always named field 14 `user_quote_raw`, but PumpSwap's two buy families assign economic roles differently:

- `buy`, `buy_v2` and `buy_v3`: `quote_amount_in` is curve input and `user_quote_amount_in` is gross user debit.
- `buy_exact_quote_in`, `_v2` and `_v3`: `user_quote_amount_in` is curve input and `quote_amount_in` is gross user debit.
- In both families, gross minus curve input equals `lp_fee + protocol_fee + coin_creator_fee` in the retained sample.

For the two exact-quote buys, the old comparison used curve input against whole-account outflow. The difference is exact in raw units:

- `8i8W…XttG`: `8,958,479,563 − 8,918,346,999 = 17,836,695 + 4,459,174 + 17,836,695 = 40,132,564`.
- `3uzy…dej4`: `746,250,000 − 742,906,918 = 1,485,814 + 371,454 + 1,485,814 = 3,343,082`.

This is an event-semantics correction, not evidence that costs are lower than previously modeled. The complete gross debit was already present in the exact token movement. It must be used once, not combined with the same fee fields a second time.

## Five-buy reconciliation

All values below are raw WSOL units with nine decimals. Exact pool `Fe7bpDYCs74GqiCUF14HwgUMToPKV1d9mDYVX5BTohFr`; exact mint `2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM`.

| Event user | Instruction | Curve input | Gross debit | LP fee | Protocol fee | Creator fee | Exact account outflow |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `CSx2…eRFZ` | `buy_v2` | 283,615,972 | 284,892,244 | 567,232 | 141,808 | 567,232 | 284,892,244 |
| `6KBt…aJfD` | `buy_v2` | 220,690,682 | 221,683,792 | 441,382 | 110,346 | 441,382 | 221,683,792 |
| `3uzy…dej4` | `buy_exact_quote_in_v2` | 742,906,918 | 746,250,000 | 1,485,814 | 371,454 | 1,485,814 | 746,250,000 |
| `FXh9…YHcn` | `buy_v2` | 43,831,330 | 44,028,572 | 87,663 | 21,916 | 87,663 | 44,028,572 |
| `8i8W…XttG` | `buy_exact_quote_in` | 8,918,346,999 | 8,958,479,563 | 17,836,695 | 4,459,174 | 17,836,695 | 8,958,479,563 |

The five gross debits total **10.255334171 SOL**. The four previously demonstrated returning buyers supply **97.2220091588%** of that gross amount, versus 97.2101822278% under the mixed-semantics field. The largest buyer supplies **87.3543408106%**. These small descriptive corrections do not change the prior-participation falsification, certify independence or create a profitable signal.

## Complete fixed-event audit

`pump_event_fee_reconciliation.py` decodes the full current IDL layout and requires exact byte consumption. It processes all retained successful transaction bodies, de-duplicates log/CPI copies by payload while retaining occurrence counts, and refuses unknown buy instruction semantics.

- Eight unique events decode: five buys and three sells. All eight appear in both log and CPI form but count once.
- All eight satisfy gross/net difference = LP + protocol + creator fee.
- All eight satisfy the intermediate LP bridge field.
- All eight report a `buyback_fee` equal to the configured integer subdivision of the protocol fee. It is not an additional fee.
- Seven events report nominal 45 bps total component rates; one sell reports 50 bps because its creator/holder-reward component is 25 bps. This tiny fixed set is not a fee-frequency estimate.
- All five buy gross amounts match exact quote-account token outflow. The old stable-prefix field matches only the three `buy_v2` events.

Cashback, holder-reward and buyback fields describe fee routing or suballocation in these events. They must not be blindly added to LP + protocol + creator fees. `creator_fee_unclaimed` is an accumulator, not a per-trade debit.

## Cost-ledger rule

For future paper receipts:

1. Prefer authenticated net fill/account movement as the economic debit or credit.
2. When only a complete PumpSwap event is available, select gross and net fields by exact `ix_name` and require the fee equation.
3. Reject an unknown instruction name, truncated schema, unexplained byte tail or failed equation; do not guess.
4. Do not add pool fee components again when a fee-aware SDK quote, gross debit or net fill already includes them.
5. Add PumpPortal service charges, Solana network/priority fees, rent exposure, conversion/off-ramp costs and paid data only when applicable and not already included. PumpPortal documents Local 0.5% and Lightning 1% separately from network and venue costs.

The existing fee-aware PumpSwap SDK quote already embeds pool economics in its route output. The quote-capacity result therefore does not receive a new 45 bps surcharge. Its separately modeled PumpPortal Local service charge and adverse-execution allowances remain separate assumptions.

## Evidence and limitations

The pinned official IDL was received **2026-10-12 05:49:14.024403 UTC** and has SHA-256 `b7d8c57a4d9c4dd0109a9ab893052352333252d4eedced10ac091d4d66cab89b`. Primary-source pages were refreshed at **12:37:23.014673 UTC**. Raw transaction bodies retain their original receipt times in `data/buyer_probe_20261012/rpc.jsonl`. The explanatory analysis plan explicitly discloses that the discrepancy and exploratory fields were inspected before it was frozen.

Canonical outputs are in `results/pump_event_fee_reconciliation_20261012/`. The implementation adds nine adversarial/integration checks, bringing the complete suite to **161 distinct passing engineering checks**. Engineering correctness is not investment validation.

There are still zero evidence-complete strategy entries, zero closed strategy positions, zero matched net-account outcomes and zero doubled campaigns. No opportunity rate, US venue acceptance, realized USD recovery or out-of-sample performance was added.

## Sources

- S47: [Official Pump AMM IDL](https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump_amm.json), refreshed October 12, 2026.
- S48: [Official PumpSwap program documentation](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_SWAP_README.md) and [creator-fee documentation](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_SWAP_CREATOR_FEE_README.md), refreshed October 12, 2026.
- S49: [Official trade-v3 fee-routing documentation](https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/TRADE_V3.md), refreshed October 12, 2026.
- S05: [PumpPortal published fees](https://pumpportal.fun/fees/), refreshed October 12, 2026.

## Reproduce

From the extracted kit, using a new output directory:

```bash
python3 pump_event_fee_reconciliation.py \
  --root . \
  --output results/fee_reconciliation_reproduction
python3 -m unittest discover -s tests -v
```
