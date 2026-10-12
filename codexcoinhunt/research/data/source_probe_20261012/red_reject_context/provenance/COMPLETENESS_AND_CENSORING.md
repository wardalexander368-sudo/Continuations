# COMPLETENESS AND CENSORING, RED-REJECT-2026-v2

## Bottom line

RED-REJECT-2026-v2 is the sampling frame of rejection events **observed by the follow-up tracker with at least one post-rejection follow-up sample**. It is **not** a census of every rejection that fired on the underlying paper-trading fleet during the 96-day window. All estimands defined against this corpus apply to the observed-events universe only; population-level rejection-rate or per-filter frequency claims are outside the corpus's inferential reach.

This document redefines the estimand for downstream users and characterizes the censoring the corpus is subject to.

## 1. Why the corpus is not a complete rejection registry

**No independent registry was available for this deposit.** The complete list of rejection events fired by the fleet is not preserved in a separate observability sink that the deposit could be cross-checked against:

- The upstream `event bus` that the tracker consumes was not itself archived at row-level fidelity for the full window. Aggregate process-manager restart logs exist but do not enumerate individual rejection events.
- The trading fleet's internal state machine emits telemetry that is consumed live by the tracker and downstream analytics but is not written to durable storage in a form that could serve as a rejection registry.
- The tracker's own append-only JSONL is the primary artefact and the only durable record of individual rejection events. Any rejection that fired but did not produce at least one follow-up sample is invisible to this corpus.

**Consequence.** The corpus therefore captures the *intersection* of (rejection fired) ∩ (tracker successfully wrote at least one follow-up sample). The absolute size of the difference between (rejections fired) and (rejections observed) cannot be measured from this deposit alone. Downstream researchers who need that difference must instrument the underlying fleet independently.

## 2. Estimand, redefined

**Universe of inference:** the set of 18,237 rejection events observed by the follow-up tracker between `2026-04-11T20:26:53.379Z` and `2026-07-16T21:57:03.283Z`, each with ≥1 post-rejection follow-up sample. The window contains one collection gap (Section 4a).

**In-scope estimands:**
- Per-filter distribution over the observed sampling frame (see `SCHEMA.md` and `corpus_distributions.json`).
- Per-DEX distribution over the observed sampling frame.
- Per-event follow-up-sample count and time-since-rejection distributions.
- Venue coverage per event (4,278 events carry more than one `(dexId, pairAddress)` value, a null value included; 88 are observed on two or more identified trading pools).
- Any counterfactual analysis whose inference is explicitly framed as "for events the tracker observed" and does not implicitly project onto events the tracker did not observe.

**Out-of-scope estimands:**
- Absolute filter firing rates on the fleet.
- Fleet-level "rejection rate per candidate token."
- Any claim of the form "the fleet rejects N% of tokens", the denominator "tokens the fleet evaluated" is not observed here.
- Any claim requiring the corpus to be a random sample of the underlying rejection population.
- Population-completeness claims of any form.

## 3. Left censoring

**Time.** No samples are observed before `2026-04-11T20:26:53.379Z` (first `sampleTs`). 31 events whose rejection fired up to about 22.5 hours earlier (earliest `rejectTs` `2026-04-10T21:54:14.836Z`) are present because their follow-up sampling extended into the window. Rejection events that fired before the window and have no follow-up sample inside it are not represented in the corpus; the corpus does not attempt to backfill them.

**Filters.** Two named filters were introduced after the start of the window:
- `utc_hour_blocked`, first appears on 2026-04-18.
- `h6_sellers_dominating`, first appears on 2026-04-23.

Aggregate counts for these two filters therefore reflect only the sub-window during which they were active. Any per-filter comparison across the full 96-day window must segment by first-appearance date. See `SCHEMA.md` §rejectReason.

**Schema.** Three fields are present only in some rows:
- `source`, present in schema_variants 1 (600,855 rows) and 3 (8,326 rows) and in every family_2 row (8,356 rows), 617,537 rows in total; absent only from variant 2 (99,225 rows).
- `alphaScoreSoFar`, populated on 40,705 rows (5.68%): 39,721 rows of schema_variant 1, 521 of variant 3, and every row of variants 6 (283), 8 (128) and 9 (52). The trading system emitted it only for part of the window.
- `regime` object, present in every schema_variant 1 row (600,855 rows), first on 2026-04-24 (`row_id_original` 0108002); absent from all earlier rows and from every family_2 row.

## 4. Right censoring

**Time.** Last observed `sampleTs` is `2026-07-16T21:57:03.283Z`. Any post-rejection dynamics beyond that time are not observed. Tokens whose observable market state persisted past 2026-07-16 have right-truncated follow-up windows here.

**Observability drop-out.** For each observed rejection event, the tracker samples until the token's market state falls below observability thresholds (DEX aggregator ceases to return liveness signals). The last-observed sample per event is therefore not necessarily "the token's end state"; it is "the last state observable to a public DEX aggregator." See `sample_table.csv` for per-sample `sampleTs`.

## 4a. Collection gap

No samples were recorded between `2026-06-04T06:32Z` and `2026-06-24T16:38Z` (about 20.4 days), and no rejection events are present between `2026-06-03T06:35Z` and `2026-06-24T16:34Z`. Allowing for the gap, the 96.06-day window contains about 75.6 days of sampling coverage. No rejection that fired between `2026-06-03T06:35Z` and `2026-06-24T16:34Z` is represented. Analyses over calendar time, including monthly counts, must exclude or explicitly model the gap.

## 5. Interval censoring, per-event sampling gaps

The tracker's sampling schedule concentrates early-post-rejection observations (typically every few minutes for the first hour, tapering to hourly and then to less frequent later samples up to ~24 hours after rejection). Gaps within a single event's follow-up trajectory are variable and observable per event via `sample_table.csv`. Users who require dense sampling should filter to events with sample_count above a threshold; users who require sparse-sampling-tolerant analysis (e.g., Kaplan-Meier survival with interval censoring) can use the sample-table timestamps directly.

## 6. Missingness within observed rows

- `priceUsd`, `liquidity`, `volume24h`, `priceChange*`, nullable per row; occur when the DEX aggregator returned incomplete data at sample time. Frequency of null varies over the window; no systematic pattern of nulls.
- `dexId`, `pairAddress`, null iff the input row is family_2 (8,356 rows, 1.17%). Not a data-quality artefact; a structural feature of the older tracker schema.
- `regime`, null for all rows before the field's introduction on 2026-04-24 and for the 7,906 later family_2 rows, whose schema has no regime field (115,907 null rows in total, 16.17%).
- `source_pseudonym`, null iff the input row is schema_variant 2 (99,225 rows, 13.84%). See canonicalization spec §4.

Each nullable field's exact distribution is derivable from the deposited JSONL; no separate missingness table is published because the semantics differ per field.

## 7. Downstream users, recommended language patterns

**Use:**
- "Among the 716,762 post-rejection samples observed in RED-REJECT-2026-v2..."
- "Of the 18,237 distinct rejection events in the corpus..."
- "Restricted to the observed sampling frame, the per-filter share of `downtrend_24h` is 56.13%."
- "Follow-up windows are right-truncated at 2026-07-16T21:57:03.283Z."

**Avoid:**
- "The fleet rejects N% of tokens by filter X", denominator not observed.
- "Every rejection event during the window is present", cannot be verified.
- "The corpus is representative of...", sampling frame is not random-sample.
- "Filter X caught N% of scams", endpoint not defined in the corpus; see the Post-Rejection Follow-up Sampling methodology for the correct careful wording ("later-observed tracker state `gone`", never "rug pull", "fraud", "scam").

## 8. Confidence tiers for corpus-derived claims

- **HIGH**, sampling-frame distributions (per-filter, per-DEX, per-family, per-source-pseudonym shares of the 716,762 observed rows). Directly counted from the deposited JSONL; regenerate with `scripts/build_release.py` and `provenance/corpus_distributions.md`.
- **HIGH**, event/sample structural statistics (18,237 events, 4,635 mints, 4,278 events with more than one `(dexId, pairAddress)` value of which 88 span two or more identified trading pools, 0 duplicate clusters). Directly counted from the deposited JSONL.
- **MEDIUM**, per-filter follow-up-time distributions and per-filter market-state summaries. Depend on sampling-schedule structure; users should segment by sample_count and by rejection month.
- **LOW**, any claim that projects onto the population of all fleet rejections (in-scope only if paired with an independent registry).
- **LOW**, any claim that the tracker's follow-up-observability threshold does not correlate with underlying token behaviour (a mild survivorship-into-observability effect is present by construction).
