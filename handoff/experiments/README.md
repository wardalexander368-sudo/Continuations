# Experiment scripts

Scripts behind the numbers in `handoff/profitability.md`. Run them from the
repo root after copying the raw snapshot into `data/raw`:

```bash
mkdir -p /tmp/tartar-exp
python3 handoff/experiments/build_dataset.py                      # caches /tmp/tartar-exp/ds60.pkl (~20 s)
python3 handoff/experiments/net_return_model.py /tmp/tartar-exp/ds60.pkl      # §3.3
python3 handoff/experiments/latency_sensitivity.py /tmp/tartar-exp/ds60.pkl   # §3.4
python3 handoff/experiments/screen_launches.py /tmp/tartar-exp/ds60.pkl 20    # §3.5 flags (writes screen_rows_20.pkl)
python3 handoff/experiments/screen_model.py /tmp/tartar-exp/ds60.pkl 20       # §3.5 learned screen
python3 handoff/experiments/jev_calibration.py                                # §3.7 Jev answers vs outcomes (needs data/jev-answers.jsonl)
python3 handoff/experiments/jev_metadata_ask.py                               # §3.8 fetch metadata + ask Jev (network; cached)
python3 handoff/experiments/jev_metadata_features.py                          # §3.8 feature sets compared
```

Thresholds are always chosen on validation launches and reported on test
launches. Anything that looks profitable must be confirmed on recordings made
after these.
