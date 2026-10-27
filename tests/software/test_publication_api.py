"""Human publication requests persist pins and stay behind worker validation."""

from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from portfolio_contracts import utcnow
from quant_service.main import create_app
from quant_service.models import Base, PublicationJob
from quant_service.publication_worker import PublicationQueue, process_one
from service_auth import AuthError, Principal
from test_snapshot_inputs import snapshot_fixture


PATH = "/api/v1/market/publications"


class Identities:
    def verify(self, token):
        if token == "invalid":
            raise AuthError("private verifier details")
        return Principal(
            "https://identity/portfolio",
            token,
            frozenset({"investor" if token == "investor" else "data-operator"}),
            frozenset({"quant:resolve"} if token == "resolver" else {"quant:publish"}),
        )


def headers(who="operator", key="publish-1"):
    return {"Authorization": f"Bearer {who}", "Idempotency-Key": key}


@pytest.fixture
def api(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'quant.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    client = TestClient(
        create_app(sessions=sessions, verifier=Identities(), catalog=None)
    )
    snapshot, rows, _ = snapshot_fixture()
    pins = {
        "snapshot_id": snapshot["id"],
        "snapshot_hash": snapshot["content_hash"],
        "universe_id": "REAL",
    }
    return client, sessions, pins, snapshot, rows, tmp_path


@pytest.mark.parametrize(
    "method,suffix", [("post", ""), ("get", ""), ("get", "/" + str(uuid4()))]
)
def test_publications_require_human_operator_and_publish_scope(api, method, suffix):
    client, _, pins, *_ = api
    kwargs = {"json": pins} if method == "post" else {}
    for who, status in [
        (None, 401),
        ("invalid", 401),
        ("investor", 403),
        ("resolver", 403),
    ]:
        response = getattr(client, method)(
            PATH + suffix, headers=headers(who) if who else {}, **kwargs
        )
        assert response.status_code == status
        assert response.json()["error"]["code"] in {"UNAUTHENTICATED", "FORBIDDEN"}
        assert "private" not in response.text


def test_enqueue_is_durable_actor_owned_and_idempotent_without_catalog_write(api):
    client, sessions, pins, *_, directory = api
    first = client.post(PATH, json=pins, headers=headers())
    assert first.status_code == 202, first.text
    job = first.json()
    assert job["status"] == "QUEUED" and job["attempts"] == 0
    assert job["request"] == pins | {
        "max_age_days": 7,
        "lookback": 252,
        "min_returns": 60,
    }
    assert job["result"] is None
    assert client.post(PATH, json=pins, headers=headers()).json() == job
    assert (
        client.post(
            PATH, json=pins | {"universe_id": "OTHER"}, headers=headers()
        ).status_code
        == 409
    )
    other = client.post(PATH, json=pins, headers=headers("other-operator"))
    assert other.status_code == 202 and other.json()["job_id"] != job["job_id"]
    assert client.get(job["status_url"], headers=headers()).json() == job
    assert (
        client.get(job["status_url"], headers=headers("other-operator")).status_code
        == 404
    )
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(PublicationJob)) == 2
    restarted = TestClient(
        create_app(sessions=sessions, verifier=Identities(), catalog=None)
    )
    assert restarted.get(job["status_url"], headers=headers()).json() == job
    assert not (directory / "catalog.json").exists()
    assert "idempotency_key" not in job and "lease_token" not in job


@pytest.mark.parametrize(
    "change",
    [
        {"snapshot_id": "latest"},
        {"snapshot_hash": "a" * 63},
        {"snapshot_hash": "A" * 64},
        {"universe_id": "DEMO"},
        {"universe_id": "../REAL"},
        {"model": {"file": "/private/model", "sha256": "a" * 64}},
        {"model": None},
        {"directory": "/tmp/bundles"},
        {"lookback": True},
        {"lookback": 10, "min_returns": 60},
        {"min_returns": 1},
        {"max_age_days": 31},
        {"max_age_days": 366},
    ],
)
def test_untrusted_or_ambiguous_publication_pins_are_rejected(api, change):
    client, sessions, pins, *_ = api
    response = client.post(PATH, json=pins | change, headers=headers())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INPUT"
    assert "/private" not in response.text and "/tmp" not in response.text
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(PublicationJob)) == 0


@pytest.mark.parametrize("key", [None, "", "has space", "x" * 129])
def test_publications_require_bounded_idempotency_header(api, key):
    client, _, pins, *_ = api
    auth = headers()
    if key is None:
        auth.pop("Idempotency-Key")
    else:
        auth["Idempotency-Key"] = key
    assert client.post(PATH, json=pins, headers=auth).status_code == 400


def test_list_paginates_only_owned_jobs_with_exact_filters(api):
    client, sessions, pins, *_ = api
    first = client.post(PATH, json=pins, headers=headers(key="first")).json()
    second = client.post(
        PATH, json=pins | {"snapshot_id": str(uuid4())}, headers=headers(key="second")
    ).json()
    client.post(PATH, json=pins, headers=headers("other-operator"))
    PublicationQueue(sessions).enqueue("cli-job", pins)
    response = client.get(PATH + "?limit=1&offset=1", headers=headers())
    assert response.status_code == 200
    assert [j["job_id"] for j in response.json()] == [first["job_id"]]
    assert response.headers["X-Total-Count"] == "2"
    assert response.headers["X-Limit"] == "1" and response.headers["X-Offset"] == "1"
    assert response.headers["Cache-Control"] == "no-store"
    filtered = client.get(
        PATH + "?snapshot_id=" + second["request"]["snapshot_id"], headers=headers()
    )
    assert [j["job_id"] for j in filtered.json()] == [second["job_id"]]
    assert client.get(PATH + "?status=SUCCEEDED", headers=headers()).json() == []
    for suffix in [
        "?limit=0",
        "?limit=101",
        "?offset=-1",
        "?status=INVALID",
        "/not-a-uuid",
    ]:
        assert client.get(PATH + suffix, headers=headers()).status_code == 422


def test_worker_success_exposes_only_safe_artifact_pins_and_no_model(api):
    client, sessions, pins, snapshot, rows, directory = api
    job = client.post(PATH, json=pins, headers=headers()).json()

    class Reader:
        def load(self, snapshot_id, expected_hash):
            assert snapshot_id == pins["snapshot_id"]
            assert expected_hash == pins["snapshot_hash"]
            return snapshot, rows

    assert process_one(
        PublicationQueue(sessions), directory / "bundles", Reader(), now=utcnow()
    )
    result = client.get(job["status_url"], headers=headers()).json()
    assert result["status"] == "SUCCEEDED" and result["attempts"] == 1
    assert set(result["result"]) == {"bundle_id", "sha256"}
    assert len(result["result"]["sha256"]) == 64
    from quant_service.artifacts import ArtifactCatalog

    catalog = ArtifactCatalog(directory / "bundles")
    assert catalog.ready("REAL", "EW").demo is False
    assert catalog.ready("REAL", "MVO").bundle_id == result["result"]["bundle_id"]
    from portfolio_contracts import ModelUnavailable

    with pytest.raises(ModelUnavailable):
        catalog.ready("REAL", "BL_ML")


def test_worker_rejects_wrong_hash_and_keeps_error_safe(api):
    client, sessions, pins, snapshot, rows, directory = api
    job = client.post(
        PATH, json=pins | {"snapshot_hash": "0" * 64}, headers=headers()
    ).json()

    class Reader:
        def load(self, _snapshot_id, _expected_hash):
            return snapshot, rows

    process_one(
        PublicationQueue(sessions), directory / "bundles", Reader(), now=utcnow()
    )
    result = client.get(job["status_url"], headers=headers()).json()
    assert result["status"] == "FAILED"
    assert result["safe_error"] == "PUBLICATION_INVALID"
    assert not (directory / "bundles/catalog.json").exists()
