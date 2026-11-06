
from fastapi.testclient import TestClient

from portfolio_contracts import utcnow
from service_auth import Principal
from market_service.api import create_app
from test_market import market as market_fixture, headers, observation, submit

market = market_fixture


def test_snapshot_preserves_origin_and_correction_without_rewriting_old_snapshot(
    market,
):
    client, *_ = market
    submit(
        market,
        {
            "observations": [
                observation(data_origin="real", price_basis="provider_adjusted")
            ]
        },
    )
    day = utcnow().date().isoformat()
    request = {
        "asset_ids": ["AAA"],
        "start_date": day,
        "end_date": day,
        "as_of_date": day,
    }
    first = client.post("/api/v1/market/snapshots", headers=headers(), json=request)
    assert first.status_code == 201, first.text
    first = first.json()
    assert first["data_origin"] == "real"
    rows = client.get(
        f"/api/v1/market/snapshots/{first['id']}/observations", headers=headers()
    ).json()
    assert rows[0]["price_basis"] == "provider_adjusted"
    # Identical price with different attestation must append, not silently relabel history.
    submit(
        market,
        {
            "observations": [
                observation(data_origin="synthetic", price_basis="raw_close")
            ]
        },
    )
    second = client.post(
        "/api/v1/market/snapshots", headers=headers(), json=request
    ).json()
    assert second["id"] != first["id"]
    assert second["data_origin"] == "synthetic"
    assert (
        client.get(f"/api/v1/market/snapshots/{first['id']}", headers=headers()).json()[
            "data_origin"
        ]
        == "real"
    )


def test_unknown_legacy_input_never_becomes_real(market):
    client, *_ = market
    submit(market)
    day = utcnow().date().isoformat()
    result = client.post(
        "/api/v1/market/snapshots",
        headers=headers(),
        json={
            "asset_ids": ["AAA"],
            "start_date": day,
            "end_date": day,
            "as_of_date": day,
        },
    ).json()
    assert result["data_origin"] == "unverified"


def test_internal_snapshot_reads_require_separate_service_scope(market):
    client, sessions, provider, _ = market
    submit(market)
    day = utcnow().date().isoformat()
    snap = client.post(
        "/api/v1/market/snapshots",
        headers=headers(),
        json={
            "asset_ids": ["AAA"],
            "start_date": day,
            "end_date": day,
            "as_of_date": day,
        },
    ).json()

    class Verifier:
        def verify(self, token):
            return Principal(
                "issuer",
                token,
                frozenset(),
                frozenset(
                    {"market:snapshot:read"}
                    if token == "publisher"
                    else {"market:read"}
                ),
            )

    with TestClient(
        create_app(sessions=sessions, verifier=Verifier(), provider=provider)
    ) as service:
        for suffix in ["", "/observations"]:
            path = f"/internal/v1/market/snapshots/{snap['id']}{suffix}"
            assert service.get(path).status_code == 401
            assert service.get(path, headers=headers("human")).status_code == 403
            assert service.get(path, headers=headers("publisher")).status_code == 200
        assert (
            service.get(
                "/api/v1/market/assets", headers=headers("publisher")
            ).status_code
            == 403
        )
