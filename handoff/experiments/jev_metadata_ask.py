"""Ask Jev the metadata question set about every recorded launch (cached in data/jev-metadata.jsonl)."""
import json, sys, time
sys.path.insert(0, '.')
from tartar.data.dataset import load_trade_tokens
from tartar.decide import launch_states
from tartar.jev import METADATA, JevClient
from tartar.metadata import fetch_metadata
from tartar.profit import curves_for

tokens = load_trade_tokens('data/raw', 60)
curves = curves_for(tokens)
states = launch_states(tokens, curves, 20.0)
meta = fetch_metadata({t.mint: t.uri for t in tokens}, 'data/metadata.jsonl')
for s in states:
    s['metadata'] = meta.get(s['mint'])
client = JevClient(questions=METADATA, cache='data/jev-metadata.jsonl', workers=6)
t = time.time()
answers = client.ask_many(states)
print(f'{len(answers)} launches answered in {time.time() - t:.0f}s; {client.latency_summary()}')
