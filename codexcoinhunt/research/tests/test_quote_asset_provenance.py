"""Exact asset/role/precision checks. Fixtures are not trading observations."""
import base64
import copy
import unittest
import test_buyer_enrichment as enrichment_tests
from buyer_enrichment import enriched_events
from buyer_probe import PUMP_AMM, b58, WSOL
from quote_asset_provenance import (audit_buy, token_transfer, execution_instructions,
    owned_changes, current_accounts, related_roles, TOKEN, USDC, POOL_DISC)


class QuoteAssetTests(unittest.TestCase):
    def fixture(self):
        tx,pool,_=enrichment_tests.EnrichmentTests().fixture()
        user=tx['transaction']['message']['accountKeys'][0]['pubkey']
        tx['transaction']['message']['accountKeys'][0]['signer']=True
        event=enriched_events(tx,'sig',pool,'target','2026-10-12T01:00:00Z')[0][0]
        event.update(mint='target',signature='sig')
        q=event['quote_token_account']
        tx['transaction']['message']['accountKeys'] += [{'pubkey':q},{'pubkey':'vault'}]
        tx['transaction']['message']['instructions']=[
          {'programId':TOKEN,'parsed':{'type':'initializeAccount3','info':{'account':q,'mint':WSOL,'owner':user}}},
          {'programId':TOKEN,'parsed':{'type':'transferChecked','info':{'source':q,'destination':'vault',
             'authority':user,'mint':WSOL,'tokenAmount':{'amount':'100','decimals':9}}}}]
        tx['meta']['preTokenBalances'].append({'accountIndex':3,'owner':'pool_owner','mint':WSOL,
                                             'uiTokenAmount':{'amount':'0','decimals':9}})
        tx['meta']['postTokenBalances'].append({'accountIndex':3,'owner':'pool_owner','mint':WSOL,
                                              'uiTokenAmount':{'amount':'100','decimals':9}})
        tx['blockTime']=100;tx['meta']['fee']=5000
        response={'request':{'method':'getTransaction','params':['sig',{'commitment':'finalized'}]},
                  'body':{'result':tx},'received_at_utc':'2026-10-12T08:00:00Z'}
        return response,event,user,q

    def test_event_quote_is_separate_from_verified_outflow(self):
        response,e,_,_=self.fixture();a=audit_buy(response,e)
        self.assertEqual(a['verified_quote_transfer_out_raw'],'100')
        self.assertEqual(a['event_reported_quote_raw'],'52')
        self.assertFalse(a['event_quote_matches_whole_account_outflow'])
        self.assertEqual(a['event_vs_outflow_difference_raw'],'48')
        self.assertFalse(a['realized_profit_usd_verified'])
        self.assertFalse(a['complete_cost_reconciliation'])

    def test_exact_quote_owner_and_user_signer_required(self):
        response,e,_,_=self.fixture();tx=response['body']['result']
        tx['transaction']['message']['instructions'][0]['parsed']['info']['owner']='other'
        self.assertEqual(audit_buy(response,e)['status'],'exact_quote_mint_owner_not_verified')
        response,e,_,_=self.fixture();response['body']['result']['transaction']['message']['accountKeys'][0]['signer']=False
        self.assertEqual(audit_buy(response,e)['status'],'exact_authorized_buy_not_verified')

    def test_failed_caught_and_unfinalized_rejected(self):
        response,e,_,_=self.fixture()
        for cause in ('failure','caught','finality'):
            r=copy.deepcopy(response)
            if cause=='failure':r['body']['result']['meta']['err']={'failed':True}
            if cause=='caught':r['body']['result']['meta']['logMessages'].append('Program router failed: caught')
            if cause=='finality':r['request']['params'][1]['commitment']='processed'
            a=audit_buy(r,e)
            self.assertNotIn('verified_quote_transfer_out_raw',a)
            if cause!='finality':self.assertEqual(a['historical_transaction_fee_lamports'],5000)

    def test_transfer_requires_exact_program_mint_and_decimals(self):
        response,e,user,q=self.fixture();ix=response['body']['result']['transaction']['message']['instructions'][1]
        identities={q:{'mint':WSOL,'owner':user},'vault':{'mint':WSOL,'owner':'pool'}}
        self.assertIsNotNone(token_transfer(ix,[],identities)[0])
        ix['programId']='spoof';ix['program']='spl-token'
        self.assertIsNone(token_transfer(ix,[],identities)[0])
        ix['programId']=TOKEN;ix['parsed']['info']['tokenAmount']['decimals']=6
        self.assertEqual(token_transfer(ix,[],identities)[1],'wrong_wsol_decimals')
        ix['parsed']['info']['tokenAmount']['decimals']=9;identities['vault']['mint']='other'
        self.assertEqual(token_transfer(ix,[],identities)[1],'unverified_or_conflicting_legacy_wsol_mint')

    def test_amounts_remain_raw_integers_without_float_or_boolean_coercion(self):
        response,e,user,q=self.fixture();ix=response['body']['result']['transaction']['message']['instructions'][1]
        identities={q:{'mint':WSOL,'owner':user},'vault':{'mint':WSOL,'owner':'pool'}}
        for amount in (0.1,True,-1,'1.2','-1'):
            ix['parsed']['info']['tokenAmount']['amount']=amount
            self.assertEqual(token_transfer(ix,[],identities)[1],'invalid_raw_token_amount')
        ix['parsed']['info']['tokenAmount']['amount']='10000000000000000001'
        self.assertEqual(token_transfer(ix,[],identities)[0]['amount_raw'],'10000000000000000001')

    def test_execution_order_interleaves_outer_and_cpi(self):
        tx={'transaction':{'message':{'accountKeys':[],'instructions':[{'programId':'router'},{'programId':'later'}]}},
            'meta':{'innerInstructions':[{'index':0,'instructions':[{'programId':'pool','stackHeight':2},
                       {'programId':TOKEN,'stackHeight':3}]}]}}
        sequence=list(execution_instructions(tx))
        self.assertEqual([x[0] for x in sequence],['outer:0','inner:0:0','inner:0:1','outer:1'])
        self.assertEqual(sequence[2][2],['router','pool'])

    def test_missing_stack_height_does_not_invent_parent(self):
        tx={'transaction':{'message':{'accountKeys':[],'instructions':[{'programId':'router'}]}},
            'meta':{'innerInstructions':[{'index':0,'instructions':[{'programId':'unknown'},
                       {'programId':TOKEN,'stackHeight':3}]}]}}
        sequence=list(execution_instructions(tx))
        self.assertIsNone(sequence[1][2]);self.assertIsNone(sequence[2][2])

    def test_owned_asset_changes_aggregate_all_accounts_in_exact_mint(self):
        tx={'meta':{'preTokenBalances':[{'owner':'u','mint':USDC,'uiTokenAmount':{'amount':'100','decimals':6}}],
                     'postTokenBalances':[{'owner':'u','mint':USDC,'uiTokenAmount':{'amount':'40','decimals':6}},
                                          {'owner':'u','mint':USDC,'uiTokenAmount':{'amount':'60','decimals':6}}]}}
        rows,issues=owned_changes(tx,'u');self.assertEqual(issues,[])
        self.assertEqual(rows[0]['net_delta_raw'],'0')
        self.assertFalse(rows[0]['ultimate_funding_or_usd_value_verified'])

    def test_conflicting_decimals_are_unknown(self):
        tx={'meta':{'preTokenBalances':[{'owner':'u','mint':USDC,'uiTokenAmount':{'amount':'100','decimals':6}}],
                     'postTokenBalances':[{'owner':'u','mint':USDC,'uiTokenAmount':{'amount':'100','decimals':9}}]}}
        rows,issues=owned_changes(tx,'u');self.assertEqual(rows,[])
        self.assertEqual(issues[0]['reason'],'conflicting_decimals')

    def test_common_fee_payer_and_current_route_owner_do_not_certify_people(self):
        common={'status':'exact_buy_and_quote_route_audited','user':'A','fee_payer':'payer',
                'quote_transfer_in':[{'source_account':'shared_vault','source_token_owner':'authority'}]}
        other=copy.deepcopy(common);other['user']='B'
        states=[{'address':'authority','owner_program':'program','bytes':100,'executable':False,
                 'available_at_utc':'2026-10-12T08:00:00Z'}]
        rows=related_roles([common,other],states)
        self.assertTrue(rows[0]['current_program_owned_data_account'])
        self.assertFalse(rows[0]['historical_service_role_verified'])
        self.assertFalse(rows[0]['classify_as_same_person_or_initial_funder'])
        self.assertFalse(rows[1]['same_owner_or_shared_initial_funder_verified'])

    def test_current_pool_requires_discriminator_and_is_not_historical(self):
        raw=bytearray(301);raw[:8]=POOL_DISC
        value={'owner':PUMP_AMM,'data':[base64.b64encode(raw).decode(),'base64'],'executable':False}
        r={'request':{'params':[['pool'],{'commitment':'finalized'}]},'body':{'result':{'context':{'slot':1},'value':[value]}},
           'received_at_utc':'2026-10-12T08:00:00Z'}
        row=current_accounts(r)[0];self.assertIn('pool_quote_vault',row)
        self.assertFalse(row['historical_owner_role_verified'])
        raw[:8]=b'bad_data';value['data'][0]=base64.b64encode(raw).decode()
        self.assertNotIn('pool_quote_vault',current_accounts(r)[0])

    def test_legacy_token_multisig_or_uninitialized_data_is_not_token_account(self):
        raw=bytearray(355);raw[108]=1
        value={'owner':TOKEN,'data':[base64.b64encode(raw).decode(),'base64'],'executable':False}
        r={'request':{'params':[['account'],{'commitment':'finalized'}]},'body':{'result':{'value':[value]}},'received_at_utc':'now'}
        self.assertNotIn('token_owner',current_accounts(r)[0])
        raw=bytearray(165);value['data'][0]=base64.b64encode(raw).decode()
        self.assertNotIn('token_owner',current_accounts(r)[0])
        raw[108]=1;value['data'][0]=base64.b64encode(raw).decode()
        self.assertIn('token_owner',current_accounts(r)[0])

    def test_transfer_authority_is_separate_from_source_owner(self):
        response,e,user,q=self.fixture();ix=response['body']['result']['transaction']['message']['instructions'][1]
        ix['parsed']['info']['authority']='delegate'
        identities={q:{'mint':WSOL,'owner':user},'vault':{'mint':WSOL,'owner':'pool'}}
        movement,_=token_transfer(ix,[],identities)
        self.assertEqual(movement['source_token_owner'],user)
        self.assertEqual(movement['transfer_authority'],'delegate')

    def test_unparsed_quote_instruction_prevents_complete_outflow_comparison(self):
        response,e,_,q=self.fixture()
        response['body']['result']['transaction']['message']['instructions'].append(
            {'programId':TOKEN,'accounts':[q,'unknown'],'data':'opaque'})
        a=audit_buy(response,e)
        self.assertIsNone(a['event_quote_matches_whole_account_outflow'])
        self.assertEqual(a['flow_attribution_issues'][0]['reason'],'unparsed_token_instruction_referencing_quote_account')

    def test_cash_disposal_with_route_credit_is_not_fresh_fiat_proof(self):
        response,e,user,q=self.fixture();tx=response['body']['result'];message=tx['transaction']['message']
        message['accountKeys'] += [{'pubkey':'route_source'},{'pubkey':'cash_account'}]
        message['instructions'].insert(1,{'programId':TOKEN,'parsed':{'type':'transferChecked','info':{
            'source':'route_source','destination':q,'authority':'route_program','mint':WSOL,
            'tokenAmount':{'amount':'100','decimals':9}}}})
        for field,amount in [('preTokenBalances','1000'),('postTokenBalances','900')]:
            tx['meta'][field].append({'accountIndex':4,'owner':'route_authority','mint':WSOL,
                                       'uiTokenAmount':{'amount':amount,'decimals':9}})
        tx['meta']['preTokenBalances'].append({'accountIndex':5,'owner':user,'mint':USDC,
                                              'uiTokenAmount':{'amount':'100','decimals':6}})
        tx['meta']['postTokenBalances'].append({'accountIndex':5,'owner':user,'mint':USDC,
                                               'uiTokenAmount':{'amount':'0','decimals':6}})
        a=audit_buy(response,e)
        self.assertEqual(a['mechanism_class'],'stablecoin_disposal_with_routed_wsol')
        self.assertEqual(a['verified_quote_transfer_in_raw'],'100')
        self.assertFalse(a['new_external_funding_from_route_credit_verified'])
        self.assertFalse(a['independent_buyer_certified'])


if __name__=='__main__':unittest.main()
