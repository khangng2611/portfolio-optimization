"""Restore the local demo backup into isolated temporary PostgreSQL and API containers."""

import argparse
from datetime import datetime, timezone
from hashlib import file_digest, sha256
import json
import os
import secrets
import shutil
import subprocess
import tarfile
import time
from uuid import UUID, uuid4

from verify_user_selection_preservation import GENERATED, ROOT, backup

CLUSTERS = {
    "postgres": (
        "local_admin",
        ["auth_db", "portfolio_db", "quant_db", "market_db", "ml_db", "chat_db"],
    ),
    "knowledge-postgres": ("knowledge_admin", ["knowledge_db"]),
}


def docker(*args, body=None):
    result = subprocess.run(["docker", *args], input=body, capture_output=True, timeout=240)
    if result.returncode:
        # SQL dumps, runtime configuration and auth responses may contain secrets.
        raise RuntimeError(f"Docker {args[0]} failed ({result.returncode}); command data withheld")
    return result.stdout


def source(service):
    return f"portfolio-auth-demo-{service}-1"


def sql(container, db, query, admin):
    return (
        docker(
            "exec",
            container,
            "psql",
            "-XAtq",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            admin,
            "-d",
            db,
            "-c",
            query,
        )
        .decode()
        .strip()
    )


def wait_for(container, *command):
    for _ in range(60):
        try:
            docker("exec", container, *command)
            return
        except RuntimeError:
            time.sleep(1)
    raise RuntimeError("Restore container not ready: " + container)


def file_hash(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def evidence(container, recommendation, admin):
    row = sql(
        container,
        "portfolio_db",
        f"""
        SELECT json_build_object('proposal', r.id, 'strategy', r.result->>'strategy',
          'run_id', r.run_id, 'input_hash', r.result->>'input_hash',
          'bundle_hash', r.result->>'bundle_hash', 'subject', u.subject,
          'result_hash', encode(sha256(convert_to(r.result::jsonb::text,'UTF8')),'hex'),
          'target', t.id, 'target_portfolio', t.portfolio_id, 'target_allocation', t.allocation)
        FROM recommendation r JOIN app_user u ON u.id=r.owner_user_id
        JOIN accepted_target t ON t.owner_user_id=u.id
        WHERE r.id='{recommendation}' ORDER BY t.accepted_at DESC,t.id LIMIT 1""",
        admin,
    )
    if not row:
        raise ValueError("Expected a saved proposal and an accepted target belonging to its owner")
    return json.loads(row)


# Runs only inside the private recovery network. Return the checked identities, never tokens.
CHECK_API = """
import json, os, sys, httpx
credential, expected = json.load(sys.stdin)
with httpx.Client(timeout=10,trust_env=False) as client:
    auth = client.post('http://auth-api:8000/internal/v1/login',json=credential,
                       headers={'Authorization':'Bearer '+os.environ['AUTH_WEB_SECRET']})
    auth.raise_for_status()
    result=auth.json()
    assert result['user']['sub']==expected['subject']
    client.headers['Authorization']='Bearer '+result['accessToken']
    get=lambda path: client.get('http://portfolio-api:8000/api/v1/'+path).raise_for_status().json()
    proposal=get('recommendations/'+expected['proposal'])
    assert proposal['id']==expected['proposal'] and proposal['strategy']=='HYBRID'
    assert all(proposal[k]==expected[k] for k in ('input_hash','bundle_hash','run_id'))
    targets=get('portfolios/'+expected['target_portfolio']+'/targets')
    assert any(t['id']==expected['target'] and t['allocation']==expected['target_allocation'] for t in targets)
"""


def drill(directory, proposal):
    if not __debug__:
        raise RuntimeError("Run the drill with Python assertions enabled")
    os.umask(0o077)
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    before = evidence(source("postgres"), proposal, "local_admin")
    if before["strategy"] != "HYBRID":
        raise ValueError("Use a saved HYBRID recommendation")
    checks = backup(directory)
    # The preservation helper covers the original six databases. Also retain Knowledge and DB roles.
    for service, (admin, _) in CLUSTERS.items():
        path = directory / f"{service}-roles.sql"
        path.write_bytes(docker("exec", source(service), "pg_dumpall", "-U", admin, "--roles-only"))
        checks[path.name] = {"sha256": file_hash(path)}
    path = directory / "knowledge_db.dump"
    path.write_bytes(
        docker(
            "exec",
            source("knowledge-postgres"),
            "pg_dump",
            "-U",
            "knowledge_admin",
            "-Fc",
            "knowledge_db",
        )
    )
    checks["knowledge_db"] = {"sha256": file_hash(path)}
    (directory / "restore-checksums.json").write_text(json.dumps(checks, indent=2))

    restore = directory / "restored"
    restore.mkdir()
    for name, entry in checks.items():
        filename = (
            "host-artifacts.tar.gz"
            if name == "host-artifacts"
            else (name if name.endswith(".sql") else name + ".dump")
        )
        if file_hash(directory / filename) != entry["sha256"]:
            raise ValueError(f"Backup checksum mismatch: {name}")
    with tarfile.open(directory / "host-artifacts.tar.gz") as archive:
        archive.extractall(restore, filter="data")
    files = sorted(p for p in restore.rglob("*") if p.is_file())
    manifest = {str(p.relative_to(restore)): file_hash(p) for p in files}
    for name, digest in manifest.items():
        if file_hash(GENERATED / name) != digest:
            raise ValueError("Restored artifact differs from currently captured source: " + name)
    artifact_hash = sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    # Resolve only the two application environments from the backed-up configuration.
    compose = json.loads(
        docker(
            "compose",
            "--env-file",
            str(restore / ".env"),
            "-f",
            str(ROOT / "infra/local/compose.yaml"),
            "config",
            "--format",
            "json",
        )
    )
    prefix = "db08-" + uuid4().hex[:12]
    containers = []
    images = {}
    revisions = {}
    docker("network", "create", "--internal", prefix)
    try:

        def launch(service, env):
            images[service] = (
                docker("inspect", "-f", "{{.Image}}", source(service)).decode().strip()
            )
            envfile = restore / (service + ".env")
            if any("\n" in str(value) for value in env.values()):
                raise ValueError("Unexpected multiline container environment")
            envfile.write_text("".join(f"{k}={v}\n" for k, v in env.items()))
            name = prefix + "-" + service
            cid = (
                docker(
                    "run",
                    "-d",
                    "--network",
                    prefix,
                    "--network-alias",
                    service,
                    "--name",
                    name,
                    "--env-file",
                    str(envfile),
                    images[service],
                )
                .decode()
                .strip()
            )
            containers.append(cid)
            return name

        for service, (admin, databases) in CLUSTERS.items():
            name = launch(
                service, {"POSTGRES_USER": admin, "POSTGRES_PASSWORD": secrets.token_hex(32)}
            )
            wait_for(name, "pg_isready", "-h", "127.0.0.1", "-U", admin, "-d", "postgres")
            roles = (directory / f"{service}-roles.sql").read_bytes()
            bootstrap_role = f"CREATE ROLE {admin};".encode()
            if roles.splitlines().count(bootstrap_role) != 1:
                raise ValueError("Missing or duplicate bootstrap role in source dump")
            # initdb already created the grantor. Restore its password, attributes and memberships.
            docker(
                "exec",
                "-i",
                name,
                "psql",
                "-Xq",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                admin,
                "-d",
                "postgres",
                body=roles.replace(bootstrap_role + b"\n", b"\n", 1),
            )
            for db in databases:
                docker(
                    "exec",
                    "-i",
                    name,
                    "pg_restore",
                    "--exit-on-error",
                    "--create",
                    "-U",
                    admin,
                    "-d",
                    "postgres",
                    body=(directory / (db + ".dump")).read_bytes(),
                )
                revisions[db] = sql(
                    name, db, "select version_num from alembic_version order by 1", admin
                )
                assert revisions[db] and revisions[db] == sql(
                    source(service), db, "select version_num from alembic_version order by 1", admin
                )
        auth = launch("auth-api", compose["services"]["auth-api"]["environment"])
        portfolio = launch("portfolio-api", compose["services"]["portfolio-api"]["environment"])
        postgres = prefix + "-postgres"
        username = sql(
            postgres,
            "auth_db",
            f"select username from account where id='{UUID(before['subject'])}'",
            "local_admin",
        )
        fixture = next(
            u
            for u in json.loads((restore / "accounts.json").read_text())["users"]
            if u["username"] == username
        )
        body = json.dumps([{k: fixture[k] for k in ("username", "password")}, before]).encode()
        for stage in ("restored", "restarted"):
            if stage == "restarted":
                docker("restart", *containers)
            for service, (admin, _) in CLUSTERS.items():
                wait_for(
                    prefix + "-" + service,
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    admin,
                    "-d",
                    "postgres",
                )
            for container in (auth, portfolio):
                wait_for(
                    container,
                    "python",
                    "-c",
                    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=2)",
                )
            assert evidence(postgres, proposal, "local_admin") == before
            docker("exec", "-i", auth, "python", "-c", CHECK_API, body=body)
            assert all(file_hash(restore / n) == h for n, h in manifest.items())
    finally:
        for cid in reversed(containers):
            docker("rm", "-fv", cid)
        docker("network", "rm", prefix)
    shutil.rmtree(restore)
    return {
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "databases": revisions,
        "images": images,
        "login_and_owner_reads": ["restored", "restarted"],
        "proposal": str(proposal),
        "result_sha256": before["result_hash"],
        "input_hash": before["input_hash"],
        "target": before["target"],
        "target_sha256": sha256(
            json.dumps(before["target_allocation"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "artifact_file_count": len(files),
        "artifacts_manifest_sha256": artifact_hash,
        "archive_checksums": checks["host-artifacts"],
        "isolation": "private internal network, no published ports, fresh anonymous DB volumes",
        "scope": "Logical backups are per database. Target is a separate saved target of the same owner.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal", type=UUID)
    args = parser.parse_args()
    directory = ROOT / "output/db08-drill" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = drill(directory, args.proposal)
    (directory / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(directory / "receipt.json")
