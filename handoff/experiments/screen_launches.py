import pickle, sys, math, numpy as np, warnings, lightgbm as lgb
from collections import defaultdict, Counter
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')
from tartar.profit import Costs, Exit, curves_for, run_policy, summarize
from tartar.scam import WalletTracker, assess, CreatorIndex, _norm
from tartar.data.rawlog import raw_files, read_events, event_price
ds = pickle.load(open(sys.argv[1], 'rb'))
S = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
tokens = ds.tokens
curves = curves_for(tokens)
tr, va, te = ds.split()
part = np.full(len(tokens), -1)
for code, m in enumerate((tr, va, te)):
    part[np.unique(ds.token[m])] = code
# launch metadata and per-mint outcome stats from raw logs
meta = {}
for e in read_events(raw_files('data/raw')):
    if e['e'] == 'create':
        meta[e['mint']] = e
order = np.argsort([t.created for t in tokens])
# causal creator index: a launch's rug status becomes known once its data window ended (last tick + 10 min idle)
idx = CreatorIndex()
pending = []  # (known_at, mint, creator, rugged)
def rug_of(tok):
    c = curves[tok]
    if len(c) == 0: return False
    peak = c.price.max(); last = c.price[-1]
    tk = [t for g in tokens[tok].ticks.values() for t, _ in g]
    bought = sum(t.volume for t in tk if t.creator and t.buys); sold = sum(t.volume for t in tk if t.creator and t.sells)
    return bought > 0 and sold >= 0.5 * bought and last <= 0.2 * peak
rows = []
for k in order:
    tok = tokens[k]
    t0 = tok.created
    # release outcomes known by now
    still = []
    for known_at, mint, creator, rugged in pending:
        if known_at <= t0 + S:
            idx.creators[creator].tokens[mint] = rugged
        else:
            still.append((known_at, mint, creator, rugged))
    pending = still
    m = meta.get(tok.mint, {})
    creator = tok.creator
    # recent launches (24h) by this creator: everything noted so far is within the recording
    tracker = WalletTracker(t0)
    buyers = set(); buy_sol = sell_sol = 0.0; n = 0
    ticks = sorted((t for g in tok.ticks.values() for t, _ in g), key=lambda t: t.ts)
    for t in ticks:
        if t.ts > t0 + S: break
        tracker.update(t); n += 1
        if t.buys and not t.creator and t.trader: buyers.add(t.trader)
        if not t.creator:
            buy_sol += t.buy_volume; sell_sol += t.sell_volume
    report = assess(tracker, None, idx, mint=tok.mint, creator=creator, name=m.get('name',''), symbol=m.get('symbol',''), uri=m.get('uri',''))
    # now note this launch (after judging it), outcome released later
    idx.note_launch(creator, m.get('name',''), m.get('symbol',''), m.get('uri',''), tok.mint)
    idx.creators[creator].tokens[tok.mint] = False
    end = curves[k].end if len(curves[k]) else t0
    pending.append((end + 600, tok.mint, creator, rug_of(k)))
    snap = tracker.snapshot()
    rec = idx.creators.get(creator)
    launches, rugs, recent = rec.excluding(tok.mint) if rec else (0, 0, 0)
    c = curves[k]; i = c.index_at(t0 + S)
    p_now = c.price[i] if i >= 0 else np.nan
    p0 = c.price[0] if len(c) else np.nan
    rows.append(dict(k=k, part=part[k], level=report.level, codes={f.code for f in report.flags}, buyers=len(buyers), trades=n,
        buy_sol=buy_sol, sell_sol=sell_sol, rise=math.log(p_now/p0) if p0==p0 and p_now==p_now else np.nan,
        creator_sold=tracker.creator_sold_share if tracker.creator_sold_share is not None else np.nan,
        launches=launches, rugs=rugs, drawdown=tracker.drawdown if tracker.drawdown is not None else np.nan, **snap))
costs = Costs()
K = np.array([r['k'] for r in rows]); P = np.array([r['part'] for r in rows])
when = np.array([tokens[k].created + S for k in K])
def run(sel, rule):
    return summarize(run_policy(curves, K[sel], when[sel], np.ones(sel.sum(), bool), costs, rule), costs, boot=1000)
def fmt(s):
    return f"n={s.trades:4d} mean {100*s.mean_ret:+6.2f}% [{100*s.ci_low:+6.2f},{100*s.ci_high:+6.2f}] win {100*s.win_rate:4.1f}% total {s.total_sol:+6.3f}"
levels = np.array([r['level'] for r in rows]); buyers = np.array([r['buyers'] for r in rows])
passed = (buyers >= 3) & ~np.isin(levels, ['danger', 'scam'])
print(f'screen at +{S:g}s: {len(rows)} launches; passed {passed.sum()} ({passed.mean():.1%}); levels {Counter(levels)}')
for H in (30, 60, 180, 600):
    rule = Exit(H)
    print(f'--- buy at +{S:g}s (+1s latency), {rule.label()}')
    for name, code in (('valid', 1), ('test', 2)):
        sp = P == code
        print(f'  {name} all      ', fmt(run(sp, rule)))
        print(f'  {name} passed   ', fmt(run(sp & passed, rule)))
        print(f'  {name} rejected ', fmt(run(sp & ~passed, rule)))
# flag-level: mean net return for 180s hold, valid+test, with vs without
rule = Exit(180)
vt = P >= 1
print('--- per flag (valid+test, hold 180s): with flag vs without')
allc = Counter(c for r in rows for c in r['codes'])
for code, cnt in allc.most_common():
    has = np.array([code in r['codes'] for r in rows])
    if (has & vt).sum() < 15: continue
    print(f'  {code:18s} with: {fmt(run(vt & has, rule))}\n  {"":18s} w/o : {fmt(run(vt & ~has, rule))}')
for b in (0, 1, 3, 5, 10, 20):
    print(f'  buyers>={b:2d}: {fmt(run(vt & (buyers >= b), rule))}')
pickle.dump(dict(rows=rows, when=when), open(f'/tmp/tartar-exp/screen_rows_{int(S)}.pkl', 'wb'))
