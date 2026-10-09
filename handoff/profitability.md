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

Where each family stands (2026-10-09):

| Family | Status | Where |
|---|---|---|
| Buying pump.fun launches: baselines, model signals, screens, flags, learned scorers, Jev | closed, loses | §3.2–3.8 |
| Faster entry (slots, private RPC, same-slot sniping) | closed: the creation-slot edge is the creator's own bundle; the best outsider slice is ~+2% only if we out-race 492 bots | §3.9, §3.18 |
| Graduation run-up on the curve | closed, break-even at best | §3.10 |
| Longer holds (10–45 min) on screened launches | closed, loses | §3.14 |
| Copy-trading wallets whose buys paid off | closed, loses | §3.15 |
| Graduated tokens in their first hour on PumpSwap (fees 1.20–1.25%/side, §3.13) | closed, loses (pre-registered, 264 pools) | §3.16 |
| Established memecoins: dip buying | rolling forward test, scored 2026-10-30 | §3.11 |
| Predictor v3.1 candle calls + P(rug), held to the candle close (1m, 5m) | closed, loses (pre-registered, 108 trades) | §3.20 |
| Smarter exits, regime gating and cheaper execution on launch buys | best: skip flags + TP +100%, Jupiter, 0.02 SOL: −2.9% [−4.1, −1.6]; still loses | §3.21 |
| Picking movers from early flow, wallets, holders, curve shape, the creator, the name | movers predictable (AUC 0.88) but they collapse; small creator buys beat buy-all by ~2–4 points, still −2.2% on test | §3.22 |
| SOL-USD with Jev (the user's jevtrader) | sealed test ends 2026-10-23; on-chain costs ≈ 0.5 bps/fill | §3.12, `handoff/jevtrader.md` |

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
* **Unobserved exits are dropped.** (Caution, see §3.10: a token's window
  length depends on its fate, so this is only near-unbiased for short
  holds. For long holds, replay through `FastLoop` and exclude by recorder
  downtime.) Each token's window records why it ended
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

### 3.10 The graduation run-up: a false edge, and two biases worth knowing (queue item 11a)

Rule: buy when a curve's real SOL raised first reaches X, and sell when it
reaches E = 80 SOL (into the last buyers before completion at ~85) or after
30 min. A curve that completes stops trading, so a buy landing after
completion fails, and a position still open is sold on PumpSwap. That price
isn't recorded yet, so it's valued at the final curve price less a 0/10/25%
haircut.

**What first looked like an edge** (`graduation_runup.py` on
`load_trade_tokens` curves): 75 → 80 SOL +5.8% per trade [+3.9, +7.8],
positive in both halves. 60 → 80: +16%. **It was two biases:**

1. **Fast graduations were dropped.** The loader kept tokens with ≥3
   closed 1-min candles. Half of all run-ups reach 75 SOL within a minute
   of launch, and those tokens vanished, along with the buys that would
   have failed because the curve completed first. (`load_trade_tokens`
   now takes `min_candles=0` for trading studies.)
2. **Length-biased censoring.** A token's recorded window ends at
   graduation (short, rarely cut by a recording interruption) or after 20
   idle minutes (long, often cut). Skipping trades whose window was cut,
   even when decided at entry, therefore skips rugs far more than wins.
   The tokens it dropped averaged **−33%**: real rugs from 74 SOL raised
   down to 0, observed before the cut.

**Fair evaluation** (`graduation_runup_replay.py`): every signal traded
through `FastLoop` itself on the full raw stream, which keeps recording
across short disconnects. A signal is excluded only when the *recorder*
was down during its holding period (event gaps > 30 s; three multi-hour
gaps between recording runs). That rule depends on the recorder, never on
the token. Mean net per signal (a failed buy costs one transaction), with
earlier/later halves:

| Rule | Signals | 1 s, haircut 0% | 1 s, 10% | 3 s, 10% | 3 s, 25% |
|---|---|---|---|---|---|
| 50 → 80 SOL | 96–97 | −7.6% | −9.2% | −9.6% | −12.5% |
| 60 → 80 SOL | 76 | −5.3% | −6.7% | −8.1% | −10.7% |
| 70 → 80 SOL | 59 | −0.6% | −2.1% | −3.4% | −6.0% |
| 75 → 80 SOL | 53 | +2.3% [+1.2, +3.6] | +1.3% | **+0.5%** [−0.6, +1.6] | −0.5% |

About half of the 75-SOL signals are missed (the curve completes within
the latency). At a realistic delay (recorded times are already ~1.5 s
after the block) 75 → 80 is **break-even**. Entering earlier is worse:
more of those run-ups end in rugs. **No edge.** The fast loop keeps the
`runup_*` policy fields (off by default; completed curves cancel buys,
post-graduation exits take `graduation_haircut`) for any future live test,
but a live paper run isn't worth a slot: the expected result is ~0.

**Lesson for every study here:** never decide inclusion with a window
whose length depends on the token's fate. Replay the full stream through
`FastLoop` and exclude only for recorder downtime. Earlier sections' short
holds (≤ 3 min after entry at +20 s) are only mildly exposed, because
migrations within minutes are rare there. **Checked:** buying every launch
at +20 s and holding 180 s, replayed through `FastLoop` on the full stream
of `handoff/data/raw` (recorder-downtime exclusion only), gives **−6.94%**
per trade [−9.10, −4.52] over 2,257 trades (halves −7.9% / −6.0%; win
11.4%). That's in line with, slightly worse than, the window-based −5.1% to
−7.0%, so §3.2–3.9 stand.

### 3.11 Established memecoins on public price data (queue item 11b)

Liquid Solana pools days to months old, from GeckoTerminal 5-minute OHLCV
(`handoff/experiments/established_collect.py`, `established_rules.py`).
Costs: 0.5% swap fee per side (believed then to be above PumpSwap's ~0.30%; **it isn't**:
memecoin pools pay 0.30–1.25% per side by market cap, see §3.13), price impact from
each pool's liquidity (size / (liquidity/2) per side; $200 trades), and
$0.05 per transaction. Fixed grid: **momentum** (1 h or 15 min return
above +5/10/20%), **dip** (below −5/10/20%), **breakout** (new 1/4/24 h
high), held 15 min / 1 h / 4 h. Entry at the next bar's open. The best
configuration per family is chosen on the first 60% of the period and
reported once on the last 40%. **Survivorship control:** today's liquid
pools are survivors, so every trade is compared with entering the same pool
at every bar of the same period with the same hold ("excess"). Intervals
bootstrap over pools. Data: `handoff/data/established/` (tar of both
collections).

**Harness check:** on 6 sets of random-walk pools (40 each, fat-tailed,
survivor-like drift), 2 of 18 family tests came out "significant", about
11% against the nominal 5%. A single positive is not evidence.

**Mixed universe** (50 pools ranked by volume; mostly majors, wrapped
assets, DeFi tokens and tokenized stocks), test period Oct 4–9:

| Family (config chosen on train) | Test trades | Mean net | Excess over random entries |
|---|---|---|---|
| dip: 1 h return < −5%, hold 4 h | 139 (28 pools) | +3.5% [−0.4, +8.4] | **+2.1%** [+0.3, +4.3] |
| momentum: 1 h return > +5%, hold 4 h | 134 | +0.5% | −0.9% |
| breakout: 4 h high, hold 4 h | 417 | −1.5% | −0.9% |

The dip result is stable across fees (excess unchanged at 0.3% or 1%),
test halves (+2.7% / +2.1%) and neighboring settings (all positive). But
**without its top 3 of 28 pools the excess is +0.3%**, and selecting pools
by today's liquidity favors exactly the dips that recovered.

**Memecoins only** (12 PumpSwap pools, history before registration):
the same dip rule averages **+7.4%** per trade [+3.3, +11.6], but only
**+0.7% [−1.5, +2.9] above random entries**. The high mean is survivorship
(these coins rose over the period), not timing.

**Pre-registered forward test** (`handoff/preregistration/dip-rolling/`):
the dip rule (fixed above, from the first study's training split), its
costs and a mechanical memecoin universe rule are registered before any
out-of-sample data exists. Established memecoins with real volume are
scarce (~12 qualify at a time), so cohorts are added over time. Any
session: run `python3 handoff/experiments/established_cohort.py` about
once a day and commit the new cohort at once. Score with
`python3 handoff/experiments/established_prereg_eval.py` at ≥ 200 trades
or 21 days after cohort 1 (2026-10-30). Success = excess > 0 with its 90%
interval above 0, AND mean net > 0. Expected: probably not, given the
memecoin in-sample excess of +0.7%. Two earlier registration drafts (v1:
mixed universe; v2: a stablecoin pair slipped through the filter) were
superseded before any out-of-sample data existed; both stay in git.

**Reading:** no reliable edge in simple rules on established memecoins.
The one candidate (dip buying) is weak, concentrated, and mostly explained
by survivorship. The forward test is the only thing that could change that.

### 3.12 SOL-USD on-chain: about 0.5 bps per fill (for the user's jevtrader)

The user's `jevtrader` (see `handoff/jevtrader.md`) measures Jev on Coinbase SOL-USD, whose
retail taker fee is 90 bps per fill (~181 bps round trip). Jupiter quotes for a $1,000 round trip
(USDC → SOL → USDC at the same moment), 33 samples on 2026-10-09: **median 0.96 bps round trip
including $0.05 per transaction, i.e. ~0.5 bps per fill**, routed through Solana's proprietary
market makers. On-chain prices sit within ~1–3 bps of Coinbase's book. Quotes, not fills, but **quote decay
is small**: re-quoting 1–5 s later moves a $1,000 quote only as much as the market moved (|decay|
p90 ≈ 1–2.5 bps, mean ≈ 0, no 50 bps slippage failures); filling at the later quote costs
≈ 0.4 bps per fill (157 samples, 04:10–05:30 UTC; `jevtrader.md`). For
any strategy on SOL itself, the on-chain venue is **~180× cheaper** than retail CEX taker fees,
which moves the profitability bar from "beat 1.8%" to "beat ~0.01–0.05%".

**Second window and quote decay** (predictor session, 2026-10-09 04:33–05:33 UTC; `sol_dex_costs.py summary|decay-summary`;
its samples were not committed, only these numbers). All figures are quotes, not
executed fills; MEV, failed transactions and the USDC/USD basis are still not priced.

- **$1,000, 120 samples:** 0.46 bps per fill (median, p90 0.70) including $0.05 per transaction.
  That matches the 03:37 window (0.48), so cost is stable across the night hours sampled.
- **$10,000, 71 samples:** 0.15 bps per fill (p90 0.33). Larger size is cheaper per dollar: the
  network fee is spread out and impact stays tiny across 2–3 market makers.
- **Quote decay, 178 samples:** each sample re-takes the same $1,000 buy and sell quotes 1, 2 and
  4 s later.

  | | 1 s | 2 s | 4 s |
  |---|---|---|---|
  | Median \|change\| (bps) | 0.12 | 0.26 | 0.52 |
  | p90 \|change\| (bps) | 0.58 | 1.27 | 2.08 |
  | Drift-free mean, (buy+sell)/2 (bps) | +0.01 ± 0.03 | +0.00 ± 0.03 | +0.01 ± 0.03 |

  The drift-free mean cancels the market's move. It is zero, so **quotes do not move against the
  trader**: latency adds noise (~0.3 bps typical at 2 s), not expected cost.
- **Realistic per-fill cost at ~2 s latency:** ~0.5 bps expected, with ~1.3 bps at p90. That is
  below jevtrader's smallest non-zero fee column (2 bps) and ~180× below Coinbase's 90 bps.
- The research session's decay run (04:10–05:30 UTC, 1/2/5 s, with Coinbase's book; above and
  `jevtrader.md`) agrees: no expected cost beyond the market's own move.
- **European morning** (clever session, 06:43–09:55 UTC, 371 samples with 1/2/5 s re-quotes):
  0.46 bps per fill (p90 0.67), filling at the later quote 0.41–0.43 bps, no slippage failures.
  Cost does not depend on the hour sampled so far (`jevtrader.md`).
- **European afternoon and US hours** (clever session, 10:56–15:55 UTC, 549 samples): 0.47 bps per
  fill (p90 0.68), later-quote fills 0.37–0.41 bps; quotes move about twice as much as in the
  morning but with no drift. **Every hour sampled (03:37–15:55 UTC) gives ~0.5 bps per fill.**
- **Still open:** real fills
  (a funded wallet; not done, paper only).

### 3.13 PumpSwap fees: 1.20–1.25% per side on young tokens, tiered by market cap

Measured 2026-10-09 (`handoff/experiments/pumpswap_fees.py`) two ways that agree: from the
fee basis points PumpSwap writes into every BuyEvent/SellEvent (fetched over RPC), and from
recorded swaps (`sol`, `paid` and post-trade reserves give LP and protocol + creator
separately; 10,283 swaps ≥ 0.05 SOL in `handoff/data/raw-pumpswap`). Every trade pays
**LP 0.20% + protocol 0.05% + a coin-creator fee that falls as market cap rises**, except
right after graduation:

| market cap (SOL) | LP + protocol + creator | per side |
|---|---|---|
| below ~420 (a fresh graduate sits at ~400) | 0.02 + 0.93 + 0.30 | **1.25%** |
| ~420–1,200 | 0.20 + 0.05 + 0.95 | **1.20%** |
| ~1,100–4,400 | 0.20 + 0.05 + 0.80–0.85 | 1.05–1.10% |
| ~4,400–6,800 | 0.20 + 0.05 + 0.75 | 1.00% |
| ~12,000 / ~18,000 | creator 0.70 / 0.65 | 0.95% / 0.90% |
| ~28,000 / ~33,000 | creator 0.55 / 0.50 | 0.80% / 0.75% |
| ~47,000 | creator 0.35 | 0.60% |
| ~500,000 | creator 0.05 | 0.30% |

(Tier edges overlap a little in the recorded data; the program's own market-cap measure
differs slightly from price × 1e9.) A handful of wallets trade fee-free (protocol accounts;
~28–48 swaps each in 20 minutes); ignore them.

**Consequences:**
* Trading a token right after graduation costs about what the bonding curve did:
  **~2.5% round trip** plus impact. Graduation doesn't buy cheaper execution until a token
  reaches thousands of SOL in market cap. The graduation-exit haircut (§3.10) and any
  PumpSwap study must charge these fees, not 0.30%.
* The dip pre-registration (§3.11) charged 0.5% per side, believing PumpSwap took ~0.30%.
  Cohort 1's pools pay 0.30–1.20%, mean 0.85%. Its primary metric (excess over random
  entries in the same pool) is barely affected, since both sides of the comparison pay the
  same fee; its "mean net > 0" criterion is optimistic by ~0.7 points per round trip. An
  addendum (written before any out-of-sample result existed) adds a secondary line at
  measured fees; SPEC.json is unchanged (`handoff/preregistration/dip-rolling/ADDENDUM-2026-10-09-fees.md`).
* §3.11's in-sample memecoin numbers used 0.5%/side as well; at real fees the memecoin
  mean net falls by ~0.7 points per trade, and the excess is unchanged.

### 3.14 Longer holds on screened launches: no edge (queue item 3)

`handoff/experiments/long_holds.py`: the fast loop itself replayed on the full raw stream of
every recording before 2026-10-09 02:00 (`handoff/data/raw`, `raw-slots`, `raw-slots-processed`,
`raw-pumpswap`; 9,591 SOL launches), excluding a trade only when the recorder was down during
it. Grid: screen 20 / 120 / 600 s × hold 10 / 20 / 30 / 45 min × {the live skip flags; the same
plus ≥ 20 distinct buyers by the screen}. Holds end inside the recorder's 60-minute tracking
window. Rule chosen on the first 60% of launches, reported once on the rest:

| | Trades | Mean net | 90% CI | Median | Win |
|---|---|---|---|---|---|
| validation, best of 24 (screen 20 s, hold 20 min, flags) | 695 | −5.3% | −8.8 … −2.0% | −3.5% | 4.0% |
| **test, same rule** | 102 | **−12.5%** | −17.6 … −7.6% | −3.7% | 3.9% |
| validation range over the 12 "flags" rules | 260–1,032 | −5.3 … −9.5% | all CIs below 0 | −3.5% | 0.5–4.6% |
| validation, "+ ≥ 20 buyers" rules | 21–57 | −36 … −67% | all below 0 | | |

**Reading:**
* The median trade is the cost round trip on a token that never trades again (−3.5%: 2 × 1.25%
  fee, 0.4% network on 0.1 SOL, ~0.6% impact). After 20 s–10 min most screened launches are
  already dead, and the few that move don't pay for the rest (win rate ~1–5%).
* Waiting longer before buying doesn't help: a 2- or 10-minute screen is worse than 20 s.
* Launches with ≥ 20 distinct buyers early are the worst by far (−35% to −67% per trade): heavy
  early buying marks pump-and-dumps. A good *skip* signal, but skipping doesn't make the rest
  profitable.
* Caveats: `tartar record` stops following a token after 10 idle minutes (the fast loop after
  20), so a token that revives after a quiet spell is valued at its stale price; revivals are
  rare, but they'd be winners. Old recordings value graduation exits at the final curve price
  less 10% (positions still open at graduation were very rare here: every test exit was at the
  horizon); since 2026-10-09 the fast loop sells them on the recorded PumpSwap pool instead.

Together with §3.2–3.10 this closes buying pump.fun launches at any entry delay up to 10
minutes and any hold up to 45 minutes.

### 3.15 Copy-trading wallets whose buys paid off: no edge

`handoff/experiments/copytrade.py`: follow a wallet's buy 1 s after it was received (about 2.5 s
after its block), on the curve at the recorded state, at 1.25% per side; exit after 30 s / 2 min /
10 min, or 1 s after the wallet's own next sell ("mirror", capped at 10 min). A wallet's score is
the mean net return of *following* its buys in a learning period (shrunk: sum / (n + 5)), so it
measures only the skill a follower can capture. One entry per token, on the first qualifying buy.
Learning / validation / test = consecutive 50 / 25 / 25% of buys by time; recorder-downtime
exclusion only; the creator's own buys aren't followed. Data: every recording before 10-09 02:00
(9,320 SOL launches, 207,178 buys; 1,098 wallets bought ≥ 10 distinct launches).

| Validation | 30 s | 2 min | 10 min | mirror |
|---|---|---|---|---|
| follow every buy | −8.0% | −14.0% | −29.2% | −13.4% |
| best of 12 wallet filters | −3.7% | −2.2% [−11.6, +6.8] | −13.6% | −7.3% |

**Test, the rule chosen on validation** (2 min, ≥ 10 learning buys, score > +10%, wallets
re-learned through validation): **−21.0% per trade [−31.0, −10.5]**, 109 trades, win 22%.

**Reading:** a buy is followed by reversion. Copying any buy 2.5 s late loses 4–5 points beyond
the ~3.5% cost floor at 30 s, and more the longer it's held. Wallets whose buys were good to
follow earlier are less bad to follow later, but never good. Their edge is being early (often
bundled with the launch), which a follower can't copy. No forward test is worth running: the best
in-sample rule already loses.

### 3.16 Trading graduated tokens on PumpSwap: no edge (queue 11a, pre-registered)

Evaluated once on 2026-10-09 at ~12:00 UTC, as `handoff/preregistration/pumpswap-graduated/SPEC.md`
fixed it before any return was computed: `pumpswap_study.py handoff/data/raw-eager
handoff/data/raw-clever --show-test` (plus the two sensitivity runs). Data: **264 graduated SOL
pools** (69 from `raw-eager` 04:06–06:00, 195 from `raw-clever` 06:23–11:59; every pool had a
recorded swap), committed in `382e827` before the run. Validation = the first 158 pools by
graduation time, test = the last 106. Fills on the recorded reserves, PumpSwap fee by market-cap
tier (§3.13), 0.1 SOL per entry, 0.0002 SOL per transaction, 1 s latency. Outputs:
`handoff/preregistration/pumpswap-graduated/results/`.

| Family | Rule chosen on validation | Validation mean | **Test** (trades) | Test mean [90% CI] | Bonferroni bound | Verdict |
|---|---|---|---|---|---|---|
| grad | buy 5 s after graduation, hold 60 s | −14.9% | 106 | **−19.6%** [−26.7, −12.4] | −28.8% | no edge |
| mom | at 15 min, if up > 50%, hold 5 min | +18.3% [+1.2, +34.8] | 14 | **−22.5%** [−45.1, −1.3] | −53.1% | no edge |
| dip | at 15 min, if down > 60%, hold 60 min | −37.1% | 26 | **−38.1%** [−49.9, −26.5] | −54.6% | no edge |
| active | at 30 min, if ≥ 50 swaps in 5 min, hold 60 s | −3.8% | 27 | **−3.4%** [−9.7, +1.9] | −12.2% | no edge |
| reference: every pool, 30 s after graduation, hold 5 min | | | 257 | −25.2% [−31.0, −19.1] | | |

Sensitivity (reported, not criteria): with 3 s latency every family stays negative (the
`active` choice changes to 15 min / 5 min hold: −14.5%); with 1 SOL per entry the test means
are −24.9 / −27.5 / −36.7 / −4.9%. No family passes in any run.

**Reading:**
* Fresh graduates fall. Buying every pool 30 s after graduation and holding 5 minutes loses a
  quarter of the stake on average (median −17%); holding an hour after a 5 s entry loses ~60% on
  validation. The insiders who held the curve sell into the new pool, and the 1.25% fee per side
  (§3.13) comes on top.
* The only rule that came near zero is `active` (a pool still busy half an hour after
  graduation, held for one minute): −3.4% on test, about the cost of the round trip. Surviving
  pools stop falling but don't pay for their fees.
* Momentum is the cautionary case: +18.3% on 23 validation trades with an interval above zero,
  then −22.5% on 14 test trades. Small validation samples on these pools produce exactly this.
* As the SPEC expected: graduation doesn't change the economics of the bonding curve.

Together with §3.2–3.15 this closes trading pump.fun tokens at launch, on the curve, at
graduation, and in their first hour on PumpSwap, with simple rules on public data.

### 3.18 Same-slot launch entry: the creation-slot edge belongs to the creator's bundle

§3.9 found one profitable launch buy: right after the create, inside its slot. This asks
whether an outsider can get it, on every slot-annotated recording (17,098 SOL launches with a
creator buy: `raw-slots`, `raw-slots-processed`, `raw-eager`, `raw-clever`, `raw-clever2`,
`raw-v3`, each mint counted once). Scripts: `handoff/experiments/same_slot_entry.py` (slot
order rebuilt by reserve chaining, 100% of launches; paper entry by position; realized results
of real same-slot buyers), `same_slot_blocks.py` (200 creation blocks from the public RPC: index
in block, fee payer, priority fee, Jito tip), `same_slot_who.py` (wallet classes, block
positions, entry scenarios). Outputs in `handoff/data/same-slot/` (`entry-report.txt`,
`who-report.txt`, `launches.jsonl.gz`, `blocks.jsonl`).

**Who buys in the creation slot.** 35% of launches have an outside (non-creator) buy there.
Two kinds of wallet:
* **One-off wallets** (seen in 1–4 launches; round, repeated sizes like 1.0 / 0.988 / 1.2 SOL):
  in the blocks, **83% of their buys sit in an unbroken run right after the create** (median
  2 transactions later). That is the creator's bundle. They take the first place after the
  create in 80% of their launches and realize **+51.8%** per position before tips (median +7%).
* **Repeat snipers** (492 wallets, each in ≥ 5 launches of ≥ 5 different creators): bots
  reacting to creates. Only 26% of their buys touch the bundle run; median **132 transactions
  later in the same block**, so they react within the slot (shred-level feeds). They pay little
  to land (priority median 0.0003 SOL, p90 0.004; a Jito tip on 15% of transactions): the race
  is won by infrastructure, not by bidding. Realized **+3.7%** per position before tips
  (median −2.5%, 39% win; 289 of 492 wallets positive).

**Where the §3.9 edge comes from.** Entering first after the create (hold 10 s, 0.1 SOL)
pays only when others buy after you in the same slot: **−3.4%** on launches nobody else buys
in that slot (11,132), **+83%** when one-off (bundle) wallets follow, +14% when only bots
follow. The profit is the creator's own bundle buying after you, and the bundle is atomic and
placed right after the create, so an outsider cannot stand in front of it.

**What an outsider can reach** (paper, curve fee 1.25%/side, network fees, sold at the end of
the slot `hold` later; 90% CI by launch):

| Entry | 0.1 SOL, priority 0.0003 | 0.1 SOL, priority 0.007 | 1 SOL, priority 0.0003 |
|---|---|---|---|
| A first after the create (inside the creator's bundle: unreachable) | +12.0% [+10.7, +13.4] | +5.3% | +5.7% |
| B first among the bots, after the bundle (beat all 492 every time) | **+2.0%** [+1.3, +2.7] | −4.7% | −3.1% |
| C a random place among the slot's bots (one more competitor) | **−1.2%** [−1.8, −0.6] | −8.0% | −6.1% |
| D after every creation-slot trade | −3.3% | −10.0% | −7.9% |

(Hold 10 s shown; 30 s and 60 s are the same or worse; `who-report.txt`.)

**Reading:**
* The only positive reachable cell, B, needs our buy to land ahead of every existing bot
  on every contested launch, at 0.1 SOL and a small priority fee. It turns negative with a
  p90-sized priority fee or at 1 SOL. As one more bot of median speed (C), it loses.
* Our current feed sees a create a median 1.15–1.47 s after its block (~5 slots, §3.9 / queue
  item 5), so today we land around D or later. Reaching B at all means raw shreds
  (e.g. Helius Shred Delivery, $1,000 per month per IP, or a Jito ShredStream proxy if still
  offered), a co-located server and staked or Jito landing paths; then winning the race
  against the 492 bots already there, which this data cannot show we would.
* Repeat snipers as a group made +12.4% SOL-weighted before tips (12,744 SOL in) but the median
  bot position loses: the winnings sit in a few fast, well-tuned wallets.
* **Closes the same-slot entry question:** the creation-slot edge is the creator's bundle;
  an outsider's best reachable slice is thin, needs a race we have no evidence of winning, and
  costs ~$1k/month before the first trade. Not worth building. (Being the creator, i.e.
  launching tokens and bundling our own buys, is how the one-off wallets earn; it profits from
  later buyers and is out of scope.)

### 3.19 Execution routes: Jupiter with our own key cuts ~2 points per round trip

The real CATE round trips (STATUS REAL MONEY entry, 2026-10-09 19:46 UTC) cost **−3.07%** at
0.01 SOL: PumpPortal Lightning's fee ≈ 2.0 (1% per side), network ≈ 0.22, pool fee + impact
≈ 0.85. Lightning is the largest piece. This compares the cheaper routes.

**Method** (`handoff/experiments/execution_routes.py`, data `handoff/data/exec-routes/routes.jsonl`,
2026-10-09 ~20:00 UTC). For one 0.1 SOL buy, each route builds its real transaction for a stand-in
wallet; the public RPC *simulates* it (signatures off). Nothing is signed or sent, and no key is
used. From the simulation's inner instructions: tokens received, and every lamport leaving the
wallet for the swap and its fees (rent and network fee excluded). Six tokens: CATE (large,
Meteora/Whirlpool liquidity), three recently graduated PumpSwap tokens, two bonding-curve tokens.

**Tokens per SOL against the best route** (0 = best; negative = worse):

| Token | PumpPortal Local | Jupiter Swap API (Metis) | Jupiter Ultra |
|---|---|---|---|
| CATE (routed via Raydium CLMM / Meteora) | −55 bps | **0** | −12 |
| PumpSwap token 1 | −50 | **0** | −9 |
| PumpSwap token 2 | −50 | **0** | −8 |
| PumpSwap token 3 | −5 (fee account not seen) | **0** | −1 (OKX router) |
| curve token 1 | −49 | **0** | −10 |
| curve token 2 | −50 | **0** | −10 |

What each charges on top of the pool, read from the transactions:
* **PumpPortal Local** (`/api/trade-local`, unsigned transaction we sign): a 0.5% transfer to a
  PumpPortal fee account inside its transaction, as its fees page says. Same pool otherwise
  (PumpSwap or the curve directly).
* **Jupiter Swap API v1 (Metis)**: no fee (`platformFee` null); the pool's own fees only (on the
  curve the same 0.95% protocol + 0.30% creator, read from pump's fee program). It finds a
  better pool when one exists (CATE).
* **Jupiter Ultra**: `feeBps` 10 (0.1%), sometimes offset by better routing.
* **Our own pump.fun / PumpSwap instructions**: no route fee, the same pool cost as Metis on
  pump tokens (Metis sends a single `Pump.fun` / `Pump.fun Amm` hop there).
* **Lightning** (`/api/trade`): 1%, measured in the real fills.

**Round trip, estimated from the measured CATE costs** (pool + impact 0.85%, network 0.22% at
0.01 SOL, ~0.02% at 0.1 SOL):

| Route | CATE 0.01 SOL | CATE 0.1 SOL | Fresh curve token (2 × 1.25% + impact 0.6%) |
|---|---|---|---|
| Lightning (measured) | −3.07% | ~−2.9% | ~−5.5% |
| PumpPortal Local | ~−2.1% | ~−1.9% | ~−4.5% |
| Jupiter Ultra | ~−1.3% | ~−1.1% | ~−3.3% |
| **Jupiter Metis, own key** | **~−1.1%** | **~−0.9%** | **~−3.1%** |

**Rent.** With our own key we can close a token account after selling and get its rent back
(0.0015 SOL for a Token-2022 pump token: 15% of a 0.01 SOL trade, 1.5% of 0.1 SOL). Lightning
cannot, which is why 0.0015 SOL is still parked in the CATE account. The PumpSwap/pump
per-wallet account (0.0013 SOL) is paid once per wallet on every route.

**Landing and reliability.** Lightning landed 1.37–1.43 s from send to confirmed, first try
(2 round trips). With our own key we send it ourselves. The public RPC's `sendTransaction` with
a priority fee is the free default. Helius Sender (free, no account needed; SWQoS-only tier at a
0.000005 SOL minimum tip, or 0.001 SOL for every path) is the fast path if needed. Our open
strategies are not latency-bound (§3.9, §3.18 closed the races), so landing speed matters less
than cost. API response time (16 calls each): Jupiter quote + swap median 0.12 s, p90 0.16 s;
PumpPortal Local median 0.17 s. The keyless `api.jup.ag` host rate-limits at 0.5 requests/s (8
of 16 calls got 429). Keyless `lite-api.jup.ag` still works (16/16), but Jupiter is phasing it
out, so use a free API key (1 request/s). One Metis quote failed once ("Missing token program")
on a curve token; Ultra routed it.

**What each needs.**
* Jupiter Metis or Ultra, or Local: the wallet's **secret key as an environment secret**
  (`TARTAR_WALLET_KEY`, never in chat or the repo; a fresh wallet with a small balance is safest),
  and for Jupiter a free `JUPITER_API_KEY` (optional while lite-api lasts).
* Our own instructions: the same key, plus instruction builders for the curve and PumpSwap that
  track pump.fun's program changes (V2 curves, the fee program and the volume accumulators have
  all changed in the last months).

**Build effort.** Jupiter: done. `handoff/experiments/jupiter_fills.py` (`dry` simulates with no
key; `roundtrip --real` signs with `TARTAR_WALLET_KEY`, sends, confirms, closes the empty token
account, logs in `real_fills.py`'s format; same caps: ≤ 0.02 SOL per buy, ≤ 5 trips). Signing
and the close transaction were checked offline with a throwaway key; nothing was sent. Own
instructions: ~1–2 days plus upkeep, for no fee saving over Metis. They would only save the
~0.12 s API call.

**Recommendation: Jupiter Swap API (Metis), signed with our own key.** It removes the 1%/side
Lightning fee (≈ 2 points per round trip, 3.07% → ~1.1% on CATE at 0.01 SOL), lets us reclaim
token-account rent, routes to the best pool, costs nothing to use, and is built. To verify it:
two 0.01 SOL round trips on CATE with `jupiter_fills.py roundtrip --real`, by the wallet's
holder, once the user adds the key. For every rule, the cost bar falls by ~2 points: fresh
curve tokens ~3.1% per round trip, large pools ~1%.

### 3.20 Trading the predictor's candle calls with P(rug): no edge (pre-registered)

Predictor v3.1's "live edge" (+8.0% at 1m, +11.9% at 5m) is a forecast-accuracy measure (point
error against "the price stays put"), not a return. Test: at every candle open of a launch at
least 20 s old, buy when a signal from the model's distribution of the close is high and the
launch's 20 s P(rug) is low; sell at the candle's close (`handoff/experiments/predictor_strategy.py`;
signals `p_clear` = P(close clears the 3.5% cost floor), `p_up`, trimmed expected return).

* **Development** (6,336 launches, `raw-clever` 13–15 + `raw-clever2` 16, unseen by both models;
  thresholds on the earlier 60%): 1m loses at every threshold in both halves (best: `p_up` top 2%,
  P(rug) < 0.1, −3.6% [−5.9, −1.6] on the later 40%), about break-even *before* costs. The trimmed
  expected return is harmful at both lengths (top rows −35% to −90%, collapsing tokens, as in §3.2).
  P(rug) < 0.1 helps every signal by a few points. 5m was noisy (−6.4% earlier, +5.0% later on 23).
* **Pre-registered forward test** (`handoff/preregistration/predictor-strategy/`, registered 18:36
  UTC, scored once on 2,800+ fresh launches): **5m `p_clear` > 0.362, P(rug) < 0.1: −5.15%
  [−11.85, +2.52] on 108 trades; −7.07% at measured Lightning costs. Not confirmed.** The 1m line:
  −4.92% [−6.63, −3.37] on 590.
* **Reading:** the predictor calls direction and flat-vs-move well, but the candles it likes do not
  move enough to pay a 2.5–5.5% round trip. Holding to one candle's close is the horizon the model
  is built for; longer holds are already closed (§3.14).

### 3.21 The agent's trading skills: exits, gating and execution (trading-skills audit)

The user asked (2026-10-09 20:30 UTC) for improvements to the agent's trading skills. Entry
families are closed (§3.2–3.20), so this audit changes the other parts of a trade: **how it
exits**, **when it trades at all** (market regime), and **how it executes** (route, size, network
fee). Data: every screened SOL launch on the five newest recordings (`raw-eager`, `raw-clever`,
`raw-clever2`, `raw-v3`, `raw-pred`; one copy per mint), **22,363 launches**: dev = created before
16:00 UTC 10-09 (15,068), test = 16:00–20:20 UTC (7,295; after the installed P(rug) model's
training data). State at +20 s is the fast loop's own (`_screens` replay, flags included); fills on
the recorded reserves after 1 s, as `profit.round_trip`. A trade counts only if the recording
covers its whole holding period up to the rule's max hold (decided at entry, never by when it
exited). Scripts: `handoff/experiments/exit_study.py` (`extract`, `run`), `regime_gate.py`,
`exit_tp_grid.py`; outputs `handoff/data/exit-study/`.

*Correction (21:55 UTC):* the first version of this section (20:45) kept a trade when its exit
fell inside the recording, so near the end of each recording early take-profits were kept and
full-length losers dropped (§3.10's lesson). That flattered the 30-minute TP rules by ~1 point.
All numbers below are from the fixed scripts.

**1. The ceiling: two thirds of launches never offer a sale above cost.** An *oracle* exit (the
best sale in the next 30 minutes, chosen with hindsight) still has a median of −3.45% on every
launch: only 33% of launches ever trade above our break-even after a +20 s entry. Its mean is
+44% on test, all from the few that run. Risk filters remove exactly those:

| Entry filter (test, paper costs) | Oracle exit mean | Oracle win | Current exit (hold 180 s) | Best exit chosen on dev |
|---|---|---|---|---|
| every launch | +44.1% | 33% | −5.0% | −4.6% (hold 60 s, TP +30%, trail 10%, dev-sell, dump) |
| live skip flags (`concentrated`, `sniped`, `dev_bag`) | +15.6% | 14% | −6.8% | **−3.7%** (TP +100%) |
| P(rug) < 0.1 | +14.2% | 21% | −6.3% | −4.6% |
| flags + P(rug) < 0.1 | **+1.8%** | 7% | −3.9% | −3.8% (hold 180 s) |

(0.1 SOL, 1.25% per side, 0.0002 SOL per transaction, as the paper model.) Filtering for safety
cuts losses by removing the launches that move: with flags and P(rug) < 0.1 even perfect hindsight
makes only +1.8%. No exit rule can rescue an entry whose oracle is near zero.

**2. Exits: take profit at +100%, don't stop out.** 360 causal rules (max hold 60 s–30 min ×
trailing stop 10–50% × TP +30%/+100% × sell on the creator's first sell × sell after a single sell
≥ 10%/25% of the curve's SOL), chosen on dev. On the live skip-flag policy a **TP of +100%** wins
on dev and holds on test: −3.7% vs −6.8% for the current fixed 180 s hold, a 3-point gain. Once
the TP is on, the max hold barely matters (180 s, 10 min and 30 min within 0.3 points on dev).
Every stop-loss and trailing stop makes that policy worse or no better (SL −50% costs up to 1
point; `tp-grid-live-flags.txt`): curve prices dip and recover often, and a stop sells the dip. TP
levels from +50% to +150% are within ~0.5 points. On unfiltered launches the best rules are tight
(trail 10%, TP +30%, 60 s) and gain only ~0.4 points over a 60 s hold. Selling on the creator's
first sell or on a large dump never adds more than 0.1 point. The fast loop's default exit is now
TP +100%, 30 min, no stop.

**3. Execution: route, size and the real network fee add ~1 point.** The paper model charges
0.0002 SOL per transaction; the real fills paid 0.000011 (STATUS real-money entry). With the
Jupiter route (no route fee, §3.19), the measured network fee and 0.02 SOL per entry (less
impact on ~30-SOL curves), the round-trip floor falls from −3.52% to −2.72%. The live skip-flag
policy with TP +100% (hold 180 s, chosen on dev at these costs) then makes **−2.88% [−4.11, −1.60]**
on test (2,588 trades, win 7.4%; dev −2.3%). At Lightning's 1% per side it is −5.3%, and Lightning
also strands 0.0015 SOL of token-account rent per new token (1.5 points at 0.1 SOL, 7.5 at 0.02),
which no row here charges: **fresh launches through Lightning cost ~7% per round trip at 0.1 SOL.**

**4. Market regime: no signal.** Three causal gates at each decision (mean net of the last 30
minutes' completed launch trades, the share of them that ever cleared cost, launches in the last
10 minutes): rank correlation with the trade's result −0.02 to +0.01 on dev; gates chosen on dev
don't hold on test (e.g. −4.1% vs −3.9% ungated) or never fire there.

**Reading:**
* The agent's exit skill had room: a fixed hold is the wrong shape for a payoff whose value sits
  in a few runners. TP +100% with no stop is worth ~3 points per trade on the live policy, and
  execution ~1 more. Together they take the best launch policy from −6.8% to −2.9%, **still a
  loss**.
* The remaining gap is the round-trip floor on launches that never trade again. Something new has
  to pick the ~30% of launches that move *without* the risk filters removing them (§3.22).
* For any launch rule: TP +100%, no stop-loss; size small; charge the real route's fee and the
  rent; Jupiter with our own key, never Lightning, for fresh tokens.

### 3.22 Picking the launches that move: early-flow features (trading-skills thread)

§3.21 left one question: can anything pick the ~33% of launches that ever trade above cost,
without the risk filters removing them? Same launches and split as §3.21 (dev before 16:00 UTC
10-09, test after), entry at +20 s or +60 s, the paper policy's default exit (TP +100%, 30 min,
no stop) at Jupiter costs (1.25% per side, 0.02 SOL, 0.000011 SOL per transaction). Script:
`handoff/experiments/mover_study.py` (features from the full trade paths, including each buyer's
history across every recording, causal); outputs `handoff/data/exit-study/mover-groups.txt`,
`dev-buy-rule.txt`.

Feature groups, each alone and all together: **flow** (buys, sells, SOL in and out, buyers,
sellers, time since the last trade), **buyers and wallets** (buy sizes, round sizes, share of
first-2 s SOL, share of fresh wallets / repeat bots (≥ 20 earlier launches) / in-between),
**holders and growth** (holders, buyers in each half of the window), **curve shape** (real SOL at
¼, ½, ¾ and all of the window, peak, drawdown, time of peak), **dev** (the creator's buys and
sells, earlier launches and rugs), **name**. LightGBM trained on the first 70% of dev, a
top-fraction threshold chosen on the last 30% of dev, test once; two targets: the trade's net,
and "mover" (any sale in 30 min above cost).

**Movers are easy to predict and lose money.** Mover AUC is 0.84–0.90 on test from flow, curve
shape or holder growth alone, the same on dev and test. But the launches most likely to move are
the ones about to collapse: their top 5–10% lose −3% to −18% on test with medians of −50% to −66%.
"Will it move" is "is it volatile", and on the curve the downside is the bigger side. Models
trained on the trade's net pick quiet launches that lose about the cost floor. No group, at
either entry time, has a positive validation pick that holds on test (best: all features, +20 s,
top 2%: valid +3.4%, test +1.4% [−6.2, +9.6] on 74 trades; buy-every-launch is −4.4% on test).

**The one consistent signal: the creator's own buy size.** Launches where the creator bought
nothing lose the floor (−3.3%); the loss grows steadily with the creator's buy above 0.3 SOL
(−6% at 0.3–0.7, −12% at 2–3.5, −21% above 6 SOL on dev: big creator buys are the bundles that
dump, §3.18). A small creator buy (0.01–0.3 SOL) with no creator sale by +20 s beats buying every
launch in **every one of the 16 hours** (+0.8 to +9.0 points). But it doesn't pay: the grid of 60
variants (`dev_buy_rule.py`: buy-size band × entry +20/+60 s × live flags × minimum buyers)
picks creator buy 0.01–0.15 SOL + live flags at +20 s, +1.7% [−1.3, +4.6] on 977 dev trades, and
it makes **−2.2% [−6.7, +2.4]** on 468 test trades (+2.2 points over buying every launch).

**Reading:** the early trades separate *volatile* launches from dead ones very well, and
separate *good* from *bad* only a little (small creator buys, the live flags). Neither is enough to
clear a ~2.7% round trip. Not pre-registered: nothing positive on held-out launches. A forward
test of the creator-buy rule would be expected to lose ~2%.

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
