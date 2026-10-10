"""Automated paper-trading agent: strategies, execution, risk limits and self-improvement.

The loop (``python -m tartar.autotrade run``, scheduled by ``.github/workflows/autotrade.yml``):

1. load the book (``autotrade/state.json``) and the config (``autotrade/config.json``);
2. for every strategy that is not retired or halted, fetch its data and ask it for intents
   (open or close a position, at a price and time it read from market data);
3. pass each intent through the risk limits (kill switch, position caps, daily loss cap);
4. fill it with the broker: ``PaperBroker`` books it at the reference price less the
   strategy's cost model; ``LiveBroker`` books the same paper fill and, for promoted strategies,
   mirrors it with a twin in SOL: quote-only in mode ``dry_live``, real in mode ``live`` (only with
   the user's standing approval and a route key; ``execution.py``, ``handoff/autotrade.md``);
5. mark open positions, then score every strategy's closed trades against its
   pre-registered rule and promote, demote, retire or keep it (``lifecycle.py``), logging
   every change in ``autotrade/changes.jsonl`` and the summary in ``autotrade/REPORT.md``.

Every fill and close goes to ``autotrade/journal.jsonl``, every twin leg to ``autotrade/fills.jsonl``.
Nothing signs or sends a transaction unless the mode is ``live`` and approved.
"""
