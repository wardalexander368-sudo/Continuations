"""Fee rates on recent pump.fun trades, read from each TradeEvent (protocol fee bps, creator fee bps).

    python3 handoff/experiments/fee_sample.py [--tx 150]

Samples the program's most recent transactions over public RPC (HTTP), decodes the
TradeEvents pump.fun itself emitted, and tabulates fee rates for SOL-quoted and other trades.
"""
import argparse, base64, collections, struct, sys, time
import httpx
sys.path.insert(0, '.')
from tartar.feeds.pumpchain import PUMP_PROGRAM as PROGRAM, SOL_QUOTE, TRADE, _Reader, program_data

parser = argparse.ArgumentParser()
parser.add_argument('--tx', type=int, default=150)
parser.add_argument('--rpc', default='https://api.mainnet-beta.solana.com')
args = parser.parse_args()
client = httpx.Client(timeout=20)


def rpc(method, params):
    for attempt in range(6):
        r = client.post(args.rpc, json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})
        if r.status_code == 429:
            time.sleep(1.5 * (attempt + 1)); continue
        r.raise_for_status()
        body = r.json()
        if 'error' in body:
            raise RuntimeError(body['error'])
        return body['result']
    raise RuntimeError('rate limited')


def fees(data):
    r = _Reader(data)
    r.key(); r.u64(); r.u64(); r.take(1); r.key(); r.i64(); r.u64(); r.u64()
    r.u64(); r.u64(); r.key(); fee_bps = r.u64(); r.u64()
    r.key(); creator_bps = r.u64(); r.u64(); r.take(1)
    quote = SOL_QUOTE
    try:
        r.u64(); r.u64(); r.u64(); r.i64(); r.string(); r.take(1)
        r.u64(); r.u64(); r.u64(); r.u64(); r.take(34 * struct.unpack('<I', r.take(4))[0])
        quote = r.key()
    except ValueError:
        pass
    return fee_bps, creator_bps, quote


sigs = rpc('getSignaturesForAddress', [PROGRAM, {'limit': min(args.tx, 1000)}])
rows = collections.Counter()
seen = 0
for s in sigs[: args.tx]:
    if s.get('err'):
        continue
    tx = rpc('getTransaction', [s['signature'], {'encoding': 'json', 'maxSupportedTransactionVersion': 1, 'commitment': 'confirmed'}])
    time.sleep(0.15)
    if not tx:
        continue
    for data in program_data(tx['meta'].get('logMessages') or [], PROGRAM):
        if data[:8] != TRADE:
            continue
        try:
            fee_bps, creator_bps, quote = fees(data)
        except (ValueError, struct.error):
            continue
        rows[('SOL' if quote == SOL_QUOTE else 'other', fee_bps, creator_bps)] += 1
        seen += 1
print(f'{seen} pump.fun trades in {len(sigs[: args.tx])} recent transactions')
for (q, f, c), n in rows.most_common():
    print(f'  quote {q:5s}  protocol {f / 100:.2f}%  creator {c / 100:.2f}%  total {(f + c) / 100:.2f}% per side: {n}')
