# CANONICALIZATION_SPEC.md, RED-REJECT-2026 corrected corpus

**Status:** FROZEN, do not amend without a new dated spec version and an updated frozen SHA-256.
**Freeze date:** 2026-08-21 (v1 audit reconciled 2026-08-21).
**Applies to:** the 716,762-valid-row `rejection_outcomes_full_v1.jsonl.gz` inside
`RED-REJECT-2026-v1.zip` (outer ZIP SHA-256 `1aeb0b96…328b9ca0`; inner gzip SHA-256
`17e31658…d3cd07d9`).
**Rule:** written before corrected event/sample tables are produced. The event-model outputs
must be reproducible strictly from this spec plus the frozen sources.

**Public-safe:** this document deliberately contains no raw producer-label
strings. Where the pseudonymization rule requires enumerating raw producer
labels, they live in a separate internal file (see Section 4) that is
excluded from every public release.

---

## 1. Scope and non-goals

- Applies to the ten observed field-set signatures documented in
  Section 2 and the two producer families documented in Section 3.
- The spec is deterministic: every rule maps a source row to exactly one
  canonical row (or one quarantined row) with a fixed set of fields.
- The spec does NOT touch analytical decisions (rejection-window definitions,
  post-rejection outcome labels, censoring corrections). Those are documented
  separately, including in `provenance/COMPLETENESS_AND_CENSORING.md`.
- The spec does NOT delete or collapse any input row. Every input line
  produces exactly one ledger row and either one normalized row or one
  quarantine row.

---

## 2. Schema-variant labelling (`schema_variant`)

Taken verbatim from the v1 audit's field-set inventory and re-labelled as `variant_1`
… `variant_10` in signature-index order. The canonical row carries the raw
integer.

| variant | rows | fields | producer_family | notes |
|---:|---:|---:|:---:|---|
| 1 | 600,855 | 17 | family_1 | full primary schema + `regime` + `alphaScoreSoFar` + `source` |
| 2 |  99,225 | 14 | family_1 | early primary schema, no `source`/`alphaScoreSoFar`/`regime` |
| 3 |   8,326 | 16 | family_1 | primary + `source`/`alphaScoreSoFar`, no `regime` |
| 4 |   6,373 | 11 | family_2 | alias schema, `rejectReason`+`rejectTs` |
| 5 |   1,300 |  7 | family_2 | alias schema, no price fields |
| 6 |     283 | 12 | family_2 | variant 4 + `alphaScoreSoFar` |
| 7 |     216 | 11 | family_2 | alias schema using `reason`+`rejectionTimestamp` |
| 8 |     128 | 12 | family_2 | variant 7 + `alphaScoreSoFar` |
| 9 |      52 |  8 | family_2 | `rejectReason` schema, no price/liq/vol fields |
|10 |       4 |  7 | family_2 | oldest alias schema (`reason`+`rejectionTimestamp`, no price) |

## 3. Producer-family labelling (`producer_family`)

Two labels only, disjoint by variant:

- `family_1`, primary tracker producer. Covers variants 1–3 and 708,406 rows (98.83 %). ISO-8601 timestamps, canonical field names.
- `family_2`, legacy/alternate tracker. Covers variants 4–10 and 8,356 rows (1.17 %). Epoch-millisecond timestamps, aliased field names.

`producer_family` is derived from `schema_variant`. It is **not** the raw
`source` string; that string is handled by Section 4.

## 4. `source` field, producer-identity pseudonymization (`source_pseudonym`)

**Design decision:** replace the public `source` string with a stable
opaque pseudonym. Preserve source-level clustering. Do not publish, commit,
archive, or checksum the raw-to-opaque mapping with the release.

Rules:

1. The public output field is named `source_pseudonym` (string).
2. `source_pseudonym` is populated by exact lookup in the private mapping
   (SHA-256 of the private mapping file recorded in the ledger).
3. Rows with no `source` field (variant 2) get `source_pseudonym = null`.
   The `normalization_status` array records `source_absent`.
4. If a `source` value is not in the mapping (should not happen for this
   corpus; enforced by pre-flight check), the row is quarantined with reason
   `unknown_source_value`.
5. The pseudonym namespace is `producer_a_v*` (raw family A) and
   `producer_b_v*` (raw family B). Version suffixes are sequential integers
   assigned by the canonical sort order of the raw strings within each
   family, so that gaps in raw version numbers do not leak. Six pseudonyms
   are populated in this corpus: `producer_a_v1..v4` and
   `producer_b_v1..v2`.
6. The raw `source` string never appears in any public artefact
   (normalized JSONL, ledger, event/sample tables, reports, manifests,
   scripts, or logs). Enforcement: Section 13 grep.
7. The concrete raw-string list, static grep patterns, and the private
   raw-to-pseudonym map are enumerated in internal-only materials kept
   outside the public candidate bundle, together with the private map file
   (see Section 17).

## 5. Canonical event and sample keys

**Event identity:** a rejection event is `(mint, rejectTs_utc_ms,
rejectReason_normalized)`, the exact tuple used to enumerate observed
events in `data/event_table.csv`.

- `event_id = sha256("event|" + mint + "|" + rejectTs_utc_ms + "|" +
  rejectReason_normalized)` truncated to 16 hex chars.
- `source_pseudonym` is **not** part of the event identity. Multiple
  producers may re-observe the same rejection; the collision means "same
  event seen by two source streams," not "different event."
- If the derived tuple would repeat with different content, both members
  are preserved with the same `event_id` and flagged via the
  duplicate/conflict tables of the event model.

**Sample identity:** a follow-up observation is
`(event_id, sampleTs_utc_ms, dexId_normalized, pairAddress_normalized)`.

- `sample_id = sha256("sample|" + event_id + "|" + sampleTs_utc_ms + "|" +
  dexId_or_"null" + "|" + pairAddress_or_"null")` truncated to 16 hex chars.
- `dexId` and `pairAddress` are absent for family_2. Sample keys built from
  family_2 rows carry the literal strings `"null"` in those two slots so
  they never collide with family_1 samples of the same event at the same
  instant.
- Rows with null `sampleTs_utc_ms` still receive a sample_id but the
  `sample_id_source` flag is set to `"null_sampleTs_synthetic"` and the row
  is flagged for duplicate/conflict classification, not for
  analysis. Note: after canonicalization no family_2 row has null
  `sampleTs_utc_ms` (`queriedAt` is always converted); this branch exists
  only for defensive robustness.

## 6. Timestamp normalization

Two output columns per timestamp: an ISO-8601 UTC string with millisecond
precision, and an integer epoch-milliseconds field. Both are always
consistent.

- `sampleTs_utc_iso` (str | null), `sampleTs_utc_ms` (int | null)
- `rejectTs_utc_iso` (str | null), `rejectTs_utc_ms` (int | null)

Conversion:

| source | producer | conversion |
|---|---|---|
| `sampleTs` ISO string | family_1 | parsed with `datetime.fromisoformat` after replacing trailing `Z`; converted to UTC epoch ms. |
| `queriedAt` integer epoch ms | family_2 | copied to `sampleTs_utc_ms`; ISO string derived from `datetime.fromtimestamp(ms/1000, tz=UTC).isoformat(timespec='milliseconds')`. |
| `rejectTs` ISO string | family_1 and family_2 variants 4/5/6/9 | parsed to UTC ms. |
| `rejectionTimestamp` ISO string | family_2 variants 7/8/10 | parsed to UTC ms; sets `alias_applied: rejectionTimestamp→rejectTs`. |

Parsing rules:

1. Trailing `Z` is treated as `+00:00`. Rows without timezone information
   would be quarantined, none observed in this corpus.
2. Millisecond precision is preserved; sub-millisecond digits are truncated
   (not rounded) to avoid non-deterministic tie-breaks.
3. If a timestamp string fails to parse, the row is quarantined with reason
   `timestamp_parse_error`.

## 7. Alias unification

Alias fields present in family_2 are copied into the canonical family_1
name. Both the raw alias value and the canonical field are preserved in
the ledger.

| raw alias | canonical | conversion | scope |
|---|---|---|---|
| `queriedAt` (int ms) | `sampleTs_utc_ms` + `sampleTs_utc_iso` | int → ISO | family_2 |
| `rejectionTimestamp` (ISO str) | `rejectTs_utc_iso` + `rejectTs_utc_ms` | ISO parse | family_2 variants 7/8/10 |
| `reason` (str) | `rejectReason` | verbatim copy; enum subset validated | family_2 variants 7/8/10 |
| `liquidityUsd` (num) | `liquidity` | verbatim copy | family_2 variants 4/6/7/8 |
| `volumeH24` (num) | `volume24h` | verbatim copy | family_2 variants 4/6/7/8 |

`classification` (family_2 only, exclusive) is preserved verbatim as a
canonical column. It has no family_1 equivalent.

## 8. `ageMin` semantics

- `ageMin_original` (int | null): copied verbatim from the input if present
  (family_1 only). Never re-derived, never overwritten.
- `ageMin_recomputed_min` (int | null): floor((sampleTs_utc_ms −
  rejectTs_utc_ms) / 60_000). Populated whenever both timestamps are
  present, in **both** families.
- `ageMin_delta_min` (int | null): `ageMin_original − ageMin_recomputed_min`
  where both are present, else null. The v1 audit showed 86.20 %
  exact match with the remainder consistently one minute low, so this delta
  usually equals 0 or 1.
- Analysts must use `ageMin_recomputed_min` for cross-producer work.
  `ageMin_original` is retained only for reproducibility of the original
  release's numbers.

## 9. Missing / null handling

- JSON `null` and "field absent" are distinct. The ledger and downstream
  reports may use `""` to denote "field absent" and JSON `null` for actual
  nulls; canonical rows use JSON `null` for missing values.
- Numeric fields keep their raw JSON type (int vs float), no silent int→float
  coercion.
- Any row that fails at least one canonicalization step is quarantined with
  a reason string. No row is silently dropped.

## 10. Exact-row duplicate handling

- No collapsing during canonicalization. Every input line gets its own canonical row.
- The event model classifies duplicates via the sample_id / event_id keys.
- Note from the v1 audit: the historical "extra rows" headline
  was 100 % rows with null sampleTs, all family_2 rows. After
  canonicalization the null-sampleTs branch is empty, so the historical
  headline number does not recur in the corrected model.

## 11. Alias-vs-canonical conflict handling

Observed empirically: family_1 rows carry canonical fields only; family_2
rows carry aliases only. The families are mutually exclusive per row. If a
row is ever observed to carry both, the rule is:

1. Canonical value wins.
2. `normalization_status` gains `alias_and_canonical_present`.
3. Both values are preserved in the ledger for manual verification.

## 12. Redaction policy

- `mint` (Solana mint public key): preserved verbatim. On-chain public
  identifier. No redaction.
- `pairAddress` (Solana pair public key): preserved verbatim. On-chain
  public identifier. No redaction.
- `symbol` (user-generated meme ticker): preserved verbatim by default;
  the canonical row also carries `symbol_redacted` (bool, default `false`).
  A later privacy review may switch selected symbols to redacted with a
  reason code. This spec's default is "publish verbatim", the release is a
  public dataset that already ships with symbol strings.
- `source` (raw producer label): NEVER preserved in any public artefact.
  Replaced by `source_pseudonym` per Section 4.

## 13. Producer-identity grep policy (pre-publication gate)

Case-insensitive grep run over every file in the public candidate bundle
(and all canonicalization and event-model outputs) before any release. The concrete
pattern list is maintained in internal-only materials (excluded from every
public release) and expanded at runtime with the
raw-source values loaded from the private map (Section 17).

Any match → the pre-publication scan gate FAILS. Report counts only, never
the offending string. The release is withheld.

## 14. `normalization_status` (array on every canonical row)

Ordered list of applied tags, drawn from a closed vocabulary:

- `alias_applied:<raw>→<canonical>` (one per alias)
- `epoch_ms_converted`
- `iso_parsed`
- `source_pseudonymized`
- `source_absent`
- `producer_family_1` / `producer_family_2`
- `schema_variant_<n>`
- `ageMin_recomputed`
- `alias_and_canonical_present` (only if observed)
- `sample_id_source:normal` / `sample_id_source:null_sampleTs_synthetic`

## 15. Canonical output row schema

`normalized_public.jsonl` rows carry the fields below and no others:

```
row_id_original          str    zero-padded input line number
schema_variant           int    1..10
producer_family          str    family_1 | family_2
source_pseudonym         str|null
mint                     str
symbol                   str
symbol_redacted          bool
sampleTs_utc_iso         str|null
sampleTs_utc_ms          int|null
rejectTs_utc_iso         str|null
rejectTs_utc_ms          int|null
rejectReason             str|null    normalized (aliases folded)
priceUsd                 number|null
priceChange24h           number|null
priceChange1h            number|null
priceChange5m            number|null
liquidity                number|null
volume24h                number|null
dexId                    str|null
pairAddress              str|null
classification           str|null    family_2 only
alphaScoreSoFar          number|null
regime                   object|null
ageMin_original          int|null
ageMin_recomputed_min    int|null
ageMin_delta_min         int|null
event_id                 str
sample_id                str
normalization_status     array<str>
```

## 16. Ledger and quarantine

- `row_transformation_ledger.csv`, one row per input line. Columns:
  `line_no`, `schema_variant`, `producer_family`, `source_raw_sha256`
  (SHA-256 of raw source string so raw string is never leaked, `null` when
  absent), `source_pseudonym`, `raw_ts_field`, `canonical_sampleTs_utc_ms`,
  `raw_rejectTs_field`, `canonical_rejectTs_utc_ms`, `alias_flags`,
  `quarantined` (bool), `quarantine_reason`, `event_id`, `sample_id`.
- Quarantine reasons closed vocabulary: `timestamp_parse_error`,
  `unknown_source_value`, `mint_absent`, `both_timestamps_absent`,
  `unknown_signature`, `json_parse_error`.

## 17. Determinism, reproducibility, private map

- The normalizer streams the source gzip line by line. Memory footprint
  independent of corpus size.
- Output row order equals input row order.
- SHA-256 of the normalized JSONL is written next to it. Two independent
  runs must produce byte-identical files.
- The private pseudonym map is loaded via absolute path and its SHA-256 is
  verified against a fingerprint file (`PRIVATE_MAP_FINGERPRINT.txt`) at
  every run. The fingerprint is safe to publish; the map itself is not.
  The map file itself lives outside every git repo and every public
  release tree by design.

---

**Frozen deliverable:** this file. Its SHA-256 is stored alongside it as
`CANONICALIZATION_SPEC.sha256`. Any change to a rule requires bumping the
file name to a new date and re-running canonicalization and the event model;
wording-only changes are recorded in `CHANGELOG.md`.
