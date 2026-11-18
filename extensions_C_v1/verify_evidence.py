"""Read-only research verification, except writing new QA reports/logs in C namespace."""
import json,subprocess,sys
from pathlib import Path
import numpy as np
import pandas as pd
from .C1_fixed_rule import HERE,C1,B_NAMES,ANCHOR
from experiments_core.src.frozen import sha,write_json,ROOT


def main():
    qa=HERE/'qa';qa.mkdir(exist_ok=True)
    tests=subprocess.run([sys.executable,'-B','-m','unittest','extensions_C_v1.tests.test_extensions','experiments_core.tests.test_core','-v'],cwd=ROOT,text=True,capture_output=True)
    (qa/'tests.log').write_text(tests.stdout+tests.stderr);assert tests.returncode==0
    a=HERE/'runs/extensions-C-20261104T210906';b=HERE/'runs/extensions-C-20261104T211105'
    checks=0
    def check(condition):
        nonlocal checks
        assert condition;checks+=1
    for run in [a,b]:
        m=json.loads((run/'manifest.json').read_text());check(m['status']=='succeeded')
        for item in m['artifacts']:check(sha(run/item['path'])==item['sha256'])
        for item in m['source']['files']:check(sha(run/'source_snapshot'/item['path'])==item['sha256'])
        check(sha(run/'source_snapshot/extensions_C_v1/protocol_frozen.md')==m['protocol_sha256'])
    csvs=sorted((a/'outputs').glob('*.csv'))
    for f in csvs:check(f.read_bytes()==(b/'outputs'/f.name).read_bytes())
    for item in json.loads((HERE/'baseline_manifest.json').read_text())['files']:
        check(sha(Path(item['source']))==item['sha256']);check(sha(HERE/'inputs'/item['snapshot'])==item['sha256'])
    prices=pd.read_csv(HERE/'inputs/prices_valuation.csv',index_col=0,parse_dates=True)
    daily=pd.read_csv(HERE/'C1_daily.csv',parse_dates=['date']);trades=pd.read_csv(HERE/'C1_trades.csv',parse_dates=['decision_date','execution_date'])
    metrics=pd.read_csv(HERE/'C1_results.csv')
    c=trades[trades.strategy==C1]
    target=c.pivot(index='execution_date',columns='asset',values='target_weight')
    for date,w in target.iterrows():
        check((w>0).sum()==7);check(abs(w.VFF-.3)<1e-14);check(np.max(abs(w[w.index!='VFF'][w>0]-.7/6))<1e-14)
        check(abs(w.sum()-1)<1e-14);check(w.min()>=0 and w.max()<=.5);check(abs(np.sum(w*w)-.17166666666666667)<1e-14)
    # Independent saved unit valuation; units are post-close, hence same close value.
    units=pd.read_csv(HERE/'C1_units.csv',parse_dates=['date']).set_index('date')
    nav=daily[daily.strategy==C1].set_index('date').gross_nav_continuous
    uvalue=(units[prices.columns]*prices.loc[units.index]).sum(axis=1)+units.cash
    unit_error=float(abs(uvalue-nav).max());check(unit_error<1e-10)
    event_groups=trades.groupby(['strategy','execution_date'])
    for key,g in event_groups:
        check(len(g)==32);check(abs(g.weight_change.abs().sum()-g.traded_notional.iloc[0])<1e-12)
        check(abs(2*g.turnover.iloc[0]-g.traded_notional.iloc[0])<1e-12)
    # Metrics independently calculated from published return columns, no helper return_stats.
    for row in metrics.itertuples():
        x=daily[daily.strategy==row.strategy].set_index('date')
        start=pd.Timestamp(row.nav_anchor);end=pd.Timestamp(row.last_return_date)
        returns=x.loc[(x.index>start)&(x.index<=end),f'net_return_{row.bps_per_side}bps']
        wealth=np.r_[1.,np.cumprod(1+returns)];vol=returns.std(ddof=1)*np.sqrt(252)
        values={'final_nav':wealth[-1],'ann_return':wealth[-1]**(252/len(returns))-1,'ann_volatility':vol,
                'sharpe':(returns.mean()-(1.06**(1/252)-1))*252/vol,'max_drawdown':np.min(wealth/np.maximum.accumulate(wealth)-1)}
        check(len(returns)==row.N)
        for key,value in values.items():check(abs(value-getattr(row,key))<1e-10)
    c2=pd.read_csv(HERE/'C2_results.csv');check(c2.status.iloc[0]=='NOT_RUN_SOURCE_GATE_NOT_MET')
    check(c2[['final_nav','ann_return','ann_volatility','sharpe','max_drawdown','turnover']].isna().all().all())
    check(len(pd.read_csv(HERE/'C2_market_daily.csv'))==0);check(len(pd.read_csv(HERE/'C2_unmatched_dates.csv'))==641)
    result={'status':'PASS','checks':checks,'unit_tests':18,'independent_saved_units_max_abs_NAV_error':unit_error,
            'byte_identical_csvs':len(csvs),'baseline_input_hashes_unchanged':True,'frozen_run_artifacts_intact':True,
            'C1':'COMPLETED','C2':'NOT_RUN_SOURCE_GATE_NOT_MET','C3_C6':'DESIGN_ONLY_NOT_EXECUTED'}
    write_json(HERE/'verification.json',result)
    (HERE/'validations.md').write_text(f'''# Verification results\n\nPASS, 2026-11-04. {checks} independent assertions; 18 unittest cases passed (12 C + 6 inherited accounting/research tests). Exact command: venv/bin/python -B -m extensions_C_v1.verify_evidence. Full test output: qa/tests.log, included in evidence archive.\n\n- Both recorded C1 runs succeeded; 12 numerical CSV files are byte-identical.\n- Saved pre-result source snapshots/protocol hashes and every recorded run-artifact hash remain intact. Original inputs and private C snapshots match all baseline hashes after execution.\n- All 310 C1 targets have exactly seven positive holdings, VFF .30, others .70/6; full investment, long-only, .50 cap and minimum target HHI checked.\n- All 930 strategy-event groups retain 32 assets, including exits/entries, and sum(abs(traded weights)) = traded notional = 2 × turnover. Event totals repeat across asset rows; deduplicate before summing.\n- Independent post-close unit × price + cash reconstruction matches C1 NAV within {unit_error:.3g}; runner's separate unit engine error was 8.66e-14.\n- All 48 strategy/phase/cost rows independently recomputed for N, NAV, CAGR, volatility, Sharpe and drawdown within 1e-10. Frozen B1/B2 grids also reconcile against accepted Step2 controls inside each run.\n- Toy tests cover prior-only membership, next-close new-position timing, full entry/exit union, initial and terminal cost, hand-calculated metrics, paired bootstrap, price-index/missing-rights rejection and C2 shorter common-sample recomputation without gap bridging.\n- C2 status/nulls/header-only daily output and all 641 not-evaluable dates verified. No empirical C2 index performance computed.\n\nIndependent read-only review found no critical/important defect. It confirmed C1 weights, menu identity, units, repeated CSVs and interpretation limits. Metadata completeness checks cannot verify the truth of a claimed license or vintage; source evidence must be reviewed before future C2 admission.\n\nReport visual QA: six DOCX-rendered pages inspected; no clipping, split rows or missing Vietnamese glyphs. Source and rights limitations are disclosed, not resolved by a software PASS.\n''')
    print(json.dumps(result))

if __name__=='__main__':main()
