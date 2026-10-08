import pytest

from tartar.market import MarketNotFound, open_market

from conftest import OTHER_MINT, PUMP_MINT, WSOL, dex_pair, gecko_pool, gecko_tokens

POOL = "58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2"
OHLCV = {"data": {"attributes": {"ohlcv_list": [[60, 1, 1, 1, 1, 1], [0, 1, 1, 1, 1, 1]]}}}


def gecko_token_route(mint, pools):
    return {f"/api/v2/networks/solana/tokens/{mint}/pools": {"data": pools, "included": gecko_tokens((mint, "MEME", "Meme Coin"))}}


async def test_pump_token_on_bonding_curve_streams_from_chain(make_apis, monkeypatch):
    monkeypatch.delenv("PUMPPORTAL_API_KEY", raising=False)
    routes = {
        **gecko_token_route(PUMP_MINT, [gecko_pool("SMALL", PUMP_MINT, reserve="10"), gecko_pool("CURVE", PUMP_MINT, reserve="9000", dex="pump-fun")]),
        f"/tokens/v1/solana/{PUMP_MINT}": [dex_pair("CURVE", PUMP_MINT, dex="pumpfun")],
        "/api/v2/networks/solana/pools/CURVE/ohlcv/minute": OHLCV,
    }
    gecko, dex, router = make_apis(routes)
    market = await open_market(PUMP_MINT, 60, gecko=gecko, dex=dex)
    assert market.info.source == "solana-rpc" and market.info.quote == "SOL"
    assert market.info.symbol == "MEME" and market.info.pool == "CURVE"
    candles = await market.history()
    assert len(candles) == 2
    params = router.requests[-1].url.params
    assert params["currency"] == "token" and params["token"] == PUMP_MINT


async def test_graduated_or_regular_token_polls_dexscreener(make_apis):
    routes = {
        **gecko_token_route(OTHER_MINT, [gecko_pool("RAY", OTHER_MINT, reserve="50000")]),
        f"/tokens/v1/solana/{OTHER_MINT}": [
            dex_pair("THIN", OTHER_MINT, liquidity=10),
            dex_pair("RAY", OTHER_MINT, liquidity=50000),
            dex_pair("INVERTED", WSOL, liquidity=10**9),  # token is the quote here: ignored
        ],
        "/api/v2/networks/solana/pools/RAY/ohlcv/minute": OHLCV,
    }
    gecko, dex, router = make_apis(routes)
    market = await open_market(OTHER_MINT, 300, gecko=gecko, dex=dex)
    assert market.info.source == "dexscreener" and market.info.quote == "USD" and market.info.pool == "RAY"
    await market.history()
    assert router.requests[-1].url.params["currency"] == "usd"


async def test_pool_address_resolves_to_its_base_token(make_apis):
    routes = {f"/api/v2/networks/solana/pools/{POOL}": {"data": gecko_pool(POOL, OTHER_MINT), "included": []}}
    gecko, dex, _ = make_apis(routes)
    market = await open_market(POOL, 60, gecko=gecko, dex=dex)
    assert market.info.address == OTHER_MINT and market.info.source == "geckoterminal"
    assert any("lag" in note for note in market.info.notes)


async def test_unindexed_pump_token_starts_cold(make_apis):
    gecko, dex, _ = make_apis({})
    market = await open_market(PUMP_MINT, 60, gecko=gecko, dex=dex)
    assert market.info.source == "solana-rpc" and market.history is None
    assert any("starting cold" in note for note in market.info.notes)


async def test_unknown_token_is_an_error(make_apis):
    gecko, dex, _ = make_apis({})
    with pytest.raises(MarketNotFound):
        await open_market(OTHER_MINT, 60, gecko=gecko, dex=dex)
    with pytest.raises(MarketNotFound):
        await open_market(OTHER_MINT, 60, "dexscreener", gecko=gecko, dex=dex)


async def test_lookup_failures_are_reported_not_called_missing(make_apis):
    gecko, dex, _ = make_apis({f"/api/v2/networks/solana/tokens/{OTHER_MINT}/pools": 503, f"/tokens/v1/solana/{OTHER_MINT}": 503})
    with pytest.raises(MarketNotFound, match="could not look up.*HTTP 503"):
        await open_market(OTHER_MINT, 60, gecko=gecko, dex=dex)


async def test_api_failures_become_notes(make_apis):
    gecko, dex, _ = make_apis({f"/tokens/v1/solana/{PUMP_MINT}": 500, f"/latest/dex/pairs/solana/{PUMP_MINT}": 500})
    market = await open_market(PUMP_MINT, 60, gecko=gecko, dex=dex)
    assert market.info.source == "solana-rpc"
    assert any("DexScreener lookup failed" in note for note in market.info.notes)


async def test_timeframe_without_gecko_candles_has_no_history(make_apis):
    routes = {
        **gecko_token_route(PUMP_MINT, [gecko_pool("CURVE", PUMP_MINT)]),
        f"/tokens/v1/solana/{PUMP_MINT}": [dex_pair("CURVE", PUMP_MINT, dex="pumpfun")],
    }
    gecko, dex, _ = make_apis(routes)
    market = await open_market(PUMP_MINT, 30, gecko=gecko, dex=dex)
    assert market.history is None and any("30s" in note for note in market.info.notes)


async def test_rejects_non_addresses(make_apis):
    gecko, dex, router = make_apis({})
    with pytest.raises(ValueError, match="not a Solana address"):
        await open_market("../../etc/passwd", 60, gecko=gecko, dex=dex)
    assert router.requests == []


async def test_pumpportal_used_when_api_key_set(make_apis, monkeypatch):
    monkeypatch.setenv("PUMPPORTAL_API_KEY", "key")
    gecko, dex, _ = make_apis({})
    market = await open_market(PUMP_MINT, 60, gecko=gecko, dex=dex)
    assert market.info.source == "pumpportal" and market.info.domain == "trades"
