"""The always-on box loop (tartar/autotrade/box.py), offline with fake Coinbase candles and a fake Alpaca paper API."""

import json
from datetime import datetime

from tartar.autotrade import alpaca
from tartar.autotrade.box import Box
from tests.test_autotrade_alpaca import FakeHttp, FakeResp
from tests.test_autotrade_coinbase import H0, bars


class Candles:
    def __init__(self, rows):
        self.rows = rows

    def get(self, url, params=None):
        t0 = datetime.fromisoformat(params["start"]).timestamp()
        t1 = datetime.fromisoformat(params["end"]).timestamp()
        return FakeResp(200, [[r[0], r[3], r[2], r[1], r[4], r[5]] for r in self.rows if t0 <= r[0] <= t1])


class Ok(FakeResp):
    def raise_for_status(self):
        pass


def make(tmp_path, crash=200):
    http = FakeHttp({"BTC/USD": 60.5})
    client = alpaca.AlpacaPaper("id", "secret", http=http, sleep=lambda s: None)
    c = Candles(bars(260, crash))
    c.get = (lambda f: (lambda url, params=None: Ok(f(url, params).status_code, f(url, params)._body)))(c.get)
    return Box(tmp_path, client, c, coins=["BTC"]), http


def rows(tmp_path):
    return [json.loads(x) for x in (tmp_path / "fills.jsonl").read_text().splitlines()]


def test_buys_minutes_after_the_crash_hour_and_sells_a_day_later(tmp_path):
    box, http = make(tmp_path)
    box.state["done_hour"] = H0 + 199
    t = (H0 + 201) * 3600 + 120
    box.step(t)
    (buy,) = [r for r in rows(tmp_path) if r["event"] == "buy"]
    assert buy["coin"] == "BTC" and buy["signal_hour"] == H0 + 200 and buy["latency_s"] == 120
    assert "BTC" in box.state["open"] and box.state["reconcile"]["ok"]
    box.step(t + 3600)  # no new entry while holding, nothing due
    assert len([r for r in rows(tmp_path) if r["event"] == "buy"]) == 1
    box.step(t + 24 * 3600)
    (sell,) = [r for r in rows(tmp_path) if r["event"] == "sell"]
    assert sell["coin"] == "BTC" and not box.state["open"] and not (tmp_path / "HALT").exists()
    assert all(u.startswith((alpaca.PAPER_URL, alpaca.DATA_URL)) for _, u in http.calls)


def test_no_signal_no_order(tmp_path):
    box, http = make(tmp_path, crash=10_000)
    box.state["done_hour"] = H0 + 199
    box.step((H0 + 201) * 3600 + 120)
    assert not http.orders and not box.state["open"]


def test_halt_file_stops_entries_and_a_stray_holding_writes_halt(tmp_path):
    box, http = make(tmp_path)
    (tmp_path / "HALT").write_text("by hand")
    box.state["done_hour"] = H0 + 199
    box.step((H0 + 201) * 3600 + 120)
    assert not http.orders and rows(tmp_path)[0]["event"] == "skip"
    (tmp_path / "HALT").unlink()
    http.held["BTCUSD"] = 5.0  # something the box never bought
    box.step((H0 + 202) * 3600 + 120)
    assert "differs" in (tmp_path / "HALT").read_text()


def test_a_live_account_key_sends_nothing(tmp_path):
    box, http = make(tmp_path)
    http.account = "LIVE1"
    box.state["done_hour"] = H0 + 199
    try:
        box.step((H0 + 201) * 3600 + 120)
    except RuntimeError as exc:
        assert "paper" in str(exc)
    assert not http.orders


def test_after_a_self_halt_the_box_does_nothing_and_repeated_errors_are_throttled(tmp_path):
    box, http = make(tmp_path)
    box.halt("test mismatch", 0.0)
    assert (tmp_path / "HALT").read_text().startswith("auto:")
    n = len(http.calls)
    box.step((H0 + 201) * 3600 + 120)
    assert len(http.calls) == n  # not even an account call
    for i in range(5):
        box.log({"event": "error", "at": 100.0 + 60 * i, "error": "same"})
    box.log({"event": "error", "at": 100.0 + 3700, "error": "same"})
    assert sum(r["event"] == "error" for r in rows(tmp_path)) == 2
