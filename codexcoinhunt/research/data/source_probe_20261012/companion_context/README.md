# Hour-Aware Adaptive Risk Management for Autonomous Memecoin Trading: Companion Dataset + Manuscript Bundle (v1.3)

**Author.** Arati Uday Kamat
**ORCID.** 0009-0000-4781-312X
**Concept DOI (cite this work; resolves to latest version).** 10.5281/zenodo.20043301
**v1.0 version DOI (permanent, unredacted deposit released 2026-05-05).** 10.5281/zenodo.20043302
**v1.1 version DOI (permanent; superseded by v1.2 for manuscript-file correction).** 10.5281/zenodo.21636182
**v1.2 version DOI (permanent; superseded by v1.3).** 10.5281/zenodo.21780072
**v1.3 version DOI.** Assigned by Zenodo on publication of this version.
**Version.** v1.3 (2026-09-28)
**Licence.** Creative Commons Attribution 4.0 International (CC-BY-4.0) for data and manuscript; MIT for the included `audit.py` reproduction script.
**Companion paper (SSRN preprint).** Kamat, A. U. (2026). *Hour-Aware Adaptive Risk Management for Autonomous Memecoin Trading on Solana DEXs: Evidence, Theory, and Design Lessons from a 15-Day Deployment.* SSRN abstract_id 6564803. https://ssrn.com/abstract=6564803
**Companion paper (arXiv preprint).** arXiv:2606.08232 (q-fin.TR).

## What is new in v1.3 vs v1.2

v1.3 removes patent application numbers from the manuscript files (Markdown, HTML and PDF), this README, `PROVENANCE.md`, `CHANGELOG_v1.0_to_v1.1.md` and `zenodo_description.txt`, replacing each with "a pending U.S. provisional patent application". It also removes the details of an earlier journal submission from this README, the two earlier changelogs and `zenodo_description.txt`. Data files, figures, `audit.py` and `LICENSE` are byte-identical to v1.2 (see `CHANGELOG_v1.2_to_v1.3.md`).

## What is new in v1.2 vs v1.1

v1.2 corrects the manuscript files that shipped in v1.1. The v1.1 bundle (published 2026-07-27) contained manuscript files produced during an intermediate v4 build; the final v4 build was completed 2026-07-29 and the v1.1 manuscript files therefore did not reflect the final published v4 content. v1.2 re-publishes the bundle with the final v4 manuscript files (matching the companion paper record on Zenodo); nothing else in the bundle changes. Data files, figures, `audit.py`, `LICENSE`, and `PROVENANCE.md` are byte-identical to v1.1 (see `CHANGELOG_v1.1_to_v1.2.md`).

## What is new in v1.1 vs v1.0

v1.0 (2026-05-05) shipped as a data-only deposit. v1.1 adds the manuscript, the four supporting figures, a reproduction script (`audit.py`), a per-filter provenance table (`PROVENANCE.md`), and updates the README to reflect the assigned Zenodo DOI and the ongoing manuscript revision.

- **v1.0 (2026-05-05):** four data CSVs + LICENSE + README + checksums (data only).
- **v1.1 (2026-07-27):** three unchanged data files + redacted `trades.csv` + LICENSE (unchanged) + updated README + four SVG figures + v4 manuscript (Markdown source + PDF) + `audit.py` reproduction script + `PROVENANCE.md`.

**Change to `trades.csv`.** The `exitReason` column is **removed** from v1.1. In v1.0 that column carried verbatim exit-trigger strings whose text embedded per-tier threshold values (for example, the first-trigger take-profit level). All seven other columns (`date`, `symbol`, `entryPrice`, `exitPrice`, `pnl`, `solIn`, `heldMin`) are cell-for-cell identical to v1.0, so every headline number in the manuscript reproduces from v1.1 by direct arithmetic; `audit.py` verifies this. The v1.0 record remains permanently archived under its own version DOI (10.5281/zenodo.20043302), as with any Zenodo version.

The other three data files (`rejection_outcomes.csv`, `scanner_2026-04-09.csv`, `scanner_2026-04-10.csv`) and `LICENSE` are byte-identical to v1.0; their SHA-256 hashes match. Readers who cited the v1.0 version DOI can continue to do so.

## Description

Companion deposit for Kamat (2026), a 15-day paper-traded deployment of an autonomous memecoin trading system on Solana decentralised exchanges. The deposit contains:

- The exact data underlying the paper's headline results: 190 closed paper-trades over a 15-day observation window (29 March to 12 April 2026, UTC), and 4,874 post-rejection price samples collected by a counterfactual tracking system across six anonymised filter categories.
- The four supporting figures used in the manuscript (SVG source).
- The manuscript v4 (Markdown source, HTML rendering and PDF), a revision that adds theoretical framing anchored on Kyle 1985, generalisable design lessons and expanded literature positioning (23 references total).

Filter labels in the post-rejection sample log are anonymised to `filter_1` through `filter_6` in descending order of sample volume. Liquidity and 24-hour volume in the sample log are quantised to the nearest power of two (log2 binning) to preserve heavy-tailed distributional shape while preventing threshold inference. Filter-internal score columns and derivative price-change columns are removed. Two days of paired scanner observation logs are included as supporting context for replication of the candidate-token universe at the same time resolution. SHA-256 checksums for all data files are provided in `checksums.txt`.

## Cutoffs (for exact reproducibility)

The paper's two headline data products are reproduced by these deterministic filters on the source logs:

- **trades.csv** - `date < 2026-04-12T18:00:00Z` applied to the production trade log to yield **190 rows** (matches paper).
- **rejection_outcomes.csv** - `sampleTs < 2026-04-12T15:00:00Z` applied to the post-rejection follow-up sample log to yield **4,874 rows** (matches paper).

## File Listing

```
Kamat_HourAware_2026_ZenodoBundle_v1.3/
|-- data/
|   |-- trades.csv                       (190 rows)
|   |-- rejection_outcomes.csv           (4,874 rows)
|   |-- scanner_2026-04-09.csv           (2,969 rows, day 1 context)
|   |-- scanner_2026-04-10.csv           (4,367 rows, day 2 context)
|
|-- figures/
|   |-- fig1_architecture_v2.svg         (pipeline architecture diagram)
|   |-- fig2_pnl_by_hour_v2.svg          (mean PnL by UTC entry hour)
|   |-- fig3_equity_curve_v2.svg         (cumulative PnL equity curve)
|   |-- fig4_filter_effectiveness_v2.svg (per-filter forward-loss shares)
|
|-- manuscript/
|   |-- Kamat_HourAware_2026_v4.md       (v4 Markdown source with figure refs)
|   |-- Kamat_HourAware_2026_v4.html     (v4 HTML rendering; source of the PDF)
|   |-- Kamat_HourAware_2026_v4.pdf      (v4 PDF)
|
|-- audit.py                              (reproduces every headline number from the CSVs)
|-- PROVENANCE.md                         (per-filter event and sample counts)
|-- README.md                             (this file)
|-- LICENSE                               (CC-BY-4.0)
|-- checksums.txt                         (SHA-256 manifest for all files)
|-- CHANGELOG_v1.0_to_v1.1.md            (record of what changed)
|-- CHANGELOG_v1.1_to_v1.2.md            (record of what changed)
|-- CHANGELOG_v1.2_to_v1.3.md            (record of what changed)
|-- zenodo_description.txt                (metadata used for the Zenodo web form)
```

## Schema (per data file)

### trades.csv (190 rows)

| Field | Type | Description |
|---|---|---|
| `date` | string | ISO 8601 UTC; trade **exit** timestamp. Entry timestamp is derived as `date - heldMin`. |
| `symbol` | string | Token ticker |
| `entryPrice` | float | USD per token at entry |
| `exitPrice` | float | USD per token at exit |
| `pnl` | string | Realised return percent (formatted, e.g. "+8.44%") |
| `solIn` | string | SOL position size (formatted, e.g. "0.015 SOL") |
| `heldMin` | string | Hold duration in minutes (formatted, e.g. "1.0min") |

The v1.0 deposit included an eighth column, `exitReason`, whose verbatim strings embedded per-tier threshold values. It is removed from v1.1. The v1.0 record remains permanently archived under its own version DOI (10.5281/zenodo.20043302), as with any Zenodo version. Every headline number in the manuscript reproduces from the seven columns above; `audit.py` verifies this.

### rejection_outcomes.csv (4,874 rows)

| Field | Type | Description |
|---|---|---|
| `sampleTs` | string | ISO 8601 UTC; observation timestamp |
| `mint` | string | Solana mint address (public on-chain identifier) |
| `symbol` | string | Token ticker |
| `rejectReason` | string | Anonymised filter label: `filter_1` to `filter_6` (descending sample volume) |
| `rejectTs` | string | ISO 8601 UTC; original rejection timestamp |
| `ageMin` | float | Minutes since rejection |
| `priceUsd` | float | USD per token (raw) |
| `liquidity` | int | USD; quantised to nearest power of 2 |
| `volume24h` | int | USD; quantised to nearest power of 2 |
| `dexId` | string | Venue identifier (DexScreener `dexId`) |
| `pairAddress` | string | Venue pair address |

### scanner_2026-04-09.csv (2,969 rows) and scanner_2026-04-10.csv (4,367 rows)

| Field | Type | Description |
|---|---|---|
| `timestamp` | string | ISO 8601 UTC; observation timestamp |
| `mint` | string | Solana mint address |
| `symbol` | string | Token ticker |
| `name` | string | Token long name |
| `chainId` | string | Chain identifier (Solana for this window) |
| `priceUsd` | float | USD per token (raw) |
| `volume5m`, `volume1h`, `volume6h`, `volume24h` | int | Quantised to nearest power of 2 |
| `liquidity`, `marketCap`, `fdv` | int | USD; quantised to nearest power of 2 |
| `buyCount5m`, `sellCount5m`, `buyCount1h`, `sellCount1h` | int | Transaction counts |
| `pairAge` | int | Pair age in milliseconds since first liquidity event |
| `dexId` | string | Venue identifier |
| `firstSeen` | string | First-seen flag |

## Reproduction

```bash
# Tested with Python 3.10+, pandas 2.0+, numpy 1.20+, scipy 1.7+
pip install pandas numpy scipy

# Reproduce the hour-of-day P&L variance reported in the paper.
# NOTE: `date` is the EXIT timestamp; entry hour is derived by subtracting heldMin.
python3 - <<'PY'
import pandas as pd
df = pd.read_csv('data/trades.csv', parse_dates=['date'])
df['heldMin_num'] = df['heldMin'].str.rstrip('min').astype(float)
df['entry_ts']    = df['date'] - pd.to_timedelta(df['heldMin_num'], unit='m')
df['entry_hour']  = df['entry_ts'].dt.hour
df['pnl_num']     = df['pnl'].str.rstrip('%').astype(float)
print(df.groupby('entry_hour')['pnl_num'].agg(['count','mean','std']))
PY
```

```bash
# Tabulate post-rejection sample volume per filter category
python3 - <<'PY'
import pandas as pd
df = pd.read_csv('data/rejection_outcomes.csv')
print(df['rejectReason'].value_counts().sort_index())
PY
```

Expected runtime: under one minute on a laptop.

## Citation

```bibtex
@dataset{kamat_houraware_2026_bundle,
  author    = {Kamat, Arati Uday},
  title     = {Hour-Aware Adaptive Risk Management for Autonomous
               Memecoin Trading: Companion Dataset + Manuscript Bundle},
  version   = {1.3},
  year      = 2026,
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.20043301},
  url       = {https://doi.org/10.5281/zenodo.20043301}
}
```

Kamat, A. U. (2026). *Hour-Aware Adaptive Risk Management for Autonomous Memecoin Trading: Companion Dataset + Manuscript Bundle* (v1.3) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.20043301

## Verification

```bash
# Verify file integrity against the SHA-256 manifest
sha256sum -c checksums.txt
```

## Competing Interests

The trading system from which the deposited data is drawn is the subject of a pending U.S. provisional patent application (filed 2026-06-25, Micro Entity status, in the author's name). The disclosed patent application covers system-level architecture claims and does not restrict access to or use of the deposited dataset or the `audit.py` reproduction script, which are released under CC-BY-4.0 and MIT respectively (this Zenodo record). The verbatim exit-trigger taxonomy, which embedded per-tier threshold values, was disclosed in the v1.0 data deposit (Zenodo v1.0 version DOI 10.5281/zenodo.20043302, released 2026-05-05) and is removed from v1.1 onward. Per-tier threshold values, the specific signal set, per-signal scoring weights, circuit-breaker triggering rules, scanner polling intervals, and the per-filter category mapping are undisclosed in the v1.1 deposit and are the subject of pending intellectual-property protection; every headline number in the manuscript reproduces from v1.1 by direct arithmetic on the deposited CSVs, and `audit.py` verifies this.

No other competing financial or personal interests are declared.
