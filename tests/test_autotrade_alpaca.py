"""The Alpaca paper mirror (tartar/autotrade/alpaca.py), offline with a fake paper API."""

import json

import pytest

from tartar.autotrade import alpaca
from tartar.autotrade.ledger import Ledger
from tartar.autotrade.runner import run_once
from tartar.autotrade.strategies.coinbase_pattern import CoinbasePattern
from tests.test_autotrade_coinbase import H0, bars


class FakeResp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body


class FakeHttp:
    """Paper API: market orders fill at ``px[symbol]`` times ``slip``; the buy fee comes out of the coin."""

    def __init__(self, px, account="PA123", slip=1.001):
        self.px, self.account, self.slip, self.calls, self.orders, self.held = px, account, slip, [], {}, {}

    def request(self, method, url, headers=None, json=None, params=None):
        self.calls.append((method, url))
        assert url.startswith((alpaca.PAPER_URL, alpaca.DATA_URL)) and "APCA-API-SECRET-KEY" in headers
        path = url.split(".markets", 1)[1]
        if path == "/v2/account":
            return FakeResp(200, {"account_number": self.account, "status": "ACTIVE"})
        if path.startswith("/v1beta3/crypto/us/latest/quotes"):
            s = params["symbols"]
            return FakeResp(200, {"quotes": {s: {"bp": self.px[s] * 0.9995, "ap": self.px[s] * 1.0005}}})
        if path.startswith("/v2/assets/"):
            return FakeResp(200, {"min_trade_increment": "0.000001"})
        if path == "/v2/positions":
            return FakeResp(200, [{"symbol": k, "qty": str(v), "asset_class": "crypto", "current_price": str(self.px[k[:-3] + "/USD"])}
                                  for k, v in self.held.items() if abs(v) > 1e-12])
        if path == "/v2/orders" and method == "GET":
            return FakeResp(200, list(getattr(self, "open", [])))
        if path.startswith("/v2/positions/"):
            sym = path.rsplit("/", 1)[1]
            return FakeResp(200, {"qty": str(self.held[sym])}) if self.held.get(sym) else FakeResp(404, {"message": "no position"})
        if path == "/v2/orders" and method == "POST":
            if json["client_order_id"] in {o["client_order_id"] for o in self.orders.values()}:
                return FakeResp(422, {"message": "client_order_id must be unique"})
            s, buy = json["symbol"], json["side"] == "buy"
            p = self.px[s] * (self.slip if buy else 2 - self.slip)
            q = float(json["notional"]) / p if buy else float(json["qty"])
            key = s.replace("/", "")
            self.held[key] = self.held.get(key, 0.0) + (q * (1 - 0.0025) if buy else -q)
            o = {"id": f"o{len(self.orders)}", "client_order_id": json["client_order_id"], "status": "filled",
                 "filled_qty": str(q), "filled_avg_price": str(p)}
            self.orders[o["id"]] = o
            return FakeResp(200, o)
        if path.startswith("/v2/orders/"):
            return FakeResp(200, self.orders[path.rsplit("/", 1)[1]])
        raise AssertionError(path)


def setup(tmp_path, account="PA123"):
    rows = bars(260, 200)
    (tmp_path / "config.json").write_text(json.dumps({"mode": "paper", "alpaca_paper": {"enabled": True, "strategies": ["c"]},
                                                      "strategies": {"c": {"kind": "coinbase_pattern"}}}))
    s = CoinbasePattern("c", {"_get": lambda ctx, coin, t0, t1: [r for r in rows if t0 <= r[0] < t1], "rule": "capit",
                              "coins": ["BTC"], "start": "2000-01-01", "end": "2100-01-01"})
    http = FakeHttp({"BTC/USD": 63.0}, account=account)
    return s, http, alpaca.AlpacaPaper("id", "secret", http=http, sleep=lambda s: None)


def test_mirror_buys_and_sells_on_the_paper_account_and_records_the_gap(tmp_path):
    s, http, client = setup(tmp_path)
    for h in range(H0 + 190, H0 + 240):
        run_once(tmp_path, now=h * 3600 + 1200, strategies={"c": s}, alpaca=client)
    (t,) = Ledger(tmp_path).trades()
    a = t.meta["alpaca"]
    assert t.mode == "paper" and a["symbol"] == "BTC/USD"
    assert a["entry_gap_bps"] == pytest.approx(10, abs=0.01) and a["exit_gap_bps"] == pytest.approx(10, abs=0.01)
    assert a["measured_side_cost"] == pytest.approx(0.0025 + 0.001, abs=1e-6)
    assert a["spread_in_bps"] == pytest.approx(10, abs=0.1)
    assert http.held["BTCUSD"] == pytest.approx(0, abs=1e-5)  # sold what the buy left after its fee
    rows = [json.loads(x) for x in (tmp_path / "alpaca_fills.jsonl").read_text().splitlines()]
    assert [r["event"] for r in rows] == ["buy", "sell"]
    assert "Alpaca paper fills" in (tmp_path / "REPORT.md").read_text()
    assert all(not u.startswith("https://api.alpaca.markets") for _, u in http.calls)


def test_a_key_that_is_not_a_paper_account_sends_nothing(tmp_path):
    s, http, client = setup(tmp_path, account="LIVE9")
    for h in range(H0 + 190, H0 + 240):
        run_once(tmp_path, now=h * 3600 + 1200, strategies={"c": s}, alpaca=client)
    (t,) = Ledger(tmp_path).trades()
    assert "alpaca" not in t.meta and not http.orders


def test_no_keys_no_mirror():
    cfg = {"alpaca_paper": {"enabled": True, "strategies": ["us_capit"]}}
    assert alpaca.make_mirror(cfg, {}) is None
    assert alpaca.make_mirror(cfg, {"APCA_API_KEY_ID": "x", "APCA_API_SECRET_KEY": ""}) is None
    assert alpaca.make_mirror({"alpaca_paper": {"enabled": False, "strategies": ["us_capit"]}}, {"APCA_API_KEY_ID": "x", "APCA_API_SECRET_KEY": "y"}) is None


def test_perps_venue_is_never_mirrored():
    m = alpaca.AlpacaMirror({**alpaca.ALPACA_DEFAULTS, "strategies": ["cde_vol_momentum"]}, None, None)
    assert not m.wants("cde_vol_momentum", {"venue": "coinbase_perps"})


def test_duplicate_client_order_id_returns_the_existing_order():
    http = FakeHttp({"BTC/USD": 100.0})
    c = alpaca.AlpacaPaper("id", "secret", http=http, sleep=lambda s: None)
    http.orders["o9"] = {"id": "o9", "client_order_id": "x", "status": "filled", "filled_qty": "1", "filled_avg_price": "100"}
    orig = http.request

    def request(method, url, **kw):
        if "by_client_order_id" in url:
            return FakeResp(200, http.orders["o9"])
        return orig(method, url, **kw)

    http.request = request
    assert c.submit("x", "BTC/USD", "buy", notional=10)["id"] == "o9"


def test_any_other_base_url_is_refused():
    c = alpaca.AlpacaPaper("id", "secret", http=FakeHttp({}), sleep=lambda s: None)
    with pytest.raises(ValueError):
        c._req("GET", "/v2/account", base="https://api.alpaca.markets")


def test_every_run_checks_the_key_and_reports_it(tmp_path):
    s, http, client = setup(tmp_path)
    run_once(tmp_path, now=(H0 + 190) * 3600 + 1200, strategies={"c": s}, alpaca=client)
    assert Ledger(tmp_path).state["alpaca"]["ok"] is True
    assert "Key check this run: paper account OK" in (tmp_path / "REPORT.md").read_text()
    (tmp_path / "x").mkdir()
    s, http, client = setup(tmp_path / "x", account="LIVE9")
    run_once(tmp_path / "x", now=(H0 + 190) * 3600 + 1200, strategies={"c": s}, alpaca=client)
    st = Ledger(tmp_path / "x").state["alpaca"]
    assert st["ok"] is False and "not an active paper account" in st["error"]
    assert not (tmp_path / "x" / "alpaca_fills.jsonl").exists()  # the hourly check alone writes no fill rows


def test_missing_secrets_show_in_state(tmp_path, monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    s, http, client = setup(tmp_path)
    run_once(tmp_path, now=(H0 + 190) * 3600 + 1200, strategies={"c": s})
    assert "not set" in Ledger(tmp_path).state["alpaca"]["error"]


def test_config_mirrors_only_us_spot_pattern_strategies():
    cfg = json.loads(open("autotrade/config.json").read())
    for name in cfg["alpaca_paper"]["strategies"]:
        assert cfg["strategies"][name]["kind"] == "coinbase_pattern", name


def test_account_matches_book_every_run_and_a_stray_holding_turns_health_red(tmp_path):
    s, http, client = setup(tmp_path)
    seen = []
    for h in range(H0 + 190, H0 + 240):
        run_once(tmp_path, now=h * 3600 + 1200, strategies={"c": s}, alpaca=client)
        rec = json.loads((tmp_path / "state.json").read_text())["alpaca"]["reconcile"]
        seen.append((bool(Ledger(tmp_path).positions), rec["ok"]))
    assert (True, True) in seen and all(ok for _, ok in seen)  # matched while holding and after the sell
    now = (H0 + 240) * 3600
    assert alpaca.health_items(tmp_path, now)[0]["level"] == "green"
    http.held["ETHUSD"] = 2.0  # something the book never bought
    http.px["ETH/USD"] = 2000.0
    run_once(tmp_path, now=now + 1200, strategies={"c": s}, alpaca=client)
    (item,) = alpaca.health_items(tmp_path, now + 1300)
    assert item["level"] == "red" and "ETHUSD" in item["detail"]
    assert "**differs**" in (tmp_path / "REPORT.md").read_text()


def test_an_order_open_for_hours_is_stuck(tmp_path):
    s, http, client = setup(tmp_path)
    http.open = [{"symbol": "BTCUSD", "side": "sell", "client_order_id": "x", "submitted_at": "2020-01-01T00:00:00Z"}]
    rec = alpaca.reconcile(client, [], 0.0025, 1.7e9)
    assert rec["ok"] is False and rec["stuck_orders"][0]["client_order_id"] == "x"


def test_a_failed_check_is_reported_not_raised(tmp_path):
    class Broken:
        cfg = {"taker_fee": 0.0025}

        def ready(self, now, quiet=False):
            return True

        @property
        def client(self):
            raise RuntimeError("boom")

    rec = alpaca.reconcile_safe(Broken(), [], 1.0)
    assert rec["ok"] is None and "boom" in rec["error"]
