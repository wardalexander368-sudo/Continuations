# Cached Jev answers and launch metadata

Copies of the caches behind `profitability.md` §3.7–3.8, so nobody has to ask
Jev (or the metadata gateways) again. Restore them with:

```bash
for f in metadata jev-answers jev-metadata; do gunzip -c handoff/data/jev/$f.jsonl.gz > data/$f.jsonl; done
```

* `metadata.jsonl`: `{"mint", "meta"}` per recorded launch (`meta` is null if it could not be fetched).
* `jev-answers.jsonl`: the `LAUNCH` question set (`tartar/jev.py`), keyed by mint and question version.
* `jev-metadata.jsonl`: the `METADATA` question set.

Rows carry the question set's `version`. A changed question gets a new version and is asked again.
