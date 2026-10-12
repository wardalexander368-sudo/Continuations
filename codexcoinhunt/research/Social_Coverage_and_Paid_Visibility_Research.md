# Social coverage and paid-visibility confounder

## Result

The fixed Claudia buyer episode cannot support Second-Look Relay's organic-audience premise. The exact-token DEX Screener paid-order response, received **2026-10-12 11:25:46.130612 UTC**, reports a **10-unit boost** paid at **2026-10-11 21:35:41.416 UTC**, plus approved token-profile and community-takeover orders. Six already retained exact-pair responses show `boosts.active = 10` through **2026-10-12 01:31:44.115 UTC**. The first of the five sampled on-chain buys occurred at **01:42:16 UTC**, 631.885 seconds later. The boost payment preceded it by 14,794.584 seconds, about four hours six minutes.

DEX Screener says boosts temporarily increase token visibility and Trending Score for 12–24 hours and do not guarantee a rank [S45]. The exact active snapshots are stronger evidence than duration arithmetic alone. This establishes a paid-visibility **confounder**. It does not establish that the boost caused buying, identify the purchaser, prove all attention was paid, or show that buying made money.

- paid visibility before sampled buying: **verified**;
- independent organic audience wave: **not verified**;
- paid-only promotion: **not verified**;
- boost-to-buy causality: **not verified**;
- historical SLR eligibility, return or profit: **not promoted**.

## Frozen social-source attempt

`SOCIAL-COVERAGE-0.1` was frozen at **2026-10-12 11:24:42.503671 UTC** before collection. It specified exact-mint, `CLAUDIA Solana`, and `claudia.gallery` searches over a fixed October 5–12 interval, at most two pages per query, URI de-duplication and DID-based authors. The official Lexicon warns that cursors may not traverse the whole result set and hit counts can be rounded or truncated [S46]. A successful bounded search therefore could not prove a complete history.

The first two direct public AppView requests returned **HTTP 403** at **11:25:44.025793** and **11:25:47.290520 UTC**, triggering the frozen two-error stop. The third query was not attempted. The result is zero successful source responses—not zero posts. Prior attention, cooldown, author/copy clusters, new-audience fraction, communities and address consensus remain unknown. No historical eligibility is backfilled from later receipts.

`social_evidence.py` enforces this null distinction. It de-duplicates posts by AT URI; the same DID or exact normalized text forms one descriptive copy cluster. A name-only match can describe a meme family but cannot satisfy exact-address agreement. Community identity and paid status require separate evidence.

## Current DEX context

Three unauthenticated, zero-cost DEX reads succeeded at **11:25:46.111875–11:25:54.295894 UTC**. The exact-token response contained ten exact-mint pair rows and one canonical pool row. Pair rows do not become ten authors, buyers or independent trials. Three project/social URLs were de-duplicated. No direct current pair row showed a positive optional active-boost value, and the target was absent from the bounded top/latest lists at those later receipts. Those absences do not prove a complete unpaid history or contradict earlier time-stamped active observations.

No authenticated account, subscription, paid data, wallet, private key or order endpoint was used. Research data cost was **$0**. The unknown promoter's purchase is a market feature, not an expense charged to this paper account. No fill was added, the target is not established as Alpaca-supported, and source access does not establish US asset/venue/account eligibility.

## Challenger: Promotion Handoff 0.1

The alternative behavioral mechanism is a **paid-to-organic handoff**: promotion may seed awareness, while persistence after a conservatively verified end may carry different information than a raw attention spike. `PROMOTION-HANDOFF-0.1`, frozen **11:24:42.503671 UTC**, excludes Claudia and admits only candidates first observed after that time.

The challenger waits at least 25 hours after the latest exact boost payment, requires no newer exact paid order, and requires two direct snapshots ten minutes apart without a positive active-boost field or target appearance in the top/latest lists. Bounded-list absence alone is insufficient; ambiguous state rejects.

After that transition it retains every SLR-0.2 US, asset, safety, seller, cost, quote, capacity, campaign and confirmation gate. It additionally requires 15 exact-mint author/copy clusters in ten minutes, 60% new audience, two new communities, 80% exact-mint agreement and eight qualified new-to-mint seasoned independent buyer clusters. Entry comes only after a second complete confirmation.

Future comparison arms are SLR-0.2, Promotion Handoff, active-boost attention, plain attention, momentum and matched random eligible tokens. All use the same $50 controller, exits and execution/data/funding/conversion costs. Matching covers age, liquidity, venue, narrative, regime and paid-visibility history. No-trade days, rejected and unsellable tokens, unresolved exits and calendar timeouts remain in the account objective. Existing requirements of 150 closes across three regimes and 30 complete campaigns are unchanged.

This challenger has zero signals, positions, matched outcomes or campaigns. It is not promoted and does not change SLR-0.2 or its configuration hash.

## Implementation and reproduction

`collect_social_evidence.py` is bounded and refuses overwrite. `collect_dex_social_context.py` preserves independent DEX context when social access stops. `collect_dex_paid_order.py` makes one exact-token read. `social_evidence.py` validates identity, clocks, missing coverage, copy clusters, paid orders, exact-pair observations and buyer chronology. Fifteen new adversarial tests bring the suite to **152 distinct engineering checks**; fixtures are not market or profit observations.

```bash
python3 social_evidence.py \
  --data data/social_evidence_20261012 \
  --output results/social_reaudit_new_directory
python3 -m unittest discover -s tests -v
```

Raw request/response bodies, HTTP status, request/receipt clocks and stop conditions are retained under `data/social_evidence_20261012`. Canonical output is in `results/social_evidence_20261012`.

No opportunity-frequency estimate, matched net-account result, recovered USD outcome, closed strategy position or doubled campaign was added. The next data step is authorized continuous exact-mint social coverage, followed by a later untouched cohort whose post, buyer, paid-visibility and exact-size quote clocks exist before decisions.

- **S45:** [DEX Screener Boosting Terms](https://docs.dexscreener.com/privacy/boosting-terms-and-conditions), [Boosting guide](https://docs.dexscreener.com/boosting), and [API reference](https://docs.dexscreener.com/api/reference), checked October 12, 2026.
- **S46:** [Bluesky public API reference](https://docs.bsky.app/docs/api/app-bsky-feed-get-author-feed) and [official `searchPosts` Lexicon](https://github.com/bluesky-social/atproto/blob/main/lexicons/app/bsky/feed/searchPosts.json), checked October 12, 2026.
