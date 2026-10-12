#!/usr/bin/env python3
"""Frozen signed-flow challenger replay using historical top quotes, not fills."""
import argparse
import bisect
import collections
import datetime as dt
import gzip
import json
import math
import pathlib
import random
from orderbook_study import stamp


def load_quotes(folder):
    streams=collections.defaultdict(list);seen=set();invalid=collections.Counter()
    completion=json.loads((folder/'summary.json').read_text())
    complete={(r['date'],r['symbol']) for r in completion['streams'] if r['status']=='complete'}
    for path in sorted(folder.glob('*.json.gz')):
        with gzip.open(path,'rt') as handle:r=json.load(handle)
        key=(r['date_partition'],r['symbol'])
        if key not in complete:continue
        for q in r.get('body',{}).get('quotes',{}).get(r['symbol'],[]):
            identity=(key,q['t'],q.get('bp'),q.get('ap'),q.get('bs'),q.get('as'))
            if identity in seen:continue
            seen.add(identity)
            try:
                bp,ap,bs,ass=[float(q[x]) for x in ('bp','ap','bs','as')]
                if not all(math.isfinite(x) and x>0 for x in (bp,ap,bs,ass)) or bp>=ap:raise ValueError('invalid quote')
                source=stamp(q['t']);mid=(bp+ap)/2
                streams[key].append({'source':source,'available':source+2,'bid':bp,'ask':ap,'bid_size':bs,'ask_size':ass,'mid':mid,'spread_bps':(ap-bp)/mid*10000,'source_string':q['t']})
            except Exception:invalid[key]+=1
    for rows in streams.values():rows.sort(key=lambda q:q['available'])
    return streams,complete,completion,invalid


def asof(rows,time,max_age):
    index=bisect.bisect_right([q['available'] for q in rows],time)-1
    if index<0:return None
    q=rows[index]
    return q if 0<=time-q['available']<=max_age else None


def quote_gate(q,cfg):
    return q is not None and q['spread_bps']<=cfg['max_spread_bps'] and min(q['bid']*q['bid_size'],q['ask']*q['ask_size'])>=cfg['minimum_side_top_quote_notional_usd']


def entered_count(track):
    return sum('entry_at' in path for path in track['entries'])


def replay(rows,decision,budget,cfg):
    max_age=cfg['maximum_quote_age_seconds_since_assumed_publication']
    quotes=[q for q in rows if decision+cfg['entry_delay_seconds']<=q['available']<=decision+cfg['maximum_entry_wait_seconds']]
    if not quotes:return {'status':'missing_entry_quote','decision':decision,'next_available':decision+cfg['maximum_entry_wait_seconds']}
    entry=quotes[0]
    if not quote_gate(entry,cfg) or entry['ask']*entry['ask_size']<budget:return {'status':'entry_capacity_reject','decision':decision,'next_available':entry['available']}
    qty=math.floor(budget/entry['ask']*(1-cfg['fee_per_side'])*(1-cfg['adverse_allowance_per_side'])*1e9)/1e9
    target=entry['available']+cfg['holding_seconds']
    exits=[q for q in rows if target<=q['available']<=target+cfg['maximum_exit_wait_seconds']]
    if not exits:return {'status':'censored_exit','decision':decision,'entry_at':entry['available'],'budget':budget,'quantity':qty,'next_available':target+cfg['maximum_exit_wait_seconds']}
    exit=exits[0]
    if exit['bid_size']<qty:return {'status':'insufficient_exit_depth','decision':decision,'entry_at':entry['available'],'budget':budget,'quantity':qty,'next_available':exit['available']}
    proceeds=qty*exit['bid']*(1-cfg['fee_per_side'])*(1-cfg['adverse_allowance_per_side'])
    return {'status':'observed_quote_path','decision':decision,'entry_at':entry['available'],'exit_at':exit['available'],'budget':budget,'quantity':qty,'proceeds':proceeds,'net_return':proceeds/budget-1,'gross_mid_return':exit['mid']/entry['mid']-1,'next_available':exit['available']}


def trade_signals(trades,cfg):
    signals=[];recent=collections.defaultdict(list)
    for t in sorted(trades,key=lambda t:t['source']):
        symbol=t['symbol'];now=t['source']
        recent[symbol]=[x for x in recent[symbol] if x['source']>=now-cfg['trade_window_seconds']]+[t]
        buys=sum(x['p']*x['s'] for x in recent[symbol] if x.get('tks')=='B')
        sells=sum(x['p']*x['s'] for x in recent[symbol] if x.get('tks')=='S')
        unknown=sum(x['p']*x['s'] for x in recent[symbol] if x.get('tks') not in ('B','S'))
        if buys>=cfg['min_buy_usd'] and buys+sells>0 and buys/(buys+sells)>=cfg['min_buy_fraction'] and unknown==0:
            signals.append({'symbol':symbol,'decision':now+cfg['decision_after_trade_seconds'],'buy_usd':buys,'sell_usd':sells,'trigger_trade_id':str(t['i'])})
    return signals


def run(trade_folder,quote_folder,config_path,output):
    cfg=json.loads(config_path.read_text());streams,complete,source,invalid=load_quotes(quote_folder)
    output.mkdir(parents=True,exist_ok=True);summaries=[];journals=[]
    for date in cfg['development_dates']+cfg['chronological_comparison_dates']:
        record=json.loads((trade_folder/(date+'_trades.json')).read_text());body=record.get('body',{})
        if record.get('http_status')!=200 or body.get('next_page_token'):
            summaries.append({'date':date,'status':'incomplete_trade_source'});continue
        raw_trades=[dict(t,symbol=symbol) for symbol,rows in body.get('trades',{}).items() for t in rows]
        trades=[];seen=set();invalid_trades=collections.Counter();day_start=stamp(date+'T00:00:00Z');day_end=day_start+86400
        for trade in raw_trades:
            try:
                trade['source']=stamp(trade['t'])
                if trade['symbol'] not in cfg['universe'] or not all(math.isfinite(float(trade[x])) and float(trade[x])>0 for x in ['p','s']):raise ValueError('invalid trade identity/price/size')
                if not day_start<=trade['source']<day_end:invalid_trades['outside_partition']+=1;continue
                identity=(trade['symbol'],str(trade['i']))
                if identity in seen:invalid_trades['duplicate_id']+=1;continue
                seen.add(identity);trades.append(trade)
            except Exception:invalid_trades['invalid_trade']+=1
        signals=trade_signals(trades,cfg)
        tracks={name:{'cash':50.,'unresolved':False,'next_available':0.,'entries':[],'instrument_last_entry':{}} for name in ('flow','random','momentum')}
        rng=random.Random(cfg['random_seed']);observed_pairs=[];counts=collections.Counter()
        day_end=stamp(date+'T00:00:00Z')+86400
        for signal in signals:
            decision=signal['decision'];main=signal['symbol'];state=tracks['flow']
            if date in cfg['development_dates'] and decision+cfg['entry_delay_seconds']+cfg['holding_seconds']+cfg['maximum_exit_wait_seconds']>=day_end:
                counts['purged_development_boundary']+=1;continue
            if state['unresolved'] or decision<state['next_available']:counts['one_position_or_unresolved_skip']+=1;continue
            if entered_count(state)>=cfg['max_entries_per_24h'] or state['cash']<=cfg['campaign_floor_usd']:counts['account_limit_skip']+=1;continue
            if decision-state['instrument_last_entry'].get(main,-1e30)<cfg['same_instrument_cooldown_seconds']:counts['same_pair_cooldown']+=1;continue
            qualified={}
            for symbol in cfg['universe']:
                if (date,symbol) not in complete:continue
                rows=streams[(date,symbol)]
                q=asof(rows,decision,cfg['maximum_quote_age_seconds_since_assumed_publication'])
                if quote_gate(q,cfg):qualified[symbol]=q
            if main not in qualified:counts['no_fresh_cost_qualified_signal_quote']+=1;continue
            main_bucket=int(qualified[main]['spread_bps']//25)
            random_pool=[s for s,q in qualified.items() if s!=main and int(q['spread_bps']//25)==main_bucket]
            selected={'flow':main,'random':rng.choice(sorted(random_pool)) if random_pool else None,'momentum':None}
            momentum=[]
            for s,q in qualified.items():
                if s==main:continue
                old=asof(streams[(date,s)],decision-600,30)
                if old and q['mid']>old['mid']:momentum.append((q['mid']/old['mid']-1,s))
            if momentum:selected['momentum']=sorted(momentum,key=lambda x:(-x[0],x[1]))[0][1]
            paths={}
            for name,symbol in selected.items():
                track=tracks[name]
                if symbol is None:counts[name+'_unmatched']+=1;continue
                if track['unresolved'] or decision<track['next_available'] or entered_count(track)>=cfg['max_entries_per_24h'] or decision-track['instrument_last_entry'].get(symbol,-1e30)<cfg['same_instrument_cooldown_seconds']:
                    counts[name+'_account_unmatched']+=1;continue
                path=replay(streams[(date,symbol)],decision,round(track['cash']*cfg['position_fraction'],9),cfg);path.update(symbol=symbol,policy=name)
                paths[name]=path;track['entries'].append(path);track['next_available']=path['next_available']
                if path['status']=='observed_quote_path':track['cash']+=path['proceeds']-path['budget'];track['instrument_last_entry'][symbol]=path['entry_at']
                elif path['status'] in ('censored_exit','insufficient_exit_depth'):
                    track['cash']-=path['budget'];track['unresolved']=True;track['instrument_last_entry'][symbol]=path['entry_at']
            journals.append({'date':date,'signal':signal,'qualified_known_universe':sorted(qualified),'matched_choices':selected,'paths':paths})
            for control in ['random','momentum']:
                if all(paths.get(n,{}).get('status')=='observed_quote_path' for n in ['flow',control]):
                    observed_pairs.append({'control':control,'decision':decision,'flow_net_return':paths['flow']['net_return'],'control_net_return':paths[control]['net_return'],'difference':paths['flow']['net_return']-paths[control]['net_return']})
        summaries.append({'date':date,'partition':'development' if date in cfg['development_dates'] else 'chronological_comparison',
            'source_trade_count':len(trades),'rejected_source_trade_rows':dict(invalid_trades),'raw_signed_flow_triggers_repeated':len(signals),'selection_and_rejection_counts':dict(counts),'accounts':tracks,'observed_pairs':observed_pairs,
            'campaign_status':'partial_window_not_30_day_complete','withdrawable_live_money_verified':False})
    result={'status':'retrospective top-quote paths with explicit publication assumption; not fills or validated account outcomes',
        'config':cfg['id'],'completed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'quote_source':source,
        'invalid_quote_counts':{str(k):v for k,v in invalid.items()},'daily_partial_replays':summaries,'validated_doubling_campaigns':0,
        'limits':cfg['scope_limits']+['no social attention control','small two-day sample; no positive edge confidence claim','no stop-price fills assumed','development exits purged at chronological boundary','fees current, not proven exact at historical execution time']}
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');(output/'decision_journal.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in journals));print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trades',type=pathlib.Path,required=True);p.add_argument('--quotes',type=pathlib.Path,required=True);p.add_argument('--config',type=pathlib.Path,default=pathlib.Path(__file__).with_name('flow_config.json'));p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();run(a.trades,a.quotes,a.config,a.output)
