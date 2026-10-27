import copy
import hashlib
import json

import portfolio_core
import pytest

from test_quant import catalog as catalog_fixture

catalog = catalog_fixture


def numerical():
    return {
        "asset_ids": ["AAA", "BBB", "VFF"],
        "mean_returns": [0.001, 0.0005, 0.0001],
        "covariance": [[0.0004, 0, 0], [0, 0.0003, 0], [0, 0, 0.00005]],
    }


INVALID_INPUTS = [
    ("covariance", [[1]]),
    ("covariance", [[1, 1, 0], [0, 1, 0], [0, 0, 1]]),
    ("covariance", [[1, 2, 0], [2, 1, 0], [0, 0, 1]]),
    ("covariance", [[-1, 0, 0], [0, 1, 0], [0, 0, 1]]),
    ("covariance", [[float("inf"), 0, 0], [0, 1, 0], [0, 0, 1]]),
    ("mean_returns", [0.01]),
    ("mean_returns", None),
    ("mean_returns", [0.01, float("nan"), 0.03]),
    ("mean_returns", [0.01, "0.02", 0.03]),
    ("mean_returns", [0.01, True, 0.03]),
    ("asset_ids", ["AAA", "AAA", "VFF"]),
    ("asset_ids", [" AAA", "BBB", "VFF"]),
    ("market_weights", [0.5, 0.5]),
    ("market_weights", [0.4, 0.4, 0.4]),
    ("market_weights", [-0.1, 0.6, 0.5]),
    ("tau", 0),
    ("delta", True),
    ("unsupported_field", [1, 2, 3]),
]


@pytest.mark.parametrize("field,value", INVALID_INPUTS)
def test_public_pure_numerical_validation_rejects_core_invalid_inputs(field, value):
    inputs = numerical() | {field: value}
    with pytest.raises(portfolio_core.CoreError):
        portfolio_core.validate_numerical_inputs(inputs)


@pytest.mark.parametrize("field,value", INVALID_INPUTS)
def test_checksum_consistent_invalid_numerics_disable_all_input_strategies(
    catalog, field, value
):
    store, path = catalog
    bundle = json.loads((path / "bundle.json").read_text())
    bundle["numerical"][field] = value
    # Deliberately preserve a matching checksum: validation must inspect the data.
    raw = json.dumps(bundle).encode()
    (path / "bundle.json").write_bytes(raw)
    (path / "catalog.json").write_text(
        json.dumps(
            {
                "bundles": [
                    {
                        "universe_id": "DEMO",
                        "demo": True,
                        "file": "bundle.json",
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                ]
            }
        )
    )
    value = store.readiness("DEMO")
    assert value["status"] == "UNAVAILABLE"
    assert value["reason_code"] == "INPUT_INVALID"
    assert all(
        not strategy["available"] and strategy["reason_code"] == "INPUT_INVALID"
        for strategy in value["strategies"]
    )
    assert value["asset_ids"] == []


@pytest.mark.parametrize(
    "covariance",
    [
        [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        [[1, 1, 0], [1, 1, 0], [0, 0, 0]],
        [[1, 1.000000001, 0], [1.000000001, 1, 0], [0, 0, 1]],
    ],
)
def test_validation_accepts_covariance_that_core_can_regularize_without_optimizing(
    covariance, monkeypatch
):
    import portfolio_core.allocator as allocator

    def forbidden(*args, **kwargs):
        raise AssertionError("Readiness must not optimize or solve a posterior")

    monkeypatch.setattr(allocator, "_optimize", forbidden)
    monkeypatch.setattr(allocator, "_posterior", forbidden)
    inputs = numerical() | {"covariance": covariance}
    assert portfolio_core.validate_numerical_inputs(inputs) is None
    assert portfolio_core.validate_numerical_inputs(inputs, strategy="EW") is None


def test_model_numerical_requirements_are_strategy_specific():
    inputs = numerical()
    assert portfolio_core.validate_numerical_inputs(inputs, strategy="EW") is None
    assert portfolio_core.validate_numerical_inputs(inputs, strategy="MVO") is None
    with pytest.raises(portfolio_core.CoreError):
        portfolio_core.validate_numerical_inputs(inputs, strategy="BL_ML")
    inputs |= {
        "market_weights": [0.3, 0.3, 0.4],
        "views_p": [[1, 0, 0]],
        "views_q": [0.01],
        "view_confidences": [0.5],
    }
    assert portfolio_core.validate_numerical_inputs(inputs, strategy="BL_ML") is None
    del inputs["market_weights"]
    with pytest.raises(portfolio_core.CoreError):
        portfolio_core.validate_numerical_inputs(inputs, strategy="BL_ML")


def test_invalid_latest_numerics_do_not_fall_back_to_older_valid_bundle(catalog):
    store, path = catalog
    original = json.loads((path / "bundle.json").read_text())
    newest = copy.deepcopy(original)
    newest["bundle_id"] = "invalid-newest"
    newest["numerical"]["covariance"] = [[1]]
    entries = []
    for name, value in (("new.json", newest), ("old.json", original)):
        raw = json.dumps(value).encode()
        (path / name).write_bytes(raw)
        entries.append(
            {
                "universe_id": "DEMO",
                "demo": True,
                "file": name,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    (path / "catalog.json").write_text(json.dumps({"bundles": entries}))
    assert store.readiness("DEMO")["reason_code"] == "INPUT_INVALID"
    values = store.readiness()
    assert len(values) == 1
    assert values[0]["reason_code"] == "INPUT_INVALID"


@pytest.mark.parametrize(
    "newest_demo,allow_demo,expected",
    [
        (True, False, None),
        ("false", True, "INPUT_INVALID"),
        ("false", False, "INPUT_INVALID"),
    ],
)
def test_latest_demo_metadata_cannot_reveal_older_ready_entry(
    catalog, newest_demo, allow_demo, expected
):
    from quant_service.artifacts import ArtifactCatalog

    _, path = catalog
    original = json.loads((path / "bundle.json").read_text())
    original["demo"] = False
    entries = []
    for name, demo in (("new.json", newest_demo), ("old.json", False)):
        value = copy.deepcopy(original)
        value["bundle_id"] = name
        value["demo"] = demo
        raw = json.dumps(value).encode()
        (path / name).write_bytes(raw)
        entries.append(
            {
                "universe_id": "DEMO",
                "demo": demo,
                "file": name,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    (path / "catalog.json").write_text(json.dumps({"bundles": entries}))
    values = ArtifactCatalog(path, allow_demo=allow_demo).readiness()
    if expected is None:
        assert values == []
    else:
        assert len(values) == 1
        assert values[0]["reason_code"] == expected
