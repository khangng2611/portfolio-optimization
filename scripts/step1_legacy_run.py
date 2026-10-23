"""Run unchanged frozen paper code in a disposable, provenance-recorded copy."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["train", "test", "both"], default="train")
    args = parser.parse_args()
    run_id = datetime.now(ZONE).strftime("legacy-current-%Y%m%dT%H%M%S") + "-" + args.phase
    run = ROOT / "outputs/step1/legacy_results" / run_id
    run.mkdir(parents=True)
    workspace = run / "workspace"
    frozen = ROOT / "legacy_version"
    shutil.copytree(frozen / "code", workspace)
    shutil.copytree(frozen / "datasets/datasets", workspace / "datasets")
    for p in (frozen / "configs").glob("*.json"):
        shutil.copy2(p, workspace / p.name)
    (workspace / "csonet-paper").mkdir(exist_ok=True)
    shutil.copy2(frozen / "outputs/csonet-paper/paper_backtest.py", workspace / "csonet-paper/paper_backtest.py")
    artifacts = run / "artifacts"
    artifacts.mkdir()
    cmd = [sys.executable, "-u", str(workspace / "csonet-paper/paper_backtest.py"),
           "--phase", args.phase, "--view-mode", "ranking_absolute", "--output-dir", str(artifacts)]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace)
    env["MPLCONFIGDIR"] = str(run / "matplotlib-cache")
    env["PYTHONUNBUFFERED"] = "1"
    snapshot = json.loads((frozen / "snapshot_manifest.json").read_text())
    manifest = {"schema_version": 1, "run_id": run_id, "status": "running",
        "hypothesis": "Reproduce unchanged current legacy IS/OOS paper results", "parent_run_id": None,
        "started_at": datetime.now(ZONE).isoformat(), "source": {"commit": snapshot["commit"].strip(),
            "branch": snapshot["branch"].strip(), "dirty_state": snapshot["dirty_state"],
            "snapshot_manifest": str(frozen / "snapshot_manifest.json"),
            "snapshot_manifest_sha256": hashlib.sha256((frozen / "snapshot_manifest.json").read_bytes()).hexdigest()},
        "inputs": [f for f in snapshot["files"] if f["source"].startswith("datasets/") or f["source"] in ["assets_1.json", "config.py"]],
        "policy": {"phase": args.phase, "view_mode": "ranking_absolute", "training_mode": "fresh walk_forward",
            "seeds": [42,43,44,45,46], "retrain": 10, "reselect": 20, "rebalance": 5,
            "costs": 0, "configuration": "unchanged frozen config.py", "cache_reuse": False},
        "environment": snapshot["environment"], "execution": {"argv": cmd, "cwd": str(workspace),
            "PYTHONPATH": str(workspace), "stdout": str(run / "stdout.log"), "stderr": str(run / "stderr.log")},
        "limitations": ["Current data/config differs from undocumented manuscript run; compare after execution.",
                         "Raw paper runner does not export per-date fitted models or NAV CSV."]}
    path = run / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    print(str(path), flush=True)
    started = time.monotonic()
    with (run / "stdout.log").open("w") as stdout, (run / "stderr.log").open("w") as stderr:
        process = subprocess.Popen(cmd, cwd=workspace, env=env, stdout=stdout, stderr=stderr)
        manifest["execution"]["pid"] = process.pid
        path.write_text(json.dumps(manifest, indent=2))
        code = process.wait()
    manifest["status"] = "succeeded" if code == 0 else "failed"
    manifest["finished_at"] = datetime.now(ZONE).isoformat()
    manifest["execution"].update(exit_code=code, elapsed_seconds=time.monotonic()-started)
    manifest["results"] = [{"path": str(p.relative_to(run)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                           for p in artifacts.glob("*") if p.is_file()]
    path.write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"run_id": run_id, "status": manifest["status"], "exit_code": code}), flush=True)
    sys.exit(code)


if __name__ == "__main__":
    main()
