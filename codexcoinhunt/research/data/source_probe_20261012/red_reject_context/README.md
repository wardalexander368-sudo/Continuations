# RED-REJECT-2026-v2 (corrected release)

**Public benchmark corpus of algorithmic filter rejections with post-rejection follow-up samples, Solana pump.fun ecosystem, observed 2026-04-11 to 2026-07-16 (a 96-day window with one collection gap: no new rejection events from 3 June and no samples from 4 June until 24 June 2026).**

A companion data-descriptor manuscript documents the corpus in narrative form. Whether an author-posted manuscript preprint (for example on arXiv) is available at the time of a given reader's access is indicated by the presence of a preprint identifier in the Zenodo record's Related Identifiers block and in `CITATION.cff`. If no preprint identifier is listed there, no manuscript preprint has been posted at that time.

This release **supersedes RED-REJECT-2026-v1** (published 2026-07-16). See `CHANGELOG.md` for the corrections applied. The v1 raw source archive is unmodified and remains cited as the origin (v1 SHA-256 recorded in `provenance/normalization_summary.json`); v2 adds a canonical schema, producer-identity pseudonymization, an explicit event / sample model, and a full provenance ledger.

## Contents

| Path | Bytes | Rows | Description |
|---|---:|---:|---|
| `data/rejection_outcomes_corrected_v2.jsonl.gz` | 125,981,598 | 716,762 | Canonical corpus: one JSON object per line, 29-column schema. Deterministic; SHA-256 in `SHA256SUMS`. |
| `data/event_table.csv` | ~2.7 MB | 18,237 | One row per distinct rejection event. |
| `data/sample_table.csv` | ~146 MB | 716,762 | One row per canonical sample; unique `sample_id` per row. |
| `data/alt_venue_report.csv` | ~494 KB | 4,278 | Events with more than one `(dexId, pairAddress)` value, a null value included; 88 of them are observed on two or more identified trading pools. |
| `data/conflict_report.md` | — | — | Narrative reconciling to the pre-correction (v1 audit) numbers. |
| `data/duplicate_classification.csv` | — | 0 | Header only: zero duplicate/conflict clusters in the corrected corpus. |
| `schema/SCHEMA.md` | — | — | User-facing field-by-field schema. |
| `schema/CANONICALIZATION_SPEC.md` | — | — | Authoritative frozen spec (SHA-256 in `CANONICALIZATION_SPEC.sha256`). |
| `provenance/normalization_summary.json` | — | — | Machine-readable normalization summary (input/output SHA-256s, per-variant counts, quarantine reasons). |
| `provenance/event_model_summary.json` | — | — | Machine-readable event/sample/duplicate summary. |
| `provenance/corpus_distributions.json` | — | — | Rejection-reason, DEX, family, source_pseudonym distributions of the corrected corpus. |
| `provenance/corpus_distributions.md` | — | — | Human-readable version of the above. |
| `provenance/COMPLETENESS_AND_CENSORING.md` | — | — | Sampling-frame limitation and censoring characterization. |
| `provenance/PRIVATE_MAP_FINGERPRINT.txt` | — | — | SHA-256 fingerprint of the private producer-string→pseudonym map (the map itself is deliberately excluded from every public artefact). |
| `provenance/NORMALIZATION_FINGERPRINTS.sha256` | — | — | Reference hashes for the intermediate uncompressed JSONL / ledger / quarantine files. |
| `provenance/PHASE4_FINGERPRINTS.sha256` | — | — | Reference hashes for the event/sample/duplicate/conflict tables. |
| `provenance/PROVENANCE.md` | — | — | End-to-end provenance ledger from raw v1 gzip to this deposit. |
| `scripts/normalize.py` | — | — | Deterministic canonicalization script (public-safe; CLI-only). |
| `scripts/event_model.py` | — | — | Deterministic event/sample/duplicate table builder. |
| `scripts/build_release.py` | — | — | Deterministic end-to-end build script. |
| `tests/synthetic_raw_input.jsonl` | — | — | Synthetic raw-input fixture (zero real private identity) exercising all schema variants, alias combinations, quarantine, and duplicate paths. |
| `tests/synthetic_pseudonym_map.json` | — | — | Synthetic pseudonym map paired with the synthetic fixture. |
| `tests/expected_normalized_output.jsonl` | — | — | Expected canonical rows and event/sample identifiers for the synthetic fixture. |
| `tests/expected_quarantine.jsonl` | — | — | Expected quarantine rows for the synthetic fixture. |
| `tests/run_synthetic_reproduction.py` | — | — | Runnable end-to-end synthetic-pipeline test; exercises alias folding, event/sample identity, quarantine, and the missing-map failure mode. |
| `SHA256SUMS` | — | — | Integrity manifest, verifiable with `sha256sum -c SHA256SUMS` from the archive root. |
| `environment.txt` | — | — | Python/library versions used to produce this release. |
| `LICENSE` | — | — | CC-BY-4.0 license text. |
| `CITATION.cff` | — | — | Citation File Format record. |
| `CHANGELOG.md` | — | — | Change history from v1 to v2.3. |

## Corpus summary (verified against the deposited data)

| Statistic | Value |
|---|---|
| Total canonical sample rows | 716,762 |
| Distinct rejection events (event_id) | 18,237 |
| Distinct mints | 4,635 |
| Distinct sample_ids | 716,762 (every row is unique) |
| Observation window (`sampleTs` UTC) | 2026-04-11T20:26:53.379Z to 2026-07-16T21:57:03.283Z (96.06 days) |
| Collection gap (no samples) | 2026-06-04T06:32Z to 2026-06-24T16:38Z (about 20.4 days); sampling coverage excluding the gap about 75.6 days |
| Rows in family_1 (variants 1-3, canonical schema) | 708,406 (98.83%) |
| Rows in family_2 (variants 4-10, alias schema) | 8,356 (1.17%) |
| Rows with a source pseudonym | 617,537 (86.16%), six opaque labels |
| Rows without a `source` field (schema_variant 2) | 99,225 (13.84%) |
| Named rejection filter families | 8 (see `schema/SCHEMA.md`) |
| Rows with null `rejectReason` | 0 (v1 had 348 due to unfolded `reason` alias) |
| Exact-duplicate `sample_id` clusters | 0 |
| Conflicting-value `sample_id` clusters | 0 |
| Events with more than one `(dexId, pairAddress)` value | 4,278 (23.5% of events); in 4,190 of them the only additional value is null, because legacy family_2 rows carry no venue |
| Events observed on two or more identified trading pools | 88 (78 on two or more exchanges) |

The v1 gzip is verified by SHA-256 (`17e31658ffd9ed7adcb08d7081c3f7718428e462e10704b1d8d5bf0ad3cd07d9`) before every normalization run; no source file is modified in place. See `scripts/normalize.py`.

## Corrections in this v2 release

The v2 release adds the following, without changing the semantics of the underlying observations:

1. **Canonical 29-column schema** applied deterministically to every row. Ten input signature variants collapse into two producer families (documented as `family_1` and `family_2`); no row is silently dropped, no row is silently collapsed. Every input line → exactly one canonical row → exactly one row in the transformation ledger.
2. **Alias unification**: `queriedAt`→`sampleTs`, `rejectionTimestamp`→`rejectTs`, `reason`→`rejectReason`, `liquidityUsd`→`liquidity`, `volumeH24`→`volume24h`. After folding, no row carries a null `rejectReason` (v1 reported 348 rows as "null / unrecorded" because the `reason` alias in schema_variants 7/8/10 was not folded).
3. **Producer-identity pseudonymization** of the `source` string: the six raw producer labels are replaced by opaque `producer_a_v1..v4` and `producer_b_v1..v2` pseudonyms. The private raw-to-pseudonym map is kept outside every public artefact; only its SHA-256 fingerprint is published (see `provenance/PRIVATE_MAP_FINGERPRINT.txt`).
4. **Explicit event / sample model** (`event_table.csv`, `sample_table.csv`, `duplicate_classification.csv`, `alt_venue_report.csv`, `conflict_report.md`). Event identity is `(mint, rejectTs_utc_ms, rejectReason)` hashed to 16 hex; sample identity is `(event_id, sampleTs_utc_ms, dexId, pairAddress)` hashed to 16 hex. The corrected model shows zero duplicate clusters after canonicalization; the v1 audit's headline of 1,286 "collision clusters" was entirely a downstream symptom of the family_2 missing-sampleTs schema failure.
5. **Corrected filter-count table** in `schema/SCHEMA.md` (differences from v1 are 156+42+12+3+50+9+75+1 rows across the eight named families; sum = 348, exactly the previously-null-`rejectReason` bucket).
6. **Explicit completeness / censoring statement**: see `provenance/COMPLETENESS_AND_CENSORING.md`. The corpus is the sampling frame of *observed* rejection events with at least one follow-up observation; it is not, and does not claim to be, a complete census of every filter firing on the underlying fleet.
7. **Number provenance**: the dataset's main statistics map to rows in `NUMBER_PROVENANCE.csv` (included at this pack root), each with the source file, computation, and reproduction command.

## Reproducibility: three levels

The deposit supports three distinct classes of reproduction. Each class has its own inputs, outputs, and independence from external artefacts.

**Level 1, Release verification (fully public).** Verify that the files a reader downloaded match the deposit as published. Command: `sha256sum -c SHA256SUMS` from the extracted archive root. Requires only the deposited files. No external inputs, no private map. This is the reproduction step every reader should run before consuming the data.

**Level 2, Analytical reproduction (fully public).** Re-run any analytical script (`scripts/event_model.py`, the figure and table builders, per-filter statistics, missingness computation) against the deposited canonical corpus (`data/rejection_outcomes_corrected_v2.jsonl.gz`). Outputs match the deposited derived tables (`event_table.csv`, `sample_table.csv`, `alt_venue_report.csv`, `duplicate_classification.csv`) and the numbers cited in the companion manuscript to byte-level fidelity for the CSVs and figure-source CSVs. Requires only the deposited files. No external inputs, no private map. This is the reproduction path for third-party researchers who want to build on the corpus.

**Level 3, Corpus re-derivation from raw source (requires a restricted producer-pseudonym mapping).** Re-derive the canonical JSONL from the v1 source archive `RED-REJECT-2026-v1.zip` (Zenodo record `10.5281/zenodo.21402477`, gzip SHA-256 `17e31658ffd9ed7adcb08d7081c3f7718428e462e10704b1d8d5bf0ad3cd07d9`). This path requires a private file `producer_pseudonym_map.json` that is deliberately not publicly distributed for identity-separation reasons (see `provenance/PRIVATE_MAP_FINGERPRINT.txt` for its SHA-256 fingerprint and `Ethics and privacy` below for the rationale). Public users cannot reproduce Level 3 byte-for-byte without either (a) obtaining the private map through direct contact with the author under a research agreement, or (b) enumerating the six raw producer labels from any log they own and assigning `producer_a_v1..vN` / `producer_b_v1..vM` per the canonicalization spec §4 (the resulting output will match on structure and counts, and will match on the `source_pseudonym` column only if the enumeration order matches the author's private map). Level 3 exists for auditability of the transformation ledger; the public package supports byte-level release verification (Level 1) and analytical reproduction from the deposited canonical corpus (Level 2) independently of Level 3.

**Known difference (disclosed in v2.3).** Every row of the deposited canonical file carries its `producer_family_1` or `producer_family_2` tag twice in `normalization_status`, whereas the deposited `scripts/normalize.py` appends it once. A Level 3 re-derivation with the deposited script therefore does not reproduce the canonical file byte-for-byte unless the tag is appended twice. Levels 1 and 2 are unaffected.

**Publicly testable pipeline logic (synthetic).** Under `tests/` the deposit ships a synthetic fixture (`synthetic_raw_input.jsonl` + `synthetic_pseudonym_map.json`) plus a runnable script (`run_synthetic_reproduction.py`) that exercises the alias-folding, event-identity, sample-identity, quarantine, and duplicate-classification behaviour of the normalization pipeline end-to-end on synthetic data containing zero real private identity. This synthetic path validates the pipeline logic without requiring the private map; it does not certify byte-equivalence against the real corpus, which is what Level 3 is for.

**Consumers who only need the corrected corpus** can use `data/rejection_outcomes_corrected_v2.jsonl.gz` directly (Level 1 verification recommended before analysis). The section below is for Level 3 full byte-for-byte re-derivation.

```bash
# 1. Canonicalize.
python scripts/normalize.py \
  --source-zip /path/to/RED-REJECT-2026-v1.zip \
  --gz-name-in-zip RED-REJECT-2026-v1/data/rejection_outcomes_full_v1.jsonl.gz \
  --private-map /path/to/producer_pseudonym_map.json \
  --out-dir /tmp/red_reject_out

# 2. Build event/sample/duplicate tables.
python scripts/event_model.py \
  --normalized /tmp/red_reject_out/normalized_public.jsonl \
  --out-dir /tmp/red_reject_out

# 3. Gzip the canonical JSONL deterministically (mtime=0, level 9).
python -c "import gzip,sys
with open(sys.argv[1],'rb') as fi, open(sys.argv[2],'wb') as raw:
    gz = gzip.GzipFile(filename='rejection_outcomes_corrected_v2.jsonl', mode='wb', fileobj=raw, compresslevel=9, mtime=0)
    while True:
        b = fi.read(1<<20)
        if not b: break
        gz.write(b)
    gz.close()" /tmp/red_reject_out/normalized_public.jsonl \
     /tmp/red_reject_out/rejection_outcomes_corrected_v2.jsonl.gz

# 4. Verify.
sha256sum -c SHA256SUMS
```

The `--private-map` file is deliberately not publicly distributed. It is not required for Level 1 (release verification) or Level 2 (analytical reproduction on the deposited canonical corpus). It is required only for Level 3 byte-for-byte re-derivation of the `source_pseudonym` column from the v1 source. Consumers who need to re-derive that column without the private map can enumerate the six raw producer labels from any log they own, sort within each family alphabetically, and assign `producer_a_v1..vN` / `producer_b_v1..vM` per canonicalization spec §4; the output will match on structure and counts, and will match byte-for-byte on `source_pseudonym` only if their enumeration order matches the author's private map.

## Publicly testable pipeline (synthetic)

The full byte-for-byte reproduction above requires the v1 source archive and the private producer-pseudonym map. Public consumers who do not hold the private map can still test the pipeline logic end-to-end using the synthetic fixture bundled at `tests/`:

- `tests/synthetic_raw_input.jsonl`, 15 hand-crafted rows exercising every schema variant (1..10), every alias fold, every producer-pseudonym label, an exact-duplicate row, two events under a single mint, a row with a missing rejectReason alias, a row with both timestamps absent, and a row with an unknown raw source label.
- `tests/synthetic_pseudonym_map.json`, public synthetic map covering the six synthetic raw source strings.
- `tests/expected_normalized_output.jsonl`, expected canonical rows produced by `scripts/normalize.py::normalize_row` when applied to the synthetic input.
- `tests/expected_quarantine.jsonl`, expected quarantine records (three rows).
- `tests/run_synthetic_reproduction.py`, self-contained Python 3.11 test harness. Loads the fixture, runs the deposited `scripts/normalize.py` when present (byte-parity certification), also runs a bundled logic-equivalent reference implementation, verifies failure modes, and reports PASS / FAIL per assertion. Exits 0 on all-pass.

```bash
python tests/run_synthetic_reproduction.py
```

All identifiers in the fixture use the `synthetic_` prefix so no real Solana address, real producer name, or real rejection timestamp is embedded. This synthetic path validates the pipeline logic only; it does not certify byte-equivalence against the deposited 716,762-row corpus (that certification requires the private map and is documented separately in `provenance/PRIVATE_MAP_FINGERPRINT.txt` and `provenance/NORMALIZATION_FINGERPRINTS.sha256`).

## Provenance

Data were collected by a purpose-built follow-up-tracking process (a Node.js daemon under a process manager) running on a dedicated research server between 2026-04-11 and 2026-07-16. The window contains one collection gap: no samples were recorded between 2026-06-04T06:32Z and 2026-06-24T16:38Z (about 20.4 days), and no rejection events are present between 2026-06-03T06:35Z and 2026-06-24T16:34Z. The tracker observed the filter-rejection event stream from the paper-trading fleet during this window and re-sampled each observed rejected token's live market state at scheduled intervals until observability dropped. The deposited corpus is the sampling frame of rejection events observed by the tracker with at least one post-rejection follow-up sample; it is not a census of every filter firing on the underlying fleet during the window (see `provenance/COMPLETENESS_AND_CENSORING.md`). Data sources are all public and free-tier: Helius WebSocket for on-chain events, DEX Screener REST for price/liquidity/volume aggregates, CoinGecko for BTC/USD spot, Alternative.me for the Fear-Greed Index.

No paid data. No authenticated-endpoint scraping. No live-money trades executed against tokens observed in this dataset, the fleet is a paper-trading system; rejections are simulated. All identifiers in the corpus are public Solana base-58 addresses (SPL token mints and DEX pair addresses); no PII.

See `provenance/PROVENANCE.md` for the full ledger from v1 raw gzip → v2 canonical corpus.

## Ethics and privacy

- All identifiers are public Solana base-58 addresses. No PII.
- No wallet-holder identities inferred, attempted, or stored.
- No trading was performed against tokens observed in this dataset by the author's live-money strategies. Rejections are from paper-trading (simulated) execution; no market-participant behaviour was influenced by the rejections recorded here.
- Data collection used only public feeds; no scraping of authenticated content.
- The `source` field in the v1 gzip carried operational producer labels; those labels are pseudonymized here to opaque `producer_a_v*` / `producer_b_v*` strings so that the deposit cannot be used to attribute operations to specific software components or people.

## Related work

Companion papers by the same author that use this corpus (or windowed subsets of it):

- Post-Rejection Follow-up Sampling methodology (arXiv 2606.08228, SSRN 6607301).
- Rejection-outcome-classified precision auditing (arXiv 2607.02830, SSRN 6638259).
- RED-2400 labelled 2,400-token benchmark subset (arXiv 2605.12151, SSRN 6702198, Zenodo 10.5281/zenodo.19989074).
- Filter-ablation empirical application on a 3,125-token subset.

Related datasets:

- RED-2400 (labelled subset): Zenodo `10.5281/zenodo.19989074`.
- RED-COHORT-2026-v1 (early-buyer co-occurrence cohort analysis record): Zenodo `10.5281/zenodo.20978741`.
- RED-PUMP-2026-v1 (pump.fun launch corpus): Zenodo `10.5281/zenodo.20633486`.
- LIFECYCLE-SEPARATION-2026-v1 (windowed subsets of this corpus): Zenodo `10.5281/zenodo.21399919` (version v1).

## Citation

If you use this dataset, please cite:

> Kamat, A. U. (2026). RED-REJECT-2026-v2 (corrected release): A 96-Day Public Corpus of Algorithmic Filter Rejections with Post-Rejection Follow-up Samples on the Solana pump.fun Ecosystem [Data set]. Zenodo. Concept DOI: 10.5281/zenodo.21402476.

Machine-readable citation in `CITATION.cff`.

## License

CC-BY-4.0. Attribution required. See `LICENSE`.

## Author

Arati Uday Kamat
Independent Researcher
ORCID: 0009-0000-4781-312X
Email: arati.kamat@ieee.org
