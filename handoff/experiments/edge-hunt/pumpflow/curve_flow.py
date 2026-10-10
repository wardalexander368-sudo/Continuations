"""pump.fun bonding-curve volume per UTC day from TARTAR's own recorder: a same-day source for the
pumpflow signal, which DefiLlama only publishes 25+ hours after the day ends (edge-hunt.md §E1,
"Publish delay").

pump.fun's launchpad revenue is its fee on bonding-curve trades, so a day's curve volume is that
day's revenue up to the fee rate, and is known minutes after midnight UTC. The recorder Action
(`recorder.yml`) streams every pump program log but keeps each token only for its first 120
minutes, so it sees most, not all, of the volume (2026-10-09 21-23 UTC: ~420-530 SOL of fees an
hour against DefiLlama's ~620 SOL/hour for 10-08). Whether its *day-over-day surprise* tracks
DefiLlama's is what the validation in edge-hunt.md checks before any forward test uses it.

Overlapping recorder runs are merged: a trade is counted once by (mint, slot, trader, side, sol).

    python3 handoff/experiments/edge-hunt/pumpflow/curve_flow.py 2026-10-10   # one day -> curve-days.jsonl
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fetch_gha_raw import REPO, _client  # noqa: E402

OUT = Path("handoff/data/pumpflow-live/curve-days.jsonl")
ASSET = re.compile(r"^(\d{8})-(\d{2})\.run(\d+)\.jsonl\.gz$")


def hour_stats(paths: list[Path]) -> dict:
    seen: set = set()
    sol = no_sol = swap_sol = 0.0
    disconnects = 0
    for p in paths:
        with gzip.open(p, "rt") as fh:
            for line in fh:
                r = json.loads(line)
                e = r.get("e")
                if e == "trade":
                    k = (r.get("mint"), r.get("slot"), r.get("trader"), r.get("side"), r.get("sol"), r.get("tok"))
                    if k in seen:
                        continue
                    seen.add(k)
                    if r.get("sol") is None:
                        no_sol += 1
                    else:
                        sol += float(r["sol"])
                elif e == "swap":
                    swap_sol += float(r.get("sol") or 0)
                elif e == "session" and r.get("state") == "disconnected":
                    disconnects += 1
    return {"curve_sol": round(sol, 3), "trades": len(seen), "no_sol": int(no_sol), "pumpswap_tracked_sol": round(swap_sol, 3),
            "disconnects": disconnects, "runs": len(paths)}


def day(d: str) -> dict:
    tag = "raw-gha-" + d.replace("-", "")
    with _client() as c:
        r = c.get(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}")
        r.raise_for_status()
        by_hour = defaultdict(list)
        for a in r.json()["assets"]:
            m = ASSET.match(a["name"])
            if m:
                by_hour[m.group(2)].append(a)
        hours = {}
        with tempfile.TemporaryDirectory() as tmp:
            for h in sorted(by_hour):
                paths = []
                for a in by_hour[h]:
                    p = Path(tmp) / a["name"]
                    with c.stream("GET", a["browser_download_url"]) as s, open(p, "wb") as fh:
                        s.raise_for_status()
                        for chunk in s.iter_bytes(1 << 20):
                            fh.write(chunk)
                    paths.append(p)
                hours[h] = hour_stats(paths)
                for p in paths:
                    p.unlink()
                print(f"{d} {h}:00 {hours[h]}", file=sys.stderr)
    return {"day": d, "hours": len(hours), "curve_sol": round(sum(x["curve_sol"] for x in hours.values()), 3),
            "trades": sum(x["trades"] for x in hours.values()), "no_sol": sum(x["no_sol"] for x in hours.values()),
            "disconnects": sum(x["disconnects"] for x in hours.values()), "per_hour": hours}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("days", nargs="+", help="UTC days, YYYY-MM-DD")
    args = ap.parse_args()
    rows = {json.loads(x)["day"]: json.loads(x) for x in OUT.read_text().splitlines() if x.strip()} if OUT.exists() else {}
    for d in args.days:
        rows[d] = day(d)
        print(f"{d}: {rows[d]['hours']} hours, curve {rows[d]['curve_sol']:,.0f} SOL, {rows[d]['trades']:,} trades")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(rows[d], separators=(",", ":")) + "\n" for d in sorted(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
