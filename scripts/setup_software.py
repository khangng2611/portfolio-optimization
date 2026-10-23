#!/usr/bin/env python3
"""Prepare, start or verify the disposable local software stack without resetting data."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv-software"
PYTHON = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
WEB = ROOT / "apps/web"
GENERATED = ROOT / "infra/local/.generated"
PACKAGES = [
    "packages/contracts",
    "packages/service-auth",
    "packages/service-observability",
    "packages/portfolio-core",
    "services/portfolio",
    "services/quant-serving",
    "services/market-data",
]
TOOLS = {"pytest": "8.4.2", "ruff": "0.13.2", "httpx": "0.28.1"}
LOCK = ROOT / "services/quant-serving/requirements.lock"


def compose_command(tracing: bool = False) -> list[str]:
    command = [
        "docker",
        "compose",
        "--env-file",
        str(GENERATED / ".env"),
        "-f",
        str(ROOT / "infra/local/compose.yaml"),
    ]
    if tracing:
        command += ["-f", str(ROOT / "infra/local/compose.tracing.yaml")]
    return command


class SetupFailure(Exception):
    pass


def run(command: list[str], *, quiet: bool = False, timeout: int | None = None):
    """Arguments never contain credentials; config is always rendered with --quiet."""
    if not quiet:
        print("+ " + shlex.join(map(str, command)), flush=True)
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            check=False,
            timeout=timeout,
            stdout=subprocess.PIPE if quiet else None,
            stderr=subprocess.PIPE if quiet else None,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SetupFailure(
            f"Không chạy được {Path(command[0]).name}; kiểm tra công cụ/runtime."
        ) from None
    if result.returncode:
        # Quiet commands may expand connection details; do not reproduce their output.
        raise SetupFailure(
            f"Lệnh {Path(command[0]).name} thất bại (exit {result.returncode})."
        )
    return result.stdout.strip() if quiet else ""


def prerequisites(python_command: str, *, daemon: bool) -> str:
    executable = shutil.which(python_command)
    if not executable:
        raise SetupFailure(
            "Cần Python 3.12; dùng --python /đường/dẫn/python3.12 nếu cần."
        )
    version = run(
        [
            executable,
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
        ],
        quiet=True,
    )
    if version != "3.12":
        raise SetupFailure("Môi trường software yêu cầu Python 3.12.")
    for name in ["node", "npm", "docker"]:
        if not shutil.which(name):
            raise SetupFailure(
                f"Thiếu {name}; xem docs/software/SETUP_AND_API_TESTING.md."
            )
    node = run(["node", "--version"], quiet=True).lstrip("v").split(".")
    if tuple(map(int, node[:2])) < (22, 12):
        raise SetupFailure("Cần Node.js >=22.12 (khuyến nghị Node 22 LTS).")
    run(["npm", "--version"], quiet=True)
    run(["docker", "compose", "version"], quiet=True)
    if daemon:
        try:
            run(["docker", "info"], quiet=True, timeout=20)
        except SetupFailure:
            raise SetupFailure(
                "Docker daemon chưa đáp ứng; mở Docker Desktop và kiểm tra dung lượng trống."
            ) from None
    print(
        "PASS: Python 3.12, Node/npm và Docker Compose"
        + (", Docker daemon." if daemon else ".")
    )
    return executable


def python_lock_fingerprint() -> str:
    paths = [LOCK] + [ROOT / package / "pyproject.toml" for package in PACKAGES]
    content = b"\n".join(path.read_bytes() for path in paths)
    return hashlib.sha256(
        content + json.dumps(TOOLS, sort_keys=True).encode()
    ).hexdigest()


def python_environment_ready() -> bool:
    if not PYTHON.exists():
        return False
    if any(not (ROOT / package / "pyproject.toml").exists() for package in PACKAGES):
        return False
    marker = VENV / ".software-setup-lock"
    if marker.exists() and marker.read_text().strip() != python_lock_fingerprint():
        return False
    expected = dict(TOOLS, **{"portfolio-service-observability": "0.1.0"})
    for line in LOCK.read_text().splitlines():
        if line and not line.startswith("#"):
            name, version = line.split("==", 1)
            expected[name] = version
    # Ensure editable packages belong to this checkout, not an unrelated install.
    script = (
        "import importlib.metadata as m,json,pathlib,sys,urllib.parse; "
        "expected=json.loads(sys.argv[1]); "
        "assert sys.version_info[:2]==(3,12); "
        "assert all(m.version(k)==v for k,v in expected.items()); "
        "packages=json.loads(sys.argv[2]); "
        "names=['portfolio-contracts','portfolio-service-auth','portfolio-service-observability','portfolio-core',"
        "'portfolio-service','portfolio-quant-service','portfolio-market-service']; "
        "urls=[json.loads(m.distribution(n).read_text('direct_url.json')) for n in names]; "
        "assert all(u.get('dir_info',{}).get('editable') and "
        "pathlib.Path(urllib.parse.unquote(urllib.parse.urlparse(u['url']).path)).resolve()==pathlib.Path(p).resolve() "
        "for u,p in zip(urls,packages))"
    )
    try:
        run(
            [
                str(PYTHON),
                "-c",
                script,
                json.dumps(expected),
                json.dumps([str(ROOT / p) for p in PACKAGES]),
            ],
            quiet=True,
        )
        run([str(PYTHON), "-m", "pip", "check"], quiet=True)
    except SetupFailure:
        return False
    return True


def web_environment_ready() -> bool:
    if not (WEB / "node_modules").exists():
        return False
    try:
        run(["npm", "--prefix", str(WEB), "ls", "--depth=0"], quiet=True)
    except SetupFailure:
        return False
    marker = WEB / "node_modules/.software-setup-lock"
    fingerprint = hashlib.sha256((WEB / "package-lock.json").read_bytes()).hexdigest()
    # Existing healthy installs are accepted once; subsequent lock changes trigger npm ci.
    return not marker.exists() or marker.read_text().strip() == fingerprint


def install(executable: str, skip: bool) -> None:
    missing = [p for p in PACKAGES if not (ROOT / p / "pyproject.toml").exists()]
    if missing:
        raise SetupFailure("Thiếu package software: " + ", ".join(missing))
    python_ready, web_ready = python_environment_ready(), web_environment_ready()
    if skip and not (python_ready and web_ready):
        raise SetupFailure(
            "--skip-install yêu cầu môi trường software và node_modules đã hợp lệ."
        )
    if not python_ready:
        if not PYTHON.exists():
            run([executable, "-m", "venv", str(VENV)])
        else:
            version = run(
                [
                    str(PYTHON),
                    "-c",
                    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
                ],
                quiet=True,
            )
            if version != "3.12":
                raise SetupFailure(
                    ".venv-software dùng Python khác 3.12; hãy đổi tên và tạo lại môi trường riêng."
                )
        command = [str(PYTHON), "-m", "pip", "install", "-c", str(LOCK)]
        for package in PACKAGES:
            command += ["-e", str(ROOT / package)]
        command += [f"{name}=={version}" for name, version in TOOLS.items()]
        run(command)
        run([str(PYTHON), "-m", "pip", "check"])
    else:
        print("Dùng lại .venv-software đang hợp lệ.")
    (VENV / ".software-setup-lock").write_text(python_lock_fingerprint() + "\n")
    if not web_ready:
        run(["npm", "--prefix", str(WEB), "ci"])
    else:
        print("Dùng lại apps/web/node_modules đang hợp lệ.")
    (WEB / "node_modules/.software-setup-lock").write_text(
        hashlib.sha256((WEB / "package-lock.json").read_bytes()).hexdigest() + "\n"
    )


def verify(live: bool, tracing: bool = False) -> None:
    compose = compose_command(tracing)
    if not python_environment_ready() or not web_environment_ready():
        raise SetupFailure("Chạy prepare trước để cài môi trường software.")
    run(
        [
            str(PYTHON),
            "-m",
            "pytest",
            "tests/software",
            "packages/portfolio-core/tests",
            "-q",
        ]
    )
    run(
        [
            str(PYTHON),
            "-m",
            "ruff",
            "check",
            "packages",
            "services",
            "tests/software",
            "scripts/setup_software.py",
            "scripts/smoke_software.py",
            "scripts/smoke_tracing.py",
            "scripts/export_software_contracts.py",
            "scripts/lock_software_dependencies.py",
            "infra",
        ]
    )
    run([str(PYTHON), "scripts/export_software_contracts.py"])
    for command in [["test"], ["run", "typecheck"], ["run", "build"]]:
        run(["npm", "--prefix", str(WEB)] + command)
    if live:
        run(compose + ["config", "--quiet"], quiet=True)
        run([str(PYTHON), "infra/local/verify_boundaries.py"])
        run([str(PYTHON), "scripts/smoke_software.py"])
        if tracing:
            run([str(PYTHON), "scripts/smoke_tracing.py"])
    print("PASS: các kiểm tra được yêu cầu đã hoàn tất.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        nargs="?",
        default="up",
        choices=["prepare", "up", "check", "verify"],
        help="prepare: cài/config; up: chạy stack; check: chỉ đọc; verify: test/build",
    )
    parser.add_argument(
        "--python",
        default="python3.12",
        help="Python 3.12 executable (default: python3.12)",
    )
    parser.add_argument(
        "--enable-test-client",
        action="store_true",
        help="Bật portfolio-test cho disposable local realm; cần cho Swagger/Postman/smoke",
    )
    parser.add_argument(
        "--refresh-demo",
        action="store_true",
        help="Tạo demo mới bất biến, giữ demo và secrets cũ",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Yêu cầu môi trường đã hợp lệ, không cài dependency",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Dùng Docker images hiện có; cần build lại khi source đổi",
    )
    parser.add_argument(
        "--tracing",
        action="store_true",
        help="Dùng Compose overlay OpenTelemetry/Jaeger local cho prepare/up/check/verify; cần truyền lại ở mỗi lệnh",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="verify: thêm boundary + real JWT/broker smoke trên stack healthy",
    )
    args = parser.parse_args()
    compose = compose_command(args.tracing)
    if args.mode in {"check", "verify"} and (
        args.enable_test_client
        or args.refresh_demo
        or args.skip_install
        or args.skip_build
    ):
        parser.error("Các cờ bootstrap/install/build chỉ dùng cho prepare hoặc up.")
    if args.live and args.mode != "verify":
        parser.error("--live chỉ dùng với verify.")
    executable = prerequisites(
        args.python, daemon=args.mode in {"up", "check"} or args.live
    )
    if args.mode == "check":
        print(
            ".venv-software: "
            + ("hợp lệ" if python_environment_ready() else "cần prepare")
        )
        print(
            "node_modules: " + ("hợp lệ" if web_environment_ready() else "cần prepare")
        )
        if (GENERATED / ".env").exists():
            run(compose + ["config", "--quiet"], quiet=True)
            print("PASS: Compose config hợp lệ (không in secrets).")
        else:
            print("Chưa bootstrap; chạy prepare hoặc up.")
        return
    if args.mode == "verify":
        verify(args.live, args.tracing)
        return
    install(executable, args.skip_install)
    command = [executable, "infra/local/bootstrap.py"]
    if args.enable_test_client:
        command.append("--enable-test-client")
    if args.refresh_demo:
        command.append("--refresh-demo")
    run(command)
    run(compose + ["config", "--quiet"], quiet=True)
    if args.mode == "up":
        if not args.skip_build:
            run(compose + ["build"])
        dependencies = ["postgres", "rabbitmq", "redis", "keycloak"]
        if args.tracing:
            dependencies.append("jaeger")
        run(compose + ["up", "-d", "--wait", "--wait-timeout", "240"] + dependencies)
        run([str(PYTHON), "infra/local/upgrade.py"])
        run(compose + ["up", "-d", "--wait", "--wait-timeout", "240"])
        print(
            "Stack healthy: http://localhost:3000 | Swagger: :8001/docs, :8002/docs, :8003/docs"
        )
    else:
        print("Đã chuẩn bị; chạy up để khởi động Docker stack.")
    if args.tracing:
        print(
            "Tracing local đã chọn; Jaeger UI: http://localhost:16686 (chỉ chạy sau up --tracing)."
        )
    print(
        "Credentials riêng: infra/local/.generated/accounts.json và .env. Hướng dẫn: docs/software/SETUP_AND_API_TESTING.md"
    )


if __name__ == "__main__":
    try:
        main()
    except (SetupFailure, ValueError, OSError) as error:
        message = (
            str(error) if isinstance(error, SetupFailure) else type(error).__name__
        )
        raise SystemExit("FAIL: " + message) from None
