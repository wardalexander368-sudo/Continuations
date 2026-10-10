# Pre-registration: open-interest rules on Hyperliquid perps (study design)

Registered 2026-10-10 (~04:00 UTC) by the second TARTAR session. The commit that adds this file
is the registration. It comes before any rule's train, validation or test number was computed.
Before this point, the only things looked at were: which coins OKX covers, how far back its
history goes, and one check of how OKX's daily timestamps line up with Hyperliquid closes. Paper only.

## Why this data
Hyperliquid's public API keeps no open-interest history; the `perps-ctx` Action has recorded
snapshots only since 2026-10-09. OKX's public endpoint keeps daily OI for its USDT swaps from
2024-01-01. Positioning on the big venues moves together, so OKX OI stands in for each coin's
market-wide OI. Of the 234 Hyperliquid perps in our daily data, 150 have an OKX USDT swap
(`fetch_okx_oi.py`).

## Fixed before scoring
* **Harness:** `handoff/experiments/edge-hunt/oi/oi_rules.py`, which reuses the perps-lane
  harness. That harness also provides prices, the universe, the weekly backtest and the bootstrap.
  It is the same one used by D and VMOM.
  * Universe each signal day: 60 consecutive closes, 30-day median volume ≥ $2M, and OKX OI
    covering the lookback.
* **Timing:**
  * A signal on day i uses OKX's OI row for day i-1 at the latest. Rows appear within about 4 hours
    of the day's end, so this leaves one extra day of slack.
  * Prices go up to day i's close.
  * Entry is at the close one day after the signal (`--lag 1`).
* **Costs:** 20 bps per side per unit of turnover, the same as the VMOM registration. Each leg's
  actual Hyperliquid hourly funding is also charged on validation and test. Train carries no
  funding charge, as in the perps lane.
* **Splits:** the same as D and VMOM.
  * Train: 2024-02-05 to 2025-03-31. It starts later than D because OKX history begins 2024-01.
  * Validation: 2025-04-01 to 2025-12-31.
  * Test: 2026-01-01 to 2026-10-09.
* **Rules:** 16 in all, every one counted. The full definitions are in the harness docstring.
  * OIC (6): L-day OI change for L = 3, 7 and 14, both signs. Weekly quintiles, long-short.
  * CONF (2): rank of the L-day return plus rank of the L-day OI change, for L = 7 and 14.
  * DIV (4): rank of the return minus rank of the OI change, for L = 7 and 14, both signs.
  * OIZ (2): log of OI over its 30-day mean, both signs.
  * MAJ (2): on BTC, ETH and SOL daily, when a 1-day OI change is more than 2 standard deviations
    from its 30-day mean:
    * A jump fades the day's price move.
    * A drop follows it.
    * Positions are held for H = 1 or 3 days.
* **Selection:** in each family, the rule with the best mean on train is chosen. It is kept only if
  both its train and validation means are above 0. Test is read only for kept rules, and only once.
  The bootstrap is the harness's: 90% CI, 4-week moving blocks, 4,000 resamples, seed 1.

## What counts as a result
* **Pass (goes to a paper test):** a kept rule whose test mean is above 0 and whose test CI lower
  bound is also above 0, both after costs and funding. If more than one rule passes, the one with
  the best validation mean goes forward.
* **Not independent:**
  * The scorer prints the passing rule's weekly correlation with VMOM-14 and D-14 on the test weeks.
  * Above 0.7, the rule counts as the same bet as the momentum tests already running.
  * Such a rule gets no paper test of its own; it is logged as momentum.
* **Otherwise:** the study is null and is logged as closed.
* **Paper test, if a rule passes:**
  * The rule is frozen in a new spec, with dry twins.
  * It runs on the same 52 signal Mondays as D and VMOM, 2026-10-12 to 2027-10-11.
  * The success rule is VMOM's: mean above 0 and CI lower bound above 0.
  * The forward signal is computed from OKX's live OI if the runner can reach OKX. Otherwise it uses
    Hyperliquid's own OI from `perps-ctx`, and the switch is logged as an addendum before the first
    signal.

## Multiple looks
This lane has now tried 24 perps rules, plus 12 in D and 16 here. A rule that passes after 52 rules
is more likely luck than a single test suggests. That is why the paper test, not this study,
decides whether anything trades.
