import pickle, time, sys
sys.path.insert(0, '.')
from tartar.data.dataset import load_trade_tokens, build_dataset
t=time.time()
tokens = load_trade_tokens('data/raw', 60)
print('tokens', len(tokens), time.time()-t)
ds = build_dataset(tokens, 60, 'trades')
print('rows', len(ds), time.time()-t)
pickle.dump(ds, open('/tmp/tartar-exp/ds60.pkl','wb'))
