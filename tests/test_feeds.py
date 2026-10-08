import asyncio
import json

import httpx
import pytest
from websockets.asyncio.server import serve

from tartar.clock import SimClock
from tartar.feeds.base import Status
from tartar.feeds.dexscreener import DexScreenerFeed, parse_pairs
from tartar.feeds.geckoterminal import GeckoTerminalFeed, parse_ohlcv, parse_pools
from tartar.feeds.http import ApiError, JsonClient, NotFound
from tartar.feeds.pumpportal import PumpPortalFeed, new_token_from_message, stream_new_tokens, tick_from_message
from tartar.candles import Tick

from conftest import PUMP_MINT, WSOL, dex_pair, gecko_pool, gecko_tokens


def test_parse_gecko_pools_with_included_tokens():
    payload = {
        "data": [gecko_pool("POOL1", PUMP_MINT, reserve="52000.5", dex="pumpswap")],
        "included": gecko_tokens((PUMP_MINT, "MEME", "Meme Coin"), (WSOL, "SOL", "Wrapped SOL")),
    }
    (pool,) = parse_pools(payload)
    assert pool.address == "POOL1" and pool.dex == "pumpswap"
    assert pool.base_token == PUMP_MINT and pool.quote_token == WSOL
    assert pool.base_symbol == "MEME" and pool.base_name == "Meme Coin" and pool.quote_symbol == "SOL"
    assert pool.reserve_usd == 52000.5 and pool.volume_24h_usd == 5000


def test_parse_gecko_ohlcv_sorts_aligns_and_drops_bad_rows():
    payload = {"data": {"attributes": {"ohlcv_list": [[120, 2, 3, 1.5, 2.5, 100], [61, 1, 2.2, 0.9, 2, 50], [0, 0, 0, 0, 0, 0]]}}}
    candles = parse_ohlcv(payload, 60)
    assert [c.start for c in candles] == [60, 120]
    assert candles[1].close == 2.5 and candles[1].volume == 100 and candles[1].trades is None
    with pytest.raises(ApiError):
        parse_ohlcv({"data": {}}, 60)


async def test_gecko_ohlcv_request_and_polling_feed(make_apis):
    ohlcv = {"data": {"attributes": {"ohlcv_list": [[300, 1, 1, 1, 1, 1]]}}}
    gecko, _, router = make_apis({"/api/v2/networks/solana/pools/POOL1/ohlcv/minute": ohlcv})
    feed = GeckoTerminalFeed(gecko, "POOL1", 300, token=PUMP_MINT, currency="token", poll_interval=1, clock=SimClock(speed=1000))
    events = feed.events()
    first = await events.__anext__()
    await events.aclose()
    assert first.candles[0].start == 300
    params = router.requests[0].url.params
    assert (params["aggregate"], params["token"], params["currency"], params["limit"]) == ("5", PUMP_MINT, "token", "3")
    with pytest.raises(ValueError):
        GeckoTerminalFeed(gecko, "POOL1", 120)


async def test_gecko_lookup_falls_back_to_pool(make_apis):
    pool = {"data": gecko_pool("POOL9", PUMP_MINT), "included": []}
    gecko, _, _ = make_apis({"/api/v2/networks/solana/pools/POOL9": pool})
    pools, is_token = await gecko.lookup("POOL9")
    assert not is_token and pools[0].base_token == PUMP_MINT


def test_parse_dexscreener_shapes():
    pair = dex_pair("PAIR1", PUMP_MINT, dex="pumpfun")
    assert parse_pairs([pair])[0].dex == "pumpfun"
    assert parse_pairs({"schemaVersion": "1.0.0", "pairs": [pair]})[0].address == "PAIR1"
    assert parse_pairs({"pair": pair})[0].price_usd == 0.0002
    assert parse_pairs({"pairs": None}) == []
    p = parse_pairs([pair])[0]
    assert p.buys_h24 == 10 and p.sells_h24 == 5 and p.liquidity_usd == 10000 and p.created_ms == 1759900000000


async def test_dexscreener_feed_turns_changes_into_ticks(make_apis):
    states = iter(
        [
            dex_pair("PAIR1", PUMP_MINT, price_usd="0.0002", volume=100, buys=10, sells=5),
            dex_pair("PAIR1", PUMP_MINT, price_usd="0.0002", volume=100, buys=10, sells=5),  # unchanged
            dex_pair("PAIR1", PUMP_MINT, price_usd="0.00025", volume=130, buys=13, sells=6),
        ]
    )
    _, dex, _ = make_apis({"/latest/dex/pairs/solana/PAIR1": lambda req: {"pairs": [next(states)]}})
    feed = DexScreenerFeed(dex, "PAIR1", poll_interval=1, clock=SimClock(speed=1000))
    events = feed.events()
    baseline = await events.__anext__()
    tick = await events.__anext__()
    await events.aclose()
    assert baseline.trades == 0 and baseline.price == 0.0002
    assert tick.price == 0.00025 and tick.trades == 4 and tick.volume == 30
    assert tick.buy_volume == pytest.approx(22.5) and tick.sell_volume == pytest.approx(7.5)


async def test_http_client_retries_and_not_found():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if request.url.path == "/missing":
            return httpx.Response(404)
        if calls["n"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"ok": True})

    client = JsonClient("https://example.test", retries=2, backoff=0.01, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await client.get("data") == {"ok": True}
    assert calls["n"] == 2
    with pytest.raises(NotFound):
        await client.get("missing")


def test_pumpportal_messages():
    trade = {
        "signature": "sig",
        "mint": PUMP_MINT,
        "traderPublicKey": "trader",
        "txType": "buy",
        "tokenAmount": 3_500_000.0,
        "solAmount": 0.1,
        "vTokensInBondingCurve": 1_000_000_000.0,
        "vSolInBondingCurve": 30.0,
        "marketCapSol": 30.0,
        "pool": "pump",
    }
    tick = tick_from_message(trade, now=5.0)
    assert tick == Tick(5.0, 3e-8, volume=0.1, buy_volume=0.1, sell_volume=0.0)
    no_curve = {**trade, "txType": "sell", "vSolInBondingCurve": None, "vTokensInBondingCurve": None}
    tick = tick_from_message(no_curve, now=6.0)
    assert tick.price == pytest.approx(0.1 / 3_500_000) and tick.sell_volume == 0.1
    assert tick_from_message({"message": "Successfully subscribed"}, 0) is None

    create = {**trade, "txType": "create", "name": "Meme Coin", "symbol": "MEME", "solAmount": 1.5}
    token = new_token_from_message(create)
    assert token.mint == PUMP_MINT and token.symbol == "MEME" and token.price == 3e-8 and token.initial_buy_sol == 1.5
    assert new_token_from_message(trade) is None


async def test_pumpportal_feed_against_local_websocket():
    received = []

    async def handler(ws):
        received.append(json.loads(await ws.recv()))
        await ws.send(json.dumps({"message": "Successfully subscribed to keys."}))
        base = {"txType": "buy", "solAmount": 0.5, "tokenAmount": 1e6, "vSolInBondingCurve": 31.0, "vTokensInBondingCurve": 1e9}
        await ws.send(json.dumps({**base, "mint": "SomeOtherMint"}))
        await ws.send(json.dumps({**base, "mint": PUMP_MINT}))
        await ws.send("not json")
        await ws.send(json.dumps({**base, "mint": PUMP_MINT, "txType": "sell", "vSolInBondingCurve": 30.5}))
        await ws.wait_closed()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        seed = Tick(1.0, 2.9e-8)
        feed = PumpPortalFeed(PUMP_MINT, url=f"ws://127.0.0.1:{port}", api_key="", initial=[seed])
        events = []
        async for event in feed.events():
            events.append(event)
            if sum(isinstance(e, Tick) for e in events) == 3:
                break
    assert received == [{"method": "subscribeTokenTrade", "keys": [PUMP_MINT]}]
    assert events[0] is seed
    assert any(isinstance(e, Status) and "connected" in e.message for e in events)
    ticks = [e for e in events if isinstance(e, Tick)][1:]
    assert [t.price for t in ticks] == [pytest.approx(31e-9), pytest.approx(30.5e-9)]
    assert ticks[1].sell_volume == 0.5


async def test_stream_new_tokens_against_local_websocket():
    async def handler(ws):
        assert json.loads(await ws.recv()) == {"method": "subscribeNewToken"}
        await ws.send(json.dumps({"message": "ok"}))
        await ws.send(json.dumps({"txType": "create", "mint": "NEWpump", "name": "New", "symbol": "NEW", "marketCapSol": 28.0}))
        await ws.wait_closed()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        async for token in stream_new_tokens(url=f"ws://127.0.0.1:{port}", api_key=""):
            break
    assert token.mint == "NEWpump" and token.price == pytest.approx(28e-9)
