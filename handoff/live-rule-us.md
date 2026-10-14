# Live rule for US strategies (v2, ADOPTED by AJ 2026-10-12 22:45 UTC)

> **Adopted** (AJ, 2026-10-12 22:45 UTC: "approved, move forward when ready"). Adopting the rule does not fund
> anything or send any order: section 4 item 1 (AJ's go in words to fund an Alpaca live account, its keys, and the
> live route built and reviewed) still has to happen. The paper side of the gate is checked every hour by
> `tartar/autotrade/live_gate.py` (REPORT line "Live rule gate", health check "Alpaca paper cost").

Redrafted by the "Full project overview and alignment" thread at AJ's request ("redraft the live rules to better
fit the whole picture we get from overview"). v1 (2026-10-12 ~00:20 UTC, "Overall improvement review") is in git
history; what changed is listed at the end. The picture it now fits: `findings.md` (every idea tested by Claude
and Codex) and `plan-2026-10-12.md` section G.

**Nothing here spends money.** Going live still needs AJ's go in words, a funded Alpaca live account and a live
order route that is not built (today `tartar/autotrade/alpaca.py` refuses any non-paper host). The registrations
and their scoring are unchanged.

## Evidence interpretation (2026-10-13 implementation clarification)

The frozen venue-cost addendum retains its original registered-pass language.
This later adopted operating policy deliberately describes a separate capped
execution measurement before a registered verdict. It is not a statistical pass,
proof of alpha, funding authority or an amendment of frozen scoring. Paper fills
are simulator evidence; proxy costs and complete real account debits are distinct.

## Why a rule, not a test result
No US registration can clear its 90% bar inside 52 weeks: CAPIT fires on ~6 crash days a year, and cde's weekly
CI is ~±1.7%. So going live is a sizing decision with a hard loss limit. Stage 1 measures real execution; it is not
expected to make meaningful money.

## 1. What any strategy needs before it can be considered (the standing checklist)
Every line in `findings.md` is judged against this, so later candidates don't need a new rule:

1. **US-usable venue** a US person may trade on (not Hyperliquid, Jupiter or Polymarket).
2. **Registered** before its forward window, with its scorer running (`experiments/final_scores.py`).
3. **Holds outside its study:** positive on coins or a period the study never used (CAPIT: +4.52%/trade on 10
   extra coins; VOLSPIKE failed this at −0.30%).
4. **Pays its real cost:** passes its train/validation splits at the measured cost of the route it would use.
5. **Fundable at a stake that survives rounding:** the live version at the stake AJ funds still has the edge
   (cde: rounding to whole contracts at $1k a leg cuts +0.39% to +0.12%/week).
6. **Beats random entries:** its paper results are reported against random entries on the same coins and hold
   (plan A2), so a market-wide drift is not mistaken for the edge.

## 2. Which strategy is eligible now
**Only `us_capit`** (CAPIT Z=4 H=24), and only on the coins that pass the cost screen in section 3.

| Line | Eligible? | Why (detail in `findings.md`) |
|---|---|---|
| `us_capit` | **yes** | Meets 1-4 and 5; item 6 reporting is built, sufficient priced forward evidence is pending and required before scaling (section 6) |
| `us_capit_fast` | no, research | Same rule booked sooner; tells us what an always-on machine would add |
| `us_capit~wide` | no, research | Its 10 coins have Alpaca meme/alt spreads (Codex measured ~0.5%/side on PEPE-type books); mostly the same crash days, so little new evidence |
| `us_volspike` | no | Fails item 3 (−0.30%/trade on the 10 extra coins) |
| `cde_vol_momentum` | no | Fails item 5 at a fundable stake (~$8k gross); look again after 26 paper weeks |
| Anything on Hyperliquid or Jupiter | never | US-only rule (AJ, 2026-10-11) |

## 3. Coin cost screen (new in v2)
The 0.39%/side assumption is an average. Alpaca's own books on 2026-10-11 were wide on several study coins
(spread in bps: BTC 1.7, ETH 2.0, SOL 9.1, XRP 12.9, LINK 17.5, DOT 22.4, ADA 29.5, DOGE 32.6, AVAX 56.9,
BCH 60.1, LTC 62.6), so AVAX, BCH and LTC cost about 0.55%/side before slippage.

* A coin trades live only if its **median measured Alpaca paper cost is at most 0.50%/side** over at least 3
  fills, or, before 3 fills exist, its quoted spread at the order is at most 50 bps (`max_spread_bps: 50`).
* A coin whose last 5 live fills have a median cost above 0.60%/side is dropped until AJ re-admits it.
* Expect BTC, ETH, SOL, XRP, LINK and DOT to pass and AVAX, BCH and LTC to fail on today's books.

## 4. Gate to start (all must hold)
1. AJ says go in words, opens and funds an Alpaca **live** account (suggested $1,500), and adds its keys as new
   GitHub secrets. Only then is the live order route built and reviewed.
2. Paper `us_capit` has at least **3 crash days and 8 trades** since 2026-10-12.
3. **Judged on the Alpaca paper fills**, not the book's prices: those of `us_capit_fast` (the same signals; its
   mirror orders go at the first hourly run after the signal), which is the timing a live route will have (~90 min, the backtest's 120-min column). Their mean net
   per trade is above **−4.7%** (the backtest's 10th percentile for 3 crash days at that entry).
4. Alpaca paper cost: median at most **0.50%/side** overall, and no fill more than 0.5% from the paper book's
   price for the same trade (health shows this once plan A1 is built).

What a real edge looks like at small samples (Coinbase hourly candles 2023-01..2026-10, 11 coins, 0.39%/side):

| | 60-min entry | 120-min entry |
|---|---|---|
| Mean net per trade | +3.66% | +2.68% |
| Trades / crash days | 71 / 25 | 71 / 25 |
| Worst day / worst drawdown at $200/trade | −$96 / −$156 | −$152 / −$209 |
| Chance the mean is below zero after 3 / 5 / 10 crash days | 34% / 28% / 18% | 37% / 31% / 24% |
| 10th percentile of the mean after 3 / 5 / 10 crash days | −3.5% / −2.7% / −1.1% | −4.7% / −3.8% / −2.2% |

A third of 3-crash-day samples are negative even if the edge is real, so the gate only screens out clearly broken
results and caps the loss.

## 5. Stake and stops
* **$100 per trade**, one position per coin, market orders at the first hourly run after the signal, exit at the
  registered 24 h hold. At most **$1,100** open (busiest day in history: 8 trades).
* At this stake the backtest's worst day is about −$76 and its worst drawdown about −$105.

Any one of these ends live trading; restarting needs AJ again:
* Realized live loss, **in account dollars after every cost**, reaches **$250**.
* After 5 live crash days, live mean net per trade below **−3.8%**.
* Median cost over the last 10 live fills above **0.60%/side** (that halves the edge).
* The registered score on 2027-10-12 comes back with a **negative mean** (inconclusive is not a stop).
* Any order the agent can't match to a paper trade, or a position open more than 2 hours past its exit: the agent
  writes `autotrade/HALT`.

## 6. Scaling (needs AJ's word each time)
All must hold before doubling to $200 a trade; never above $500 a trade without a fresh review:
* At least **10 live crash days**, live mean net above **+1%** per trade, median cost at most 0.45%/side.
* **The live account is up in dollars** after every cost (Codex's lesson: summed trade percentages are not account
  growth).
* Paper `us_capit` beats random entries on the same coins and hold (plan A2), point estimate above zero.
* At $200+ a trade, review the always-on machine using actual additional account
  benefit less marginal expenses. Earlier timing estimates do not guarantee
  payback. Saved $100-stake hourly-policy models support only $1.31-$1.52/month
  of extra cost under fixed historical assumptions; an extra $5/month exceeds
  their modeled advantage. Both entry and exit shift; no actual box latency,
  expense-inclusive account replay, forecast or linear stake scaling is implied.
  Shared/sunk infrastructure and research utility need separate allocation.
  See `reviews/box-fixed-cost-hurdle-2026-10-13.md`. Existing scaling gates above
  and separate authority are unchanged.

## 7. Honest expectations
CAPIT fires on about 6 crash days and ~16 trades a year, fewer after the coin screen. At $100/trade and +2-3% net
that is **about +$25 to +$50 a year**: stage 1 buys real fills and a cost measurement, not income. At $1,000 a
trade it would be roughly +$250 to +$500 a year with up to $6,000-11,000 exposed for a day. Reaching 10 live
crash days takes about 18 months at historical rates. No other line in `findings.md` is close: the next
candidates would come from the watch list (Deribit perps via Coinbase for retail) or from paper results that change.

## What changed from v1
* Section 1: a standing checklist so later candidates are judged the same way (from the overview).
* Section 3: per-coin cost screen; v1 used the 11-coin average, which hides AVAX/BCH/LTC's wide Alpaca books.
* Gate item 3: judged on the Alpaca paper fills (real timing and cost), not the book's prices.
* Stops: in account dollars after every cost; a negative registered score in 2027-10 is a stop.
* Scaling: needs the account up in dollars and a positive excess over random entries (Codex's two lessons).
* Expectations: coin screen lowers the trade count a little.
