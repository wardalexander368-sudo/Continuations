import json

from tartar.autotrade.ledger import Ledger
from tartar.autotrade.runner import run_once
from tartar.autotrade.strategies.wick_bounce import HOLD, WIN, WickBounce

H0 = 500_000  # an hour index (2027)


def series(n, spike_at):
    """Gently oscillating closes; one hour with a long lower wick."""
    rows = []
    for k in range(n):
        c = 100 + (0.1 if k % 2 else -0.1)
        lo = c - 0.2 if k != spike_at else c - 10
        rows.append({"t": (H0 + k) * 3_600_000, "o": c, "h": c + 0.2, "l": lo, "c": c + (1 if k > spike_at else 0)})
    return rows


def test_wick_bounce_books_long_after_lower_wick_and_exits_after_hold(tmp_path):
    rows = series(WIN + 40, WIN + 10)

    def post(ctx, body):
        if body["type"] == "allMids":
            return {"BTC": "100"}
        q = body["req"]
        return [r for r in rows if q["startTime"] <= r["t"] < q["endTime"]]

    (tmp_path / "config.json").write_text(json.dumps({"mode": "paper", "strategies": {"w": {"kind": "wick_bounce"}}}))
    s = WickBounce("w", {"_post": post, "coins": ["BTC"], "start": "2000-01-01", "end": "2100-01-01"})
    for k in range(WIN + 5, WIN + 30):  # one run per hour
        run_once(tmp_path, now=(H0 + k) * 3600 + 60, strategies={"w": s})
    (t,) = Ledger(tmp_path).trades()
    assert t.side == 1 and t.meta["entry_hour"] == H0 + WIN + 10 and t.exit_at == (H0 + WIN + 10 + HOLD + 1) * 3600
    assert t.net_return == __import__("pytest").approx(101 / 100 * (1 - 0.00085) ** 2 - 1, abs=2e-3)
    assert s.evaluate([t], t.exit_at, {}).decision == "pending"


def test_execution_realistic_score_uses_5m_prices_after_the_run_lag_and_gates_pass():
    from tartar.autotrade.core import Context, Trade

    t_in, t_out = 3600 * 10 + 1200, 3600 * 15 + 1200

    def post(ctx, body):
        q = body["req"]
        assert q["interval"] == "5m"
        return [{"t": t * 1000, "o": 100.0 if t < 3600 * 12 else 90.0, "c": 100.0 if t < 3600 * 12 else 90.0}
                for t in range(q["startTime"] // 1000, q["endTime"] // 1000, 300)]

    s = WickBounce("w", {"_post": post, "start": "1970-01-01", "end": "1970-01-02"})
    st = {"exec_pending": {"BTC:9": {"coin": "BTC", "side": 1, "day": "1970-01-01", "entry_t": t_in, "exit_t": t_out}}}
    s.score_executions(Context(t_out + 600, [], st, {}))
    assert st["exec"]["BTC:9"]["net"] == __import__("pytest").approx(-0.10 - 2 * 0.00085) and not st["exec_pending"]
    good = [Trade(str(k), "w", "BTC", 1, 200, 1, 86400 * 0.1 * k, 1.1, 1, 0, 20, 0.1 + 0.01 * (k % 3),
                  meta={"entry_day": f"1970-01-0{1 + k % 2}"}) for k in range(20)]
    v = s.evaluate(good, 86400 * 5, st)
    assert v.decision == "fail" and "can't execute" in v.reason and v.stats["exec_n"] == 1
