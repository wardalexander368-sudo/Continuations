# Pre-registration: spot-perp funding carry on Hyperliquid (edge hunt E3)

Registered 2026-10-10 ~03:55 UTC, after fetching the data (`handoff/data/edge-hunt/spotcarry/data.json.gz`) and
**before computing any return**. Paper only. Code: `handoff/experiments/edge-hunt/spotcarry/` (`fetch.py`, `carry.py`).

## Question
Hyperliquid perps pay funding hourly; at rest it is the 0.01%/8 h interest term (about +11% APR, shorts receive).
Holding the spot token and shorting the same units of the perp removes price risk and collects funding. After both
sides' fees, spreads, basis moves, margin top-ups and the cash parked as margin, does it beat lending USDC (Kamino),
and does switching it on only when funding is high help?

Not tested before: D2 shorted high-funding perps *without* spot (it lost to momentum); A2 was JitoSOL vs the SOL perp
(staking yield plus SOL funding, decaying).

## Universe (fixed)
Hyperliquid spot pairs in USDC with ≥ $1M spot volume on 2026-10-09/10 that map to a perp: PURR, HYPE, UBTC→BTC,
UETH→ETH, USOL→SOL, UPUMP→PUMP, UENA→ENA, UZEC→ZEC (8). Chosen on current volume (liquidity), not on returns.
UBTC/UETH/USOL/UPUMP/UENA/UZEC are bridged tokens (Unit); a depeg is a risk the backtest can't show.

## Costs (fixed, measured from today's books at $1,000 per side)
Per side = taker fee (spot 0.07%, perp 0.045%) + the worse of half-spread-plus-impact buying or selling, per coin
(`*_cost_side` in the data file; e.g. BTC spot 0.071%, perp 0.046%; ENA spot 0.27%; PURR 0.35% / 0.37%).
Entering or leaving a coin pays both legs. Daily margin top-ups pay the spot cost on the cash moved.

## Rule family (chosen on period A)
Each 00:00 UTC, per coin: signal = mean hourly funding over the last L days, annualized. A coin turns **on** when the
signal > E and **off** when it falls below E/2 (always-on ignores the signal).
Grid: L ∈ {1, 3, 7} days × E ∈ {always on, 0%, 15%, 30% APR}: 12 rules.

Book: capital split into 8 equal slots, one per coin. An on slot holds spot worth 2/3 of the slot and shorts the
same units of the perp at 2x (margin 1/3 of the slot). Units are fixed while on; each day the perp's P&L is moved
between margin and spot (top-up cost as above). Funding hourly on the perp notional. **Liquidation:** if a perp's
hourly high is more than 45% above the previous 00:00 close, the slot is liquidated (1.5% of notional penalty) and
counted. Off slots and idle cash earn Kamino USDC supply (`carry_daily.csv`, column `usdc`).

## Periods
A (choose the rule): 2026-03-16 .. 2026-07-01. B (score once): 2026-07-01 .. 2026-10-08 (99 days).
The rule with the highest excess APR over Kamino USDC in A is the one scored in B.

## Criteria (B)
**Holds** only if both: (1) excess return over Kamino USDC, annualized, has its 90% block-bootstrap interval (7-day
blocks) above 0; (2) no liquidation. Reported: each coin alone (always on), each month, gross funding vs costs.
If it holds: a basket paper strategy in the agent (spot leg + perp short, dry twins), registered forward.
**Prior: modest.** The 11% interest floor is known and productized (Ethena and others), so expect a few % APR over
USDC at best, and bridge or venue risk the history doesn't price.
