# PROVENANCE, RED-REJECT-2026-v2

End-to-end provenance ledger from the operational fleet to this deposit.

## 1. Collection

**Producer.** A purpose-built follow-up-tracking process (a Node.js daemon under a process manager) on a dedicated research server. The tracker consumes filter-rejection events fired by a paper-trading fleet and re-samples each rejected token's live market state at scheduled intervals.

**Observation window.** `sampleTs` UTC first observation `2026-04-11T20:26:53.379Z`; last observation `2026-07-16T21:57:03.283Z`. The window spans 96.06 days and contains one collection gap: no samples were recorded between `2026-06-04T06:32Z` and `2026-06-24T16:38Z` (about 20.4 days), and no rejection events are present between `2026-06-03T06:35Z` and `2026-06-24T16:34Z`. Allowing for the gap, the window contains about 75.6 days of sampling coverage. Outside the gap, the append-only writer resumed writing to the same JSONL file after routine process-manager restarts.

**Data feeds** (all public, all free-tier):
- Helius WebSocket, on-chain events feeding the fleet's filter evaluations (the tracker itself does not consume Helius; the source of the rejection event does).
- DEX Screener REST, token price, liquidity, volume, rolling price changes at sample time.
- CoinGecko, BTC/USD spot and 24-hour change (feeds `regime.btc_usd` and `regime.btc_change_24h_pct`).
- Alternative.me, crypto Fear-Greed Index (feeds `regime.fear_greed_index` and `regime.fear_greed_label`).

## 2. Frozen v1 source archive

**Outer archive:** `RED-REJECT-2026-v1.zip`, SHA-256 `1aeb0b96…328b9ca0` (73,299,873 bytes). Verified this pass.

**Inner data file:** `RED-REJECT-2026-v1/data/rejection_outcomes_full_v1.jsonl.gz`, SHA-256 `17e31658ffd9ed7adcb08d7081c3f7718428e462e10704b1d8d5bf0ad3cd07d9` (73 MB gz, 436 MB raw, 716,762 valid JSON rows). Deposited at Zenodo record `10.5281/zenodo.21402477` (v1, 2026-07-16).

**Verification.** Every normalization run stream-hashes the inner gzip directly from the outer zip and refuses to proceed on mismatch (`scripts/normalize.py`).

## 3. Canonicalization (`normalized_public.jsonl`)

**Frozen spec:** `../schema/CANONICALIZATION_SPEC.md`, SHA-256 `5384223bfe66248fc8ad82f76f63f68bbaa31bc1cddad12871fd2938f955d76f`. Frozen 2026-08-21 before the corrected event/sample tables were computed; later revisions change wording only and are listed in `../CHANGELOG.md` (the v2.2 file had SHA-256 `4e6357fb3854ad96519f387f483739d867c635943040c93c5467d1214ebb399e`).

**Private producer map.** `producer_pseudonym_map.json`, SHA-256 `d687a82db4853e6313bc6de0446156a5197447b9538e7731f3577ee570239a7d` (see `PRIVATE_MAP_FINGERPRINT.txt`). Held outside every public artefact. Not required to *consume* this deposit; required only to byte-for-byte re-derive the `source_pseudonym` column. Consumers who wish to regenerate that column from a private mapping of their own must sort the six raw producer labels within each family alphabetically and assign `producer_a_v1..vN` / `producer_b_v1..vM` (six labels total; see canonicalization spec §4).

**Canonicalization outputs (intermediate, uncompressed):**

| file | rows | SHA-256 |
|---|---:|---|
| `normalized_public.jsonl` | 716,762 | `b90a8ea57ac1675e14ffd708624c138ea2094734986297cc193de287707d7683` |
| `row_transformation_ledger.csv` | 716,763 (with header) | `31841add7a8e7333df4b3a318a53558c1402add0486abc61d6e87431449a4101` |
| `quarantine.jsonl` | 0 (empty file) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

**Row-count reconciliation to the v1 forensic audit** (see `NORMALIZATION_FINGERPRINTS.sha256`, `normalization_summary.json`):

| statistic | v1 audit | v2 canonical | match |
|---|---:|---:|---|
| valid JSON rows | 716,762 | 716,762 | yes |
| variant 1 (V3 primary) | 600,855 | 600,855 | yes |
| variant 2 (V1 early primary) | 99,225 | 99,225 | yes |
| variant 3 (V2 primary) | 8,326 | 8,326 | yes |
| variant 4 (b3 alt) | 6,373 | 6,373 | yes |
| variant 5 (b3' alt) | 1,300 | 1,300 | yes |
| variant 6 (b3+ alt) | 283 | 283 | yes |
| variant 7 (b1 alt) | 216 | 216 | yes |
| variant 8 (b2 alt) | 128 | 128 | yes |
| variant 9 (b4 alt) | 52 | 52 | yes |
| variant 10 (b0 alt) | 4 | 4 | yes |
| rows with a source field | 617,537 | 617,537 (six pseudonym buckets) | yes |
| rows lacking a source field | 99,225 | 99,225 (`source_pseudonym = null`) | yes |

Family-2 timestamp normalization eliminated every null-`sampleTs_utc_ms` row: `queriedAt` was converted for all 8,356 family-2 rows.

## 4. Event / sample / duplicate model

**Rules:** canonicalization spec §5.
**Outputs (fingerprints):**

| file | rows | SHA-256 |
|---|---:|---|
| `event_table.csv` | 18,237 | `9d1b6f2385ae508244b84badcc68df1f0af0ce6d03a7e26220b557fe2703b00e` |
| `sample_table.csv` | 716,762 | `8e1735b7a1bf78281a81840e7a88b5aad4ffc958b3b08cb90654ebd67fedbca3` |
| `duplicate_classification.csv` | header only | `f6386e91cfdbbf3d2638f6fb3df2d6e13f1ae6abc018e760e46dd4402e1b0e03` |
| `alt_venue_report.csv` | 4,278 | `160d7cd31f283d1b6b5ed68769d7ae05a515f0bdf1b17cc164a1d97c77a86b93` |
| `conflict_report.md` | narrative | `6b9772225487c8336aafbacc6c77ebf5b356f3ad9eab1892aaceb5682ef147d1` |

**Corrected model:**
- Distinct events (`event_id`): **18,237**
- Distinct mints: **4,635**
- Mints with more than one distinct event: **3,253**
- Events with more than one `(dexId, pairAddress)` value: **4,278**; in 4,190 of them the only additional value is null (legacy family_2 rows carry no venue), and **88** are observed on two or more identified trading pools (78 on two or more exchanges)
- Distinct samples (`sample_id`): **716,762**, every canonical row is a unique observation
- `sample_id` exact-duplicate clusters: **0**
- `sample_id` conflicting-value clusters: **0**
- `(mint, sampleTs_utc_ms)` collision clusters: **0** (the v1 audit's headline of 1,286 clusters was entirely a downstream symptom of the family_2 missing-`sampleTs` schema failure; canonicalization eliminates it)

## 5. Compressed release artifact

**File:** `data/rejection_outcomes_corrected_v2.jsonl.gz`
**Size:** 125,981,598 bytes
**SHA-256:** `34fe7a1af336d68b5a25ab8f1d1b12de93445ef1becbe741b9629fd238fd19a9`
**Compression:** gzip level 9, `mtime = 0`, embedded filename `rejection_outcomes_corrected_v2.jsonl`. Reproduces byte-for-byte from `normalized_public.jsonl` on any environment satisfying `environment.txt`.

## 6. Producer-identity clearance

Pre-publication clearance ran against the same public-safe rules stated in `../schema/CANONICALIZATION_SPEC.md` §4 and §13; all deposited files passed.

## 7. Invariants

- The v1 outer zip and inner gzip are unmodified.
- The private pseudonym map is not published anywhere; only its SHA-256 fingerprint is in this deposit.
- No claim of "complete rejection capture" is made in the corpus or the manuscript; see `COMPLETENESS_AND_CENSORING.md`.
