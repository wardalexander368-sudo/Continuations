"""Download the recorder Action's hours (.github/workflows/recorder.yml) from GitHub Releases.

Each UTC day is a release tagged `raw-gha-YYYYMMDD`; each asset is `YYYYmmdd-HH.run<RUN>.jsonl.gz`.
One Action run is one recorder's timeline, so the files land one directory per run:

    data/raw-gha/run<RUN>/YYYYmmdd-HH.jsonl.gz

and `--dirs` prints those directories comma-separated, ready for `tartar train --raw` and the
loaders (which dedupe launches two recorders both caught). Files already present are skipped.

    python3 handoff/experiments/fetch_gha_raw.py                      # everything
    python3 handoff/experiments/fetch_gha_raw.py --since 20261010 --dirs
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import httpx

REPO = "StaticPush7217/TARTAR"
ASSET = re.compile(r"^(\d{8}-\d{2})\.run(\d+)\.jsonl\.gz$")


def _client() -> httpx.Client:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(headers=headers, timeout=120, follow_redirects=True)


def releases(client: httpx.Client) -> list[dict]:
    out, page = [], 1
    while True:
        r = client.get(f"https://api.github.com/repos/{REPO}/releases", params={"per_page": 100, "page": page})
        r.raise_for_status()
        batch = r.json()
        out += [rel for rel in batch if rel["tag_name"].startswith("raw-gha-")]
        if len(batch) < 100:
            return out
        page += 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default="data/raw-gha")
    ap.add_argument("--since", help="first UTC day, YYYYMMDD")
    ap.add_argument("--until", help="last UTC day, YYYYMMDD")
    ap.add_argument("--dirs", action="store_true", help="print the run directories, comma-separated")
    args = ap.parse_args()

    root = Path(args.out)
    fetched = skipped = 0
    with _client() as client:
        for rel in releases(client):
            day = rel["tag_name"].removeprefix("raw-gha-")
            if (args.since and day < args.since) or (args.until and day > args.until):
                continue
            for asset in rel["assets"]:
                m = ASSET.match(asset["name"])
                if not m:
                    continue
                target = root / f"run{m.group(2)}" / f"{m.group(1)}.jsonl.gz"
                if target.exists() and target.stat().st_size == asset["size"]:
                    skipped += 1
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(".part")
                with client.stream("GET", asset["browser_download_url"]) as r, open(tmp, "wb") as fh:
                    r.raise_for_status()
                    for chunk in r.iter_bytes(1 << 20):
                        fh.write(chunk)
                tmp.rename(target)
                fetched += 1
                print(f"{target} ({asset['size'] / 1e6:.1f} MB)", file=sys.stderr)
    print(f"{fetched} fetched, {skipped} already present", file=sys.stderr)
    if args.dirs:
        print(",".join(str(d) for d in sorted(root.glob("run*")) if d.is_dir()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
