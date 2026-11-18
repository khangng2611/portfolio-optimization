"""Private local backups and token-free preservation receipts; never restores or resets."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "infra/local/.generated"
TABLES = {
    "auth_db": ["account"],
    "portfolio_db": [
        "app_user",
        "portfolio",
        "risk_assessment",
        "recommendation",
        "accepted_target",
        "job",
    ],
    "quant_db": ["numerical_run", "publication_job"],
    "market_db": [
        "asset",
        "price_revision",
        "market_snapshot",
        "ingestion_quality_report",
    ],
    "ml_db": ["ml_model", "ml_review", "ml_training_job"],
}


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def row_receipt(rows):
    columns = sorted(rows[0]) if rows else []
    values = sorted(rows, key=lambda x: x.get("id", x.get("job_id")))
    return {
        "columns": columns,
        "ids": [x.get("id", x.get("job_id")) for x in values],
        "sha256": digest(values),
    }


def verify_rows(saved, rows):
    wanted = set(saved["ids"])
    values = {row.get("id", row.get("job_id")): row for row in rows}
    if not wanted <= values.keys():
        raise ValueError("Preserved rows missing")
    projected = [
        {key: values[identity][key] for key in saved["columns"]}
        for identity in saved["ids"]
    ]
    if digest(projected) != saved["sha256"]:
        raise ValueError("Preserved rows changed")


def compose(*args):
    return [
        "docker",
        "compose",
        "--env-file",
        str(GENERATED / ".env"),
        "-f",
        str(ROOT / "infra/local/compose.yaml"),
        "-p",
        "portfolio-auth-demo",
        *args,
    ]


def run(args):
    result = subprocess.run(args, capture_output=True, timeout=180, cwd=ROOT)
    if result.returncode:
        raise RuntimeError("Local preservation command failed; details withheld")
    return result.stdout


def table_rows(database, table):
    if database not in TABLES or table not in TABLES[database]:
        raise ValueError("Unexpected preservation table")
    condition = (
        " WHERE status IN ('SUCCEEDED','FAILED')"
        if table in {"job", "publication_job", "ml_training_job"}
        else ""
    )
    key = "job_id" if table == "ingestion_quality_report" else "id"
    sql = f"SELECT row_to_json(t) FROM (SELECT * FROM {table}{condition} ORDER BY {key}) t"
    data = run(
        compose(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "local_admin",
            "-d",
            database,
            "-Atq",
            "-c",
            sql,
        )
    )
    return [json.loads(line, parse_float=str) for line in data.splitlines() if line]


def file_hashes():
    result = {}
    for name in ["accounts.json", ".env", "secrets.json", "auth-signing-key.b64"]:
        path = GENERATED / name
        if path.exists():
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ["bundles", "ml-models", "datasets"]:
        for path in (GENERATED / name).rglob("*"):
            if not path.is_file() or path.name in {"catalog.json", ".catalog.lock"}:
                continue
            if name == "datasets" and not re.fullmatch(
                r"[a-f0-9]{64}\.(json|csv)", path.name
            ):
                continue
            result[str(path.relative_to(GENERATED))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return result


def capture(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    value = {"schema_version": 1, "tables": {}, "files": file_hashes()}
    for db, tables in TABLES.items():
        value["tables"][db] = {
            name: row_receipt(table_rows(db, name)) for name in tables
        }
    value["volumes"] = sorted(
        run(
            [
                "docker",
                "volume",
                "ls",
                "--filter",
                "label=com.docker.compose.project=portfolio-auth-demo",
                "--format",
                "{{.Name}}",
            ]
        )
        .decode()
        .splitlines()
    )
    value["catalog_entries"] = json.loads(
        (GENERATED / "bundles/catalog.json").read_text()
    )["bundles"]
    target = directory / "preservation.json"
    if target.exists():
        raise ValueError("Preservation receipt exists; never overwrite")
    target.write_text(json.dumps(value, indent=2))
    os.chmod(target, 0o600)
    return target


def verify(path):
    value = json.loads(Path(path).read_text())
    for db, tables in value["tables"].items():
        for table, saved in tables.items():
            verify_rows(saved, table_rows(db, table))
    for name, checksum in value["files"].items():
        path = GENERATED / name
        if (
            not path.exists()
            or hashlib.sha256(path.read_bytes()).hexdigest() != checksum
        ):
            raise ValueError("Preserved artifact missing or changed: " + name)
    volumes = sorted(
        run(
            [
                "docker",
                "volume",
                "ls",
                "--filter",
                "label=com.docker.compose.project=portfolio-auth-demo",
                "--format",
                "{{.Name}}",
            ]
        )
        .decode()
        .splitlines()
    )
    if volumes != value["volumes"]:
        raise ValueError("Preserved volumes changed")
    entries = json.loads((GENERATED / "bundles/catalog.json").read_text())["bundles"]
    if any(entry not in entries for entry in value["catalog_entries"]):
        raise ValueError("Preserved catalog history changed")


def backup(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    receipts = {}
    for db in [*TABLES, "chat_db"]:
        target = directory / (db + ".dump")
        if target.exists():
            raise ValueError("Backup exists; never overwrite")
        with target.open("xb") as stream:
            os.chmod(target, 0o600)
            result = subprocess.run(
                compose(
                    "exec", "-T", "postgres", "pg_dump", "-U", "local_admin", "-Fc", db
                ),
                stdout=stream,
                stderr=subprocess.PIPE,
                timeout=180,
            )
        if result.returncode:
            raise RuntimeError("Backup failed; details withheld")
        # TOC validation uses the same PostgreSQL binary version without restoring anything.
        with target.open("rb") as stream:
            checked = subprocess.run(
                compose("exec", "-T", "postgres", "pg_restore", "-l"),
                stdin=stream,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
            )
        if checked.returncode:
            raise RuntimeError("Backup cannot be read")
        receipts[db] = {
            "bytes": target.stat().st_size,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
    archive = directory / "host-artifacts.tar.gz"
    if archive.exists():
        raise ValueError("Backup exists; never overwrite")
    with tarfile.open(archive, "w:gz") as target:
        os.chmod(archive, 0o600)
        for name in [
            "bundles",
            "ml-models",
            "datasets",
            "accounts.json",
            ".env",
            "secrets.json",
            "auth-signing-key.b64",
        ]:
            if (GENERATED / name).exists():
                target.add(GENERATED / name, arcname=name)
    with tarfile.open(archive, "r:gz") as target:
        target.getmembers()
    receipts["host-artifacts"] = {
        "bytes": archive.stat().st_size,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    (directory / "backup-checksums.json").write_text(json.dumps(receipts, indent=2))
    os.chmod(directory / "backup-checksums.json", 0o600)
    return receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "verify", "backup"])
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.action == "capture":
        print("Preservation receipt:", capture(args.path))
    elif args.action == "verify":
        verify(args.path)
        print(
            "Existing rows, artifacts, accounts, volumes and catalog history preserved: PASS"
        )
    else:
        print("Private backups validated:", ", ".join(backup(args.path)))


if __name__ == "__main__":
    main()
