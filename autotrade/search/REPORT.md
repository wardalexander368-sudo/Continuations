# Candidate search (2026-10-21)

The agent's weekly search (tartar/autotrade/search.py): every member of the perps-momentum grid, per family, the last 26 weeks held out; penalty level 0.1/189 (every rule this search has ever tested, both families). Weekly long-short returns, $1 per leg.

**Survivors this run: 0** (none queued).

## Coinbase US perps momentum (US-tradable)

95 rules backtested on 272 weeks (2021-08-02 .. 2026-10-12), Coinbase's daily USD history for the 23 coins with US perps, net of 20 bps per side of turnover, funding not charged.

Rules failing each check: penalized train 95, walk-forward thirds 76, holdout 36, copy of a registered rule 0.

| Rule | Train mean/wk | Penalized lower bound | Thirds | Holdout mean/wk | Corr. registered | Checks |
|---|---|---|---|---|---|---|
| cde_vol_momentum | +0.57% | -1.42% | +0.12% / -0.16% / +1.75% | +0.42% | nan | registered |
| cand-cde-L14-q3-vol-thu-lag1 | +1.18% | -0.27% | +0.46% / +1.39% / +1.68% | +0.76% | 0.34 | fails penalized_train |
| cand-cde-L14-q3-vol-thu-lag2 | +0.80% | -0.40% | +0.39% / +1.01% / +1.00% | +1.05% | 0.20 | fails penalized_train |
| cand-cde-L14-q3-raw-thu-lag1 | +0.72% | -0.57% | -0.04% / +0.90% / +1.29% | +0.25% | 0.31 | fails penalized_train, walk_forward, holdout |
| cand-cde-L21-q3-vol-thu-lag1 | +0.59% | -0.65% | -0.21% / +0.95% / +1.03% | -0.48% | 0.31 | fails penalized_train, walk_forward, holdout |
| cand-cde-L28-q3-raw-thu-lag1 | +0.63% | -0.66% | -0.09% / +1.72% / +0.26% | -0.10% | 0.27 | fails penalized_train, walk_forward, holdout |
| cand-cde-L21-q3-raw-thu-lag1 | +0.64% | -0.67% | -0.33% / +1.33% / +0.92% | -0.94% | 0.28 | fails penalized_train, walk_forward, holdout |
| cand-cde-L14-q5-raw-thu-lag1 | +1.21% | -0.67% | +0.13% / +2.21% / +1.30% | -0.20% | 0.33 | fails penalized_train, holdout |
| cand-cde-L7-q3-vol-mon-lag2 | +0.64% | -0.68% | +0.50% / +0.23% / +1.19% | +1.06% | 0.41 | fails penalized_train |
| cand-cde-L21-q3-vol-thu-lag2 | +0.45% | -0.71% | -0.10% / +0.88% / +0.56% | -0.68% | 0.25 | fails penalized_train, walk_forward, holdout |
| cand-cde-L21-q3-vol-mon-lag2 | +0.43% | -0.74% | -0.10% / +1.00% / +0.41% | +0.31% | 0.56 | fails penalized_train, walk_forward |
| cand-cde-L28-q3-vol-thu-lag1 | +0.46% | -0.81% | +0.03% / +1.62% / -0.27% | -0.29% | 0.28 | fails penalized_train, walk_forward, holdout |
| cand-cde-L7-q3-vol-mon-lag1 | +0.54% | -0.81% | +0.20% / +0.04% / +1.37% | +1.04% | 0.50 | fails penalized_train |
| cand-cde-L14-q3-raw-mon-lag2 | +0.38% | -0.82% | +0.13% / +0.77% / +0.24% | -0.33% | 0.60 | fails penalized_train, holdout |
| cand-cde-L28-q3-vol-mon-lag2 | +0.37% | -0.85% | -0.07% / +1.05% / +0.13% | +0.46% | 0.63 | fails penalized_train, walk_forward |
| cand-cde-L14-q3-vol-mon-lag2 | +0.41% | -0.86% | +0.17% / +0.34% / +0.72% | -0.27% | 0.72 | fails penalized_train, holdout |

(Top 15 by penalized lower bound, plus the registered rules for reference.)

## Hyperliquid perps momentum (research only: Hyperliquid bars US persons)

94 rules backtested on 148 weeks (2023-12-18 .. 2026-10-12), Hyperliquid's daily history, net of 20 bps per side of turnover and funding.

Rules failing each check: penalized train 93, walk-forward thirds 79, holdout 21, copy of a registered rule 1.

| Rule | Train mean/wk | Penalized lower bound | Thirds | Holdout mean/wk | Corr. registered | Checks |
|---|---|---|---|---|---|---|
| vol_momentum | +1.32% | -1.22% | -0.16% / +3.07% / +1.06% | +1.51% | 0.85 | registered |
| xs_momentum | +0.79% | -2.05% | +0.70% / +2.07% / -0.44% | +2.04% | 0.85 | registered |
| cand-xsm-L21-q10-vol-mon-lag2 | +2.77% | +0.02% | +1.70% / +4.66% / +1.98% | +2.78% | 0.46 | **survives** |
| cand-xsm-L21-q10-raw-mon-lag2 | +3.03% | -0.34% | +2.37% / +5.74% / +1.01% | +4.80% | 0.59 | fails penalized_train |
| cand-xsm-L14-q3-vol-thu-lag2 | +1.41% | -0.42% | +1.49% / +2.32% / +0.40% | +0.70% | 0.49 | fails penalized_train, holdout |
| cand-xsm-L14-q3-vol-thu-lag1 | +1.40% | -0.47% | +1.50% / +2.21% / +0.48% | +1.38% | 0.51 | fails penalized_train |
| cand-xsm-L21-q10-vol-mon-lag1 | +2.55% | -0.56% | +1.17% / +5.97% / +0.45% | +1.95% | 0.67 | fails penalized_train |
| cand-xsm-L14-q5-vol-thu-lag1 | +1.66% | -0.64% | +0.21% / +3.68% / +1.06% | +2.36% | 0.46 | fails penalized_train |
| cand-xsm-L21-q3-vol-thu-lag1 | +0.95% | -0.77% | +0.81% / +1.87% / +0.16% | +0.42% | 0.53 | fails penalized_train, holdout |
| cand-xsm-L21-q3-vol-thu-lag2 | +0.78% | -0.91% | +1.05% / +1.27% / +0.01% | -0.37% | 0.44 | fails penalized_train, holdout |
| cand-xsm-L14-q5-vol-thu-lag2 | +1.39% | -0.93% | +0.42% / +3.21% / +0.54% | +0.96% | 0.42 | fails penalized_train |
| cand-xsm-L14-q5-vol-mon-lag2 | +1.41% | -0.97% | +0.35% / +2.67% / +1.23% | +1.44% | 0.81 | fails penalized_train |
| cand-xsm-L14-q3-raw-mon-lag2 | +0.95% | -1.20% | +0.56% / +2.09% / +0.22% | +0.38% | 0.77 | fails penalized_train, holdout |
| cand-xsm-L7-q3-vol-thu-lag2 | +0.61% | -1.20% | -0.22% / +0.71% / +1.38% | +0.40% | 0.23 | fails penalized_train, walk_forward |
| cand-xsm-L21-q3-raw-thu-lag1 | +0.97% | -1.22% | +1.95% / +1.14% / -0.21% | -0.23% | 0.43 | fails penalized_train, walk_forward, holdout |
| cand-xsm-L21-q5-vol-thu-lag1 | +0.84% | -1.22% | +0.56% / +2.13% / -0.21% | +0.76% | 0.45 | fails penalized_train, walk_forward |
| cand-xsm-L21-q3-raw-thu-lag2 | +0.95% | -1.25% | +2.05% / +1.34% / -0.59% | -0.91% | 0.34 | fails penalized_train, walk_forward, holdout |

(Top 15 by penalized lower bound, plus the registered rules for reference.)

## Candidates queue

| Candidate | Registered | Paper from | Scored after | Status |
|---|---|---|---|---|
| cand-xsm-L21-q10-vol-mon-lag2 | 2026-10-10T03:09:25Z | 2026-10-17 (first signal 2026-10-19) | 26 weeks | queued |
