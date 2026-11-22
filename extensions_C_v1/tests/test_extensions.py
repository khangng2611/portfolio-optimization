import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd

try:
    from extensions_C_v1.C1_fixed_rule import fixed_targets,resolve_membership,validate_index_metadata,align_total_return
except ImportError:
    fixed_targets=resolve_membership=validate_index_metadata=align_total_return=None

from experiments_core.src.core import simulate,cost_returns,return_stats,bootstrap_effects


class ExtensionsTests(unittest.TestCase):
    def test_rule_is_minimum_concentration_feasible(self):
        self.assertIsNotNone(fixed_targets,'C1 fixed-rule implementation is missing')
        names=['A','B','C','D','E','F','GOLD','VFF']
        w=fixed_targets(names,['A','B','C','D','E'])
        np.testing.assert_allclose(w,[7/60]*5+[0,7/60,.3],rtol=0,atol=1e-15)
        self.assertAlmostEqual(w@w,.17166666666666666)

    def test_missing_or_duplicate_instrument_fails(self):
        self.assertIsNotNone(fixed_targets,'C1 fixed-rule implementation is missing')
        with self.assertRaises(ValueError):fixed_targets(['A','B','C','D','E','GOLD'],['A','B','C','D','E'])
        with self.assertRaises(ValueError):fixed_targets(['A','B','C','D','E','GOLD','VFF'],['A','A','C','D','E'])

    def test_future_membership_cannot_enter_current_decision(self):
        self.assertIsNotNone(resolve_membership,'C1 membership resolver is missing')
        events=[{'selection_date':'2023-01-02','history_end':'2022-12-30','selected_assets':['A','B','C','D','E']},
                {'selection_date':'2023-01-10','history_end':'2023-01-09','selected_assets':['A','B','C','D','F']}]
        self.assertEqual(resolve_membership(events,pd.Timestamp('2023-01-09'))['selected_assets'][-1],'E')
        self.assertEqual(resolve_membership(events,pd.Timestamp('2023-01-10'))['selected_assets'][-1],'F')

    def test_reselection_exit_and_entry_turnover_in_union(self):
        dates=pd.date_range('2020-01-01',periods=5)
        prices=pd.DataFrame({'A':[1]*5,'B':[1]*5},index=dates)
        r=simulate(prices,{dates[0]:np.array([1.,0.]),dates[2]:np.array([0.,1.])},0)
        self.assertAlmostEqual(r['trades'].iloc[-1].turnover,1.)
        self.assertAlmostEqual(r['trades'].iloc[-1].traded_notional,2.)
        np.testing.assert_allclose(r['weights'].tail(2).weight_change,[-1,1])

    def test_new_position_cannot_earn_execution_day_jump(self):
        dates=pd.date_range('2020-01-01',periods=4)
        p=pd.DataFrame({'A':[1,2,4,8],'B':[1,1,1,1]},index=dates)
        r=simulate(p,{dates[0]:np.array([.5,.5])},0)
        np.testing.assert_allclose(r['nav'],[1,1,1.5,2.5])

    def test_initial_and_terminal_cost_not_omitted(self):
        dates=pd.date_range('2020-01-01',periods=4)
        p=pd.DataFrame({'A':[1]*4,'B':[1]*4},index=dates)
        r=simulate(p,{dates[0]:np.array([1.,0.]),dates[2]:np.array([0.,1.])},0)
        net=cost_returns(r['nav'].pct_change().iloc[1:],r['trades'],100)
        np.testing.assert_allclose(net,[-.01,0.,-.02])
        self.assertAlmostEqual(np.prod(1+net),.9702)

    def test_hand_calculated_metrics(self):
        r=return_stats(np.array([.1,-.1]))
        self.assertAlmostEqual(r['final_nav'],.99)
        self.assertAlmostEqual(r['max_drawdown'],-.1)
        self.assertAlmostEqual(r['ann_volatility'],np.sqrt(5.04))
        self.assertAlmostEqual(r['ann_return'],.99**126-1)

    def test_joint_bootstrap_identical_paths(self):
        a=np.linspace(-.01,.02,30)
        for r in bootstrap_effects(a,a,replicates=20,seed=20261104):
            self.assertEqual(r['effect'],0);self.assertEqual(r['ci_low'],0);self.assertEqual(r['ci_high'],0)

    def test_price_index_and_missing_rights_are_rejected(self):
        self.assertIsNotNone(validate_index_metadata,'C2 source gate is missing')
        with self.assertRaises(ValueError):validate_index_metadata({'identifier':'VN30','return_type':'price'})
        with self.assertRaises(ValueError):validate_index_metadata({'identifier':'VN30TRI','return_type':'total_return','research_use_permitted':False})

    def test_alignment_does_not_bridge_missing_sessions(self):
        self.assertIsNotNone(align_total_return,'C2 alignment implementation is missing')
        dates=pd.date_range('2023-01-01',periods=6)
        levels=pd.DataFrame({'index_date':dates[[0,1,3,4,5]],'index_level':[100,110,120,132,145.2]})
        aligned,report=align_total_return(levels,dates)
        self.assertTrue(pd.isna(aligned.loc[dates[2]]))
        self.assertTrue(pd.isna(aligned.loc[dates[3]]))
        self.assertAlmostEqual(aligned.loc[dates[4]],.1)
        self.assertEqual(report['missing_levels'],1)

    def test_valid_total_return_metadata_gate(self):
        meta={k:'synthetic test only' for k in ['identifier','name','provider','dividend_method','methodology_url',
              'vintage','first_public_availability','retrieved_at','rights_evidence']}
        meta.update(identifier='VN30TRI',return_type='total_return',currency='VND',research_use_permitted=True)
        self.assertTrue(validate_index_metadata(meta))

    def test_c2_shorter_sample_recomputes_both_portfolios(self):
        from extensions_C_v1 import C2_market
        dates=pd.bdate_range('2023-09-29',periods=10)
        meta={k:'synthetic test only' for k in ['identifier','name','provider','dividend_method','methodology_url',
              'vintage','first_public_availability','retrieved_at','rights_evidence']}
        meta.update(identifier='VN30TRI',return_type='total_return',currency='VND',research_use_permitted=True)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'inputs').mkdir()
            pd.DataFrame({'A':np.ones(10)},index=dates).to_csv(root/'inputs/prices_valuation.csv')
            for name in C2_market.B_NAMES:
                pd.DataFrame({'return':np.full(9,.01)},index=dates[1:]).to_csv(root/'inputs'/f'{name}_daily_returns.csv')
            levels=pd.DataFrame({'index_date':dates,'index_level':100*1.02**np.arange(10),'vendor_record_date':'2026-11-04'})
            levels=levels.drop(index=3) # breaks the daily chain on both sides of the missing level
            with patch.object(C2_market,'HERE',root):
                result=C2_market.compare(levels,meta,root/'output')
            table=pd.read_csv(root/'output/C2_results.csv')
            self.assertEqual(result['used_returns'],5)
            self.assertEqual(set(table.N),{5})
            self.assertEqual(set(table.first_return),{str(dates[5].date())})
            self.assertAlmostEqual(table[table.strategy=='B1_BLnoML'].iloc[0].final_nav,1.01**5)
            self.assertTrue(table.turnover.isna().all())


if __name__=='__main__':unittest.main()
