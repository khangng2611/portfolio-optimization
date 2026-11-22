#!/usr/bin/env python3
"""Deploy a committed demo tag from the Mac; private cold backups live on the VPS."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from uuid import uuid4

PROJECT = "portfolio-auth-demo"
ORIGIN = "https://portfolio-demo.tail16175c.ts.net"
ROOT = Path.home() / "portfolio-demo"
BASE = Path.home() / "demo-deploy"
LOG = None


def validate_release(value):
    if not re.fullmatch(r"v[0-9][A-Za-z0-9._-]{0,63}", value):
        raise ValueError("Release must be a version tag, for example v0.1.0-demo.3")
    return value


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_archive(path, expected):
    if digest(path) != expected:
        raise RuntimeError("Backup checksum mismatch; restore refused")


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w") as stream:
        os.chmod(tmp, 0o600)
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def run(command, *, cwd=None, env=None, private=False):
    result = subprocess.run(
        [str(c) for c in command], cwd=cwd, env=env, text=True, capture_output=True
    )
    if LOG is not None and not private:
        with LOG.open("a") as stream:
            stream.write(shlex.join([str(c) for c in command]) + "\n")
            stream.write(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(
            f"{Path(str(command[0])).name} failed; see private transaction log"
        )
    return result.stdout.strip()


def event(name, **fields):
    try:
        print(json.dumps({"event": name, **fields}), flush=True)
    except BrokenPipeError:
        # Losing the Mac connection must not interrupt database restoration.
        sys.stdout = open(os.devnull, "w")


def checkout(root, commit):
    # Tracked files can be bind-mounted into non-root containers; secrets stay under umask 077.
    mask = os.umask(0o022)
    try:
        run(["git", "checkout", "--detach", commit], cwd=root)
    finally:
        os.umask(mask)


def compose(root, images=None):
    result = [
        "docker",
        "compose",
        "-p",
        PROJECT,
        "--env-file",
        str(root / "infra/local/.generated/.env"),
        "-f",
        str(root / "infra/local/compose.yaml"),
        "-f",
        str(root / "infra/public/compose.funnel.yaml"),
    ]
    if images:
        result += ["-f", str(images)]
    return result


def public_check(origin):
    command = [
        "curl",
        "--noproxy",
        "*",
        "-fsS",
        "--connect-timeout",
        "3",
        "--max-time",
        "8",
    ]
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if (
            subprocess.run(
                command + [origin + "/health/live"], capture_output=True
            ).returncode
            == 0
        ):
            return
        # Public DNS is independently checked; never disable TLS verification.
        if shutil.which("dig"):
            host = urlsplit(origin).hostname
            lookup = subprocess.run(
                ["dig", "@1.1.1.1", host, "A", "+short", "+time=2", "+tries=1"],
                text=True,
                capture_output=True,
            )
            for address in lookup.stdout.splitlines():
                try:
                    ipaddress.IPv4Address(address)
                except ValueError:
                    continue
                if (
                    subprocess.run(
                        command
                        + [
                            "--resolve",
                            f"{host}:443:{address}",
                            origin + "/health/live",
                        ],
                        capture_output=True,
                    ).returncode
                    == 0
                ):
                    return
                break
        time.sleep(3)
    raise RuntimeError("Public HTTPS health check failed")


class Transaction:
    def __init__(self, release, commit, origin=ORIGIN):
        self.release, self.commit_hash, self.origin = release, commit, origin
        self.id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid4().hex[:8]
        self.path = BASE / "transactions" / self.id
        self.path.mkdir(parents=True, mode=0o700)
        self.state = {
            "schema": 1,
            "id": self.id,
            "path": str(self.path),
            "phase": "preparing",
            "backup_complete": False,
            "origin": origin,
        }
        self.maintenance = None
        global LOG
        LOG = self.path / "private.log"
        LOG.touch(mode=0o600)

    def checkpoint(self, phase):
        self.state["phase"] = phase
        atomic_json(self.path / "journal.json", self.state)
        atomic_json(BASE / "pending.json", self.state)
        event("phase", phase=phase, transaction=self.id)

    def dc(self, *args, old=False):
        image_file = self.state["old_images"] if old else str(self.path / "images.json")
        return run(compose(ROOT, image_file) + list(args), cwd=ROOT)

    def prepare(self):
        if run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT):
            raise RuntimeError("VPS checkout must be clean")
        previous = run(["git", "rev-parse", "HEAD"], cwd=ROOT)
        self.state["previous_commit"] = previous
        self.state["previous_manifest"] = (
            json.loads((BASE / "current.json").read_text())
            if (BASE / "current.json").exists()
            else None
        )
        self.state["previous_python"] = (self.state["previous_manifest"] or {}).get(
            "python", str(ROOT / ".venv-software/bin/python")
        )
        candidate = self.path / "source"
        mask = os.umask(0o022)
        try:
            run(["git", "clone", "--shared", "--no-checkout", ROOT, candidate])
            run(["git", "checkout", "--detach", self.commit_hash], cwd=candidate)
        finally:
            os.umask(mask)
        gen = Path("infra/local/.generated")
        shutil.copytree(ROOT / gen, candidate / gen, symlinks=True)
        run(["python3.12", "infra/local/bootstrap.py", "--refresh-demo"], cwd=candidate)
        config = json.loads(
            run(
                compose(candidate) + ["config", "--format", "json"],
                cwd=candidate,
                private=True,
            )
        )
        for service in config["services"].values():
            for mount in service.get("volumes", []):
                if mount["type"] == "bind" and not mount.get("read_only", False):
                    if (
                        not Path(mount["source"])
                        .resolve()
                        .is_relative_to((candidate / gen).resolve())
                    ):
                        raise RuntimeError(
                            "Writable bind mount is outside the protected generated directory"
                        )
        # Use the candidate's own release/profile validation before touching the live stack.
        run(
            [
                "python3.12",
                "scripts/check_private_demo.py",
                "--release",
                self.commit_hash,
                "--funnel-origin",
                self.origin,
            ],
            cwd=candidate,
        )
        builds = {s["image"] for s in config["services"].values() if "build" in s}
        image_names = {
            name: "portfolio-release/"
            + hashlib.sha256(name.encode()).hexdigest()[:16]
            + ":"
            + self.commit_hash
            for name in builds
        }
        images = {
            "services": {
                name: {"image": image_names[s["image"]]}
                for name, s in config["services"].items()
                if s.get("image") in builds
            }
        }
        atomic_json(self.path / "images.json", images)
        event("phase", phase="building-release-images", transaction=self.id)
        run(compose(candidate, self.path / "images.json") + ["build"], cwd=candidate)
        for service in config["services"].values():
            name = service.get("image")
            if not name or name in builds:
                continue
            result = subprocess.run(
                ["docker", "image", "inspect", name], capture_output=True
            )
            if result.returncode:
                run(["docker", "pull", name])
        # Smoke dependencies are isolated per release; rollback keeps its prior environment.
        event("phase", phase="preparing-smoke-environment", transaction=self.id)
        python = candidate / ".venv-deploy/bin/python"
        run(["python3.12", "-m", "venv", python.parent.parent])
        spec = importlib.util.spec_from_file_location(
            "software_setup", candidate / "scripts/setup_software.py"
        )
        setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup)
        command = [
            python,
            "-m",
            "pip",
            "install",
            "-c",
            candidate / "services/quant-serving/requirements.lock",
        ]
        for package in setup.PACKAGES:
            command += ["-e", candidate / package]
        command += [f"{name}=={version}" for name, version in setup.TOOLS.items()]
        run(command)
        run([python, "-m", "pip", "check"])
        self.state["python"] = str(python)
        self.state["candidate"] = str(candidate)
        self.state["commit"], self.state["release"] = self.commit_hash, self.release
        self.capture_previous_images()
        volumes = run(
            [
                "docker",
                "volume",
                "ls",
                "-q",
                "--filter",
                "label=com.docker.compose.project=" + PROJECT,
            ]
        ).splitlines()
        self.state["volumes"] = [self.volume(name) for name in volumes]
        if not volumes:
            raise RuntimeError(
                "No existing demo volumes; refusing an unprotected deployment"
            )
        if {v["name"] for v in config.get("volumes", {}).values()} != set(volumes):
            raise RuntimeError(
                "Volume topology changes require a separate backup/migration plan"
            )
        for volume in volumes:
            users = run(
                ["docker", "ps", "-aq", "--filter", "volume=" + volume]
            ).splitlines()
            for container in users:
                owner = run(
                    [
                        "docker",
                        "inspect",
                        container,
                        "--format",
                        '{{index .Config.Labels "com.docker.compose.project"}}',
                    ]
                )
                if owner != PROJECT:
                    raise RuntimeError("A demo volume is also used by another project")
        used = sum(
            int(run(["sudo", "du", "-sk", v["mount"]]).split()[0]) * 1024
            for v in self.state["volumes"]
        )
        used += int(run(["du", "-sk", ROOT / gen]).split()[0]) * 1024
        if shutil.disk_usage(BASE).free < 2 * used + 1024**3:
            raise RuntimeError("Insufficient disk for backup and restore")
        # Do not start downtime close to the unchanged daily shutdown.
        from zoneinfo import ZoneInfo
        from datetime import datetime

        now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        if now.hour == 22:
            raise RuntimeError(
                "Too close to 23:00 auto-shutdown; deploy earlier or after 23:00"
            )

    def volume(self, name):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise RuntimeError("Invalid managed volume name")
        data = json.loads(run(["docker", "volume", "inspect", name], private=True))[0]
        docker_root = Path(run(["docker", "info", "--format", "{{.DockerRootDir}}"]))
        mount = docker_root / "volumes" / name / "_data"
        if (
            data["Driver"] != "local"
            or data.get("Options")
            or Path(data["Mountpoint"]) != mount
        ):
            raise RuntimeError(
                "Unsupported volume storage; refusing destructive restore"
            )
        if (data.get("Labels") or {}).get("com.docker.compose.project") != PROJECT:
            raise RuntimeError("Volume is not owned by the demo project")
        return {"name": name, "mount": str(mount)}

    def capture_previous_images(self):
        ids = run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                "label=com.docker.compose.project=" + PROJECT,
            ]
        ).splitlines()
        if not ids:
            raise RuntimeError("No previous containers to protect")
        services = {}
        volumes_used = set()
        for container in ids:
            # Select only required metadata, never record container environment/secrets.
            row = json.loads(
                run(
                    [
                        "docker",
                        "inspect",
                        container,
                        "--format",
                        '{"service":{{json (index .Config.Labels "com.docker.compose.service")}},"image":{{json .Image}},"mounts":{{json .Mounts}}}',
                    ],
                    private=True,
                )
            )
            service = row["service"]
            tag = f"portfolio-rollback/{service}:{self.id.lower()}"
            try:
                run(["docker", "image", "tag", row["image"], tag])
            except RuntimeError:
                # A running container can outlive removed image metadata. Preserve its runtime too.
                event(
                    "phase", phase="protecting-runtime-" + service, transaction=self.id
                )
                snapshot = run(["docker", "commit", "--pause=true", container, tag])
                self.state.setdefault("runtime_image_snapshots", {})[service] = snapshot
            services[service] = {"image": tag}
            volumes_used.update(
                m["Name"] for m in row["mounts"] if m["Type"] == "volume"
            )
        managed = set(
            run(
                [
                    "docker",
                    "volume",
                    "ls",
                    "-q",
                    "--filter",
                    "label=com.docker.compose.project=" + PROJECT,
                ]
            ).splitlines()
        )
        if not volumes_used <= managed:
            raise RuntimeError(
                "Unmanaged/anonymous volumes require an explicit backup strategy"
            )
        file = self.path / "previous-images.json"
        atomic_json(file, {"services": services})
        self.state["old_images"] = str(file)

    def enter_maintenance(self):
        self.checkpoint("stopping")
        self.start_maintenance()
        run(
            [
                "sudo",
                "tailscale",
                "funnel",
                "--bg",
                "--https=443",
                "http://127.0.0.1:3001",
            ]
        )
        self.dc("stop", "-t", "30", old=True)
        # A cold snapshot requires every project container to be stopped.
        if run(
            [
                "docker",
                "ps",
                "-q",
                "--filter",
                "label=com.docker.compose.project=" + PROJECT,
            ]
        ):
            raise RuntimeError("Containers are still running; cold backup refused")

    def start_maintenance(self):
        import socket

        with socket.socket() as sock:
            occupied = sock.connect_ex(("127.0.0.1", 3001)) == 0
        if occupied:
            from urllib.request import urlopen
            from urllib.error import HTTPError

            try:
                urlopen("http://127.0.0.1:3001", timeout=3)
            except HTTPError as error:
                if (
                    error.code == 503
                    and error.headers.get("X-Portfolio-Maintenance") == "1"
                ):
                    return
            raise RuntimeError("Maintenance port 3001 is already in use")
        self.maintenance = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--maintenance"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for _ in range(30):
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", 3001)) == 0:
                    return
            time.sleep(0.1)
        raise RuntimeError("Maintenance page did not start")

    def backup(self):
        archives = []
        for volume in self.state["volumes"]:
            file = self.path / (volume["name"] + ".tar.gz")
            file.touch(mode=0o600)
            run(
                [
                    "sudo",
                    "tar",
                    "--xattrs",
                    "--acls",
                    "--numeric-owner",
                    "-czf",
                    file,
                    "-C",
                    volume["mount"],
                    ".",
                ]
            )
            run(["sudo", "tar", "-tzf", file], private=True)
            archives.append({"file": str(file), "sha256": digest(file), **volume})
        generated = self.path / "generated.tar.gz"
        generated.touch(mode=0o600)
        run(["tar", "-czf", generated, "-C", ROOT / "infra/local/.generated", "."])
        run(["tar", "-tzf", generated], private=True)
        self.state["archives"] = archives
        self.state["generated"] = {"file": str(generated), "sha256": digest(generated)}
        for archive in [*archives, self.state["generated"]]:
            with Path(archive["file"]).open("r+b") as stream:
                os.fsync(stream.fileno())
        self.state["backup_complete"] = True
        self.checkpoint("backup-complete")

    def activate(self):
        self.checkpoint("activating")
        checkout(ROOT, self.commit_hash)
        run(["python3.12", "infra/local/bootstrap.py", "--refresh-demo"], cwd=ROOT)
        self.dc(
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "--force-recreate",
            "--wait",
            "--wait-timeout",
            "300",
        )

    def verify(self):
        self.checkpoint("verifying")
        run(
            [
                "python3.12",
                "scripts/check_private_demo.py",
                "--release",
                self.commit_hash,
                "--funnel-origin",
                self.origin,
            ],
            cwd=ROOT,
        )
        if (ROOT / "infra/local/.generated/g2-receipt.json").exists():
            run(
                [
                    self.state["python"],
                    ROOT / "scripts/smoke_g2.py",
                    "--verify-receipt",
                ],
                cwd=ROOT,
            )
        run(
            [
                self.state["python"],
                ROOT / "scripts/smoke_demo_web.py",
                "--origin",
                self.origin,
            ],
            cwd=ROOT,
        )
        for script in ["smoke_software.py", "smoke_g2.py"]:
            run([self.state["python"], ROOT / "scripts" / script], cwd=ROOT)
        run(["curl", "-fsS", "--max-time", "15", "http://127.0.0.1:3000/health/live"])
        run(["curl", "-fsS", "--max-time", "15", "http://127.0.0.1:3000/login"])

    def publish(self):
        self.checkpoint("awaiting-public-check")
        run(
            [
                "sudo",
                "tailscale",
                "funnel",
                "--bg",
                "--https=443",
                "http://127.0.0.1:3000",
            ]
        )
        event("public-ready", transaction=self.id, origin=self.origin)
        for _ in range(180):
            decision = self.path / "decision.json"
            if decision.exists():
                if json.loads(decision.read_text())["decision"] != "accept":
                    raise RuntimeError("External public check rejected the release")
                return
            time.sleep(1)
        raise RuntimeError("External verification timed out; rollback required")

    def commit(self):
        manifest = {
            "schema": 1,
            "release": self.release,
            "commit": self.commit_hash,
            "images": str(self.path / "images.json"),
            "python": self.state["python"],
            "origin": self.origin,
            "transaction": self.id,
        }
        atomic_json(BASE / "current.json", manifest)
        self.checkpoint("committed")
        (BASE / "pending.json").unlink()
        self.finish_maintenance()
        event("done", status="deployed", release=self.release, backup=str(self.path))

    def finish_maintenance(self):
        if self.maintenance:
            self.maintenance.terminate()
            self.maintenance.wait(timeout=10)
            self.maintenance = None
        pidfile = BASE / "maintenance.pid"
        if pidfile.exists():
            pid = int(pidfile.read_text())
            command = Path(f"/proc/{pid}/cmdline")
            if command.exists() and b"--maintenance" in command.read_bytes().split(
                b"\0"
            ):
                os.kill(pid, signal.SIGTERM)
            pidfile.unlink(missing_ok=True)

    def rollback(self):
        self.checkpoint("rolling-back")
        self.start_maintenance()
        run(
            [
                "sudo",
                "tailscale",
                "funnel",
                "--bg",
                "--https=443",
                "http://127.0.0.1:3001",
            ]
        )
        # Verify every byte before stopping/clearing any storage.
        if self.state["backup_complete"]:
            for archive in [*self.state["archives"], self.state["generated"]]:
                verify_archive(archive["file"], archive["sha256"])
        try:
            self.dc("stop", "-t", "30")
        except RuntimeError:
            self.dc("stop", "-t", "30", old=True)
        if run(
            [
                "docker",
                "ps",
                "-q",
                "--filter",
                "label=com.docker.compose.project=" + PROJECT,
            ]
        ):
            raise RuntimeError("Rollback requires stopped containers")
        if self.state["backup_complete"]:
            for archive in self.state["archives"]:
                actual = self.volume(archive["name"])
                if actual["mount"] != archive["mount"]:
                    raise RuntimeError("Volume path changed; restore refused")
                run(["sudo", "find", actual["mount"], "-mindepth", "1", "-delete"])
                run(
                    [
                        "sudo",
                        "tar",
                        "--xattrs",
                        "--acls",
                        "--numeric-owner",
                        "-xzf",
                        archive["file"],
                        "-C",
                        actual["mount"],
                    ]
                )
            generated = ROOT / "infra/local/.generated"
            generated.rename(self.path / ("failed-generated-" + uuid4().hex[:8]))
            generated.mkdir(mode=0o700)
            run(["tar", "-xzpf", self.state["generated"]["file"], "-C", generated])
        checkout(ROOT, self.state["previous_commit"])
        self.dc(
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "--force-recreate",
            "--wait",
            "--wait-timeout",
            "300",
            old=True,
        )
        run(["curl", "-fsS", "--max-time", "15", "http://127.0.0.1:3000/health/live"])
        run(
            [
                "sudo",
                "tailscale",
                "funnel",
                "--bg",
                "--https=443",
                "http://127.0.0.1:3000",
            ]
        )
        previous = self.state["previous_manifest"] or {
            "schema": 1,
            "release": "v0.1.0-demo.2",
            "commit": self.state["previous_commit"],
            "python": self.state["previous_python"],
            "origin": self.origin,
        }
        previous["images"] = self.state["old_images"]
        atomic_json(BASE / "current.json", previous)
        self.checkpoint("rolled-back")
        (BASE / "pending.json").unlink()
        self.finish_maintenance()
        event("done", status="rolled-back", backup=str(self.path))

    def execute(self):
        try:
            self.enter_maintenance()
            self.backup()
            self.activate()
            self.verify()
            self.publish()
            self.commit()
        except BaseException:
            self.rollback()
            raise


def recover():
    pending = BASE / "pending.json"
    if not pending.exists():
        return
    state = json.loads(pending.read_text())
    if state["schema"] != 1:
        raise RuntimeError("Unknown recovery journal version")
    tx = Transaction.__new__(Transaction)
    tx.id, tx.path, tx.state, tx.origin = (
        state["id"],
        Path(state["path"]),
        state,
        state["origin"],
    )
    tx.maintenance = None
    global LOG
    LOG = tx.path / "private.log"
    tx.rollback()


def maintenance():
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = "Đang cập nhật demo. Vui lòng quay lại sau.\n".encode()
            self.send_response(503)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Portfolio-Maintenance", "1")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    os.umask(0o077)
    (BASE / "maintenance.pid").write_text(str(os.getpid()))
    HTTPServer(("127.0.0.1", 3001), Handler).serve_forever()


def remote(args):
    import fcntl

    os.umask(0o077)
    BASE.mkdir(mode=0o700, exist_ok=True)
    if args.remote_action == "decision":
        if not re.fullmatch(r"[0-9TZ-]+[a-f0-9]{8}", args.transaction):
            raise ValueError("Invalid transaction identifier")
        pending = json.loads((BASE / "pending.json").read_text())
        if (
            pending["id"] != args.transaction
            or pending["phase"] != "awaiting-public-check"
        ):
            raise RuntimeError("Transaction is not awaiting a decision")
        atomic_json(
            Path(pending["path"]) / "decision.json", {"decision": args.decision}
        )
        return
    with (BASE / "deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.environ["DEMO_PUBLIC_ORIGIN"] = ORIGIN
        recover()
        if args.remote_action == "recover":
            return
        validate_release(args.release)
        if not re.fullmatch("[a-f0-9]{40}", args.commit):
            raise ValueError("Invalid commit")
        if (
            run(["git", "rev-parse", args.release + "^{commit}"], cwd=ROOT)
            != args.commit
        ):
            raise RuntimeError("Release tag/commit mismatch")
        for signum in [signal.SIGINT, signal.SIGTERM, signal.SIGHUP]:
            signal.signal(
                signum,
                lambda *_: (_ for _ in ()).throw(
                    RuntimeError("Deployment interrupted")
                ),
            )
        tx = Transaction(args.release, args.commit)
        tx.prepare()
        tx.execute()


def local(args):
    repo = args.repo.resolve()
    deployment = args.deployment_dir.resolve()
    validate_release(args.release)
    commit = run(
        [
            "git",
            "rev-parse",
            "--verify",
            "--end-of-options",
            args.release + "^{commit}",
        ],
        cwd=repo,
    )
    if (
        run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo)
        or run(["git", "rev-parse", "HEAD"], cwd=repo) != commit
    ):
        raise RuntimeError("Checkout the requested tag in a clean repository first")
    print("Checking local software, Web tests and types...", flush=True)
    subprocess.run(
        [repo / ".venv-software/bin/python", "-m", "pytest", "-q", "tests/software"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["npm", "--prefix", str(repo / "apps/web"), "test", "--", "--run"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["npm", "--prefix", str(repo / "apps/web"), "run", "typecheck"],
        cwd=repo,
        check=True,
    )
    az = deployment / ".azure-cli-venv/bin/az"
    env = dict(os.environ, AZURE_CONFIG_DIR=str(deployment / ".azure"))
    vm = [
        "--subscription",
        "8dfe7471-70b5-46b8-880a-936558465b36",
        "-g",
        "rg-portfolio-demo",
        "-n",
        "portfolio-demo",
    ]
    token = subprocess.run(
        [az, "account", "get-access-token", "--query", "expiresOn", "-o", "tsv"],
        env=env,
        capture_output=True,
    )
    if token.returncode:
        login_env = dict(env, AZURE_CORE_LOGIN_EXPERIENCE_V2="off")
        subprocess.run(
            [
                az,
                "login",
                "--tenant",
                "fc263570-d0d7-4cfd-b721-8efc1f3363a7",
                "--output",
                "none",
            ],
            env=login_env,
            check=True,
        )
    schedule = json.loads(
        run(
            [
                az,
                "resource",
                "show",
                "--subscription",
                vm[1],
                "-g",
                "rg-portfolio-demo",
                "--resource-type",
                "Microsoft.DevTestLab/schedules",
                "--name",
                "shutdown-computevm-portfolio-demo",
                "--api-version",
                "2018-09-15",
                "--query",
                "properties",
                "-o",
                "json",
            ],
            env=env,
        )
    )
    if (
        schedule["status"],
        schedule["dailyRecurrence"]["time"],
        schedule["timeZoneId"],
    ) != ("Enabled", "2300", "SE Asia Standard Time"):
        raise RuntimeError(
            "Auto-shutdown differs from 23:00 Vietnam; deployment will not change it"
        )
    run([az, "vm", "start", *vm, "--only-show-errors"], env=env)
    ssh = [
        "ssh",
        "-F",
        str(deployment / "ssh_config"),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "portfolio-demo",
    ]
    for _ in range(40):
        if subprocess.run(ssh + ["true"], capture_output=True).returncode == 0:
            break
        time.sleep(5)
    else:
        raise RuntimeError("SSH unavailable; check the NSG source IP")
    with tempfile.TemporaryDirectory(prefix="portfolio-release-") as temp:
        bundle = Path(temp) / "release.bundle"
        run(["git", "bundle", "create", bundle, args.release], cwd=repo)
        run(ssh + ['umask 077; mkdir -p "$HOME/demo-deploy/incoming"'])
        scp = ["scp", "-F", str(deployment / "ssh_config")]
        remote_dir = "/home/deploy/demo-deploy/incoming"
        run(scp + [str(bundle), f"portfolio-demo:{remote_dir}/{commit}.bundle"])
        run(
            scp
            + [
                str(repo / "scripts/deploy_demo.py"),
                f"portfolio-demo:{remote_dir}/controller-new.py",
            ]
        )
        command = (
            "set -e; umask 077; "
            'cp "$HOME/demo-deploy/incoming/controller-new.py" "$HOME/demo-deploy/controller.py"; '
            'cd "$HOME/portfolio-demo"; git fetch '
            + shlex.quote(f"{remote_dir}/{commit}.bundle")
            + " "
            + shlex.quote(f"refs/tags/{args.release}:refs/tags/{args.release}")
        )
        run(ssh + [command])
    controller = "/home/deploy/demo-deploy/controller.py"
    command = shlex.join(
        [
            "python3.12",
            controller,
            "--remote-action",
            "deploy",
            args.release,
            "--commit",
            commit,
        ]
    )
    process = subprocess.Popen(
        ssh + [command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        for line in process.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message["event"] == "phase":
                print("VPS:", message["phase"], flush=True)
            elif message["event"] == "public-ready":
                decision = "accept"
                try:
                    public_check(ORIGIN)
                except RuntimeError:
                    decision = "reject"
                run(
                    ssh
                    + [
                        shlex.join(
                            [
                                "python3.12",
                                controller,
                                "--remote-action",
                                "decision",
                                "--transaction",
                                message["transaction"],
                                "--decision",
                                decision,
                            ]
                        )
                    ]
                )
            elif message["event"] == "error":
                print("VPS:", message["message"], flush=True)
            elif message["event"] == "done":
                print(json.dumps(message, ensure_ascii=False), flush=True)
        if process.wait() != 0:
            raise RuntimeError(
                "Deploy failed; inspect transaction/rollback status on VPS"
            )
    except BaseException:
        process.terminate()
        # The journal also supports recovery on the next startup if SSH is lost.
        subprocess.run(
            ssh
            + [shlex.join(["python3.12", controller, "--remote-action", "recover"])],
            capture_output=True,
        )
        raise
    print("DEPLOY THÀNH CÔNG: " + ORIGIN)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", nargs="?")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--deployment-dir",
        type=Path,
        default=Path.home() / "Documents/MASTER/Thesis/deployment",
    )
    parser.add_argument("--commit")
    parser.add_argument("--remote-action", choices=["deploy", "recover", "decision"])
    parser.add_argument("--transaction")
    parser.add_argument("--decision", choices=["accept", "reject"])
    parser.add_argument("--maintenance", action="store_true")
    args = parser.parse_args()
    if args.maintenance:
        maintenance()
    elif args.remote_action:
        remote(args)
    else:
        local(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        event(
            "error",
            message=str(exc)
            if isinstance(exc, (RuntimeError, ValueError))
            else type(exc).__name__,
        )
        raise SystemExit(1) from None
