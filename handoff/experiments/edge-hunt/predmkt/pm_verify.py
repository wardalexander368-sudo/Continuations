"""Re-price one pm_biases.py rule at hourly resolution (checks that a result isn't stale daily prices).

    python3 handoff/experiments/edge-hunt/predmkt/pm_verify.py CACHE_DIR FAM LO HI K

FAM is FAV or LONG, the band is [LO, HI) on the side bought, K days before the scheduled end.
For every market the daily rule would enter, fetch the hourly price history for the two days
before entry (cached in CACHE_DIR/hist60/) and re-enter at the last hourly price at or before the
entry time, if it is at most 2 hours old. Prints daily-priced and hourly-priced results on the
same markets, by split, with pm_biases.py's cost and bootstrap.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

sys.argv, ARGS = sys.argv[:2], sys.argv[2:]
FAM, LO, HI, K = ARGS[0], float(ARGS[1]), float(ARGS[2]), int(ARGS[3])
import pm_biases as pb  # noqa: E402  (loads the markets; its rule table only runs as a script)

cache = pb.cache / "hist60"
cache.mkdir(exist_ok=True)
client = httpx.Client(timeout=30)


def hourly(m, te):
    f = cache / f"{m['id']}_{K}.json"
    if f.exists():
        return json.loads(f.read_text())
    q = {"market": m["token"], "startTs": int(te - 2 * 86400), "endTs": int(te + 3600), "fidelity": 60}
    for i in range(4):
        try:
            r = client.get("https://clob.polymarket.com/prices-history", params=q)
            if r.status_code == 200:
                h = r.json()["history"]
                break
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(2 * (i + 1))
    else:
        return None
    f.write_text(json.dumps(h))
    time.sleep(0.1)
    return h


daily, hour = [], []
for m in pb.markets:
    e = pb.entry(m, K)
    if e is None:
        continue
    p = e[0]
    if not (0.005 < p < 0.995):
        continue
    te = m["end_t"] - K * 86400
    for side_yes, q in ((True, p), (False, 1 - p)):
        if not LO <= q < HI:
            continue
        h = hourly(m, te)
        if not h:
            continue
        pts = [x for x in h if te - 7200 <= x["t"] <= te]
        if not pts:
            continue
        ph = pts[-1]["p"]
        qh = ph if side_yes else 1 - ph
        if not (0.005 < qh < 0.995):
            continue
        key = (m["end_day"], m["event"] or m["id"])
        daily.append((*key, pb.ret(m, side_yes, q)))
        # the same trade at the hourly price, kept only if that price is still in the band
        hour.append((*key, pb.ret(m, side_yes, qh) if LO <= qh < HI else None))

print(f"{FAM} [{LO},{HI}) k={K}: {len(daily)} trades with an hourly price within 2h of entry")
for s in pb.SPLITS:
    d = pb.split(daily, s)
    h_all = [(a, b, r) for a, b, r in pb.split(hour, s) if r is not None]
    print(f"  {s:5s} daily price {pb.fmt(pb.stats(d))}   hourly price, still in band {pb.fmt(pb.stats(h_all))}")
