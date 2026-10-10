# Pre-registration: copying Hyperliquid accounts with a strong record (edge hunt E2)

Registered 2026-10-10 ~02:00 UTC, **before any account's performance was looked at** (only the leaderboard's
size and volume columns, to set the pool). Paper only, public data, no keys. Code:
`handoff/experiments/edge-hunt/hl_copy/` (`fetch.py`, `select.py`, `copysim.py`); outputs
`handoff/data/edge-hunt/hl-copy/`.

## Question
Hyperliquid publishes every account's fills and P&L. If we pick accounts by their record in one period and
copy their perp positions in a later period, with a realistic delay, taker costs and funding, do we make
money, and more than copying randomly chosen accounts of the same kind?

## Periods
* **A (selection):** 2026-05-01 00:00 .. 2026-08-20 00:00 UTC. Only data up to the end of A picks accounts.
* **B (holdout, scored once):** 2026-08-20 00:00 .. 2026-10-09 00:00 UTC (50 days; Hyperliquid serves 15-minute
  candles back to about 2026-08-18, which sets the length).

## Pool (fixed)
Leaderboard of 2026-10-10 01:40 UTC (47,082 accounts, including 13k with zero value, so blown-up accounts are
not dropped); accounts with all-time volume between $5M and $2B (37,991); a seeded random sample of 1,500
(`pool.json`, seed 20261010). The volume filter uses all-time volume, which includes B; it says an account
traded, not whether it made money, so it is the one place B can leak (noted, accepted).

## Selection rule (period A only)
From Hyperliquid's `portfolio` history (perp P&L, account value), on a weekly grid over A (16 weeks):
1. account value at the start of A between $10k and $50M;
2. perp P&L changed in at least 10 of the 16 weeks;
3. P&L over A > 0;
4. rank by the Sharpe ratio of weekly returns (weekly P&L / account value at the week's start);
5. walking down the ranking, keep an account only if it is **followable**: at most 3,000 fills
   (time-aggregated) between 2026-06-01 and the end of A, and at least 1 fill in that span on a main-dex perp;
6. the first **20** that pass are the selection.

**Placebo:** 60 accounts drawn (seed 20261011) from those passing 1, 2 and 5, whatever their P&L.

## Copy rule (period B)
For each copied account, a follower with its own capital:
* the target's position in each coin is rebuilt from its fills (`startPosition` and size), main-dex perps only;
* at each target fill, the follower's target weight in each coin is the target's position notional over the
  target's account value (interpolated from `portfolio`), i.e. the same leverage; total capped at 3x;
* **delay:** the follower trades at the open of the first 15-minute candle starting at least 2 minutes after
  the target's fill (so 2-17 minutes late);
* it trades a coin only when its weight moves by at least 0.02 (2% of capital);
* **costs:** 0.10% of traded notional per side; **funding** from Hyperliquid's hourly history on the notional held;
* daily returns on the follower's equity, marked at 15-minute closes.
The portfolio is the equal-weight average of the 20 followers' daily returns.

## Criteria (B, scored once)
**Holds** only if all three:
1. mean daily net return > 0 with the 90% block-bootstrap interval (blocks of 5 days) above 0;
2. the mean beats the 90th percentile of 1,000 placebo portfolios (20 drawn at random from the 60 placebo
   accounts, same copy rule);
3. the part not explained by BTC (daily regression, intercept) is > 0.
Also reported, not criteria: costs at 0.20%/side, delay of one more candle, each follower alone.

If it holds, it becomes a paper forward test in the agent (dry perp twins), with a new selection on data up to
its start and this same rule. **Prior: little or none.** 50 days is short; only a large effect can pass.
