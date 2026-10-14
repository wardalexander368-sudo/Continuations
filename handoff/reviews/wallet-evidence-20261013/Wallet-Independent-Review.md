# Independent wallet data review

Reviewed the descriptive verified cohort, expanded saved activity, public snapshot
and null account-role display. No profitability or identity assessment was made.

## Reproduced finding

**Initial public RPC responses lack original HTTP bytes.** All 56 receipts retain
parsed JSON plus transport-time response length and SHA-256, but none retain the
original bytes, base64 or response text. Common lexical JSON re-encoding reproduced
48 hashes; request IDs 13, 16, 17, 23, 42, 47, 54 and 56 remained unreconstructed.
The saved receipt JSONL hash reproduced. This limits acquisition provenance; it
does not demonstrate incorrect parsed balances. The report and dashboard disclose
the limit. Future collector code retains original responses as base64; the initial
collection remains unchanged.

Reproduction:

```python
import json
from pathlib import Path
receipts = [json.loads(s) for s in Path("Wallet-Public-RPC-Receipts.jsonl").read_text().splitlines()]
print(len(receipts))
print(sum(any(k in r for k in ("raw_response", "raw_response_base64", "raw_response_text", "raw_bytes")) for r in receipts))
print(sum("raw_response_sha256" in r for r in receipts))
```

Observed output: `56`, `0`, `56`.

## Independently reproduced calculations

- 120 unique saved bodies: 117 successful and 3 failed.
- 47 successful swaps attributed to the wallet signer and base-token owner;
  45 complete current-IDL decodes with exact fee equations.
- The selected target episode has five buys and two sells, gross buy debit
  10.255334171 SOL; the eighth audited fee event is an other-mint route sell.
- Largest buyer share 87.3543408105877%; verified returner share 97.2220091588471%.
- Expanded prior target history: 15 buys and 3 sells. Prior other-mint history:
  21 events. Every counted prior block time precedes its wallet cutoff.
- All canonical source and generated verified artifact hashes.
- Public snapshot: 56 receipts, seven exact native balances, 498 token-account
  records, 350 signature references and 21 successful transaction bodies.
  Five bodies correctly show that the wallet was not a signer.
- Five UI/raw token differences remain preserved. Both null account-role
  responses render as unknown; neither is labeled a healthy or non-executable
  system account.

## Not checked

Unsaved archive/full pool history, live endpoint authenticity, cryptographic
signature verification, full wallet PnL/cost basis/net worth, human identity,
independent ownership, ultimate funding origin, individual Token-2022 mint
extension configuration and the unfinished archive dashboard were not checked.
This review used saved finalized RPC bodies, success metadata, signer flags and
exact token ownership. Browser and archive checks are reported separately.
