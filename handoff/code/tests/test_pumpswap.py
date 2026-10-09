"""PumpSwap (graduated pump.fun tokens): event decoding, canonical pools, live feed."""

import json
from pathlib import Path

import pytest

from tartar.candles import Tick
from tartar.feeds.pumpswap import PUMP_AMM, PumpSwapFeed, SwapTrade, canonical_pool, swap_events_from_logs

DATA = Path(__file__).parent / "data"


def load(name):
    return json.loads((DATA / name).read_text())


def test_consecutive_trades_chain_their_reserves():
    buy_tx, sell_tx = load("pumpswap_buy.json"), load("pumpswap_sell.json")
    (buy,) = swap_events_from_logs(buy_tx["logs"])
    (sell,) = swap_events_from_logs(sell_tx["logs"])
    assert isinstance(buy, SwapTrade) and buy.is_buy and not sell.is_buy and buy.pool == sell.pool
    # The sell's pre-trade reserves are exactly the buy's post-trade reserves.
    assert sell.base_after - sell.base == pytest.approx(buy.base_after, abs=1e-6)
    assert sell.quote_after + sell.quote == pytest.approx(buy.quote_after, abs=1e-9)
    assert buy.price == pytest.approx(137.474161536 / 128879639.516385)
    assert buy.user_quote > buy.quote > 0 and 0 < sell.user_quote < sell.quote  # fees on top of buys, out of sells


def test_canonical_pool_matches_mainnet():
    tx = load("pumpswap_buy.json")
    (trade,) = swap_events_from_logs(tx["logs"])
    assert canonical_pool(tx["mint"]) == trade.pool == "FEmnAsVEXHDEZ9tS7cbs3NdUAhUAbRKU5P5Pqj1ZWQTK"


def test_only_pumpswap_frames_count():
    logs = load("pumpswap_buy.json")["logs"]
    data = [line for line in logs if line.startswith("Program data: ")]
    foreign = ["Program Other111111111111111111111111111111111 invoke [1]", *data, "Program Other111111111111111111111111111111111 success"]
    assert swap_events_from_logs(foreign) == []
    assert len(swap_events_from_logs([f"Program {PUMP_AMM} invoke [1]", *data, f"Program {PUMP_AMM} success"])) == 1


async def test_feed_turns_pool_trades_into_ticks():
    buy_tx, sell_tx = load("pumpswap_buy.json"), load("pumpswap_sell.json")
    mint = buy_tx["mint"]

    async def stream():
        yield 1.0, "b", swap_events_from_logs(buy_tx["logs"]), buy_tx["slot"]
        yield 2.0, "s", swap_events_from_logs(sell_tx["logs"])

    ticks = [t async for t in PumpSwapFeed(mint, stream=stream()).events()]
    assert [type(t) for t in ticks] == [Tick, Tick]
    assert ticks[0].buys == 1 and ticks[1].sells == 1 and ticks[0].price > 0 and ticks[0].liquidity == pytest.approx(137.474161536)
