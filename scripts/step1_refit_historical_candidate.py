"""Fresh independent run of recovered source, with its unchanged historical inputs."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'outputs/step1/historical_source_71cc107'
RUN=ROOT/'outputs/step1/blocker_evidence_20261012/historical_fresh_refit'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if RUN.exists():raise RuntimeError('Preserve prior attempt; use a new run directory')
RUN.mkdir(parents=True);WORK=RUN/'workspace'
shutil.copytree(SOURCE,WORK)
for p in WORK.rglob('*'):
 if p.is_file():p.chmod(0o644)
records=[dict(path=str(p.relative_to(SOURCE)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(SOURCE.rglob('*')) if p.is_file()]
env=os.environ.copy();env.update(MPLBACKEND='Agg',MPLCONFIGDIR=str(RUN/'mpl'),PYTHONUNBUFFERED='1',PYTHONPATH=str(WORK))
commands=[[sys.executable,'-u','-m','backtest._main','--phase',phase,'--view-mode','ranking_absolute','--ml-training-mode','walk_forward','--no-plot'] for phase in ['train','test']]
manifest=dict(run_id='historical-fresh-refit-20261012',status='running',started_at_utc=datetime.now(timezone.utc).isoformat(),source_commit='71cc107b807b6437ddd38430f30a0381333befa2',source_files=records,commands=commands,cwd=str(WORK),interpreter=sys.executable,original_environment_known=False,model_cache_files=[str(p.relative_to(WORK)) for p in WORK.rglob('*.pkl')],seeds=[42,43,44,45,46],purpose='Attempt full independent decision regeneration, not target-weight replay; historical protocol unchanged; currently installed research environment',results=[])
assert not manifest['model_cache_files']
(RUN/'requirements_frozen.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True))
(RUN/'manifest.json').write_text(json.dumps(manifest,indent=2));start=time.time()
for phase,cmd in zip(['train','test'],commands):
 with (RUN/f'{phase}_stdout.log').open('w') as stdout,(RUN/f'{phase}_stderr.log').open('w') as stderr:
  proc=subprocess.run(cmd,cwd=WORK,env=env,stdout=stdout,stderr=stderr)
 manifest['results'].append(dict(phase=phase,exit_code=proc.returncode))
 (RUN/'manifest.json').write_text(json.dumps(manifest,indent=2))
 if proc.returncode:break
manifest.update(status='succeeded' if len(manifest['results'])==2 and all(x['exit_code']==0 for x in manifest['results']) else 'failed',completed_at_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.time()-start)
assert all(sha(SOURCE/r['path'])==r['sha256'] for r in records)
manifest['source_snapshot_preserved']=True
manifest['generated_logs']=[str(p.relative_to(RUN)) for p in WORK.glob('logs/*.json')]
(RUN/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({k:manifest[k] for k in ['status','elapsed_seconds','results','generated_logs']}))
