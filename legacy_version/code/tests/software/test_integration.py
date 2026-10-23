"""Service integration using real core and separate databases; no broker required."""

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from portfolio_contracts import Envelope, utcnow
from portfolio_service.api import create_app
from portfolio_service.models import Base as PortfolioBase, Outbox as PortfolioOutbox
from portfolio_service.workflow import consume_result
from quant_service.artifacts import ArtifactCatalog
from quant_service.models import Base as QuantBase, Outbox as QuantOutbox
from quant_service.workflow import execute
from service_auth import Principal


def test_two_databases_real_solver_and_persisted_recommendation(tmp_path):
    value = {
        "schema_version": 1,
        "bundle_id": "synthetic-v1",
        "universe_id": "DEMO",
        "snapshot_id": "synthetic",
        "model_bundle_id": None,
        "model_status": None,
        "as_of_date": "2026-09-26",
        "valid_until": (utcnow() + timedelta(hours=1)).isoformat(),
        "demo": True,
        "strategies": ["MVO"],
        "numerical": {
            "asset_ids": ["AAA", "BBB", "VFF"],
            "mean_returns": [0.001, 0.0005, 0.0001],
            "covariance": [[0.0004, 0, 0], [0, 0.0003, 0], [0, 0, 0.00005]],
        },
    }
    data = json.dumps(value).encode()
    (tmp_path / "bundle.json").write_bytes(data)
    (tmp_path / "catalog.json").write_text(
        json.dumps(
            {
                "bundles": [
                    {"file": "bundle.json", "sha256": hashlib.sha256(data).hexdigest()}
                ]
            }
        )
    )
    catalog = ArtifactCatalog(tmp_path, allow_demo=True)
    portfolio_engine = create_engine(
        f"sqlite:///{tmp_path}/portfolio.db", connect_args={"check_same_thread": False}
    )
    quant_engine = create_engine(f"sqlite:///{tmp_path}/quant.db")
    PortfolioBase.metadata.create_all(portfolio_engine)
    QuantBase.metadata.create_all(quant_engine)
    portfolio_sessions = sessionmaker(portfolio_engine, expire_on_commit=False)
    quant_sessions = sessionmaker(quant_engine, expire_on_commit=False)

    class Verifier:
        def verify(self, token):
            return Principal(
                "issuer",
                token,
                frozenset({"investor"}),
                frozenset({"portfolio:read", "portfolio:write"}),
            )

    with TestClient(
        create_app(sessions=portfolio_sessions, verifier=Verifier(), resolver=catalog)
    ) as client:
        headers = {"Authorization": "Bearer alice", "Idempotency-Key": str(uuid4())}
        response = client.post(
            "/api/v1/portfolios",
            headers=headers,
            json={
                "name": "Real solver",
                "capital_vnd": "1000000",
                "max_position_weight": 0.5,
            },
        )
        assert response.status_code == 201
        pid = response.json()["id"]
        response = client.post(
            f"/api/v1/portfolios/{pid}/recommendations",
            headers=headers,
            json={"strategy": "MVO"},
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        with portfolio_sessions() as session:
            command = Envelope.model_validate(
                session.scalar(select(PortfolioOutbox)).payload
            )
        execute(quant_sessions, catalog, command)
        with quant_sessions() as session:
            result = Envelope.model_validate(
                session.scalar(select(QuantOutbox)).payload
            )
        consume_result(portfolio_sessions, result)
        # New API instance reads durable state; there is no in-memory job store.
        with TestClient(
            create_app(
                sessions=portfolio_sessions, verifier=Verifier(), resolver=catalog
            )
        ) as restarted:
            state = restarted.get(
                f"/api/v1/jobs/portfolio/{job_id}", headers=headers
            ).json()
            assert state["status"] == "SUCCEEDED", state
            recommendation = restarted.get(
                f"/api/v1/recommendations/{state['recommendation_id']}", headers=headers
            ).json()
            weights = [float(w) for w in recommendation["weights"]]
            assert max(weights) <= 0.5000001
            assert abs(sum(weights) - 1) < 1e-7
            assert recommendation["input_hash"] == command.payload["input_hash"]
            assert recommendation["capital_vnd"] == "1000000.0000"


def test_authorization_requires_both_human_role_and_operation_scope(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/auth.db", connect_args={"check_same_thread": False}
    )
    PortfolioBase.metadata.create_all(engine)
    sessions = sessionmaker(engine)

    class Verifier:
        def verify(self, token):
            if token == "no-role":
                return Principal(
                    "issuer",
                    "u",
                    frozenset(),
                    frozenset({"portfolio:read", "portfolio:write"}),
                )
            return Principal(
                "issuer", "u", frozenset({"investor"}), frozenset({"portfolio:read"})
            )

    with TestClient(
        create_app(sessions=sessions, verifier=Verifier(), resolver=None)
    ) as client:
        assert (
            client.get(
                "/api/v1/portfolios", headers={"Authorization": "Bearer no-role"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/portfolios",
                headers={"Authorization": "Bearer read-only"},
                json={"name": "Denied", "capital_vnd": "100"},
            ).status_code
            == 403
        )
