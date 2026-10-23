"""Compare regenerated decisions against archived logs, excluding run timestamps."""
from pathlib import Path
import json,hashlib,csv
ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'outputs/step1/blocker_evidence_20261012/historical_fresh_refit';rows=[];checks={}
for phase,oldname in [('train','views_ranking_absolute_train_20260628_113308.json'),('test','views_ranking_absolute_test_20260628_114800.json')]:
 paths=list((RUN/'workspace/logs').glob(f'views_ranking_absolute_{phase}_*.json'))
 if not paths:checks[phase]={'generated':False};continue
 newpath=paths[0];oldpath=ROOT/'logs'/oldname;new=json.loads(newpath.read_text());old=json.loads(oldpath.read_text())
 phase_checks={k:new[k]==old[k] for k in ['assets','metrics','weights_history','views_history','phase','view_mode','ml_training_mode']}
 checks[phase]=dict(generated=True,all_exact=all(phase_checks.values()),checks=phase_checks,new_file=str(newpath.relative_to(ROOT)),new_sha256=hashlib.sha256(newpath.read_bytes()).hexdigest(),archived_file=str(oldpath.relative_to(ROOT)),archived_sha256=hashlib.sha256(oldpath.read_bytes()).hexdigest(),n_weight_records=len(new['weights_history']),n_view_records=len(new['views_history']))
 for strategy,value in new['metrics'].items():
  for metric,v in value.items():rows.append(dict(phase=phase,strategy=strategy,metric=metric,archived=old['metrics'][strategy][metric],regenerated=v,difference=v-old['metrics'][strategy][metric]))
with (RUN/'metrics_comparison.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['phase','strategy','metric','archived','regenerated','difference']);w.writeheader();w.writerows(rows)
summary=dict(status='BOTH_PHASES_EXACT' if all(checks.get(p,{}).get('all_exact') for p in ['train','test']) else 'PARTIAL',both_phases_exact=all(checks.get(p,{}).get('all_exact') for p in ['train','test']),phases=checks,does_not_prove_original_environment_identity=True,does_not_prove_april_original_run=True,alpha_grid_fresh_fit_performed=False)
(RUN/'comparison_verification.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
