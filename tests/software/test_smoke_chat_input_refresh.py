"""Offline harness guards do not substitute for actual BL_ML acceptance."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def smoke(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/smoke_chat_input_refresh.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("input_refresh_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def facts():
    return {
        "strategy": "BL_ML",
        "requested_strategy": "BL_ML",
        "fallback_reason": None,
        "model_bundle_id": "a" * 64,
        "data_snapshot_id": "snapshot",
        "selection_proof": {"snapshot_hash": "b" * 64},
        "diagnostics": {
            "inference": {
                "manifest_hash": "a" * 64,
                "snapshot_id": "snapshot",
                "snapshot_hash": "b" * 64,
                "model_family": "phase1-asset-ensemble-v5",
            }
        },
    }


def test_native_bl_ml_strategy_is_accepted(smoke):
    smoke.assert_strategy(facts(), "BL_ML")


@pytest.mark.parametrize(
    "change",
    ["fallback", "strategy", "missing_inference", "model_hash", "snapshot_hash"],
)
def test_bl_ml_cannot_be_certified_by_fallback_or_wrong_native_pins(smoke, change):
    value = facts()
    if change == "fallback":
        value["fallback_reason"] = "NO_VALID_ML_VIEWS"
    elif change == "strategy":
        value["strategy"] = "EW"
    elif change == "missing_inference":
        value["diagnostics"] = {}
    else:
        value["diagnostics"]["inference"][
            "manifest_hash" if change == "model_hash" else "snapshot_hash"
        ] = "c" * 64
    from smoke_chat import SmokeFailure

    with pytest.raises(SmokeFailure):
        smoke.assert_strategy(value, "BL_ML")


def test_bl_ml_readiness_is_checked_before_any_chat_mutation(
    smoke, monkeypatch, tmp_path
):
    monkeypatch.setattr(smoke, "login", lambda _: "offline-unit-token")
    monkeypatch.setattr(
        smoke,
        "get",
        lambda base, path, token: {
            "strategies": [
                {"strategy": "MVO", "reason_code": "READY"},
                {"strategy": "BL_ML", "reason_code": "MODEL_EPOCH_MISMATCH"},
            ]
        }
        if path.endswith("readiness")
        else {"id": "portfolio"},
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Blocked BL_ML must not create a Chat conversation")

    monkeypatch.setattr(smoke, "request", forbidden)
    from smoke_chat import SmokeFailure

    with pytest.raises(SmokeFailure, match="BL_ML"):
        smoke.run("fresh", "portfolio", tmp_path / "receipt.json", strategy="BL_ML")


def test_requested_bl_ml_is_sent_explicitly(smoke, monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "login", lambda _: "offline-unit-token")
    monkeypatch.setattr(
        smoke,
        "get",
        lambda base, path, token: {
            "strategies": [
                {"strategy": "MVO", "reason_code": "READY"},
                {"strategy": "BL_ML", "reason_code": "READY"},
            ]
        }
        if path.endswith("readiness")
        else {"id": "portfolio"},
    )
    monkeypatch.setattr(
        smoke, "request", lambda *args, **kwargs: (201, {"id": "conversation"})
    )

    class Sent(Exception):
        pass

    def send(token, cid, body):
        assert body["strategy"] == "BL_ML" and body["intent"] == "allocation"
        assert "fallback_strategy" not in body
        raise Sent()

    monkeypatch.setattr(smoke, "send", send)
    with pytest.raises(Sent):
        smoke.run("fresh", "portfolio", tmp_path / "receipt.json", strategy="BL_ML")
