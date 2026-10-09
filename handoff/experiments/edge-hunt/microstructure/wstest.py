import asyncio, json, time, ssl, os
import websockets
ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
async def probe(name, url, sub=None, n=5):
    try:
        async with websockets.connect(url, ssl=ctx, open_timeout=10) as ws:
            if sub: await ws.send(json.dumps(sub))
            t0 = time.time(); k = 0
            while k < n and time.time() - t0 < 8:
                m = await asyncio.wait_for(ws.recv(), 8)
                k += 1
                if k <= 2: print(name, "msg:", m[:200])
            print(name, f"OK {k} msgs in {time.time()-t0:.2f}s")
    except Exception as e:
        print(name, "FAIL", type(e).__name__, str(e)[:200])
async def main():
    await asyncio.gather(
        probe("binance-vision", "wss://data-stream.binance.vision/ws/solusdt@bookTicker", n=20),
        probe("binance-us", "wss://stream.binance.us:9443/ws/solusdt@bookTicker", n=20),
        probe("coinbase", "wss://ws-feed.exchange.coinbase.com", {"type":"subscribe","product_ids":["SOL-USD"],"channels":["ticker"]}, n=5),
        probe("okx", "wss://ws.okx.com:8443/ws/v5/public", {"op":"subscribe","args":[{"channel":"bbo-tbt","instId":"SOL-USDT-SWAP"}]}, n=20),
        probe("solana-rpc", "wss://api.mainnet-beta.solana.com", {"jsonrpc":"2.0","id":1,"method":"slotSubscribe"}, n=5),
    )
asyncio.run(main())
