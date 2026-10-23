"""Freeze the pre-audit research tree, without changing original files."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/step1"
DEST = ROOT / "legacy_version"
SKIP_DIRS = {".git", "node_modules", ".next", "__pycache__", ".pytest_cache",
             ".ruff_cache", ".venv-software", "venv", "legacy_version", "trusted_baseline"}
SECRET_NAMES = {".env", ".env.local", ".env.production", "credentials", ".DS_Store"}


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def freeze():
    OUT.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        raise RuntimeError("legacy_version already exists: verify its manifest, never overwrite")
    manifest = {"schema_version": 1, "created_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
                "repository": str(ROOT), "files": [], "excluded": [],
                "immutability": "read-only files plus SHA256 verification; not a WORM storage device"}
    for arg, key in [(["rev-parse", "HEAD"], "commit"), (["branch", "--show-current"], "branch"),
                     (["status", "--porcelain"], "dirty_state")]:
        manifest[key] = subprocess.check_output(["git", *arg], cwd=ROOT, text=True)
    sections = {
        "code": ["backtest", "gen_view", "utils", "crawl", "scripts", "packages", "services", "apps", "tests", "infra", "docs", "config.py", "README.md", "QUICKSTART.md", "requirements.txt"],
        "configs": ["assets_0.json", "assets_1.json"],
        "outputs": ["logs", "reports", "csonet-paper"],
        "datasets": ["datasets"],
    }
    for section, entries in sections.items():
        for name in entries:
            source = ROOT / name
            candidates = [source] if source.is_file() else (
                Path(base) / filename
                for base, dirs, files in os.walk(source)
                if not (set(Path(base).relative_to(ROOT).parts) & SKIP_DIRS)
                for filename in files
            )
            for p in candidates:
                relative = p.relative_to(ROOT)
                if p.is_symlink() or p.name in SECRET_NAMES or p.suffix in {".pem", ".key"} or set(relative.parts) & SKIP_DIRS:
                    manifest["excluded"].append(str(relative))
                    continue
                target = DEST / section / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)
                target.chmod(0o444)
                manifest["files"].append({"source": str(relative), "snapshot": str(target.relative_to(DEST)),
                                          "bytes": p.stat().st_size, "sha256": digest(p)})
    spec = DEST / "instructions"
    spec.mkdir(parents=True)
    for name in ["guide_0.md", "project_0.md"]:
        p = Path("/Users/nguyenkhang/Downloads") / name
        target = spec / name
        shutil.copy2(p, target)
        target.chmod(0o444)
        manifest["files"].append({"source": str(p), "snapshot": str(target.relative_to(DEST)),
                                  "bytes": p.stat().st_size, "sha256": digest(p)})
    (OUT / "initial_tracked_diff.patch").write_bytes(subprocess.check_output(["git", "diff", "--binary"], cwd=ROOT))
    env = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
           "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}}
    (OUT / "environment.json").write_text(json.dumps(env, indent=2))
    (OUT / "requirements_frozen.txt").write_text("\n".join(f"{k}=={v}" for k, v in sorted(env["packages"].items())) + "\n")
    manifest["environment"] = env
    (DEST / "snapshot_manifest.json").write_text(json.dumps(manifest, indent=2))
    (DEST / "snapshot_manifest.json").chmod(0o444)
    (OUT / "freeze_summary.json").write_text(json.dumps({"files": len(manifest["files"]),
         "bytes": sum(f["bytes"] for f in manifest["files"]), "manifest_sha256": digest(DEST / "snapshot_manifest.json")}, indent=2))
    print(json.dumps({"snapshot": str(DEST), "files": len(manifest["files"]), "bytes": sum(f["bytes"] for f in manifest["files"])}))


if __name__ == "__main__":
    freeze()
