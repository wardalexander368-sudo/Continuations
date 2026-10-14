# Public GitHub strategy intake — 2026-10-14

Build requested by Alex: discover public crypto methods, test economics, and bring evidenced improvements into Continuations. This implements bounded daily discovery, inert commit/tree/blob-verified sources, license/prior-work review, trusted offline adapters, matched account controls and a shared capped trial log. Foreign code is never executed. The operating recipe is [github-strategy-intake.md](../github-strategy-intake.md).

The first live batch retained 24 HTTP receipts, 30 unique eligible returned repositories, 4 pinned revisions and 26 deferred candidates. The search pages reported more matches than the pages retained; coverage is incomplete even though the bounded run completed. All four captured revisions have unknown detected licenses, so source reuse remains blocked. The initial narrow seed query returnedzero; the evergreen seed below was separately inspected and explicitly labelled as such.

First source: caktux/pytrader@b45b216dab3db78d6028d85e9a6f80419c22cea0, MIT declared and license bytes inspected. Source SHA256 values:

{
  "LICENSE": "8f71659370c5268d9a1dc962a46232540e8fca63462586d8efaa95aab492a208",
  "README.md": "e5d16a3b9f64e2a54c08eee580a449f2e64d2d0155cff9b2e1544eeca78d31ea",
  "balancer.py": "8bb39c6360750ae37c6805de5d56b1ff383e17da28ef2e916eb53ac171d7f734"
}

The allocation formula is a 50/50 cash/BTC target; daily scheduling, next-hour frozen share intents and current project cost budgets are declared local adaptations. The original limit grid/fee compensation/legacy exchange execution was not reproduced. No return-derived parameter choice was made. The full 2024 calendar window was chosen from input coverage metadata; it is already-explored history.

| Scenario | Strategy net | Starting-allocation buy-and-hold net | Excess | Strategy drawdown | Control drawdown |
|---|---:|---:|---:|---:|---:|
|39bp/side modeled|$516.27|$590.44|−$74.18|16.64%|20.54%|
|78bp/side stress|$499.62|$583.07|−$83.46|16.88%|20.54%|

Cash earns assumedzero in this diagnostic. The buy-and-hold exposure drifts; same initial allocation does not mean identical path risk. The strategy executed 367 modeled sides at base costs; this is one continuous portfolio year, not 367 independent completed trades. Missing actual quotes, liquidity, fills, eligibility, taxes and costs prevent profitability validation. `FAIL_SCREEN` records this adaptation/window's failed return criterion, not a universal rejection of portfolio rebalancing. Positive candidate screens will remain `REVIEW_ONLY` until a new independently evaluated protocol.

First trial 20261014-b7f84180dc30 result SHA256 46e93a0c0d0ff952e6fc86b95a8bef1df809cc77fe4be4a53b5b5dc60baa4f42.
Exported screen-log head after duplicate proof: be69f8f6bdbdcbb9cf18f88285c3189699903ae51ea7bbda7f1f8fb7db675087.
The duplicate invocation returned SKIPPED_IDENTICAL_SCREEN. One later engineering replay added interpreter identity to the controller receipt; its method, costs, data/window and numerical outcomes are identical, and it is not new independent market evidence. Immediate discovery returned SKIPPED_24H_GUARD with 0 requests. Raw sources and full cash/equity receipts are local under CodexCoinHunt, outside public Git history; only summaries, own source/tests and the reviewed spec are included here.

Validation: **591 passed, 1 skipped, 9 subtests passed** in 80.88s on Python 3.12.6 with the existing 47-package environment. This includes142 focused new checks; the final interpreter-provenance addition separately passed all13 controller checks, bringing the new focused total to143. The final GitHub run is recorded in the PR description at its exact pushed head. The first full attempt had 6 setup failures (two missing sparse-checkout config reads and four sandbox-denied localhost fixtures), 585 passed; materialising the unchanged public HEAD config and permitting loopback fixtures resolved them. No test assertion or trading configuration was loosened. Fullsuite was rerun once to resolve those concrete failures.

No existing strategy/source pin, frozen registration, owner paper book, configuration or GitHub workflow changed. The recurring Codex follow-up is updated through its automation tool once the deliverable is ready; it preserves the prior market-evidence work and 4-hour wake schedule, adding a 24-hour-guarded GitHub stage and capped source reviews/screens. Main merge remains with Claude.
