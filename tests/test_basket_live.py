"""The hedged JLP basket's live path: the JLP leg through the gated Jupiter USDC sender, its restart safety,
and the rule that a basket never stays unhedged (a failed or short hedge unwinds the basket). Offline: dry
routes with fake quotes and a fake Hyperliquid book, and the live USD executor against a fake chain."""

import json

import pytest
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from tartar.autotrade import broker as broker_mod
from tartar.autotrade.core import CostModel, Intent, Verdict
from tartar.autotrade.execution import USDC, DryExecutor
from tartar.autotrade.ledger import Ledger
from tartar.autotrade.perps import DryPerpExecutor
from tartar.autotrade.runner import run_once
from tartar.autotrade.strategies.jlp_hedged import JLP_MINT
from tartar.autotrade.usd_spot import DryUsdSpotExecutor, LiveUsdSpotExecutor

from test_execution_send import CONFIRMED, FakeChain, unsigned_tx

NOW = 100_000.0
MARK = {"SOL": 150.0, "ETH": 2500.0, "BTC": 60000.0}


class Killed(BaseException):
    pass


class Quotes:
    """JLP at 4.0 USDC (6 decimals both); SOL at 150 USDC."""

    def quote(self, a, b, amount):
        if a == USDC and b == JLP_MINT:
            return {"outAmount": str(int(amount / 4.0)), "priceImpactPct": "0"}
        if a == JLP_MINT and b == USDC:
            return {"outAmount": str(int(amount * 4.0)), "priceImpactPct": "0"}
        if b == USDC:  # SOL -> USDC
            return {"outAmount": str(int(amount / 1e9 * 150 * 1e6))}
        return {"outAmount": str(int(amount))}

    def sol_usd(self):
        return 150.0


class Book:
    """Hyperliquid book; ``fail`` coins raise, ``thin`` coins fill half (``PartialPerp``)."""

    fail: set = set()
    thin: set = set()

    def book(self, coin):
        if coin in self.fail:
            raise RuntimeError(f"{coin} book unavailable")
        m, sz = MARK[coin], "1000"
        return [{"px": str(m * 0.9995), "sz": sz}], [{"px": str(m * 1.0005), "sz": sz}]

    def sz_decimals(self, coin):
        return 5

    def funding_rate_sum(self, coin, t0, t1):
        return 0.0


class PartialPerp(DryPerpExecutor):
    """Fills only half of an order on a ``Book.thin`` coin, as a thin IOC would."""

    def _take(self, leg, coin, side, sz=None, usd=None):
        f = super()._take(leg, coin, side, sz=sz, usd=usd)
        if f.ok and coin in Book.thin and leg == "open":
            f.sz, f.notional_usd = f.sz / 2, f.notional_usd / 2
        return f


class KillableUsd(DryUsdSpotExecutor):
    kill = None
    buys = 0

    def buy(self, mint, usd):
        f = super().buy(mint, usd)
        KillableUsd.buys += 1
        if KillableUsd.kill == "buy_after":
            raise Killed
        return f


class Strat:
    def __init__(self, script):
        self.name, self.prereg, self.script = "jlp", "test", list(script)

    def step(self, ctx):
        return self.script.pop(0) if self.script else []

    def marks(self, ctx):
        return {}

    def evaluate(self, trades, now, state):
        return Verdict("pending", len(trades), {}, "test")


def jlp_open(at=NOW - 60):
    return Intent("open", "jlp", at, 4.0, "basket", asset="JLP", side=1, notional_usd=200.0, cost=CostModel(fee=0.001),
                  meta={"key": "jlp:JLP", "venue": "jupiter_usd", "mint": JLP_MINT, "basket": "jlp", "twin_usd": 100.0})


def short(coin, at=NOW - 60, usd=20.0):
    return Intent("open", "jlp", at, MARK[coin], "basket", asset=coin, side=-1, notional_usd=usd * 2, cost=CostModel(fee=0.00045),
                  meta={"key": f"jlp:{coin}", "venue": "hyperliquid", "coin": coin, "basket": "jlp", "twin_usd": usd})


def basket(at=NOW - 60):
    return [jlp_open(at), short("SOL", at), short("ETH", at), short("BTC", at)]


def close(coin, at=NOW):
    return Intent("close", "jlp", at, MARK.get(coin, 4.0), "end", cost=CostModel(fee=0.001), meta={"key": f"jlp:{coin}"})


@pytest.fixture
def dry(monkeypatch):
    Book.fail, Book.thin = set(), set()
    KillableUsd.kill, KillableUsd.buys = None, 0
    monkeypatch.setattr(broker_mod, "make_executor", lambda route, cfg, env=None: DryExecutor(quotes=Quotes(), priority_sol=0.0))
    monkeypatch.setattr(broker_mod, "make_perp_executor", lambda route, cfg, env=None, *a: PartialPerp(Book(), clock=lambda: NOW))
    monkeypatch.setattr(broker_mod, "make_usd_spot_executor", lambda route, *a, **k: KillableUsd(Quotes(), clock=lambda: NOW))
    for k in ("TARTAR_LIVE_KILL", "GITHUB_RUN_ID", "TARTAR_WALLET_KEY", "TARTAR_LIVE_APPROVED"):
        monkeypatch.delenv(k, raising=False)


def setup(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"mode": "dry_live", "strategies": {}, "live": {"perps": {}}}))
    led = Ledger(tmp_path)
    led.strategy("jlp")["status"] = "paper"
    led.save()
    return tmp_path


def go(root, script, now):
    return run_once(root, now=now, strategies={"jlp": Strat(script)})


def twins(root):
    return {p.asset: p.meta["live"] for p in Ledger(root).positions if p.meta.get("live")}


def wallet(root):
    return json.loads((root / "dry_wallet.json").read_text())["tokens"]


def perp_account(root):
    return json.loads((root / "dry_perp_account.json").read_text())["positions"]


def live(root):
    return json.loads((root / "state.json").read_text())["live"]


def test_the_whole_basket_gets_twins_and_the_jlp_tokens_sit_in_the_wallet(tmp_path, dry):
    root = setup(tmp_path)
    s = go(root, [basket()], NOW)
    t = twins(root)
    assert set(t) == {"JLP", "SOL", "ETH", "BTC"} and not s["new_halts"]
    assert wallet(root) == {JLP_MINT: 25_000_000} and set(perp_account(root)) == {"SOL", "ETH", "BTC"}
    s = go(root, [[]], NOW + 300)  # reconcile: wallet and account match the book
    assert "reconcile" not in s and "perp_reconcile" not in s


def test_a_failed_hedge_unwinds_the_basket_and_stops_it(tmp_path, dry):
    root = setup(tmp_path)
    Book.fail = {"ETH"}
    s = go(root, [basket()], NOW)
    assert not twins(root), "something stayed live"
    assert wallet(root) == {} and perp_account(root) == {}
    assert "basket jlp unwound: hedge ETH failed" in live(root)["strategies"]["jlp"]["halted"] and s["new_halts"]
    assert len(Ledger(root).positions) == 4  # the paper basket is untouched
    rows = [json.loads(x) for x in (root / "fills.jsonl").read_text().splitlines()]
    assert sorted(r["position"] for r in rows if r["event"] == "basket_unwind")  # JLP and SOL were closed


def test_a_short_hedge_fill_unwinds_the_basket(tmp_path, dry):
    root = setup(tmp_path)
    Book.thin = {"BTC"}
    go(root, [basket()], NOW)
    assert not twins(root) and wallet(root) == {} and perp_account(root) == {}
    assert "filled $" in live(root)["basket_broken"]["jlp"]


def test_a_partial_unwind_close_leaves_the_rest_as_an_orphan(tmp_path, dry, monkeypatch):
    root = setup(tmp_path)
    Book.fail = {"BTC"}
    orig = PartialPerp._take

    def half_close(self, leg, coin, side, sz=None, usd=None):
        f = orig(self, leg, coin, side, sz=sz, usd=usd)
        if f.ok and leg == "close" and coin == "SOL":
            f.sz, f.notional_usd = f.sz / 2, f.notional_usd / 2
        return f

    monkeypatch.setattr(PartialPerp, "_take", half_close)
    go(root, [basket()], NOW)
    (o,) = [o for o in live(root)["orphans"] if o.get("coin") == "SOL"]
    assert o["sz"] == pytest.approx(perp_account(root)["SOL"] * -1) and "closed" in o["error"] and "SOL" not in twins(root)
    s = go(root, [[]], NOW + 300)  # the orphan is the account's remaining SOL short: no mismatch
    assert "perp_reconcile" not in s


def test_no_hedge_without_its_jlp_leg(tmp_path, dry, monkeypatch):
    root = setup(tmp_path)
    monkeypatch.setattr(KillableUsd, "buy", lambda self, mint, usd: __import__("tartar.autotrade.usd_spot", fromlist=["UsdFill"]).UsdFill(
        "dry", "buy", mint, False, error="no route"))
    go(root, [basket()], NOW)
    assert not twins(root) and perp_account(root) == {}
    rows = [json.loads(x) for x in (root / "fills.jsonl").read_text().splitlines()]
    assert sum("spot leg has no live twin" in r.get("reason", "") for r in rows) == 3


def test_killed_after_the_jlp_buy_landed_next_run_adopts_it(tmp_path, dry):
    root = setup(tmp_path)
    KillableUsd.kill = "buy_after"
    with pytest.raises(Killed):
        go(root, [basket()], NOW)
    assert wallet(root) == {JLP_MINT: 25_000_000} and not Ledger(root).positions
    KillableUsd.kill = None
    s = go(root, [basket()], NOW + 300)
    assert KillableUsd.buys == 1, "bought JLP twice"
    t = twins(root)
    assert t["JLP"]["adopted"] and set(t) == {"JLP", "SOL", "ETH", "BTC"}
    assert s["reconcile"]["claims"] == 1 and not s["new_halts"]


def test_jlp_tokens_nobody_explains_halt_live_entries(tmp_path, dry):
    root = setup(tmp_path)
    go(root, [basket()], NOW)
    w = json.loads((root / "dry_wallet.json").read_text())
    w["tokens"][JLP_MINT] += 1000
    (root / "dry_wallet.json").write_text(json.dumps(w))
    s = go(root, [[]], NOW + 300)
    assert s["reconcile"]["orphans"] == 1 and "untracked holding" in live(root)["halted"]


def test_existing_dry_jlp_twins_are_seeded_into_the_wallet_once(tmp_path, dry):
    root = setup(tmp_path)
    go(root, [basket()], NOW)
    (root / "dry_wallet.json").write_text(json.dumps({"sol": 0.05, "tokens": {}}))  # as on main before this change
    s = go(root, [[]], NOW + 300)
    assert wallet(root) == {JLP_MINT: 25_000_000} and "reconcile" not in s


def test_closing_the_basket_sells_jlp_and_closes_the_shorts(tmp_path, dry):
    root = setup(tmp_path)
    go(root, [basket()], NOW)
    s = go(root, [[close("SOL"), close("ETH"), close("BTC"), close("JLP")]], NOW + 300)
    assert wallet(root) == {} and perp_account(root) == {} and not s["new_halts"]
    jlp = next(t for t in Ledger(root).trades() if t.asset == "JLP")
    assert jlp.meta["live"]["usd_out"] == pytest.approx(100.0 - 0.003)


def test_perps_without_a_solana_key_keep_the_whole_basket_on_paper(tmp_path, dry):
    from tartar.autotrade.broker import LiveBroker

    b = LiveBroker({"mode": "dry_live", "live": {}}, ledger=Ledger(tmp_path), root=tmp_path, env={})
    b.usd_route = None  # as in mode live with Hyperliquid keys only
    pos, row = b.open(jlp_open(), [])
    assert "no USD spot route" in row["live"]["skipped"]
    _, row = b.open(short("SOL"), [pos])
    assert "basket leg" in row["live"]["skipped"]


# the live USD executor

def usdc_tx(wallet, usdc_change, jlp_change, fee=5000):
    def bal(mint, owner, amt, idx):
        return {"accountIndex": idx, "mint": mint, "owner": owner, "uiTokenAmount": {"amount": str(amt)}}

    return {"slot": 9, "transaction": {"message": {"accountKeys": [{"pubkey": wallet}, {"pubkey": "A1"}, {"pubkey": "A2"}]}},
            "meta": {"err": None, "fee": fee, "preBalances": [10**9, 2039280, 2039280], "postBalances": [10**9 - fee, 2039280, 2039280],
                     "preTokenBalances": [bal(USDC, wallet, 500_000_000, 1), bal(JLP_MINT, wallet, 0, 2)],
                     "postTokenBalances": [bal(USDC, wallet, 500_000_000 + usdc_change, 1), bal(JLP_MINT, wallet, jlp_change, 2)]}}


class SwapQuotes(Quotes):
    def __init__(self, tx):
        self.tx = tx

    def swap(self, q, wallet, priority):
        return self.tx, 1000


def test_live_usd_buy_reads_usdc_and_jlp_from_the_chain_and_checks_the_gate():
    me = Keypair()
    w = str(me.pubkey())
    chain = FakeChain(statuses=[CONFIRMED], tx=usdc_tx(w, -100_000_000, 25_000_000))
    ex = LiveUsdSpotExecutor(secret=str(me), quotes=SwapQuotes(unsigned_tx(me.pubkey())), chain=chain)
    f = ex.buy(JLP_MINT, 100.0)
    assert f.ok and f.token_raw == 25_000_000 and f.usd == pytest.approx(100.0 + 0.000005 * 150, rel=1e-6) and f.signature == "SIG"
    ex.guard = lambda: (_ for _ in ()).throw(RuntimeError("HALT_LIVE present"))
    chain2 = FakeChain(statuses=[CONFIRMED], tx=usdc_tx(w, -1, 1))
    ex.chain = chain2
    f = ex.buy(JLP_MINT, 100.0)
    assert not f.ok and "HALT_LIVE" in f.error and not chain2.sent()


def test_live_usd_executor_refuses_someone_elses_transaction_and_reports_unknown():
    me = Keypair()
    ex = LiveUsdSpotExecutor(secret=str(me), quotes=SwapQuotes(unsigned_tx(Keypair().pubkey())), chain=FakeChain())
    f = ex.buy(JLP_MINT, 100.0)
    assert not f.ok and "fee payer" in f.error
    q = SwapQuotes(unsigned_tx(me.pubkey()))
    q.swap = lambda *a: (unsigned_tx(me.pubkey()), None)
    f = LiveUsdSpotExecutor(secret=str(me), quotes=q, chain=FakeChain(statuses=[None])).buy(JLP_MINT, 100.0)
    assert not f.ok and f.unknown and f.signature == "SIG"
