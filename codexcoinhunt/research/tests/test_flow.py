import json
import pathlib
import unittest
from flow_study import asof, entered_count, replay, trade_signals

ROOT=pathlib.Path(__file__).resolve().parents[1]


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.cfg=json.loads((ROOT/'flow_config.json').read_text())
    def q(self,t,bid=99.9,ask=100.1,size=100):
        return {'source':t-2,'available':t,'bid':bid,'ask':ask,'bid_size':size,'ask_size':size,'mid':(bid+ask)/2,'spread_bps':(ask-bid)/((ask+bid)/2)*10000}

    def test_future_quote_is_not_asof_signal(self):
        self.assertIsNone(asof([self.q(11)],10,2))
        self.assertIsNotNone(asof([self.q(9)],10,2))
        self.assertIsNone(asof([self.q(7)],10,2))

    def test_correct_direction_can_still_lose_after_fees(self):
        entry=self.q(10);exit=self.q(3610,bid=100.0,ask=100.2)
        path=replay([entry,exit],0,7,self.cfg)
        self.assertGreater(path['gross_mid_return'],0)
        self.assertLess(path['net_return'],0)

    def test_missing_quote_is_not_a_filled_entry(self):
        path=replay([],0,7,self.cfg)
        self.assertEqual(path['status'],'missing_entry_quote')
        self.assertNotIn('entry_at',path)
        self.assertEqual(entered_count({'entries':[path]}),0)

    def test_censored_exit_keeps_open_allocation(self):
        path=replay([self.q(10)],0,7,self.cfg)
        self.assertEqual(path['status'],'censored_exit')
        self.assertNotIn('proceeds',path)
        self.assertEqual(entered_count({'entries':[path]}),1)

    def test_insufficient_exit_size_is_not_full_recovery(self):
        path=replay([self.q(10),self.q(3610,size=.001)],0,7,self.cfg)
        self.assertEqual(path['status'],'insufficient_exit_depth')
        self.assertNotIn('proceeds',path)

    def test_signed_flow_uses_only_prior_window(self):
        trades=[{'symbol':'DOGE/USD','source':1,'i':1,'p':1,'s':50,'tks':'B'},{'symbol':'DOGE/USD','source':80,'i':2,'p':1,'s':1,'tks':'S'}]
        signals=trade_signals(trades,self.cfg)
        self.assertEqual(len(signals),1)
        self.assertEqual(signals[0]['decision'],3)

    def test_unknown_taker_side_not_favorable_buy(self):
        t={'symbol':'DOGE/USD','source':1,'i':1,'p':1,'s':100,'tks':'?'}
        self.assertEqual(trade_signals([t],self.cfg),[])


if __name__=='__main__':unittest.main()
