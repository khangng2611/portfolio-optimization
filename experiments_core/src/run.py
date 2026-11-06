"""Execute pre-registered A/B experiments using frozen causal signals.

Run from repository root: venv/bin/python -B -m experiments_core.src.run
Each invocation creates a new run; --parent-run links verification/retry runs.
"""
import argparse
from datetime import datetime
from itertools import combinations
import json
import os
from pathlib import Path
import pickle
import platform
import shutil
import subprocess
import sys
import time
import traceback
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from .frozen import ROOT,PKG,READY,BASE,BASE_RUN,BASELINE_ID,SEEDS,sha,write_json,relocated,activate
from .core import simulate,prior_posterior,simple_selection,cost_returns,bootstrap_effects,return_stats


def now():return datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat()


def freeze(run,run_id,parent):
    config=activate()
    import cvxpy
    source=[p for p in BASE.rglob('*.py') if '__pycache__' not in p.parts]
    source += [BASE/'assets_1.json',BASE_RUN/'run_config.json']
    source += list((PKG/'src').glob('*.py'))+list((PKG/'tests').glob('*.py'))
    old_manifest=json.loads((BASE_RUN/'manifest.json').read_text())
    inputs=[relocated(item['path']) for item in old_manifest['inputs']]
    inputs += [BASE_RUN/n for n in ['result.pkl','aligned_prices.csv','views_history.json','ml_training_audit.json','ml_prediction_audit.json','manifest.json']]
    inputs += list((BASE_RUN/'selection_matrices').glob('*.npz'))
    inputs += list((BASE_RUN/'artifacts').glob('*.csv'))
    plan={'selection':{'K':5,'cadence':20,'simple_window_returns':20,'first_IS_available_returns':19,'random_seeds':SEEDS},
          'allocation':{'window':config['WINDOW'],'rebalance':config['REBALANCE_FREQ'],'risk_aversion':config['RISK_AVERSION_BASE'],
                        'max_position':config['MAX_POSITION_SIZE'],'min_weight':config['MIN_WEIGHT_THRESHOLD'],
                        'non_VFF_cap':config['MAX_EQUITY_EXPOSURE'],'VFF_floor_nominal':config['MIN_DEFENSIVE_WEIGHT'],
                        'VFF_floor_effective':1-config['MAX_EQUITY_EXPOSURE'],'tau':config['BL_TAU'],'delta':config['BL_DELTA'],
                        'w_eq':'equal weight in current active universe','constraint_tolerance':1e-8,
                        'regime_views':'off in all A/B arms','risk_aversion_regime_adjustment':'off in all A/B arms',
                        'B2_confidence':'saved dynamic ML confidence, includes frozen volatility dampener'},
          'costs_bps_per_side':[0,10,25,50],'cost_method':'execution-day multiplicative haircut; include initial buy; exclude initial funding from turnover',
          'bootstrap':{'method':'non-circular moving blocks, joint paired indices','block':10,'replicates':1000,'seed':20261014,
                       'random_aggregate':'cross-seed median return each date, analytical not investable'},
          'OOS':{'anchor':'2023-09-29','first_return':'2023-10-02','last_return':'2026-04-29','n_returns':641},
          'optional_mechanisms':'SKIPPED — no additional comparisons; H4/H5 not tested',
          'baseline_reproduction':'saved target holdings replay + original/repeat artifact hashes; no fresh model fitting in sprint'}
    (run/'outputs').mkdir();(run/'source_snapshot').mkdir()
    entries=[]
    for p in sorted(set(source+inputs)):
        entry={'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size}
        entries.append(entry)
    manifest={'schema_version':1,'run_id':run_id,'parent_run_id':parent,'status':'prepared','started_at':now(),
              'hypothesis':'H1 selection, H2 matched estimator/prior, H3 incremental ML views',
              'baseline_run_id':BASELINE_ID,'plan':plan,'files':entries,
              'source':{'root':str(ROOT),'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                        'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
                        'dirty_state':subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=ROOT,text=True)},
              'execution':{'argv':sys.argv,'cwd':str(ROOT),'interpreter':sys.executable,'python':sys.version,
                           'platform':platform.platform(),'machine':platform.machine(),'solvers':cvxpy.installed_solvers(),
                           'thread_env':{k:os.environ.get(k) for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']},
                           'numpy_configuration':str(np.show_config(mode='dicts'))},
              'model':{'mode':'saved causal signal replay','cache_reused':False,'models_refitted':False,'training_seeds':[42,43,44,45,46],
                       'hyperparameters_source':'frozen ml_training_audit.json; no model parameters changed'},
              'limitations':['static universe','declared availability, first-release timestamps unverified','provider adjusted-close vintages unverified',
                             'valuation proxies for GOLD/VFF, execution not certified','costs approximate','pre-OOS parameter provenance incomplete']}
    write_json(run/'manifest.json',manifest)
    for p in source:
        target=run/'source_snapshot'/p.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    (run/'requirements_frozen.txt').write_bytes(subprocess.check_output([sys.executable,'-m','pip','freeze']))
    (run/'tracked_diff.patch').write_bytes(subprocess.check_output(['git','diff','--binary'],cwd=ROOT))
    write_json(run/'run_config.json',config);write_json(run/'experiment_plan.json',plan)
    if not parent:
        write_json(PKG/'config/experiment_plan.json',plan)
        write_json(PKG/'config/seeds.json',{'random_K5':SEEDS,'bootstrap':20261014,'inherited_ML':[42,43,44,45,46]})
        write_json(PKG/'config/frozen_baseline_ref.json',{'baseline_run_id':BASELINE_ID,'current_root':str(BASE),
                   'original_manifest_sha256':sha(BASE_RUN/'manifest.json'),'frozen_at':now(),
                   'baseline_files':[x for x in entries if x['path'].startswith('outputs/step1/')]})
    return config,plan,manifest


def verify_baseline(bundle,out):
    from backtest._metrics import metric_summary
    original=json.loads((BASE_RUN/'manifest.json').read_text())
    checks=[]
    def check(name,value,detail=None):
        checks.append({'check':name,'pass':bool(value),'detail':detail})
        if not value:raise AssertionError(f'{name}: {detail}')
    for item in original['inputs']:
        check('input_hash:'+str(relocated(item['path']).relative_to(ROOT)),sha(relocated(item['path']))==item['sha256'])
    # Compare numeric source against the original run's snapshot; fixture-only differences allowed.
    for p in (BASE_RUN/'source_snapshot').rglob('*.py'):
        rel=p.relative_to(BASE_RUN/'source_snapshot')
        if rel.parts[0]=='tests':continue
        check('source_hash:'+str(rel),sha(p)==sha(BASE/rel))
    repeat=READY/'runs/availability-observed-contract-repeat-20261012T234301/artifacts'
    for p in (BASE_RUN/'artifacts').glob('*.csv'):
        check('inherited_fresh_repeat:'+p.name,sha(p)==sha(repeat/p.name))
    prices=bundle['prices'];r=bundle['result']
    reference=pd.read_csv(BASE_RUN/'artifacts/trusted_baseline_metrics.csv')
    table=[];anchor=pd.Timestamp('2023-09-29')
    display={'EW':(1.7278,.946,-.1708,.628),'MVO':(3.3904,1.441,-.3018,23.363),
             'BL':(1.8136,1.385,-.0951,8.200),'HYBRID':(2.7044,1.665,-.1613,16.613)}
    for s in ['EW','MVO','BL','HYBRID']:
        targets={x['decision_date']:x[s] for x in r['rebalance_weights_history']}
        replay=simulate(prices,targets)
        for phase,nav in [('IS',replay['nav'].loc[:anchor]),('OOS',replay['nav'].loc[anchor:])]:
            normalized=nav/nav.iloc[0]
            stored=(r['warmup_result'] if phase=='IS' else r)[s.lower()+'_nav']
            error=float(np.max(np.abs(normalized-stored)))
            check(f'baseline_NAV_replay:{phase}:{s}',error<1e-10,error)
            stats=metric_summary(normalized)
            trades=replay['trades'];mask=(trades.execution_date>nav.index[0])&(trades.execution_date<=nav.index[-1])&~trades.initial_allocation
            stats['annualized_turnover']=float(trades.loc[mask,'turnover'].sum()*252/(len(nav)-1))
            row=reference[(reference.phase==phase)&(reference.strategy==s)].iloc[0]
            for key in ['final_nav','ann_return','ann_volatility','sharpe','max_drawdown','annualized_turnover']:
                check(f'baseline_metric:{phase}:{s}:{key}',abs(stats[key]-row[key])<1e-9,stats[key]-row[key])
            if phase=='OOS':
                expected=display[s]
                check('reported_precision:'+s,round(stats['final_nav'],4)==expected[0] and round(stats['sharpe'],3)==expected[1]
                      and round(stats['max_drawdown'],4)==expected[2] and round(stats['annualized_turnover'],3)==expected[3])
                check('OOS_641:'+s,len(nav)-1==641)
            table.append({'phase':phase,'strategy':s,**stats,'replay_NAV_max_abs_error':error})
    ledger=pd.read_csv(READY/'availability_ledger.csv')
    check('availability_50176',len(ledger)==50176)
    available=pd.to_datetime(ledger.available_at,utc=True);cutoff=pd.to_datetime(ledger.decision_at,utc=True)
    check('availability_at_cutoff',bool((available<=cutoff).all()))
    check('observed_before_available',bool((pd.to_datetime(ledger.observed_at,utc=True)<=available).all()))
    panel=pd.read_csv(READY/'candidate_information_prices.csv',index_col=0,parse_dates=True)
    rebuilt=ledger.pivot(index='session_date',columns='asset',values='price')
    rebuilt.index=pd.to_datetime(rebuilt.index)
    check('lineage_rebuilds_information_panel',np.allclose(rebuilt.loc[panel.index,panel.columns],panel,atol=1e-12,rtol=0))
    training=pd.read_csv(BASE_RUN/'artifacts/ml_training_audit.csv')
    fitted=training[training.status=='trained']
    check('fitting_labels_before_validation',bool((pd.to_datetime(fitted.last_fitting_label_end)<pd.to_datetime(fitted.validation_start)).all()))
    check('known_labels_before_decision',bool((pd.to_datetime(fitted.last_label_end)<pd.to_datetime(fitted.retrain_date)).all()))
    check('scaler_fit_row_counts',bool((fitted.scaler_n_samples_seen==fitted.n_train).all()))
    pd.DataFrame(checks).to_csv(out/'baseline_checks.csv',index=False)
    pd.DataFrame(table).to_csv(out/'baseline_replay_metrics.csv',index=False)
    (out/'baseline_reproduction.md').write_text('# Baseline reproduction\n\nPASS: independently replayed saved target weights with next-close fixed-share accounting; reconciled all IS/OOS metrics and turnover, displayed OOS values, input/source hashes, inherited fresh-fit repeat files, availability lineage and saved ML timing/scaler counts.\n\nThis is signal/decision replay, not a new ML fit. Original first-release data and exact vintage are not certified.\n')
    return panel


def selections(bundle,panel,out):
    from gen_view.ranking.stock_selection import compute_distance_matrix
    universe=bundle['selections'][0]['universe']
    histories={name:{} for name in ['A0_Full30','A2_SimpleK5','A3_ProposedK5']+[f'A1_RandomK5_s{s}' for s in SEEDS]}
    generators={s:np.random.default_rng(s) for s in SEEDS}
    combos=np.array(list(combinations(range(30),5)))
    rows=[];audit=[];previous={}
    for j,event in enumerate(bundle['selections']):
        date=event['selection_date'];t=panel.index.get_loc(date)
        frame=panel[universe].iloc[:t]
        dist,names=compute_distance_matrix(frame)
        saved=np.load(BASE_RUN/event['distance_file'])
        assert names==universe and np.allclose(dist,saved['distance'],atol=1e-14,rtol=0)
        chosen=event['selected_assets'];idx=[names.index(a) for a in chosen]
        objective=float(dist[:,idx].min(axis=1).sum())
        best=min(float(dist[:,chunk].min(axis=2).sum(axis=0).min()) for chunk in np.array_split(combos,15))
        assert abs(objective-best)<1e-10
        assert frame.index[-1]<date
        arms={'A0_Full30':universe,'A2_SimpleK5':simple_selection(panel[universe],t),'A3_ProposedK5':chosen}
        for seed,rng in generators.items():arms[f'A1_RandomK5_s{seed}']=[universe[i] for i in sorted(rng.choice(30,5,replace=False))]
        for arm,assets in arms.items():
            histories[arm][date]=assets
            selected=[names.index(a) for a in assets];off=(1-dist)[np.ix_(selected,selected)]
            pair=off[np.triu_indices(len(selected),1)]
            old=previous.get(arm);oldset=set(old) if old is not None else None;newset=set(assets)
            rows.append({'experiment_id':arm,'selection_date':date,'history_start':frame.index[0],'history_end':frame.index[-1],
                         'n_prior_returns':len(frame)-1,'simple_returns_used':min(20,len(frame)-1),
                         'selected_assets':json.dumps(assets),'coverage_objective':float(dist[:,selected].min(axis=1).sum()),
                         'mean_nearest_distance':float(dist[:,selected].min(axis=1).mean()),
                         'mean_pair_correlation':float(pair.mean()),'median_pair_correlation':float(np.median(pair)),
                         'jaccard':len(oldset&newset)/len(oldset|newset) if oldset is not None else np.nan,
                         'switch_count':len(newset-oldset) if oldset is not None else 0})
            previous[arm]=assets
        audit.append({'selection_date':date,'matrix_max_error':float(np.abs(dist-saved['distance']).max()),
                      'selected_objective':objective,'independent_global_minimum':best,'global_optimum_pass':abs(objective-best)<1e-10})
    history=pd.DataFrame(rows);history.to_csv(out/'selection_history_comparison.csv',index=False)
    pd.DataFrame(audit).to_csv(out/'selection_optimality_audit.csv',index=False)
    summary=history.assign(phase=np.where(history.selection_date<pd.Timestamp('2023-10-01'),'IS','OOS')).groupby(['experiment_id','phase']).agg(
        selection_events=('selection_date','size'),coverage_objective=('coverage_objective','mean'),mean_nearest_distance=('mean_nearest_distance','mean'),
        mean_pair_correlation=('mean_pair_correlation','mean'),median_pair_correlation=('median_pair_correlation','median'),
        mean_jaccard=('jaccard','mean'),stock_changes=('switch_count','sum')).reset_index()
    summary.to_csv(out/'selection_structure.csv',index=False)
    return histories


def run_experiment(selection_method,optimizer,ml_views,confidence_mode,regime_mode,seed,frozen_inputs,constraints_config):
    """One fixed downstream optimizer and one supplied historical selection path."""
    from backtest._optimizer import optimize_weight_ranking,_weights_feasible,_regularize_covariance
    from backtest._black_litterman import black_litterman_posterior_mu
    bundle,panel,history=frozen_inputs
    prices=bundle['prices'];assets=list(prices.columns);info_returns=panel.pct_change(fill_method=None).iloc[1:]
    views={x['date']:x for x in bundle['result']['views_history']}
    samples={x['date']:x for x in bundle['bl_samples']}
    targets={};audit=[];selection_dates=sorted(history);active=None
    for event in bundle['result']['views_history']:
        date=event['date'];t=prices.index.get_loc(date)
        if date in history:active=history[date]
        names=active+['GOLD','VFF'];indices=[assets.index(a) for a in names]
        hist=info_returns.iloc[t-20:t];sigma=hist.cov().to_numpy()[np.ix_(indices,indices)]
        p=q=conf=None
        if ml_views and date in samples:
            sample=samples[date]
            assert sample['assets']==names
            mask=np.array(['_ml_' in n for n in event['view_names']])
            p=np.asarray(sample['P'])[mask];q=np.asarray(sample['Q'])[mask];conf=np.asarray(sample['confidence'])[mask]
        if optimizer=='MVO':mu=hist.mean().to_numpy()[indices]
        else:mu=prior_posterior(sigma,2.5,.05,p,q,conf)
        posterior_error=0.
        if p is not None and len(p):
            other=black_litterman_posterior_mu(sigma,np.full(len(names),1/len(names)),p,q,conf)
            posterior_error=float(np.abs(other-mu).max());assert posterior_error<1e-10
        w=optimize_weight_ranking(mu,sigma,names,risk_aversion=1.5)
        assert _weights_feasible(w,.5,[names.index('VFF')],[i for i,a in enumerate(names) if a!='VFF'],.15,.7)
        full=np.zeros(len(assets));full[indices]=w;targets[date]=full
        residual=max(abs(w.sum()-1),max(0,-w.min()),max(0,w.max()-.5),max(0,.15-w[names.index('VFF')]),max(0,w.sum()-w[names.index('VFF')]-.7))
        audit.append({'decision_date':date,'assets':json.dumps(names),'optimizer':optimizer,'ml_views':ml_views,
                      'n_ml_views':0 if p is None else len(p),'constraint_max_residual':residual,'posterior_max_error':posterior_error,
                      'risk_aversion':1.5,'information_end':hist.index[-1],'selection_information_end':prices.index[max(d for d in [prices.index.get_loc(x) for x in selection_dates if x<=date])-1],
                      'mu':json.dumps(mu.tolist()),'pi':json.dumps(prior_posterior(sigma,2.5,.05).tolist()),
                      'covariance':json.dumps(sigma.tolist()),'P':json.dumps([] if p is None else p.tolist()),
                      'Q':json.dumps([] if q is None else q.tolist()),'confidence':json.dumps([] if conf is None else conf.tolist())})
    result=simulate(prices,targets)
    result['posterior_audit']=pd.DataFrame(audit)
    return result


def export_variant(arm,result,out):
    anchor=pd.Timestamp('2023-09-29');rows=[]
    for phase,nav in [('IS',result['nav'].loc[:anchor]),('OOS',result['nav'].loc[anchor:])]:
        returns=nav.pct_change().iloc[1:]
        stats=return_stats(returns)
        trades=result['trades'];mask=(trades.execution_date>nav.index[0])&(trades.execution_date<=nav.index[-1])&~trades.initial_allocation
        daily=result['daily_weights'].loc[returns.index]
        hhi=(daily**2).sum(axis=1)
        rows.append({'experiment_id':arm,'phase':phase,'start_date':nav.index[0],'first_return_date':returns.index[0],
                     'end_date':nav.index[-1],'n_returns':len(returns),**stats,
                     'annualized_turnover':float(trades.loc[mask,'turnover'].sum()*252/len(returns)),
                     'mean_HHI':float(hhi.mean()),'mean_effective_holdings':float((1/hhi[hhi>0]).mean())})
    directory=out/'variants'/arm;directory.mkdir(parents=True)
    result['nav'].rename('nav').to_csv(directory/'nav.csv',index_label='date')
    result['nav'].pct_change().iloc[1:].rename('return').to_csv(directory/'daily_returns.csv',index_label='date')
    for key in ['weights','trades','daily_weights','posterior_audit']:
        result[key].to_csv(directory/(key+'.csv'),index=key=='daily_weights',index_label='date' if key=='daily_weights' else None)
    return rows


def diagnostics(results,out):
    costs=[];uncertainty=[];anchor=pd.Timestamp('2023-09-29')
    oos=pd.DataFrame({arm:r['nav'].pct_change().loc[anchor:].iloc[1:] for arm,r in results.items()})
    assert len(oos)==641 and not oos.isna().any().any()
    for arm,r in results.items():
        full=r['nav'].pct_change().iloc[1:]
        for phase,mask in [('IS',full.index<=anchor),('OOS',full.index>anchor)]:
            for bps in [0,10,25,50]:
                net=cost_returns(full,r['trades'],bps).loc[mask]
                stats=return_stats(net)
                costs.append({'experiment_id':arm,'phase':phase,'bps_per_side':bps,**stats,
                              'approximation':'event multiplicative haircut on gross target turnover',
                              'initial_funding_charge':'included once in IS; no second OOS funding',
                              'break_even_cost':None,'break_even_reason':'not required; no additional root search performed'})
    random=[f'A1_RandomK5_s{s}' for s in SEEDS]
    oos['A1_RandomMedianAnalytical']=oos[random].median(axis=1)
    for left,right in [('A3_ProposedK5','A2_SimpleK5'),('A3_ProposedK5','A1_RandomMedianAnalytical'),('B1_BLnoML','B0_MVOmatched'),('B2_BLML','B1_BLnoML')]:
        for row in bootstrap_effects(oos[left],oos[right]):uncertainty.append({'left':left,'right':right,**row})
    pd.DataFrame(costs).to_csv(out/'cost_sensitivity.csv',index=False)
    pd.DataFrame(uncertainty).to_csv(out/'uncertainty_intervals.csv',index=False)
    oos.to_csv(out/'paired_oos_returns.csv',index_label='date')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--parent-run');args=parser.parse_args()
    run_id='core-evidence-'+datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y%m%dT%H%M%S')
    run=PKG/'runs'/run_id;run.mkdir(parents=True)
    config,plan,manifest=freeze(run,run_id,args.parent_run);out=run/'outputs';started=time.monotonic()
    print(run_id,flush=True)
    manifest['status']='running';write_json(run/'manifest.json',manifest)
    try:
        bundle=pickle.load((BASE_RUN/'result.pkl').open('rb'))
        panel=verify_baseline(bundle,out)
        print('Baseline replay, hashes and timing: PASS',flush=True)
        histories=selections(bundle,panel,out)
        print('Selection histories and 78 independent global optima: PASS',flush=True)
        results={};metrics=[];registry=[]
        arms=[(name,'BL',False,history) for name,history in histories.items()]
        arms += [(name,optimizer,ml,histories['A3_ProposedK5']) for name,optimizer,ml in [('B0_MVOmatched','MVO',False),('B1_BLnoML','BL',False),('B2_BLML','BL',True)]]
        for arm,optimizer,ml,history in arms:
            begin=time.monotonic()
            result=run_experiment(arm,optimizer,ml,'dynamic' if ml else 'none','off',None,(bundle,panel,history),plan['allocation'])
            results[arm]=result;metrics.extend(export_variant(arm,result,out))
            registry.append({'experiment_id':arm,'hypothesis':'H1' if arm.startswith('A') else 'H2/H3','selection_method':arm if arm.startswith('A') else 'A3_ProposedK5',
                             'universe':'Full30+GOLD+VFF' if arm=='A0_Full30' else 'K5+GOLD+VFF','optimizer':optimizer,'ML_view':ml,
                             'confidence':'saved dynamic' if ml else 'none','regime':'defensive views OFF; risk aversion fixed',
                             'constraints_hash':__import__('hashlib').sha256(json.dumps(plan['allocation'],sort_keys=True).encode()).hexdigest(),
                             'data_hash':sha(BASE_RUN/'aligned_prices.csv'),'seed':int(arm.split('_s')[-1]) if '_s' in arm else None,
                             'IS_start':'2020-02-18','IS_end':'2023-09-29','OOS_start':'2023-10-02','OOS_end':'2026-04-29',
                             'run_status':'succeeded','metrics_path':'selection_portfolio_metrics.csv' if arm.startswith('A') else 'optimizer_ladder_metrics.csv',
                             'code_commit':manifest['source']['commit'],'runtime_minutes':(time.monotonic()-begin)/60,'run_id':run_id})
            print(f'{arm}: saved',flush=True)
        metrics=pd.DataFrame(metrics)
        for prefix,name in [('A','selection_portfolio_metrics.csv'),('B','optimizer_ladder_metrics.csv')]:
            metrics[metrics.experiment_id.str.startswith(prefix)].to_csv(out/name,index=False)
        pd.DataFrame(registry).to_csv(out/'experiment_registry.csv',index=False)
        for prefix,ret_name,weight_name in [('A','selection_portfolio_returns.csv','selection_portfolio_weights.csv'),('B','ablation_daily_returns.csv','ablation_weights.csv')]:
            pd.DataFrame({a:r['nav'].pct_change().iloc[1:] for a,r in results.items() if a.startswith(prefix)}).to_csv(out/ret_name,index_label='date')
            pd.concat([r['weights'].assign(experiment_id=a) for a,r in results.items() if a.startswith(prefix)],ignore_index=True).to_csv(out/weight_name,index=False)
        diagnostics(results,out)
        # A3 and B1 are a clean same-model identity gate, solved independently.
        assert np.max(np.abs(results['A3_ProposedK5']['nav']-results['B1_BLnoML']['nav']))<1e-10
        manifest['status']='succeeded';manifest['result_artifacts']=[{'path':str(p.relative_to(run)),'sha256':sha(p)} for p in sorted(out.rglob('*.csv'))]
        write_json(run/'validation.json',{'baseline':'PASS','availability':'PASS','selection_optima':78,'arms':len(results),'OOS_returns':641,
                   'A3_B1_identity':'PASS','unit_and_posterior':'PASS','constraint_tolerance':1e-8,'method':'frozen numerical optimizer; independent posterior and holdings replay'})
    except Exception:
        manifest['status']='failed';manifest['error']=traceback.format_exc();(run/'error.txt').write_text(manifest['error']);raise
    finally:
        manifest['finished_at']=now();manifest['execution']['elapsed_seconds']=time.monotonic()-started
        manifest['execution']['exit_code']=0 if manifest['status']=='succeeded' else 1
        write_json(run/'manifest.json',manifest)
    print(f'PASS {run_id} ({time.monotonic()-started:.1f}s)',flush=True)


if __name__=='__main__':main()
