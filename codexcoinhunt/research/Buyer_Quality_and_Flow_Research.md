# Buyer quality and fee-surviving flow — research increment

UTC research receipts: October 12, 2026; America/Chicago date October 11. Paper-only. SLR-0.2 remains unchanged and unvalidated.

## Concrete improvement

The buyer parser now verifies successful PumpSwap provenance for both log and inner-instruction (CPI) events, checks the Anchor CPI tag, and merges equivalent representations without collapsing repeated actual occurrences. It reconciles each event to the exact token account, mint and owner in transaction metadata. Reading a mint somewhere in a transaction is no longer sufficient evidence for that event account.

The same fixed 12 finalized transactions were re-audited, not counted as new observations. All seven swaps appeared in both logs and CPI metadata and reconcile to the exact event account. Counting the representations separately would have doubled observed swap notional. No extra swap was recovered, so original five-buy/two-sell and 87.33% largest-buyer results remain.

Five buy-event users have notional HHI 0.769270, equivalent to 1.2999 equal-sized buyers. This is a diagnostic of quote-notional concentration, not a count of independent people and not a new fitted entry threshold.

## Deeper buyer-history evidence

Forty-two fresh finalized public RPC responses retrieved up to five pages of 100 signatures per user and inspected four prior transaction bodies per user. Two wallets establish at least fourteen days of earlier activity. The other three remain unknown because their pages reach only a recent prefix, not a verified birth or complete archival history. All five have other-mint balance evidence; that does not establish the required trades in three other mints.

| Exact event wallet | Prior age lower bound | Signature pages | Other-mint balance identities | 14-day requirement |
| --- | ---: | ---: | ---: | --- |
| `3uzy6vZMwwgHRrbe86YYFKZj2XaQjWXijqcnV3T6dej4` | 265.31 days | 3 | 5 | Verified |
| `6KBtrzj3Rxew41MD5ydL3AiB7WwTjLtFUKsSEf9yaJfD` | 3.13 days | 5 | 3 | Unknown |
| `8i8WsSj27j998Z7fqjw4JLeBBo7FkAPfqoNKEhYzXttG` | 15.41 days | 4 | 4 | Verified |
| `CSx2gDhH9nw6vqknJkrHVCaWWDDr6sLbRvtJkiUieRFZ` | 2.53 days | 5 | 4 | Unknown |
| `FXh9XcdM38anfSjMjqvPsj7zk2ttzJbwtDCzDhR6YHcn` | 7.12 days | 5 | 4 | Unknown |

The four observed incoming native transfers range from 1 to 6,238 lamports (at most 0.000006238 SOL). They are recorded as transfers, not initial funding roots. None identifies a verified common funder between these buyers, and absence of a link is not proof of independence. Dust, refunds and routine service payments must not manufacture buyer clusters. First funding, service labels, creator links, full mint participation and independently verified cluster coverage remain unknown. Receipt timestamps postdate the sampled swaps; these profiles cannot retroactively make the old decision eligible.

## Signed-flow challenge

FLOW-0.2 was frozen at 2026-10-12T02:15:10.934116+00:00 with SHA-256 `6a06c5cddec93e6df232a191c92f20b1653e4125b8dce378728a6875aceb3123` before quote outcome analysis. FLOW-0.1 is retained; 0.2 clarified that freshness is at most two seconds after an explicitly assumed two-second historical publication lag. The source can therefore be up to four seconds old. This is an assumption because historical arrival timestamps are not provided. Neither version was selected using returns.

Rules: at least $50 signed buys and at least 60% buy-side notional in the previous minute, spread no greater than 100 bps, sufficient top-quote size, later entry at least five seconds after the decision within a 30-second deadline, and a one-hour exit with a 30-second quote deadline. Each model begins with $50, uses 14% allocation, one open position, at most three actual entries per 24 hours, a 24-hour same-pair cooldown and a $40 floor. A missing entry quote is a rejected attempt, not an entry quota consumed. The earlier implementation that counted rejected attempts is archived, and the mechanical correction is disclosed.

The source returned 93 signed trades and 249,457 quote rows across eight complete paginated symbol/day requests. There are 243,121 distinct cross-partition quote records and 6,336 overlapping rows. All raw pages, UTC retrieval times and pagination states are retained. These are historical observations, not independent trade trials. Development is October 9; the later chronological comparison is October 10. Development signals whose exit could enter the later date are purged. Both daily runs are partial campaign illustrations, not thirty-day campaigns or fresh forward validation.

| Result | October 9 development | October 10 chronological comparison |
| --- | ---: | ---: |
| Returned signed trades | 54 | 39 |
| Raw minute-flow triggers, including repeated windows | 22 | 3 |
| Observed entry-and-exit quote paths | 3 | 0 |
| Missing entry quote | 1 | 0 |
| Entered modeled position with censored exit | 0 | 1 |
| Conditional cash at end | $49.75595 | $43 plus unresolved modeled $7 allocation |
| Matched random or momentum return pairs | 0 | 0 |
| Validated doubling campaigns | 0 | 0 |

The three completed development paths all gained at midpoint prices: PEPE +0.2611%, BONK +0.3026%, WIF +0.8122%. After crossing the historical ask/bid, the published 0.25% taker charge in the received asset on each side, and a separately assumed 0.25% adverse allowance on each side, net position returns are **−1.2541%, −1.5927%, −0.6450%**. Thus directional success alone does not create net growth in these observed examples. The conditional $50 account ends at approximately **$49.76**. These are top-quote replays, not fills, and current fees are assumed rather than proven exact historical charges.

The later day's DOGE entry has no quote in the permitted one-hour exit window. It remains unresolved and pauses the model; the $7 is neither a realized loss nor an unsellable-token conclusion. Random controls matched on contemporaneous eligibility and 25-bps spread bucket were unavailable, and no eligible positive-momentum peer existed at the admitted signals. The records retain unmatched decisions rather than relaxing the controls after seeing returns. The attention control is missing social evidence. No superiority claim is possible.

Assumptions and gaps: funded USD, no conversion cost, no additional broker charge and free public data provider access; quantity increments, personal US-state/account eligibility, actual order acceptance, complete depth, queue behavior, fills and recoverable bank withdrawal are unverified. No cost or private-key action occurred.

## Candidate decisions

Keep SLR-0.2 as the leading research hypothesis, with no profitability promotion. Do not promote raw signed-buy dominance from this two-day study. It may predict small upward moves while its fees consume them; the later comparison still lacks a closed outcome. Continue testing audience change, distinct demand conversion and economically meaningful buyer diversification against costs. Evaluate concentration as an ablation in a later untouched period rather than retrofitting a new 1.3-buyer threshold to these five wallets.

Funder graphs need a verified funding basis, known service boundaries and timestamps. Neither a shared exchange withdrawal address nor a tiny incoming transfer should automatically collapse wallets. Native transfers among old transaction bodies are useful evidence leads, not ownership declarations.

## New dataset assessment

The MemeTrans paper links to its successor, MELT, a public launch-risk research project with bundle traces and parsed data. Its repository states CC BY-NC 4.0 and requires separate author permission for commercial use. We did not download or adopt its datasets, feature pickle, code or predictions for the Resolant trading strategy. It is retained only as a cited research lead; original public-chain evidence allows work to continue without relying on that licence. A risk label or published reduction of simulated losses is not proof of our account doubling.

## Reproduce

```bash
python3 buyer_enrichment.py audit data/buyer_probe_20261012 --output results/new_buyer_audit
python3 buyer_enrichment.py history data/buyer_probe_20261012 --output data/new_history --max-pages 5
python3 flow_study.py --trades data/alpaca_flow_access_20261012 --quotes data/alpaca_flow_quotes_20261012 --output results/new_flow_replay
python3 -m unittest discover -s tests -v
```

All source and new output folders should remain distinct. No scripts send an order or use a keypair. The suite contains 64 engineering checks, not strategy validation.

## Primary references

- [Solana Anchor event provenance and CPI tag](https://solana.com/docs/programs/anchor-events), [transaction balances](https://solana.com/docs/rpc/json-structures), and [transaction versions](https://solana.com/docs/core/transactions/versioned-transactions), checked October 12, 2026.
- [Alpaca historical quotes](https://docs.alpaca.markets/us/reference/cryptoquotes-1), [historical trades](https://docs.alpaca.markets/us/reference/cryptotrades-1), and [fees](https://docs.alpaca.markets/us/docs/crypto-fees), checked October 12, 2026.
- [MemeTrans/MELT paper](https://arxiv.org/abs/2602.13480) and [successor repository/licence](https://github.com/git-disl/MELT), researched October 12, 2026; dataset not adopted.

