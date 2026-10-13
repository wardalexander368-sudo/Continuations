# Independent adversarial review — CAPIT account controls

The read-only reviewer found no material chronology, stop, control or reporting defect. A midnight ambiguity was resolved by documenting candle-start UTC signal-day labels separately from close execution timestamps; no code or outcome changed. A new midnight-boundary test then passed in the parent's 29-test focused run.

The reviewer independently matched protocol/cohort/code/full-output hashes, reconstructed all 10,000 shared shift vectors and their matrix hash, and recomputed every control mean, quantile, tail count, halt total and rejection total. The primary gain is $153.288806935; control mean −$55.719965181; exactly one of 10,000 controls is at least actual. Episode 13 contributes $100.531885854 (65.58%). Eight targeted tests passed in 0.17 seconds.

The reviewer reproduced two further boundary checks with this command:

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/cde-research-venv-20261013/bin/python - <<'PY'
import importlib.util, sys
from pathlib import Path
import numpy as np
p=Path('/Users/alexanderward/Projects/CodexCoinHunt/account-controls/handoff/experiments/edge-hunt/patterns/capit_account_controls.py')
s=importlib.util.spec_from_file_location('review_controls',p); m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m)
def row(i,c='BTC',h=0): return {'cohort_id':i,'coin':c,'signal_index':h,'episode_id':0}
def prices(): return {c:np.full(100,100.) for c in m.COINS}
a=m.account(prices(),[row(0),row(1,h=24)],{0:0},1,m.Policy(cash=100,cap=100))
print('fee-cost-funded-next-entry:',a['executed'],a['rejected'],format(a['terminal_cash_usd'],'.12f'))
c=prices(); c['BTC'][25]=200; c['ETH'][25]=40
b=m.account(c,[row(0),row(1,'ETH'),row(2,'SOL',24)],{0:0},1,m.Policy(fee=0,budget=0,loss_stop=50))
print('same-timestamp-net-stop:',b['executed'],b['halt_reason'],b['net_pnl_usd'])
assert a['executed']==1 and a['rejected']=={'cash':1} and a['terminal_cash_usd']<100
assert b['executed']==3 and b['halt_reason'] is None and b['net_pnl_usd']==40
print('synthetic checks passed')
PY
```

Observed output:

```text
fee-cost-funded-next-entry: 1 {'cash': 1} 99.222412747154
same-timestamp-net-stop: 3 None 40.0
synthetic checks passed
```

The first check shows that fees reduce released cash enough to prevent a second $100 debit in a $100 account. The second confirms that simultaneous gains and losses are netted before the cumulative-loss stop.

The reviewer did not independently reconstruct cache endpoints/signals, regenerate the full accounts, rerun the parent's Fraction oracle or 80,008 invariants/full suite, source-mutate tests, or check the newly compacted public JSON. Real fills/fees, rounding, intratrade losses, taxes and alternative cash returns remain unverified. The shifted tail is not a profitability confidence interval or untouched evidence. The review accessed no network, keys, private CTS, live accounts, bot books or registered outcomes, and changed no files.
