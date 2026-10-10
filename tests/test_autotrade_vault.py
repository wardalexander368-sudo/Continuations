"""HLP vault twins (tartar/autotrade/vault.py), offline: dry deposits rolled across paper intervals and withdrawn at
the end, lockup and vault checks, the gated live sender, and restart safety."""

import json
from datetime import datetime, timezone

import pytest

from tartar.autotrade import broker as broker_mod
from tartar.autotrade.gate import LiveNotAllowed
from tartar.autotrade.ledger import Ledger
from tartar.autotrade.runner import run_once
from tartar.autotrade.strategies.vault_hold import HLP, VaultHold
from tartar.autotrade.vault import DryVaultExecutor, LiveVaultExecutor, VaultPending, make_vault_executor

T0 = datetime(2026, 10, 12, tzinfo=timezone.utc).timestamp()
DAY = 86400


class FakeVaultInfo:
    """vaultDetails with a moving 'now' point; ``follower`` is the account's followerState for live tests."""

    def __init__(self, t, av, pnl, **kw):
        self.now = (t, av, pnl)
        self.kw = {"isClosed": False, "allowDeposits": True, "maxDistributable": 4e7, **kw}
        self.follower = None
        self._cache = {}

    def details(self, vault, user=None):
        t, av, pnl = self.now
        d = {"portfolio": [["allTime", {"accountValueHistory": [[t * 1000, str(av)]], "pnlHistory": [[t * 1000, str(pnl)]]}]],
             "apr": 0.04, "leaderCommission": 0.0, **self.kw}
        if user:
            d["followerState"] = self.follower
        return d


def history(points):
    return lambda ctx: ([(t, v) for t, v, _ in points], {t: p for t, _, p in points})


CFG = {"kind": "vault_hold", "size_usd": 200, "start": "2026-10-12", "end": "2026-11-10"}


def setup(tmp_path, monkeypatch, info, clock):
    monkeypatch.delenv("TARTAR_LIVE_KILL", raising=False)
    monkeypatch.setattr(broker_mod, "make_executor", lambda route, cfg, env=None: None)
    monkeypatch.setattr(broker_mod, "make_vault_executor", lambda route, cfg, *a: DryVaultExecutor(cfg, info=info, clock=lambda: clock[0]))
    (tmp_path / "config.json").write_text(json.dumps({"mode": "dry_live", "strategies": {"hlp": CFG}, "live": {"perps": {}}}))


def fills(root):
    return [json.loads(x) for x in (root / "fills.jsonl").read_text().splitlines()]


def test_dry_twin_deposits_rolls_with_the_paper_intervals_and_withdraws_at_the_end(tmp_path, monkeypatch):
    clock = [T0 + 3600 + 300]
    info = FakeVaultInfo(clock[0], 100.0, 0.0)
    setup(tmp_path, monkeypatch, info, clock)
    pts = [(T0 - DAY, 100.0, 0.0), (T0 + 3600, 100.0, 0.0), (clock[0], 100.0, 0.0)]
    run_once(tmp_path, now=clock[0], strategies={"hlp": VaultHold("hlp", {**CFG, "_fetch": history(pts)})})
    (pos,) = Ledger(tmp_path).positions
    twin = pos.meta["live"]
    assert twin["venue"] == "hyperliquid_vault" and twin["vault"] == HLP and twin["usd_in"] == 200 and twin["dry"]
    assert twin["lockup_until"] == pytest.approx(clock[0] + 4 * DAY)
    assert [r["event"] for r in fills(tmp_path)] == ["vault_deposit"]

    # the next history point: the paper interval closes and reopens; the twin stays deposited and is marked
    clock[0] = T0 + 14 * DAY + 300
    info.now = (clock[0], 101.0, 1.0)
    pts = pts[:-1] + [(T0 + 14 * DAY, 101.0, 1.0), (clock[0], 101.0, 1.0)]
    run_once(tmp_path, now=clock[0], strategies={"hlp": VaultHold("hlp", {**CFG, "_fetch": history(pts)})})
    L = Ledger(tmp_path)
    (pos,) = L.positions
    assert pos.meta["live"]["equity"] == pytest.approx(202.0) and pos.meta["live"]["usd_in"] == 200
    rows = fills(tmp_path)
    assert [r["event"] for r in rows] == ["vault_deposit", "vault_roll_out", "vault_roll_in"]
    cmp = rows[1]["compare"]
    assert cmp["live_net_return_usd"] == pytest.approx(0.01) and cmp["live_minus_paper"] == pytest.approx(0.0, abs=1e-9)
    assert not L.state["live"].get("vault_handover")

    # past the window: the window-end close withdraws the twin
    clock[0] = T0 + 43 * DAY
    info.now = (clock[0], 103.02, 3.02)
    pts = pts[:-1] + [(T0 + 42 * DAY, 103.02, 3.02), (clock[0], 103.02, 3.02)]
    run_once(tmp_path, now=clock[0], strategies={"hlp": VaultHold("hlp", {**CFG, "_fetch": history(pts)})})
    L = Ledger(tmp_path)
    assert not L.positions and not L.state["live"].get("vault_handover") and not L.state["live"]["orphans"]
    last = fills(tmp_path)[-1]
    assert last["event"] == "vault_withdraw"
    assert last["compare"]["equity_out"] == pytest.approx(202.0 * 1.02)
    assert "Vault twin intervals" in (tmp_path / "REPORT.md").read_text()


def test_closed_vault_or_locked_withdrawal_never_moves_money():
    info = FakeVaultInfo(T0, 100.0, 0.0, allowDeposits=False)
    ex = DryVaultExecutor(info=info, clock=lambda: T0)
    f = ex.deposit(HLP, 200)
    assert not f.ok and "does not accept deposits" in f.error
    info.kw["allowDeposits"] = True
    assert not ex.deposit(HLP, 5).ok  # under the minimum
    f = ex.deposit(HLP, 200)
    assert f.ok and f.lockup_until == T0 + 4 * DAY
    assert "locked until" in ex.withdraw(HLP, 200, f.lockup_until).error
    info.kw["maxDistributable"] = 50.0
    late = DryVaultExecutor(info=info, clock=lambda: T0 + 5 * DAY)
    assert "can pay out" in late.withdraw(HLP, 200, f.lockup_until).error


def test_failed_withdrawal_orphans_the_twin_and_halts(tmp_path, monkeypatch):
    clock = [T0 + 3600 + 300]
    info = FakeVaultInfo(clock[0], 100.0, 0.0)
    setup(tmp_path, monkeypatch, info, clock)
    cfg = {**CFG, "end": "2026-10-13"}
    pts = [(T0 + 3600, 100.0, 0.0), (clock[0], 100.0, 0.0)]
    run_once(tmp_path, now=clock[0], strategies={"hlp": VaultHold("hlp", {**cfg, "_fetch": history(pts)})})
    clock[0] = T0 + 2 * DAY  # past the window but inside the 4-day lockup
    pts = pts[:-1] + [(T0 + 1.5 * DAY, 100.0, 0.0), (clock[0], 100.0, 0.0)]
    run_once(tmp_path, now=clock[0], strategies={"hlp": VaultHold("hlp", {**cfg, "_fetch": history(pts)})})
    L = Ledger(tmp_path)
    (o,) = L.state["live"]["orphans"]
    assert o["venue"] == "hyperliquid_vault" and "locked until" in o["error"]
    assert "vault withdrawal failed" in L.state["live"]["strategies"]["hlp"]["halted"]


class FakeExchange:
    url = "https://api.hyperliquid-testnet.xyz"

    def __init__(self, info):
        self.info, self.sent = info, []

    def post(self, action):
        self.sent.append(action)
        fs = self.info.follower or {"vaultEquity": "0", "lockupUntil": 0}
        eq = float(fs["vaultEquity"]) + (1 if action["isDeposit"] else -1) * action["usd"] / 1e6
        self.info.follower = {"vaultEquity": str(eq), "lockupUntil": int((T0 + 4 * DAY) * 1000)}
        return {"status": "ok", "response": {"type": "default"}}


def test_live_sender_signs_vault_transfers_only_past_the_gate(tmp_path):
    info = FakeVaultInfo(T0, 100.0, 0.0)
    ex = FakeExchange(info)
    halted = {"on": False}

    def guard(leg):
        if halted["on"] and leg == "open":
            raise LiveNotAllowed("live kill switch: HALT_LIVE")

    live = LiveVaultExecutor(ex, "0xacc", info=info, guard=guard, clock=lambda: T0)
    live.free_usd = lambda: 150.0
    f = live.deposit(HLP, 200)
    assert not f.ok and "perp balance" in f.error and ex.sent == []  # short of free USDC: nothing sent
    live.free_usd = lambda: 500.0
    f = live.deposit(HLP, 200)
    assert f.ok and ex.sent == [{"type": "vaultTransfer", "vaultAddress": HLP, "isDeposit": True, "usd": 200_000_000}]
    assert f.lockup_until == T0 + 4 * DAY and live.held(HLP) == 200
    halted["on"] = True
    assert not live.deposit(HLP, 200).ok and len(ex.sent) == 1  # kill switch: no deposit
    assert "locked until" in live.withdraw(HLP, 200).error  # withdrawals ignore the kill switch, not the lockup
    after = LiveVaultExecutor(ex, "0xacc", info=info, guard=guard, clock=lambda: T0 + 5 * DAY)
    f = after.withdraw(HLP, 250)  # more than held: capped at the account's equity
    assert f.ok and ex.sent[-1] == {"type": "vaultTransfer", "vaultAddress": HLP, "isDeposit": False, "usd": 200_000_000}
    with pytest.raises(LiveNotAllowed):
        make_vault_executor("live", {}, env={}, config={"mode": "dry_live"})


def test_a_deposit_a_dead_run_left_is_adopted_not_repeated(tmp_path, monkeypatch):
    clock = [T0 + 3600 + 300]
    info = FakeVaultInfo(clock[0], 100.0, 0.0)
    info.follower = {"vaultEquity": "200", "lockupUntil": 0}  # the dead run's deposit landed
    ex = FakeExchange(info)
    live = LiveVaultExecutor(ex, "0xacc", info=info, clock=lambda: clock[0])
    monkeypatch.setattr(broker_mod, "make_vault_executor", lambda route, cfg, *a: live)
    monkeypatch.setattr(broker_mod, "make_executor", lambda route, cfg, env=None: None)
    monkeypatch.delenv("TARTAR_LIVE_KILL", raising=False)
    (tmp_path / "config.json").write_text(json.dumps({"mode": "dry_live", "strategies": {"hlp": CFG}, "live": {"perps": {}}}))
    oid = f"vault_deposit|hlp|hlp:{int(T0 + 3600)}|{T0 + 3600:.0f}"
    VaultPending(tmp_path).add(oid, {"leg": "vault_deposit", "venue": "hyperliquid_vault", "usd": 200})
    pts = [(T0 + 3600, 100.0, 0.0), (clock[0], 100.0, 0.0)]
    run_once(tmp_path, now=clock[0], strategies={"hlp": VaultHold("hlp", {**CFG, "_fetch": history(pts)})})
    (pos,) = Ledger(tmp_path).positions
    assert pos.meta["live"]["adopted"] == oid and pos.meta["live"]["equity"] == 200
    assert ex.sent == [] and VaultPending(tmp_path).load() == {}
