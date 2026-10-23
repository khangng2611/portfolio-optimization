"""Recover a read-only historical scientific source/data snapshot from Git."""
from pathlib import Path
import hashlib
import io
import json
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
REF = "71cc107"
DEST = ROOT / "outputs/step1/historical_source_71cc107"

if __name__ == "__main__":
    if DEST.exists():
        raise RuntimeError("Historical snapshot already exists; never overwrite")
    blob = subprocess.check_output(["git", "archive", REF], cwd=ROOT)
    DEST.mkdir(parents=True)
    files = []
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as archive:
        for member in archive:
            if not member.isfile():
                continue
            rel = Path(member.name)
            if rel.is_absolute() or ".." in rel.parts or rel.name.startswith(".env"):
                raise RuntimeError(f"Unsafe archive member: {rel}")
            content = archive.extractfile(member).read()
            path = DEST / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(0o444)
            files.append({"path": str(rel), "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
    manifest = {"ref": REF, "commit": subprocess.check_output(["git", "rev-parse", REF], cwd=ROOT, text=True).strip(),
                "archive_sha256": hashlib.sha256(blob).hexdigest(), "files": files,
                "role": "Recovered historical candidate source/data; identity checked against logs, not assumed"}
    (DEST / "history_snapshot_manifest.json").write_text(json.dumps(manifest, indent=2))
    (DEST / "history_snapshot_manifest.json").chmod(0o444)
    print(json.dumps({"directory": str(DEST), "files": len(files)}))
