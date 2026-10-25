import unittest
import numpy as np
import pandas as pd
from experiments_core.src.core import simulate, prior_posterior, simple_selection, cost_returns, bootstrap_effects


class CoreTests(unittest.TestCase):
    def test_next_close_and_holdings_drift(self):
        # A target decided Jan 1 executes Jan 2; the Jan 2 jump is not earned.
        dates = pd.date_range('2020-01-01', periods=4)
        prices = pd.DataFrame({'A':[1,2,4,8], 'B':[1,1,1,1]}, index=dates)
        targets = {dates[0]: np.array([.5,.5])}
        result = simulate(prices, targets, start_index=0)
        np.testing.assert_allclose(result['nav'].values, [1,1,1.5,2.5])
        np.testing.assert_allclose(result['daily_weights'].iloc[-1], [2/3,1/3])
        self.assertEqual(result['trades'].iloc[0].execution_date, dates[1])

    def test_last_close_trade_has_no_future_return(self):
        dates = pd.date_range('2020-01-01', periods=3)
        p = pd.DataFrame({'A':[1,1,2], 'B':[1,1,1]},index=dates)
        r = simulate(p,{dates[1]:np.array([1.,0.])},start_index=0)
        self.assertEqual(r['nav'].iloc[-1],1)
        self.assertEqual(r['trades'].iloc[-1].execution_date,dates[-1])

    def test_no_view_is_equilibrium_prior(self):
        sigma = np.diag([.0001,.0004])
        np.testing.assert_allclose(prior_posterior(sigma,2.5,.05), [.000125,.0005],atol=1e-14)

    def test_simple_ignores_decision_and_future_price(self):
        dates=pd.date_range('2020-01-01',periods=25)
        p=pd.DataFrame({'B':np.ones(25),'A':np.ones(25),'C':1+np.arange(25)*.01},index=dates)
        before=simple_selection(p,21,k=2)
        p.iloc[21:]=1e9
        self.assertEqual(before,['A','B'])
        self.assertEqual(simple_selection(p,21,k=2),before)

    def test_per_side_cost_on_execution_and_final_date(self):
        dates=pd.date_range('2020-01-01',periods=3)
        gross=pd.Series([.1,.2],index=dates[1:])
        trades=pd.DataFrame({'execution_date':dates[1:], 'traded_notional':[1.,2.], 'initial_allocation':[True,False]})
        net=cost_returns(gross,trades,100)
        np.testing.assert_allclose(net, [.089,.176])
        np.testing.assert_array_equal(cost_returns(gross,trades,0),gross)

    def test_paired_bootstrap_preserves_identical_streams(self):
        a=np.linspace(-.01,.02,40)
        result=bootstrap_effects(a,a,block=10,replicates=50,seed=20261014)
        for row in result:
            self.assertAlmostEqual(row['effect'],0)
            self.assertAlmostEqual(row['ci_low'],0)
            self.assertAlmostEqual(row['ci_high'],0)


if __name__ == '__main__':
    unittest.main()
