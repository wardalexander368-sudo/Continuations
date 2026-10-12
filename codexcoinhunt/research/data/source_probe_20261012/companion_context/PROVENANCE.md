# PROVENANCE.md: per-filter breakdown for `rejection_outcomes.csv`

**Bundle:** Kamat_HourAware_2026 Zenodo companion, v1.1
**Companion manuscript:** Section VI.B, Figure 4
**Reproduction:** every number below is asserted by `audit.py`.

## What this file records

Two aggregations of the 4,874-row `rejection_outcomes.csv`, broken out by the six anonymised filter categories `filter_1` through `filter_6`, together with per-filter median follow-up-duration statistics that §VI.B and the Figure 4 caption both reference. The two aggregations answer different questions:

- **Event-level.** Grouping the 4,874 rows into distinct rejection events (unique `(rejectTs, mint, rejectReason)` triples) yields **184 events**. For each event, the reference price is taken as the price at the first observed sample (minimum `ageMin`), and mark the event as `lost-half` if any subsequent sample's `priceUsd` is ≤ 50 percent of that reference. The event-level column answers *"of the tokens the filter rejected, what share reached at least a 50 percent drawdown over the event's actual observed follow-up span?"* This is the quantity plotted in Figure 4 and the 17.9 percent full-cohort aggregate reported in §VI.B as a censored lower bound.
- **Sample-level.** Counting individual price observations (each row of `rejection_outcomes.csv` is one sample), and marking a sample as `below-half` on the same reference-price definition. The sample-level column answers *"of the price observations collected across all rejected tokens, what share sat below half of reference?"* This is the volume-weighted 26.0 percent aggregate reported in §VI.B. It is not the aggregation of Figure 4's bars.

The two share the same reference-price definition per event but count different units. Figure 4's caption calls this distinction out explicitly.

**Observation-window note.** No event in the deposited slice reaches a 24-hour follow-up span; the maximum observed span is 18.4 hours, and 47.3 percent of events consist of a single sample. Section §VI.B reports the primary event-level result on the restricted subset of 48 events with at least six hours of follow-up (27 lost-half, 56.25 percent). The full-cohort 17.9 percent below and Figure 4 both aggregate over each event's actual observed follow-up span rather than a fixed 24-hour window; the per-filter median-span column in the cross-tab makes the per-filter observation-duration confound explicit.

## Per-filter cross-tab

| filter    | events | events lost-half | events lost-half % | samples | samples below-half | samples below-half % | median follow-up span (min) |
|-----------|-------:|-----------------:|-------------------:|--------:|-------------------:|---------------------:|---------------------------:|
| filter_1  |     96 |               11 |               11.5 |   2,126 |                474 |                 22.3 |                        0.0 |
| filter_2  |     56 |               13 |               23.2 |   1,640 |                336 |                 20.5 |                       92.5 |
| filter_3  |      5 |                4 |               80.0 |     448 |                271 |                 60.5 |                    1,105.1 |
| filter_4  |      7 |                3 |               42.9 |     356 |                 40 |                 11.2 |                      390.0 |
| filter_5  |     17 |                2 |               11.8 |     192 |                146 |                 76.0 |                        0.0 |
| filter_6  |      3 |                0 |                0.0 |     112 |                  0 |                  0.0 |                       15.1 |
| **total** |    184 |               33 |               17.9 |   4,874 |              1,267 |                 26.0 |                       10.0 |

The `total` row's median follow-up span is the pooled event median (10.0 minutes), not the mean of the per-filter medians. Per-event follow-up spans are computed as `max(sampleTs) - min(sampleTs)` per event group; a single-sample event has span 0.

## Duration-stratified event counts

| Follow-up span | Events | Lost-half | Rate       |
|----------------|-------:|----------:|-----------:|
| under 1h       |    111 |         0 |  0.0 percent |
| 1 to 6h        |     25 |         6 | 24.0 percent |
| 6 to 12h       |     14 |         8 | 57.1 percent |
| over 12h       |     34 |        19 | 55.9 percent |
| **all**        |    184 |        33 | 17.9 percent |

The rate is not separable from observation duration on this slice: Pearson r(span, lost-half) = 0.604.

## Reconciliation with Figure 4

Figure 4 plots **event-level lost-half share** for five of the six categories. `filter_6` (n=3 events, 0/3 lost-half) is omitted from the plotted bars for readability but is included in the aggregate 33/184 (17.9 percent). The five plotted bars sum to 33 events across 181 events; adding `filter_6`'s 0/3 gives the 33/184 total. The range of plotted values is 11.5 percent (filter_1) to 80.0 percent (filter_3). Per §VI.B, this per-filter dispersion co-varies with per-filter median follow-up duration (rank-order match) and should not be read as evidence of relative filter quality on this deposited slice; longer per-event follow-up in the categories with short median spans would tighten the interpretation.

## Reproducibility

Running `audit.py` at the bundle root prints one OK line per assertion and exits 0 if every number above is reproduced from the deposited CSVs (four data files, no additional inputs). Grouping key: `["rejectTs", "mint", "rejectReason"]` (Python pandas syntax); this matches the manuscript §VI.B statement that events are "grouped on the mint, rejection-timestamp, and rejection-reason keys." A reviewer can invoke `python3 audit.py && echo PASS || echo FAIL` and treat the exit code as verification.

## Filter-category anonymisation policy

Filter labels `filter_1` through `filter_6` are ordered by descending sample volume, not by lost-half rate. The mapping from filter number to the underlying filter's operational identity (specific signal set, gate thresholds, category name) is undisclosed and is the subject of a pending U.S. provisional patent application. Every quantity in this file, in Figure 4, and in §VI.B is invariant under any consistent one-to-one relabelling of the six categories.
