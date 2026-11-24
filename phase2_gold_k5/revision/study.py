"""Repeat the registered matched GOLD–K5 study on a separate SJC archive."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback

from phase2_gold_k5.run import digest, frozen_files, sources, write

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = STUDY.parent
ORIGINAL = STUDY / "runs/20261124T083539735869Z"


def now():
    return datetime.now(timezone.utc).isoformat()


def confirm_old():
    old = json.loads((ORIGINAL / "manifest.json").read_text())
    for paths, base in [(old["csv_sha256"], ORIGINAL), (old["inputs"], ROOT), (old["source"], ROOT)]:
        for name, checksum in paths.items():
            if digest(base / name) != checksum:
                raise ValueError(f"Reference changed: {name}")


def phase1_comparison(out):
    import numpy as np
    import pandas as pd
    from experiments_core.src.core import return_stats, simulate
    phase1 = ROOT / "extensions_C_v1/inputs"
    old_metrics = pd.read_csv(phase1 / "baseline_metrics.csv").query("phase == 'OOS'").set_index("experiment_id")
    rows = []
    for vintage, directory in [("frozen", phase1), ("revised", out / "inputs")]:
        prices = pd.read_csv(directory / "prices_valuation.csv", parse_dates=["date"], index_col="date")
        for arm in ("B1_BLnoML", "B2_BLML"):
            weights = pd.read_csv(directory / f"{arm}_weights.csv", parse_dates=["decision_date"])
            targets = weights.pivot(index="decision_date",columns="asset",values="target_weight")[prices.columns]
            sim = simulate(prices, {date: row.to_numpy() for date,row in targets.iterrows()})
            window = sim["nav"].loc["2023-09-29":].pct_change().dropna()
            assert len(window) == 641
            stats = return_stats(window)
            if vintage == "frozen":
                for metric, value in stats.items():
                    np.testing.assert_allclose(value,old_metrics.at[arm,metric],atol=1e-9,rtol=0)
            rows.append({"vintage":vintage, "arm":arm, **stats})
    pd.DataFrame(rows).to_csv(out / "phase1_gross.csv",index=False)


def stage(name, out, feed):
    from phase2_gold_k5 import forecast, portfolio
    from phase2_gold_k5.score import score
    from phase2_gold_k5.sensitivity import sensitivity
    from .rebuild import prepare

    # Each stage runs in an isolated interpreter with read-only historical helpers.
    forecast.FROZEN = portfolio.BASE = out
    portfolio.INPUT = out / "inputs"
    archive = HERE / feed / "archive.csv"
    if name == "prepare":
        prepare(out, archive)
    elif name == "forecast":
        forecast.forecast(out)
    elif name == "primary":
        portfolio.portfolios(out)
        score(out)
    elif name == "sensitivity":
        if feed == "alternate":
            from .alternate import alternate_sensitivity
            alternate_sensitivity(out)
        else:
            sensitivity(out)
    elif name == "phase1":
        phase1_comparison(out)
    else:
        raise ValueError(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat",type=Path)
    parser.add_argument("--feed",choices=["snapshot","alternate"], default="snapshot")
    parser.add_argument("--stage",choices=["prepare","forecast","primary","sensitivity","phase1"])
    parser.add_argument("--out",type=Path)
    args = parser.parse_args()
    if args.stage:
        stage(args.stage,args.out.resolve(),args.feed)
        return
    confirm_old()
    snapshot = HERE / args.feed
    if not (snapshot / "archive.csv").is_file():
        raise FileNotFoundError("Recovery snapshot is required")
    revision_sources = [HERE / name for name in ("study.py", "rebuild.py", "test_rebuild.py", "scope.md", "recover.py")]
    if args.feed == "alternate":
        revision_sources += [HERE / "alternate.py", HERE / "verification" / "compare.py", HERE / "verification" / "capture.py"]
        revision_sources += sorted(HERE.glob("compose*.py"))
    paths = list(frozen_files()) + list(sources()) + revision_sources
    paths.extend(ROOT / name for name in ("gen_view/view_generators.py","gen_view/ranking/risk_management.py",
                                          "backtest/_black_litterman.py","backtest/_optimizer.py"))
    paths.extend((snapshot/"raw").glob("*"))
    paths.append(HERE / "snapshot" / "manifest.json")
    if args.feed == "alternate":
        paths.extend([snapshot / "provenance.csv", HERE / "verification" / "overrides.csv"])
        paths.extend(p for p in snapshot.glob("*.md"))
        paths.extend(p for p in snapshot.glob("*manifest*.json"))
    paths.append(snapshot/"archive.csv")
    if any(not path.is_file() for path in revision_sources):
        raise ValueError("Missing revision source")
    pinned = {str(p.relative_to(ROOT)):digest(p) for p in sorted(set(paths)) if p.is_file()}
    out = HERE / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True,exist_ok=False)
    parent = args.repeat.resolve() if args.repeat else None
    print(out,flush=True)
    started = time.monotonic()
    meta = dict(status="prepared",feed=args.feed,start_utc=now(),original_run=ORIGINAL.name,repeat_of=str(parent) if parent else None,
                command=sys.argv, executable=sys.executable,platform=platform.platform(), python=sys.version,
                git_head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                worktree_dirty=bool(subprocess.check_output(["git","status","--porcelain"],cwd=ROOT)),
                pinned_sha256=pinned,stage_seconds={})
    write(out/"manifest.json",meta)
    try:
        ref = None
        if parent:
            ref=json.loads((parent/"manifest.json").read_text())
            if ref["status"]!="complete" or ref["pinned_sha256"]!=pinned:
                raise ValueError("Primary inputs or source differ")
            for name,h in ref["outcome_sha256"].items():
                if digest(parent/name)!=h:
                    raise ValueError(f"Primary artifact changed: {name}")
        source = out/"source"
        source.mkdir()
        for f in revision_sources:
            shutil.copy2(f,source/f.name)
        with (out/"requirements.txt").open("w") as deps:
            subprocess.run([sys.executable,"-m","pip","freeze"],stdout=deps,check=True)
        for name in ["prepare","phase1","forecast","primary","sensitivity"]:
            t=time.monotonic()
            with (out/f"{name}.log").open("w") as log:
                subprocess.run([sys.executable,"-B","-m","phase2_gold_k5.revision.study","--stage",name,"--out",str(out),"--feed",args.feed],
                               env=os.environ | {"MPLCONFIGDIR":str(out/".mpl"),"OMP_NUM_THREADS":"1",
                                                 "OPENBLAS_NUM_THREADS":"1","VECLIB_MAXIMUM_THREADS":"1"},
                               cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            meta["stage_seconds"][name]=round(time.monotonic()-t,2)
            write(out/"manifest.json",meta)
            print(name,"complete",flush=True)
        files = [p for p in out.rglob("*.csv") if not p.is_symlink()]
        meta["outcome_sha256"] = {str(p.relative_to(out)):digest(p) for p in sorted(files)}
        if ref and ref["outcome_sha256"]!=meta["outcome_sha256"]:
            raise ValueError("Repeat mismatch: "+str([n for n,h in meta["outcome_sha256"].items() if ref["outcome_sha256"].get(n)!=h]))
        for name,h in pinned.items():
            if digest(ROOT/name)!=h:
                raise ValueError(f"Input modified during run: {name}")
        confirm_old()
        meta["status"]="complete"
    except BaseException:
        meta.update(status="failed",error=traceback.format_exc())
        raise
    finally:
        meta.update(end_utc=now(),seconds=round(time.monotonic()-started,2))
        write(out/"manifest.json",meta)


if __name__=="__main__":
    main()
