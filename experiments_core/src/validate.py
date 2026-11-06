"""Independent checks of saved experiment artifacts; no optimization or training."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .frozen import PKG,BASE_RUN,sha,write_json


def validate(primary,repeat):
    root=PKG/'runs'/primary;out=root/'outputs';other=PKG/'runs'/repeat/'outputs'
    rows=[]
    def check(name,passed,value=None):
        rows.append({'check':name,'pass':bool(passed),'value':value})
        if not passed:raise AssertionError(f'{name}: {value}')
    for p in sorted(out.rglob('*.csv')):
        if p.name=='experiment_registry.csv':continue
        check('deterministic_bytes:'+str(p.relative_to(out)),sha(p)==sha(other/p.relative_to(out)))
    prices=pd.read_csv(BASE_RUN/'aligned_prices.csv',index_col=0,parse_dates=True)
    anchors={'IS':pd.Timestamp('2020-02-18'),'OOS':pd.Timestamp('2023-09-29')}
    metrics=pd.concat([pd.read_csv(out/n) for n in ['selection_portfolio_metrics.csv','optimizer_ladder_metrics.csv']])
    for directory in sorted((out/'variants').iterdir()):
        arm=directory.name
        weights=pd.read_csv(directory/'weights.csv',parse_dates=['execution_date','decision_date'])
        trades=pd.read_csv(directory/'trades.csv',parse_dates=['execution_date','decision_date','first_return_date'])
        targets=weights.pivot(index='execution_date',columns='asset',values='target_weight').reindex(columns=prices.columns)
        check('target_budget:'+arm,np.max(np.abs(targets.sum(axis=1)-1))<1e-8)
        check('long_only:'+arm,targets.min().min()>=-1e-8)
        check('position_cap:'+arm,targets.max().max()<=.5+1e-8)
        check('non_VFF_group_cap:'+arm,targets.drop(columns='VFF').sum(axis=1).max()<=.7+1e-8)
        check('VFF_floor:'+arm,targets.VFF.min()>=.3-1e-8)
        for row in trades.itertuples():
            di=prices.index.get_loc(row.decision_date);ex=prices.index.get_loc(row.execution_date)
            check('next_close:'+arm+':'+str(row.execution_date.date()),ex==di+1)
            check('first_return:'+arm+':'+str(row.execution_date.date()),pd.isna(row.first_return_date) if ex+1==len(prices) else row.first_return_date==prices.index[ex+1])
        # Actual units, independent of the simulator's drifting-weight recurrence.
        units=np.zeros(prices.shape[1]);cash=1.;values=[]
        for date,price in prices.loc['2020-02-18':].iterrows():
            value=float(units@price.to_numpy()+cash);values.append(value)
            if date in targets.index:
                units=value*targets.loc[date].to_numpy()/price.to_numpy();cash=0.
        nav=pd.Series(values,index=prices.loc['2020-02-18':].index)
        saved=pd.read_csv(directory/'nav.csv',index_col=0,parse_dates=True).nav
        error=float(np.max(np.abs(nav-saved)))
        check('independent_units_NAV:'+arm,error<1e-10,error)
        audits=pd.read_csv(directory/'posterior_audit.csv',parse_dates=['decision_date','information_end','selection_information_end'])
        check('covariance_cutoff:'+arm,bool((audits.information_end<=audits.decision_date).all()))
        check('selection_t_minus_1:'+arm,bool((audits.selection_information_end<audits.decision_date).all()))
        check('no_defensive_views:'+arm,int(audits.n_ml_views.max())==0 if arm!='B2_BLML' else True)
        check('posterior_residual:'+arm,audits.posterior_max_error.max()<1e-10,audits.posterior_max_error.max())
        if arm!='B0_MVOmatched' and arm!='B2_BLML':
            error=max(np.max(np.abs(np.array(json.loads(r.mu))-np.array(json.loads(r.pi)))) for r in audits.itertuples())
            check('noML_is_prior:'+arm,error<1e-14,error)
        cost=pd.read_csv(out/'cost_sensitivity.csv')
        for phase in ['IS','OOS']:
            row=metrics[(metrics.experiment_id==arm)&(metrics.phase==phase)].iloc[0]
            zero=cost[(cost.experiment_id==arm)&(cost.phase==phase)&(cost.bps_per_side==0)].iloc[0]
            check('zero_cost_metrics:'+arm+':'+phase,all(abs(row[k]-zero[k])<1e-12 for k in ['final_nav','ann_return','ann_volatility','sharpe','max_drawdown']))
    b0=pd.read_csv(out/'variants/B0_MVOmatched/posterior_audit.csv')
    b1=pd.read_csv(out/'variants/B1_BLnoML/posterior_audit.csv')
    b2=pd.read_csv(out/'variants/B2_BLML/posterior_audit.csv')
    for key in ['decision_date','assets','risk_aversion','information_end','selection_information_end','covariance','pi']:
        check('matched_B_inputs:'+key,b0[key].equals(b1[key]) and b1[key].equals(b2[key]))
    checks=pd.DataFrame(rows);checks.to_csv(root/'independent_checks.csv',index=False)
    write_json(root/'independent_verification.json',{'status':'PASS','checks':len(rows),'primary':primary,'repeat':repeat,
                'all_experiment_csvs_identical_except_runtime_registry':True,'independent_units_replay':True})
    print(f'PASS: {len(rows)} independent checks')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('primary');p.add_argument('repeat');a=p.parse_args();validate(a.primary,a.repeat)
