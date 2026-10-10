# Pre-registration: trading liquidation-sized hourly wicks on Hyperliquid perps (paper, 52 weeks)

Registered 2026-10-10 (~16:40 UTC) by the trading-skills thread (round 4, intraday timing). The commit
adding this file is the registration; the window starts 2026-10-12. Paper only. Scored from
Hyperliquid's own hourly candles by `handoff/experiments/edge-hunt/perps/wick_forward.py`, which
the `perps-ctx` Action keeps appending (`--update`) because HL's API only keeps ~5,000 bars.

## Where it came from (exploratory)
`experiments/edge-hunt/perps/intraday.py` (edge-hunt §J): 27 intraday rules on 20 liquid perp coins,
Binance hourly 2020-01..2026-09 as a stand-in for HL, 8.5 bps per side (HL taker 4.5 + ~4 bps to fill
$5k, the Jev cost session's book measurement). The rule chosen on train in its family, WICK BOUNCE
Z=6 H=4: train +53 bp/trade [−39, +164] (399), validation 2024 +79 [+0.5, +156] (128), **test
2025-01..2026-09 +80 [−20, +177] (125)**; at maker-only costs (1.5 bps) test +94 [−6, +191]. Weak
points: the train CI spans zero; neighbours are mixed (Z=4 fails, Z=5–8 mostly positive in test);
trades cluster on a few crash days; 2026-03..09 alone was −141 bp (24 trades). On the same window
HL's own candles give −143 bp (28 trades), so the Binance stand-in matches HL. Prior: low.

## Rule
For each of ADA APT ARB AVAX BCH BNB BTC DOGE DOT ETH INJ LINK LTC NEAR OP SEI SOL SUI TIA XRP:
sigma = std (ddof 0) of the previous 168 hourly close-to-close returns (all present). When an hour's
lower wick (min(open, close) − low) / open is at least 6 sigma, go long at that hour's close; when
its upper wick (high − max(open, close)) / open is, go short (both: no trade). Hold 4 hours, exit
at that close. One position per coin at a time. Cost 8.5 bps per side; funding ignored.

## Window and statistic
Entries from 2026-10-12 to 2027-10-11 (52 weeks, ~125 trades expected). Mean return per trade with
a 90% bootstrap CI over entry days (10,000 resamples, seed 1).

## Success
Mean > 0 AND the CI's lower bound > 0, from `wick_forward.py --final` after 2027-10-12. Anything
else is a FAIL. Every constant in `wick_forward.py` is fixed; later mistakes get a dated addendum
that leaves the primary statistic as registered.
