# TARTAR strategy review (2026-10-10)

Built from profitability.md, edge-hunt.md, preregistration/ results, STATUS.md and autotrade/REPORT.md.
Facts below are as recorded in those files. Likelihoods in the "live" table are judgement calls, marked as such.

## Bottom line

- **More than 20 studies are null, and nearly all for the same reason. Round-trip costs are larger than the moves we can predict.**
  On pump.fun and fresh pools a round trip costs about 2.7–3.5%. The best predictable moves there are about 1% before costs.
- **Every result that survived comes from a cheap venue.** These are Hyperliquid perps (about 5–20 bps a side) and yield products (JLP, HLP). There the signal is bigger than the cost.
- **Recommendation: stop new pump.fun entry research.** Let the two pump.fun tests that are already running finish, since they cost nothing. Spend effort on low-cost venues and on yield carry.

## 1. Ruled out, and why

| Family | Best result | Why it failed |
|---|---|---|
| pump.fun launch buying, all variants (§3.2–3.8) | negative after costs | Cost floor ~3.5% round trip (later ~2.7–3.1% via Jupiter); predictable move ~1% |
| Faster entry / same-slot sniping (§3.9, §3.18) | n/a | The edge is the creator's own bundle; we can't get ahead of it |
| Graduation run-up (§3.10) | null | No move left after costs |
| Longer holds | −12.5% | Fresh tokens decay |
| Copy-trading wallets (§3.15) | null | Followers pay the cost and get no edge |
| PumpSwap graduated (pre-registered, 264 pools) | test −19.6% to −38% | Costs ~1.2–1.25%/side, no signal |
| Predictor v3.1 + P(rug) (pre-registered) | −5.15% [−11.85, +2.52], n=108 | Model ranks, but not by more than the costs |
| Exits, gating, Jupiter re-routing | best −2.9% [−4.1, −1.6] | Cheaper route adds only +0.4–0.8 pts; flips nothing |
| Early-flow movers / curve triggers | −2.2% / −0.3% [−7.4, +6.7] | Too small and noisy |
| Recalibration | −5.6% | — |
| Who-trades F1 (pre-registered, backtest) | +1.12% [−6.30, +8.49], n=175; Lightning −4.69% | ~1% at best; CI spans zero |
| Revival, PumpSwap-late (round I) | null | — |
| PumpSwap LP | 0.67x at 1 h | Impermanent loss beats fees |
| Fresh-token shorts | not possible | No borrow venue |
| SOL microstructure (lead-lag, 2 s prediction, seasonality) | null | Prediction dies within 2 s; seasonality doesn't persist |
| Crash reversal | on-chain median −7.6 bps | Needs a CEX for fills |
| LST carry / LST loop | +0.3% APR excess in 2026 | Decayed |
| Funding dispersion / D2 funding carry | weak / loses | Reverse of it is mostly momentum (kept as D) |
| D3 other perp rule families (trend, reversal, residual, volume, nearness) | null | — |
| Listing fade F1 | +2.9% [−28, +25], n=7 | Squeezes (PANDORA −1,888%) |
| Vault following | null | Past winners don't persist |
| Polymarket (33 rules) | null | — |
| revflow E1b | −0.01%/day [−0.14, +0.13] | — |
| hl-copy E2 | +0.06%/day, below random placebo (+0.11%) | — |
| pumpflow E1 (public data) | timing effect ~0 | DefiLlama posts ≥25 h late; removed from the agent |

**Pattern.** Whenever a signal was real, it was smaller than the round-trip cost of the venue. pump.fun is the extreme case: costs are 15–30x those on Hyperliquid, and the signals there are not proportionally bigger.

## 2. Still live (paper)

Likelihood of passing is my judgement from the recorded test CIs and decay. It is not a computed number.

| Test | Evidence so far | Scored | Likelihood to pass |
|---|---|---|---|
| **xs_momentum 14d (D)**, Hyperliquid perps | test +1.50%/week [−0.12, +3.31] after funding; 12 rules tried | signals Mondays 2026-10-12 → 2027-10-11; final after ~2027-10-20 | **Moderate.** Strongest survivor, but CI touches zero and 12 rules were tried |
| **vol_momentum (D3)** | val +2.15% [+0.46, +3.88], test +2.03% [+0.26, +3.97]; 0.87 correlated with D | same 52 weeks; interim 2027-04-13; final after 2027-10-20 | **Moderate.** Mostly the same bet as D, so it's not independent confirmation |
| **jlp_hedged A1** (JLP long, perps hedge) | +7.9% APR excess over Kamino USDC [+3.0, +12.4], 304 days, exploratory | window 2026-10-10 → 2027-01-08; `jlp_paper.py evaluate --final` after 2027-01-08 | **Moderate-to-good.** Earliest score date. Risks: liquidation on a spike, and one year of mostly bear-market data |
| **hlp_hold** | test +1.33%/month [+0.18, +2.70], decaying | 2026-10-12 → 2027-04-10 vs 5% hurdle; scored after 2027-04-11 | **Moderate-low.** Positive but shrinking |
| dip rule on established memecoins | in-sample excess +0.7%; REPORT: 9 trades, +0.52%, wide CI | ≥200 trades or 2026-10-30 | **Low.** Signal is about the size of its costs |
| who-trades-forward F1 (powered) | backtest ~1% best case | launches 2026-10-10 01:00 → 10-19 01:00; scored after 2026-10-19 02:00; needs CI lower bound > 0 | **Low.** ~1% true edge can't clear a zero lower bound at these costs |
| pumpflow E1 forward | expected fail (data lag) | ~2027-04-08 | **Very low.** Faster-source check: 21 recorder days, needs 12/14 sign agreement and corr ≥ 0.8, else E1 closes |
| SOL-USD jevtrader | costs ≈ 0.5 bps/fill on-chain | sealed until 2026-10-23 | Not touched here (sealed) |

**Live path status.** Live senders for spot, perps and the JLP basket are built, gated and tested in dry run or simulation. Restart and overlap safety is in place. Nothing is promoted. Going live still needs Alexander's keys and an explicit OK (see handoff/autotrade.md, go-live checklist).

## 3. Where any remaining edge most plausibly sits

1. **Cross-sectional perp signals on Hyperliquid.** This is the only family with two independent-looking survivors (D and D3). Costs are small enough that a +1–2%/week signal clears them.
2. **Hedged yield carry (JLP, HLP).** The return comes from fees paid to liquidity providers, not from prediction. That makes it the most structural edge we have. The main risk is tail events, not decay of a signal.
3. **Perp data we haven't studied yet.** Examples are open interest and positioning context from the perps-ctx recorder, once enough data has built up. Same cheap venue, a different signal family.
4. **Not pump.fun.** The cheapest route found is still ~2.7% round trip on fresh tokens. A new pump.fun idea would need a move of 4%+ that we can predict, and 20+ studies found nothing close. The best was ~1%.

## 4. Ranked recommendation

1. **Hyperliquid perps momentum (D, D3): keep running, and widen carefully.**
   Let the 52-week tests run untouched; the first signal is Monday 2026-10-12. New perp research should be pre-registered as separate tests with their own placebo. Do not tune D or D3.
2. **Yield carry: get JLP-hedged and HLP ready to promote the day they score.**
   JLP scores first (after 2027-01-08). The infrastructure is done. What's left for Alexander: about $330, the wallet key, a funded Hyperliquid account, and the OK. Before then, it's worth a liquidation stress test on the hedge (a SOL/ETH/BTC spike day replay). **Done 2026-10-10** (edge-hunt.md §A, "A1 liquidation stress test"): the registered 3x rules survived 2021-2026 only by path luck (9 spikes would have liquidated from the top-up trigger); go live at 2x, restored every check-in.
3. ~~Perp data research (OI and positioning)~~ **Done 2026-10-10, null** (edge-hunt.md §D4): 16 pre-registered OI rules on OKX OI history, none with train and validation both positive.
4. **pump.fun: stop new entry research.**
   Keep only what is already running and free: who-trades F1 forward (scored 2026-10-19) and the E1 faster-source check. If F1 fails as expected, close pump.fun entry strategies on the board. Keep the recorders running only if their data feeds another test.
5. **Drop:** CEX-dependent ideas (crash reversal), decayed carries (LST), copy-trading and vault following, Polymarket rules, listing fades.

**Effort split suggestion:** most new work goes to items 1–3. pump.fun gets only monitoring until 2026-10-19.
