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
* **Unobserved exits are dropped.** Each token's window records why it ended
  (`TokenData.end_reason`). An exit after a *recording cut* (recorder
  stopped, long disconnect, tracking limit) has an unknown price, so the
  trade is dropped; the cut is unrelated to the token, so this doesn't bias
  the result. After *idle* untracking the price is known flat. After
  *migration* the last curve price stands in (an approximation; dropping
  those trades would remove the biggest winners).
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

### 3.5 Scam flags and a learned screen as filters (queue item 2)

Each launch is judged on its first 20 s of recorded trades, the way
`--next-launch` does it. Creator history comes only from launches whose
outcome was known by then (a causal `CreatorIndex`). We then buy at +20 s
(1 s latency) and hold. Trades whose exit falls after a recording cut are
dropped (§2). Script: `handoff/experiments/screen_launches.py`.

* **The existing screen does not help trading.** It passes 3.9% of
  launches (139 of 3,523), and those do no better than the rest on test
  launches (180 s hold: −4.7% vs −5.1%; validation: −33% vs −7%).
  Requiring 3+ buyers selects *worse* trades (−9.2% vs −6.1% for all
  launches; valid + test, 180 s).
* **Flags that mark worse trades** (valid + test, 180 s hold, with vs
  without the flag):

| Flag | With | Without |
|---|---|---|
| odd_curve (non-standard curve) | −12.5% (285) | −3.5% (721) |
| concentrated (top-10 ≥ 50%) | −13.7% (78) | −5.4% (928) |
| serial_rugger (creator rugged before) | −12.7% (135) | −5.1% (871) |
| dev_bag (creator holds ≥ 20%) | −8.0% (451) | −4.5% (555) |
| sniped (≥ 25% bought in 5 s) | −7.5% (402) | −5.1% (604) |

  Skipping these cuts losses but leaves the strategy negative. Flags such as
  dev_dumped, copycat and serial_launcher go with *smaller* losses: buying
  after the dump already happened.
* **A learned screen** (LightGBM on the 20 s snapshot: tracker features,
  buyers, buy/sell SOL, rise since launch, causal creator history, risk
  level; trained on train launches, threshold on validation): nothing holds
  up on test launches. One configuration (hold 30 min, take-profit +200%,
  stop-loss −40%, top 10%) looked positive (+4 to +14% on test over five
  seeds). Then exits after recording cuts were dropped and it fell to −1.4%
  (45 trades). Before that it rested on its top three trades. Other positive
  test cells were negative on validation.
* **Long holds have little clean data.** 1,748 of the 3,523 token windows
  end at a recording cut (the second run's disconnects), so few holds of
  10 minutes or more can be scored.

### 3.6 `tartar decide`: buy-or-skip scorers at +20 s (fair comparison)

`tartar/decide.py` builds each launch's state 20 s after it is seen (causal,
as in §3.5). Every scorer picks its threshold on validation launches and is
reported on test launches. The flag rule now picks its flags on **training
launches only**; the hand-picked five in §3.5 were chosen on valid + test,
so they can't be graded fairly there.

| Exit | Buy every launch | `--next-launch` screen | Skip flags that lost on train | LightGBM screen |
|---|---|---|---|---|
| hold 180 s | −5.1% (488) | −4.7% (22) | **−1.8%** (150; CI −5.8 … +4.7%) | −0.6% (27; CI −28 … +30%) |
| hold 60 s | −6.2% (528) | −2.6% (23) | −6.2% (273) | −16.8% (19) |
| hold 600 s, TP +100%, SL −30% | −9.3% (244) | −6.3% (14) | **−1.1%** (63; CI −10.5 … +9.3%) | −5.6% (94) |

Skipping flagged launches roughly halves the loss but is not profitable. The
flags it picks change with the exit rule (always `concentrated`, `sniped` or
`dev_bag`), which says part of the selection is noise.

**TypeSafe Jev** (the user's decision API) plugs in as one more scorer
(`tartar/jev.py`): the launch state goes in with a yes/no question, "will
this beat the ~3.5% round-trip cost?". Scores are cached by mint in
`data/jev-scores.jsonl`, and per-call latency is reported. Its request format
is **unverified** (docs unreachable from this session); see the module
docstring.

### 3.7 TypeSafe Jev (`tartar decide --jev`)

Client: `tartar/jev.py`, now matching docs.typesafe.ai/api (checked
2026-10-08) and the TypeSafe agent skill's guidance. Each launch's numbers
become phrases in code, since Jev is weak with raw numbers. One request per
launch asks five narrow yes/no questions: the direct "buy" question (would
buying now and selling in 3 min beat ~3.5% costs?) plus four judgments about
the name and symbol: `copycat`, `low_effort`, `meme`, `scam_wording`.
Credentials come from the environment's proxy. All 3,523 recorded launches
were asked: median **243 ms** per call (p90 284 ms), ~1.15M input tokens.
Answers are cached in `data/jev-answers.jsonl` (not in git).

| Scorer (test launches) | Hold 180 s | Hold 600 s, TP +100%, SL −30% |
|---|---|---|
| Buy every launch | −5.1% (488) | −9.3% (244) |
| Skip flags that lost on train | −1.8% (150) | −1.1% (63) |
| LightGBM screen | −0.0% (22) | −5.8% (93) |
| **Jev, direct question** (top 6% on validation) | **−9.2%** (41; CI −15.9 … −1.9%) | **−24.2%** (16) |
| LightGBM + Jev's 4 judgments | +5.4% (25; CI −23.7 … +36.8%; validation −8.9%) | +0.8% (55; CI −15 … +17%; validation −8.7%) |

**Calibration over all 3,444 launches with outcomes (hold 180 s):**

* The direct "buy" answer averages 0.20 while 10.5% of launches actually beat
  costs, so it's **overconfident by about 2×**. Its top quintile (0.28–0.50)
  wins more often (16.9% vs 10.5%) but loses more on average (−13.2% mean,
  −16% median). It picks volatile launches, not good ones.
* The name judgments are nearly flat. `low_effort` has the clearest slope
  (P(net > 0) 15.3% in the lowest quintile vs 8.0% in the highest), then
  `copycat` (13.1% vs 9.6%). Every bucket's mean is negative.

**Reading:** Jev doesn't find a tradable edge at the 20 s decision. That's
what TypeSafe's own docs warn about: it's built for common-sense judgments,
not market forecasting, and must be validated in the target domain. The name
judgments carry a weak signal that could matter only if something else
supplies most of the edge.

**Shadow mode** (`"shadow_jev": true` in the policy) now asks Jev every
question about every screened launch and journals the answers without
acting on them. `tartar review` reports each question's rank correlation
with the outcome and P(net > 0) by answer quintile. A replay over the 5,598
recorded launches agrees with the above: Spearman between −0.03 and +0.03
for all five questions (`buy` +0.005). Run it live to test Jev on fresh
launches. That's the only test left that could change this conclusion.

### 3.8 Jev on launch metadata: feature discovery (queue item 8)

Jev had only seen names and symbols, but every launch also links a metadata
file with a description and social links. `tartar/metadata.py` fetches it
(ipfs.io now refuses requests, so IPFS paths go through pump.fun's Pinata
gateway). Metadata was found for 3,042 of 3,523 launches; 295 have no link.
`tartar/jev.py` gained question sets. `METADATA` sends Jev only the name,
symbol, description (≤600 chars) and links, and asks 15 narrow yes/no
questions plus 2 Scores. Each Score is used as two columns, its level and
its uncertainty, following TypeSafe's feature-discovery cookbook. The
questions: explains, news_event, famous_person, famous_link, utility_claim,
ai_theme, animal, spam_text, hype, relaunch, name_matches, copycat,
low_effort, meme, scam_wording, narrative (Score), effort (Score). All
launches were answered in 144 s: median 238 ms per call, ~1.4k input
tokens each. Link features computed in code (description length, which
links exist, launch-tool host) were tested alongside.
Script: `handoff/experiments/jev_metadata_features.py`.

| Features (LightGBM P(net > 0), buy at +20 s) | Hold 180 s: valid AUC | test AUC [90% CI] | test P&L (top 5% on valid) |
|---|---|---|---|
| A numeric launch state | 0.781 | 0.758 [0.697, 0.805] | −0.0% (22 trades) |
| B + link features (code) | 0.785 | **0.767** [0.710, 0.813] | +9.6% (17; CI −24.5 … +49.7%) |
| C + links + Jev answers | 0.790 | 0.740 [0.681, 0.792] | +4.4% (31; CI −21 … +34%) |
| D + Jev answers | 0.784 | 0.724 [0.665, 0.777] | −7.1% (38) |

With hold 600 s, TP +100%, SL −30%, every set loses on test (−4.2% to
−8.3%), and the Jev sets have the lowest test AUC again (0.679 vs 0.691).

* **Jev's best metadata judgment is `explains`** (Spearman +0.083 with net
  return, train + validation). Counting the description's characters in
  code does as well (+0.091). Everything else is within ±0.06.
* **Adding Jev's answers lowers test AUC.** Validation AUC rises slightly
  (0.785 → 0.790) while test falls (0.767 → 0.740): the model fits noise
  in 19 extra columns.
* **AUC ~0.76 doesn't mean profit.** The screens mostly tell launches that
  never trade (a certain −3.5% loss) from launches that do. They don't
  tell winners from losers after costs.

**Scope:** all evaluations here use the tokens `load_trade_tokens` keeps,
which excludes pump.fun V2 launches whose trades the decoder drops (STATUS
queue item 9): 130 of the 3,523 tokens lack create reserves, and every one
of them has recorded trades. So the results describe V1 launches. Rerun
them once V2 decoding lands.

**Conclusion across §3.7–3.8:** with three question designs (the direct
question, name judgments, metadata judgments), Jev adds no predictive value
for which pump.fun launches beat costs. What separates launches here is
order flow and timing, not language. That fits TypeSafe's own positioning:
Jev is built for semantic judgments, and our problem is market
microstructure.

### 3.9 Entry speed in slots: the launch edge is inside the creation slot (queue item 10)

§3.4 measured latency from *receive* times, which arrive a median 1.47 s
after the block. `handoff/experiments/slot_profit.py` redoes it in slots
(~0.266 s each) on the slot-annotated recording `handoff/data/raw-slots`:
1,347 SOL launches, of which 964 have a price at creation (a creator buy).
A buy lands k slots after the create's slot. Its fill is bounded by being
the first or the last transaction in that slot, with the order inside a slot
rebuilt by chaining reserves. It is sold at the end of the slot one hold
later.

**Fees, measured** (`handoff/experiments/fee_sample.py`, 212 pump.fun
trades from 800 recent transactions, read from each TradeEvent): SOL-quoted
trades pay **0.95% protocol + 0.30% creator = 1.25% per side** (150 of
185). 35 paid 0%, probably special cases such as creator first buys.
None paid the 2.5% creator fee seen on some quote-paired curves.
Quote-paired curves vary (0.30–1.95%) and are skipped anyway.

Mean net per trade (0.1 SOL, 1.25%/side, 0.001 SOL tip on the buy), 90% CI by launch:

| Lands at | Hold 10 s | Hold 30 s | Hold 60 s | Hold 180 s |
|---|---|---|---|---|
| creation slot, **first** (bundled with the create) | **+6.8%** [+2.1, +12.1] | **+5.4%** [+0.2, +11.1] | +1.7% | −2.1% |
| creation slot, last (after same-slot snipers) | −5.6% | −6.7% | −10.4% | −14.1% |
| slot +1, first in slot | −5.3% | −6.6% | −10.4% | −14.1% |
| slot +5 | −6.2% | −6.4% | −10.8% | −13.8% |
| slot +20 | −6.2% | −7.8% | −11.9% | −15.0% |
| slot +100 (~27 s) | −5.9% | −5.6% | −9.9% | −10.9% |

Sensitivity (hold 10 s, slot +1 first): no tip −4.3%; **no fee and no
tip −1.8%** [−3.8, +0.1]; 1 SOL size −9.2% (own price impact). The
creation-slot "first" entry is the only positive cell in every variant
(+7.8% without tip, +10.5% without fees).

**Reading:**
* After the creation slot, the average launch drifts **down** even before
  costs: the creator's bundle and same-slot snipers sell into later
  buyers. Speed can't fix that. Landing first in the very next slot, the
  best any outside bot can do, still loses.
* So a private RPC or Jito-speed execution would **not** make launch
  buying profitable. They're worth it for data quality only (complete trade
  streams, lower notification delay).
* The value sits in the creation transaction, i.e. with the creator. We
  will not pursue that: profiting from it means launching tokens and
  dumping on buyers.
* This closes the launch-entry strategy family (§3.2–3.9: buy everything,
  screens, flags, models, Jev, speed). Research should move to other
  entry points (graduated tokens on PumpSwap now that a decoder exists, or
  longer-lived tokens) or other markets.

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
   * Exits, not entries: who to *avoid* and when to get out. Five flags are
     now validated as marking worse trades (§3.5), but avoiding them alone
     does not make launch buying profitable.
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
