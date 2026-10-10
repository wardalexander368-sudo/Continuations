"""Score the F1 forward test (handoff/preregistration/who-trades-forward/SPEC.md) from the recorder Action's hours.

    python3 handoff/experiments/who_trades_forward.py [--count-only]

Fetches every `raw-gha` hour since the window opened (`fetch_gha_raw.py`), extracts each run
directory once (`exit_study.py extract`, cached as data/who-forward/<run>-<hours>.pkl), then runs
`who_trades.py --test` with the forward SPEC. `--count-only` reports launches and signals so far
without trade returns (a progress check, not a look at the result).
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "handoff/experiments")
SPEC = "handoff/preregistration/who-trades-forward/SPEC.json"
CACHE = Path("data/who-forward")


def main():
    out = subprocess.run([sys.executable, "handoff/experiments/fetch_gha_raw.py", "--since", "20261010", "--dirs"], capture_output=True, text=True, check=True)
    dirs = [d for d in out.stdout.strip().splitlines()[-1].split(",") if d]
    CACHE.mkdir(parents=True, exist_ok=True)
    pkls = []
    for d in dirs:
        files = sorted(p.name for p in Path(d).glob("*.jsonl.gz"))
        key = hashlib.sha1(",".join(files).encode()).hexdigest()[:10]
        pkl = CACHE / f"{Path(d).name}-{key}.pkl"
        if not pkl.exists():
            subprocess.run([sys.executable, "handoff/experiments/exit_study.py", "extract", d, str(pkl)], check=True)
        pkls.append(str(pkl))
    if "--count-only" in sys.argv:
        from who_trades import dip_signals, load
        spec = json.load(open(SPEC))
        launches = [L for L in load(pkls) if spec["test_from_unix"] <= L["created"] < spec["test_until_unix"]]
        print(f"{len(launches)} window launches so far, {len(dip_signals(launches, spec['peak_real_sol'], spec['dip']))} dip signals (before the seller filter)")
        return
    subprocess.run([sys.executable, "handoff/experiments/who_trades.py", "--test", SPEC, *pkls], check=True)


if __name__ == "__main__":
    main()
