import pytest

from tartar.candles import Candle, CandleBook, Tick, fill_gaps, format_timeframe, load_csv, parse_timeframe


def test_timeframes():
    assert parse_timeframe("1m") == 60
    assert parse_timeframe("15s") == 15
    assert parse_timeframe(" 4H ") == 14400
    assert format_timeframe(300) == "5m"
    assert format_timeframe(90) == "90s"
    with pytest.raises(ValueError):
        parse_timeframe("1w")
    with pytest.raises(ValueError):
        parse_timeframe("2s")


def test_ticks_build_candles_and_close_on_next_period():
    book = CandleBook(60)
    assert book.add_tick(Tick(0, 10, volume=1, buy_volume=1)) == []
    book.add_tick(Tick(10, 12, volume=2, sell_volume=2))
    book.add_tick(Tick(20, 9))
    book.add_tick(Tick(59, 11))
    closed = book.add_tick(Tick(61, 11.5))
    assert len(closed) == 1
    c = closed[0]
    assert (c.start, c.open, c.high, c.low, c.close) == (0, 10, 12, 9, 11)
    assert c.trades == 4 and c.volume == 3 and c.buy_volume == 1 and c.sell_volume == 2
    assert book.current.start == 60 and book.current.open == 11.5


def test_gaps_become_flat_candles():
    book = CandleBook(60)
    book.add_tick(Tick(5, 10))
    closed = book.add_tick(Tick(200, 13))
    assert [c.start for c in closed] == [0, 60, 120]
    assert all(c.close == 10 and not c.active for c in closed[1:])
    assert book.current.start == 180


def test_clock_closes_candle_after_grace_and_fills_quiet_periods():
    book = CandleBook(60, grace=2)
    book.add_tick(Tick(5, 10))
    assert book.advance(61) == []
    closed = book.advance(62)
    assert [c.start for c in closed] == [0]
    assert book.view().start == 60 and not book.view().active
    closed = book.advance(185)
    assert [c.start for c in closed] == [60, 120]
    assert book.deadline() == 180 + 60 + 2


def test_late_ticks_are_ignored():
    book = CandleBook(60)
    book.add_tick(Tick(70, 10))
    assert book.add_tick(Tick(30, 99)) == []
    assert book.current.high == 10


def test_snapshots_upsert_and_ignore_revisions():
    book = CandleBook(60, counts_trades=False)
    closed = book.add_snapshot([Candle(0, 1, 2, 1, 2, volume=5), Candle(60, 2, 3, 2, 3, volume=1)])
    assert [c.start for c in closed] == [0]
    book.add_snapshot([Candle(60, 2, 4, 2, 3.5, volume=2)])
    assert book.current.high == 4
    closed = book.add_snapshot([Candle(0, 9, 9, 9, 9), Candle(180, 3, 3, 3, 3, volume=1)])
    assert [c.start for c in closed] == [60, 120]
    assert closed[1].trades is None  # unknown, not zero, for a source without trade counts
    assert closed[0].close == 3.5


def test_snapshot_seed_then_ticks():
    book = CandleBook(60)
    book.add_snapshot([Candle(0, 1, 1, 1, 1, volume=3), Candle(60, 1, 2, 1, 2, volume=3)])
    book.add_tick(Tick(90, 2.5))
    assert book.current.start == 60 and book.current.high == 2.5 and book.current.trades == 1


def test_fill_gaps_sorts_and_dedupes():
    candles = [Candle(120, 3, 3, 3, 3), Candle(0, 1, 1, 1, 1), Candle(0, 2, 2, 2, 2)]
    out = fill_gaps(candles, 60)
    assert [c.start for c in out] == [0, 60, 120]
    assert out[0].close == 2 and out[1].close == 2


def test_load_csv(tmp_path):
    path = tmp_path / "c.csv"
    path.write_text("Timestamp,Open,High,Low,Close,Volume\n1700000000000,1,2,0.5,1.5,10\n2023-11-14T22:14:20Z,1.5,1.6,1.4,1.45,\n")
    candles = load_csv(path)
    assert candles[0].start == 1700000000 and candles[0].volume == 10
    assert candles[1].start == 1700000060 and candles[1].close == 1.45
