# Candidate search (2026-10-10)

The agent's weekly search over the perps-momentum family (tartar/autotrade/search.py). 94 rules backtested on 147 weeks (2023-12-18 .. 2026-09-28), the last 26 held out; penalty level 0.1/94 (every rule this search has ever tested). Weekly long-short returns, $1 per leg, net of 20 bps per side of turnover and funding.

**Survivors this run: 1** (queued: cand-xsm-L21-q10-vol-mon-lag2).

Rules failing each check: penalized train 93, walk-forward thirds 74, holdout 24, copy of a registered rule 1.

| Rule | Train mean/wk | Penalized lower bound | Thirds | Holdout mean/wk | Corr. registered | Checks |
|---|---|---|---|---|---|---|
| xs_momentum | +0.87% | -1.89% | +0.87% / +1.97% / -0.23% | +1.74% | 0.85 | registered |
| vol_momentum | +1.37% | -1.07% | -0.02% / +2.86% / +1.27% | +1.68% | 0.85 | registered |
| cand-xsm-L21-q10-vol-mon-lag2 | +2.82% | +0.24% | +1.42% / +5.05% / +1.98% | +2.90% | 0.46 | **survives** |
| cand-xsm-L21-q10-raw-mon-lag2 | +3.12% | -0.19% | +2.12% / +5.96% / +1.28% | +4.34% | 0.59 | fails penalized_train |
| cand-xsm-L21-q10-vol-mon-lag1 | +2.62% | -0.33% | +0.95% / +5.67% / +1.23% | +2.34% | 0.67 | fails penalized_train |
| cand-xsm-L14-q3-vol-thu-lag1 | +1.48% | -0.33% | +1.50% / +2.30% / +0.63% | +1.17% | 0.52 | fails penalized_train |
| cand-xsm-L14-q3-vol-thu-lag2 | +1.47% | -0.33% | +1.88% / +1.97% / +0.58% | +0.86% | 0.49 | fails penalized_train |
| cand-xsm-L14-q5-vol-thu-lag1 | +1.72% | -0.46% | +0.21% / +3.65% / +1.34% | +2.18% | 0.46 | fails penalized_train |
| cand-xsm-L21-q3-vol-thu-lag1 | +1.02% | -0.66% | +0.81% / +2.05% / +0.22% | +0.17% | 0.53 | fails penalized_train, holdout |
| cand-xsm-L14-q5-vol-thu-lag2 | +1.42% | -0.78% | +0.72% / +2.83% / +0.69% | +1.28% | 0.43 | fails penalized_train |
| cand-xsm-L14-q5-vol-mon-lag2 | +1.40% | -0.84% | +0.42% / +2.66% / +1.12% | +1.73% | 0.81 | fails penalized_train |
| cand-xsm-L21-q3-vol-thu-lag2 | +0.82% | -0.87% | +1.25% / +1.21% / +0.00% | -0.13% | 0.45 | fails penalized_train, holdout |
| cand-xsm-L14-q5-raw-mon-lag2 | +1.45% | -1.11% | +1.92% / +2.05% / +0.37% | +1.35% | 0.84 | fails penalized_train |
| cand-xsm-L21-q3-raw-thu-lag1 | +1.05% | -1.12% | +1.95% / +1.33% / -0.17% | -0.57% | 0.43 | fails penalized_train, walk_forward, holdout |
| cand-xsm-L14-q3-raw-mon-lag2 | +0.99% | -1.14% | +0.67% / +1.98% / +0.31% | +0.28% | 0.77 | fails penalized_train, holdout |
| cand-xsm-L14-q5-raw-thu-lag1 | +1.76% | -1.14% | +2.33% / +2.23% / +0.71% | +1.62% | 0.49 | fails penalized_train |
| cand-xsm-L7-q3-vol-thu-lag1 | +0.88% | -1.15% | -0.53% / +1.60% / +1.59% | +0.79% | 0.33 | fails penalized_train, walk_forward |

(Top 15 by penalized lower bound, plus the two registered rules for reference.)

## Candidates queue

| Candidate | Registered | Paper from | Scored after | Status |
|---|---|---|---|---|
| cand-xsm-L21-q10-vol-mon-lag2 | 2026-10-10T03:09:25Z | 2026-10-17 (first signal 2026-10-19) | 26 weeks | queued |
