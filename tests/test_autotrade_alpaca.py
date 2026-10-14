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
    assert a["paper_cost_evidence"] == "paper-fill-proxy" and a["fee_basis"] == "configured"
    assert a["configured_fee_per_side"] == 0.0025 and a["commission_paid_usd"] is None and a["commission_evidence"] == "unknown"
    assert a["spread_in_bps"] == pytest.approx(10, abs=0.1)
    assert http.held["BTCUSD"] == pytest.approx(0, abs=1e-5)  # sold what the buy left after its fee
    rows = [json.loads(x) for x in (tmp_path / "alpaca_fills.jsonl").read_text().splitlines()]
    assert [r["event"] for r in rows] == ["buy", "sell"]
    assert all(r["paper_cost_evidence"] == "paper-fill-proxy" and r["commission_evidence"] == "unknown" for r in rows)
    assert all(r["order_status"] == "filled" and r["fill_completion"] == "complete-requested-fill" for r in rows)
    assert all(r["broker_submitted_at"] is None and r["broker_filled_at"] is None for r in rows)
    assert all(r["observation_clock_basis"] == "local-run-observation" and r["terminal_inventory_evidence"] == "unknown" for r in rows)
    assert rows[1]["requested_qty"] == pytest.approx(rows[1]["filled_qty"])
    assert "Alpaca paper fills" in (tmp_path / "REPORT.md").read_text()
    assert all(not u.startswith("https://api.alpaca.markets") for _, u in http.calls)


def test_cost_report_labels_legacy_proxy_and_malformed_evidence(tmp_path):
    legacy = {"event": "sell", "measured_side_cost": 0.004, "entry_gap_bps": 10, "exit_gap_bps": 20,
              "fee_per_side": 0.0025, "alpaca_net_return": 0.01, "paper_net_return": 0.02}
    (tmp_path / "alpaca_fills.jsonl").write_text(json.dumps(legacy) + '\nnot json\n[1, 2]\n{"event": "sell"}\n')
    report = "\n".join(alpaca.report_lines(tmp_path))
    assert "2 malformed/non-object line(s), 1 unmeasured sell(s)" in report
    assert "paper_cost_evidence=unmeasured" in report
    assert "Mean modeled net" not in report and "actual commission paid is unknown" in report
    assert "Legacy records without completion proof remain unknown" in report
    assert "unknown receipt(s)" in report and "Terminal paper inventory: unknown" in report


def test_returned_order_metadata_preserves_broker_clocks_without_claiming_inventory():
    order = {"status": "filled", "qty": "2", "filled_qty": "2", "filled_avg_price": "100",
             "submitted_at": "2026-10-12T10:00:00Z", "filled_at": "2026-10-12T10:00:01Z"}
    evidence = alpaca._order_evidence(order, alpaca._fill(order))
    assert evidence["broker_submitted_at"] == order["submitted_at"] and evidence["broker_filled_at"] == order["filled_at"]
    assert evidence["broker_clock_basis"] == "broker-provided"
    assert evidence["requested_qty"] == evidence["filled_qty"] == 2
    assert evidence["fill_completion"] == "complete-requested-fill"
    assert evidence["terminal_inventory_qty"] is None and evidence["terminal_inventory_evidence"] == "unknown"


def test_partial_exit_is_recorded_and_rejected_without_changing_order_flow(tmp_path):
    from types import SimpleNamespace
    from tartar.autotrade import live_gate

    class PartialSell(FakeHttp):
        def request(self, method, url, headers=None, json=None, params=None):
            response = super().request(method, url, headers=headers, json=json, params=params)
            if method == "POST" and url.endswith("/v2/orders") and json["side"] == "sell":
                requested = float(json["qty"])
                response._body["status"] = "partially_filled"
                response._body["filled_qty"] = str(requested / 2)
                self.held[json["symbol"].replace("/", "")] += requested / 2
            return response

    http = PartialSell({"BTC/USD": 63.0})
    client = alpaca.AlpacaPaper("id", "secret", http=http, sleep=lambda _: None)
    mirror = alpaca.AlpacaMirror({**alpaca.ALPACA_DEFAULTS, "strategies": ["us_capit_fast"], "fill_wait_s": 0}, client, tmp_path)
    at = 1_791_800_000.0
    pos = SimpleNamespace(id="partial", strategy="us_capit_fast", asset="BTC", notional_usd=200,
                          meta={"venue": "coinbase", "signal_hour": 1})
    intent = SimpleNamespace(meta={}, price=63.0, at=at)
    mirror.on_open(pos, intent, at)
    trade = SimpleNamespace(net_return=0.0, meta={})
    mirror.on_close(pos, trade, intent, at + 86400)
    rows = [json.loads(line) for line in (tmp_path / "alpaca_fills.jsonl").read_text().splitlines()]
    assert len(http.orders) == 2 and [r["event"] for r in rows] == ["buy", "sell"]
    sell = rows[1]
    assert sell["order_status"] == "partially_filled" and sell["fill_completion"] == "partial-or-unfilled"
    assert sell["filled_qty"] == pytest.approx(sell["requested_qty"] / 2)
    assert sell["terminal_inventory_evidence"] == "unknown" and http.held["BTCUSD"] > 0
    rejected = []
    assert live_gate.round_trips(rows, rejected=rejected) == []
    assert rejected == [{"position": "partial", "why": "sell partial or unfilled"}]
    report = "\n".join(alpaca.report_lines(tmp_path))
    assert "1 partial/unfilled receipt(s)" in report and "0 validated complete requested-fill pair(s)" in report
    assert "Mean modeled net" not in report


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
    assert "Terminal paper inventory: unmatched" in (tmp_path / "REPORT.md").read_text()


@pytest.mark.parametrize("kind, level", (("missing", "yellow"), ("unconfirmed", "yellow"),
                                        ("stale", "yellow"), ("mismatch", "red"), ("complete", "green")))
def test_account_health_cannot_make_unknown_or_unconfirmed_inventory_green(tmp_path, kind, level):
    now = 1_791_800_000.0
    rec = {"checked_at": now, "ok": True, "valuation_evidence": "finite-inputs-checked",
           "unconfirmed": [], "mismatches": [], "stuck_orders": []}
    if kind == "unconfirmed":
        rec["unconfirmed"] = ["BTCUSD"]
    elif kind == "stale":
        rec["checked_at"] -= 4 * 3600
    elif kind == "mismatch":
        rec["mismatches"] = [{"symbol": "BTCUSD"}]
    state = {} if kind == "missing" else {"alpaca": {"reconcile": rec}}
    (tmp_path / "state.json").write_text(json.dumps(state))
    (item,) = alpaca.health_items(tmp_path, now)
    assert item["level"] == level and "terminal_inventory_evidence" in item


def test_an_order_open_for_hours_is_stuck(tmp_path):
    s, http, client = setup(tmp_path)
    http.open = [{"symbol": "BTCUSD", "side": "sell", "client_order_id": "x", "submitted_at": "2020-01-01T00:00:00Z"}]
    rec = alpaca.reconcile(client, [], 0.0025, 1.7e9)
    assert rec["ok"] is False and rec["stuck_orders"][0]["client_order_id"] == "x"


@pytest.mark.parametrize("price", [None, 0, "NaN", "Infinity", -100])
def test_unvalued_residual_holdings_are_unconfirmed_not_reconciled(price):
    from types import SimpleNamespace
    holding = {"symbol": "BTCUSD", "qty": "2.9625", "asset_class": "crypto"}
    if price is not None:
        holding["current_price"] = price
    fake = SimpleNamespace(positions=lambda: [holding], open_orders=lambda: [])
    rec = alpaca.reconcile(fake, [], 0.0025, 1_791_800_000.0)
    assert rec["ok"] is False and rec["unconfirmed"] == ["BTCUSD"]


def test_valued_residual_dust_retains_existing_one_dollar_allowance():
    from types import SimpleNamespace
    fake = SimpleNamespace(positions=lambda: [{"symbol": "BTCUSD", "qty": "0.00001", "current_price": "50000"}],
                           open_orders=lambda: [])
    rec = alpaca.reconcile(fake, [], 0.0025, 1_791_800_000.0)
    assert rec["ok"] is True and rec["mismatches"] == rec["unconfirmed"] == []


@pytest.mark.parametrize("quantity", ["NaN", "Infinity", "-1", True])
def test_invalid_held_quantity_is_unconfirmed(quantity):
    from types import SimpleNamespace
    fake = SimpleNamespace(positions=lambda: [{"symbol": "BTCUSD", "qty": quantity, "current_price": "50000"}],
                           open_orders=lambda: [])
    rec = alpaca.reconcile(fake, [], 0.0025, 1_791_800_000.0)
    assert rec["ok"] is False and rec["unconfirmed"] == ["BTCUSD"]


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


@pytest.mark.parametrize("quantities,held,price", [
    ([1e308], "0.9975", "100"),
    ([1e308, 1e308], "0.9975", "1"),
    ([1.0], "1e308", "100"),
    ([1e308], "9.975e307", "100"),
])
def test_nonfinite_derived_inventory_valuation_is_unconfirmed(quantities, held, price):
    from types import SimpleNamespace
    modeled = [SimpleNamespace(meta={"alpaca": {"symbol": "BTC/USD", "qty": qty, "price_in": 100.0}},
                               mark_price=100.0) for qty in quantities]
    fake = SimpleNamespace(positions=lambda: [{"symbol": "BTCUSD", "qty": held, "current_price": price}],
                           open_orders=lambda: [])
    rec = alpaca.reconcile(fake, modeled, 0.0025, 1_791_800_000.0)
    assert rec["ok"] is False and rec["unconfirmed"] == ["BTCUSD"]
    assert rec["valuation_evidence"] == "unknown"
