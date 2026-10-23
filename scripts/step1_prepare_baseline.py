"""Prepare an isolated integrity-correction copy of frozen current research."""
from pathlib import Path
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "trusted_baseline"
FROZEN = ROOT / "legacy_version"

if __name__ == "__main__":
    if DEST.exists():
        raise RuntimeError("Baseline already exists; never overwrite")
    DEST.mkdir()
    for name in ["backtest", "gen_view", "utils", "crawl"]:
        shutil.copytree(FROZEN / "code" / name, DEST / name)
    for name in ["config.py", "requirements.txt"]:
        shutil.copy2(FROZEN / "code" / name, DEST / name)
    shutil.copy2(FROZEN / "configs/assets_1.json", DEST / "assets_1.json")
    shutil.copytree(FROZEN / "datasets/datasets", DEST / "datasets")
    for p in DEST.rglob("*"):
        if p.is_file():
            p.chmod(0o644)
    (DEST / "STATUS.json").write_text(json.dumps({"status": "candidate_not_certified",
        "evaluation_end": "2026-07-01", "source": "legacy_version snapshot of current dirty source",
        "reason": "Integrity repairs, canonical VFF retrieval and full verification pending"}, indent=2))
    print(str(DEST))
