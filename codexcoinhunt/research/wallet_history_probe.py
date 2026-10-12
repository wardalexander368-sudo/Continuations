#!/usr/bin/env python3
"""Bounded public prior-activity evidence; missing provenance stays unknown."""
import argparse
import collections
import datetime as dt
import json
import pathlib
import time
from buyer_probe import rpc, utc


def profile(folder):
    events=[json.loads(x) for x in (folder/'events.jsonl').read_text().splitlines() if x]
    buyers=collections.defaultdict(list)
    for e in events:
        if e['side']=='B':buyers[e['user']].append(e)
    raw=folder/'wallet_rpc.jsonl'
    if raw.exists():raise ValueError('wallet profile already exists; use a new bounded session')
    rows=[]
    for user,own in sorted(buyers.items()):
        time.sleep(1)
        r=rpc('https://api.mainnet-beta.solana.com','getSignaturesForAddress',[user,{'limit':100,'commitment':'finalized'}],raw)
        signatures=r.get('body',{}).get('result') or []
        cutoff=min(e['event_unix_time'] for e in own)
        prior=[s for s in signatures if s.get('blockTime') is not None and s['blockTime']<cutoff and s.get('err') is None]
        earliest=min((s['blockTime'] for s in prior),default=None)
        age=(cutoff-earliest)/86400 if earliest is not None else None
        rows.append({'wallet':user,'mint':own[0]['mint'],'available_at_utc':r['received_at_utc'],
            'prior_evidence_cutoff_unix_time':cutoff,'returned_signature_count':len(signatures),'successful_prior_signature_count_lower_bound':len(prior),
            'at_least_10_prior_transactions_verified':len(prior)>=10,'wallet_observed_prior_age_days_lower_bound':age,
            'at_least_14_days_prior_activity_verified':True if age is not None and age>=14 else None,
            'first_wallet_activity_time':None,'complete_wallet_history':False,
            'known_other_mints_count':None,'new_to_this_mint':None,'first_funding_root':None,'service_funder_label':None,'buyer_cluster':None,
            'eligibility':'UNKNOWN_MATURITY_FUNDING_FIRST_MINT_AND_OTHER_MINT_EVIDENCE',
            'note':'absence of an old transaction in a bounded recent page does not prove a young wallet; blockTime is approximate, and the full profile became available after the sampled swaps'})
    result={'status':'public prior-signature lower bounds, not independent buyer proof','completed_at_utc':utc(),'wallet_count':len(rows),
        'maturity_14d_verified':sum(r['at_least_14_days_prior_activity_verified'] is True for r in rows),'at_least_10_prior_verified':sum(r['at_least_10_prior_transactions_verified'] for r in rows),
        'funding_provenance_verified':0,'apparently_unrelated_clusters_verified':0,'rows':rows}
    (folder/'wallet_profiles.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=pathlib.Path);a=p.parse_args();profile(a.folder)
