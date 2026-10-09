# The user's jevtrader, and how TARTAR relates to it

`github.com/AJW9991/jevtrader` (public since 2026-10-09; read-only for TARTAR sessions: clone it
anonymously, never push to it). Read 2026-10-09 by the profitability session at commit 9ce9b7b.

## What it is
A **paper-only, forward-only measurement** of a "two models at two speeds" loop on **Coinbase
SOL-USD**. Every minute, Jev (TypeSafe System One) answers five fixed typed questions from a
~10-word adjective state. Nightly, a slow model (Claude) proposes a rewrite of the `action`
question's wording, and a person applies it. Arms are paired on every tick: **A** = frozen wording,
**B** = nightly-rewritten wording, **C** = the no-model rule the thresholds imply (and in v2, **D** =
the wording's own table). It runs on the user's Mac under launchd, and its data stays there.

- **v1 (sealed, running):** T0 2026-09-25 21:40Z → ends **2026-10-23 21:40Z**; `make results` that
  evening. H1/H2 at 0 bps gross; results (report §4–§7) **withheld until day 28 by design**.
- **v2 (drafted, pre-registered `PREREG-v2.md`):** 15/60/240-minute decision cadences, per-product
  (SOL plus candidates ETH/XRP/AVAX/ADA from a probe), primary B − C pooled at α 1/40, family F
  of four. **Fee arithmetic:** each arm's break-even fee per fill,
  `f*_X = 90 · E_X(0) / (E_X(0) − E_X(90))`, printed against `FEE_BPS_COLUMNS = (0, 2, 10, 25, 50, 90)`.

## Rules for TARTAR sessions (from its PROTOCOL and design)
- **Never unblind or disturb it.** Don't run its reports on its data (we don't have the data
  anyway), don't push to it, don't feed its outcomes or proposals into anything, and don't propose
  changes to its sealed documents.
- **Its PROTOCOL keeps it separate from the user's `crypto-trading-system` repo** and sits under
  the user's personal JEV protocol, whose §5 lists "any always-on hook that makes a model call"
  and "`jev ask` as a decision instrument" as Never (jevtrader is a signed carve-out, a
  measurement). **TARTAR's Jev uses (shadow mode, `tartar decide --jev`, the fast loop's `jev`
  scorer) aren't covered by that carve-out.** The user should decide whether TARTAR needs one
  (paper only, own key, own ledger, spend tripwire). Flagged to the user on 2026-10-09.

## TARTAR's contribution: an on-chain cost table for the day-28 fee arithmetic
`handoff/experiments/sol_dex_costs.py`: every 20–30 s, a Jupiter (lite-api.jup.ag) quote of
$1,000 USDC → SOL and exactly that SOL → USDC (the round trip, no reference price needed), plus
Coinbase's best bid/ask. First sample, 2026-10-09 03:37–03:48Z, 33 samples
(`handoff/data/sol-dex/`):

| | median | p90 |
|---|---|---|
| on-chain round trip, fees + impact, both legs | −0.04 bps | 0.36 bps |
| + $0.05 per transaction (generous; priority fees ~0) | 0.96 bps | 1.36 bps |
| **per fill** (comparable to jevtrader's per-fill fee columns) | **0.48 bps** | **0.68 bps** |
| buy leg vs Coinbase ask | +1.6 bps | +2.6 bps |
| sell leg vs Coinbase bid | −2.9 bps (better) | −1.8 bps |
| Coinbase retail round trip at 90 bps taker | ~181 bps | |

Routes: Solana's proprietary on-chain market makers (Kipseli, BisonFi, HumidiFi, Aquifer,
TesseraV, Obsidian) quote $1,000 at near-zero spread. **Reading:** on-chain SOL-USD costs about
**0.5 bps per fill against 90 at the venue**, below jevtrader's smallest non-zero column (2 bps).
On day 28, any arm whose f*_X is above ~1 bps per fill would clear on-chain costs that the
Coinbase retail tier cannot.

**Second window, 2026-10-09 04:33–05:33Z** (predictor session; data committed in
`handoff/data/sol-dex/`):
- $1,000: **0.46 bps per fill** (p90 0.70; 120 samples).
- $10,000: **0.15 bps per fill** (p90 0.33; 71 samples).
- **Quote decay** (same quote re-taken 1/2/4 s later, 178 samples): the drift-free mean is
  0.00 ± 0.03 bps at every delay, so latency adds noise (median |change| 0.26 bps at 2 s, p90 1.3),
  not cost.
- Realistic per fill: **~0.5 bps expected, ~1.3 bps p90**. That is under jevtrader's 2 bps column.

**Caveats:** quotes, not fills. Prop AMMs update every slot and a quote can move before a
transaction lands (latency ~1–2 s), so realised cost is higher than quoted. Quote decay is now measured
(above): it adds noise, not cost. MEV/sandwich risk, failed
transactions and the USDC/USD basis aren't priced. Two night-time (UTC) windows so far (03:37–03:48 and 04:33–05:33). US/EU daytime is still to
sample: `sample --minutes 60` and `decay --minutes 60`.

## Not done, on purpose
No SOL-USD + Jev loop was built in TARTAR. jevtrader is that loop, already pre-registered and
running, and a duplicate would add nothing until its day-28 results exist. If they show an arm
with positive f*_X, the on-chain execution path (Jupiter, paper first) is where TARTAR's code
(slots, latency, costs) can help.
