# Offline research evidence receipts

`experiments/research_evidence.py` is a standalone stdlib tool. It appends public-safe
research metadata to a user-selected JSONL file. It makes no network requests and has no
order, wallet, account, collector, workflow, or strategy interface. Evidence labels and
structural validation never authorize trading; reports always say `order_authorization: false`.

Create a scratch directory outside owner paper books and frozen registrations, write an
event JSON there, and run from the repository root:

```sh
python3 handoff/experiments/research_evidence.py append --ledger /tmp/research-evidence.jsonl --event /tmp/plan-event.json
python3 handoff/experiments/research_evidence.py validate --ledger /tmp/research-evidence.jsonl
python3 handoff/experiments/research_evidence.py report --ledger /tmp/research-evidence.jsonl
```

Save the returned `hash` independently of the ledger. Supply it with `--expected-head`
when validating a previously exported ledger or appending to that exact previous head.
Hash chaining detects damaged/changed rows. An independent head additionally detects a
valid-prefix truncation or rewritten chain. It is not signed, tamper-proof storage: a party
controlling both ledger and exported head can replace them. Append takes a Unix file lock,
validates the complete chain, then flushes and fsyncs one new row; it never rewrites a row.
Do not edit JSONL by hand. Keep public-safe plan/revision/result/rejection receipts for every
attempt, including failures and missing-data attempts. The tool cannot discover unlogged work.

Each input event has exactly `event_id`, `utc`, `kind`, `trial_id`, and `payload`. UTC is
`YYYY-MM-DDTHH:MM:SS[.microseconds]Z`; recorded event times cannot move backwards. IDs must
be nonempty and event IDs must be unique. The tool adds schema version 1, a sequential
`seq`, `prev_hash`, and `hash`. Missing/unknown fields, duplicate JSON keys, nonfinite
numbers, incomplete final lines, and duplicate events/attempts fail closed.

This is a synthetic plan event. Repeated `a` digests are placeholders for an example,
not evidence of actual artifacts; replace them with SHA-256 digests calculated locally.
Only public-safe summaries and hashes belong in receipts. Never paste raw prompts, source
data, private account rows, credentials, or protected metadata. The schema rejects extra
raw-data fields but cannot determine whether a free-text summary contains private material.

```json
{
  "event_id": "example-plan-1",
  "utc": "2026-10-01T10:00:00Z",
  "kind": "plan",
  "trial_id": "example-1",
  "payload": {
    "lineage_id": "example-1",
    "parent_trial_id": null,
    "revision": 1,
    "hypothesis": "Synthetic fixture control",
    "proposer": "synthetic-reviewer", "model_version": "not-used",
    "cost_model": "synthetic fixed dollars", "universe": "synthetic fixtures",
    "controls": "cash", "regimes": "all fixtures",
    "readout_schedule": "once after window", "feature_availability": "fixture time",
    "owner": "synthetic-reviewer",
    "economic_mechanism": "synthetic null fixture; no economic claim",
    "decision": "reject fixture on failed integrity check",
    "stop_schedule": "stop at fixed window end",
    "alternatives": ["null fixture"],
    "primary_metric": "net_account_pnl_usd",
    "baselines": ["cash"],
    "windows": {
      "development": {"start_utc": "2026-09-01T00:00:00Z", "end_utc": "2026-10-01T00:00:00Z"},
      "outcome": {"start_utc": "2026-10-02T00:00:00Z", "end_utc": "2026-10-03T00:00:00Z"}
    },
    "evidence_class": "synthetic",
    "hashes": {
      "prompt": null,
      "code": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "config": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "data": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    },
    "registration_hash": null
  }
}
```

`prompt: null` means no prompt artifact. Code/config/data digests are mandatory. The data
digest identifies the declared input snapshot/manifest; future outcome artifacts are hashed
when access is recorded. A digest proves equality to a supplied artifact, not its quality,
availability, or provenance. Root plans use `lineage_id == trial_id`; child plans name an
existing `parent_trial_id` and inherit its lineage ID. `revision` events reuse the plan
schema and increment exactly once. Lineage/evidence class cannot change through a revision.
Revisions stop after any freeze, access, or attempted result/rejection; create a child trial
and retain the earlier record. Development and outcome windows must be nonempty/disjoint.

Valid evidence labels are `external/unreplicated`, `hypothesis`, `synthetic`,
`explored-history`, `prospective-paper`, `registered-final`, and `real-execution`.
Result labels must match the trial plan; no result event upgrades a class. Prospective
plans/revisions and freeze must precede the outcome window. Access must be inside or after
that window. `registered-final` additionally requires `registration_hash` and delays the final
result until the full window closes. Fixed-rule monitoring may be recorded earlier;
it does not permit outcome-informed revisions or change an existing registered verdict.
Artifact first-access times are shared across trials; child trials cannot restart
the access clock for already inspected bytes. Use an artifact manifest including
source/window identity when identical raw bodies belong to different observations. These checks validate supplied dates and
digests, not an external registry or an operator's unlogged access. Explored history can
record an earlier actual access date without pretending it was untouched.

Event payloads after a plan are:

| Kind | Exact payload fields | Meaning |
|---|---|---|
| `freeze` | `plan_hash` | Hash of the latest plan/revision; one freeze per trial |
| `access` | `first_access_utc`, `artifact_hash`, `purpose` | First actual outcome access for an artifact, recorded after freeze; first access cannot be future-dated or duplicated |
| `result` | `attempt_id`, `evidence_class`, `metrics`, `costs` | One attempted result; requires freeze and access |
| `rejection` | `attempt_id`, `reason` | Failed/rejected/unavailable attempt, including ones rejected before freeze |

Attempt IDs are unique across the whole file. Record public-safe rejection reasons as
separate attempts. If an attempt yielded a result, include its rejection/decision in a
separate public-safe review document rather than falsely counting a second attempt.

Metrics require exactly `status`, `opportunities`, `fills`, `executed_sides`, `round_trips`, `days`,
`episodes`, `net_account_pnl_usd`, and `max_drawdown_usd`. Counts are nonnegative integers
and not booleans. Fills are execution records (partial fills count separately), executed
sides are filled order legs, round trips are completed entry/exit pairs, days are observed
trading days, and episodes are separately declared clusters of dependent opportunities.
Round trips need at least two sides each; sides cannot exceed fills. Days/episodes must
be positive for estimated completed-trade results. These counts do not assert independence.
`max_drawdown_usd` is a finite, nonnegative loss magnitude, never a signed negative return.
The tool validates supplied metrics; it does not recompute a cash-account equity curve.
`status` describes completed-trade inference, not the existence of account facts.
If no round trip completed, status must be `not-estimable`; known account fees,
marked loss or a verified flat no-trade zero may still be recorded. Unknown
P&L/drawdown remains `null` in any sample. No inference or order pass follows. For example:

```json
{"status":"not-estimable","opportunities":0,"fills":0,"executed_sides":0,"round_trips":0,"days":0,"episodes":0,"net_account_pnl_usd":null,"max_drawdown_usd":null}
```

Each cost receipt requires exactly these fields:

```json
{
  "component_id": "example-pool-fee",
  "amount_usd": 1.0,
  "basis": "per-side",
  "size": {"value": 100.0, "unit": "USD"},
  "route": "synthetic-route",
  "source": "https://example.invalid/synthetic-receipt",
  "source_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "valid_from_utc": "2026-10-01T00:00:00Z",
  "valid_until_utc": "2026-10-05T00:00:00Z",
  "evidence_class": "synthetic",
  "payer": "trader",
  "trader_charge": true,
  "included_in": null
}
```

`amount_usd` is the total dollar amount for that declared size/basis, not an unconverted
percentage or rate. `null` is unknown; `0` is an observed/explicitly assumed zero whose
evidence class/source still matter. Basis is `per-side`, `round-trip`, `per-order`, or
`account`; size units are `USD`, `SOL`, `base-units`, or `contracts`. Payer is `trader`,
`pool`, `protocol`, `other`, or `unknown`. A true `trader_charge` requires trader payer.
Component IDs must be unique inside a result. Source and route must be nonempty; source
hashes and a nonempty UTC validity interval are required. Validity is declared source
applicability; the tool does not silently substitute current fees for historical fees or
verify that a source is authoritative. Lock that assumption in the plan/review.

For an LP/protocol/creator share already embedded in a trader-paid pool fee, name the
parent component in `included_in` and set `trader_charge: false`. Parent and subdivisions
must have matching route, size, basis, and validity; known subdivisions cannot exceed the
known parent amount, and the parent must be a top-level trader charge. Unknown or cyclic
relationships are refused. The report sums only explicit trader charges, once. Unknown
components remain listed; empty costs have unknown total, and a known partial total is
marked `partial`. There are no hardcoded product-specific fee splits.

Focused synthetic validation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider tests/test_research_evidence.py
```

Plan metadata also requires nonempty proposer, model/version, cost model, universe,
controls, regime definitions, readout schedule and feature-availability descriptions.
`owner` names the accountable research owner; `economic_mechanism` explains the
proposed payer/benefit; `decision` states the research decision rule; and
`stop_schedule` states when the fixed test stops. Each is a required nonempty string.
The stop/readout schedule and decision are recorded declarations, never order permissions.
Use explicit `not-used`/`all opportunities` descriptions where applicable rather than
dropping required fields. These are public-safe declarations, not authentication.
Trader-paid top-level costs cannot opt out of the sum: exclusions require a
validated parent component.
