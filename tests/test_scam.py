"""Scam detection: wallet behaviour, mint checks, RugCheck, creator history, launch screening."""

import json

import httpx
import pytest

from tartar.candles import Tick
from tartar.data.rawlog import RawWriter
from tartar.feeds.base import Status
from tartar.feeds.pumpchain import ChainCreate, ChainTrade
from tartar.scam import CreatorIndex, StaticReport, WalletTracker, assess, rugcheck_top10, static_checks
from tartar.screen import next_clean_launch

T0 = 1_760_000_000.0


def trade(ts, wallet, tokens, buy=True, creator=False, sol=None, price=1e-7, virtual_sol=40.0, liquidity=10.0):
    sol = tokens * price if sol is None else sol
    return Tick(
        ts, price, volume=sol, buy_volume=sol if buy else 0.0, sell_volume=0.0 if buy else sol,
        buys=int(buy), sells=int(not buy), trader=wallet, creator=creator, tokens=tokens,
        virtual_sol=virtual_sol, liquidity=liquidity,
    )  # fmt: skip


def test_tracker_measures_holders_snipes_and_creator():
    t = WalletTracker(launched_at=T0)
    t.update(trade(T0, "dev", 1000, creator=True))
    t.update(trade(T0 + 1, "sniper", 3000))
    t.update(trade(T0 + 30, "a", 500))
    t.update(trade(T0 + 31, "b", 500))
    t.update(trade(T0 + 60, "dev", 600, buy=False, creator=True))
    snap = t.snapshot()
    assert snap["sniper_share"] == pytest.approx(3000 / 5000)  # of all tokens bought, the creator's included
    assert t.holders == 4 and t.creator == "dev"
    assert snap["creator_share"] == pytest.approx(400 / 4400)
    assert t.creator_sold_share == pytest.approx(0.6)
    assert snap["nonstandard_curve"] == 0.0  # 40 virtual - 10 real = the standard 30


def test_tracker_round_trips_and_odd_curve():
    t = WalletTracker()
    for i in range(10):
        t.update(trade(T0 + 2 * i, "bot", 100))
        t.update(trade(T0 + 2 * i + 1, "bot", 100, buy=False, virtual_sol=5.0, liquidity=1.0))
    snap = t.snapshot()
    assert snap["wash_share"] == pytest.approx(0.5)
    assert snap["trades_per_wallet"] == 20
    assert snap["nonstandard_curve"] == 1.0
    assert t.snapshot()["sniper_share"] != t.snapshot()["sniper_share"]  # NaN: launch time unknown


def test_assess_flags_a_dump_and_a_clean_token():
    dump = WalletTracker(launched_at=T0)
    dump.update(trade(T0, "dev", 5000, creator=True))
    for i in range(20):
        dump.update(trade(T0 + 0.5 + i * 0.1, f"w{i}", 1000))
    dump.update(trade(T0 + 60, "dev", 5000, buy=False, creator=True, price=5e-8))  # -50%: dumped, not (yet) collapsed
    report = assess(dump)
    codes = {f.code for f in report.flags}
    # Alone, these mark worse trades but not later collapses: caution, still skipped by screens.
    assert {"dev_dumped", "sniped"} <= codes and report.level == "caution" and report.avoid

    clean = WalletTracker(launched_at=T0)
    clean.update(trade(T0, "dev", 100, creator=True))
    for i in range(30):
        clean.update(trade(T0 + 20 + i, f"w{i}", 100))
    assert assess(clean).level == "ok"
    assert assess(WalletTracker()).level == "unknown"


def test_assess_collapse_is_scam():
    t = WalletTracker()
    for i in range(12):
        t.update(trade(T0 + i, f"w{i}", 100, price=1e-6 if i < 11 else 5e-8))
    report = assess(t)
    assert report.level == "scam" and any(f.code == "collapsed" for f in report.flags)


def test_assess_static_mint_and_rugcheck():
    static = StaticReport(
        mint_authority="Auth111",
        freeze_authority=None,
        token_program="TokenzQd",
        extensions={"permanentDelegate": {"delegate": "x"}, "transferFeeConfig": {"newerTransferFee": {"transferFeeBasisPoints": 250}}},
        rugcheck={"rugged": False, "risks": [{"name": "Top 10 holders high ownership", "level": "danger"}, {"name": "Mutable metadata", "level": "warn"}], "graphInsidersDetected": 7},
    )
    report = assess(None, static)
    codes = {f.code for f in report.flags}
    assert {"mint_authority", "permanent_delegate", "transfer_fee", "insiders", "rugcheck_top_10_holders_high_ownership"} <= codes
    assert "rugcheck_mutable_metadata" not in codes  # too common to be a signal
    assert report.level == "scam"
    assert assess(None, StaticReport(token_program="Tokenkeg")).level == "ok"


def test_rugcheck_top10_excludes_pools_and_lockers():
    report = {
        "knownAccounts": {"CURVE": {"type": "AMM"}, "LOCK": {"type": "LOCKER"}},
        "markets": [{"pubkey": "POOL", "liquidityA": "VAULT"}],
        "topHolders": [
            {"address": "acc1", "owner": "CURVE", "pct": 60},
            {"address": "VAULT", "owner": "x", "pct": 20},
            {"address": "acc3", "owner": "whale", "pct": 8},
            {"address": "acc4", "owner": "fish", "pct": 2},
        ],
    }
    assert rugcheck_top10(report) == pytest.approx(0.10)


async def test_static_checks_parses_rpc_and_rugcheck():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            info = {"mintAuthority": None, "freezeAuthority": "Freezer", "extensions": [{"extension": "transferHook", "state": {"programId": "Hook"}}]}
            return httpx.Response(200, json={"result": {"value": {"owner": "TokenzQd", "data": {"parsed": {"info": info}}}}})
        if request.url.path.endswith("/report"):
            return httpx.Response(400)
        return httpx.Response(200, json={"score_normalised": 40, "risks": [], "rugged": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        static = await static_checks("Mint111", client=client)
    assert static.freeze_authority == "Freezer" and "transferHook" in static.extensions
    assert static.rugcheck["rugged"] and not static.errors  # fell back to the summary endpoint
    codes = {f.code for f in assess(None, static).flags}
    assert {"freeze_authority", "transfer_hook", "rugcheck_rugged"} <= codes


def _write_raw(directory, events):
    writer = RawWriter(directory, clock=lambda: T0)
    for event in events:
        writer.write(event)
    writer.close()


def test_creator_index_finds_rugs_and_copycats(tmp_path):
    def create(mint, creator, t, name="Coin", uri=""):
        return {"e": "create", "t": t, "mint": mint, "creator": creator, "name": name, "symbol": "C", "uri": uri, "sol": 1.0, "tok": 1e7, "vsol": 31.0, "vtok": 1.04e9}

    def tr(mint, t, trader, side, sol, vsol):
        return {"e": "trade", "t": t, "mint": mint, "side": side, "trader": trader, "sol": sol, "tok": 1e6, "vsol": vsol, "vtok": 32.19e9 / vsol}

    events = [
        create("RUG1", "badguy", T0, uri="ipfs://same"),
        tr("RUG1", T0 + 5, "fish", "b", 5.0, 36.0),
        tr("RUG1", T0 + 60, "badguy", "s", 1.2, 15.0),  # dev sells, price collapses >80% from peak
        create("NEW1", "badguy", T0 + 600, uri="ipfs://same"),
        create("OK1", "goodguy", T0, name="Other"),
        tr("OK1", T0 + 5, "fish", "b", 2.0, 33.0),
    ]
    _write_raw(tmp_path, events)
    index = CreatorIndex.from_raw(tmp_path)
    assert index.creators["badguy"].tokens == {"RUG1": True, "NEW1": False}
    report = assess(None, None, index, mint="NEW1", creator="badguy", name="Coin", symbol="C", uri="ipfs://same")
    codes = {f.code for f in report.flags}
    assert {"serial_rugger", "copycat"} <= codes and report.level == "danger"
    # Judging the rug itself does not count it as its own history.
    own = assess(None, None, index, mint="RUG1", creator="badguy", name="Coin", symbol="C")
    assert "serial_rugger" not in {f.code for f in own.flags}
    assert assess(None, None, index, mint="OK1", creator="goodguy", name="Other", symbol="C").level == "ok"


def _chain_trade(mint, user, sol, buy=True, creator="dev", vsol=31.0):
    return ChainTrade(mint, sol, sol * 3e7, buy, user, int(T0), vsol, 32.19e9 / vsol, creator, vsol - 30)


async def test_screening_skips_sniped_and_dead_launches():
    clock = [T0]

    async def stream():
        yield Status("connected")
        # Launch A: bundled, a sniper wallet takes most of the supply in the launch transaction.
        yield T0, "sigA", [ChainCreate("MintA", "A", "A", "dev", None), _chain_trade("MintA", "dev", 1.0), _chain_trade("MintA", "sniper", 20.0)]
        # Launch B: nobody buys.
        yield T0 + 1, "sigB", [ChainCreate("MintB", "B", "B", "dev2", None), _chain_trade("MintB", "dev2", 0.5, creator="dev2")]
        # Launch C: organic buyers arrive after a few seconds.
        yield T0 + 2, "sigC", [ChainCreate("MintC", "C", "C", "dev3", None), _chain_trade("MintC", "dev3", 0.5, creator="dev3")]
        for i in range(6):
            clock[0] = T0 + 10 + i
            yield T0 + 10 + i, f"s{i}", [_chain_trade("MintC", f"buyer{i}", 0.3, creator="dev3"), _chain_trade("MintA", f"late{i}", 0.1)]
        clock[0] = T0 + 40
        yield T0 + 40, "tick", [_chain_trade("MintC", "buyer9", 0.2, creator="dev3")]

    verdicts = []
    verdict = await next_clean_launch(stream(), screen_seconds=20, min_buyers=3, creators=CreatorIndex(), on_verdict=verdicts.append, clock=lambda: clock[0])
    assert verdict.candidate.create.mint == "MintC" and verdict.passed
    rejected = {v.candidate.create.mint: v.reason for v in verdicts if not v.passed}
    assert "sniped" in rejected["MintA"] or "danger" in rejected["MintA"]
    assert "buyer" in rejected["MintB"]
    ticks = verdict.candidate.ticks
    assert ticks[0].creator and len(ticks) == 8  # the dev's buy, six buyers, the last trade


async def test_agent_reports_risk(tmp_path):
    import asyncio
    import io

    from tartar.agent import CandleAgent
    from tartar.clock import SimClock
    from tartar.feeds.base import LiveFeed
    from tartar.market import Market, MarketInfo
    from tartar.output import JsonLines

    clock = SimClock(start=T0, speed=300)

    class Feed(LiveFeed):
        name = "script"

        async def events(self):
            yield trade(T0 + 1, "dev", 5000, creator=True)
            for i in range(5):
                yield trade(T0 + 2 + i, f"w{i}", 100)
            yield trade(T0 + 30, "dev", 5000, buy=False, creator=True, price=5e-8)
            while True:
                await clock.sleep(3600)

    out = io.StringIO()
    info = MarketInfo("MintZ", "Z", "", "SOL", "script", creator="dev", launched_at=T0)
    agent = CandleAgent(Market(info, Feed(), None, clock), 60, sinks=[JsonLines(out, every=0)], update_interval=0.02, scam_checks=False, p_rug=0.3)
    await asyncio.wait_for(agent.run(max_candles=2), timeout=10)
    risks = [json.loads(line) for line in out.getvalue().splitlines() if '"risk"' in line]
    assert risks and risks[-1]["level"] == "caution"
    assert any(f["code"] == "dev_dumped" for f in risks[-1]["flags"])
    assert risks[-1]["p_rug"] == 0.3  # the launch screen's P(rug) travels with the risk report
