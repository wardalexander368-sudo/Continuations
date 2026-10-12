"""Prior-trade proof tests; synthetic fixtures, no investment outcomes."""
import copy
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import test_buyer_enrichment as enrichment_tests
from buyer_trade_history import prior_swap_events
from buyer_enrichment import account_keys
from buyer_probe import WSOL


class PriorTradeProofTests(unittest.TestCase):
    def fixture(self):
        tx, pool, payload = enrichment_tests.EnrichmentTests().fixture()
        user=account_keys(tx)[0]
        tx['transaction']['message']['accountKeys'][0]['signer']=True
        tx['blockTime']=100
        profile={user:{'mint':'original_target','prior_cutoff_unix_time':200}}
        response={'request':{'method':'getTransaction','params':['synthetic_signature',{'commitment':'finalized'}]},
                  'body':{'result':tx},'received_at_utc':'2026-10-12T00:00:00Z'}
        return response,profile,user

    def test_actual_event_not_log_cpi_double_count(self):
        response,profiles,_=self.fixture()
        events,_=prior_swap_events(response,profiles)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['mint'],'target')
        self.assertTrue(events[0]['other_mint_trade_verified'])
        self.assertFalse(events[0]['historical_entry_eligibility_promoted'])

    def test_balance_without_swap_event_is_not_a_trade(self):
        response,profiles,_=self.fixture();meta=response['body']['result']['meta']
        meta['logMessages']=[];meta['innerInstructions']=[]
        self.assertEqual(prior_swap_events(response,profiles)[0],[])

    def test_signer_and_exact_event_owner_required(self):
        response,profiles,_=self.fixture()
        response['body']['result']['transaction']['message']['accountKeys'][0]['signer']=False
        self.assertEqual(prior_swap_events(response,profiles)[0],[])
        response['body']['result']['transaction']['message']['accountKeys'][0]['signer']=True
        response['body']['result']['meta']['postTokenBalances'][0]['owner']='other'
        self.assertEqual(prior_swap_events(response,profiles)[0],[])

    def test_finalized_success_and_strict_prior_time_required(self):
        response,profiles,_=self.fixture()
        for change in ('commitment','failed','cutoff'):
            current=copy.deepcopy(response)
            if change=='commitment':current['request']['params'][1]['commitment']='processed'
            if change=='failed':current['body']['result']['meta']['err']={'InstructionError':[0,'failed']}
            if change=='cutoff':current['body']['result']['blockTime']=200
            self.assertEqual(prior_swap_events(current,profiles)[0],[],msg=change)

    def test_caught_inner_failure_is_not_successful_swap_proof(self):
        response,profiles,_=self.fixture()
        response['body']['result']['meta']['logMessages'].append('Program synthetic_parent failed: caught by router')
        events,issues=prior_swap_events(response,profiles)
        self.assertEqual(events,[])
        self.assertEqual(issues[0]['reason'],'failed_inner_invocation_requires_rollback_alignment')

    def test_roundtrip_net_zero_does_not_erase_successful_event(self):
        response,profiles,_=self.fixture()
        response['body']['result']['meta']['postTokenBalances'][0]['uiTokenAmount']['amount']='0'
        events,_=prior_swap_events(response,profiles)
        self.assertEqual(len(events),1)
        self.assertFalse(events[0]['reconciliation']['event_base_direction_matches_net'])
        self.assertFalse(events[0]['quote_asset_cash_reconciliation_complete'])

    def test_current_target_and_wsol_do_not_count_as_other_mints(self):
        response,profiles,user=self.fixture()
        profiles[user]['mint']='target'
        self.assertEqual(prior_swap_events(response,profiles)[0],[])
        profiles[user]['mint']='original_target'
        for balance in response['body']['result']['meta']['preTokenBalances']+response['body']['result']['meta']['postTokenBalances']:
            balance['mint']=WSOL
        self.assertEqual(prior_swap_events(response,profiles)[0],[])


if __name__=='__main__':unittest.main()
