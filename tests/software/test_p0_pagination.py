from datetime import timedelta
from uuid import uuid4

import pytest

from portfolio_contracts import utcnow
from portfolio_service.models import AcceptedTarget, Job, Portfolio, Recommendation
from test_workflow import headers, portfolio, stack as stack_fixture

stack = stack_fixture


def test_portfolio_pages_apply_owner_filters_counts_and_stable_orders(stack):
    client, sessions = stack
    ids = []
    for name, capital in (
        ("Alpha", "100"),
        ("Alpha", "200"),
        ("Beta", "300"),
        ("% rate", "400"),
    ):
        result = client.post(
            "/api/v1/portfolios",
            headers=headers(),
            json={"name": name, "capital_vnd": capital},
        )
        ids.append(result.json()["id"])
    client.post(
        "/api/v1/portfolios",
        headers=headers("bob"),
        json={"name": "Alpha", "capital_vnd": "500"},
    )
    stamp = utcnow()
    with sessions.begin() as session:
        for i, pid in enumerate(ids):
            value = session.get(Portfolio, pid)
            value.created_at = stamp
            if i < 2:
                value.risk_profile = {"profile": "balanced"}
    expected = sorted(ids[:2])
    for offset, wanted in ((0, expected[:1]), (1, expected[1:]), (2, [])):
        response = client.get(
            "/api/v1/portfolios",
            headers=headers(),
            params={
                "q": "  ALPHA ",
                "risk_profile": "balanced",
                "sort": "name_asc",
                "limit": 1,
                "offset": offset,
            },
        )
        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == wanted
        assert response.headers["X-Total-Count"] == "2"
        assert response.headers["X-Limit"] == "1"
        assert response.headers["X-Offset"] == str(offset)
    capital = client.get(
        "/api/v1/portfolios",
        headers=headers(),
        params={"sort": "capital_desc", "risk_profile": "manual"},
    )
    assert [item["id"] for item in capital.json()] == [ids[3], ids[2]]
    assert capital.headers["X-Total-Count"] == "2"
    literal = client.get("/api/v1/portfolios", headers=headers(), params={"q": "%"})
    assert [item["id"] for item in literal.json()] == [ids[3]]
    default = client.get("/api/v1/portfolios", headers=headers())
    assert [item["id"] for item in default.json()] == sorted(ids)
    assert default.headers["X-Total-Count"] == "4"
    assert default.headers["X-Limit"] == "100"
    other = client.get("/api/v1/portfolios", headers=headers("admin"))
    assert other.json() == [] and other.headers["X-Total-Count"] == "0"


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": 1000001},
        {"q": "x" * 121},
        {"risk_profile": "admin"},
        {"sort": "private"},
    ],
)
def test_invalid_portfolio_paging_queries_are_rejected(stack, params):
    client, _ = stack
    assert (
        client.get("/api/v1/portfolios", headers=headers(), params=params).status_code
        == 422
    )


def test_search_length_is_validated_after_trimming(stack):
    client, _ = stack
    response = client.get(
        "/api/v1/portfolios", headers=headers(), params={"q": " " * 121}
    )
    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["X-Total-Count"] == "0"


def test_history_pages_are_owner_scoped_stable_and_counted(stack):
    client, sessions = stack
    pid = portfolio(client)
    stamp = utcnow()
    rec_ids = sorted(str(uuid4()) for _ in range(3))
    with sessions.begin() as session:
        owner = session.get(Portfolio, pid).owner_user_id
        for index, rid in enumerate(rec_ids):
            job = Job(
                id=str(uuid4()),
                owner_user_id=owner,
                portfolio_id=pid,
                idempotency_key=str(index),
                body_hash="a" * 64,
                input_hash="b" * 64,
                input={},
                deadline=stamp + timedelta(hours=1),
            )
            session.add(job)
            session.flush()
            session.add(
                Recommendation(
                    id=rid,
                    job_id=job.id,
                    owner_user_id=owner,
                    portfolio_id=pid,
                    run_id=str(uuid4()),
                    result={"weights": [0.5, 0.5]},
                    created_at=stamp,
                )
            )
            session.flush()
            session.add(
                AcceptedTarget(
                    id=str(uuid4()),
                    recommendation_id=rid,
                    portfolio_id=pid,
                    owner_user_id=owner,
                    portfolio_version=index + 2,
                    allocation={"weights": [0.5, 0.5]},
                    # Acceptance version remains authoritative if host clocks skew.
                    accepted_at=stamp - timedelta(minutes=index),
                )
            )
    for suffix in ("recommendations", "targets"):
        route = f"/api/v1/portfolios/{pid}/{suffix}"
        for subject in ("bob", "admin"):
            assert client.get(route, headers=headers(subject)).status_code == 404
        response = client.get(
            route, headers=headers(), params={"limit": 1, "offset": 1}
        )
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.headers["X-Total-Count"] == "3"
        assert (
            response.headers["X-Limit"] == "1" and response.headers["X-Offset"] == "1"
        )
        page = client.get(route, headers=headers(), params={"limit": 100}).json()
        if suffix == "recommendations":
            assert [row["id"] for row in page] == rec_ids
        else:
            assert [row["portfolio_version"] for row in page] == [4, 3, 2]
        assert response.json()[0] == page[1]
        assert (
            client.get(route, headers=headers(), params={"limit": 101}).status_code
            == 422
        )
        assert (
            client.get(route, headers=headers(), params={"offset": -1}).status_code
            == 422
        )
