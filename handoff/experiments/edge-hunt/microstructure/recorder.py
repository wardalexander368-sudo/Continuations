"""Paper-only data recorder: public market data, no orders. Writes JSONL lines with local receive time."""
import asyncio, json, time, ssl, sys
import websockets, httpx
ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
OUT = open(sys.argv[1], "a", buffering=1)
MINUTES = float(sys.argv[2])
END = time.time() + MINUTES * 60
SOL = "So11111111111111111111111111111111111111112"; USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
JUP = "https://lite-api.jup.ag/swap/v1/quote"
def w(d): OUT.write(json.dumps(d, separators=(",", ":")) + "\n")
async def binance():
    url = "wss://data-stream.binance.vision/stream?streams=solusdt@bookTicker/btcusdt@bookTicker/solusdt@aggTrade"
    while time.time() < END:
        try:
            async with websockets.connect(url, ssl=ctx, open_timeout=10, max_queue=None) as ws:
                last = {}
                while time.time() < END:
                    m = json.loads(await ws.recv()); tl = time.time(); d = m["data"]
                    if m["stream"].endswith("bookTicker"):
                        key = (d["s"], d["b"], d["a"])
                        if last.get(d["s"]) == key: continue  # only price changes
                        last[d["s"]] = key
                        w({"k": "bn", "tl": round(tl, 4), "s": d["s"], "b": float(d["b"]), "a": float(d["a"]), "B": float(d["B"]), "A": float(d["A"])})
                    else:
                        w({"k": "bt", "tl": round(tl, 4), "T": d["T"], "p": float(d["p"]), "q": float(d["q"]), "m": d["m"]})
        except Exception as e:
            print("binance", type(e).__name__, e, file=sys.stderr); await asyncio.sleep(1)
async def coinbase():
    while time.time() < END:
        try:
            async with websockets.connect("wss://ws-feed.exchange.coinbase.com", ssl=ctx, open_timeout=10, max_queue=None) as ws:
                await ws.send(json.dumps({"type": "subscribe", "product_ids": ["SOL-USD"], "channels": ["ticker"]}))
                while time.time() < END:
                    d = json.loads(await ws.recv()); tl = time.time()
                    if d.get("type") == "ticker":
                        w({"k": "cb", "tl": round(tl, 4), "te": d["time"], "b": float(d["best_bid"]), "a": float(d["best_ask"]), "p": float(d["price"])})
        except Exception as e:
            print("coinbase", type(e).__name__, e, file=sys.stderr); await asyncio.sleep(1)
async def slots():
    while time.time() < END:
        try:
            async with websockets.connect("wss://api.mainnet-beta.solana.com", ssl=ctx, open_timeout=10, max_queue=None) as ws:
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "slotSubscribe"}))
                while time.time() < END:
                    d = json.loads(await ws.recv()); tl = time.time()
                    if d.get("method") == "slotNotification":
                        w({"k": "sl", "tl": round(tl, 4), "slot": d["params"]["result"]["slot"]})
        except Exception as e:
            print("slots", type(e).__name__, e, file=sys.stderr); await asyncio.sleep(1)
async def jup(side, every):
    async with httpx.AsyncClient(timeout=5, verify="/root/.ccr/ca-bundle.crt") as c:
        while time.time() < END:
            t0 = time.time()
            if side == "buy": params = {"inputMint": USDC, "outputMint": SOL, "amount": 1_000_000_000}
            else: params = {"inputMint": SOL, "outputMint": USDC, "amount": 9_000_000_000}
            params.update(slippageBps=50, restrictIntermediateTokens="true")
            try:
                r = await c.get(JUP, params=params); t1 = time.time()
                if r.status_code == 200:
                    q = r.json()
                    w({"k": "j" + side[0], "t0": round(t0, 4), "t1": round(t1, 4), "out": int(q["outAmount"]), "slot": q.get("contextSlot"), "r": [p["swapInfo"].get("label") for p in q.get("routePlan", [])]})
                else:
                    w({"k": "jerr", "t0": round(t0, 4), "code": r.status_code}); await asyncio.sleep(2)
            except Exception as e:
                w({"k": "jerr", "t0": round(t0, 4), "err": type(e).__name__})
            await asyncio.sleep(max(0, every - (time.time() - t0)))
async def jupalt(every):
    async with httpx.AsyncClient(timeout=5, verify="/root/.ccr/ca-bundle.crt") as c:
        side = "buy"; back = every
        while time.time() < END:
            t0 = time.time()
            if side == "buy": params = {"inputMint": USDC, "outputMint": SOL, "amount": 1_000_000_000}
            else: params = {"inputMint": SOL, "outputMint": USDC, "amount": 9_000_000_000}
            params.update(slippageBps=50, restrictIntermediateTokens="true")
            try:
                r = await c.get(JUP, params=params); t1 = time.time()
                if r.status_code == 200:
                    q = r.json(); back = every
                    w({"k": "j" + side[0], "t0": round(t0, 4), "t1": round(t1, 4), "out": int(q["outAmount"]), "slot": q.get("contextSlot"), "r": [p["swapInfo"].get("label") for p in q.get("routePlan", [])]})
                    side = "sell" if side == "buy" else "buy"
                else:
                    w({"k": "jerr", "t0": round(t0, 4), "code": r.status_code}); back = min(back * 2, 10)
            except Exception as e:
                w({"k": "jerr", "t0": round(t0, 4), "err": type(e).__name__})
            await asyncio.sleep(max(0, back - (time.time() - t0)))
async def main():
    await asyncio.gather(binance(), coinbase(), slots(), jupalt(1.05))
asyncio.run(main())
