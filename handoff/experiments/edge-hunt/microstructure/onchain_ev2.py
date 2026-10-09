import httpx, datetime as dt, numpy as np, time, json, sys
pool = sys.argv[1]; tag = sys.argv[2]
evs = np.load("dl/events_k30z4.npy")
since = int(dt.datetime(2026, 4, 14, tzinfo=dt.timezone.utc).timestamp())
evs = [int(t) for t in evs if t >= since]
c = httpx.Client(timeout=20, verify="/root/.ccr/ca-bundle.crt")
res = {}
for t in evs:
    for attempt in range(5):
        r = c.get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/minute", params={"aggregate": 1, "before_timestamp": t + 3660 + 120, "limit": 120})
        if r.status_code in (429, 500, 502, 503): time.sleep(12); continue
        break
    if r.status_code != 200: print("skip", t, r.status_code); continue
    res[t] = r.json()["data"]["attributes"]["ohlcv_list"]
    time.sleep(2.2)
json.dump(res, open(f"dl/gt_{tag}.json", "w")); print(tag, len(res), "events saved")
