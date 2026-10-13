# Trading agents and the next 3 months (to mid-January 2027): forecast and plan

Written 2026-10-13 by thread "Agent-surge market outlook" for AJ's question: what will the surge in trading agents
change in crypto over the next three months, and how do we set up for profit. US venues only; nothing here changes
live rule v2 or its gate.

**First, the "elliptical algorithm".** Trading agents do not touch the elliptic-curve cryptography (secp256k1,
ed25519) that secures coins and wallets; that would take a cryptographic break, not more traders. This plan reads the
question as: how does agent-driven trading change how prices move.

## 1. What the evidence says (checked 2026-10-13)

| Claim | Source | How solid |
|---|---|---|
| Agents/bots are a large share of crypto volume ("58%" to "65-80%") | Vendor blogs ([BlockEden, 2026-03](https://blockeden.xyz/blog/2026/03/14/ai-driven-crypto-trading-80-percent-volume-invisible-market-microstructure-revolution/)) | Weak: no primary data, estimates disagree |
| Regulators are worried about correlated agent trading: Bank of England warning (mid-2026); House Financial Services Democrats' letter to the SEC on "herding" (June 2026) | Cited in an arXiv survey of LLM trading systems ([arXiv 2609.19705](https://arxiv.org/pdf/2609.19705)) | Medium: second-hand, but consistent |
| The biggest recent crash (10 Oct 2025, ~$19B liquidated) came from a macro shock, cascading liquidations and thin books; no public evidence ties it to AI agents | [CoinShares](https://coinshares.com/se/insights/knowledge/billions-in-liquidations-what-happened), [Bitfinex](https://blog.bitfinex.com/education/ai-trading-agents-useful-tool-or-security-liability/) | Medium-strong |
| One year on, BTC and ETH order books are deeper than before that crash; altcoin books stay thin | [Pickaxe, 2026-10-10](https://pickaxe.io/resources/news/flash-crashes-in-crypto-lessons-from-the-1010-anniversary) | Medium (one source) |
| A few liquidation bots took $207.6M from 28,037 forced loan closures on Ethereum since Jan 2025 | A June 2026 analysis seen only in search summaries | Weak-medium (source not opened); fits the idea that bots already harvest crashes at speed |
| Robinhood's CEO: many agents reacting to the same news in milliseconds could amplify swings and drain liquidity, but also close price gaps faster | [Motley Fool, 2026-08-01](https://www.fool.com/investing/2026/08/01/robinhood-ceo-vlad-tenev-thinks-ai-agents-could-tr/) | Opinion |
| A "February 2026 wick" where $400M of liquidity vanished in 3 seconds because of agents | Vendor blog only | Unverified: ignored |

**Our own data (new, `handoff/experiments/edge-hunt/patterns/agent_regime.py`, 21-coin Coinbase hourly cache, CAPIT
Z=4 H=24, entry one hour after the signal, 0.39%/side):**

| Half-year | Crash days | Trades | Mean/trade | Mean per day | Worst hour / 24h drop |
|---|---|---|---|---|---|
| 2023H1 | 3 | 19 | +3.45% | +2.25% | 0.65 |
| 2023H2 | 3 | 9 | −5.20% | −8.53% | 0.62 |
| 2024H1 | 7 | 20 | −5.72% | −0.21% | 0.53 |
| 2024H2 | 4 | 24 | +7.75% | +6.22% | 0.30 |
| 2025H1 | 4 | 25 | +15.56% | +7.02% | 0.35 |
| 2025H2 | 2 | 15 | −1.78% | −2.03% | 0.42 |
| 2026H1 | 5 | 6 | +4.07% | +4.01% | 0.28 |
| 2026H2 (to 10-09) | 1 | 1 | −0.65% | −0.65% | 0.49 |

Reading: crash days have **not** become more frequent (2 to 7 per half-year, no trend), crashes have **not** become
sharper on the hourly scale (the share of the 24-hour drop that happens in the single worst hour fell from ~0.6 in
2023 to ~0.3-0.5), and the bounce is as noisy as ever. Samples are tiny (1-7 days per row), so this rules out only a
big change, not a small one. Whatever agents do so far shows up below one hour, where we don't trade.

## 2. Forecast for the next 3 months

Rough probabilities are judgement, not measurement.

1. **Short-horizon edges keep shrinking (≈80%).** News reactions, simple arbitrage, standard indicators and
   anything that pays off in minutes get crowded by more agents running similar code. This is already what our
   ledger shows: every short-horizon idea died on costs.
2. **Majors get deeper, alts stay thin (≈60%).** BTC/ETH/SOL spreads hold or tighten; alt and meme books stay thin
   and get emptier in stress, so the cost gap between them widens on crash days.
3. **When a crash comes, the first minutes get faster and the bounce starts sooner (≈50%).** Liquidation bots and
   dip-buying agents react in seconds. Our hourly data does not show this yet. If it happens, the part of the
   capitulation bounce we can reach at ~90 minutes gets smaller.
4. **Crash days stay rare, ~1-4 in the quarter (≈70%).** Agents don't create the macro shocks and leverage build-ups
   that cause them. One correlated-agent cascade on alts is possible but not a base case (≈20%).
5. **No call on price direction.** Nothing in the agent story says up or down for the next quarter.

## 3. What this means for us

Our one live candidate, `us_capit`, is the kind of edge agents crowd out last: slow (24-hour hold), contrarian
(buys forced selling), and only worth it after costs, which keeps fast competitors out. The main risk is forecast 3:
the bounce is already worth +4.11% at 15 minutes, +2.97% at 30 and +1.93% at 90 (`reviews/timing-2026-10-11.md`).
If agents make it decay faster, our hourly-run delay costs more.

Closed ideas stay closed: agent crowding makes momentum, breakouts and indicator rules (all closed on US venues)
worse, not better. One closed idea has a concrete reopen trigger from this thesis: US-spot wick bounce, if our data
starts showing sharper one-hour crashes (H2 below).

## 4. Plan (top 3 actions, all paper)

1. **Change nothing on the live path.** Keep `us_capit` and the live rule v2 gate as they are. Its coin screen
   (measured Alpaca cost ≤0.50%/side) already favours the majors that forecast 2 says stay liquid.
2. **Re-run the regime check each quarter (next mid-January 2027)** after refreshing the cache
   (`wide_coins.py DIR`, ~9 min, then `agent_regime.py DIR`). Two falsifiable hypotheses:
   * **H1, faster decay:** on crash days in the quarter, us_capit_fast's paper return beats us_capit's by more than
     the backtest gap (~1 pt). If true, the pending ~$5/month always-on box decision for AJ moves up, once the gate
     is met.
   * **H2, sharper crashes:** "worst hour / 24h drop" averages above 0.6 over the next two half-years (2023's level).
     If true, retest US-spot wick bounce at Alpaca cost; otherwise it stays closed.
3. **Watch crash-day costs on alts.** Alpaca paper fills already record cost per side; if alt costs on a crash day
   exceed 0.50%/side, the live rule's coin screen drops them automatically. Nothing to build.

Not in the plan: anything spending real money, faster-than-hourly GitHub jobs, or non-US venues.
