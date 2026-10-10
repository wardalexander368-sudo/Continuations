import numpy as np, datetime as dt
exec(open("extremes2.py").read().split("grid = list")[0])
days = set(); evs = []
for name in ("valid", "test"):
    ii, pnl = events(30, 4, "down", 0, 60, *P[name])
    for i in ii:
        t = int(m[i]) * 60
        evs.append((name, t))
        for dd in (0, 1):  # event day and next day (holds can cross midnight)
            days.add(dt.datetime.fromtimestamp(t + dd * 86400, dt.timezone.utc).strftime("%Y-%m-%d"))
open("dl/evdays.txt", "w").write("\n".join(sorted(days)))
np.save("dl/events_k30z4.npy", np.array([t for _, t in evs]))
print(len(evs), "events,", len(days), "days")
