# Pre-registration: does E1's revenue signal hold on other buyback / revenue-share tokens? (E1b)

Registered 2026-10-09 ~23:10 UTC, **before any revenue value or price of these tokens was read**
(only which DefiLlama series and Hyperliquid perps exist, and their date ranges, were checked).
This is a fresh check of E1 (`handoff/preregistration/pumpflow/SPEC.md`), not more searching:
the token list, the rule, the costs and the criteria are fixed here. Script to be written after
this commit: `handoff/experiments/edge-hunt/pumpflow/revflow.py`. Paper only.

## Tokens (fixed)
Protocols whose revenue funds buybacks of, or distributions to, their token, with a Hyperliquid
perp, and the DefiLlama `summary/fees/<slug>?dataType=dailyRevenue` series used:

| Perp | DefiLlama slug | Mechanism (as publicly described) |
|---|---|---|
| HYPE | `hyperliquid` | Assistance Fund buys HYPE with most trading fees |
| JUP | `jupiter` | buybacks with part of fees |
| AAVE | `aave` | ongoing buyback program |
| DYDX | `dydx` | share of net revenue to buybacks |
| GMX | `gmx` | fees to buybacks / stakers |
| CAKE | `pancakeswap` | buyback-and-burn |
| SKY | `sky` | Smart Burn Engine buybacks |
| BANANA | `banana-gun` | revenue share and buybacks |

RAY (Raydium) has no Hyperliquid perp and is excluded; PUMP is E1 itself and is excluded.
No token is added or dropped after this commit.

## Rule (identical to E1's backtest)
* Only complete UTC days (the fetch day is dropped). `surprise_d = log(rev_d / mean(rev_{d-7..d-1}))`,
  skipped when any of those is ≤ 0 or missing.
* Position on the token's perp from day *d*'s close to day *d+1*'s close: +1 if `surprise_d > 0`,
  −1 otherwise. 0.10% per side per unit of turnover, Hyperliquid daily funding of day *d+1*
  charged (longs pay positive rates). Daily candles and funding from Hyperliquid.
* Period: every day from 2024-03-01 (or the later of the series' start and the perp's first
  candle + 8 days) to 2026-10-08.
* Timing part: net − mean(position) × (return − funding), day by day (removes the share of the
  result that comes from simply being long more often than short in a trend).

## Criteria (fixed)
* **Family test, does the mechanism generalize?** Equal-weight portfolio of the 8 tokens' daily
  net (average over the tokens with a position that day). **Holds** if its timing part's 90%
  interval (block bootstrap, blocks of 10 days, 5,000 draws, seed 0) is above 0.
* **Per token:** passes if its mean net and its timing part both have 90% intervals above 0.
  With 8 tokens about 0.4 false passes are expected by chance, so a single pass when the family
  test fails is reported but is **not** sent to a forward test.
* **Next step:** if the family test holds, every passing token gets a forward test exactly like
  E1's (first-published DefiLlama day, hourly Action), registered as an addendum to this file
  before its window opens. If the family test fails, E1 stays a PUMP-only lead and this is
  written up as evidence against the general mechanism.

**Prior expectation:** weaker than PUMP's or none. PUMP's buybacks are large relative to its
market cap and daily; for most of these tokens they are smaller or weekly, so the result is
expected to be a family test near zero.
