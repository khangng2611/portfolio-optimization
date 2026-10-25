"""Read-only adapter to the active, relocated Step 1 snapshot."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
PKG=ROOT/'experiments_core'
READY=ROOT/'outputs/step1/readiness_20261012'
BASE=READY/'candidate_workspace'
BASELINE_ID='availability-observed-contract-20261012T233110'
BASE_RUN=READY/'runs'/BASELINE_ID
SEEDS=[7,11,19,23,31,43,59,71,83,97]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def encode(value):
    if hasattr(value,'isoformat'):return value.isoformat()
    if hasattr(value,'tolist'):return value.tolist()
    if hasattr(value,'item'):return value.item()
    return str(value)


def write_json(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,default=encode)+'\n')


def relocated(old):
    old=str(old)
    marker='portfolio-optimization/'
    if marker in old:return ROOT/old.split(marker,1)[1]
    raise ValueError(f'Unresolved historical path: {old}')


def activate():
    os.environ.setdefault('MPLCONFIGDIR',str(PKG/'runs/.mpl-cache'))
    sys.path.insert(0,str(BASE))
    import config
    actual=json.loads((BASE_RUN/'run_config.json').read_text())
    for key,value in actual.items():setattr(config,key,value)
    return actual
