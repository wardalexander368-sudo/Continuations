"""The agent's own candidate search (self improvement), run weekly by .github/workflows/autotrade-search.yml.

    python -m tartar.autotrade search [--root autotrade]

1. **Generate**: every member of the registered perps-momentum family (edge hunt D, xs-momentum and
   vol-momentum registrations) on a grid of lookback (7/14/21/28 days), quantile (3/5/10), volatility
   scaling (off/on), signal day (Monday/Thursday) and execution lag (1/2 days): 96 rules, minus the 2
   already registered.
2. **Backtest** each on Hyperliquid's full daily history (delisted perps included) from the first
   week with 15 eligible perps (late 2023: earlier candles carry no volume) to the last complete week, with the registered universe (60 days of history, 30-day median volume
   >= $2M), 20 bps per side per unit of turnover and actual funding (daily sums of the hourly rates).
3. **Judge** with walk-forward splits and a multiple-testing penalty. A rule survives only if all hold:
   * train (every week before the last 26): the one-sided block-bootstrap lower bound (4-week blocks)
     of its mean weekly return at level 0.10 / M is above 0, where M is the number of distinct rules
     this search has ever tested (Bonferroni over everything looked at, across runs);
   * walk-forward stability: the mean is positive in each third of the train weeks;
   * holdout (the last 26 weeks, the freshest data): mean > 0 and at least half the train mean;
   * not a copy: weekly returns correlate below 0.9 with each registered rule's.
4. **Queue**: each survivor (at most 3 a run, at most 8 waiting or running) is written to
   ``autotrade/candidates/<name>.json`` as a draft pre-registration: its rule, the backtest numbers, a
   start date ``WAIT_DAYS`` after registration and its success rule (26 paper weeks, mean > 0 and the
   block-bootstrap CI above 0, widened by Bonferroni over every candidate ever queued). The commit that
   adds the file is the registration. The agent (runner.py) adds it as a paper strategy once the wait
   is over; from then on the normal lifecycle promotes, demotes or retires it.

Every tested rule and its numbers go to ``autotrade/search/tested.jsonl``; ``autotrade/search/REPORT.md``
shows the latest run. Paper only: nothing here trades.
"""

from __future__ import annotations

import itertools
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from .strategies.xs_momentum import MIN_HIST, MIN_VOL, rank_signal

COST = 0.002
FIRST_WEEK = date(2023, 7, 3)
HOLDOUT_WEEKS = 26
ALPHA = 0.10
WAIT_DAYS = 7
SCORE_WEEKS = 26
MAX_NEW, MAX_ACTIVE = 3, 8
CORR_MAX = 0.9
GRID = {"lookback": [7, 14, 21, 28], "quant": [3, 5, 10], "scaled": [False, True], "signal_weekday": [0, 3], "lag_days": [1, 2]}
REGISTERED = {  # rules already pre-registered elsewhere: compared against, never re-queued
    "xs_momentum": {"lookback": 14, "quant": 5, "scaled": False, "signal_weekday": 0, "lag_days": 1},
    "vol_momentum": {"lookback": 14, "quant": 5, "scaled": True, "signal_weekday": 0, "lag_days": 1},
}
WD = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}


def name_of(p: dict) -> str:
    return f"cand-xsm-L{p['lookback']}-q{p['quant']}-{'vol' if p['scaled'] else 'raw'}-{WD[p['signal_weekday']]}-lag{p['lag_days']}"


def grid() -> list[dict]:
    keys = sorted(GRID)
    out = [dict(zip(keys, v)) for v in itertools.product(*(GRID[k] for k in keys))]
    return [p for p in out if p not in REGISTERED.values()]


class Panel:
    """Daily closes, volumes and funding as aligned matrices, with the per-day pieces every rule shares."""

    def __init__(self, days: list[date], coins: list[str], C: np.ndarray, V: np.ndarray, F: dict | None):
        self.days, self.coins, self.C, self.V = days, coins, C, V
        self.ix = {d: i for i, d in enumerate(days)}
        # forward-filled closes: a delisted coin exits at its last close
        self.Cf = C.copy()
        for i in range(1, len(days)):
            m = np.isnan(self.Cf[i])
            self.Cf[i, m] = self.Cf[i - 1, m]
        fm = np.zeros_like(C)
        if F:
            col = {c: j for j, c in enumerate(coins)}
            for c, by_day in F.items():
                j = col.get(c)
                if j is None:
                    continue
                for d, v in by_day.items():
                    i = self.ix.get(date.fromisoformat(d))
                    if i is not None:
                        fm[i, j] = v
        self.fund_cum = np.cumsum(fm, axis=0)  # funding over (e, x] = cum[x] - cum[e]
        self._base: dict[int, np.ndarray] = {}

    def base_ok(self, i: int) -> np.ndarray:
        if i not in self._base:
            hist = ~np.isnan(self.C[i - MIN_HIST + 1: i + 1]).any(axis=0)
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                medv = np.nanmedian(self.V[i - 29: i + 1], axis=0)
            self._base[i] = hist & (medv >= MIN_VOL)
        return self._base[i]


def backtest(P: Panel, p: dict, first: date = FIRST_WEEK, last: date | None = None, funding: bool = True,
             cost: float = COST) -> list[tuple[date, float]]:
    """Weekly long-short returns ($1 per leg) of rule p: signal at the signal day's close, enter lag days
    later at the close, exit 7 days after entry (as xs_momentum_forward.py / vmom_forward.py)."""
    L, Q, lag = p["lookback"], p["quant"], p["lag_days"]
    out, prev = [], {}
    n = len(P.days)
    for i, d in enumerate(P.days):
        if d.weekday() != p["signal_weekday"] or d < first or (last and d > last) or i < max(MIN_HIST, 30, L):
            continue
        e, x = i + lag, i + lag + 7
        if x >= n:
            break
        sig = rank_signal(P.C, i, L, p["scaled"])
        ok = P.base_ok(i) & ~np.isnan(P.C[i - L]) & ~np.isnan(P.C[e]) & np.isfinite(sig)
        ids = np.where(ok)[0]
        if len(ids) < 15:
            continue
        order = ids[np.argsort(sig[ids])]
        q = len(order) // Q
        longs, shorts = order[-q:], order[:q]
        ret = P.Cf[x] / P.C[e] - 1
        fund = (P.fund_cum[x] - P.fund_cum[e]) if funding else np.zeros(len(P.coins))
        r = np.mean(ret[longs] - fund[longs]) + np.mean(-ret[shorts] + fund[shorts])
        w = {**{int(j): 1 / q for j in longs}, **{int(j): -1 / q for j in shorts}}
        turn = sum(abs(w.get(k, 0) - prev.get(k, 0)) for k in set(w) | set(prev)) / 2
        prev = w
        out.append((d, float(r - 2 * cost * turn)))
    return out


def block_means(n: int, B: int = 20000, block: int = 4, seed: int = 1) -> np.ndarray:
    """Index matrix (B, n) for a moving-block bootstrap with wraparound."""
    rng = np.random.default_rng(seed)
    k = n // block + 1
    starts = rng.integers(0, n, (B, k))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(B, -1)[:, :n] % n
    return idx


def judge(series: dict[str, list[tuple[date, float]]], M: int, holdout_weeks: int = HOLDOUT_WEEKS) -> dict[str, dict]:
    """Per rule: train / walk-forward / holdout numbers and pass flags (see the module doc)."""
    a = ALPHA / max(M, 1)
    def by_week(s):  # align rules with different signal days by the week of their signal
        return {d - timedelta(days=d.weekday()): v for d, v in s}

    reg = {k: by_week(v) for k, v in series.items() if k in REGISTERED}
    out = {}
    idx_cache: dict[int, np.ndarray] = {}
    for name, s in series.items():
        if not s:
            continue
        r = np.array([v for _, v in s])
        tr, ho = r[:-holdout_weeks], r[-holdout_weeks:]
        if len(tr) < 30:
            continue
        idx = idx_cache.setdefault(len(tr), block_means(len(tr)))
        boot = tr[idx].mean(axis=1)
        lo = float(np.quantile(boot, a))
        thirds = [float(x.mean()) for x in np.array_split(tr, 3)]
        corr = {}
        for k, rs in reg.items():
            if k == name:
                continue
            common = [(v, rs[w]) for w, v in by_week(s).items() if w in rs]
            if len(common) > 10:
                xa = np.array(common)
                corr[k] = float(np.corrcoef(xa[:, 0], xa[:, 1])[0, 1])
        st = {"weeks": len(r), "train_weeks": len(tr), "train_mean": float(tr.mean()), "train_lo_penalized": lo,
              "alpha": a, "thirds": thirds, "holdout_mean": float(ho.mean()), "holdout_weeks": len(ho),
              "corr_registered": corr, "first": s[0][0].isoformat(), "last": s[-1][0].isoformat()}
        st["checks"] = {
            "penalized_train": bool(lo > 0),
            "walk_forward": bool(all(t > 0 for t in thirds)),
            "holdout": bool(ho.mean() > 0 and ho.mean() >= 0.5 * tr.mean()),
            "not_a_copy": bool(all(abs(c) < CORR_MAX for c in corr.values())),
        }
        st["survives"] = bool(name not in REGISTERED and all(st["checks"].values()))
        out[name] = st
    return out


def queue_dir(root: Path) -> Path:
    return root / "candidates"


def queued(root: Path) -> list[dict]:
    d = queue_dir(root)
    return [json.loads(f.read_text()) for f in sorted(d.glob("*.json"))] if d.exists() else []


def next_signal_day(after: date, weekday: int) -> date:
    return after + timedelta(days=(weekday - after.weekday()) % 7)


def register(root: Path, name: str, p: dict, st: dict, now: float, family_size: int, run_id: str) -> dict:
    reg_day = datetime.fromtimestamp(now, timezone.utc).date()
    starts = reg_day + timedelta(days=WAIT_DAYS)
    first = next_signal_day(starts, p["signal_weekday"])
    spec = {
        "name": name, "kind": "xs_momentum", "family": "perps-momentum", "params": p,
        "registered_at": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "search_run": run_id, "starts_at": starts.isoformat(),
        "start": first.isoformat(), "end": (first + timedelta(days=7 * (SCORE_WEEKS - 1))).isoformat(),
        "score_weeks": SCORE_WEEKS, "family_size": family_size, "leg_usd": 500,
        "success": (f"after {SCORE_WEEKS} paper weeks: mean weekly long-short return net of 20 bps/side turnover "
                    f"and funding > 0 AND the moving-block bootstrap CI (4-week blocks) lower bound > 0 at "
                    f"level 0.05/{family_size} (Bonferroni over every candidate queued so far)"),
        "backtest": st, "status": "queued",
        "note": "draft pre-registration written by the agent's candidate search; the commit adding this file is the registration",
    }
    queue_dir(root).mkdir(parents=True, exist_ok=True)
    (queue_dir(root) / f"{name}.json").write_text(json.dumps(spec, indent=1, sort_keys=True))
    return spec


def active_candidates(root: Path, now: float) -> dict[str, dict]:
    """Strategy configs for queued candidates whose wait is over (runner.py adds them to the run)."""
    today = datetime.fromtimestamp(now, timezone.utc).date()
    out = {}
    for c in queued(root):
        if c.get("status") == "withdrawn" or date.fromisoformat(c["starts_at"]) > today:
            continue
        out[c["name"]] = {"kind": c["kind"], "enabled": True, "candidate": True, "shadow": True,
                          "prereg": f"autotrade/candidates/{c['name']}.json", "leg_usd": c.get("leg_usd", 500),
                          "start": c["start"], "end": c["end"], "score_weeks": c["score_weeks"],
                          "family_size": c["family_size"], **c["params"]}
    return out


def run(root: Path, http=None, now: float | None = None, panel: Panel | None = None) -> dict:
    now = time.time() if now is None else now
    root = Path(root)
    sdir = root / "search"
    sdir.mkdir(parents=True, exist_ok=True)
    today = datetime.fromtimestamp(now, timezone.utc).date()
    if panel is None:
        import httpx

        from . import hl_data

        http = http or httpx.Client(timeout=60)
        days, coins, C, V, _ = hl_data.load_daily(http, today)
        F = hl_data.update_funding(http, sdir / "funding_daily.csv", coins, today)
        panel = Panel(days, coins, C, V, F)
    run_id = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
    rules = {**{k: v for k, v in REGISTERED.items()}, **{name_of(p): p for p in grid()}}
    series = {name: backtest(panel, p) for name, p in rules.items()}
    tested_path = sdir / "tested.jsonl"
    seen = set()
    if tested_path.exists():
        seen = {json.loads(line)["name"] for line in tested_path.read_text().splitlines() if line.strip()}
    seen |= {n for n in rules if n not in REGISTERED}
    M = len(seen)
    verdicts = judge(series, M)
    with tested_path.open("a") as f:
        for name, st in verdicts.items():
            if name not in REGISTERED:
                f.write(json.dumps({"run": run_id, "name": name, "params": rules[name], **st}, sort_keys=True) + "\n")
    q = queued(root)
    names_q = {c["name"] for c in q}
    active = [c for c in q if c.get("status") != "withdrawn" and date.fromisoformat(c["end"]) + timedelta(days=9) >= today]
    surv = sorted((n for n, st in verdicts.items() if st["survives"] and n not in names_q),
                  key=lambda n: -verdicts[n]["train_lo_penalized"])
    room = max(0, min(MAX_NEW, MAX_ACTIVE - len(active)))
    new = [register(root, n, rules[n], verdicts[n], now, len(q) + k + 1, run_id) for k, n in enumerate(surv[:room])]
    summary = {"run": run_id, "tested": len(verdicts) - len([n for n in verdicts if n in REGISTERED]), "M": M,
               "survivors": surv, "queued": [c["name"] for c in new], "weeks": max((v["weeks"] for v in verdicts.values()), default=0)}
    write_report(sdir / "REPORT.md", summary, verdicts, rules, q + new)
    (sdir / "last_run.json").write_text(json.dumps(summary, indent=1))
    return summary


def write_report(path: Path, summary: dict, verdicts: dict, rules: dict, queue: list[dict]) -> None:
    def pct(x):
        return f"{100 * x:+.2f}%"

    fails = {k: 0 for k in ("penalized_train", "walk_forward", "holdout", "not_a_copy")}
    for n, st in verdicts.items():
        if n in REGISTERED:
            continue
        for k, ok in st["checks"].items():
            fails[k] += 0 if ok else 1
    any_v = next(iter(verdicts.values()), {})
    lines = [f"# Candidate search ({summary['run']})", "",
             f"The agent's weekly search over the perps-momentum family (tartar/autotrade/search.py). "
             f"{summary['tested']} rules backtested on {summary['weeks']} weeks "
             f"({any_v.get('first', '?')} .. {any_v.get('last', '?')}), the last {HOLDOUT_WEEKS} held out; penalty level "
             f"{ALPHA}/{summary['M']} (every rule this search has ever tested). Weekly long-short returns, $1 per leg, net of 20 bps "
             f"per side of turnover and funding.", "",
             f"**Survivors this run: {len(summary['survivors'])}** "
             + (f"(queued: {', '.join(summary['queued'])})" if summary["queued"] else "(none queued)") + ".", "",
             f"Rules failing each check: penalized train {fails['penalized_train']}, walk-forward thirds "
             f"{fails['walk_forward']}, holdout {fails['holdout']}, copy of a registered rule {fails['not_a_copy']}.", "",
             "| Rule | Train mean/wk | Penalized lower bound | Thirds | Holdout mean/wk | Corr. registered | Checks |",
             "|---|---|---|---|---|---|---|"]
    order = sorted(verdicts, key=lambda n: -verdicts[n]["train_lo_penalized"])
    for n in [*[k for k in REGISTERED if k in verdicts], *[k for k in order if k not in REGISTERED][:15]]:
        st = verdicts[n]
        ch = "registered" if n in REGISTERED else ("**survives**" if st["survives"] else
                                                     "fails " + ", ".join(k for k, ok in st["checks"].items() if not ok))
        corr = max((abs(c) for c in st["corr_registered"].values()), default=float("nan"))
        lines.append(f"| {n} | {pct(st['train_mean'])} | {pct(st['train_lo_penalized'])} | "
                     f"{' / '.join(pct(t) for t in st['thirds'])} | {pct(st['holdout_mean'])} | {corr:.2f} | {ch} |")
    lines += ["", "(Top 15 by penalized lower bound, plus the two registered rules for reference.)", "", "## Candidates queue", ""]
    if queue:
        lines += ["| Candidate | Registered | Paper from | Scored after | Status |", "|---|---|---|---|---|"]
        for c in queue:
            lines.append(f"| {c['name']} | {c['registered_at']} | {c['starts_at']} (first signal {c['start']}) | "
                         f"{c['score_weeks']} weeks | {c.get('status', 'queued')} |")
    else:
        lines.append("Empty: no rule has passed every check yet.")
    path.write_text("\n".join(lines) + "\n")
