# US paper evidence review — 2026-10-13 UTC

CAPIT remains the strongest existing US candidate, without demonstrated live profitability. Claude has completed
the historical random-entry baseline and paper cost/gate reporting; do not rebuild plan E1/E2. The useful next
step is to protect the validity of that evidence before interpreting readiness or execution savings.

Reviewed baseline: `39bdddd875b4141fec70127a4c3d489e9bd831a4` (2026-10-13 00:42 UTC). This is an offline
review, with synthetic reproductions below. No live account, keys, fees ledger or orders were accessed. At this
snapshot no `autotrade/alpaca_fills.jsonl` is tracked; REPORT says **0/3 crash days, 0/8 trades, not met**.

## 1. Reproduced gate defects — implementation belongs to the live-rule owner

`tartar/autotrade/live_gate.py` counts sell rows without validating a unique completed buy/sell pair, a forward
window or finite numeric inputs. All five malformed cohorts below produce `met=true`, the same result as the
complete finite control. The three-position control correctly fails until its sell records are repeated.

| Priority | Reproduced input | Observed | Required interpretation |
|---|---|---|---|
| 1 | All return, cost and gap values NaN | 9 trades, 3 days, met | Unknown values must not satisfy return/cost bounds |
| 1 | Entry/exit gap fields absent | 9 trades, 3 days, met | Missing gaps must not become zero gaps |
| 2 | Three real positions, each sell row counted three times | 9 trades, 3 days, met | Three distinct completed trades, below the eight-trade minimum |
| 2 | Nine sells, no buys | 9 trades, 3 days, met | No verified paired round trips or entry days |
| 3 | Nine complete pairs from September 2026 | 9 trades, 3 days, met | Outside the adopted forward window beginning 2026-10-12 |

These are input-integrity failures, not evidence that the actual journal contains these records. Python's JSON
parser accepts NaN, although NaN is not a valid JSON number. The current reporting function can therefore report
paper readiness from unusable evidence. It still cannot enable live orders: funding, a live route and AJ's
separate authorization remain required.

Suggested owner fix: validate finite timestamps, returns, costs and both gaps; match buy/sell strategy, symbol
and position; count unique completed pairs; exclude pre-window entries explicitly; surface rejected/ambiguous
records and keep readiness unmet when their interpretation is unresolved. Add these cases as regression tests
alongside the existing valid-cohort test. Preserve the adopted thresholds and frozen registration.

Run from the reviewed repository root using its Python environment; no files or orders are touched:

```sh
PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
"""Synthetic input probe; never reads a paper book or sends an order."""
import copy
import json
from datetime import datetime, timezone
from tartar.autotrade import live_gate as lg

START = datetime(2026, 10, 12, tzinfo=timezone.utc).timestamp()

def trip(position, day, start=START):
    at = start + day * 86400
    common = {"position": position, "strategy": lg.GATE_STRATEGY, "symbol": "BTC/USD"}
    return [{**common, "event": "buy", "at": at, "paper_at": at},
            {**common, "event": "sell", "at": at + 86400,
             "measured_side_cost": 0.004, "alpaca_net_return": 0.02,
             "entry_gap_bps": 10.0, "exit_gap_bps": 10.0}]

valid = [row for d in range(3) for k in range(3) for row in trip(f"p{d}-{k}", d)]
three = [row for d in range(3) for row in trip(f"p{d}", d)]
duplicated = three + [copy.deepcopy(row) for row in three if row["event"] == "sell"] * 2
orphans = [row for row in valid if row["event"] == "sell"]
old = [row for d in range(3) for k in range(3) for row in trip(f"old{d}-{k}", d, START - 30 * 86400)]
nonfinite = copy.deepcopy(valid)
missing = copy.deepcopy(valid)
for row in nonfinite:
    if row["event"] == "sell":
        for field in ("measured_side_cost", "alpaca_net_return", "entry_gap_bps", "exit_gap_bps"):
            row[field] = float("nan")
for row in missing:
    if row["event"] == "sell":
        row.pop("entry_gap_bps")
        row.pop("exit_gap_bps")

for name, rows in [("valid", valid), ("only_three_unique_trips", three),
                   ("duplicated_sells", duplicated), ("orphan_sells", orphans),
                   ("pre_window", old), ("nonfinite", nonfinite), ("missing_gaps", missing)]:
    g = lg.gate(rows)
    print(json.dumps({"case": name, "met": g["met"], "trades": g["trades"],
                      "crash_days": g["crash_days"], "unmet": g["unmet"]}, allow_nan=False))
PY
```

Observed at the reviewed commit:

```jsonl
{"case": "valid", "met": true, "trades": 9, "crash_days": 3, "unmet": []}
{"case": "only_three_unique_trips", "met": false, "trades": 3, "crash_days": 3, "unmet": ["3/3 crash days, 3/8 trades"]}
{"case": "duplicated_sells", "met": true, "trades": 9, "crash_days": 3, "unmet": []}
{"case": "orphan_sells", "met": true, "trades": 9, "crash_days": 3, "unmet": []}
{"case": "pre_window", "met": true, "trades": 9, "crash_days": 3, "unmet": []}
{"case": "nonfinite", "met": true, "trades": 9, "crash_days": 3, "unmet": []}
{"case": "missing_gaps", "met": true, "trades": 9, "crash_days": 3, "unmet": []}
```

## 2. Paper cost is a proxy, not a measured live execution cost

Alpaca describes quote-based simulated fills and excludes market impact, latency slippage and passive-order
queue position. Its general specification also ignores displayed quantity and randomizes some partial fills;
the page uses equity-oriented NBBO terminology and gives no separate crypto engine guarantee. These limits
support using paper for route correctness and simulated execution checks, not live depth or maker-fill proof.
[Official paper specification](https://docs.alpaca.markets/us/docs/paper-trading).

The adapter currently calculates `measured_side_cost = assumed_fee + (entry_gap_bps + exit_gap_bps)/20000`.
The gaps compare an Alpaca simulated fill with the strategy's Coinbase paper reference. **Inference from that
equation:** this combines venue basis and reference-time price movement with spread and simulation behavior;
it does not isolate live slippage. The fee is configured, not reconciled to a fee activity. Keep the existing
field for compatibility, but interpret and label it as a **paper cost proxy** when assessing readiness.

Alpaca's published lowest-volume crypto tier remains 0.15% maker and 0.25% taker. Marketable limits pay taker.
Fees reduce the received asset, and fee activities may post at day-end. Absence of same-day fee activities is
not zero fees. [Official crypto fees](https://docs.alpaca.markets/us/docs/crypto-fees).

Calculated fee-only economics, assuming both legs fill at unchanged prices and both fees use that tier:

| Two-leg method | Gross return needed to break even | Net return at zero gross move |
|---|---:|---:|
| Taker/taker | 0.501881% | −0.499375% |
| Maker/maker | 0.300676% | −0.299775% |

Formula: break-even gross return is `1 / ((1-f_buy)*(1-f_sell)) - 1`. At zero gross move the maker advantage
is **0.199600 percentage points per round trip**, before differences in fill price, latency or missed trades.
This is a hurdle, not a strategy return. It agrees with the approximate 0.2-point saving already noted in
`overall-2026-10-11.md`.

Alpaca documents market, limit and stop-limit crypto orders; a limit order alone does not establish maker
treatment. [Crypto order documentation](https://docs.alpaca.markets/us/docs/crypto-orders). Coinbase's Post Only
option rejects an order that would execute immediately; it guarantees maker classification if filled, not a
fill. [Official order types](https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/order-types).
Coinbase now directs exact account rates and tier criteria to its signed-in fee page. Existing registered
0.91% taker and 0.50% maker counterfactuals remain historical assumptions, not newly account-verified rates.
[Official Advanced fees](https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees).

An eventual passive-window/fallback comparison must score every eligible signal, including no fills, partial
fills, fallback taker fees and delayed bounces. Compare net dollars per signal and deployed capital. Comparing
only filled maker orders selects favorable survivors. No new route, collector or strategy is proposed here.

## 3. What the completed random-entry analysis supports

Claude's recorded local-control CAPIT excess is +4.85%/trade [90% CI +0.98, +8.73] on the study coins and
+6.00% [−0.17, +11.79] on the extra coins. The corresponding extra-coin VOLSPIKE excess is −0.25%
[−1.40, +0.99]. These are reported results from `random_entry.py`/`findings.md`, not independently reproduced
here. They strengthen CAPIT's historical prior and weaken VOLSPIKE's transfer case.

The code uses same-coin random hours within ±15 days, fixed hold and 0.39%/side; it bootstraps signal calendar
days. Its Monte Carlo tail share samples each trade independently and does not preserve simultaneous cross-coin
shocks. A crash can span adjacent days; 13 of the extra universe's 17 crash days overlap the study universe.
The pooled history is already explored, the hourly entry differs from registered timing, and costs are fixed.
The positive study interval is therefore not untouched forward evidence or a live profitability verdict.

The 21-coin hourly cache and random-baseline stdout are not tracked at this snapshot. The current fetch routine
does not pin cache hashes or verify complete coverage after exhausted retries. No historical redownload was
made: a fresh run would require roughly 2,300 Coinbase requests. Recover the original cache/output before
spending on replication; record hashes, missing hours and failed chunks.

## 4. Next work, within the existing lanes

1. **Live-rule owner:** correct the reproduced integrity failures before relying on a future met gate.
2. **Agent owner:** finish the forward same-coin/same-hold control REPORT line (plan A2 remains open).
3. **Research diagnostic after cache recovery:** fix the existing CAPIT rule and adopted coin screen, preserve
   joint trade schedules within whole crash episodes, report episode-bootstrap and leave-one-episode-out excess,
   and show net dollars/exposure at $100 stakes. Classify this as a robustness check of explored history.
4. **Execution evidence:** distinguish assumed fees, simulated fill gaps and actual reconciled costs. A maker
   method earns its place only after its savings exceed missed fills and adverse selection over all signals.

The registrations, trading policy, bot book and owner code are unchanged. Existing non-US and closed memecoin
lanes remain as recorded. Northstar still needs its exact source/model artifacts before empirical integration.

## Validation and limits

Seven deterministic synthetic cohorts ran against the reviewed gate: one complete finite control, one
insufficient-three-position control and five false-met cohorts. Full repository verification: **324 passed,
1 skipped in 81.93 s**. No production gate records, live costs, historical cache returns, passive fill quality,
Coinbase account tier or sealed Jev outcomes were checked. No profit result or live-order capability was added.

## Supplemental writer-to-reader reproduction, 2026-10-13

The nonfinite case also reproduces through the actual paper adapter, JSON serialization,
JSON reader, gate report and health reporter at the reviewed commit. A synthetic filled buy
returns the string `NaN`; eight distinct position IDs span three entry days. The adapter
writes 56 `NaN` tokens, the reader accepts them, the gate reports **met**, and cost health
reports **green**. This checks a complete in-memory path rather than supplying constructed
gate rows alone. It does not establish that the live paper book contains any malformed fill.

Run from the repository root with the development environment. The fake client has no
network methods or credentials; log and file reads are replaced with memory objects.

```python
"""Synthetic adapter -> JSON reader -> gate/health reproduction; no files/orders."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from tartar.autotrade.alpaca import AlpacaMirror
from tartar.autotrade import live_gate as lg


class FakePaper:
    def account(self):
        return {"account_number": "PA-SYNTHETIC", "status": "ACTIVE"}

    def spread_bps(self, sym):
        return 10.0

    def submit(self, cid, sym, side, **kw):
        return {"id": cid, "status": "filled", "filled_qty": "1",
                "filled_avg_price": "NaN" if side == "buy" else "100"}

    def wait_fill(self, order, seconds):
        return order

    def asset(self, sym):
        return {"min_trade_increment": ".000001"}

    def position_qty(self, sym):
        return 1.0


mirror = AlpacaMirror({"strategies": ["us_capit_fast"], "taker_fee": .0025,
                       "fill_wait_s": 0}, FakePaper(), None)
rows = []
mirror.log = rows.append
start = datetime(2026, 10, 12, 10, tzinfo=timezone.utc).timestamp()
for i in range(8):
    at = start + (i % 3) * 86400
    pos = SimpleNamespace(id=f"p{i}", strategy="us_capit_fast", asset="BTC",
                          notional_usd=100.0, meta={"venue": "coinbase"})
    mirror.on_open(pos, SimpleNamespace(price=100.0, at=at, meta={}), at)
    mirror.on_close(pos, SimpleNamespace(net_return=.02, meta={}),
                    SimpleNamespace(price=100.0, at=at + 86400), at + 86400)
payload = "".join(json.dumps(r) + "\n" for r in rows)


class MemoryFile:
    def __truediv__(self, name):
        return self

    def exists(self):
        return True

    def read_text(self):
        return payload


lg.Path = lambda root: MemoryFile()
print("nan_tokens_in_writer_json=" + str(payload.count("NaN")))
g = lg.gate(lg._rows("synthetic-in-memory"))
print(json.dumps({k: g[k] for k in ("trades", "crash_days", "mean_net",
                                   "median_cost", "max_gap_bps", "met", "unmet")},
                 sort_keys=True))
print(lg.report_lines("synthetic-in-memory")[1])
print(json.dumps(lg.health_items("synthetic-in-memory"), sort_keys=True))
```

Observed:

```text
nan_tokens_in_writer_json=56
{"crash_days": 3, "max_gap_bps": NaN, "mean_net": NaN, "median_cost": NaN, "met": true, "trades": 8, "unmet": []}
**Live rule gate** (`handoff/live-rule-us.md`, us_capit, judged on `us_capit_fast`'s Alpaca paper fills): 3/3 crash days, 8/8 trades, mean net +nan% (bar -4.7%), median cost nan%/side (bar 0.50%). **Paper side met**; going live still needs AJ's go, a funded Alpaca live account and a live route.
[{"check": "Alpaca paper cost", "detail": "median nan%/side over the last 8 round trips (live rule: gate 0.50%, stop 0.60%; assumed 0.39%); coins above 0.50%: BTC/USD", "level": "green"}]
```
