# Candidate search (2026-10-14)

The agent's weekly search (tartar/autotrade/search.py): every member of the perps-momentum grid, per family, the last 26 weeks held out; penalty level 0.1/189 (every rule this search has ever tested, both families). Weekly long-short returns, $1 per leg.

**Survivors this run: 0** (none queued).

## Coinbase US perps momentum (US-tradable)

95 rules backtested on 271 weeks (2021-08-02 .. 2026-10-05), Coinbase's daily USD history for the 23 coins with US perps, net of 20 bps per side of turnover, funding not charged.

Rules failing each check: penalized train 95, walk-forward thirds 74, holdout 46, copy of a registered rule 0.

| Rule | Train mean/wk | Penalized lower bound | Thirds | Holdout mean/wk | Corr. registered | Checks |
|---|---|---|---|---|---|---|
| cde_vol_momentum | +0.62% | -1.50% | +0.12% / -0.16% / +1.92% | -0.03% | nan | registered |
| cand-cde-L14-q3-vol-thu-lag1 | +1.22% | -0.20% | +0.46% / +1.42% / +1.78% | +0.49% | 0.34 | fails penalized_train, holdout |
| cand-cde-L14-q3-vol-thu-lag2 | +0.84% | -0.35% | +0.39% / +1.03% / +1.09% | +0.90% | 0.20 | fails penalized_train |
| cand-cde-L14-q3-raw-thu-lag1 | +0.75% | -0.46% | -0.04% / +0.93% / +1.38% | -0.07% | 0.31 | fails penalized_train, walk_forward, holdout |
| cand-cde-L28-q3-raw-thu-lag1 | +0.67% | -0.53% | -0.09% / +1.75% / +0.34% | -0.35% | 0.27 | fails penalized_train, walk_forward, holdout |
| cand-cde-L21-q3-raw-thu-lag1 | +0.68% | -0.55% | -0.33% / +1.46% / +0.90% | -1.25% | 0.28 | fails penalized_train, walk_forward, holdout |
| cand-cde-L21-q3-vol-thu-lag1 | +0.63% | -0.57% | -0.21% / +1.08% / +1.01% | -0.81% | 0.31 | fails penalized_train, walk_forward, holdout |
| cand-cde-L14-q5-raw-thu-lag1 | +1.29% | -0.63% | +0.13% / +2.16% / +1.60% | -0.82% | 0.33 | fails penalized_train, holdout |
| cand-cde-L7-q3-vol-mon-lag2 | +0.65% | -0.65% | +0.50% / +0.28% / +1.18% | +0.93% | 0.41 | fails penalized_train |
| cand-cde-L21-q3-vol-thu-lag2 | +0.48% | -0.66% | -0.10% / +0.99% / +0.56% | -0.85% | 0.25 | fails penalized_train, walk_forward, holdout |
| cand-cde-L28-q3-vol-thu-lag1 | +0.50% | -0.71% | +0.03% / +1.65% / -0.18% | -0.61% | 0.28 | fails penalized_train, walk_forward, holdout |
| cand-cde-L21-q3-vol-mon-lag2 | +0.43% | -0.75% | -0.10% / +1.09% / +0.32% | +0.46% | 0.56 | fails penalized_train, walk_forward |
| cand-cde-L7-q3-vol-mon-lag1 | +0.56% | -0.79% | +0.20% / +0.04% / +1.46% | +0.79% | 0.50 | fails penalized_train |
| cand-cde-L21-q5-raw-thu-lag1 | +1.04% | -0.79% | +0.86% / +1.66% / +0.60% | -3.05% | 0.34 | fails penalized_train, holdout |
| cand-cde-L28-q3-vol-mon-lag2 | +0.37% | -0.81% | -0.07% / +1.02% / +0.15% | +0.65% | 0.63 | fails penalized_train, walk_forward |
| cand-cde-L14-q3-raw-mon-lag2 | +0.37% | -0.83% | +0.13% / +0.80% / +0.20% | -0.10% | 0.60 | fails penalized_train, holdout |

(Top 15 by penalized lower bound, plus the registered rules for reference.)

## Hyperliquid perps momentum (research only: Hyperliquid bars US persons)

94 rules backtested on 147 weeks (2023-12-18 .. 2026-10-05), Hyperliquid's daily history, net of 20 bps per side of turnover and funding.

Rules failing each check: penalized train 94, walk-forward thirds 74, holdout 25, copy of a registered rule 1.

| Rule | Train mean/wk | Penalized lower bound | Thirds | Holdout mean/wk | Corr. registered | Checks |
|---|---|---|---|---|---|---|
| vol_momentum | +1.42% | -1.05% | -0.16% / +2.88% / +1.59% | +1.33% | 0.85 | registered |
| xs_momentum | +0.88% | -1.90% | +0.70% / +1.92% / +0.03% | +1.88% | 0.85 | registered |
| cand-xsm-L21-q10-vol-mon-lag2 | +2.82% | -0.10% | +1.42% / +5.05% / +1.98% | +2.90% | 0.46 | fails penalized_train |
| cand-xsm-L21-q10-raw-mon-lag2 | +3.12% | -0.33% | +2.12% / +5.96% / +1.28% | +4.34% | 0.59 | fails penalized_train |
| cand-xsm-L21-q10-vol-mon-lag1 | +2.63% | -0.36% | +1.17% / +5.27% / +1.48% | +2.34% | 0.67 | fails penalized_train |
| cand-xsm-L14-q3-vol-thu-lag2 | +1.48% | -0.39% | +1.49% / +2.36% / +0.58% | +0.73% | 0.49 | fails penalized_train, holdout |
| cand-xsm-L14-q3-vol-thu-lag1 | +1.48% | -0.39% | +1.50% / +2.30% / +0.63% | +1.17% | 0.52 | fails penalized_train |
| cand-xsm-L14-q5-vol-thu-lag1 | +1.72% | -0.59% | +0.21% / +3.65% / +1.34% | +2.18% | 0.46 | fails penalized_train |
| cand-xsm-L21-q3-vol-thu-lag1 | +1.02% | -0.73% | +0.81% / +2.05% / +0.22% | +0.17% | 0.53 | fails penalized_train, holdout |
| cand-xsm-L14-q5-vol-thu-lag2 | +1.46% | -0.91% | +0.42% / +3.17% / +0.81% | +1.11% | 0.43 | fails penalized_train |
| cand-xsm-L21-q3-vol-thu-lag2 | +0.84% | -0.92% | +1.05% / +1.41% / +0.07% | -0.37% | 0.45 | fails penalized_train, holdout |
| cand-xsm-L14-q5-vol-mon-lag2 | +1.40% | -1.07% | +0.42% / +2.66% / +1.12% | +1.73% | 0.81 | fails penalized_train |
| cand-xsm-L14-q3-raw-mon-lag2 | +0.99% | -1.21% | +0.67% / +1.98% / +0.31% | +0.28% | 0.77 | fails penalized_train, holdout |
| cand-xsm-L7-q3-vol-thu-lag1 | +0.88% | -1.23% | -0.53% / +1.60% / +1.59% | +0.79% | 0.33 | fails penalized_train, walk_forward |
| cand-xsm-L21-q3-raw-thu-lag1 | +1.05% | -1.27% | +1.95% / +1.33% / -0.17% | -0.57% | 0.43 | fails penalized_train, walk_forward, holdout |
| cand-xsm-L7-q3-vol-thu-lag2 | +0.59% | -1.28% | -0.22% / +0.64% / +1.37% | +0.71% | 0.23 | fails penalized_train, walk_forward |
| cand-xsm-L21-q5-vol-thu-lag1 | +0.90% | -1.29% | +0.56% / +2.16% / +0.00% | +0.50% | 0.46 | fails penalized_train |

(Top 15 by penalized lower bound, plus the registered rules for reference.)

## Candidates queue

| Candidate | Registered | Paper from | Scored after | Status |
|---|---|---|---|---|
| cand-xsm-L21-q10-vol-mon-lag2 | 2026-10-10T03:09:25Z | 2026-10-17 (first signal 2026-10-19) | 26 weeks | queued |
