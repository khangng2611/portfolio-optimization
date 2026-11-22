"""Release transactions must restore data, not merely checkout old source."""

import importlib.util
from pathlib import Path
import pytest


def module():
    path = Path(__file__).resolve().parents[2] / "scripts/deploy_demo.py"
    assert path.is_file(), "One-command deploy is not implemented"
    spec = importlib.util.spec_from_file_location("deploy_demo", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_failure_restores_backup_and_never_commits(tmp_path):
    m = module()
    data = tmp_path / "database"
    data.write_text("before")
    events = []

    class Tx(m.Transaction):
        def enter_maintenance(self):
            events.append("maintenance")

        def backup(self):
            events.append("backup")
            (tmp_path / "backup").write_bytes(data.read_bytes())

        def activate(self):
            events.append("activate")
            data.write_text("migration and new writes")

        def verify(self):
            events.append("verify")
            raise RuntimeError("unhealthy")

        def publish(self):
            events.append("publish")

        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")
            data.write_bytes((tmp_path / "backup").read_bytes())

    tx = Tx.__new__(Tx)
    with pytest.raises(RuntimeError, match="unhealthy"):
        tx.execute()
    assert data.read_text() == "before"
    assert events == ["maintenance", "backup", "activate", "verify", "rollback"]


def test_backup_failure_does_not_activate_and_attempts_recovery():
    m = module()
    events = []

    class Tx(m.Transaction):
        def enter_maintenance(self):
            events.append("maintenance")

        def backup(self):
            raise RuntimeError("disk full")

        def activate(self):
            events.append("activate")

        def rollback(self):
            events.append("recover old stack")

    with pytest.raises(RuntimeError, match="disk full"):
        Tx.__new__(Tx).execute()
    assert events == ["maintenance", "recover old stack"]


def test_publish_failure_rolls_back_instead_of_committing():
    m = module()
    events = []

    class Tx(m.Transaction):
        def enter_maintenance(self):
            pass

        def backup(self):
            pass

        def activate(self):
            pass

        def verify(self):
            pass

        def publish(self):
            raise RuntimeError("external HTTPS failed")

        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    with pytest.raises(RuntimeError, match="external HTTPS"):
        Tx.__new__(Tx).execute()
    assert events == ["rollback"]


def test_corrupt_backup_is_rejected_before_any_restore(tmp_path):
    m = module()
    archive = tmp_path / "volume.tar.gz"
    archive.write_bytes(b"corrupt")
    with pytest.raises(RuntimeError, match="checksum"):
        m.verify_archive(archive, "0" * 64)


def test_release_input_cannot_be_a_shell_command_or_git_option():
    m = module()
    for value in ["--help", "v1; touch /tmp/oops", "../v1", "v1\nwhoami"]:
        with pytest.raises(ValueError):
            m.validate_release(value)
    assert m.validate_release("v0.1.0-demo.3") == "v0.1.0-demo.3"


def test_real_rollback_restores_cold_volume_config_and_commit(tmp_path, monkeypatch):
    import json
    import subprocess

    m = module()
    root, base, volume = tmp_path / "repo", tmp_path / "control", tmp_path / "volume"
    root.mkdir()
    base.mkdir()
    volume.mkdir()

    def git(*args):
        return subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                *args,
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    git("init")
    (root / ".gitignore").write_text("infra/\n")
    (root / "version").write_text("old")
    git("add", ".")
    git("commit", "-m", "old")
    old = git("rev-parse", "HEAD")
    (root / "version").write_text("new")
    git("add", ".")
    git("commit", "-m", "new")
    generated = root / "infra/local/.generated"
    generated.mkdir(parents=True)
    (generated / "secrets").write_text("old secret")
    (volume / "database").write_text("old database and queue state")
    txdir = base / "transactions" / "test"
    txdir.mkdir(parents=True)
    varchive = txdir / "volume.tar.gz"
    garchive = txdir / "generated.tar.gz"
    for src, archive in [(volume, varchive), (generated, garchive)]:
        subprocess.run(["tar", "-czf", str(archive), "-C", str(src), "."], check=True)
    (volume / "database").write_text("migrated state")
    (volume / "new-table").write_text("must disappear on rollback")
    (generated / "secrets").write_text("changed secret")
    images = txdir / "previous-images.json"
    images.write_text("{}")
    monkeypatch.setattr(m, "ROOT", root)
    monkeypatch.setattr(m, "BASE", base)
    calls = []
    original = m.run

    def run(command, **kwargs):
        command = [str(c) for c in command]
        calls.append(command)
        if command[0] in ("docker", "curl") or command[:2] == ["sudo", "tailscale"]:
            return ""
        if command[0] == "sudo":
            command = command[1:]
        command = [
            c for c in command if c not in ("--xattrs", "--acls", "--numeric-owner")
        ]
        return original(command, **kwargs)

    monkeypatch.setattr(m, "run", run)
    tx = m.Transaction.__new__(m.Transaction)
    tx.id = "test"
    tx.path = txdir
    tx.origin = m.ORIGIN
    tx.maintenance = None
    tx.state = {
        "schema": 1,
        "id": "test",
        "path": str(txdir),
        "origin": m.ORIGIN,
        "backup_complete": True,
        "archives": [
            {
                "name": "data",
                "mount": str(volume),
                "file": str(varchive),
                "sha256": m.digest(varchive),
            }
        ],
        "generated": {"file": str(garchive), "sha256": m.digest(garchive)},
        "previous_commit": old,
        "previous_manifest": None,
        "previous_python": "old/python",
        "old_images": str(images),
    }
    monkeypatch.setattr(tx, "start_maintenance", lambda: None)
    monkeypatch.setattr(tx, "finish_maintenance", lambda: None)
    monkeypatch.setattr(tx, "volume", lambda _: {"name": "data", "mount": str(volume)})
    monkeypatch.setattr(tx, "dc", lambda *a, **k: "")
    import os

    mask = os.umask(0o077)
    try:
        tx.rollback()
    finally:
        os.umask(mask)
    assert (generated / "secrets").stat().st_mode & 0o777 == 0o644
    assert (volume / "database").read_text() == "old database and queue state"
    assert not (volume / "new-table").exists()
    assert (generated / "secrets").read_text() == "old secret"
    assert git("rev-parse", "HEAD") == old
    assert (root / "version").stat().st_mode & 0o777 == 0o644
    assert json.loads((base / "current.json").read_text())["images"] == str(images)
    assert not (base / "pending.json").exists()
    assert json.loads((txdir / "journal.json").read_text())["phase"] == "rolled-back"


def test_missing_image_metadata_is_protected_by_container_snapshot(
    tmp_path, monkeypatch
):
    import json

    m = module()
    calls = []

    def run(command, **kwargs):
        command = [str(c) for c in command]
        calls.append(command)
        if command[:3] == ["docker", "ps", "-aq"]:
            return "old-container"
        if command[:2] == ["docker", "inspect"]:
            return json.dumps(
                {
                    "service": "knowledge-postgres",
                    "image": "sha256:missing",
                    "mounts": [],
                }
            )
        if command[:3] == ["docker", "image", "tag"]:
            raise RuntimeError("No such image")
        if command[:2] == ["docker", "commit"]:
            return "sha256:runtime-snapshot"
        if command[:3] == ["docker", "volume", "ls"]:
            return ""
        raise AssertionError(command)

    monkeypatch.setattr(m, "run", run)
    tx = m.Transaction.__new__(m.Transaction)
    tx.id = "test"
    tx.path = tmp_path
    tx.state = {}
    tx.capture_previous_images()
    assert any(c[:3] == ["docker", "commit", "--pause=true"] for c in calls)
    assert json.loads((tmp_path / "previous-images.json").read_text())["services"][
        "knowledge-postgres"
    ]["image"].startswith("portfolio-rollback/")


def test_successful_transaction_can_commit_with_a_source_commit_hash(
    tmp_path, monkeypatch
):
    m = module()
    monkeypatch.setattr(m, "BASE", tmp_path)
    events = []

    class Tx(m.Transaction):
        def enter_maintenance(self):
            events.append("maintenance")

        def backup(self):
            events.append("backup")

        def activate(self):
            events.append("activate")

        def verify(self):
            events.append("verify")

        def publish(self):
            events.append("public-check")

        def commit(self):
            events.append("committed")

        def rollback(self):
            events.append("rollback")

    tx = Tx("v0.1.0-demo.8", "a" * 40)
    tx.execute()
    assert events == [
        "maintenance",
        "backup",
        "activate",
        "verify",
        "public-check",
        "committed",
    ]
