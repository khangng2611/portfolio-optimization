"""Opt-in tracing selects the overlay at every setup/verification command boundary."""

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_setup():
    spec = importlib.util.spec_from_file_location(
        "tracing_setup", ROOT / "scripts/setup_software.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("mode", ["prepare", "up", "check", "verify"])
def test_tracing_flag_selects_overlay_for_all_compose_commands(
    mode, tmp_path, monkeypatch
):
    setup = load_setup()
    generated = tmp_path / ".generated"
    generated.mkdir()
    (generated / ".env").write_text("# disposable test config\n")
    setup.GENERATED = generated
    emitted = []
    monkeypatch.setattr(setup, "prerequisites", lambda *args, **kwargs: "python3.12")
    monkeypatch.setattr(setup, "install", lambda *args: None)
    monkeypatch.setattr(setup, "python_environment_ready", lambda: True)
    monkeypatch.setattr(setup, "web_environment_ready", lambda: True)
    monkeypatch.setattr(
        setup, "run", lambda command, **kwargs: emitted.append((command, kwargs)) or ""
    )
    arguments = ["setup_software.py", mode, "--tracing"]
    if mode == "verify":
        arguments.append("--live")
    monkeypatch.setattr(sys, "argv", arguments)
    setup.main()
    compose = [
        (command, options)
        for command, options in emitted
        if command[:2] == ["docker", "compose"]
    ]
    assert compose
    for command, options in compose:
        compose_files = [
            command[index + 1] for index, arg in enumerate(command) if arg == "-f"
        ]
        assert compose_files == [
            str(ROOT / "infra/local/compose.yaml"),
            str(ROOT / "infra/local/compose.tracing.yaml"),
        ]
        if "config" in command:
            assert command[-2:] == ["config", "--quiet"]
            assert options["quiet"] is True
    if mode == "up":
        dependency_start = next(
            command for command, _ in compose if "postgres" in command
        )
        assert "jaeger" in dependency_start
        positions = {
            "dependencies": emitted.index(
                next(entry for entry in emitted if entry[0] == dependency_start)
            ),
            "upgrade": next(
                index
                for index, (command, _) in enumerate(emitted)
                if command[-1] == "infra/local/upgrade.py"
            ),
        }
        assert positions["dependencies"] < positions["upgrade"]
    if mode == "verify":
        assert any(command[-1] == "scripts/smoke_tracing.py" for command, _ in emitted)


@pytest.mark.parametrize("mode", ["prepare", "up", "check", "verify"])
def test_base_setup_stays_opt_out_and_never_starts_jaeger(mode, tmp_path, monkeypatch):
    setup = load_setup()
    generated = tmp_path / ".generated"
    generated.mkdir()
    (generated / ".env").write_text("# disposable test config\n")
    setup.GENERATED = generated
    emitted = []
    monkeypatch.setattr(setup, "prerequisites", lambda *args, **kwargs: "python3.12")
    monkeypatch.setattr(setup, "install", lambda *args: None)
    monkeypatch.setattr(setup, "python_environment_ready", lambda: True)
    monkeypatch.setattr(setup, "web_environment_ready", lambda: True)
    monkeypatch.setattr(
        setup, "run", lambda command, **kwargs: emitted.append(command) or ""
    )
    arguments = ["setup_software.py", mode]
    if mode == "verify":
        arguments.append("--live")
    monkeypatch.setattr(sys, "argv", arguments)
    setup.main()
    for command in emitted:
        assert str(ROOT / "infra/local/compose.tracing.yaml") not in command
        assert "jaeger" not in command
        assert command[:2] != [str(setup.PYTHON), "scripts/smoke_tracing.py"]


def test_install_includes_editable_observability_package_in_software_environment(
    tmp_path, monkeypatch
):
    setup = load_setup()
    # Package files are a controlled fixture; pip/npm are external command boundaries.
    for package in [
        "packages/contracts",
        "packages/service-auth",
        "packages/service-observability",
        "packages/portfolio-core",
        "services/portfolio",
        "services/quant-serving",
        "services/market-data",
    ]:
        directory = tmp_path / package
        directory.mkdir(parents=True)
        (directory / "pyproject.toml").write_text(
            '[project]\nname="fixture"\nversion="0.1.0"\n'
        )
    (tmp_path / "requirements.lock").write_text("# fixture\n")
    (tmp_path / "apps/web/node_modules").mkdir(parents=True)
    (tmp_path / "apps/web/package-lock.json").write_text("{}")
    (tmp_path / ".venv-software/bin").mkdir(parents=True)
    setup.ROOT = tmp_path
    setup.WEB = tmp_path / "apps/web"
    setup.VENV = tmp_path / ".venv-software"
    setup.PYTHON = setup.VENV / "bin/python"
    setup.LOCK = tmp_path / "requirements.lock"
    monkeypatch.setattr(setup, "python_environment_ready", lambda: False)
    monkeypatch.setattr(setup, "web_environment_ready", lambda: True)
    emitted = []
    monkeypatch.setattr(
        setup, "run", lambda command, **kwargs: emitted.append(command) or ""
    )
    setup.install("python3.12", skip=False)
    install = next(
        command for command in emitted if command[1:4] == ["-m", "pip", "install"]
    )
    package_index = install.index(str(tmp_path / "packages/service-observability"))
    assert install[package_index - 1] == "-e"


def test_overlay_compose_preserves_business_configuration_and_exports_only_to_local_jaeger(
    tmp_path,
):
    import json
    import shutil
    import subprocess

    if not shutil.which("docker"):
        pytest.skip("Docker Compose CLI is unavailable")
    values = [
        "POSTGRES_PASSWORD",
        "IDENTITY_MIGRATOR_PASSWORD",
        "IDENTITY_RUNTIME_PASSWORD",
        "PORTFOLIO_MIGRATOR_PASSWORD",
        "PORTFOLIO_RUNTIME_PASSWORD",
        "QUANT_MIGRATOR_PASSWORD",
        "QUANT_RUNTIME_PASSWORD",
        "MARKET_MIGRATOR_PASSWORD",
        "MARKET_RUNTIME_PASSWORD",
        "KEYCLOAK_ADMIN_PASSWORD",
        "OIDC_CLIENT_SECRET",
        "QUANT_CLIENT_SECRET",
        "REDIS_PASSWORD",
        "SESSION_ENCRYPTION_KEY",
        "PORTFOLIO_PUBLISHER_PASSWORD",
        "PORTFOLIO_CONSUMER_PASSWORD",
        "QUANT_PUBLISHER_PASSWORD",
        "QUANT_CONSUMER_PASSWORD",
        "MARKET_PUBLISHER_PASSWORD",
        "MARKET_CONSUMER_PASSWORD",
    ]
    env_file = tmp_path / "compose.env"
    env_file.write_text("\n".join(name + "=disposable-test-value" for name in values))
    command = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(ROOT / "infra/local/compose.yaml"),
    ]
    outputs = []
    for files in [[], ["-f", str(ROOT / "infra/local/compose.tracing.yaml")]]:
        result = subprocess.run(
            command + files + ["config", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, "Compose failed to merge the tracing overlay"
        outputs.append(json.loads(result.stdout))
    base, traced = outputs
    assert "jaeger" not in base["services"]
    jaeger = traced["services"]["jaeger"]
    assert jaeger["image"] == "cr.jaegertracing.io/jaegertracing/jaeger:2.22.0"
    assert {
        (port["host_ip"], port["published"], port["target"]) for port in jaeger["ports"]
    } == {("127.0.0.1", "16686", 16686), ("127.0.0.1", "4318", 4318)}
    assert not jaeger.get("volumes")
    instrumented = [
        "web",
        "portfolio-api",
        "portfolio-dispatch",
        "portfolio-consume",
        "quant-api",
        "quant-dispatch",
        "quant-consume",
        "market-api",
        "market-dispatch",
        "market-consume",
    ]
    for service in instrumented:
        before = base["services"][service]
        after = traced["services"][service]
        environment = after["environment"]
        assert environment["OTEL_TRACES_ENABLED"] == "true"
        assert (
            environment["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"]
            == "http://jaeger:4318/v1/traces"
        )
        assert environment["OTEL_SERVICE_NAME"] == (
            "web-bff" if service == "web" else service
        )
        assert environment["OTEL_TRACES_SAMPLER"] == "always_on"
        assert environment["TRACE_VIEWER_URL"] == "http://localhost:16686"
        assert all(
            environment[name] == value for name, value in before["environment"].items()
        )
        assert "OTEL_TRACES_ENABLED" not in before["environment"]
        assert {
            name: value for name, value in after.items() if name != "environment"
        } == {name: value for name, value in before.items() if name != "environment"}
    assert base["volumes"] == traced["volumes"]
    for service in [
        "postgres",
        "rabbitmq",
        "redis",
        "identity-migrate",
        "keycloak",
        "portfolio-migrate",
        "quant-migrate",
        "market-migrate",
    ]:
        assert base["services"][service] == traced["services"][service]
