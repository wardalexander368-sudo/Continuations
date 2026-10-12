# Findings ledger: every idea tested, by Claude or Codex

One table of everything this project has tested, its status, the evidence **after costs**, and where the detail
lives. Written 2026-10-12 by the "Full project overview and alignment" thread from the existing write-ups (no new
backtests). When a result changes, update its row here and the topic document; the topic document holds the detail.

**Bottom line (2026-10-12):** nothing is proven profitable on a venue a US person can use. One US rule
(`us_capit`) is the go-live candidate under a draft rule AJ has not adopted; three more US lines collect paper
evidence. Every non-US line is research only (AJ, 2026-10-11) and can never go live. Costs, not ideas, decide
almost every result: a rule needs moves of a day or more to pay US spot fees.

Status words: **paper (US)** = forward test on a US-usable venue, could go live; **paper (research)** = forward
test on a non-US venue, can never go live; **closed** = tested and failed after costs; **untested** = idea only.
CIs are 90% unless stated. "Test" means the untouched last split of a backtest.

## 1. US-usable, paper now (the only lines that could go live)

| Idea | Venue | Evidence after costs | Status | Where |
|---|---|---|---|---|
| Capitulation bounce (`us_capit`, CAPIT Z=4 H=24) | US spot; Coinbase prices, Alpaca paper mirror | Test +6.23%/trade at Alpaca 0.39%/side (+5.77% [−1.5, +11.4] at the registered 0.62%), **28 trades on 11 days**. Fails train at Coinbase taker (0.91%). Fades with delay: +4.11% at 15 min, +2.97% at the registered 30 min (Alpaca cost, 105 trades all splits), +1.93% at the ~90 min a next-run order gets. Holds on 10 extra coins (+4.52%, mostly the same crash days). | paper (US) from 10-12; live rule v2 adopted 10-12 (gate in REPORT; no live route); scored 2027-10-12 | `edge-hunt.md` §K, `reviews/gap-review-2026-10-11.md`, `reviews/timing-2026-10-11.md`, `reviews/overall-2026-10-11.md`, `live-rule-us.md` |
| `us_capit_fast` (same, booked one bar sooner) | same | Research line for the latency finding above | paper (US) research line | `reviews/timing-2026-10-11.md` |
| `us_capit~wide` (same, 10 extra coins) | same | +4.52%/trade at 0.39%; CI spans zero; 13 of 17 crash days shared with the 11 study coins. Codex's measured Alpaca books on meme coins (PEPE, BONK, DOGE, WIF) suggest ~0.5%/side before adverse fills there, a little above 0.39% | paper (US) shadow line | `reviews/overall-2026-10-11.md`; Codex `codexcoinhunt/research/Orderbook_and_Buyer_Research.md` |
| Volume-spike follow-through (`us_volspike`, K=10 H=72) | US spot, Alpaca paper mirror | Test +1.78%/trade at 0.39% (+1.32% [−1.9, +4.5] at 0.62%), 87 trades. Fails train at Coinbase taker. **Fails on 10 extra coins (−0.30%)**, so likely fitted to the first 11 | paper (US) from 10-12, low prior; scored 2027-10-12 | `edge-hunt.md` §K, `reviews/overall-2026-10-11.md` |
| Vol-scaled momentum on Coinbase US perps (`cde_vol_momentum`) | Coinbase Derivatives (US) | Test +0.39%/week [−1.05, +1.94] at 20 bp/side; whole-contract rounding at $1k a leg cuts it to +0.12%/wk; funding ~−0.04%/wk. Needs ~$8k gross | paper (US) from 10-12; scored 2027-10-19 | `edge-hunt.md` §L, `preregistration/cde-vol-momentum/` |
| Weekly search, US "cde" family | Coinbase US perps | 95 momentum rules, shared Bonferroni M=189: first run no survivor (best penalised bound −0.20%) | runs Wednesdays | `autotrade.md` "Self improvement", `autotrade/search/REPORT.md` |

**Why none can be "proven" in a year:** CAPIT sees ~6 crash days a year and cde's 52-week CI half-width is
~±1.7%/week, so no US registration can clear its 90% bar inside 52 weeks. Going live depends on the draft
go-live-small rule (`live-rule-us.md`), which is AJ's decision.

## 2. Non-US venues, paper research only (never live: Hyperliquid and Jupiter bar US persons)

| Idea | Evidence after costs | Status | Where |
|---|---|---|---|
| 14-day cross-sectional momentum on HL perps (`xs_momentum`) | Test +1.50%/week [−0.12, +3.31] after funding (39 weeks), 12 rules looked at. Perps audit (full history): +1.0%/wk, +0.1% without the best 5 weeks (fragile) | paper (research); scored 2027-10-21 | `edge-hunt.md` §D, `preregistration/xs-momentum/` |
| Vol-scaled momentum on HL perps (`vol_momentum`) | Test +2.03%/week, CI above zero; 0.87 correlated with xs_momentum. Perps audit: +1.4%/wk, +0.7% without the best weeks (most robust of the family) | paper (research); scored 2027-10-20 | `edge-hunt.md` §D3, `preregistration/vol-momentum/` |
| Weekly search, HL family (`cand-*`) | First survivor (L21 q10 vol lag2) is best-of-94; expect ~+2.5%/wk, not +2.8% | paper (research) from 10-19 | `autotrade.md` "candidate L21 q10 vol lag2" |
| Wick bounce on HL perps (`wick_bounce`) | Test +80 bp/trade [−20, +177], 125 trades; 2026-03..09 −141 bp; low prior. Does not carry over to US spot | paper (research); scored 2027-10-12 | `edge-hunt.md` §J, `preregistration/wick-bounce/` |
| Hedged JLP (JLP long, SOL/ETH/BTC perp shorts) | +7.9% APR over USDC, exploratory; live rebalance must resize, not close/reopen | paper (research); scored 2027-01-08 | `edge-hunt.md` §A1, `preregistration/jlp-hedged/` |
| HLP vault hold | +11 to +28%/yr in recent halves vs a 5% hurdle, thin and decaying | paper (research); scored 2027-04-11 | `edge-hunt.md` §G, `preregistration/hlp-hold/` |
| Pump.fun revenue surprise → PUMP perp (E1, pumpflow) | Backtest edge needs same-day data; DefiLlama publishes ~25 h late, and at that delay the timing part is +0.20% [−0.45, +0.85] (no edge). The live version needs our own pump.fun feed, which is off. Same rule on 8 other buyback tokens is flat | **effectively closed**: the registered test still collects (one small commit a day) and is scored 2027-04-09, but expect a fail; agent strategy disabled | `edge-hunt.md` §E1 "publish delay" |
| Dip buying on established memecoins (`dip` + 8 variants) | OOS −3.9%/trade before fees; agent paper −5.21%/trade on 137 trades (fail), variants −1.9% to −8.7% | **closed for real money**; the registered test is scored 2026-10-30; variants retire at 200 trades or 21 days | `profitability.md` §3.11, `preregistration/dip-rolling/` |
| SOL-USD with Jev (AJ's jevtrader) | On-chain cost ~0.5 bp/fill; sealed test | readout 2026-10-24; Jev stays off in TARTAR | `jevtrader.md`, `profitability.md` §3.12 |

## 3. Closed on US venues

| Idea | Evidence after costs | Where |
|---|---|---|
| US long-only spot momentum (and BTC-hedged) | ~+0.05%/week, negative without the best 5 weeks; the edge was in the short leg | `autotrade.md` "US-only venues" |
| US spot breakouts, RSI oversold, Bollinger squeeze, wick bounce | Fail at every US cost; none reopens at Alpaca 0.39% | `edge-hunt.md` §K, `reviews/gap-review-2026-10-11.md` |
| Exit variants on the US patterns (24: trails, take-profit, break-even, longer holds) | None beats the registered fixed holds | `reviews/timing-2026-10-11.md` |
| CDE momentum variants (8: hold bands, lag, weekday) | Fail validation | `reviews/timing-2026-10-11.md` |
| Kalshi favourite/longshot (24 rules, 16,342 markets) | Every band loses in train at the ask with fees | `edge-hunt.md` §M |
| S&P 500 / Coinbase US500 trend timing (8 rules, 1950-2026) | All lose to holding in train | `edge-hunt.md` §N |
| Polymarket biases (33 rules; also not US-usable) | Nothing passes after the spread | `edge-hunt.md` §H |

## 4. Closed on non-US venues (Hyperliquid, Solana, pump.fun)

| Idea | Evidence | Where |
|---|---|---|
| Buying pump.fun launches in every form (baselines, model signals, screens, Jev, faster entry, same-slot, graduation run-up, longer holds, copy-trading, graduated tokens, curve triggers, early-flow pickers, exits/gating) | All lose at real costs (Lightning round trip ~3.07%, a fresh token ~5.5%); best −2.2% to −2.9% on test | `profitability.md` §1, §3.2-3.23 |
| Predictor candle calls + P(rug), recalibrated | Calibration fixed, trading unchanged (best −5.6% at Jupiter cost) | `profitability.md` §3.20, §3.24 |
| Who sold the dip (edge hunt F, pre-registered) | +1.1% [−6.3, +8.5] at curve fees, −4.7% via Lightning | `profitability.md` §3.25 |
| F1 who-trades forward test | Closed: needs the recorder, which is off under the GitHub-terms decision | `STATUS.md` Active |
| Memecoin LP on PumpSwap, memecoin shorts | Closed | `edge-hunt.md` §C |
| HL funding carry across perps (D2) | Loses; its reverse is weaker momentum | `edge-hunt.md` §D2 |
| HL spot-perp funding carry (E3, pre-registered) | All 12 rules lose vs USDC lending; 2 liquidations | `preregistration/spot-carry/RESULT-2026-10-10.md` |
| LST cash-and-carry (A2), funding dispersion (A3) | Decayed to ~0 in 2026; weakest | `edge-hunt.md` §A |
| SOL microstructure: lead-lag, seasonality, seconds-scale | Closed; crash reversal real on Binance only (on-chain −7.6 bp) | `edge-hunt.md` §B |
| Open interest rules (D4, 16 rules) | Nothing passes | `edge-hunt.md` §D4, `preregistration/oi-study/RESULT-2026-10-10.md` |
| Following HL vaults (G), copying HL leaders | Closed | `edge-hunt.md` §G, `preregistration/hl-copy/RESULT-2026-10-10.md` |
| Short new HL listings (F1 round 2) | Median fades, squeezes own the mean; test +2.9% [−28, +25] | `preregistration/listing-fade/RESULT-2026-10-09.md` |
| Calendar, lottery, IVOL, BAB, skew, CME gap (36 rules) | None passes | `edge-hunt.md` §I |
| Hour of day, big-move reversal on perps | Closed | `edge-hunt.md` §J |
| HL trend on majors; other momentum variants | Closed | project memory; `edge-hunt.md` §D3 |
| Funding-spike event trades (F2) | Designed, never run; now research-only by venue | `preregistration/funding-spike/SPEC.md` |
| Token unlocks, pre-market hyperps, decoder → HL perp | Dropped (no free data or too few events) | `edge-hunt.md` Round 2 |
| AgenKit/Jev "24/7 agent" prompt (10-12) | No help: 24/7 loop breaks GitHub terms; Kelly sizing only after a proven edge | project memory |

## 5. Codex (ChatGPT lane): CodexCoinHunt, imported 2026-10-12

Paper-only memecoin research under `codexcoinhunt/`; not wired into the agent. Review:
`reviews/codex-review-2026-10-12.md`. Its own record: **zero verified positions, zero doubled campaigns.**

| Codex idea | Evidence | Status |
|---|---|---|
| SLR-0.2 "Second-Look Relay" (buy a second wave of attention, $50 → $100 campaigns) | No validated entries. The one buyer episode studied: 4 of 5 buyers (97.2% of buy notional) were returning buyers, and a paid DEX Screener boost was active 10 min before buying, so it is not organic second-look demand | untested forward; lane closed here (memecoin buying) |
| REV-0.1 revival | Zero signals in either historical partition | not promoted (Codex D14) |
| Rebound/momentum on a 716k-row memecoin rejection corpus | Holdout mean −13.00% on 588 paths; momentum and random both ~−12.3% | closed (Codex D16); agrees with our pump.fun results |
| OB-0.1 order-book support on Alpaca meme pairs | Zero signals in a 12-minute capture | not promoted |
| FLOW-0.2 signed-flow on Alpaca meme pairs | Three paths rose at the midpoint but lost −0.65% to −1.59% after costs | not promoted (Codex D25): costs eat the move, same lesson as §1 |
| Audit of a published 190-trade track record | +117.7% summed trade returns ≈ $50 → $53.34 at a 14% stake | lesson adopted: judge in account dollars (plan A3) |

## 6. Cross-checks between Claude's and Codex's numbers

| Quantity | Claude | Codex | Reading |
|---|---|---|---|
| Alpaca fees | 0.15% maker / 0.25% taker; ~0.39%/side all-in on the 11 study coins | Same fees (refreshed 10-12); $7 round trips on DOGE/WIF/PEPE/BONK cost 1.32-1.85% incl. a 0.25%/side adverse allowance | Agree. Alt and meme spreads are wider than BTC/ETH; check `us_capit~wide` against measured fills before any live use |
| PumpPortal fees | Lightning 1%/side; round trip ~3.07% measured | Local 0.5%, Lightning 1% | Agree |
| PumpSwap pool fees | 0.30-1.25%/side, tiered by market cap (`profitability.md` §3.13) | 45-50 bp on one larger token's events; fee-aware quotes must not be charged twice | Agree (larger cap = lower tier); our decoder already counts each fee once |
| Memecoin entries vs random | Dip: excess over random −0.84% [−2.91, +0.96] | Momentum ≈ random ≈ −12% | Agree: no selection skill after costs |

No contradiction between the two lanes' findings. Codex's methods worth keeping (hash-pinned configs, matched
random controls, measured over modelled cost, unknown ≠ zero, account-dollar returns) are in the plan.

## 7. Not yet tested on US venues (ideas with a prior, no work until a trigger)

| Idea | Prior | Trigger |
|---|---|---|
| Vol-momentum on Deribit's ~90 perps via Coinbase | +0.68%/wk backtest on that list (vs +1.42 on HL) | Coinbase opens it to retail |
| Spot-long / Coinbase-perp-short funding carry | Low: the HL version earned about what USDC lending pays, and US spot costs more | Funding regime well above lending rates |
| Alpaca or Coinbase maker-only entries for CAPIT | Saves ~0.2-0.4 pts/side, but resting bids in a crash face adverse selection | Measured Alpaca paper fills (plan A1) |
| Kalshi beyond favourite/longshot (event-specific models) | Unknown; fees are high | A concrete event-level edge proposal |
