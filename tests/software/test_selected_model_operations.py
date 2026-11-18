from pathlib import Path

import httpx
import pytest

from portfolio_contracts import canonical_hash
from ml_platform.contracts import TrainingRequest
from ml_platform.queue import validate_request
from ml_platform.worker import TrainingQueue, process_one, materialize_approvals
from quant_service.publication_api import (
    CredentialModelResolver,
    ModelResolutionUnavailable,
)
import test_model_operations
from test_model_operations import headers, PATH

ml = test_model_operations.ml


def test_v5_family_preserves_legacy_enqueue_hash(ml):
    client, sessions, directory, pins, *_ = ml
    legacy = TrainingRequest.model_validate(pins).model_dump(mode="json")
    assert "model_family" not in legacy
    assert validate_request(pins | {"model_family": None}) == legacy
    queue = TrainingQueue(sessions)
    first = queue.enqueue("old-intent", pins)
    assert first.body_hash == canonical_hash({"request": legacy, "max_attempts": 5})
    assert queue.enqueue("old-intent", pins | {"model_family": None}).id == first.id
    new = queue.enqueue(
        "new-intent", pins | {"model_family": "phase1-asset-ensemble-v5"}
    )
    assert new.request["model_family"] == "phase1-asset-ensemble-v5"
    assert new.body_hash != first.body_hash


def test_v5_review_and_nested_resolver(ml, monkeypatch):
    from quant_service.selection_panel import SelectionPanel
    from ml_platform.selected_train import fit_state
    from test_selection_panel import fixture

    client, sessions, directory, *_ = ml
    snapshot, rows, now = fixture(170)
    panel = SelectionPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    state = fit_state(panel)
    pins = dict(
        snapshot_id=snapshot["id"],
        snapshot_hash=snapshot["content_hash"],
        training_cutoff=str(state["training_cutoff"]),
        model_family="phase1-asset-ensemble-v5",
    )

    class Reader:
        def load(self, identity, digest):
            assert identity == snapshot["id"] and digest == snapshot["content_hash"]
            return snapshot, rows

    response = client.post(
        PATH + "/training-jobs", json=pins, headers=headers(key="v5-intent")
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert (
        client.post(
            PATH + "/training-jobs", json=pins, headers=headers(key="v5-intent")
        ).json()
        == job
    )
    assert process_one(TrainingQueue(sessions), directory, Reader())
    result = client.get(job["status_url"], headers=headers()).json()
    assert result["status"] == "SUCCEEDED", result
    model_id = result["result"]["model_id"]
    model = client.get(PATH + "/models/" + model_id, headers=headers()).json()
    assert model["metadata"]["schema_version"] == 5
    assert model["metadata"]["covered_asset_ids"] == list(panel.ids[:30])
    assert model["metadata"]["ensemble_count"] == 30
    assert model["metadata"]["native_member_count"] == 150
    route = "/internal/v1/ml/models/" + model_id + "/manifest"
    assert client.get(route, headers=headers("reader")).status_code == 409
    review_path = PATH + "/models/" + model_id + "/reviews"
    body = {
        "decision": "APPROVED",
        "reason": "Verified per-asset native coverage and purge",
    }
    assert (
        client.post(
            review_path, json=body, headers=headers("reviewer", key="review-v5")
        ).status_code
        == 428
    )
    approved = client.post(
        review_path,
        json=body,
        headers=headers("reviewer", key="review-v5", version=model["version"]),
    )
    assert approved.status_code == 200, approved.text
    assert materialize_approvals(sessions, directory) == 1
    reference = client.get(route, headers=headers("reader")).json()["manifest"]
    assert len(Path(reference["file"]).parts) == 4
    original_client = httpx.Client
    tamper = {}

    def service(request):
        if request.url.host == "token":
            return httpx.Response(200, json={"access_token": "scoped-test-token"})
        response = client.get(request.url.path, headers=headers("reader"))
        value = response.json()
        if tamper.get("other_model"):
            value["model_id"] = "e376079c-3ff5-4160-ae84-9e6708152591"
        if tamper.get("path"):
            value["manifest"]["file"] = (
                "ml-models/00000000-0000-0000-0000-000000000000/phase1-other/manifest.json"
            )
        return httpx.Response(response.status_code, json=value)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(service)),
    )
    monkeypatch.setenv("OIDC_TOKEN_URL", "https://token/token")
    monkeypatch.setenv("ML_API_URL", "https://ml")
    monkeypatch.setenv("ML_READER_CLIENT_SECRET", "test-fixture-secret")
    assert CredentialModelResolver().resolve(model_id) == reference
    for kind in ("other_model", "path"):
        tamper[kind] = True
        with pytest.raises(ModelResolutionUnavailable):
            CredentialModelResolver().resolve(model_id)
        tamper.clear()
    native = next((directory / job["job_id"]).rglob("*.ubj"))
    old = native.read_bytes()
    try:
        native.write_bytes(old + b"tampered")
        with pytest.raises(ModelResolutionUnavailable):
            CredentialModelResolver().resolve(model_id)
    finally:
        native.write_bytes(old)
