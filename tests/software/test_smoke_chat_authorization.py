"""Offline safety checks for the separate live authorization gate; no E2E substitute."""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def gate(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    path = scripts / "smoke_chat_authorization.py"
    assert path.exists(), "The live delegation authorization gate is missing"
    spec = importlib.util.spec_from_file_location("chat_authorization_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_gate_requires_explicit_disposable_stack_opt_in(gate, monkeypatch):
    monkeypatch.delenv("E2E_DISPOSABLE_STACK", raising=False)
    with pytest.raises(gate.GateFailure, match="E2E_DISPOSABLE_STACK"):
        gate.require_disposable_stack()
    monkeypatch.setenv("E2E_DISPOSABLE_STACK", "1")
    gate.require_disposable_stack()


def test_account_enabled_state_is_restored_after_probe_failure(gate):
    calls = []

    def admin(method, path, body=None):
        calls.append((method, path, body))
        if method == "GET":
            return 200, {"enabled": True}
        return 204, {}

    with pytest.raises(RuntimeError, match="probe failed"):
        with gate.temporarily_disabled(admin, "test-user"):
            raise RuntimeError("probe failed")
    assert calls == [
        ("GET", "/users/test-user", None),
        ("PUT", "/users/test-user", {"enabled": False}),
        ("PUT", "/users/test-user", {"enabled": True}),
        ("GET", "/users/test-user", None),
    ]


def test_expired_input_fixture_selection_requires_real_expired_provenance(gate):
    expired = {
        "universe_id": "OLD_REAL",
        "status": "EXPIRED",
        "reason_code": "INPUT_EXPIRED",
        "data_origin": "real",
        "demo": False,
        "valid_until": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }
    assert gate.select_expired_real([expired | {"demo": True}, expired]) == expired
    for changed in (
        {"demo": True},
        {"data_origin": "unverified"},
        {"status": "READY"},
        {"valid_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
    ):
        with pytest.raises(gate.GateFailure, match="expired real"):
            gate.select_expired_real([expired | changed])
