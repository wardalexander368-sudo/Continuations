"""End to end on Hyperliquid **testnet**, with a throwaway key made inside the test (never stored).

Runs only with HL_TESTNET=1 (the Action .github/workflows/hl-testnet.yml); skipped otherwise.

A fresh key has no testnet account, so the exchange answers every order with "User or API Wallet <address>
does not exist". That address is the one the exchange recovered from our EIP-712 signature: when it is the
throwaway key's own address, the order was encoded, hashed and signed exactly as Hyperliquid expects, and it
went through the whole live path (gate, route, broker, executor, fill log). A tampered signature recovers a
different address (the negative control). Real fills need a funded testnet account: see handoff/autotrade.md.
"""

import json
import os
import secrets

import pytest

if os.environ.get("HL_TESTNET") != "1":
    pytest.skip("testnet run only with HL_TESTNET=1", allow_module_level=True)

from eth_account import Account  # noqa: E402

from tartar.autotrade.broker import LiveBroker  # noqa: E402
from tartar.autotrade.core import CostModel, Intent  # noqa: E402
from tartar.autotrade.hl_exchange import HyperliquidExchange, URLS  # noqa: E402
from tartar.autotrade.ledger import Ledger  # noqa: E402


@pytest.fixture
def throwaway(tmp_path):
    key = "0x" + secrets.token_hex(32)
    addr = Account.from_key(key).address
    cfg = {"mode": "live", "live_approved_on": "testnet-ci", "strategies": {},
           "live": {"perps": {"network": "testnet", "max_leg_usd": 12, "dry_all": False}}}
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    env = {"TARTAR_LIVE_APPROVED": "testnet-ci", "HYPERLIQUID_AGENT_KEY": key, "HYPERLIQUID_ACCOUNT": addr}
    return tmp_path, cfg, env, key, addr


def test_order_through_the_agent_is_signed_as_the_throwaway_key(throwaway):
    root, cfg, env, key, addr = throwaway
    led = Ledger(root)
    led.strategy("s")["status"] = "promoted"
    b = LiveBroker(cfg, ledger=led, root=root, env=env)
    assert b.perp_route == "live" and b.perp_exec().ex.url == URLS["testnet"]
    from tartar.autotrade.perps import HyperliquidInfo

    mid = float(HyperliquidInfo(url=URLS["testnet"] + "/info").post({"type": "allMids"})["BTC"])
    it = Intent("open", "s", b.now, mid, "testnet e2e", asset="BTC", side=-1, notional_usd=100.0, cost=CostModel(fee=0.001),
                meta={"venue": "hyperliquid", "key": "BTC"})
    pos, row = b.open(it)
    err = row["live"].get("failed", "")
    print("exchange said:", err)
    assert addr.lower() in err.lower(), err  # the exchange recovered our address from the signature
    fills = [json.loads(x) for x in (root / "fills.jsonl").read_text().splitlines()]
    assert fills[-1]["event"] == "perp_open" and fills[-1]["fill"]["route"] == "live" and not fills[-1]["fill"]["ok"]


def test_tampered_signature_recovers_someone_else(throwaway):
    _, _, _, key, addr = throwaway
    ex = HyperliquidExchange(key, network="testnet")
    action = {"type": "order", "orders": [{"a": 3, "b": True, "p": "1000", "s": "0.001", "r": False, "t": {"limit": {"tif": "Ioc"}}}],
              "grouping": "na"}
    n = ex.nonce()
    sig = ex.sign(action, n)
    sig["s"] = hex(int(sig["s"], 16) ^ 1)
    r = ex.http.post(ex.url + "/exchange", json={"action": action, "nonce": n, "signature": sig, "vaultAddress": None}).json()
    print("tampered:", r)
    assert addr.lower() not in json.dumps(r).lower()

