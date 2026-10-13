import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "handoff/experiments/edge-hunt/cde_contract_economics.py"
spec = importlib.util.spec_from_file_location("cde_contract_economics", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def inputs():
    products, books = [], {}
    for coin in m.COINS:
        pid = f"{coin}-20DEC30-CDE"
        products.append({"product_id": pid, "product_type": "FUTURE", "base_min_size": "1", "base_increment": "1",
                         "future_product_details": {"venue": "cde", "contract_root_unit": coin, "contract_size": "0.01",
                                                    "contract_expiry": "2089-12-30T16:00:00Z", "contract_expiry_name": "2030-12",
                                                    "funding_rate": "0.000015", "funding_time": "2026-10-13T01:00:00Z",
                                                    "perpetual_details": {"funding_rate": "", "funding_time": None},
                                                    "intraday_margin_rate": {"long_margin_rate": "0.1"}}})
        books[coin] = {"pricebook": {"product_id": pid, "time": "2026-10-13T01:00:00Z",
                                    "bids": [{"price": "79900", "size": "4"}],
                                    "asks": [{"price": "80000", "size": "5"}]}}
    return products, books


def test_notional_floor_margin_is_not_exposure_and_metadata_preserved():
    products, books = inputs()
    receipt = {"requested_at_utc": "request", "completed_at_utc": "response", "request_started_at": "start",
               "request_completed_at": "end", "http_status": 200, "request_url": "https://example.test/public/book"}
    r = m.analyze(products, books, receipts_by_root={"BTC": receipt})
    assert r["status"] == "ok" and r["error_count"] == 0
    b = r["rows"][0]
    assert b["one_contract_exposure_usd"] == "800.00"
    assert b["max_whole_contracts_by_notional"] == 0 and b["target_exposure_usd"] == "0.00"
    assert b["long_margin"]["intraday_margin_rate"]["one_contract_margin_usd"] == "80.000"
    assert b["long_margin"]["overnight_margin_rate"]["status"] == "unknown"
    assert b["long_margin"]["overnight_margin_rate"]["fraction"] is None
    assert b["contract_metadata"]["contract_expiry"] == "2089-12-30T16:00:00Z"
    assert b["contract_metadata"]["contract_expiry_name"] == "2030-12"
    assert b["funding_point_observations"]["funding_rate"] == "0.000015"
    assert b["funding_point_observations"]["perpetual_details"]["funding_rate"] == ""
    assert b["quote"]["size_units"] == "unknown" and b["quote"]["ask_raw_size"] == "5"
    assert b["quote"]["book_time"] == "2026-10-13T01:00:00Z"
    assert b["quote"]["local_receipt"]["completed_at_utc"] == "response"
    assert b["quote"]["local_receipt"]["request_started_at"] == "start"
    assert b["quote"]["local_receipt"]["request_completed_at"] == "end"
    assert b["quote"]["local_receipt"]["http_status"] == 200
    assert b["quote"]["local_receipt"]["request_url"] == receipt["request_url"]
    assert r["policy"]["fee_assumption"] is None and r["policy"]["funding_projection"] is None
    assert r["policy"]["funding_rate_units_or_period"] == "unknown"


def test_two_contracts_fit_exact_floor_and_exchange_book():
    products, books = inputs()
    products[0]["future_product_details"]["contract_size"] = "0.5"
    books["BTC"] = {"bids": [["98", "1", 2]], "asks": [["100", "2", 3]]}
    b = m.analyze(products, books)["rows"][0]
    assert b["one_contract_exposure_usd"] == "50.0"
    assert b["max_whole_contracts_by_notional"] == 2 and b["target_exposure_usd"] == "100.0"
    assert b["immediate_cross_gross_return"] == "-0.02"
    assert b["immediate_cross_loss_usd_one_contract"] == "1.0"
    assert b["one_percent_adverse_move_loss_usd"] == "0.5"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0", "oops", None, True])
def test_invalid_contract_multiplier_never_becomes_zero(value):
    products, books = inputs()
    products[0]["future_product_details"]["contract_size"] = value
    r = m.analyze(products, books)
    assert r["status"] == "error" and r["error_count"] == 1
    assert r["rows"][0]["status"] == "error" and "max_whole_contracts_by_notional" not in r["rows"][0]


@pytest.mark.parametrize("badbook", [None, {}, {"bids": [], "asks": []},
                                      {"bids": [["101", "1"]], "asks": [["100", "1"]]},
                                      {"bids": [["NaN", "1"]], "asks": [["100", "1"]]},
                                      {"bids": [["99", "1"]], "asks": [["0", "1"]]},
                                      {"bids": [["99", "0"]], "asks": [["100", "1"]]}])
def test_invalid_books_explicit_error(badbook):
    products, books = inputs()
    books["BTC"] = badbook
    r = m.analyze(products, books)
    assert r["error_count"] == 1 and r["rows"][0]["status"] == "error"


def test_missing_and_duplicate_roots_do_not_select_a_product():
    products, books = inputs()
    products.pop(0)
    assert m.analyze(products, books)["rows"][0]["error"] == "product mapping: expected one match, found 0"
    products, books = inputs()
    products.append(copy.deepcopy(products[0]))
    assert m.analyze(products, books)["rows"][0]["error"] == "product mapping: expected one match, found 2"


def test_wrong_quote_identity_and_invalid_margin_are_errors():
    products, books = inputs()
    books["BTC"]["pricebook"]["product_id"] = "ETH-20DEC30-CDE"
    assert m.analyze(products, books)["rows"][0]["status"] == "error"
    products, books = inputs()
    products[0]["future_product_details"]["overnight_margin_rate"] = {"long_margin_rate": "NaN"}
    assert m.analyze(products, books)["rows"][0]["status"] == "error"


def test_decimal_boundary_floor_and_deterministic_output():
    products, books = inputs()
    products[0]["future_product_details"]["contract_size"] = "1"
    books["BTC"] = {"bids": [["49.99", "1"]], "asks": [["50.00000000000000000001", "1"]]}
    first = m.analyze(products, books)
    assert first["rows"][0]["max_whole_contracts_by_notional"] == 1
    assert first == m.analyze(products, books)


@pytest.mark.parametrize("value", ["NaN", "0", "-100", "Infinity", True])
def test_invalid_target_rejected(value):
    products, books = inputs()
    with pytest.raises(ValueError, match="target_notional"):
        m.analyze(products, books, value)


def test_duplicate_multiplier_cli_cannot_turn_800_exposure_into_80(tmp_path, monkeypatch, capsys):
    products, books = inputs()
    product_path = tmp_path / "products.json"
    # A last-wins parser makes BTC's contract look like $80 rather than $800,
    # falsely admitting a contract at the $100 notional cap.
    body = json.dumps({"products": products}).replace(
        '"contract_size": "0.01"', '"contract_size": "0.01", "contract_size": "0.001"', 1)
    product_path.write_text(body)
    for coin, book in books.items():
        (tmp_path / f"{coin}-book.json").write_text(json.dumps(book))
    with pytest.raises(ValueError, match="JSON duplicate key: contract_size"):
        m.load_json(product_path)
    monkeypatch.setattr(sys, "argv", [str(PATH), str(product_path), str(tmp_path)])
    assert m.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error" and report["error"] == "JSON duplicate key: contract_size"
    assert "rows" not in report


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_constants_rejected_even_in_uninterpreted_metadata(tmp_path, literal):
    product_path = tmp_path / "metadata.json"
    product_path.write_text('{"unused_metadata": ' + literal + '}')
    with pytest.raises(ValueError, match="JSON nonstandard numeric constant"):
        m.load_json(product_path)


def test_malformed_json_cli_emits_standard_error_json(tmp_path, monkeypatch, capsys):
    product_path = tmp_path / "products.json"
    product_path.write_text('{"products": [')
    monkeypatch.setattr(sys, "argv", [str(PATH), str(product_path), str(tmp_path)])
    assert m.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error" and report["error"]
