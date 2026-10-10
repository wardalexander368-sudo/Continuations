# Pre-registration: trading predictor v3.1 + P(rug) at candle opens

Registered 2026-10-09 18:36 UTC (`SPEC.json`, frozen; models pinned by SHA-256 and by commit).
Script: `handoff/experiments/predictor_strategy.py` (`explore`, `evaluate`).

## The question
Predictor v3.1's "live edge" (+8.0% at 1m, +11.9% at 5m) is a **forecast-accuracy** measure:
how much smaller its point error is than "price stays where it is". It is not a return. This test
asks whether its forecasts, filtered by P(rug), pick candles that make money after real costs.

## Rule (both lines)
At every candle open of a launch at least 20 s old (the launch-entry window is another study's
lane), with the launch's 20 s P(rug) below the cap and the signal above the threshold, buy 0.1 SOL
1 s later on the recorded curve and sell at the candle's close. Fees 1.25%/side, 0.0002 SOL per
transaction, constant-product impact, one position per token, exits after recording cuts
dropped (`profit.run_policy`).

Signals from the installed model's distribution of the candle close: `p_clear` = P(close / price
now − 1 > 3.5%, the round-trip cost floor); `p_up` = P(close > price now); `er_trim` = expected
return with the tails trimmed.

* **Primary:** 5m candles, `p_clear > 0.362`, P(rug) < 0.1.
* **Secondary (reported, not a criterion):** 1m candles, `p_up > 0.47`, P(rug) < 0.1.

**Success:** primary has ≥ 100 trades and its 90% interval (bootstrap by token) is above 0.
Evaluate once at 100 primary trades or on 2026-10-12, whichever is first.

## Development data and why these rules (read this before trusting any result)
Development: 6,054 launches (1m) / 2,619 (5m) from `raw-clever` 13–15 and `raw-clever2` 16 UTC,
recorded after both models' training data ended (P(rug) ≤ 12:30 UTC, predictor ≤ 12:00).
Thresholds were set as quantiles on the earlier 60% of launches; results on the later 40%:

| Candle | Rule | Earlier 60% | Later 40% |
|---|---|---|---|
| 1m | every open | −6.7% (50,101) | −7.1% (25,410) |
| 1m | p_up top 2%, P(rug)<0.1 | −3.9% [−5.5, −2.4] (818) | −3.8% [−6.0, −1.9] (352) |
| 1m | p_clear top 2%, P(rug)<0.1 | −6.4% (801) | −6.7% (408) |
| 1m | er_trim top 2% | −35% (1,002) | −37% (627) |
| 5m | every open | −7.6% (4,554) | −11.3% (2,639) |
| 5m | p_clear top 2%, P(rug)<0.1 | **−8.8%** [−14.5, −3.8] (74) | **+7.4%** [−3.7, +19.3] (31) |
| 5m | p_up top 10%, P(rug)<0.1 | −4.5% (420) | +0.8% [−3.9, +5.8] (130) |

* **1m loses in both halves at every threshold.** The best line (p_up, rug-filtered) loses
  ~4% per trade, i.e. about break-even before costs: the predictor ranks direction but not by
  enough to pay a 2.5% round trip.
* **The trimmed expected return is a harmful signal** at both lengths (§3.2's finding holds for
  v3.1): its top rows are collapsing tokens.
* **P(rug) < 0.1 helps every signal** by a few points, never enough.
* The primary rule was picked because it is the only family positive on the later half. It lost
  on the earlier half, and pooled over both it is about −4%. **The prior expectation is a loss**;
  this forward test exists so that a positive later-half result is not taken on faith.

## Addendum, 2026-10-09 18:50 UTC (before any fresh launch was scored)
The registered script loaded tokens with `load_trade_tokens`' default `min_candles=3`, which drops
every token with fewer than three closed candles (15 minutes at 5m): selection on the outcome, the
pitfall its docstring warns about. Fixed to `min_candles=0` before any evaluation; `SPEC.json` is
unchanged. On the development data the fix leaves the picture as it was (later-40% numbers):
1m p_up top 2%, P(rug)<0.1: −3.6% [−5.9, −1.6] (329); 5m p_clear > ~0.38, P(rug)<0.1:
earlier −6.4% [−9.5, −3.4] (89), later +5.0% [−2.7, +13.0] (23).

## Addendum, 2026-10-09 19:55 UTC: measured real costs (before any fresh launch was scored)
The real-money cost test (STATUS, 19:46–19:49 UTC) found that trading through PumpPortal Lightning
adds a 1% fee per side, which the paper model lacks, and that orders land ~1.4 s after sending. A
fresh-token round trip then costs ~5.5%, not ~3.5%. `SPEC.json` and the success criterion are
unchanged. `evaluate` now also prints each rule at **2.25% per side (1.25% pool + 1% Lightning)
and 1.4 s latency**, on the same decisions. A SUCCESS whose real-cost line has a mean ≤ 0, or an
interval reaching below 0, is not profitable to trade through Lightning.
