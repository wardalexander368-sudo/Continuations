# Profitability: does TARTAR make money after costs?

Written 2026-10-08 (~22:30 UTC) by the session that took over after the
predictor handoff (`candle-prediction-agent.md`). The role of this work:
**judge every model and strategy by net SOL after real costs, on launches the
model never saw**, and improve that number.

## 1. Short answer

**No strategy tested is profitable at realistic costs on this data.** Every
one that looked good on the validation launches lost on the later (test)
launches, or its 90% interval spans zero. Treat the dashboard's "predicted
close" and confidence as measurement, not as trade signals.

## 2. How it is measured (`tartar/profit.py`, `tartar profit`)

* **Fills on the real curve.** A buy of `size` SOL at the reserves of the last
  recorded trade before *decision + latency*: constant product, fee taken from
  the input. A sell at the exit time's reserves, fee taken from the output.
  Entry and exit each pay their own price impact on the market's reserves
  (slightly conservative: our buy's support of the price is ignored).
* **Default costs:** 0.1 SOL per entry, **1.25% fee per side** (pump.fun
  bonding curve, protocol + creator; check the current schedule), 0.0002 SOL
  per transaction (base + priority), **1.0 s** from decision to execution.
  All are flags: `--size --fee --network --latency`.
* **Exits:** fixed hold, optional take-profit / stop-loss checked on every
  recorded trade, then executed after the latency.
* **One position per token at a time.** Signals that fire while a position is
  open are skipped.
* **Splits:** launches ordered by time; thresholds are chosen on validation
  (70–85%), results reported on test (latest 15%). 90% intervals bootstrap
  over tokens, because trades on one token are correlated.
* `Dataset.time` (new) records the moment each row's prediction is made, so
  any row-level signal can be traded.

## 3. Results (v1 data: 3,523 launches, ~2.7 h, public RPC)

### 3.1 Round-trip cost floor

The median trade returns **−3.5%**: 2 × 1.25% fees + 2 × 0.0002 SOL network
(0.4% of 0.1 SOL) + price impact ~0.3% per side at 30–40 virtual SOL. A
strategy needs an average gross move above ~3.5% just to break even.

### 3.2 Baselines and the v1 model as a signal (`tartar profit`)

| Strategy | Exit | Test trades | Mean net | 90% CI | Win |
|---|---|---|---|---|---|
| Buy every launch when seen | 30 s | 525 | −3.6% | −8.6 … +2.6% | 19.6% |
| Buy every launch when seen | 60 s | 525 | −4.3% | −10.6 … +2.5% | 17.7% |
| Buy every launch when seen | 180 s | 525 | −5.2% | −12.2 … +2.4% | 16.0% |
| v1 expected return in top 0.5% | 60 s | 38 | **−43.3%** | −66.7 … −14.6% | 7.9% |
| v1 P(up) in top 0.5% | 60 s | 16 | −7.0% | −25.8 … +9.4% | 31.2% |
| Trade every decision row | 60 s | 2,594 | −5.9% | −7.2 … −4.7% | 4.7% |

**The v1 model's expected return is a harmful signal.** Rows it rates most
bullish (predicted +13% or more) realize −3% gross on average; they are
tokens with huge σ that are collapsing, where the distribution's fat upper
tail inflates the mean. The model is calibrated for direction and bands, not
for the size of expected moves.

### 3.3 Models trained on net trade outcomes (scratch experiment)

LightGBM on the same 57 features, labels = net return of the round trip
decided at each row (Huber regression and P(net > 0)), early stopping on
validation, threshold chosen on validation, one position per token:

| Exit | Huber model, test | Binary model, test |
|---|---|---|
| hold 30 s | −3.7% (26 trades) | −16.8% (25) |
| hold 60 s | −3.0% (52) | −14.8% (22) |
| hold 180 s | −3.4% (37) | −9.6% (18) |
| hold 180 s, TP +50%, SL −20% | −3.5% (34) | −4.8% (25) |
| hold 600 s, TP +100%, SL −30% | −3.9% (29) | +7.9% (31; CI −12 … +30%; −12% on validation) |

Only 3–5% of decision rows are profitable at all after costs, and nothing
separates them reliably on later launches. The Huber model learns to pick
quiet rows that lose about the cost floor; the classifier's picks are noise.

### 3.4 Latency is the edge (launch sniping, valid + test, 1,048 launches)

| Latency | Fee/side | Hold 15 s | Hold 30 s | Hold 60 s |
|---|---|---|---|---|
| 0 s (price at the create event) | 1.25% | **+8.0%** [+4.6, +11.1] | +9.0% | +9.6% |
| 0.4 s | 1.25% | −3.3% | −1.6% | −1.7% |
| 1.0 s | 1.25% | −2.9% | −1.5% | −2.5% |
| 1.0 s | 0% | −0.4% | +1.0% | 0.0% |

Buying at the price right after the creator's first buy is very profitable;
being 0.4 s later (about one slot) is not. That profit belongs to bots that
land in the same block as the launch (often the creator's own bundle). Our
timestamps are when the public RPC delivered the event, already after that,
so the 0-latency row is **not achievable** with this setup. Lower fees alone
do not rescue any strategy at realistic latency.

## 4. What this means for the plan

1. **Don't trade the current predictions.** The confidence is honest about
   direction, but direction calls are mostly "flat", and the moves they get
   right are smaller than the costs.
2. **Data is the binding constraint.** 2.7 h of lossy public-RPC data
   (median 93% capture) is too little to find an edge that survives ~3.5%
   costs, and the trade sequence and timing is distorted. Needs:
   * network access to `api.mainnet-beta.solana.com` (blocked by this
     session's network policy as of 22:00 UTC; the proxy answers 403), or
     better a private RPC (Helius / QuickNode / Triton) in `SOLANA_RPC_WS`;
   * 24 h+ of recording, then rerun `tartar profit` and the net-model
     experiment.
3. **Where an edge could plausibly exist** (ranked; each must clear the cost
   floor on later launches in `tartar profit` before any money is used):
   * Exits, not entries: who to *avoid* (scam/rug signals as a filter on
     launch buys) and when to get out. The scam flags are still unvalidated.
   * Longer horizons (10–90 min) on tokens that already passed screening and
     have organic flow, where the fee is small relative to moves.
   * Graduation (≈85 SOL raised → PumpSwap): needs a PumpSwap decoder and
     data past migration, which the recorder doesn't follow yet.
   * Same-block sniping is a latency arms race (Jito bundles, co-located
     validators). Not realistic from here.
4. **Never** paper over this with leaked or in-sample numbers: thresholds
   come from validation, results from test, intervals by token.

## 5. Reproduce

```bash
cp handoff/data/raw/*.gz data/raw/        # the v1 snapshot
tartar profit                             # baselines + v1-as-signal table (~30 s)
tartar profit --latency 0.4 --fee 0.5     # sensitivity
pytest tests/test_profit.py               # simulator tests
```
