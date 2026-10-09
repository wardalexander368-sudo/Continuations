import numpy as np, zipfile, io, glob, datetime as dt
evs = np.load("dl/events_k30z4.npy")
# load all 1s closes for event days into a dict second->close
px = {}
for f in sorted(glob.glob("dl/k1s_ev/*.zip")):
    z = zipfile.ZipFile(f); a = np.loadtxt(io.TextIOWrapper(z.open(z.namelist()[0])), delimiter=",", usecols=(0, 4))
    t = a[:, 0]; t = np.where(t > 1e14, t / 1e6, t / 1e3).astype(np.int64)
    px[t[0] // 86400] = (t, a[:, 1])
def price(sec):
    d = sec // 86400
    if d not in px: return np.nan
    t, c = px[d]; i = np.searchsorted(t, sec, side="right") - 1
    if i < 0: return np.nan
    return c[i]
# need also 1m-based z for each event (all events are z<=-4, k=30); recompute z>=5 subset from 1m file
D = np.load("dl/SOL_1m.npz"); m = D["m"]; lc = np.log(D["c"]) * 1e4
r1 = np.zeros(len(m)); r1[1:] = np.diff(lc); cs = np.concatenate([[0], np.cumsum(r1 ** 2)])
COST = 1.5
cut = int(dt.datetime(2025, 7, 1, tzinfo=dt.timezone.utc).timestamp())
rows = []
for t in evs:
    i = np.searchsorted(m, t // 60)
    vol = np.sqrt((cs[i] - cs[i - 240]) / 240); z = (lc[i] - lc[i - 30]) / (vol * np.sqrt(30))
    close_sec = t + 59  # last second of signal minute
    p0 = price(close_sec)
    r = {"z": z, "per": "valid" if t < cut else "test"}
    for lat in [0, 3, 10, 30, 60]:
        pe = price(close_sec + lat)
        for H in [30, 60]:
            px_ = price(close_sec + lat + H * 60)
            r[(lat, H)] = 1e4 * np.log(px_ / pe) - COST
    rows.append(r)
for per in ["valid", "test"]:
    for zmin in [4, 5]:
        sub = [r for r in rows if r["per"] == per and r["z"] <= -zmin]
        line = []
        for H in [30, 60]:
            for lat in [0, 3, 10, 30, 60]:
                v = np.array([r[(lat, H)] for r in sub]); v = v[np.isfinite(v)]
                line.append(f"+{lat}s {v.mean():+.0f}")
            line.append("|")
        print(f"{per} z<=-{zmin} (n={len(sub)}) H=30: " + " ".join(line[:5]) + "  H=60: " + " ".join(line[6:11]))
