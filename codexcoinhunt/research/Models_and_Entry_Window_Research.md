# Specialized models, entry windows and prior buyer trade proof

Research increment: October 12, 2026 UTC. Investment specification **SLR-0.2 unchanged**. This document separates model recommendations, verified public-chain facts and untested hypotheses. No model was installed, trained, downloaded or called through hosted inference; no money or private key was used.

## Which models should power the project?

For engineering the collectors, research workflow and application, a tool-using LLM remains useful. For the numerical prediction component, the first proposed comparison is a rule/logistic baseline, **CatBoost** and a simple **discrete-time competing-risk survival model**. This is a fit-for-task recommendation, not demonstrated superiority on Resolant returns.

| Candidate | Proposed purpose | Current priority and evidence |
| --- | --- | --- |
| CatBoost | Estimate net-payoff distributions from mixed numeric/categorical buyer, flow, identity, cost and coverage features. | First trained challenger once labels exist. The original ordered-boosting/categorical-feature paper addresses encoding-related leakage [S32]; it does not remove chronological leakage automatically. |
| Competing-risk survival model | Model time to cost-qualified capital recovery versus adverse/zero-recovery events, with incomplete observations separate. | Start with simple discrete-time hazards. DeepHit is a possible later neural implementation of competing risks [S33], not our already trained model. |
| TabPFN v2 | Compare a pretrained tabular predictor on a small, properly labeled dataset. | Secondary benchmark. The January 8, 2025 paper evaluates small tabular datasets [S34]; its results are not crypto-profit evidence. Version 2 weights use attribution-based terms. Current default/newer weights have a noncommercial licence, so do not silently use defaults for this commercial project [S37]. |
| Temporal convolutional network | Learn ordered buyer/flow/depth sequences rather than only static window summaries. | Later, with adequate independent sequences. Generic sequence-modeling evidence supports investigating TCNs [S35], not assuming a market edge. |
| Temporal graph network | Rank coordination patterns across transactions, wallets, creators and classified funding/service nodes. | Later, with labeled relationships and reliable temporal edges [S36]. It cannot certify independent people. Known exchange/service hubs must not be treated as common ownership. |

A reinforcement-learning policy should wait for an execution simulator that reproduces observed fees, liquidity, failures and latency. Optimizing against assumed fills or an incomplete simulator would teach a policy to exploit our accounting omissions. No RL training or return claim was made.

The useful prediction is a distribution of **net recoverable outcomes and exit timing**, under a fixed exit policy. A high probability of a small winning move can still have negative value after fees or occasional full losses. The deterministic paper controller retains sizing, identity, US eligibility, safety, liquidity, reserve and calendar constraints; a model score cannot waive missing required evidence.

## Where might an entry exist?

The current entry hypothesis is verified new demand arriving while prior selling weakens and the price remains near its base, with enough fresh capacity to exit the actual quantity. We still need to distinguish that from busy bots, repeated buyers or sellers continuously replenishing supply. Prior signed-flow tests had rising midpoint prices but negative net paths after costs, so direction alone is insufficient.

`ENTRY-MODEL-0.1`, frozen at **2026-10-12 06:00:00.724255 UTC**, specifies future model/entry comparisons. It is a research plan, not a revised live strategy or a claimed profitable entry rule. Test buyer quality against raw activity counts; audience conversion against signed flow alone; persistent nearby capacity against total displayed depth; and, with actual event data, ask depletion against ask replenishment during completed buying. Compare capital recovery/runner with full liquidation on identical eligible paths. Keep Alpaca book and Solana AMM versions separate; a PumpSwap curve is not a queue of resting human orders.

Required labels include fixed-policy net recovery, failed/zero-recovery exits, time to capital recovery and separate quote-observability/censoring states. Chart peaks, wallet counts, old balances and missing exits are not substitutes. Censoring can be informative; missing data cannot automatically be labeled a rug or discarded to improve a training set.

Split chronologically and group by day/narrative/mint where needed. Historical wallet profiles become usable only at their receipt time. Tune on development data, freeze before later untouched evaluation, and replay complete $50 accounts including all costs, no-trade days and deadlines. Match random, attention and momentum peers using only contemporary eligibility. If a control is unavailable, retain that gap rather than inventing its return. There are currently **zero trustworthy completed SLR net-outcome labels** for choosing a winning model.

## Prior buyer activity: new evidence

The fixed target remains mint `2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM`, pool `Fe7bpDYCs74GqiCUF14HwgUMToPKV1d9mDYVX5BTohFr`, exact WSOL quote `So11111111111111111111111111111111111111112`. This pass examines earlier activity of the same five buy-event users. It is not a new five-buyer opportunity sample.

Before retrieving outcomes, eight uninspected successful signatures per user were selected at evenly spaced chronological ranks from the already saved bounded signature pages, strictly before each target event. **40 fresh finalized `getTransaction` responses** arrived **05:45:26.905815–05:49:22.619986 UTC**, with no request errors. Combined with the previous 20 bodies, the audit examines 60 bodies. Original selection, requests, responses, slot/version metadata and receipt times are retained.

`buyer_trade_history.py` requires an authenticated PumpSwap log/CPI event under the known program, positive swap amounts, the exact event base account's mint/owner, a transaction-signing event user, finalized successful metadata and a strictly pre-target block time. It deduplicates log/CPI copies. A caught failed inner invocation is rejected unless rollback alignment can be proved; none occurred in these sixty bodies. Other venues and proxy users remain unknown. A successful emitted swap can have zero transaction-net balance after another swap/transfer; that does not make its trade disappear, and it is not a profitability calculation.

| Public event user | Verified prior swap events | Other mints traded, lower bound | Fourteen-day activity | Both maturity and three other mints verified |
| --- | ---: | ---: | --- | --- |
| `3uzy6vZMwwgHRrbe86YYFKZj2XaQjWXijqcnV3T6dej4` | 4 | 3 | Yes | Yes |
| `6KBtrzj3Rxew41MD5ydL3AiB7WwTjLtFUKsSEf9yaJfD` | 1 | 1 | Unknown | No verification |
| `8i8WsSj27j998Z7fqjw4JLeBBo7FkAPfqoNKEhYzXttG` | 2 | 1 | Yes | No verification |
| `CSx2gDhH9nw6vqknJkrHVCaWWDDr6sLbRvtJkiUieRFZ` | 2 | 2 | Unknown | No verification |
| `FXh9XcdM38anfSjMjqvPsj7zk2ttzJbwtDCzDhR6YHcn` | 4 | 4 | Unknown | No verification |

**Thirteen deduplicated earlier trades** establish at least three other mints for two users, with only one also establishing fourteen-day activity. These are lower bounds; failure to find three is not proof that a user lacks experience. Repeated same-mint trades do not become different mints. This corrects the earlier balance-only gap without inferring returns, skill, first-ever target participation or funding independence.

Profiles arrived after the original target events and cannot retroactively qualify an entry. No independent funding cluster, complete five-minute buyer window, social gate, safety-qualified fill or whole-account outcome was added. Consequently, there is no new matched random/attention/momentum account comparison, daily opportunity-rate estimate, calendar timeout or reliable doubling evidence. SLR still requires eight qualifying buyer clusters plus all other gates; this sample does not provide them.

The official PumpSwap IDL was independently retrieved **05:49:14.024403 UTC**, SHA-256 `b7d8c57a4d9c4dd0109a9ab893052352333252d4eedced10ac091d4d66cab89b`. It specifies signing `user` and explicit mint/token-account roles for buy, exact-quote buy and sell [S38]. The downloaded JSON and receipt are retained. Model-source documentation was refreshed at **05:54:05.332 UTC**. The source excerpts establish method capabilities and terms, not memecoin performance.

## Reproduction and handoff

```bash
python3 buyer_trade_history.py data/buyer_history_deep_20261012 \
  --additional-rpc data/buyer_trade_history_20261012/rpc.jsonl \
  --output results/new_prior_swap_audit --maximum 8
python3 -m unittest discover -s tests -v
```

This reproduces the already saved evidence without new requests. Choose a fresh output folder. `--collect` instead retrieves a bounded new set and must preserve its own selection plan and receipts. Exact other-mint identities and evidence paths are in `results/prior_swap_audit_20261012/events.jsonl` and its summary, with raw sources under `data/`. Original collection output remains intact.

**107 distinct engineering checks pass**, including seven new prior-trade proof cases. An initial 115-test output included eight imported test functions twice; the duplicate import was corrected and its output retained. Neither count is investment evidence. No model training occurred.

The user's preferred Mac project copy is `~/Projects/CodexCoinHunt`. This cloud runtime cannot access that Mac directory; prepare the complete archive and installer with shared project/handoff notes. Claude chats or unseen local files are not part of this evidence. Northstar's next-finalized-five-minute forecast, V1 control and research-only V2 remain a separate evaluation against persistence; those accuracy results must not be reported as this strategy's profit.

- **S32:** [CatBoost, NeurIPS 2018](https://proceedings.neurips.cc/paper_files/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html).
- **S33:** [DeepHit, AAAI 2018](https://aaai.org/papers/11842-deephit-a-deep-learning-approach-to-survival-analysis-with-competing-risks/).
- **S34:** [TabPFN small-data study, Nature, January 8, 2025](https://www.nature.com/articles/s41586-024-08328-6).
- **S35:** [Temporal convolutional sequence-model study, 2018](https://arxiv.org/abs/1803.01271).
- **S36:** [Temporal Graph Networks, 2020](https://arxiv.org/abs/2006.10637).
- **S37:** [Current TabPFN repository and weight terms](https://github.com/PriorLabs/TabPFN), [v2 classifier licence](https://huggingface.co/Prior-Labs/TabPFN-v2-clf/blob/main/LICENSE.txt), [v2 regressor licence](https://huggingface.co/Prior-Labs/TabPFN-v2-reg/blob/main/LICENSE.txt), checked October 12, 2026.
- **S38:** [Official PumpSwap IDL](https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump_amm.json), checked October 12, 2026.
