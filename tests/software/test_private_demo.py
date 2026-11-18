"""The private demo must stay on its release and expose only loopback ports."""

from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "check_private_demo",
    Path(__file__).resolve().parents[2] / "scripts/check_private_demo.py",
)
demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo)


@pytest.fixture
def config():
    return {
        "name": "portfolio-auth-demo",
        "services": {
            "web": {
                "environment": {
                    "APP_ORIGIN": "http://localhost:3000",
                    "ALLOW_INSECURE_HTTP": "true",
                },
                "ports": [{"host_ip": "127.0.0.1", "published": "3000", "target": 3000}],
            },
            "auth-api": {},
            "chat-worker": {},
        },
    }


def test_accepts_loopback_compose_without_changing_it(config):
    before = deepcopy(config)
    demo.validate_compose(config)
    assert config == before


@pytest.mark.parametrize("address", [None, "", "0.0.0.0", "::", "192.0.2.1"])
def test_rejects_public_or_implicit_bind(config, address):
    config["services"]["web"]["ports"][0]["host_ip"] = address
    with pytest.raises(ValueError, match="loopback"):
        demo.validate_compose(config)


def test_accepts_ipv6_loopback(config):
    config["services"]["web"]["ports"][0]["host_ip"] = "::1"
    demo.validate_compose(config)


def test_rejects_host_network(config):
    config["services"]["auth-api"]["network_mode"] = "host"
    with pytest.raises(ValueError, match="network_mode"):
        demo.validate_compose(config)


@pytest.mark.parametrize("key", [
    "OPENAI_API_KEY", "CHAT_LLM_PROVIDER", "CHAT_PROVIDER_URL",
    "CHAT_PROVIDER_KEY", "KNOWLEDGE_PAID_APPROVAL",
])
def test_rejects_provider_configuration_without_disclosing_values(config, key):
    config["services"]["chat-worker"]["environment"] = {key: "private-test-value"}
    with pytest.raises(ValueError, match="provider") as error:
        demo.validate_compose(config)
    assert "private-test-value" not in str(error.value)


def test_rejects_changed_origin(config):
    config["services"]["web"]["environment"]["APP_ORIGIN"] = "http://localhost:3001"
    with pytest.raises(ValueError, match="APP_ORIGIN"):
        demo.validate_compose(config)


def test_rejects_another_compose_project(config):
    config["name"] = "another-project"
    with pytest.raises(ValueError, match="project"):
        demo.validate_compose(config)


def test_release_requires_matching_commit_and_clean_files(monkeypatch):
    responses = iter(["a" * 40, "a" * 40, ""])
    monkeypatch.setattr(demo, "run", lambda _: next(responses))
    assert demo.check_release("demo-tag") == "a" * 40
    for responses_list, message in [
        (["a" * 40, "b" * 40], "release"),
        (["a" * 40, "a" * 40, "?? missing-file.py"], "clean"),
    ]:
        responses = iter(responses_list)
        with pytest.raises(ValueError, match=message):
            demo.check_release("demo-tag")


def test_subprocess_errors_hide_configuration_and_secrets(monkeypatch):
    import subprocess

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="private-test-value")

    monkeypatch.setattr(demo.subprocess, "run", fail)
    with pytest.raises(ValueError) as error:
        demo.run(["docker", "compose", "config"])
    assert "private-test-value" not in str(error.value)


def test_accepts_explicit_funnel_origin(config):
    origin = 'https://portfolio-demo.tail123.ts.net'
    config['services']['web']['environment']['APP_ORIGIN'] = origin
    demo.validate_compose(config, origin=origin)


@pytest.mark.parametrize('origin', [
    'http://portfolio-demo.tail123.ts.net',
    'https://portfolio-demo.tail123.ts.net/path',
    'https://portfolio-demo.tail123.ts.net?x=1',
    'https://user:password@portfolio-demo.tail123.ts.net',
    'https://portfolio-demo.tail123.ts.net.evil.example',
])
def test_rejects_invalid_funnel_origin(config, origin):
    config['services']['web']['environment']['APP_ORIGIN'] = origin
    with pytest.raises(ValueError, match='origin'):
        demo.validate_compose(config, origin=origin)


def test_funnel_still_requires_exact_origin_and_loopback(config):
    origin = 'https://portfolio-demo.tail123.ts.net'
    with pytest.raises(ValueError, match='APP_ORIGIN'):
        demo.validate_compose(config, origin=origin)
    config['services']['web']['environment']['APP_ORIGIN'] = origin
    config['services']['web']['ports'][0]['host_ip'] = '0.0.0.0'
    with pytest.raises(ValueError, match='loopback'):
        demo.validate_compose(config, origin=origin)
