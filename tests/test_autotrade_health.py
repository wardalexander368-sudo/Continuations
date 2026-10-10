"""The agent's health check and the pumpflow strategy, offline."""

import json
from datetime import datetime, timezone

import pytest

from tartar.autotrade import health
from tartar.autotrade.core import Context, Trade
from tartar.autotrade.strategies.pumpflow import KEY, PumpFlow


def t(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


NOW = t("2026-10-11T12:00:00")


class Resp:
    def __init__(self, body, code=200):
        self.body, self.status_code = body, code

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(self.status_code)


class FakeGH:
    def __init__(self, runs, assets):
        self.runs, self.assets = runs, assets

    def get(self, url, params=None):
        if "/runs" in url:
            wf = url.split("/workflows/")[1].split("/")[0]
            return Resp({"workflow_runs": self.runs.get(wf, [])})
        day = url.rsplit("raw-gha-", 1)[1]
        names = [a for a in self.assets if a.startswith(day)]
        return Resp({"assets": [{"name": n} for n in names]}) if names else Resp({}, 404)


def run_row(conclusion="success", started="2026-10-11T11:50:00Z", status="completed"):
    return {"status": status, "conclusion": conclusion, "run_started_at": started, "html_url": "u"}


def write_inputs(repo, age_h=1.0):
    ts = datetime.fromtimestamp(NOW - age_h * 3600, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for rel in ("handoff/data/jlp-paper/snapshots.jsonl", "handoff/data/pumpflow-paper/snapshots.jsonl"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(json.dumps({"t": ts}) + "\n")
    (repo / "handoff/data/edge-hunt/hl-ctx").mkdir(parents=True, exist_ok=True)
    (repo / "handoff/data/edge-hunt/hl-ctx/2026-10.jsonl").write_text(json.dumps({"t": NOW - age_h * 3600}) + "\n")
    d = repo / "handoff/preregistration/dip-rolling"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"cohort-{datetime.fromtimestamp(NOW - age_h * 3600, timezone.utc):%Y-%m-%dT%H%M}.json").write_text("{}")


def all_hours():
    out, h = [], t("2026-10-09T21:00:00")
    while h <= NOW - 2 * 3600:
        out.append(datetime.fromtimestamp(h, timezone.utc).strftime("%Y%m%d-%H") + ".run1.jsonl.gz")
        h += 3600
    return out


def test_all_green(tmp_path):
    write_inputs(tmp_path)
    gh = FakeGH({wf: [run_row()] for wf in health.WORKFLOWS}, all_hours())
    h = health.run(tmp_path, tmp_path, now=NOW, http=gh)
    assert h["status"] == "green", [i for i in h["items"] if i["level"] != "green"]
    assert "🟢 GREEN" in "\n".join(health.report_lines(tmp_path, NOW))


def test_failed_skipped_gaps_and_stale_are_red(tmp_path):
    write_inputs(tmp_path, age_h=60)
    runs = {wf: [run_row()] for wf in health.WORKFLOWS}
    runs["autotrade.yml"] = [run_row("failure")]
    runs["paper-tests.yml"] = [run_row(started="2026-10-10T20:00:00Z")]
    hours = [h for h in all_hours() if not h.startswith("20261011-0")]
    h = health.run(tmp_path, tmp_path, now=NOW, http=FakeGH(runs, hours))
    red = {i["check"] for i in h["items"] if i["level"] == "red"}
    assert {"Action autotrade.yml", "Action paper-tests.yml", "Input: JLP snapshots",
            "Input: pumpflow snapshots", "Input: dip cohorts"} <= red
    text = "\n".join(health.report_lines(tmp_path, NOW))
    assert "🔴 RED" in text and "10 hours missing" not in text


def test_agent_halts_orphans_and_drift(tmp_path):
    (tmp_path / "state.json").write_text(json.dumps({"live": {"orphans": [{}], "strategies": {"x": {"halted": "boom"}}}}))
    rows = [{"event": "perp_close", "strategy": "xs", "compare": {"live_minus_paper": -0.05}} for _ in range(4)]
    (tmp_path / "fills.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    items = {i["check"]: i["level"] for i in health.check_agent(tmp_path)}
    assert items == {"Agent: orphans": "red", "Agent: halts": "red", "Twins: xs": "yellow"}


class FakeInfo:
    def __init__(self):
        self.calls = []

    def funding_rate_sum(self, coin, t0, t1):
        self.calls.append((t0, t1))
        return 0.001

    def post(self, body):
        return {"PUMP": "0.006"}


def snaps(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_pumpflow_books_snapshots_closes_flips_and_keeps(tmp_path):
    p = tmp_path / "s.jsonl"
    rows = [{"t": "2026-10-09T21:38:25Z", "day": "2026-10-08", "signal": -0.1, "position": -1, "mid": 0.0053},  # pilot
            {"t": "2026-10-10T01:15:00Z", "day": "2026-10-09", "signal": 0.2, "position": 1, "mid": 0.0054}]
    snaps(p, rows)
    info = FakeInfo()
    s = PumpFlow("pumpflow", {"snapshots": str(p), "_info": info, "size_usd": 200})
    ctx = Context(NOW, [], {}, {})
    (op,) = s.step(ctx)
    assert op.kind == "open" and op.side == 1 and op.price == 0.0054 and op.meta["venue"] == "hyperliquid"
    assert s.step(ctx) == []  # cursor
    rows += [{"t": "2026-10-11T02:15:00Z", "day": "2026-10-10", "signal": 0.1, "position": 1, "mid": 0.0055},
             {"t": "2026-10-12T01:15:00Z", "day": "2026-10-11", "signal": -0.3, "position": -1, "mid": 0.0050}]
    snaps(p, rows)

    class Pos:
        side, entry_at, notional_usd, meta = 1, t("2026-10-10T01:15:00"), 200.0, {"key": KEY}

    ctx.positions = [Pos()]
    out = s.step(ctx)
    assert [(i.kind, i.side if i.kind == "open" else None, i.cost.fee) for i in out] == [
        ("close", None, 0.0), ("open", 1, 0.0), ("close", None, 0.001), ("open", -1, 0.001)]
    assert out[0].meta["kept"] and "(kept)" in out[0].reason and not out[2].meta["kept"]
    assert out[0].meta["carry_usd"] == pytest.approx(-1 * 200 * 0.001)
    assert all(i.meta["key"] == KEY for i in out)


def test_pumpflow_verdict_pending_then_scored():
    s = PumpFlow("pumpflow", {"_info": FakeInfo()})
    tr = [Trade(str(i), "pumpflow", "PUMP", 1 if i % 2 else -1, 200, 1.0, i, 1.01 if i % 2 else 0.99, i + 1, 0, 2, 0.01, meta={})
          for i in range(130)]
    assert s.evaluate(tr, NOW, {}).decision == "pending"
    v = s.evaluate(tr, t("2027-05-01T00:00:00"), {})
    assert v.decision == "pass" and v.n == 130
