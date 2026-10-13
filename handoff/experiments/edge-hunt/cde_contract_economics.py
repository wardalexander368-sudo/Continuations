"""Offline contract-size diagnostic from saved public Coinbase metadata and books.

Usage: python cde_contract_economics.py PRODUCTS_JSON BOOKS_DIR --target-notional 100
Books are ROOT-book.json; optional request receipts are ROOT-book.receipt.json.
No network, orders, assumed fees, or projected funding. A notional floor is not
account buying power. Quote sizes retain unknown units as ``raw_size``.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal, DecimalException, InvalidOperation, localcontext
from pathlib import Path

COINS = ("BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC", "BCH", "DOT")
SUFFIX = "20DEC30-CDE"


def number(value, name: str, *, allow_zero: bool = False) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name}: missing or invalid number")
    try:
        x = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name}: invalid number") from None
    if not x.is_finite() or x < 0 or (x == 0 and not allow_zero):
        raise ValueError(f"{name}: requires finite {'nonnegative' if allow_zero else 'positive'} number")
    return x


def exact(x: Decimal) -> str:
    return format(x, "f")


def best_level(levels, side: str) -> tuple[Decimal, object]:
    if not isinstance(levels, list) or not levels:
        raise ValueError(f"{side}: empty or invalid book")
    parsed = []
    for level in levels:
        if isinstance(level, dict):
            price, size = level.get("price"), level.get("size")
        elif isinstance(level, (list, tuple)) and len(level) >= 2:
            price, size = level[:2]
        else:
            raise ValueError(f"{side}: malformed level")
        px = number(price, f"{side} price")
        if size is not None:
            number(size, f"{side} raw_size")
        parsed.append((px, size))
    return (max if side == "bids" else min)(parsed, key=lambda row: row[0])


def margin(details: dict, key: str, notional: Decimal) -> dict:
    raw = details.get(key)
    value = raw.get("long_margin_rate") if isinstance(raw, dict) else None
    if value is None or value == "":
        return {"status": "unknown", "raw": raw, "fraction": None, "one_contract_margin_usd": None}
    rate = number(value, f"{key}.long_margin_rate", allow_zero=True)
    if rate > 1:
        raise ValueError(f"{key}.long_margin_rate: fraction above one")
    return {"status": "observed", "raw": raw, "fraction": exact(rate),
            "one_contract_margin_usd": exact(notional * rate)}


def receipt_fields(receipt: dict | None) -> dict:
    if not isinstance(receipt, dict):
        return {}
    return {k: receipt[k] for k in ("requested_at_utc", "completed_at_utc", "request_started_at", "request_completed_at",
                                   "url", "params", "status", "request_method", "request_url", "http_status",
                                   "response_date", "response_age", "response_content_type", "body_sha256", "body_bytes")
            if k in receipt}


def analyze(products, books_by_root: dict, target_notional="100", *, receipts_by_root=None, products_receipt=None) -> dict:
    """Return per-root errors explicitly; all arithmetic uses Decimal, no missing-value zero fill."""
    target = number(target_notional, "target_notional")
    rows = products.get("products") if isinstance(products, dict) else products
    if not isinstance(rows, list) or not all(isinstance(x, dict) for x in rows):
        raise ValueError("products: requires list of product objects")
    receipts_by_root = receipts_by_root or {}
    out = []
    with localcontext() as ctx:
        ctx.prec = 50
        for coin in COINS:
            result = {"root": coin}
            candidates = [x for x in rows if isinstance(x.get("future_product_details"), dict)
                          and x["future_product_details"].get("contract_root_unit") == coin
                          and str(x.get("product_id", "")).endswith(SUFFIX)]
            try:
                if len(candidates) != 1:
                    raise ValueError(f"product mapping: expected one match, found {len(candidates)}")
                product = candidates[0]
                details = product["future_product_details"]
                result["product_id"] = product["product_id"]
                if details.get("venue") != "cde" or product.get("product_type") != "FUTURE":
                    raise ValueError("product mapping: expected FUTURE on venue cde")
                multiplier = number(details.get("contract_size"), "contract_size")
                raw_book = books_by_root.get(coin)
                if not isinstance(raw_book, dict):
                    raise ValueError("book: missing or invalid object")
                book = raw_book.get("pricebook", raw_book)
                if not isinstance(book, dict):
                    raise ValueError("book: invalid pricebook")
                reported_id = book.get("product_id")
                if reported_id is not None and reported_id != product["product_id"]:
                    raise ValueError("book: product_id differs from mapped product")
                bid, bid_size = best_level(book.get("bids"), "bids")
                ask, ask_size = best_level(book.get("asks"), "asks")
                if bid > ask:
                    raise ValueError("book: crossed bid above ask")
                ctx.prec = max(50, len(ask.as_tuple().digits) + len(bid.as_tuple().digits)
                               + len(multiplier.as_tuple().digits) + len(target.as_tuple().digits) + 8)
                mid, notional = (bid + ask) / 2, ask * multiplier
                target_n, target_d = target.as_integer_ratio()
                notional_n, notional_d = notional.as_integer_ratio()
                count = (target_n * notional_d) // (target_d * notional_n)
                ctx.prec = max(ctx.prec, len(str(count)) + len(notional.as_tuple().digits) + 8)
                result.update(status="ok", contract_size_coins=exact(multiplier),
                              quote={"bid": exact(bid), "ask": exact(ask), "midpoint": exact(mid),
                                     "bid_raw_size": bid_size, "ask_raw_size": ask_size, "size_units": "unknown",
                                     "book_time": book.get("time"), "reported_product_id": reported_id,
                                     "local_receipt": receipt_fields(receipts_by_root.get(coin))},
                              one_contract_exposure_usd=exact(notional),
                              one_percent_adverse_move_loss_usd=exact(notional / 100),
                              max_whole_contracts_by_notional=count,
                              target_exposure_usd=exact(count * notional),
                              unused_target_notional_usd=exact(target - count * notional),
                              half_spread_bps=exact((ask - bid) / (2 * mid) * 10000),
                              immediate_cross_gross_return=exact(bid / ask - 1),
                              immediate_cross_loss_usd_one_contract=exact((ask - bid) * multiplier),
                              long_margin={k: margin(details, k, notional) for k in
                                           ("intraday_margin_rate", "overnight_margin_rate")},
                              funding_point_observations={k: details.get(k) for k in
                                                          ("funding_rate", "funding_time", "funding_interval", "perpetual_details")},
                              contract_metadata={k: details.get(k) for k in
                                                 ("contract_expiry", "contract_expiry_name", "contract_expiry_type", "contract_display_name")},
                              order_rules_raw={k: product.get(k) for k in
                                               ("base_min_size", "base_increment", "base_max_size", "price_increment")},
                              session_raw=product.get("fcm_trading_session_details"))
            except (ValueError, TypeError, DecimalException) as exc:
                # Partial arithmetic never appears as a valid zero-cost / zero-exposure row.
                result = {"root": coin, "status": "error", "error": str(exc),
                          "candidate_product_ids": [x.get("product_id") for x in candidates]}
            out.append(result)
    errors = sum(x["status"] == "error" for x in out)
    return {"schema_version": 1, "status": "error" if errors else "ok", "error_count": errors,
            "target_notional_usd": exact(target), "roots": list(COINS),
            "policy": {"sizing": "floor(target_notional / (best_ask * contract_size)); whole contracts",
                       "fee_assumption": None, "funding_projection": None, "funding_rate_units_or_period": "unknown",
                       "quote_size_units": "unknown",
                       "margin": "published long fractions only; not account buying power or liquidation model",
                       "limits": "snapshot diagnostic; no order-rule, fill, fee, account-capital or stop simulation"},
            "products_receipt": receipt_fields(products_receipt), "rows": out}


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"JSON duplicate key: {key}")
        out[key] = value
    return out


def reject_constant(value: str):
    raise ValueError(f"JSON nonstandard numeric constant: {value}")


def load_json(path: Path):
    return json.loads(path.read_text(), parse_float=Decimal,
                      object_pairs_hook=unique_object, parse_constant=reject_constant)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("products_json", type=Path)
    parser.add_argument("books_dir", type=Path)
    parser.add_argument("--target-notional", default="100")
    parser.add_argument("--products-receipt", type=Path)
    args = parser.parse_args()
    try:
        books, receipts = {}, {}
        for coin in COINS:
            p = args.books_dir / f"{coin}-book.json"
            if p.exists():
                try:
                    books[coin] = load_json(p)
                except ValueError:
                    books[coin] = None
            p = args.books_dir / f"{coin}-book.receipt.json"
            if p.exists():
                receipts[coin] = load_json(p)
        report = analyze(load_json(args.products_json), books, args.target_notional,
                         receipts_by_root=receipts,
                         products_receipt=load_json(args.products_receipt) if args.products_receipt else None)
    except (OSError, ValueError) as exc:
        report = {"schema_version": 1, "status": "error", "error": str(exc)}
    print(json.dumps(report, indent=2, sort_keys=True, default=lambda x: exact(x) if isinstance(x, Decimal) else str(x)))
    return 1 if report["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
