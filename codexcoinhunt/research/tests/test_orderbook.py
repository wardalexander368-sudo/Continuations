import base64
import copy
import json
import pathlib
import struct
import unittest
from orderbook_study import features, fresh, gate, forward_path, snapshot_ofi, sweep_buy, sweep_sell
from buyer_probe import BUY_DISC, PUMP_AMM, b58, swap_events
from amm_depth import depth_bands

ROOT=pathlib.Path(__file__).resolve().parents[1]


class OrderBookTests(unittest.TestCase):
    def setUp(self):
        self.cfg=json.loads((ROOT/'orderbook_config.json').read_text())
        self.book={'b':[{'p':99,'s':10}], 'a':[{'p':101,'s':10}]}

    def test_far_ask_wall_does_not_count_as_near_demand(self):
        b={'b':[{'p':99.9,'s':10}], 'a':[{'p':100.1,'s':10},{'p':10000,'s':1000}]}
        f=features(b)
        self.assertAlmostEqual(f['near_bid_share'],.4995)
        self.assertLess(f['all_levels_bid_share'],.001)

    def test_fee_is_applied_to_credited_asset_both_sides(self):
        qty=sweep_buy(self.book,7,fee=.0025,adverse=0)
        self.assertAlmostEqual(qty,7/101*.9975,places=8)
        proceeds=sweep_sell(self.book,qty,fee=.0025,adverse=0)
        self.assertAlmostEqual(proceeds,qty*99*.9975,places=8)
        self.assertLess(proceeds,7)

    def test_sweep_uses_more_than_top_level(self):
        b={'a':[{'p':100,'s':.01},{'p':110,'s':1}],'b':[{'p':99,'s':1}]}
        self.assertAlmostEqual(sweep_buy(b,7,fee=0,adverse=0),.01+6/110,places=8)

    def test_depth_exhaustion_is_not_full_fill(self):
        with self.assertRaises(ValueError):sweep_buy(self.book,2000)
        with self.assertRaises(ValueError):sweep_sell(self.book,20)

    def test_source_age_not_http_age_controls_freshness(self):
        row={'available':100,'source_time':90,'age_seconds':10}
        self.assertFalse(fresh(row,100,self.cfg))
        row={'available':100,'source_time':99.5,'age_seconds':.5}
        self.assertTrue(fresh(row,100,self.cfg))
        self.assertFalse(fresh(row,105,self.cfg))

    def test_future_trade_does_not_confirm_current_flow(self):
        b={'b':[{'p':99.9,'s':100}], 'a':[{'p':100.1,'s':10}], 't':'2026-10-12T00:00:00Z'}
        history=[]
        for when in [1,70,80,90]:
            row=features(b);row.update(available=when,source_time=when,age_seconds=0,book=b);history.append(row)
        trades=[{'symbol':'X/USD','p':100,'s':10,'tks':'B','available':91,'source_time':89,'page_complete':True}]
        ok,info=gate('X/USD',history,trades,90,self.cfg)
        self.assertEqual(info['signed_buy_usd'],0)
        self.assertFalse(ok)

    def test_copied_rest_book_does_not_create_persistence(self):
        b={'b':[{'p':99.9,'s':100}], 'a':[{'p':100.1,'s':10}]}
        history=[]
        for when in [70,80,90]:
            row=features(b);row.update(available=when,source_time=89,age_seconds=when-89,book=b);history.append(row)
        _,info=gate('X/USD',history,[],90,self.cfg)
        self.assertFalse(info['persistent'])

    def test_no_exit_book_is_censored_not_threshold_fill(self):
        b={'b':[{'p':99.9,'s':100}], 'a':[{'p':100.1,'s':100}]}
        row=features(b);row.update(available=10,source_time=10,age_seconds=0,book=b)
        result=forward_path('X/USD',{'X/USD':[row]},0,self.cfg)
        self.assertEqual(result['status'],'censored_exit')
        self.assertNotIn('proceeds',result)

    def test_unchanged_top_book_has_zero_snapshot_ofi(self):
        f=features(self.book)
        self.assertEqual(snapshot_ofi(f,f),0)


class BuyerEventTests(unittest.TestCase):
    def make_event(self):
        values=[1,100,1,1,1,1000,2000,50,20,1,5,1,51,52]
        keys=[bytes([x])*32 for x in range(1,8)]
        raw=BUY_DISC+struct.pack('<q13Q',*values)+b''.join(keys)
        pool=b58(keys[0])
        tx={'slot':1,'meta':{'err':None,'logMessages':[f'Program {PUMP_AMM} invoke [1]','Program data: '+base64.b64encode(raw).decode(),f'Program {PUMP_AMM} success']},'_target_mint':'mint'}
        return tx,pool

    def test_failed_transaction_not_buyer_flow(self):
        tx,pool=self.make_event();tx['meta']['err']={'error':'failed'}
        events,_=swap_events(tx,'sig',pool);self.assertEqual(events,[])

    def test_exact_pool_and_invoking_program_required(self):
        tx,pool=self.make_event()
        self.assertEqual(len(swap_events(tx,'sig',pool)[0]),1)
        self.assertEqual(swap_events(tx,'sig','other')[0],[])
        tx['meta']['logMessages'][0]='Program spoof invoke [1]'
        self.assertEqual(swap_events(tx,'sig',pool)[0],[])

    def test_stable_prefix_fields_and_event_identity(self):
        tx,pool=self.make_event();event=swap_events(tx,'sig',pool)[0][0]
        self.assertEqual(event['user_quote_raw'],'52')
        self.assertEqual(event['event_id'],'sig:log:1')
        self.assertFalse(event['account_mint_reconciled'])


class AmmDepthTests(unittest.TestCase):
    def test_virtual_pricing_does_not_create_real_exit_cash(self):
        band=depth_bands(1000,1,999,0,price_changes=[.1])[0]
        self.assertTrue(band['gross_sell_exceeds_real_quote'])
        self.assertEqual(band['real_quote_capacity_raw'],1)

    def test_fee_buckets_cannot_exceed_vault(self):
        with self.assertRaises(ValueError):depth_bands(1000,100,0,101)


if __name__=='__main__':unittest.main()
