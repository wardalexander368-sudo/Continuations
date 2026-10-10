"""Restart and overlap safety (tartar/autotrade/safety.py), in dry run: a run is killed mid-order and the
next run must neither lose the order nor place it twice. The dry route's wallet is simulated on disk
(dry_wallet.json), so a killed run leaves it the way a real wallet would be."""

import json
from pathlib import Path

import pytest

from tartar.autotrade import broker as broker_mod
from tartar.autotrade.execution import DryExecutor
from tartar.autotrade.ledger import Ledger
from tartar.autotrade.runner import run_once
from tartar.autotrade.safety import Busy, LEASE_TTL_S, run_lock

from test_autotrade_live import NOW, Strat, closer, opener, setup


class Killed(BaseException):
    """Stands in for SIGKILL / a lost runner: nothing after it runs, no except-Exception catches it."""


class FakeQuotes:
    """0.01 SOL buys 1,000,000 raw; 1,000,000 raw sells for 0.0099 SOL."""

    def quote(self, i, o, amount):
        if i.startswith("So111"):
            return {"outAmount": str(int(amount) // 10)}
        return {"outAmount": str(int(amount) * 99 // 10)}

    def sol_usd(self):
        return 100.0


class KillableDry(DryExecutor):
    """The dry route, with a switch that kills the process before or after the order lands."""

    def __init__(self):
        super().__init__(quotes=FakeQuotes(), balance_sol=0.05, priority_sol=0.0)
        self.kill = None  # ("buy" | "sell", "before" | "after")
        self.buys, self.sells = 0, 0

    def buy(self, mint, sol):
        if self.kill == ("buy", "before"):
            raise Killed
        f = super().buy(mint, sol)
        self.buys += 1
        if self.kill == ("buy", "after"):
            raise Killed
        return f

    def sell(self, mint, raw):
        if self.kill == ("sell", "before"):
            raise Killed
        f = super().sell(mint, raw)
        self.sells += 1
        if self.kill == ("sell", "after"):
            raise Killed
        return f


@pytest.fixture
def dry(monkeypatch):
    ex = KillableDry()
    monkeypatch.setattr(broker_mod, "make_executor", lambda route, cfg, env=None: ex)
    for k in ("TARTAR_WALLET_KEY", "PUMPPORTAL_API_KEY", "TARTAR_LIVE_APPROVED", "TARTAR_LIVE_KILL", "GITHUB_RUN_ID"):
        monkeypatch.delenv(k, raising=False)
    return ex


def go(root, script, now):
    return run_once(root, now=now, strategies={"s": Strat(script)})


def wallet(root):
    return json.loads((root / "dry_wallet.json").read_text())


def live(root):
    return json.loads((root / "state.json").read_text()).get("live", {})


def test_killed_after_the_buy_landed_next_run_adopts_it_and_does_not_buy_again(tmp_path, dry):
    root = setup(tmp_path)
    dry.kill = ("buy", "after")
    with pytest.raises(Killed):
        go(root, [[opener()]], NOW)
    assert dry.buys == 1 and wallet(root)["tokens"] == {"M1": 1_000_000}
    assert "M1" in (root / "pending.json").read_text()
    assert not Ledger(root).positions  # the book never saw it

    dry.kill = None
    s = go(root, [[opener()]], NOW + 300)  # the strategy re-emits the same entry: same order id
    assert dry.buys == 1, "bought twice"
    (pos,) = Ledger(root).positions
    assert pos.meta["live"]["token_raw"] == 1_000_000 and pos.meta["live"]["adopted"] == "s|a|99940"
    assert s["reconcile"]["claims"] == 1 and not s["new_halts"]
    assert json.loads((root / "pending.json").read_text()) == {}
    assert not live(root)["unclaimed"] and not live(root)["orphans"]

    s = go(root, [[closer()]], NOW + 600)  # and it exits normally
    assert dry.sells == 1 and wallet(root)["tokens"] == {} and not s["new_halts"]


def test_killed_before_the_buy_landed_next_run_buys_once(tmp_path, dry):
    root = setup(tmp_path)
    dry.kill = ("buy", "before")
    with pytest.raises(Killed):
        go(root, [[opener()]], NOW)
    assert dry.buys == 0 and wallet(root)["tokens"] == {}
    dry.kill = None
    s = go(root, [[opener()]], NOW + 300)
    assert dry.buys == 1 and not s["new_halts"] and "reconcile" not in s
    assert Ledger(root).positions[0].meta["live"]["token_raw"] == 1_000_000


def test_killed_after_the_sell_landed_next_run_does_not_sell_again(tmp_path, dry):
    root = setup(tmp_path)
    go(root, [[opener()]], NOW)
    dry.kill = ("sell", "after")
    with pytest.raises(Killed):
        go(root, [[closer()]], NOW + 300)
    assert dry.sells == 1 and wallet(root)["tokens"] == {}
    dry.kill = None
    s = go(root, [[closer()]], NOW + 600)
    assert dry.sells == 1, "sold twice"
    assert s["reconcile"]["sold_unrecorded"] == 1 and not s["new_halts"]
    (trade,) = Ledger(root).trades()
    assert trade.meta["live"]["sold_unrecorded"]
    assert not Ledger(root).positions


def test_killed_before_the_sell_landed_next_run_sells_once(tmp_path, dry):
    root = setup(tmp_path)
    go(root, [[opener()]], NOW)
    dry.kill = ("sell", "before")
    with pytest.raises(Killed):
        go(root, [[closer()]], NOW + 300)
    dry.kill = None
    s = go(root, [[closer()]], NOW + 600)
    assert dry.sells == 1 and wallet(root)["tokens"] == {} and not s["new_halts"]
    assert Ledger(root).trades()[0].meta["live"]["sol_out"] > 0


def test_tokens_nobody_can_explain_halt_live_entries_before_any_trade(tmp_path, dry):
    """A runner lost before it committed: no pending order, no fill row, but the wallet holds the mint."""
    root = setup(tmp_path)
    go(root, [[opener()]], NOW)
    w = wallet(root)
    w["tokens"]["M1"] += 500
    (root / "dry_wallet.json").write_text(json.dumps(w))
    s = go(root, [[opener("b", "M2")]], NOW + 300)
    assert s["reconcile"]["orphans"] == 1 and s["new_halts"]
    assert "untracked holding" in live(root)["halted"]
    assert dry.buys == 1  # M2 was not bought


def test_unexplained_sol_drop_counts_against_the_daily_cap_and_halts(tmp_path, dry):
    root = setup(tmp_path)
    go(root, [[]], NOW)
    w = wallet(root)
    w["sol"] -= 0.004
    (root / "dry_wallet.json").write_text(json.dumps(w))
    s = go(root, [[opener()]], NOW + 300)
    assert s["new_halts"] and dry.buys == 0
    st = live(root)
    assert "wallet SOL fell" in st["halted"]
    assert sum(st["daily_sol"].values()) == pytest.approx(-0.004)


def test_a_claim_never_readopted_becomes_an_orphan(tmp_path, dry):
    root = setup(tmp_path)
    dry.kill = ("buy", "after")
    with pytest.raises(Killed):
        go(root, [[opener()]], NOW)
    dry.kill = None
    go(root, [[]], NOW + 300)  # the strategy moved on
    assert live(root)["unclaimed"]
    s = go(root, [[]], NOW + 300 + 3601)
    assert not live(root)["unclaimed"] and live(root)["orphans"] and s["new_halts"]


def test_live_lease_blocks_a_second_trader_until_it_goes_stale(tmp_path, dry, monkeypatch):
    root = setup(tmp_path, mode="live", live_approved_on="2026-10-10")
    led = Ledger(root)
    led.state["lease"] = {"holder": "gha:other", "at": NOW - 60}
    led.save()
    monkeypatch.setenv("GITHUB_RUN_ID", "me")
    strat = Strat([[opener()]])
    s = run_once(root, now=NOW, strategies={"s": strat})
    assert "gha:other" in s["skipped"] and strat.script  # never stepped
    s = run_once(root, now=NOW + LEASE_TTL_S + 1, strategies={"s": strat})
    assert "skipped" not in s and json.loads((root / "state.json").read_text())["lease"]["holder"] == "gha:me"


def test_run_lock_is_exclusive(tmp_path):
    with run_lock(tmp_path):
        with pytest.raises(Busy):
            with run_lock(tmp_path):
                pass
    with run_lock(tmp_path):  # released
        pass


def test_workflow_never_runs_two_traders_and_commits_failed_runs():
    wf = (Path(__file__).resolve().parents[1] / ".github/workflows/autotrade.yml").read_text()
    assert "group: autotrade-main" in wf and "cancel-in-progress: false" in wf
    loop = wf.split("while [")[1]
    assert loop.index("git add -f autotrade") < loop.index('[ "$rc" = 0 ] ||')  # commit before failing
    assert "release-lease" in wf
    secs = int(wf.split('LOOP_SECONDS: "')[1].split('"')[0])
    assert secs + 600 < int(wf.split("timeout-minutes: ")[1].split()[0]) * 60


def test_a_reconcile_that_cannot_read_the_wallet_stops_live_entries_not_paper(tmp_path, dry, monkeypatch):
    root = setup(tmp_path)
    monkeypatch.setattr(KillableDry, "holdings", lambda self, mints: (_ for _ in ()).throw(RuntimeError("rpc down")))
    go(root, [[opener()]], NOW)  # first run: no mints to check yet, buys
    s = go(root, [[opener("b", "M2")]], NOW + 300)
    assert "reconcile failed" in live(root)["halted"] and s["new_halts"]
    assert len(Ledger(root).positions) == 2 and dry.buys == 1  # paper booked, no blind live buy
