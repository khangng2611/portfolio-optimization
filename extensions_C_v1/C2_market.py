"""Fail-closed total-return comparator. No remote download or implicit data license."""
import argparse
import json
import shutil
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from .C1_fixed_rule import HERE,ANCHOR,B_NAMES,validate_index_metadata,align_total_return
from experiments_core.src.core import return_stats
from experiments_core.src.frozen import sha,write_json


def compare(levels,meta,output):
    validate_index_metadata(meta)
    if meta['identifier'] not in ['VN30TRI','VNINDEXTR']:
        raise ValueError('Index outside the frozen candidate families; review protocol before running')
    if 'vendor_record_date' not in levels or pd.to_datetime(levels.vendor_record_date,errors='coerce',utc=True).isna().any():
        raise ValueError('C2 vendor_record_date missing; do not substitute index_date')
    levels=levels.copy();levels['index_date']=pd.to_datetime(levels.index_date)
    if not levels.index_date.is_monotonic_increasing:raise ValueError('C2 levels must be sorted by observation date')
    prices=pd.read_csv(HERE/'inputs/prices_valuation.csv',index_col=0,parse_dates=True)
    dates=prices.index[prices.index>=ANCHOR]
    r,alignment=align_total_return(levels,dates)
    # Longest contiguous valid single-session return block, earliest tie.
    good=r.iloc[1:].notna().to_numpy();best=(0,0);start=0
    for i in range(len(good)+1):
        if i==len(good) or not good[i]:
            if i-start>best[1]-best[0]:best=(start,i)
            start=i+1
    common=r.index[1:][best[0]:best[1]]
    if len(common)<2:raise ValueError('No usable contiguous common-return sample')
    streams={'VN30TRI' if meta['identifier']=='VN30TRI' else meta['identifier']:r.loc[common]}
    for name in B_NAMES:
        saved=pd.read_csv(HERE/'inputs'/f'{name}_daily_returns.csv',index_col=0,parse_dates=True)['return']
        streams[name]=saved.loc[common]
    frame=pd.DataFrame(streams);rows=[]
    for name in frame:
        rows.append({'strategy':name,'status':'COMPUTED_DESCRIPTIVE','first_return':common[0],'last_return':common[-1],'N':len(common),
                     'anchor':dates[dates.get_loc(common[0])-1],**return_stats(frame[name]),'turnover':None,
                     'turnover_note':'N/A for index; not inferred in descriptive market comparison'})
    output.mkdir(parents=True,exist_ok=True)
    frame.to_csv(output/'C2_market_daily.csv',index_label='return_date');pd.DataFrame(rows).to_csv(output/'C2_results.csv',index=False)
    alignment.update(status='PASS',used_returns=len(common),full_641=len(common)==641,excluded_from_common_sample=int(641-len(common)),
                     selection_rule='longest contiguous valid interval, earliest tie',metadata=meta)
    write_json(output/'C2_alignment.json',alignment)
    # All paths start at one on the same preceding session, including a shorter sample.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    wealth=pd.concat([pd.DataFrame(1.,index=[dates[dates.get_loc(common[0])-1]],columns=frame.columns),(1+frame).cumprod()])
    ax=wealth.plot(figsize=(9,4));ax.set(ylabel='Gross wealth, common anchor = 1',title='C2 descriptive total-return comparison')
    ax.figure.tight_layout();ax.figure.savefig(output/'C2_common_wealth.png',dpi=160);plt.close(ax.figure)
    return alignment


def main():
    p=argparse.ArgumentParser();p.add_argument('--levels',type=Path,required=True);p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() and any(a.output.iterdir()):p.error('Choose a new empty output directory')
    meta=json.loads(a.metadata.read_text());validate_index_metadata(meta)
    a.output.mkdir(parents=True,exist_ok=True)
    # Freeze exact local inputs BEFORE computing any comparison. Raw copies stay private.
    private=a.output/'private_inputs';private.mkdir()
    shutil.copy2(a.levels,private/'levels.csv');shutil.copy2(a.metadata,private/'metadata.json')
    manifest={'status':'running','started_at':datetime.now(timezone.utc).isoformat(),'levels':str(a.levels),
              'levels_sha256':sha(a.levels),'metadata_sha256':sha(a.metadata),'source_sha256':sha(Path(__file__)),
              'protocol_sha256':sha(HERE/'protocol_frozen.md'),'raw_redistribution_permitted':False}
    write_json(a.output/'C2_input_hashes.json',manifest)
    try:
        result=compare(pd.read_csv(private/'levels.csv'),meta,a.output)
        manifest.update(status='succeeded',used_returns=result['used_returns'])
    except Exception as exc:
        manifest.update(status='failed',reason=str(exc));raise
    finally:
        manifest['finished_at']=datetime.now(timezone.utc).isoformat();write_json(a.output/'C2_input_hashes.json',manifest)
    print(json.dumps({'status':result['status'],'N':result['used_returns']}))


if __name__=='__main__':main()
