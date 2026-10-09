# DRAFT: a JEV-protocol carve-out for TARTAR's Jev calls

**Status: DRAFT, not in force.** Written 2026-10-09 by the research session for the user to
accept, change or reject (STATUS blocker "Jev usage policy"). Modelled on jevtrader's
`PROTOCOL.md` (read at `9ce9b7b`; jevtrader itself is untouched). Until the user signs §5, the
honest reading is that TARTAR's always-on Jev use is outside the user's JEV protocol.

## 1. What TARTAR uses Jev for

| Use | Kind | Status |
|---|---|---|
| `tartar decide --jev` (profitability §3.7) | one-off offline batch, answers cached | done 10-08: no edge |
| `jev_metadata_ask.py` (§3.8) | one-off offline batch, 17 questions × 3,523 launches, cached | done 10-09: no edge |
| fast loop `"shadow_jev": true` | **always-on caller**: every screened launch, answers journaled, never acted on | running in the Jev session's container since 10-08 23:44 |
| fast loop `"scorer": "jev"` | **decision instrument** (paper): buys on Jev's answer | built, not in use (lost money offline) |

## 2. The JEV-protocol rules these would otherwise break
As quoted in jevtrader's PROTOCOL §2: §5 Never, *"Any always-on hook that makes a model call"*
(shadow mode); §5, *"`jev ask` as a decision instrument"* (the `jev` scorer); rule 8, *"No hook
makes a model call."*

## 3. Proposed conditions (the user may cut or add)
Granted for `StaticPush7217/TARTAR` only:

1. **Paper only.** Already true in code: `Policy.mode` must be `"paper"`, and nothing in the
   repo can sign or send a transaction.
2. **Measurement only.** Shadow mode journals answers and never acts on them. The `jev` scorer
   is **not** covered: it stays off unless the user approves it separately.
3. **Separate.** No reads or writes of `crypto-trading-system` or `jevtrader`, and none of
   TARTAR's Jev answers or outcomes are fed into either.
4. **Own ledger, before every send, failing closed.** *Not built yet:* `tartar/jev.py` needs to
   append each request to `data/jev-sends.tsv` (same columns as the user's `DISCLOSURE.tsv`)
   before opening a socket; an unwritable ledger means no send.
5. **Own key.** A TARTAR-only TypeSafe key (today the cloud environment's proxy injects the
   shared `TYPESAFE_API_KEY`), so a limit or suspension caused by TARTAR can't reach the
   user's other Jev uses.
6. **Spend tripwire.** *Not built yet:* a daily cap (proposed: $0.25/day of input tokens, as in
   jevtrader). Past it, `data/JEV-HALT` stops sends; the fast loop keeps trading on rules.
7. **Pinned model.** *Not yet:* requests name `jev-latest`; pin a version and log drift.
8. **Retries.** *Not yet:* at most one retry, on 429/5xx only (today up to 4).
9. **Enforced in code.** *Not yet:* `JevClient.ask` refuses (`unsigned`) until §5 below is
   filled, before reading a key or writing the ledger.

## 4. The line for the JEV protocol's §7 (if accepted)
```
10. <date> — CARVE-OUT, TARTAR only: github.com/StaticPush7217/TARTAR's fast loop may run an
    always-on Jev caller in SHADOW mode (answers journaled, never acted on) as a paper-only
    MEASUREMENT; offline batch evaluations with cached answers. Own ledger, own key, spend
    tripwire, pinned model. The 'jev' scorer (acting on answers) is NOT covered.
```

## 5. Signature
In force from: `________`  Signed: `________`

(Until both fields are filled, by the user or on their explicit word, conditions 4 and 6–9
should be built first and shadow mode should stay off.)
