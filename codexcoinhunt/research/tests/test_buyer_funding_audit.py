"""Adversarial provenance checks; synthetic fixtures, no investment outcomes."""
import copy
import unittest
import test_buyer_enrichment as enrichment_tests
from buyer_funding_audit import audit_transaction, source_relations, SYSTEM
from buyer_probe import WSOL


class FundingEvidenceTests(unittest.TestCase):
    def fixture(self):
        wallet='wallet'; source='source'
        tx={'blockTime':100,'slot':1,'transaction':{'message':{'accountKeys':[
                {'pubkey':wallet,'signer':True},{'pubkey':source,'signer':True}],
                'instructions':[{'programId':SYSTEM,'program':'system','parsed':{'type':'transfer',
                     'info':{'source':source,'destination':wallet,'lamports':20_000_000}}}]}},
            'meta':{'err':None,'fee':5000,'preBalances':[100_000_000,100_000_000],
                    'postBalances':[119_995_000,80_000_000],'logMessages':[],
                    'preTokenBalances':[],'postTokenBalances':[],'innerInstructions':[]}}
        response={'request':{'method':'getTransaction','params':['sig',{'commitment':'finalized'}]},
                  'body':{'result':tx},'received_at_utc':'2026-10-12T07:00:00Z'}
        profile={'wallet':wallet,'start_unix_time':0,'cutoff_unix_time':200,'materiality_lamports':10_000_000}
        plan={'pool':'pool','mint':'mint','historical_event_coin_creator':'creator',
              'selection':[profile,{'wallet':'other'}]}
        return response,profile,plan

    def test_material_signed_receipt_does_not_certify_initial_funding(self):
        response,p,plan=self.fixture();a=audit_transaction(response,p,plan)
        payment=a['incoming_system_payments'][0]
        self.assertTrue(payment['material_direct_receipt_candidate'])
        self.assertFalse(payment['first_funding_root_verified'])
        self.assertFalse(payment['retained_external_funding_verified'])
        self.assertFalse(a['initial_funding_or_independence_verified'])

    def test_signer_and_exact_program_not_alias_are_required(self):
        response,p,plan=self.fixture();tx=response['body']['result']
        tx['transaction']['message']['accountKeys'][1]['signer']=False
        a=audit_transaction(response,p,plan)
        self.assertEqual(a['incoming_system_payments'][0]['classification'],'source_not_transaction_signer')
        tx['transaction']['message']['instructions'][0]['programId']='spoof'
        a=audit_transaction(response,p,plan)
        self.assertEqual(a['incoming_system_payments'],[])
        self.assertEqual(a['unknown_instructions'][0]['reason'],'parsed_program_alias_does_not_verify_program_id')

    def test_failed_caught_unfinalized_and_future_bodies_are_rejected(self):
        original,p,plan=self.fixture()
        for change in ('failed','caught','unfinalized','future'):
            response=copy.deepcopy(original);tx=response['body']['result']
            if change=='failed':tx['meta']['err']={'InstructionError':[0,'failed']}
            if change=='caught':tx['meta']['logMessages']=['Program parent failed: caught']
            if change=='unfinalized':response['request']['params'][1]['commitment']='processed'
            if change=='future':tx['blockTime']=200
            a=audit_transaction(response,p,plan)
            self.assertNotIn('incoming_system_payments',a,msg=change)
            if change=='failed':self.assertEqual(a['transaction_fee_lamports'],5000)

    def test_dust_and_self_transfers_are_preserved_without_root_claims(self):
        response,p,plan=self.fixture();info=response['body']['result']['transaction']['message']['instructions'][0]['parsed']['info']
        info['lamports']=1
        self.assertEqual(audit_transaction(response,p,plan)['incoming_system_payments'][0]['classification'],'below_frozen_materiality')
        info['source']=p['wallet'];info['lamports']=20_000_000
        self.assertEqual(audit_transaction(response,p,plan)['incoming_system_payments'][0]['classification'],'self_transfer')

    def test_token_account_source_is_not_external_native_wallet(self):
        response,p,plan=self.fixture();tx=response['body']['result']
        tx['meta']['preTokenBalances']=[{'accountIndex':1,'mint':WSOL,'owner':p['wallet']}]
        a=audit_transaction(response,p,plan)
        self.assertEqual(a['incoming_system_payments'][0]['classification'],'token_account_source_not_external_wallet')

    def test_wrapped_sol_close_is_not_a_separate_external_funder(self):
        response,p,plan=self.fixture();tx=response['body']['result']
        tx['meta']['preTokenBalances']=[{'accountIndex':1,'mint':WSOL,'owner':p['wallet']}]
        tx['transaction']['message']['instructions']=[{'programId':'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',
           'parsed':{'type':'closeAccount','info':{'account':'source','destination':p['wallet'],'owner':p['wallet']}}}]
        a=audit_transaction(response,p,plan)
        self.assertEqual(a['incoming_system_payments'],[])
        self.assertEqual(a['token_account_closures'][0]['classification'],'wrapped_SOL_release')
        self.assertFalse(a['token_account_closures'][0]['independent_funder_verified'])

    def test_balance_increase_alone_is_not_external_funding(self):
        response,p,plan=self.fixture();tx=response['body']['result']
        tx['transaction']['message']['instructions']=[]
        a=audit_transaction(response,p,plan)
        self.assertGreater(a['native_balance']['net_change_lamports'],0)
        self.assertFalse(a['native_balance']['external_funding_attribution_verified'])
        self.assertEqual(a['incoming_system_payments'],[])

    def test_identical_instruction_occurrences_remain_two_payments(self):
        response,p,plan=self.fixture();tx=response['body']['result']
        tx['transaction']['message']['instructions']*=2
        payments=audit_transaction(response,p,plan)['incoming_system_payments']
        self.assertEqual(len(payments),2)
        self.assertNotEqual(payments[0]['instruction_path'],payments[1]['instruction_path'])

    def test_shared_unknown_and_distinct_sources_do_not_certify_owners(self):
        response,p,plan=self.fixture();a=audit_transaction(response,p,plan)
        b=copy.deepcopy(a);b['wallet']='other'
        relations=source_relations([a,b],plan)
        self.assertEqual(relations[0]['relation'],'shared_unknown_source_candidate')
        self.assertFalse(relations[0]['same_owner_cluster_verified'])
        self.assertEqual(relations[0]['independent_clusters_verified'],0)
        b['incoming_system_payments'][0]['source']='different'
        self.assertTrue(all(r['independent_clusters_verified']==0 for r in source_relations([a,b],plan)))

    def test_verified_service_is_excluded_from_common_owner_grouping(self):
        response,p,plan=self.fixture();a=audit_transaction(response,p,plan)
        b=copy.deepcopy(a);b['wallet']='other'
        registry={'source':{'category':'service','source_url':'https://example.test/official',
                            'available_at_utc':'2026-10-12T07:00:00Z'}}
        relation=source_relations([a,b],plan,registry)[0]
        self.assertEqual(relation['relation'],'verified_service_excluded_from_common_owner_grouping')
        self.assertFalse(relation['same_owner_cluster_verified'])
        self.assertEqual(source_relations([a,b],plan,{'source':{'category':'service'}})[0]['service_status'],'unknown')

    def test_creator_fee_role_payment_is_relationship_not_person_proof(self):
        response,p,plan=self.fixture();a=audit_transaction(response,p,plan)
        a['incoming_system_payments'][0]['source']='creator'
        relation=source_relations([a],plan)[0]
        self.assertEqual(relation['relation'],'payment_from_historical_event_creator_fee_role')
        self.assertFalse(relation['same_owner_cluster_verified'])

    def test_prior_exact_authorized_swap_falsifies_first_time_entry_evidence(self):
        tx,pool,_=enrichment_tests.EnrichmentTests().fixture()
        wallet=tx['transaction']['message']['accountKeys'][0]['pubkey']
        tx['transaction']['message']['accountKeys'][0]['signer']=True;tx['blockTime']=100
        response={'request':{'method':'getTransaction','params':['sig',{'commitment':'finalized'}]},
                  'body':{'result':tx},'received_at_utc':'2026-10-12T07:00:00Z'}
        p={'wallet':wallet,'start_unix_time':0,'cutoff_unix_time':200,'materiality_lamports':1}
        plan={'pool':pool,'mint':'target'}
        a=audit_transaction(response,p,plan)
        self.assertEqual(len(a['prior_target_swap_events']),1)
        self.assertEqual(set(a['prior_target_swap_events'][0]['evidence_paths']),{'log','cpi'})
        tx['transaction']['message']['accountKeys'][0]['signer']=False
        self.assertEqual(audit_transaction(response,p,plan)['prior_target_swap_events'],[])

    def test_unsolicited_inventory_without_authorized_trade_is_not_prior_buy(self):
        response,p,plan=self.fixture();tx=response['body']['result']
        tx['meta']['postTokenBalances']=[{'accountIndex':1,'owner':p['wallet'],'mint':plan['mint'],
                                        'uiTokenAmount':{'amount':'1'}}]
        a=audit_transaction(response,p,plan)
        self.assertEqual(len(a['prior_target_inventory']),1)
        self.assertEqual(a['prior_target_swap_events'],[])

    def test_transient_wrapped_sol_account_requires_initializer_identity(self):
        response,p,plan=self.fixture();tx=response['body']['result']
        token='TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
        close={'programId':token,'parsed':{'type':'closeAccount','info':{
               'account':'source','destination':p['wallet'],'owner':p['wallet']}}}
        tx['transaction']['message']['instructions']=[close]
        self.assertEqual(audit_transaction(response,p,plan)['token_account_closures'][0]['classification'],
                         'token_account_close_identity_unknown')
        initialize={'programId':token,'parsed':{'type':'initializeAccount3','info':{
                    'account':'source','mint':WSOL,'owner':p['wallet']}}}
        tx['transaction']['message']['instructions']=[initialize,close]
        record=audit_transaction(response,p,plan)['token_account_closures'][0]
        self.assertEqual(record['classification'],'wrapped_SOL_release')
        self.assertEqual(record['source_token_owner'],p['wallet'])
        self.assertEqual(record['identity_evidence_paths'],['outer:0'])
        self.assertFalse(record['independent_funder_verified'])

    def test_conflicting_token_identity_stays_unknown(self):
        response,p,plan=self.fixture();tx=response['body']['result']
        tx['meta']['preTokenBalances']=[{'accountIndex':1,'mint':WSOL,'owner':p['wallet']}]
        tx['meta']['postTokenBalances']=[{'accountIndex':1,'mint':'conflict','owner':p['wallet']}]
        tx['transaction']['message']['instructions']=[{'programId':'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',
          'parsed':{'type':'closeAccount','info':{'account':'source','destination':p['wallet'],'owner':p['wallet']}}}]
        record=audit_transaction(response,p,plan)['token_account_closures'][0]
        self.assertEqual(record['classification'],'token_account_close_identity_unknown')
        self.assertFalse(record['source_owner_proof_available'])


if __name__=='__main__':unittest.main()
