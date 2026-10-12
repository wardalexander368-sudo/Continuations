import httpx
import pytest

from tartar.feeds.dexscreener import BASE_URL as DEX_URL
from tartar.feeds.dexscreener import DexScreener
from tartar.feeds.geckoterminal import BASE_URL as GECKO_URL
from tartar.feeds.geckoterminal import GeckoTerminal
from tartar.feeds.http import JsonClient

WSOL = "So11111111111111111111111111111111111111112"
PUMP_MINT = "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"[:40] + "pump"
OTHER_MINT = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"


def gecko_pool(address, base, quote=WSOL, reserve="1000", dex="raydium", symbol="MEME", name="Meme Coin"):
    return {
        "id": f"solana_{address}",
        "type": "pool",
        "attributes": {
            "address": address,
            "name": f"{symbol} / SOL",
            "pool_created_at": "2026-10-08T05:00:00Z",
            "reserve_in_usd": reserve,
            "base_token_price_usd": "0.0001",
            "volume_usd": {"h24": "5000"},
        },
        "relationships": {
            "base_token": {"data": {"id": f"solana_{base}", "type": "token"}},
            "quote_token": {"data": {"id": f"solana_{quote}", "type": "token"}},
            "dex": {"data": {"id": dex, "type": "dex"}},
        },
    }


def gecko_tokens(*pairs):
    return [{"id": f"solana_{addr}", "type": "token", "attributes": {"address": addr, "symbol": sym, "name": name}} for addr, sym, name in pairs]


def dex_pair(address, base, dex="raydium", price_usd="0.0002", price_native="0.000001", liquidity=10000, volume=500.0, buys=10, sells=5):
    return {
        "chainId": "solana",
        "dexId": dex,
        "url": f"https://dexscreener.com/solana/{address}",
        "pairAddress": address,
        "baseToken": {"address": base, "name": "Meme Coin", "symbol": "MEME"},
        "quoteToken": {"address": WSOL, "name": "Wrapped SOL", "symbol": "SOL"},
        "priceNative": price_native,
        "priceUsd": price_usd,
        "txns": {"m5": {"buys": 1, "sells": 1}, "h24": {"buys": buys, "sells": sells}},
        "volume": {"h24": volume, "m5": 1.0},
        "liquidity": {"usd": liquidity, "base": 1, "quote": 1},
        "pairCreatedAt": 1759900000000,
    }


class Router:
    """Mock HTTP backend: exact path -> JSON (or status code), recording requests."""

    def __init__(self, routes):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        result = self.routes.get(request.url.path, 404)
        if callable(result):
            result = result(request)
        if isinstance(result, int):
            return httpx.Response(result, json={"errors": [{"status": str(result)}]})
        return httpx.Response(200, json=result)


@pytest.fixture
def make_apis():
    clients = []

    def factory(routes):
        router = Router(routes)
        transport = httpx.MockTransport(router)
        gecko = GeckoTerminal(JsonClient(GECKO_URL, retries=0, client=httpx.AsyncClient(transport=transport)))
        dex = DexScreener(JsonClient(DEX_URL, retries=0, client=httpx.AsyncClient(transport=transport)))
        clients.extend([gecko.http._client, dex.http._client])
        return gecko, dex, router

    yield factory
