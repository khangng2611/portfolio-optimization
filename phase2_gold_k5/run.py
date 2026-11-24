"""Run from the project root with venv/bin/python -B -m phase2_gold_k5.run."""
import argparse
from datetime import datetime, timezone
from hashlib import file_digest
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
READY = ROOT / "outputs/step1/readiness_20261012"


def digest(file):
    with file.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def inventory(files):
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(set(files)) if p.is_file()}


def frozen_files():
    paths = [*sorted((ROOT / "extensions_C_v1/inputs").glob("*")),
             ROOT / "extensions_C_v1/selected_k5_events.csv", ROOT / "extensions_C_v1/rebalance_calendar.csv",
             ROOT / "datasets/gold/gold_full.csv", ROOT / "outputs/step1/ml_prediction_audit.csv"]
    paths.extend((READY / "gold_archive_raw").glob("*.html"))
    paths.extend(READY.glob("gold_archive*.csv"))
    baseline = READY / "runs/availability-observed-contract-20261012T233110"
    paths.extend(baseline / name for name in ("run_config.json", "views_history.json", "artifacts/ml_prediction_audit.csv"))
    paths.extend([ROOT / "extensions_C_v1/baseline_manifest.json",ROOT / "extensions_C_v1/publication_manifest.json",
                  READY / "gold_archive_manifest.json", baseline / "ml_prediction_audit.json", ROOT / "crawl/gold.py"])
    paths.extend(baseline / "artifacts" / name for name in ("ml_training_audit.csv","selection_history.csv"))
    return paths


def sources():
    files = [ROOT / "config.py"] + [HERE / name for name in ("run.py","audit.py","forecast.py","portfolio.py","score.py","sensitivity.py","test_audit.py","test_forecast.py","test_portfolio.py")] + list((ROOT / "experiments_core/src").glob("*.py"))
    for name in ["trusted_baseline", "outputs/step1/readiness_20261012/candidate_workspace"]:
        directory = ROOT / name
        files.extend(directory.glob("config.py"))
        files.extend((directory / "backtest").glob("*.py"))
    return files + [HERE / name for name in ("protocol.json", "execution-policy.md", "registration.json")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=Path, help="completed primary directory to verify before and after independent rerun")
    args = parser.parse_args()
    os.chdir(ROOT)
    for file, wanted in json.loads((HERE / "registration.json").read_text())["sha256"].items():
        if digest(HERE / file) != wanted:
            raise ValueError(f"Registration mismatch: {file}")
    out = HERE / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True, exist_ok=False)
    meta = dict(status="prepared", start_utc=timestamp(), id=out.name, repo=str(ROOT), source=inventory(sources()),
                inputs=inventory(frozen_files()), python=sys.version, interpreter=sys.executable,
                platform=platform.platform(), command=sys.argv,
                git_head=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
                git_branch=subprocess.check_output(["git","branch","--show-current"],text=True).strip(),
                git_dirty=bool(subprocess.check_output(["git","status","--porcelain"])),
                repeat_of=str(args.repeat) if args.repeat else None, stages={})
    write(out / "manifest.json", meta)
    print(out, flush=True)
    started = time.monotonic()
    try:
        parent = None
        if args.repeat:
            parent = json.loads((args.repeat / "manifest.json").read_text())
            if any(digest(args.repeat / name) != value for name,value in parent["csv_sha256"].items()):
                raise ValueError("Primary evidence changed after completion")
            if parent["status"] != "complete" or any(parent[key] != meta[key] for key in ("source","inputs")):
                raise ValueError("Repeat requires identical source and inputs")
        with (out / "requirements.txt").open("w") as deps:
            subprocess.run([sys.executable,"-m","pip","freeze"],stdout=deps,check=True)
        # Preserve editable Phase 2 implementation alongside the fingerprints of inherited code.
        snap = out / "source"
        snap.mkdir()
        for path in sources():
            if path.parent == HERE:
                shutil.copy2(path, snap / path.name)
        for module, fn in [("audit","audit"),("forecast","forecast"),("portfolio","portfolios"),("score","score"),("sensitivity","sensitivity")]:
            stage_start = time.monotonic()
            with (out / f"{module}.log").open("w") as log:
                subprocess.run([sys.executable,"-B","-c",
                                f"from phase2_gold_k5.{module} import {fn}; from pathlib import Path; import sys; {fn}(Path(sys.argv[1]))", str(out)],
                               cwd=ROOT, env=os.environ | {"MPLCONFIGDIR":str(out / ".mpl"),"OMP_NUM_THREADS":"1",
                                                          "OPENBLAS_NUM_THREADS":"1","VECLIB_MAXIMUM_THREADS":"1"},
                               stdout=log,stderr=subprocess.STDOUT,check=True)
            meta["stages"][module]=round(time.monotonic()-stage_start,2)
            write(out / "manifest.json", meta)
            print(module,"complete", flush=True)
        files = sorted(out.glob("*.csv")) + sorted((out / "dated_quotes").glob("*.csv"))
        meta["csv_sha256"] = {str(p.relative_to(out)):digest(p) for p in files}
        meta["unchanged_inputs_and_sources"] = meta["inputs"] == inventory(frozen_files()) and meta["source"] == inventory(sources())
        if not meta["unchanged_inputs_and_sources"]:
            raise ValueError("Inputs or sources changed during execution")
        if parent:
            # Runtime timestamps and absolute run paths may differ in audit metadata; numeric CSVs must match.
            if parent["csv_sha256"] != meta["csv_sha256"]:
                raise ValueError("Independent replay CSV mismatch: "+str([p for p,h in meta["csv_sha256"].items() if parent["csv_sha256"].get(p)!=h]))
        meta["status"]="complete"
    except BaseException:
        meta.update(status="failed",error=traceback.format_exc())
        raise
    finally:
        meta.update(end_utc=timestamp(),seconds=round(time.monotonic()-started,2))
        write(out / "manifest.json", meta)


if __name__ == "__main__":
    main()
