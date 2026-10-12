#!/usr/bin/env python3
"""Costed displayed-book research replay; no order submission or claimed fills."""
import argparse
import bisect
import collections
import datetime as dt
from decimal import Decimal, ROUND_DOWN
import json
import math
import pathlib
import random

D = lambda x: Decimal(str(x))


def stamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def levels(book, side):
    rows = [(D(x["p"]), D(x["s"])) for x in book.get(side, [])]
    if any(not p.is_finite() or not s.is_finite() or p <= 0 or s < 0 for p, s in rows):
        raise ValueError("invalid book level")
    summed = collections.defaultdict(Decimal)
    for price, size in rows:
        summed[price] += size
    return sorted(((p, s) for p, s in summed.items() if s > 0), reverse=side == "b")


def features(book, band_bps=100):
    bids, asks = levels(book, "b"), levels(book, "a")
    if not bids or not asks or bids[0][0] >= asks[0][0]:
        raise ValueError("missing, locked or crossed book")
    bp, bs = bids[0]; ap, ass = asks[0]
    mid = (bp + ap) / 2
    band = D(band_bps) / 10000
    bnear = sum((p*s for p, s in bids if p >= mid*(1-band)), Decimal(0))
    anear = sum((p*s for p, s in asks if p <= mid*(1+band)), Decimal(0))
    ball = sum((p*s for p, s in bids), Decimal(0))
    aall = sum((p*s for p, s in asks), Decimal(0))
    microprice = (ap*bs + bp*ass)/(bs+ass)
    return {"mid": float(mid), "bid": float(bp), "ask": float(ap), "bid_size": float(bs), "ask_size": float(ass),
        "spread_bps": float((ap-bp)/mid*10000), "near_bid_usd": float(bnear), "near_ask_usd": float(anear),
        "near_bid_share": float(bnear/(bnear+anear)) if bnear+anear else None,
        "all_levels_bid_share": float(ball/(ball+aall)),
        "microprice_gap_bps": float((microprice-mid)/mid*10000)}


def snapshot_ofi(current, previous):
    """Cont-style best-level proxy; sampled changes miss intrapoll events."""
    return ((current["bid_size"] if current["bid"] >= previous["bid"] else 0)
        - (previous["bid_size"] if current["bid"] <= previous["bid"] else 0)
        - (current["ask_size"] if current["ask"] <= previous["ask"] else 0)
        + (previous["ask_size"] if current["ask"] >= previous["ask"] else 0))


def sweep_buy(book, cash, fee=0.0025, adverse=0.0025):
    remaining = D(cash)
    qty = Decimal(0)
    for price, size in levels(book, "a"):
        spend = min(remaining, price*size)
        qty += spend/price
        remaining -= spend
        if remaining <= 0: break
    if remaining > Decimal("1e-12"):
        raise ValueError("insufficient displayed ask depth")
    # Alpaca charges the buy fee in received tokens; no double deduction from USD.
    credited = (qty*(1-D(fee))*(1-D(adverse))).quantize(Decimal("0.000000001"), rounding=ROUND_DOWN)
    return float(credited)


def sweep_sell(book, qty, fee=0.0025, adverse=0.0025):
    remaining = D(qty)
    usd = Decimal(0)
    for price, size in levels(book, "b"):
        amount = min(remaining, size)
        usd += amount*price
        remaining -= amount
        if remaining <= 0: break
    if remaining > Decimal("1e-9"):
        raise ValueError("insufficient displayed bid depth")
    return float(usd*(1-D(fee))*(1-D(adverse)))


def load_records(path):
    raw = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    books = collections.defaultdict(list)
    trades = {}
    invalid = []
    for record in raw:
        received = stamp(record["received_at_utc"])
        if record.get("http_status") != 200:
            invalid.append({"kind": record["kind"], "received": received, "reason": "http_failure"}); continue
        body = record.get("body", {})
        if record["kind"] == "books":
            for symbol, book in body.get("orderbooks", {}).items():
                try:
                    f = features(book)
                    source = stamp(book["t"])
                    f.update(source_time=source, available=received, age_seconds=received-source, book=book, symbol=symbol, cycle=record["cycle"])
                    books[symbol].append(f)
                except Exception as error:
                    invalid.append({"symbol": symbol, "kind": "book", "received": received, "reason": str(error)})
        elif record["kind"] == "trades":
            if body.get("next_page_token"):
                invalid.append({"kind": "trades", "received": received, "reason": "truncated_page"})
            for symbol, rows in body.get("trades", {}).items():
                for trade in rows:
                    key = (symbol, str(trade["i"]))
                    if key not in trades:
                        trades[key] = {**trade, "symbol": symbol, "available": received, "source_time": stamp(trade["t"]), "page_complete": not body.get("next_page_token")}
    for rows in books.values(): rows.sort(key=lambda x: x["available"])
    return raw, books, sorted(trades.values(), key=lambda x:x["available"]), invalid


def fresh(row, decision, cfg):
    return row["available"] <= decision and -0.25 <= decision-row["source_time"] <= cfg["source_book_max_age_seconds"]


def gate(symbol, history, trades, decision, cfg):
    past = [r for r in history if r["available"] <= decision]
    if not past: return False, {"reason": "no_book"}
    row = past[-1]
    reasons = []
    if not fresh(row, decision, cfg): reasons.append("stale_source_book")
    if row["spread_bps"] > cfg["max_spread_bps"]: reasons.append("spread")
    if min(row["near_bid_usd"], row["near_ask_usd"]) < cfg["minimum_side_depth_usd"]: reasons.append("near_depth")
    # Repeated REST copies of one source timestamp cannot provide persistence votes.
    distinct = {r["source_time"]:r for r in past if decision-r["available"] <= 40}
    recent = sorted(distinct.values(),key=lambda r:r["available"])[-cfg["persistence_snapshots"]:]
    persistent = len(recent) == cfg["persistence_snapshots"] and all(r["near_bid_share"] is not None and r["near_bid_share"] >= cfg["buy_imbalance_min"] for r in recent)
    ofi = sum(snapshot_ofi(a,b) for b,a in zip(recent,recent[1:])) if len(recent)>1 else 0
    window = [t for t in trades if t["symbol"]==symbol and t["available"]<=decision and decision-cfg["signed_flow_window_seconds"]<=t["source_time"]<=decision]
    buy = sum(t["p"]*t["s"] for t in window if t.get("tks")=="B")
    sell = sum(t["p"]*t["s"] for t in window if t.get("tks")=="S")
    unknown = sum(t["p"]*t["s"] for t in window if t.get("tks") not in ("B","S"))
    baseline = [r for r in past if r["available"] <= decision-60]
    momentum = row["mid"]/baseline[-1]["mid"]-1 if baseline else None
    cost_ok = not reasons
    if not persistent: reasons.append("no_persistent_near_bid_imbalance")
    if ofi <= 0: reasons.append("nonpositive_sampled_ofi")
    if buy < cfg["minimum_signed_buy_usd"] or buy+sell <= 0 or buy/(buy+sell) < cfg["signed_buy_notional_fraction_min"] or unknown > 0 or any(not t["page_complete"] for t in window): reasons.append("no_verified_signed_buy_flow")
    if momentum is None or momentum > cfg["maximum_trailing_60s_mid_return"]: reasons.append("missing_or_extended_60s_price")
    return not reasons, {"reasons":reasons,"cost_qualified":cost_ok,"persistent":persistent,"sampled_ofi":ofi,"signed_buy_usd":buy,"signed_sell_usd":sell,"unknown_side_usd":unknown,"momentum_60s":momentum,"near_bid_share":row["near_bid_share"],"age_seconds":row["age_seconds"]}


def forward_path(symbol, histories, decision, cfg, budget=7):
    rows = histories[symbol]
    entries = [r for r in rows if decision+cfg["paper_entry_delay_seconds"] <= r["available"] <= decision+cfg["max_entry_wait_seconds"] and fresh(r,r["available"],cfg)]
    if not entries: return {"status":"missing_fresh_entry", "symbol":symbol, "decision":decision}
    entry=entries[0]
    try:
        if entry["spread_bps"]>cfg["max_spread_bps"] or min(entry["near_bid_usd"],entry["near_ask_usd"])<cfg["minimum_side_depth_usd"]: raise ValueError("entry cost gates fail on later book")
        qty=sweep_buy(entry["book"],budget,cfg["fee_fraction_each_side"],cfg["adverse_allowance_each_side"])
    except Exception as e: return {"status":"entry_rejected", "symbol":symbol,"decision":decision,"reason":str(e)}
    target=entry["available"]+cfg["holding_seconds"]
    exits=[r for r in rows if target<=r["available"]<=target+cfg["max_exit_wait_seconds"] and fresh(r,r["available"],cfg)]
    if not exits: return {"status":"censored_exit","symbol":symbol,"decision":decision,"entry_at":entry["available"],"budget":budget,"quantity":qty,"next_available_at":target+cfg["max_exit_wait_seconds"]}
    exit=exits[0]
    try: proceeds=sweep_sell(exit["book"],qty,cfg["fee_fraction_each_side"],cfg["adverse_allowance_each_side"])
    except Exception as e: return {"status":"insufficient_exit_depth","symbol":symbol,"decision":decision,"entry_at":entry["available"],"budget":budget,"quantity":qty,"reason":str(e)}
    return {"status":"observed_book_path","symbol":symbol,"decision":decision,"entry_at":entry["available"],"exit_at":exit["available"],"budget":budget,"proceeds":proceeds,"net_return":proceeds/budget-1,"next_available_at":exit["available"]}


def study(raw_path, cfg_path, output):
    cfg=json.loads(cfg_path.read_text()); raw, histories, trades, invalid=load_records(raw_path)
    output.mkdir(parents=True,exist_ok=True)
    symbols=[x["symbol"] for x in cfg["instruments"]]
    decisions=sorted({r["available"] for rows in histories.values() for r in rows})
    journal=[]; qualified_counts=collections.Counter(); signals=collections.Counter();
    snapshots=[]
    for symbol,rows in histories.items():
        for r in rows:
            snapshots.append({k:v for k,v in r.items() if k!="book"})
    random_seed=random.Random(20261012)
    tracks={name:{"cash":50.,"position_unresolved":False,"next_decision":0,"attempts":[]} for name in ["full_book_and_flow","book_only","momentum","matched_random"]}
    for decision in decisions:
        states={s:gate(s,histories.get(s,[]),trades,decision,cfg) for s in symbols}
        full=[s for s in symbols if states[s][0]]
        cost=[s for s in symbols if states[s][1].get("cost_qualified")]
        book=[s for s in cost if states[s][1].get("persistent")]
        momentum=[s for s in cost if states[s][1].get("momentum_60s") is not None and 0 < states[s][1]["momentum_60s"] <= cfg["maximum_trailing_60s_mid_return"]]
        for s,(_,info) in states.items():
            journal.append({"decision":decision,"symbol":s,**info})
            for reason in info.get("reasons",[]): qualified_counts[reason]+=1
        selected={
            "full_book_and_flow":sorted(full,key=lambda s:(-states[s][1]["near_bid_share"],s))[0] if full else None,
            "book_only":sorted(book,key=lambda s:(-states[s][1]["near_bid_share"],s))[0] if book else None,
            "momentum":sorted(momentum,key=lambda s:(-states[s][1]["momentum_60s"],s))[0] if momentum else None,
            "matched_random":None}
        primary=tracks["full_book_and_flow"]
        primary_can_attempt=not primary["position_unresolved"] and decision>=primary["next_decision"] and len(primary["attempts"])<cfg["max_entries_in_bounded_pilot"] and primary["cash"]>cfg["campaign_floor_usd"]
        if selected["full_book_and_flow"] and cost and primary_can_attempt:
            controls=[s for s in cost if s!=selected["full_book_and_flow"]]
            selected["matched_random"]=random_seed.choice(controls) if controls else None
        for name,symbol in selected.items():
            if not symbol: continue
            signals[name]+=1
            track=tracks[name]
            if track["position_unresolved"] or decision<track["next_decision"] or len(track["attempts"])>=cfg["max_entries_in_bounded_pilot"] or track["cash"]<=cfg["campaign_floor_usd"]:continue
            budget=track["cash"]*cfg["position_fraction"]
            path=forward_path(symbol,histories,decision,cfg,budget)
            track["attempts"].append(path)
            track["next_decision"]=path.get("next_available_at",decision+cfg["max_entry_wait_seconds"])
            if path["status"]=="observed_book_path":track["cash"]+=path["proceeds"]-budget
            elif path["status"] in ("censored_exit","insufficient_exit_depth"):
                track["cash"]-=budget;track["position_unresolved"]=True
    def desc(nums):
        nums=sorted(nums)
        return {"min":nums[0],"median":nums[len(nums)//2],"max":nums[-1]} if nums else None
    summaries={}
    for symbol,rows in histories.items():
        own_trades=[t for t in trades if t["symbol"]==symbol]
        immediate=[]
        for row in rows:
            try: immediate.append(1-sweep_sell(row["book"],sweep_buy(row["book"],7))/7)
            except ValueError:pass
        summaries[symbol]={"book_receipts":len(rows),"unique_source_updates":len({r["source_time"] for r in rows}),"fresh_source_receipts_2s":sum(fresh(r,r["available"],cfg) for r in rows),
            "source_age_seconds":desc([r["age_seconds"] for r in rows]),"spread_bps":desc([r["spread_bps"] for r in rows]),
            "all_levels_bid_share":desc([r["all_levels_bid_share"] for r in rows]),"near_mid_bid_share":desc([r["near_bid_share"] for r in rows if r["near_bid_share"] is not None]),
            "all_vs_near_share_gap_max":max((abs(r["all_levels_bid_share"]-r["near_bid_share"]) for r in rows if r["near_bid_share"] is not None),default=None),
            "same_state_net_roundtrip_cost_fraction":desc(immediate),"signed_trade_count":len(own_trades),"buy_trade_count":sum(t.get("tks")=="B" for t in own_trades),"sell_trade_count":sum(t.get("tks")=="S" for t in own_trades),"trade_participant_identity":None}
    result={"status":"bounded prospective displayed-book development probe; paths are not fills", "config":cfg["id"], "completed_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "collection_first_receipt":min((r["received_at_utc"] for r in raw),default=None),"collection_last_receipt":max((r["received_at_utc"] for r in raw),default=None),
        "http_records":len(raw),"invalid_or_incomplete_records":invalid,"snapshot_count":len(snapshots),"independent_campaigns":0,"validated_doubling_campaigns":0,
        "symbols":summaries,"signal_counts_repeated_decisions_not_independent":dict(signals),"rejection_reason_counts":dict(qualified_counts),"account_replays":tracks,
        "limits":["no authenticated asset increment/account or US-state eligibility", "no queue/latency fill guarantee", "polled snapshots miss intrapoll additions/cancellations", "no distinct buyer identities from Alpaca trades", "attention control unavailable", "12-minute window does not complete 30-day campaigns", "small window and repeated observations cannot establish profitability"]}
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'features.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in snapshots))
    (output/'decision_journal.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in journal))
    (output/'trades_deduplicated.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in trades))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('raw',type=pathlib.Path)
    p.add_argument('--config',type=pathlib.Path,default=pathlib.Path(__file__).with_name('orderbook_config.json'))
    p.add_argument('--output',type=pathlib.Path,required=True)
    a=p.parse_args();study(a.raw,a.config,a.output)
