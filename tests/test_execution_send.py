"""The real-order senders (tartar/autotrade/execution.py), offline: what gets signed, what gets sent, and
how each outcome (confirmed, failed, expired, unknown) comes back. Keys here are throwaway keypairs made
by the test; nothing touches a network."""

import base64
import json

import pytest
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import MessageV0, to_bytes_versioned
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction

from tartar.autotrade import broker as broker_mod
from tartar.autotrade.execution import STAND_IN, Chain, Fill, JupiterExecutor, LightningExecutor, check_tx
from tartar.autotrade.ledger import Ledger

from test_autotrade_live import NOW, opener, run, setup

MINT = "MintMintMintMintMintMintMintMintMintMintMint"
SYSTEM = Pubkey.from_string("11111111111111111111111111111111")


def unsigned_tx(payer: Pubkey, extra_signer: Pubkey | None = None) -> bytes:
    """An unsigned v0 transaction paid by ``payer`` (a 0-lamport transfer), like a swap API returns."""
    metas = [AccountMeta(payer, True, True), AccountMeta(payer, False, True)]
    if extra_signer:
        metas.append(AccountMeta(extra_signer, True, False))
    ix = Instruction(SYSTEM, bytes([2, 0, 0, 0]) + (0).to_bytes(8, "little"), metas)
    msg = MessageV0.try_compile(payer, [ix], [], Hash.default())
    return bytes(VersionedTransaction.populate(msg, [Signature.default()] * msg.header.num_required_signatures))


def chain_tx(wallet: str, sol_change: float, token_change: int, fee=5000):
    """A confirmed jsonParsed transaction moving ``wallet``'s SOL and ``MINT`` balance."""
    pre_tok = [{"accountIndex": 1, "mint": MINT, "owner": wallet, "uiTokenAmount": {"amount": "1000"}}]
    post_tok = [{"accountIndex": 1, "mint": MINT, "owner": wallet, "uiTokenAmount": {"amount": str(1000 + token_change)}}]
    return {"slot": 7, "transaction": {"message": {"accountKeys": [{"pubkey": wallet}, {"pubkey": "ATA"}]}},
            "meta": {"err": None, "fee": fee, "preBalances": [10**9, 2039280], "postBalances": [10**9 + int(sol_change * 1e9), 2039280],
                     "preTokenBalances": pre_tok, "postTokenBalances": post_tok}}


class FakeChain(Chain):
    """Scripted JSON-RPC. ``statuses`` are returned in turn by getSignatureStatuses (the last repeats)."""

    def __init__(self, statuses=(None,), tx=None, height=0, sim_err=None, held=(0, 6)):
        self.calls, self.statuses, self.tx, self.height, self.sim_err, self._held = [], list(statuses), tx, height, sim_err, held
        self.sleep = lambda s: None
        self.t = 0.0

    def clock(self):
        self.t += 1.0
        return self.t

    def confirm(self, signature, timeout=90.0, last_valid=None, clock=None):
        return super().confirm(signature, timeout, last_valid, clock=self.clock)

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "sendTransaction":
            return "SIG"
        if method == "getSignatureStatuses":
            st = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return {"value": [st]}
        if method == "getTransaction":
            return self.tx
        if method == "getBlockHeight":
            return self.height
        if method == "simulateTransaction":
            return {"value": {"err": self.sim_err, "unitsConsumed": 90_000, "logs": []}}
        if method == "getTokenAccountsByOwner":
            raw, dec = self._held
            return {"value": [{"account": {"data": {"parsed": {"info": {"tokenAmount": {"amount": str(raw), "decimals": dec}}}}}}]}
        if method == "getTokenSupply":
            return {"value": {"decimals": 6}}
        if method == "getBalance":
            return {"value": 5 * 10**7}
        raise AssertionError(method)

    def sent(self):
        return [VersionedTransaction.from_bytes(base64.b64decode(p[0])) for m, p in self.calls if m == "sendTransaction"]


class FakeQuotes:
    def __init__(self, tx_bytes, out=123_456, last_valid=1000):
        self.tx_bytes, self.out, self.last_valid, self.asked = tx_bytes, out, last_valid, []

    def quote(self, i, o, amount):
        self.asked.append((i, o, amount))
        return {"outAmount": str(self.out)}

    def swap(self, quote, wallet, priority):
        return self.tx_bytes, self.last_valid

    def sol_usd(self):
        return 150.0


CONFIRMED = {"confirmationStatus": "confirmed", "err": None}


def jupiter(kp, chain, tx_bytes=None):
    return JupiterExecutor(secret=str(kp), quotes=FakeQuotes(tx_bytes or unsigned_tx(kp.pubkey())), chain=chain)


# pre-sign checks

def test_check_tx_accepts_only_our_single_signer_transaction():
    me, other = Keypair(), Keypair()
    check_tx(unsigned_tx(me.pubkey()), str(me.pubkey()))
    with pytest.raises(RuntimeError, match="fee payer"):
        check_tx(unsigned_tx(other.pubkey()), str(me.pubkey()))
    with pytest.raises(RuntimeError, match="2 signatures"):
        check_tx(unsigned_tx(me.pubkey(), extra_signer=other.pubkey()), str(me.pubkey()))


def test_jupiter_refuses_to_sign_a_transaction_paid_by_someone_else():
    me = Keypair()
    chain = FakeChain()
    f = jupiter(me, chain, unsigned_tx(Keypair().pubkey())).buy(MINT, 0.01)
    assert not f.ok and not f.unknown and "fee payer" in f.error
    assert not chain.sent()


# Jupiter outcomes

def test_jupiter_buy_signs_with_our_key_sends_and_reads_the_fill_from_chain():
    me = Keypair()
    w = str(me.pubkey())
    chain = FakeChain(statuses=[None, CONFIRMED], tx=chain_tx(w, -0.010025, 5000))
    f = jupiter(me, chain).buy(MINT, 0.01)
    assert f.ok and f.signature == "SIG" and f.token_raw == 5000 and f.quote_out == 123_456
    assert f.sol == pytest.approx(0.010025) and f.fee_sol == pytest.approx(5e-6)
    (tx,) = chain.sent()
    assert tx.message.account_keys[0] == me.pubkey()
    assert tx.signatures[0].verify(me.pubkey(), to_bytes_versioned(tx.message))
    assert not any(m == "simulateTransaction" for m, _ in chain.calls)


def test_jupiter_on_chain_error_is_a_failure_not_unknown():
    me = Keypair()
    chain = FakeChain(statuses=[{"err": {"InstructionError": [3, {"Custom": 6001}]}}])
    f = jupiter(me, chain).buy(MINT, 0.01)
    assert not f.ok and not f.unknown and "6001" in f.error


def test_jupiter_expired_blockhash_is_a_definite_failure():
    me = Keypair()
    chain = FakeChain(statuses=[None], height=1001)  # last valid 1000, never landed
    f = jupiter(me, chain).buy(MINT, 0.01)
    assert not f.ok and not f.unknown and "expired" in f.error


def test_jupiter_landing_just_before_expiry_is_still_read():
    me = Keypair()
    w = str(me.pubkey())
    # three empty polls, then the height check sees expiry but the re-check finds it landed
    chain = FakeChain(statuses=[None, None, None, None, CONFIRMED], tx=chain_tx(w, -0.01, 10), height=1001)
    f = jupiter(me, chain).buy(MINT, 0.01)
    assert f.ok and f.token_raw == 10


def test_jupiter_no_answer_by_timeout_is_unknown():
    me = Keypair()
    q = FakeQuotes(unsigned_tx(me.pubkey()), last_valid=None)
    f = JupiterExecutor(secret=str(me), quotes=q, chain=FakeChain(statuses=[None])).buy(MINT, 0.01)
    assert not f.ok and f.unknown and f.signature == "SIG"


def test_jupiter_simulation_needs_no_key_and_sends_nothing():
    chain = FakeChain()
    ex = JupiterExecutor(simulate=True, quotes=FakeQuotes(unsigned_tx(Pubkey.from_string(STAND_IN))), chain=chain)
    f = ex.buy(MINT, 0.01)
    assert f.ok and f.dry and f.extra["simulated"] and f.token_raw == 123_456
    (sim,) = [p for m, p in chain.calls if m == "simulateTransaction"]
    assert sim[1]["sigVerify"] is False and sim[1]["replaceRecentBlockhash"] is True
    assert not chain.sent()


# Lightning

class FakeHTTP:
    def __init__(self, body=None, content=b"", raise_exc=None, code=200):
        self.body, self.content, self.raise_exc, self.code, self.posts = body, content, raise_exc, code, []

    def post(self, url, params=None, data=None, json=None):
        self.posts.append((url, params, data))
        if self.raise_exc:
            raise self.raise_exc
        outer = self

        class R:
            status_code = outer.code
            content = outer.content
            text = "x"

            def json(self):
                return outer.body

        return R()


def lightning(http, chain):
    return LightningExecutor("LWallet", api_key="k", http=http, chain=chain, quotes=FakeQuotes(b""))


def test_lightning_sells_only_the_twin_when_the_wallet_holds_more():
    chain = FakeChain(statuses=[CONFIRMED], tx=chain_tx("LWallet", 0.0099, -5_000_000), held=(12_000_000, 6))
    http = FakeHTTP({"signature": "SIG"})
    f = lightning(http, chain).sell(MINT, 5_000_000)
    assert http.posts[0][2]["amount"] == pytest.approx(5.0) and http.posts[0][2]["denominatedInSol"] == "false"
    assert f.ok and f.token_raw == 5_000_000


def test_lightning_sells_100_percent_when_the_twin_is_all_we_hold():
    chain = FakeChain(statuses=[CONFIRMED], tx=chain_tx("LWallet", 0.0099, -5_000_000), held=(5_000_000, 6))
    http = FakeHTTP({"signature": "SIG"})
    lightning(http, chain).sell(MINT, 5_000_000)
    assert http.posts[0][2]["amount"] == "100%"


def test_lightning_no_answer_is_unknown_and_an_error_body_is_a_failure():
    f = lightning(FakeHTTP(raise_exc=TimeoutError("read")), FakeChain()).buy(MINT, 0.01)
    assert not f.ok and f.unknown
    f = lightning(FakeHTTP({"errors": ["bad mint"]}), FakeChain()).buy(MINT, 0.01)
    assert not f.ok and not f.unknown and "no signature" in f.error


def test_lightning_simulation_uses_trade_local_for_a_stand_in_and_needs_no_key(monkeypatch):
    monkeypatch.delenv("PUMPPORTAL_API_KEY", raising=False)
    chain = FakeChain()
    http = FakeHTTP(content=unsigned_tx(Pubkey.from_string(STAND_IN)))
    ex = LightningExecutor(simulate=True, http=http, chain=chain, quotes=FakeQuotes(b""))
    f = ex.buy(MINT, 0.01)
    assert f.ok and f.dry and f.extra["simulated"]
    url, params, data = http.posts[0]
    assert url.endswith("/trade-local") and data["publicKey"] == STAND_IN and params is None
    s = ex.sell(MINT, 2_500_000)
    assert s.ok and s.dry and http.posts[1][2]["amount"] == pytest.approx(2.5)
    assert not chain.sent()


def test_lightning_needs_wallet_and_key_unless_simulating(monkeypatch):
    monkeypatch.delenv("PUMPPORTAL_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="lightning_wallet"):
        LightningExecutor(None, api_key="k")
    with pytest.raises(RuntimeError, match="PUMPPORTAL_API_KEY"):
        LightningExecutor("W")


# the broker on an unknown outcome

class UnknownExec:
    name, wallet = "fake", "W"

    def __init__(self):
        self.buys = []

    def balance_sol(self):
        return 0.05

    def sol_usd(self):
        return 100.0

    def buy(self, mint, sol):
        self.buys.append(mint)
        return Fill("fake", "buy", mint, False, unknown=True, signature="SIGX", error="not confirmed: outcome unknown")


def test_unknown_buy_is_kept_as_an_orphan_and_halts_the_strategy(tmp_path, monkeypatch):
    ex = UnknownExec()
    monkeypatch.setattr(broker_mod, "make_executor", lambda route, cfg, env=None: ex)
    for k in ("TARTAR_WALLET_KEY", "PUMPPORTAL_API_KEY", "TARTAR_LIVE_APPROVED", "TARTAR_LIVE_KILL"):
        monkeypatch.delenv(k, raising=False)
    root = setup(tmp_path)
    run(root, [[opener("a", "M1"), opener("b", "M2", at=NOW - 59)]])
    live = json.loads((root / "state.json").read_text())["live"]
    (orphan,) = live["orphans"]
    assert orphan["signature"] == "SIGX" and orphan["unknown"] and orphan["mint"] == "M1"
    assert "unknown" in live["strategies"]["s"]["halted"]
    assert ex.buys == ["M1"]  # the second entry was not tried blind
    assert all(p.mode == "paper" for p in Ledger(root).positions)


def test_the_shared_live_gate_is_checked_right_before_signing():
    from tartar.autotrade.gate import LiveNotAllowed

    me = Keypair()
    chain = FakeChain(statuses=[CONFIRMED], tx=chain_tx(str(me.pubkey()), -0.01, 10))
    ex = jupiter(me, chain)

    def closed():
        raise LiveNotAllowed("HALT_LIVE present")

    ex.guard = closed
    f = ex.buy(MINT, 0.01)
    assert not f.ok and not f.unknown and "HALT_LIVE" in f.error and not chain.sent()
    http = FakeHTTP({"signature": "SIG"})
    lx = lightning(http, FakeChain())
    lx.guard = closed
    assert "live gate" in lx.buy(MINT, 0.01).error and not http.posts


def test_live_broker_wires_the_gate_into_a_signing_executor(tmp_path, monkeypatch):
    from tartar.autotrade.broker import LiveBroker

    me = Keypair()
    ex = jupiter(me, FakeChain())
    monkeypatch.setattr(broker_mod, "make_executor", lambda route, cfg, env=None: ex)
    env = {"TARTAR_WALLET_KEY": "k", "TARTAR_LIVE_APPROVED": "2026-10-10"}
    cfg = {"mode": "live", "live_approved_on": "2026-10-10", "live": {}, "us_only": False}
    LiveBroker(cfg, ledger=Ledger(tmp_path), root=tmp_path, env=env)
    ex.guard()  # open now
    (tmp_path / "HALT_LIVE").write_text("stop")
    with pytest.raises(Exception, match="HALT_LIVE|kill"):
        ex.guard()
