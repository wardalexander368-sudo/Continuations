import base64
import json
import pathlib
import struct
import unittest
from buyer_probe import BUY_DISC, PUMP_AMM, b58
from buyer_enrichment import EVENT_IX_TAG, enriched_events, token_reconciliation, concentration, unb58

ROOT=pathlib.Path(__file__).resolve().parents[1]


class EnrichmentTests(unittest.TestCase):
    def fixture(self,logs=True,cpi=True):
        numbers=[1,100,1,1,1,1000,2000,50,20,1,5,1,51,52]
        pubkeys=[bytes([n])*32 for n in range(1,8)]
        payload=BUY_DISC+struct.pack('<q13Q',*numbers)+b''.join(pubkeys)
        pool,user,account=b58(pubkeys[0]),b58(pubkeys[1]),b58(pubkeys[2])
        tx={'slot':1,'transaction':{'message':{'accountKeys':[{'pubkey':user},{'pubkey':account}]}},'meta':{
            'err':None,'logMessages':([f'Program {PUMP_AMM} invoke [1]','Program data: '+base64.b64encode(payload).decode(),f'Program {PUMP_AMM} success'] if logs else []),
            'innerInstructions':([{'index':0,'instructions':[{'programId':PUMP_AMM,'data':b58(EVENT_IX_TAG+payload)}]}] if cpi else []),
            'preTokenBalances':[{'accountIndex':1,'mint':'target','owner':user,'uiTokenAmount':{'amount':'0','decimals':6}}],
            'postTokenBalances':[{'accountIndex':1,'mint':'target','owner':user,'uiTokenAmount':{'amount':'100','decimals':6}}]}}
        return tx,pool,payload

    def test_dual_event_representations_are_counted_once(self):
        tx,pool,_=self.fixture()
        events,errors=enriched_events(tx,'sig',pool,'target','2026-10-12T00:00:00Z')
        self.assertEqual(errors,[]);self.assertEqual(len(events),1)
        self.assertEqual(set(events[0]['evidence_paths']),{'log','cpi'})

    def test_cpi_only_event_is_recovered(self):
        tx,pool,_=self.fixture(logs=False)
        events,_=enriched_events(tx,'sig',pool,'target','2026-10-12T00:00:00Z')
        self.assertEqual(len(events),1);self.assertEqual(set(events[0]['evidence_paths']),{'cpi'})

    def test_wrong_program_or_tag_is_not_cpi_event(self):
        tx,pool,payload=self.fixture(logs=False)
        ix=tx['meta']['innerInstructions'][0]['instructions'][0]
        ix['programId']='spoof'
        self.assertEqual(enriched_events(tx,'sig',pool,'target','now')[0],[])
        ix['programId']=PUMP_AMM;ix['data']=b58(b'12345678'+payload)
        self.assertEqual(enriched_events(tx,'sig',pool,'target','now')[0],[])

    def test_two_identical_occurrences_are_not_collapsed(self):
        tx,pool,_=self.fixture()
        tx['meta']['logMessages'].insert(2,tx['meta']['logMessages'][1])
        tx['meta']['innerInstructions'][0]['instructions']*=2
        self.assertEqual(len(enriched_events(tx,'sig',pool,'target','now')[0]),2)

    def test_exact_account_owner_and_mint_are_required(self):
        tx,pool,_=self.fixture();events,_=enriched_events(tx,'sig',pool,'target','now');e=events[0]
        self.assertTrue(e['reconciliation']['verified'])
        self.assertTrue(e['reconciliation']['single_event_amount_matches_transaction_net'])
        tx['meta']['postTokenBalances'][0]['mint']='other'
        self.assertFalse(token_reconciliation(tx,e,'target')['verified'])
        tx['meta']['postTokenBalances'][0]['mint']='target'
        tx['meta']['postTokenBalances'][0]['owner']='other'
        self.assertFalse(token_reconciliation(tx,e,'target')['verified'])

    def test_failed_transactions_do_not_count_cpi_buys(self):
        tx,pool,_=self.fixture();tx['meta']['err']={'failed':1}
        self.assertEqual(enriched_events(tx,'sig',pool,'target','now')[0],[])

    def test_notional_diversity_is_not_raw_wallet_count(self):
        c=concentration([{'user':'A','user_quote_raw':'900'},{'user':'B','user_quote_raw':'100'}])
        self.assertEqual(c['raw_event_users'],2)
        self.assertAlmostEqual(c['notional_effective_user_count'],1/.82)

    def test_base58_roundtrip_preserves_leading_zeros(self):
        raw=b'\0\0'+bytes(range(1,30))
        self.assertEqual(unb58(b58(raw)),raw)
        with self.assertRaises(ValueError):unb58('0')


if __name__=='__main__':unittest.main()
