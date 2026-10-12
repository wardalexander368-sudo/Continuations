# RED-REJECT-2026-v2, schema (corrected release)

This release supersedes RED-REJECT-2026-v1 (2026-07-16). See `../CHANGELOG.md`
for the full rationale. This schema document describes the corrected
canonical corpus `data/rejection_outcomes_corrected_v2.jsonl.gz`.

The canonical corpus is one JSONL file (one JSON object per line) with a
frozen 29-column schema. Every input row from the original v1 gzip becomes
exactly one canonical row; provenance from the multi-schema input is
preserved via explicit `schema_variant`, `producer_family`, and
`source_pseudonym` columns.

**Companion tables** (bundled alongside the JSONL):

- `data/event_table.csv`, one row per distinct rejection event (18,237 rows).
- `data/sample_table.csv`, one row per canonical sample (716,762 rows).
- `data/alt_venue_report.csv`, events with more than one `(dexId, pairAddress)` value, a null value included (4,278 rows; 88 of them on two or more identified trading pools).
- `data/conflict_report.md`, narrative report on the duplicate/conflict classification (all-clear after canonicalization).
- `data/duplicate_classification.csv`, header only; the corrected event/sample model has zero exact-duplicate and zero conflicting-value sample clusters.

The exact canonicalization rules were frozen in
`../schema/CANONICALIZATION_SPEC.md` (SHA-256
`5384223bfe66248fc8ad82f76f63f68bbaa31bc1cddad12871fd2938f955d76f`) before
the corrected tables were computed. That spec is the authoritative source.
This document is a user-facing summary.

---

## Canonical row schema (29 columns)

| # | field | type | nullable | first appears | description |
|--:|---|---|:---:|---|---|
| 1 | `row_id_original` | string (7-digit zero-padded) | no | v2 | Input line number in the source gzip; monotonic and unique per row. |
| 2 | `schema_variant` | int (1-10) | no | v2 | Which of the 10 observed input field-set signatures produced this row. |
| 3 | `producer_family` | string enum | no | v2 | Derived from `schema_variant`: `family_1` (variants 1-3) or `family_2` (variants 4-10). |
| 4 | `source_pseudonym` | string \| null | yes | v2 | Opaque source label (`producer_a_v1`..`producer_a_v4`, `producer_b_v1`..`producer_b_v2`) or `null` when the input row had no `source` field (variant 2). The raw-to-pseudonym map is kept private and outside every public artefact. |
| 5 | `mint` | string (Solana base-58) | no | v1 | SPL token mint address (public, on-chain). |
| 6 | `symbol` | string | no | v1 | Token ticker as reported by the DEX aggregator at sample time. |
| 7 | `symbol_redacted` | bool | no | v2 | Always `false` in this release; reserved for future privacy review. |
| 8 | `sampleTs_utc_iso` | string (ISO-8601 UTC ms) \| null | rare | v2 | Post-rejection follow-up observation time, ISO string with millisecond precision, trailing `Z`. |
| 9 | `sampleTs_utc_ms` | int (epoch ms) \| null | rare | v2 | Same instant as `sampleTs_utc_iso`, in UTC epoch milliseconds. |
| 10 | `rejectTs_utc_iso` | string (ISO-8601 UTC ms) \| null | rare | v2 | Time of the original rejection event, ISO string. |
| 11 | `rejectTs_utc_ms` | int (epoch ms) \| null | rare | v2 | Same instant as `rejectTs_utc_iso`, in UTC epoch milliseconds. |
| 12 | `rejectReason` | string enum \| null | rare | v1 | Normalized filter name; one of eight named families (see enumeration). After canonicalization the `reason` alias from `family_2` variants 7/8/10 has been folded into this column, so no row carries a null `rejectReason` in the corrected corpus. |
| 13 | `priceUsd` | number \| null | yes | v1 | DEX-aggregator token price in USD at `sampleTs`. |
| 14 | `priceChange24h` | number \| null | yes | v1 | Trailing 24-hour price change (percent) at `sampleTs`. |
| 15 | `priceChange1h` | number \| null | yes | v1 | Trailing 1-hour price change (percent) at `sampleTs`. |
| 16 | `priceChange5m` | number \| null | yes | v1 | Trailing 5-minute price change (percent) at `sampleTs`. |
| 17 | `liquidity` | number \| null | yes | v1 | Pool liquidity in USD at `sampleTs`. `family_2` alias `liquidityUsd` is folded into this column. |
| 18 | `volume24h` | number \| null | yes | v1 | Trailing 24-hour trading volume in USD at `sampleTs`. `family_2` alias `volumeH24` is folded into this column. |
| 19 | `dexId` | string \| null | yes | v1 | DEX venue enum (see enumeration). `family_2` rows may carry `null`. |
| 20 | `pairAddress` | string (Solana base-58) \| null | yes | v1 | Trading-pair account address. `family_2` rows may carry `null`. |
| 21 | `classification` | string \| null | yes | v1 late | `family_2`-only column preserved verbatim. No `family_1` equivalent. |
| 22 | `alphaScoreSoFar` | number \| null | yes | v1 (part of window) | Strategy alpha score at rejection time. Emitted for part of the window only: populated on 40,705 rows (5.68%). |
| 23 | `regime` | object \| null | yes | v1 row 108,002 | BTC macro-regime context; see nested schema below. Absent from rows written before its introduction. |
| 24 | `ageMin_original` | int \| null | yes | v1 (family_1) | `ageMin` verbatim from the input row when present (family_1 only). Never re-derived, never overwritten. |
| 25 | `ageMin_recomputed_min` | int \| null | rare | v2 | Recomputed as `floor((sampleTs_utc_ms - rejectTs_utc_ms) / 60_000)`. Populated whenever both timestamps are present, in **both** families. |
| 26 | `ageMin_delta_min` | int \| null | yes | v2 | `ageMin_original - ageMin_recomputed_min` when both present, else `null`. Typically 0 or 1 (the v1 audit observed 86.20% exact match; the remainder is consistently one minute low). |
| 27 | `event_id` | string (16 hex chars) | no | v2 | `sha256("event\|" + mint + "\|" + rejectTs_utc_ms + "\|" + rejectReason)` truncated to 16 hex chars. Excludes `source_pseudonym` from the identity: multiple producers seeing the same rejection collapse into one event. |
| 28 | `sample_id` | string (16 hex chars) | no | v2 | `sha256("sample\|" + event_id + "\|" + sampleTs_utc_ms + "\|" + dexId_or_"null" + "\|" + pairAddress_or_"null")` truncated to 16 hex chars. Zero exact-duplicate clusters observed in the corrected corpus. |
| 29 | `normalization_status` | array of strings | no | v2 | Ordered closed-vocabulary tags describing which canonicalization rules fired for this row (aliases applied, epoch-ms converted, ISO parsed, source pseudonymized/absent, producer_family, schema_variant, ageMin_recomputed, sample_id_source). Full vocabulary in the canonicalization spec §14. |

Rows with schema_variant 4/5/6/7/8/9/10 (family_2, 8,356 rows total) carry
a `source` value in the input; their `source_pseudonym` is populated and their
`normalization_status` array carries `source_pseudonymized`. Only
schema_variant 2 (99,225 rows) has no `source` and a null `source_pseudonym`.

## Nested `regime` object schema

Present in every schema_variant 1 row (600,855 rows), from 24 April 2026 onward (first at `row_id_original` 0108002); absent from all other schema variants, including every family_2 row.

```json
{
  "btc_usd": 64149,
  "btc_change_24h_pct": -0.9864669016548487,
  "fear_greed_index": 25,
  "fear_greed_label": "Extreme Fear",
  "regime_label": "neutral",
  "regime_snapshot_ts": "2026-07-16T21:46:46.975Z"
}
```

| field | type | description |
|---|---|---|
| `btc_usd` | number | BTC/USD spot at snapshot time. |
| `btc_change_24h_pct` | number | Trailing 24-hour BTC/USD change (percent). |
| `fear_greed_index` | integer [0-100] | Crypto Fear-Greed Index at snapshot. |
| `fear_greed_label` | string enum | "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed". |
| `regime_label` | string enum | "neutral", "up", "down", "crash", "unknown" (the values observed in the corpus). |
| `regime_snapshot_ts` | ISO-8601 UTC string | When the regime snapshot was fetched. |

## `rejectReason` enumeration (corrected corpus)

Eight named filter families. **Corrected counts**, after canonicalization
folded the `reason` alias from `family_2` variants 7/8/10 into
`rejectReason`, no row carries a null `rejectReason`.

| filter name | rows | corpus share | note |
|---|---:|---:|---|
| `downtrend_24h` | 402,300 | 56.13% | Trailing 24h price change past a negative threshold. |
| `marketcap_out_of_range` | 153,248 | 21.38% | Market cap outside a configured band. |
| `multi_tf_fade` | 85,895 | 11.98% | Multi-timeframe momentum decay. |
| `timeSlot_not_strong` | 37,075 | 5.17% | UTC time-slot historically associated with poor entries. |
| `hour_blacklist` | 16,928 | 2.36% | Specific UTC hours identified as consistent losers. |
| `ultra_fast_reject_exit` | 11,747 | 1.64% | Fast-exit heuristic triggered immediately after entry signal. |
| `utc_hour_blocked` | 6,612 | 0.92% | Updated blocklist (introduced 2026-04-18). |
| `h6_sellers_dominating` | 2,957 | 0.41% | 6-hour seller-side volume dominates buy-side (introduced 2026-04-23). |
| **total** | **716,762** | **100.00%** | |

The v1 release published 348 rows (0.05%) as "null / unrecorded" because
the `reason` alias in schema variants 7/8/10 was not folded into
`rejectReason`. The corrected canonicalization folds it; the corresponding
totals are the small increments visible above.

## `dexId` enumeration (verbatim, unchanged from v1)

| dexId | rows | corpus share | lifecycle stage |
|---|---:|---:|---|
| `pumpswap` | 657,928 | 91.79% | Post-graduation open-market venue. |
| `meteora` | 19,580 | 2.73% | Post-graduation DLMM / dynamic vaults. |
| `raydium` | 17,628 | 2.46% | Post-graduation AMM. |
| `pumpfun` | 13,121 | 1.83% | Pre-graduation bonding curve. |
| `null` | 8,356 | 1.17% | Venue identifier absent from the input row (`family_2` schema). |
| `metadao` | 149 | 0.02% | Post-graduation, residual. |

The `family_2`-origin 8,356 null-`dexId` rows are exactly the 8,356 rows in
`producer_family = family_2`.

## `producer_family` distribution

| family | rows | corpus share | notes |
|---|---:|---:|---|
| `family_1` | 708,406 | 98.83% | Variants 1-3; canonical field names; ISO-8601 timestamps. |
| `family_2` | 8,356 | 1.17% | Variants 4-10; alias field names; epoch-ms timestamps. |

## `source_pseudonym` distribution (opaque labels)

The raw producer strings are held in a private mapping outside every
public artefact. The public labels have no ordering or semantic content
beyond "same label = same input source stream." The private mapping's
SHA-256 fingerprint is recorded in
`provenance/PRIVATE_MAP_FINGERPRINT.txt`.

| source_pseudonym | rows | corpus share |
|---|---:|---:|
| `producer_a_v1` | 256,768 | 35.82% |
| `producer_a_v4` | 179,606 | 25.06% |
| `producer_a_v2` | 102,745 | 14.33% |
| `null` (input row had no `source` field; schema_variant 2) | 99,225 | 13.84% |
| `producer_b_v1` | 39,062 | 5.45% |
| `producer_a_v3` | 27,916 | 3.89% |
| `producer_b_v2` | 11,440 | 1.60% |

## Missingness, what is and isn't nullable

- `mint`, `symbol`, `event_id`, `sample_id`, `row_id_original`,
  `schema_variant`, `producer_family`, `symbol_redacted`,
  `normalization_status`, **always present**.
- `rejectReason`, always present in the corrected corpus.
- `dexId`, `pairAddress`, null iff `producer_family = family_2` (8,356 rows).
- `source_pseudonym`, null iff `schema_variant = 2` (99,225 rows).
- `sampleTs_utc_iso`, `sampleTs_utc_ms`, `rejectTs_utc_iso`,
  `rejectTs_utc_ms`, `ageMin_recomputed_min`, `ageMin_delta_min`, rarely
  null in practice; nulled only when the underlying timestamp is absent
  from the input row. `family_2` `queriedAt` is always converted, so no
  `family_2` row carries a null `sampleTs_utc_ms` in the corrected corpus.
- `priceUsd`, `priceChange5m`, `priceChange1h`, `priceChange24h`,
  `liquidity`, `volume24h`, nullable per row; occur when the DEX
  aggregator returned incomplete data.
- `classification`, `alphaScoreSoFar`, `regime`, nullable per row (see
  the "first appears" column above for the introduction points).

## Row uniqueness, what the corrected event/sample model guarantees

- **Sample identity** (`sample_id`): every input row becomes exactly one
  canonical row with a unique `sample_id`. Zero exact-duplicate clusters
  observed in the corrected corpus.
- **Event identity** (`event_id`): 18,237 distinct events across 4,635
  distinct mints. Same event seen by two source streams collapses into
  one event (because `source_pseudonym` is not part of the event key).
- **Events with more than one venue value** (`alt_venue_report.csv`):
  4,278 events (23.5% of events, 72.4% of the sample rows) carry more than
  one `(dexId, pairAddress)` value during their post-rejection follow-up
  window. In 4,190 of them the only additional value is null, because the
  event also has rows in the legacy family_2 schema, which records no
  venue; 88 events are observed on two or more identified trading pools,
  78 of them on two or more exchanges (a token can cross venues after
  graduation). None of these is a duplicate.

## Streaming-friendly access pattern

```python
import gzip, json
with gzip.open("data/rejection_outcomes_corrected_v2.jsonl.gz", "rt") as f:
    for line in f:
        row = json.loads(line)
        # row is a 29-column dict per the schema above
```

For summary analytics over events instead of individual samples, prefer
`data/event_table.csv` (18,237 rows), one row per distinct event with
sample counts and first/last input line references.
