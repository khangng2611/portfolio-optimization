"""Additional C experiments. Run from repo root with venv/bin/python -B -m extensions_C_v1.C1_fixed_rule."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from experiments_core.src.core import simulate,cost_returns,return_stats,bootstrap_effects
from experiments_core.src.frozen import ROOT,BASE_RUN,READY,sha,write_json

HERE=Path(__file__).resolve().parent
B_RUN=ROOT/'experiments_core/runs/core-evidence-20261023T211011'
C1='C1-FixedRule-K5-7'
B_NAMES=['B1_BLnoML','B2_BLML']
ANCHOR=pd.Timestamp('2023-09-29')


def fixed_targets(assets,selected):
    if len(assets)!=len(set(assets)) or len(selected)!=5 or len(set(selected))!=5 or any(a in ['GOLD','VFF'] for a in selected):
        raise ValueError('Need exactly five distinct equities and unique asset columns')
    if not set(selected+['GOLD','VFF']).issubset(assets):raise ValueError('Missing fixed-rule instrument')
    w=np.zeros(len(assets));w[[assets.index(a) for a in selected+['GOLD']]]=.7/6;w[assets.index('VFF')]=.3
    return w


def resolve_membership(events,decision):
    known=[e for e in events if pd.Timestamp(e['selection_date'])<=decision]
    if not known:raise ValueError('No eligible membership at this decision')
    event=max(known,key=lambda e:pd.Timestamp(e['selection_date']))
    if pd.Timestamp(event['history_end'])>=decision:raise ValueError('Selection history must end before decision')
    return event


def validate_index_metadata(meta):
    required=['identifier','name','provider','currency','return_type','dividend_method','methodology_url',
              'vintage','first_public_availability','retrieved_at','rights_evidence','research_use_permitted']
    missing=[x for x in required if meta.get(x) in [None,'',False]]
    if missing:raise ValueError('C2 missing source/rights fields: '+','.join(missing))
    if meta['return_type']!='total_return' or meta['currency']!='VND':raise ValueError('C2 needs documented VND total-return index')
    if meta['research_use_permitted'] is not True:raise ValueError('C2 research-use permission not established')
    return True


def align_total_return(levels,calendar):
    frame=levels.copy();frame['index_date']=pd.to_datetime(frame.index_date)
    if frame.index_date.duplicated().any() or (frame.index_level<=0).any() or not np.isfinite(frame.index_level).all():
        raise ValueError('Invalid/duplicate total-return levels')
    aligned=frame.set_index('index_date').index_level.reindex(calendar)
    returns=aligned.pct_change(fill_method=None)
    return returns,{'missing_levels':int(aligned.isna().sum()),'missing_return_dates':returns.index[returns.isna()].strftime('%Y-%m-%d').tolist(),
                    'available_one_session_returns':int(returns.notna().sum()),'source_rows':len(frame),'calendar_rows':len(calendar)}


def prepare_inputs():
    inputs=HERE/'inputs';inputs.mkdir(exist_ok=True)
    selected={'prices_valuation.csv':BASE_RUN/'aligned_prices.csv',
              'prices_eligible.csv':READY/'candidate_information_prices.csv','availability_ledger.csv':READY/'availability_ledger.csv',
              'availability_policy.json':READY/'availability_policy.json',
              'selection_history.csv':B_RUN/'outputs/selection_history_comparison.csv',
              'baseline_metrics.csv':B_RUN/'outputs/optimizer_ladder_metrics.csv','baseline_costs.csv':B_RUN/'outputs/cost_sensitivity.csv',
              'baseline_run_manifest.json':B_RUN/'manifest.json','step1_manifest.json':BASE_RUN/'manifest.json',
              'assets_1.json':READY/'candidate_workspace/assets_1.json',
              'experiment_1.md':Path('/Users/nguyenkhang/Documents/MASTER/Thesis/phase2-journal-plan/experiment_1.md')}
    for arm in B_NAMES:
        for name in ['nav.csv','daily_returns.csv','weights.csv','daily_weights.csv','trades.csv','posterior_audit.csv']:
            selected[f'{arm}_{name}']=B_RUN/'outputs/variants'/arm/name
    old=json.loads((B_RUN/'manifest.json').read_text())
    expected={x['path']:x['sha256'] for x in old['files']}
    expected.update({str((B_RUN/x['path']).relative_to(ROOT)):x['sha256'] for x in old['result_artifacts']})
    entries=[]
    for name,source in selected.items():
        if str(source.relative_to(ROOT)) in expected if source.is_relative_to(ROOT) else False:
            assert sha(source)==expected[str(source.relative_to(ROOT))],f'Frozen source changed: {source}'
        target=inputs/name
        if target.exists() and sha(target)!=sha(source):raise AssertionError(f'Input snapshot already differs: {target}')
        if not target.exists():shutil.copy2(source,target)
        entries.append({'snapshot':name,'source':str(source),'sha256':sha(source),'bytes':source.stat().st_size})
    manifest={'schema_version':1,'baseline_run_id':BASE_RUN.name,'B_run_id':B_RUN.name,'created_at':datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),
              'authorization':'User requested execution of experiment_1.md in this chat; existing research inputs reused under same declared scope',
              'raw_data_redistribution_permitted':False,'data_rights_note':'No new raw-vendor publication authorization inferred. Private local snapshots only; publication archive excludes inputs.',
              'historical_publication_verified':False,'static_universe':True,'files':entries}
    path=HERE/'baseline_manifest.json'
    if not path.exists():write_json(path,manifest)
    else:
        prior=json.loads(path.read_text());assert prior['files']==entries
    return inputs


def load_baselines(inputs,prices):
    results={}
    for arm in B_NAMES:
        weights=pd.read_csv(inputs/f'{arm}_weights.csv',parse_dates=['decision_date','execution_date'])
        targets=weights.pivot(index='decision_date',columns='asset',values='target_weight').reindex(columns=prices.columns)
        replay=simulate(prices,{d:r.to_numpy() for d,r in targets.iterrows()})
        saved=pd.read_csv(inputs/f'{arm}_nav.csv',index_col=0,parse_dates=True).nav
        assert replay['nav'].index.equals(saved.index) and np.max(np.abs(replay['nav']-saved))<1e-10
        trades=pd.read_csv(inputs/f'{arm}_trades.csv',parse_dates=['decision_date','execution_date','first_return_date'])
        assert np.max(np.abs(trades.turnover-replay['trades'].turnover))<1e-10
        results[arm]=replay
    return results


def independent_units(prices,targets,start=20):
    units=np.zeros(prices.shape[1]);cash=1.;values=[];unit_rows=[]
    executions={prices.index[prices.index.get_loc(d)+1]:w for d,w in targets.items()}
    for date,p in prices.iloc[start:].iterrows():
        value=float(units@p.to_numpy()+cash);values.append(value)
        if date in executions:units=value*executions[date]/p.to_numpy();cash=0.
        unit_rows.append({'date':date,'cash':cash,**{a:u for a,u in zip(prices.columns,units)}})
    return pd.Series(values,index=prices.index[start:]),pd.DataFrame(unit_rows)


def phase_navs(nav):return [('IS',nav.loc[:ANCHOR]),('OOS',nav.loc[ANCHOR:])]


def analyze(results,out):
    metrics=[];daily=[];trades=[];exposures=[];effects=[];ci=[]
    reference=pd.read_csv(HERE/'inputs/baseline_metrics.csv');reference_cost=pd.read_csv(HERE/'inputs/baseline_costs.csv')
    for name,result in results.items():
        nav=result['nav'];gross=nav.pct_change().iloc[1:]
        full_daily=pd.DataFrame({'date':nav.index,'strategy':name,'gross_nav_continuous':nav.values})
        full_daily['gross_return']=nav.pct_change().values
        w=result['daily_weights'];target=result['weights'].pivot(index='execution_date',columns='asset',values='target_weight')
        for bps in [0,10,25,50]:
            net=cost_returns(gross,result['trades'],bps)
            full_daily[f'net_return_{bps}bps']=net.reindex(nav.index).to_numpy()
            full_daily[f'net_nav_{bps}bps_continuous']=np.r_[1.,np.cumprod(1+net)]
            for phase,phase_nav in phase_navs(nav):
                r=net.loc[phase_nav.index[1:]];stats=return_stats(r)
                event=result['trades'];mask=(event.execution_date>phase_nav.index[0])&(event.execution_date<=phase_nav.index[-1])&~event.initial_allocation
                selected_target=target.loc[(target.index>phase_nav.index[0])&(target.index<=phase_nav.index[-1])]
                daily_hhi=(w.loc[r.index]**2).sum(axis=1);target_hhi=(selected_target**2).sum(axis=1)
                row={'strategy':name,'phase':phase,'bps_per_side':bps,'nav_anchor':phase_nav.index[0],
                     'first_return_date':r.index[0],'last_return_date':r.index[-1],'N':len(r),**stats,
                     'annualized_turnover':float(event.loc[mask,'turnover'].sum()*252/len(r)),
                     'mean_target_HHI':float(target_hhi.mean()),'mean_daily_HHI':float(daily_hhi.mean()),
                     'mean_effective_holdings':float((1/daily_hhi[daily_hhi>0]).mean()),'effective_holdings_definition':'mean of 1/HHI over positive-investment return days',
                     'cost_method':'approximate execution-day multiplicative gross-target haircut','initial_funding':'charged once in IS, excluded from TO; none repeated OOS'}
                metrics.append(row)
                if name in B_NAMES:
                    ref=reference_cost[(reference_cost.experiment_id==name)&(reference_cost.phase==phase)&(reference_cost.bps_per_side==bps)].iloc[0]
                    assert all(abs(stats[k]-ref[k])<1e-10 for k in stats),f'Frozen metric/cost mismatch {name}/{phase}/{bps}'
                    if bps==0:
                        ref=reference[(reference.experiment_id==name)&(reference.phase==phase)].iloc[0]
                        assert len(r)==ref.n_returns and abs(row['annualized_turnover']-ref.annualized_turnover)<1e-10
        daily.append(full_daily)
        detail=result['weights'].merge(result['trades'],on=['decision_date','execution_date'],validate='many_to_one')
        detail['strategy']=name
        for bps in [0,10,25,50]:detail[f'event_cost_fraction_{bps}bps']=detail.traded_notional*bps/10000
        trades.append(detail)
        for kind,frame in [('start_of_return_drifted',w),('execution_target',target)]:
            data=pd.DataFrame({'date':frame.index,'strategy':name,'weight_type':kind,
                               'equities':frame.drop(columns=['GOLD','VFF']).sum(axis=1).to_numpy(),
                               'GOLD':frame.GOLD.to_numpy(),'VFF':frame.VFF.to_numpy(),'HHI':(frame**2).sum(axis=1).to_numpy()})
            exposures.append(data)
        result['daily_weights'].to_csv(out/f'{name}_holdings_weights.csv',index_label='return_date')
    results_frame=pd.DataFrame(metrics);results_frame.to_csv(out/'C1_results.csv',index=False)
    pd.concat(daily,ignore_index=True).to_csv(out/'C1_daily.csv',index=False)
    pd.concat(trades,ignore_index=True).to_csv(out/'C1_trades.csv',index=False)
    pd.concat(exposures,ignore_index=True).to_csv(out/'C1_class_exposures.csv',index=False)
    target0=results[C1]['weights'].pivot(index='execution_date',columns='asset',values='target_weight')
    distances=[]
    for other in B_NAMES:
        target=results[other]['weights'].pivot(index='execution_date',columns='asset',values='target_weight')
        assert target.index.equals(target0.index) and target.columns.equals(target0.columns)
        l1=(target-target0).abs().sum(axis=1)
        for date,value in l1.items():distances.append({'execution_date':date,'reference':other,'L1_distance_from_C1':value})
        for phase in ['IS','OOS']:
            for bps in [0,10,25,50]:
                a=results_frame[(results_frame.strategy==C1)&(results_frame.phase==phase)&(results_frame.bps_per_side==bps)].iloc[0]
                b=results_frame[(results_frame.strategy==other)&(results_frame.phase==phase)&(results_frame.bps_per_side==bps)].iloc[0]
                for metric in ['ann_return','sharpe','max_drawdown','annualized_turnover']:
                    scale=100 if metric in ['ann_return','max_drawdown'] else 1
                    effects.append({'left':C1,'right':other,'phase':phase,'bps_per_side':bps,'metric':metric,'effect':scale*(a[metric]-b[metric]),'unit':'percentage_points' if scale==100 else 'ratio_or_turnovers_per_year'})
        ra=results[C1]['nav'].loc[ANCHOR:].pct_change().iloc[1:];rb=results[other]['nav'].loc[ANCHOR:].pct_change().iloc[1:]
        assert ra.index.equals(rb.index) and len(ra)==641
        for row in bootstrap_effects(ra,rb,seed=20261104):
            scale=100 if row['metric']=='ann_return' else 1
            ci.append({'left':C1,'right':other,**{k:v*scale if k in ['effect','ci_low','ci_high'] else v for k,v in row.items()},'unit':'percentage_points' if scale==100 else 'Sharpe'})
    pd.DataFrame(effects).to_csv(out/'comparisons.csv',index=False)
    pd.DataFrame(ci).to_csv(out/'paired_uncertainty.csv',index=False)
    pd.DataFrame(distances).to_csv(out/'target_L1_distances.csv',index=False)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--parent-run');args=parser.parse_args()
    inputs=prepare_inputs();prices=pd.read_csv(inputs/'prices_valuation.csv',index_col=0,parse_dates=True)
    history=pd.read_csv(inputs/'selection_history.csv',parse_dates=['selection_date','history_end'])
    events=history[history.experiment_id=='A3_ProposedK5'].copy()
    events['selected_assets']=events.selected_assets.map(json.loads);events=events.to_dict('records')
    calendar=pd.read_csv(inputs/'B1_BLnoML_trades.csv',parse_dates=['decision_date','execution_date'])
    run_id='extensions-C-'+datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y%m%dT%H%M%S')
    run=HERE/'runs'/run_id;run.mkdir(parents=True);out=run/'outputs';out.mkdir()
    files=[p for p in HERE.glob('*.py')]+list((HERE/'tests').glob('*.py'))+[HERE/'protocol_frozen.md',HERE/'baseline_manifest.json',HERE/'implementation_plan.md',ROOT/'experiments_core/src/core.py']
    manifest={'schema_version':1,'run_id':run_id,'parent_run_id':args.parent_run,'status':'running','started_at':datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),
              'hypothesis':'C1 deterministic feasible weighting versus frozen B1/B2; C2 independently source gated',
              'source':{'root':str(ROOT),'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
                        'dirty_state':subprocess.check_output(['git','status','--porcelain'],text=True),'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in files]},
              'inputs':json.loads((HERE/'baseline_manifest.json').read_text())['files'],
              'protocol_sha256':sha(HERE/'protocol_frozen.md'),'execution':{'argv':sys.argv,'interpreter':sys.executable,'cwd':str(ROOT),'python':sys.version,'platform':platform.platform(),'stdout':'stdout.log','stderr':'stderr.log'},
              'policy':{'model_refit':False,'B1_B2_reoptimized':False,'same_saved_selector':True,'C1_weights':{'VFF':.3,'each_other':.7/6},'costs_bps':[0,10,25,50],
                        'bootstrap':{'block':10,'replicates':1000,'seed':20261104},'constraints_tolerance':1e-8,'prospective_preregistration':False,'independent_new_OOS':False}}
    write_json(run/'manifest.json',manifest)
    for p in files:
        target=run/'source_snapshot'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    (run/'requirements_frozen.txt').write_bytes(subprocess.check_output([sys.executable,'-m','pip','freeze']))
    print(run_id,flush=True);begin=time.monotonic()
    try:
        targets={};membership=[]
        for row in calendar.itertuples():
            event=resolve_membership(events,row.decision_date);w=fixed_targets(list(prices.columns),event['selected_assets']);targets[row.decision_date]=w
            di=prices.index.get_loc(row.decision_date);assert prices.index[di+1]==row.execution_date
            assert abs(w.sum()-1)<1e-8 and w.min()>=0 and w.max()<=.5+1e-8 and abs(w[prices.columns.get_loc('VFF')]-.3)<1e-8
            active=event['selected_assets']+['GOLD','VFF']
            for name in B_NAMES:
                audit=pd.read_csv(inputs/f'{name}_posterior_audit.csv')
                baseline_active=json.loads(audit[audit.decision_date==str(row.decision_date.date())].iloc[0].assets)
                assert active==baseline_active
            membership.append({'decision_index':di,'decision_date':row.decision_date,'assumed_execution_date':row.execution_date,
                               'selection_state_id':str(event['selection_date'].date()),'history_end':event['history_end'],
                               **{f'ticker_{j+1}':a for j,a in enumerate(event['selected_assets'])}})
        pd.DataFrame(membership).to_csv(out/'selected_k5_events.csv',index=False)
        c1=simulate(prices,targets);independent,units=independent_units(prices,targets)
        error=float(np.abs(independent-c1['nav']).max());assert error<1e-10
        assert np.max(np.abs(c1['trades'].traded_notional-2*c1['trades'].turnover))<1e-14
        units.to_csv(out/'C1_units.csv',index=False)
        results={C1:c1,**load_baselines(inputs,prices)}
        analyze(results,out)
        for item in manifest['inputs']:assert sha(Path(item['source']))==item['sha256'] and sha(inputs/item['snapshot'])==item['sha256']
        checks={'status':'PASS','selection_events':len(events),'trade_events':len(calendar),'OOS_return_count':len(c1['nav'].loc[ANCHOR:])-1,
                'independent_units_max_abs_NAV_error':error,'same_B1_B2_memberships':True,'targets_feasible':True,'cost_grid_reconciles_frozen_B1_B2':True,
                'input_hashes_unchanged':True,'traded_notional_equals_2TO':True,'C2_status':'SOURCE_GATE_PENDING'}
        write_json(run/'validation.json',checks)
        manifest['status']='succeeded';manifest['artifacts']=[{'path':str(p.relative_to(run)),'sha256':sha(p)} for p in sorted(out.glob('*.csv'))]
    except Exception:
        manifest['status']='failed';manifest['error']=traceback.format_exc();(run/'error.txt').write_text(manifest['error']);raise
    finally:
        manifest['finished_at']=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat();manifest['execution']['elapsed_seconds']=time.monotonic()-begin
        manifest['execution']['exit_code']=0 if manifest['status']=='succeeded' else 1;write_json(run/'manifest.json',manifest)
    print(f'PASS {run_id}',flush=True)


if __name__=='__main__':main()
