"""Live Hyperliquid orders for perp twins (``perps.py``): EIP-712 signing and an IOC taker executor.

Same interface as ``perps.DryPerpExecutor`` (``open``, ``close``, ``mid``, ``funding_usd``), so the broker
treats a live twin exactly like a dry one; only the fill comes from the exchange instead of a book walk.

* **Keys.** ``HYPERLIQUID_AGENT_KEY``: the private key of an API ("agent") wallet that the trading account
  approved on Hyperliquid; it can place and cancel orders but cannot withdraw. ``HYPERLIQUID_ACCOUNT``:
  the trading account's address (fills and positions are read for it). Nothing here holds the account's
  own key.
* **Gate.** ``make_live_perp_executor`` and every send call ``gate.require_live`` first (mode ``live``,
  ``live_approved_on`` == ``TARTAR_LIVE_APPROVED``, both keys). Opens also stop on any kill switch;
  closes don't, so a halted agent can still flatten.
* **Orders.** Immediate-or-cancel limit orders priced ``slippage`` (default 1%) through the mid, size
  rounded down to the coin's step, $10 minimum on opens, closes reduce-only. A partial fill is reported
  as filled at its size; an unfilled IOC is a failed leg (the broker logs it; a failed close becomes an
  orphan and halts the strategy). Fees come from ``userFills`` for the order id when available.
* **Network.** ``network: "testnet"`` (config ``live.perps.network``) points at
  api.hyperliquid-testnet.xyz and signs with the testnet source; used only by the CI test with a
  throwaway key (``.github/workflows/hl-testnet.yml``).

Signing follows Hyperliquid's L1 action scheme (as in the official Python SDK): msgpack of the action,
nonce and vault flag, keccak, wrapped as an EIP-712 ``Agent`` message (source "a" mainnet, "b" testnet,
chain id 1337). Needs the optional dependencies ``eth-account`` and ``msgpack`` (``pip install
.[live]``).
"""

from __future__ import annotations

import math
import time
from decimal import Decimal

from .gate import require_live
from .perps import MIN_ORDER_USD, PERP_DEFAULTS, HyperliquidInfo, PerpFill

URLS = {"mainnet": "https://api.hyperliquid.xyz", "testnet": "https://api.hyperliquid-testnet.xyz"}
PERP_KEYS = ("HYPERLIQUID_AGENT_KEY", "HYPERLIQUID_ACCOUNT")


def float_to_wire(x: float) -> str:
    rounded = f"{x:.8f}"
    if abs(float(rounded) - x) >= 1e-12:
        raise ValueError(f"float_to_wire would round {x}")
    if rounded == "-0.00000000":
        rounded = "0"
    return f"{Decimal(rounded).normalize():f}"


def round_px(px: float, sz_decimals: int) -> float:
    """A price Hyperliquid accepts for a perp: at most 5 significant figures and 6 - szDecimals decimals
    (integers always allowed)."""
    if px > 100_000:
        return float(round(px))
    return round(float(f"{px:.5g}"), 6 - sz_decimals)


def l1_typed_data(connection_id: bytes, mainnet: bool) -> dict:
    return {
        "domain": {"chainId": 1337, "name": "Exchange", "verifyingContract": "0x0000000000000000000000000000000000000000", "version": "1"},
        "types": {
            "Agent": [{"name": "source", "type": "string"}, {"name": "connectionId", "type": "bytes32"}],
            "EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                             {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}],
        },
        "primaryType": "Agent",
        "message": {"source": "a" if mainnet else "b", "connectionId": connection_id},
    }


class HyperliquidExchange:
    """Signs and posts L1 actions with an agent key."""

    def __init__(self, agent_key: str, network: str = "mainnet", http=None, clock=time.time):
        import httpx
        from eth_account import Account

        if network not in URLS:
            raise ValueError(f"unknown network {network!r}")
        self.network, self.url = network, URLS[network]
        self.wallet = Account.from_key(agent_key)
        self.http = http or httpx.Client(timeout=30)
        self.clock = clock
        self._last_nonce = 0

    @property
    def address(self) -> str:
        return self.wallet.address

    def nonce(self) -> int:
        n = max(int(self.clock() * 1000), self._last_nonce + 1)
        self._last_nonce = n
        return n

    def sign(self, action: dict, nonce: int) -> dict:
        import msgpack
        from eth_account.messages import encode_typed_data
        from eth_utils import keccak, to_hex

        h = keccak(msgpack.packb(action) + nonce.to_bytes(8, "big") + b"\x00")
        s = self.wallet.sign_message(encode_typed_data(full_message=l1_typed_data(h, self.network == "mainnet")))
        return {"r": to_hex(s.r), "s": to_hex(s.s), "v": s.v}

    def post(self, action: dict) -> dict:
        n = self.nonce()
        r = self.http.post(self.url + "/exchange", json={"action": action, "nonce": n, "signature": self.sign(action, n), "vaultAddress": None})
        r.raise_for_status()
        return r.json()

    def ioc(self, asset: int, is_buy: bool, px: float, sz: float, reduce_only: bool, cloid: str | None = None) -> dict:
        order = {"a": asset, "b": is_buy, "p": float_to_wire(px), "s": float_to_wire(sz), "r": reduce_only, "t": {"limit": {"tif": "Ioc"}}}
        if cloid:
            order["c"] = cloid  # client order id, last as in the official SDK's wire order
        return self.post({"type": "order", "orders": [order], "grouping": "na"})


def parse_order(resp: dict) -> tuple[dict | None, str | None]:
    """(filled {"totalSz", "avgPx", "oid"}, error)."""
    if resp.get("status") != "ok":
        return None, str(resp.get("response"))[:300]
    statuses = ((resp.get("response") or {}).get("data") or {}).get("statuses") or []
    st = statuses[0] if statuses else {}
    if "filled" in st:
        return st["filled"], None
    if "error" in st:
        return None, str(st["error"])[:300]
    if "resting" in st:  # an IOC never rests; treat it as a failure to look at
        return None, f"order resting (unexpected for IOC): {st['resting']}"
    return None, f"unexpected response: {str(resp)[:300]}"


class LivePerpExecutor:
    """IOC taker orders on Hyperliquid. ``guard(leg)`` re-checks the live gate right before each send."""

    name = "live"

    def __init__(self, exchange: HyperliquidExchange, account: str, info: HyperliquidInfo | None = None,
                 taker_fee: float = PERP_DEFAULTS["taker_fee"], slippage: float = 0.01, guard=None, clock=time.time):
        self.ex, self.account_addr = exchange, account
        self.info = info or HyperliquidInfo(url=exchange.url + "/info")
        self.taker_fee, self.slippage, self.clock = taker_fee, slippage, clock
        self.guard = guard or (lambda leg: None)
        self._assets: dict[str, int] | None = None

    def asset(self, coin: str) -> int:
        if self._assets is None:
            self._assets = {u["name"]: i for i, u in enumerate(self.info.post({"type": "meta"})["universe"])}
        return self._assets[coin]

    def mid(self, coin: str) -> float:
        bids, asks = self.info.book(coin)
        return (float(bids[0]["px"]) + float(asks[0]["px"])) / 2

    def _fee(self, oid, notional: float) -> float:
        try:
            fills = self.info.post({"type": "userFills", "user": self.account_addr}) or []
            fees = [float(f["fee"]) for f in fills if f.get("oid") == oid]
            if fees:
                return sum(fees)
        except Exception:  # noqa: BLE001 - fall back to the schedule
            pass
        return notional * self.taker_fee

    def account(self) -> dict:
        """{"positions": {coin: signed size}, "open_orders": [...]} for the trading account."""
        st = self.info.post({"type": "clearinghouseState", "user": self.account_addr}) or {}
        pos = {a["position"]["coin"]: float(a["position"]["szi"]) for a in st.get("assetPositions", []) if float(a["position"]["szi"])}
        return {"positions": pos, "open_orders": self.info.post({"type": "openOrders", "user": self.account_addr}) or []}

    def find(self, cloid_: str) -> PerpFill | None:
        """The fill of an earlier order with this client order id, or None if the venue never saw one."""
        res = self.info.post({"type": "orderStatus", "user": self.account_addr, "oid": cloid_}) or {}
        if res.get("status") != "order":
            return None
        o, status = res["order"]["order"], res["order"].get("status")
        got = float(o.get("origSz", 0)) - float(o.get("sz", 0))
        if got <= 0:
            return None  # cancelled unfilled (an IOC that missed): nothing to adopt, a resend is safe
        fills = [f for f in (self.info.post({"type": "userFills", "user": self.account_addr}) or []) if f.get("oid") == o.get("oid")]
        px = (sum(float(f["px"]) * float(f["sz"]) for f in fills) / sum(float(f["sz"]) for f in fills)) if fills else float(o.get("limitPx", 0))
        side = 1 if o.get("side") == "B" else -1
        return PerpFill("live", "found", o["coin"], side, True, px=px, sz=got, notional_usd=px * got,
                        fee_usd=sum(float(f["fee"]) for f in fills) if fills else px * got * self.taker_fee, at=self.clock(),
                        extra={"oid": o.get("oid"), "cloid": cloid_, "status": status, "found": True, "network": self.ex.network})

    def _send(self, leg: str, coin: str, side: int, sz: float | None = None, usd: float | None = None, cloid: str | None = None) -> PerpFill:
        """``side`` is the direction of this order (+1 buy, -1 sell)."""
        at = self.clock()
        try:
            self.guard(leg)
            mid = self.mid(coin)
            d = self.info.sz_decimals(coin)
            if usd is not None:
                sz = math.floor(usd / mid * 10 ** d) / 10 ** d
            sz = round(sz, d)
            if sz <= 0:
                return PerpFill("live", leg, coin, side, False, mid=mid, at=at, error="size rounds to 0")
            if leg == "open" and sz * mid < MIN_ORDER_USD:
                return PerpFill("live", leg, coin, side, False, mid=mid, at=at,
                                error=f"${sz * mid:.2f} after rounding is under Hyperliquid's ${MIN_ORDER_USD:.0f} minimum")
            px = round_px(mid * (1 + side * self.slippage), d)
            resp = self.ex.ioc(self.asset(coin), side > 0, px, sz, reduce_only=leg == "close", **({"cloid": cloid} if cloid else {}))
            filled, err = parse_order(resp)
            if err:
                return PerpFill("live", leg, coin, side, False, mid=mid, at=at, error=err, extra={"limit_px": px, "sz_sent": sz})
            got, avg = float(filled["totalSz"]), float(filled["avgPx"])
            notional = got * avg
            return PerpFill("live", leg, coin, side, True, px=avg, sz=got, notional_usd=notional, fee_usd=self._fee(filled.get("oid"), notional),
                            mid=mid, at=at, extra={"oid": filled.get("oid"), "limit_px": px, "sz_sent": sz, "partial": got < sz - 1e-12,
                                                   "slippage_bps": 1e4 * side * (avg / mid - 1), "network": self.ex.network})
        except Exception as exc:  # noqa: BLE001 - a failed send is a failed leg, logged by the broker
            return PerpFill("live", leg, coin, side, False, at=at, error=f"{type(exc).__name__}: {exc}"[:300])

    def open(self, coin: str, side: int, usd: float, cloid: str | None = None) -> PerpFill:
        return self._send("open", coin, side, usd=usd, cloid=cloid)

    def close(self, coin: str, side: int, sz: float, cloid: str | None = None) -> PerpFill:
        """Close a position of ``side`` (so trade the other way), reduce-only."""
        return self._send("close", coin, -side, sz=sz, cloid=cloid)

    def funding_usd(self, coin: str, side: int, notional_usd: float, t0: float, t1: float) -> float:
        return -side * notional_usd * self.info.funding_rate_sum(coin, t0, t1)


def make_live_perp_executor(config: dict, cfg: dict, env, root=None, http=None) -> LivePerpExecutor:
    """The live executor, only past the gate. ``config`` is the agent's whole config, ``cfg`` its ``live.perps``."""
    require_live(config, env, PERP_KEYS)

    def guard(leg: str) -> None:  # opens also honour the kill switches; closes must still be able to flatten
        require_live(config, env, PERP_KEYS, root if leg == "open" else None)

    network = cfg.get("network", "mainnet")
    ex = HyperliquidExchange(env["HYPERLIQUID_AGENT_KEY"], network=network, http=http)
    return LivePerpExecutor(ex, env["HYPERLIQUID_ACCOUNT"], taker_fee=cfg.get("taker_fee", PERP_DEFAULTS["taker_fee"]),
                            slippage=cfg.get("slippage", 0.01), guard=guard)
