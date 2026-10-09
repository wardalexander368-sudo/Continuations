"""P(rug): the chance that a new launch collapses, learned from recorded launches.

The displayed risk level (scam.py) barely ranks which launches collapse later (AUC 0.57,
predictor doc problem 6). This model does: a LightGBM classifier on the numbers of a launch's
state `screen` seconds after it appeared (decide.NUMERIC: flow, buyers, curve, holders,
creator record, risk level), predicting a **rug**: the price `horizon` seconds after the screen
is 80% or more below the price at the screen, and the token has not graduated by then.

States come from a fast-loop replay that screens every launch and buys none, so each launch is
judged exactly as `tartar watch --next-launch` and the fast loop see it live (causal creator
history). Outcomes are read from the full raw stream; a launch is left out only when its recorder
was down in between (an event gap over 30 s, or the recording's end). Training splits launches
by time like the global model (70% train, 15% validation for early stopping and a Platt
recalibration, the latest 15% test).
"""

from __future__ import annotations

import bisect
import json
import math
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from .decide import NUMERIC as FEATURES

SCREEN = 20.0
HORIZON = 1800.0
RUG_RATIO = 0.2  # price at the horizon / price at the screen at or below this is a rug
PARAMS = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 50, "feature_fraction": 0.8, "verbose": -1, "seed": 7}


def _dirs(raw: str | Path | Sequence[str | Path]) -> list[str]:
    items = raw.split(",") if isinstance(raw, str) else [raw] if isinstance(raw, Path) else list(raw)
    return [str(d).strip() for d in items if str(d).strip()]


def _stream(directory: str):
    """Curve prices by mint, graduation times, recorder gaps, the last event time and whether simulated."""
    from .data.rawlog import raw_files, read_events

    prices: dict[str, tuple[list, list]] = defaultdict(lambda: ([], []))
    graduated: dict[str, float] = {}
    times = []
    simulated = False
    for e in read_events(raw_files(directory)):
        times.append(e["t"])
        simulated = simulated or (e["e"] == "session" and bool(e.get("simulated")))
        if e.get("quote"):
            continue
        if e["e"] in ("create", "trade") and e.get("vsol") and e.get("vtok"):
            ts, ps = prices[e["mint"]]
            ts.append(e["t"])
            ps.append(e["vsol"] / e["vtok"])
        elif e["e"] in ("migrate", "graduate"):
            graduated.setdefault(e["mint"], e["t"])
    times.sort()
    gaps = [(a, b) for a, b in zip(times, times[1:]) if b - a > 30.0]
    for ts, ps in prices.values():
        order = np.argsort(ts, kind="stable")
        ts[:], ps[:] = [ts[i] for i in order], [ps[i] for i in order]
    return prices, graduated, gaps, times[-1] if times else 0.0, simulated


def _price_at(path: tuple[list, list], t: float) -> float | None:
    ts, ps = path
    i = bisect.bisect_right(ts, t) - 1
    return ps[i] if i >= 0 else None


def _screens(directory: str, screen: float) -> list[dict]:
    """Every launch's journaled screen state from a replay that buys nothing."""
    from .fastloop import FastLoop, Journal, Policy, PolicyFile, replay
    from .review import load_journal

    with tempfile.TemporaryDirectory() as tmp:
        policy = asdict(Policy())
        policy.update(screen_seconds=screen, min_buyers=1000, skip_flags=[], shadow_jev=False)
        Path(tmp, "policy.json").write_text(json.dumps(policy))
        loop = FastLoop(PolicyFile(Path(tmp, "policy.json")), Journal(Path(tmp, "j")))
        replay(directory, loop)
        return [r for r in load_journal(Path(tmp, "j")) if r["e"] == "screen"]


def labelled_states(raw: str | Path | Sequence[str | Path], screen: float = SCREEN, horizon: float = HORIZON) -> list[dict]:
    """[{t, mint, state, ratio, rug, moon, simulated}] for every SOL launch whose outcome was recorded, in time order.

    `raw` names one directory per recorder (comma-separated or a sequence). A launch two
    recorders caught counts once (the first directory's copy).
    """
    rows, seen = [], set()
    for d in _dirs(raw):
        prices, graduated, gaps, end, simulated = _stream(d)
        for r in _screens(d, screen):
            mint, t0 = r["mint"], r["t"]
            if mint in seen or mint not in prices:
                continue
            t1 = t0 + horizon
            if t1 > end or any(a < t1 and b > t0 for a, b in gaps):
                continue
            p0, p1 = _price_at(prices[mint], t0), _price_at(prices[mint], t1)
            if not p0 or not p1:
                continue
            seen.add(mint)
            grad = mint in graduated and graduated[mint] <= t1
            ratio = p1 / p0
            rug, moon = (not grad) and ratio <= RUG_RATIO, grad or ratio >= 2.0
            rows.append({"t": t0, "mint": mint, "state": r["state"], "ratio": ratio, "rug": rug, "moon": moon, "simulated": simulated})
    rows.sort(key=lambda r: r["t"])
    return rows


def features(state: dict) -> list[float]:
    return [math.nan if state.get(k) is None else float(state[k]) for k in FEATURES]


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-z))


def fit_platt(p: np.ndarray, y: np.ndarray, steps: int = 50) -> tuple[float, float]:
    """(a, b) minimising log loss of sigmoid(a * logit(p) + b) on (p, y), by Newton's method."""
    z, y = _logit(np.asarray(p, float)), np.asarray(y, float)
    a, b = 1.0, 0.0
    for _ in range(steps):
        q = _sigmoid(a * z + b)
        g = np.array([np.sum((q - y) * z), np.sum(q - y)])
        w = q * (1 - q) + 1e-9
        h = np.array([[np.sum(w * z * z), np.sum(w * z)], [np.sum(w * z), np.sum(w)]]) + 1e-6 * np.eye(2)
        da, db = np.linalg.solve(h, g)
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-9:
            break
    return float(a), float(b)


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def auc(score: np.ndarray, y: np.ndarray) -> float:
    """Probability that a random rug scores above a random non-rug (ties count half)."""
    score, y = np.asarray(score, float), np.asarray(y, bool)
    order = np.argsort(score, kind="stable")
    ranks = np.empty(len(score))
    ranks[order] = np.arange(1, len(score) + 1)
    for v in np.unique(score):  # average ranks over ties
        tie = score == v
        if tie.sum() > 1:
            ranks[tie] = ranks[tie].mean()
    pos, neg = y.sum(), (~y).sum()
    return float((ranks[y].sum() - pos * (pos + 1) / 2) / max(pos * neg, 1))


@dataclass
class RugModel:
    booster: object
    meta: dict = field(default_factory=dict)

    def predict_many(self, states: Sequence[dict]) -> np.ndarray:
        if not states:
            return np.zeros(0)
        x = np.array([features(s) for s in states], dtype=float)
        raw = self.booster.predict(x, num_iteration=self.meta.get("best_iteration") or None)
        a, b = self.meta.get("platt", (1.0, 0.0))
        return _sigmoid(a * _logit(raw) + b)

    def predict(self, state: dict) -> float:
        return float(self.predict_many([state])[0])

    def save(self, path: str | Path) -> Path:
        path = Path(path).with_suffix(".txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(str(path))
        path.with_suffix(".json").write_text(json.dumps(self.meta, indent=2))
        return path

    @classmethod
    def load(cls, path: str | Path) -> RugModel:
        import lightgbm as lgb

        path = Path(path).with_suffix(".txt")
        meta = json.loads(path.with_suffix(".json").read_text())
        if list(meta.get("features", [])) != list(FEATURES):
            raise ValueError("P(rug) model was trained on other features")
        return cls(lgb.Booster(model_file=str(path)), meta)


def rug_model_name(screen: float = SCREEN) -> str:
    return f"rug-{screen:g}s"


def find_rug_model(directory: str | Path | None = None, screen: float = SCREEN) -> RugModel | None:
    """The installed P(rug) model, if one exists and loads; else None (callers show no P(rug))."""
    from .model.global_model import model_dir

    path = model_dir(directory) / f"{rug_model_name(screen)}.txt"
    if not path.exists():
        return None
    try:
        return RugModel.load(path)
    except Exception:  # missing LightGBM, corrupt or mismatched files: run without it
        return None


def split(n: int) -> tuple[slice, slice, slice]:
    """Train / validation / test by time: the first 70%, the next 15%, the latest 15%."""
    a, b = int(0.7 * n), int(0.85 * n)
    return slice(0, a), slice(a, b), slice(b, n)


def train_rug(rows: Sequence[dict], *, screen: float = SCREEN, horizon: float = HORIZON, log: Callable[[str], None] = print) -> tuple[RugModel, dict]:
    """Train on the earlier launches, recalibrate on validation, report on the latest (test)."""
    import lightgbm as lgb

    x = np.array([features(r["state"]) for r in rows], dtype=float)
    y = np.array([bool(r["rug"]) for r in rows])
    tr, va, te = split(len(rows))
    if y[tr].sum() < 10 or y[va].sum() < 5:
        raise ValueError(f"too few rugs to train on ({int(y[tr].sum())} train, {int(y[va].sum())} validation)")
    booster = lgb.train(
        PARAMS, lgb.Dataset(x[tr], y[tr]), 2000, valid_sets=[lgb.Dataset(x[va], y[va])], callbacks=[lgb.early_stopping(50, verbose=False)]
    )
    best = booster.best_iteration or booster.current_iteration()
    raw_va = booster.predict(x[va], num_iteration=best)
    platt = fit_platt(raw_va, y[va])
    meta = {
        "features": list(FEATURES),
        "screen": screen,
        "horizon": horizon,
        "rug_ratio": RUG_RATIO,
        "best_iteration": best,
        "platt": list(platt),
        "launches": len(rows),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "first_launch": rows[0]["t"],
        "last_launch": rows[-1]["t"],
    }
    model = RugModel(booster, meta)
    report = rug_report(model, rows)
    meta["test_auc"], meta["test_log_loss"] = report["test"]["auc"], report["test"]["log_loss"]
    log(f"P(rug): {len(rows)} launches, best iteration {best}, Platt a={platt[0]:.3f} b={platt[1]:+.3f}")
    return model, report


def rug_report(model: RugModel, rows: Sequence[dict]) -> dict:
    """How the model and the displayed risk level rank and size rugs on the test launches."""
    tr, va, te = split(len(rows))
    test = list(rows[te])
    y = np.array([bool(r["rug"]) for r in test])
    p = model.predict_many([r["state"] for r in test])
    raw = model.booster.predict(np.array([features(r["state"]) for r in test], dtype=float), num_iteration=model.meta.get("best_iteration") or None)
    level = np.array([float(r["state"].get("risk_rank") or 0) for r in test])
    deciles = []
    for chunk in np.array_split(np.argsort(p, kind="stable"), 10):
        if len(chunk):
            deciles.append({"predicted": float(p[chunk].mean()), "observed": float(y[chunk].mean()), "n": int(len(chunk))})
    by_level = {}
    for name in ("unknown", "ok", "caution", "danger", "scam"):
        mask = np.array([r["state"].get("risk") == name for r in test])
        if mask.any():
            by_level[name] = {"n": int(mask.sum()), "share": float(mask.mean()), "rug_rate": float(y[mask].mean()), "p_rug": float(p[mask].mean())}
    gain = model.booster.feature_importance("gain")
    return {
        "screen": model.meta.get("screen"),
        "horizon": model.meta.get("horizon"),
        "launches": {"train": tr.stop - tr.start, "valid": va.stop - va.start, "test": len(test)},
        "base_rate": {"train": float(np.mean([r["rug"] for r in rows[tr]])), "test": float(y.mean()) if len(y) else None},
        "test": {
            "auc": auc(p, y),
            "auc_risk_level": auc(level, y),
            "log_loss": log_loss(p, y),
            "log_loss_uncalibrated": log_loss(raw, y),
            "log_loss_base_rate": log_loss(np.full(len(y), float(np.mean([r["rug"] for r in rows[tr]]))), y),
            "brier": float(np.mean((p - y) ** 2)),
            "mean_predicted": float(p.mean()),
            "deciles": deciles,
            "by_level": by_level,
        },
        "feature_gain": {FEATURES[i]: float(gain[i] / gain.sum()) for i in np.argsort(gain)[::-1] if gain.sum() > 0},
    }
