import copy
import hashlib
import json
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from portfolio_contracts import utcnow
from portfolio_service.api import create_app
from portfolio_service.runtime import QuantResolver
from quant_service.artifacts import ArtifactCatalog
from quant_service.main import create_app as quant_app
from service_auth import Principal
from test_ml_serving import ml_catalog as ml_catalog_fixture, write_bundle
from test_quant import catalog as catalog_fixture
from test_workflow import Verifier, headers, portfolio, stack as stack_fixture

ml_catalog = ml_catalog_fixture
catalog = catalog_fixture
stack = stack_fixture


def strategy_codes(value):
    return {
        s["strategy"]: (s["available"], s["reason_code"]) for s in value["strategies"]
    }


def test_catalog_readiness_explains_missing_model_without_disabling_market_strategies(
    catalog,
):
    store, _ = catalog
    value = store.readiness("DEMO")
    assert value["status"] == "READY"
    assert value["reason_code"] == "READY"
    assert value["next_action"] == "NONE"
    assert value["data_origin"] == "synthetic"
    assert value["asset_ids"] == ["AAA", "BBB", "VFF"]
    assert strategy_codes(value) == {
        "EW": (True, "READY"),
        "MVO": (True, "READY"),
        "BL_ML": (False, "MODEL_UNAVAILABLE"),
    }
    assert set(value) == {
        "universe_id",
        "asset_ids",
        "as_of_date",
        "valid_until",
        "demo",
        "data_origin",
        "status",
        "reason_code",
        "strategies",
        "next_action",
        "checked_at",
    }
    assert value["checked_at"]


def test_latest_expired_is_visible_and_never_falls_back_to_older_ready(catalog):
    store, path = catalog
    original = json.loads((path / "bundle.json").read_text())
    newest = copy.deepcopy(original)
    newest["bundle_id"] = "expired-newest"
    newest["valid_until"] = (utcnow() - timedelta(seconds=1)).isoformat()
    entries = []
    for name, value in (("new.json", newest), ("old.json", original)):
        data = json.dumps(value).encode()
        (path / name).write_bytes(data)
        entries.append(
            {
                "universe_id": "DEMO",
                "file": name,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    (path / "catalog.json").write_text(json.dumps({"bundles": entries}))
    value = store.readiness("DEMO")
    assert value["status"] == "EXPIRED"
    assert value["reason_code"] == "INPUT_EXPIRED"
    assert value["valid_until"] == newest["valid_until"]
    assert value["next_action"] == "REFRESH_DATA"
    assert all(
        code == (False, "INPUT_EXPIRED") for code in strategy_codes(value).values()
    )
    global_values = store.readiness()
    assert len(global_values) == 1
    assert global_values[0]["status"] == "EXPIRED"
    assert store.universes() == []
    with pytest.raises(ValueError):
        store.ready("DEMO", "EW")


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("missing", "MODEL_UNAVAILABLE"),
        ("candidate", "MODEL_UNAVAILABLE"),
        ("corrupt", "MODEL_INVALID"),
        ("future", "MODEL_INVALID"),
        ("invalid_manifest", "MODEL_INVALID"),
    ],
)
def test_readiness_validates_actual_model_and_current_inference_timing(
    ml_catalog, mutation, code
):
    store, path, original, candidate = ml_catalog
    value = copy.deepcopy(original)
    if mutation == "missing":
        (path / value["ml_inference"]["manifest"]["file"]).unlink()
    elif mutation == "candidate":
        value["ml_inference"]["manifest"] = candidate
        value["model_bundle_id"] = candidate["sha256"]
    elif mutation == "corrupt":
        (path / value["ml_inference"]["manifest"]["file"]).write_text(
            "secret=/operator/private"
        )
    elif mutation == "future":
        value["ml_inference"]["feature_date"] = (
            utcnow().date() + timedelta(days=1)
        ).isoformat()
    elif mutation == "invalid_manifest":
        value["ml_inference"] = {"manifest": []}
    write_bundle(path, value)
    result = store.readiness("DEMO")
    assert strategy_codes(result)["BL_ML"] == (False, code)
    assert strategy_codes(result)["MVO"] == (True, "READY")
    assert result["status"] == "READY"
    assert "secret" not in json.dumps(result)
    assert str(path) not in json.dumps(result)


def test_unknown_universe_and_corrupt_latest_do_not_advertise_ready_inputs(catalog):
    store, path = catalog
    unknown = store.readiness("UNKNOWN")
    assert unknown["universe_id"] == "UNKNOWN"
    assert unknown["status"] == "UNAVAILABLE"
    assert unknown["reason_code"] == "INPUT_UNAVAILABLE"
    assert unknown["asset_ids"] == []
    assert unknown["as_of_date"] is None and unknown["valid_until"] is None
    metadata = json.loads((path / "catalog.json").read_text())
    metadata["bundles"][0]["universe_id"] = "DEMO"
    (path / "catalog.json").write_text(json.dumps(metadata))
    (path / "bundle.json").write_text('{"universe_id":"DEMO","secret":"/private/path"}')
    invalid = store.readiness("DEMO")
    assert invalid["reason_code"] == "INPUT_INVALID"
    assert invalid["next_action"] == "CONTACT_OPERATOR"
    assert invalid["asset_ids"] == []
    assert "/private/path" not in json.dumps(invalid)
    assert store.readiness()[0]["reason_code"] == "INPUT_INVALID"


def test_native_approved_model_is_available_and_missing_catalog_is_safe(ml_catalog):
    store, path, _, _ = ml_catalog
    assert strategy_codes(store.readiness("DEMO"))["BL_ML"] == (True, "READY")
    (path / "catalog.json").unlink()
    value = store.readiness("DEMO")
    assert value["status"] == "UNAVAILABLE"
    assert value["reason_code"] == "INPUT_UNAVAILABLE"
    assert all(not item["available"] for item in value["strategies"])
    with pytest.raises(ValueError):
        store.readiness()


def test_global_readiness_hides_demo_without_runtime_opt_in(catalog):
    _, path = catalog
    store = ArtifactCatalog(path)
    assert store.readiness() == []
    assert store.readiness("DEMO")["reason_code"] == "INPUT_INVALID"


def test_malformed_catalog_identity_never_exposes_operator_path(catalog):
    store, path = catalog
    (path / "catalog.json").write_text(
        json.dumps(
            {
                "bundles": [
                    {
                        "universe_id": "/private/operator/credential",
                        "demo": False,
                        "file": "missing.json",
                        "sha256": "a" * 64,
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError):
        store.readiness()


def test_readiness_http_auth_owner_boundary_and_safe_dependency_errors(stack, catalog):
    client, sessions = stack
    pid = portfolio(client)
    store, _ = catalog
    with TestClient(
        create_app(sessions=sessions, verifier=Verifier(), resolver=store)
    ) as client:
        assert client.get("/api/v1/universes/readiness").status_code == 401
        assert client.get(f"/api/v1/portfolios/{pid}/readiness").status_code == 401
        for subject in ("bob", "admin"):
            assert (
                client.get(
                    f"/api/v1/portfolios/{pid}/readiness", headers=headers(subject)
                ).status_code
                == 404
            )
        assert (
            client.get(f"/api/v1/portfolios/{pid}/readiness", headers=headers()).json()[
                "status"
            ]
            == "READY"
        )
        assert (
            client.get("/api/v1/universes/readiness", headers=headers()).json()[0][
                "universe_id"
            ]
            == "DEMO"
        )

    class BrokenResolver:
        def readiness(self, universe_id=None):
            raise httpx.ConnectError("credential=secret private=/operator/path")

    with TestClient(
        create_app(sessions=sessions, verifier=Verifier(), resolver=BrokenResolver())
    ) as client:
        for route in (
            "/api/v1/universes/readiness",
            f"/api/v1/portfolios/{pid}/readiness",
        ):
            response = client.get(route, headers=headers())
            assert response.status_code == 503
            assert "secret" not in response.text and "/operator" not in response.text


def test_quant_readiness_auth_scope_and_optional_universe(catalog):
    store, _ = catalog

    class ServiceVerifier:
        def verify(self, token):
            return Principal(
                "iss",
                token,
                frozenset(),
                frozenset({"quant:resolve"} if token == "alice" else set()),
            )

    with TestClient(
        quant_app(sessions=None, verifier=ServiceVerifier(), catalog=store)
    ) as client:
        route = "/internal/v1/inputs/readiness"
        assert client.get(route).status_code == 401
        assert client.get(route, headers=headers("other")).status_code == 403
        assert client.get(route, headers=headers()).json()[0]["status"] == "READY"
        assert (
            client.get(
                route, params={"universe_id": "UNKNOWN"}, headers=headers()
            ).json()["reason_code"]
            == "INPUT_UNAVAILABLE"
        )


def test_resolver_handles_non_json_dependency_errors(
    monkeypatch,
):
    resolver = QuantResolver()
    resolver.token, resolver.expires = "fixture-token", float("inf")
    monkeypatch.setenv("QUANT_API_URL", "http://quant")

    def unavailable(*args, **kwargs):
        return httpx.Response(
            409, text="private=secret", request=httpx.Request("GET", "http://quant")
        )

    monkeypatch.setattr(httpx, "get", unavailable)
    with pytest.raises(httpx.HTTPStatusError):
        resolver.readiness("DEMO")
