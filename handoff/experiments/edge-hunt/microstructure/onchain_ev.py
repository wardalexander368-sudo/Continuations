import httpx, datetime as dt, numpy as np, time, json
evs = np.load("dl/events_k30z4.npy")
since = int(dt.datetime(2026, 4, 14, tzinfo=dt.timezone.utc).timestamp())
evs = [int(t) for t in evs if t >= since]
D = np.load("dl/SOL_1m.npz"); m = D["m"]; cl = D["c"]
c = httpx.Client(timeout=20, verify="/root/.ccr/ca-bundle.crt")
pool = "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE"
out = []
for t in evs:
    for attempt in range(4):
        r = c.get(f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/minute", params={"aggregate": 1, "before_timestamp": t + 3660 + 120, "limit": 80})
        if r.status_code == 429: time.sleep(15); continue
        break
    if r.status_code != 200: print("skip", t, r.status_code); continue
    ol = {int(x[0]): (x[1], x[4]) for x in r.json()["data"]["attributes"]["ohlcv_list"]}  # open, close
    i = np.searchsorted(m, t // 60)
    b0, b60 = cl[i], cl[i + 60]
    # on-chain: entry at next minute's open (first trade after signal close), exit at close of minute t+60
    e = ol.get(t + 60); x = ol.get(t + 3600)
    if e is None or x is None: print("missing candles", t); continue
    out.append({"t": t, "bin": 1e4 * np.log(b60 / b0), "onchain": 1e4 * np.log(x[1] / e[0]), "entry_dev": 1e4 * np.log(e[0] / b0), "exit_dev": 1e4 * np.log(x[1] / b60)})
    time.sleep(2.5)
json.dump(out, open("dl/onchain_ev.json", "w"))
a = np.array([[o["bin"], o["onchain"], o["entry_dev"], o["exit_dev"]] for o in out])
print(f"{len(out)} events since 2026-04-14 (k30 z<=-4, H=60, gross, no cost)")
print("binance fwd mean %+.1f median %+.1f | on-chain (Orca, entry next-minute open) mean %+.1f median %+.1f" % (a[:, 0].mean(), np.median(a[:, 0]), a[:, 1].mean(), np.median(a[:, 1])))
print("entry deviation on-chain vs binance close: median %+.1f p10 %+.1f p90 %+.1f | exit deviation median %+.1f" % (np.median(a[:, 2]), np.quantile(a[:, 2], .1), np.quantile(a[:, 2], .9), np.median(a[:, 3])))
