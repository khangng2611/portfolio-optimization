"""Refresh fixtures use KBS wire payloads; never substitute a synthetic live source."""

import json
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test_market import market as market_fixture, headers

from portfolio_contracts import utcnow

market = market_fixture

FIRST = utcnow().date() - timedelta(days=4)
SECOND = utcnow().date() - timedelta(days=1)
NOW = utcnow() + timedelta(seconds=1)


@pytest.fixture(autouse=True)
def controlled_enqueue_clock(monkeypatch):
    # API acceptance and worker eligibility share the same deterministic clock,
    # including when this file runs late in the complete software suite.
    from market_service import refresh_api

    monkeypatch.setattr(refresh_api, "utcnow", lambda: NOW - timedelta(seconds=1))


def schedule_body(**changes):
    return {
        "name": "Daily stocks",
        "asset_ids": ["FPT", "HPG"],
        "initial_start_date": FIRST.isoformat(),
        "interval_minutes": 1440,
        "overlap_days": 7,
        "max_age_days": 14,
        "enabled": False,
    } | changes


def create_schedule(market, **changes):
    response = market[0].post(
        "/api/v1/market/refresh-schedules",
        json=schedule_body(**changes),
        headers=headers(key="create"),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_aged_schedule_can_be_disabled_without_changing_pinned_history(
    market, monkeypatch
):
    from market_service import refresh_api, refresh
    from market_service.refresh_provider import completed_cutoff

    first_day = utcnow()
    start = (completed_cutoff(first_day) - timedelta(days=3650)).isoformat()
    schedule = create_schedule(market, initial_start_date=start, enabled=True)
    tomorrow = first_day + timedelta(days=1)
    monkeypatch.setattr(refresh_api, "utcnow", lambda: tomorrow)
    monkeypatch.setattr(refresh, "utcnow", lambda: tomorrow)
    response = market[0].patch(
        f"/api/v1/market/refresh-schedules/{schedule['id']}",
        json={"enabled": False},
        headers=headers(key="disable-aged") | {"If-Match": '"1"'},
    )
    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is False
    assert response.json()["initial_start_date"] == start
    assert response.json()["history_window_expired"] is True
    assert response.json()["version"] == 2
    assert (
        market[0]
        .patch(
            f"/api/v1/market/refresh-schedules/{schedule['id']}",
            json={"enabled": False},
            headers=headers(key="disable-aged") | {"If-Match": '"1"'},
        )
        .json()
        == response.json()
    )
    assert (
        market[0]
        .patch(
            f"/api/v1/market/refresh-schedules/{schedule['id']}",
            json={"enabled": True},
            headers=headers(key="enable-aged") | {"If-Match": '"2"'},
        )
        .status_code
        == 422
    )


def test_timer_expires_aged_history_without_enqueuing_or_moving_start(
    market, monkeypatch
):
    from market_service import refresh
    from market_service.models import RefreshJob, RefreshSchedule
    from market_service.refresh_provider import completed_cutoff
    from sqlalchemy import select

    first_day = utcnow()
    start = (completed_cutoff(first_day) - timedelta(days=3650)).isoformat()
    schedule = create_schedule(market, initial_start_date=start, enabled=True)
    tomorrow = first_day + timedelta(days=1)
    monkeypatch.setattr(refresh, "utcnow", lambda: tomorrow)
    assert refresh.tick(market[1], now=tomorrow) == 0
    assert refresh.tick(market[1], now=tomorrow) == 0
    with market[1]() as session:
        row = session.get(RefreshSchedule, schedule["id"])
        assert row.enabled == 0
        assert row.version == 2
        assert row.config["initial_start_date"] == start
        assert row.config["enabled"] is False
        assert session.scalar(select(RefreshJob)) is None


def test_manual_refresh_rejects_aged_window_before_creating_job(market, monkeypatch):
    from market_service import refresh_api, refresh
    from market_service.models import RefreshJob
    from market_service.refresh_provider import completed_cutoff
    from sqlalchemy import select

    first_day = utcnow()
    start = (completed_cutoff(first_day) - timedelta(days=3650)).isoformat()
    schedule = create_schedule(market, initial_start_date=start)
    tomorrow = first_day + timedelta(days=1)
    monkeypatch.setattr(refresh_api, "utcnow", lambda: tomorrow)
    monkeypatch.setattr(refresh, "utcnow", lambda: tomorrow)
    response = market[0].post(
        "/api/v1/market/refresh-jobs",
        json={"schedule_id": schedule["id"]},
        headers=headers(key="run-aged"),
    )
    assert response.status_code == 409, response.text
    with market[1]() as session:
        assert session.scalar(select(RefreshJob)) is None


def enqueue(market, schedule_id, key="run"):
    response = market[0].post(
        "/api/v1/market/refresh-jobs",
        json={"schedule_id": schedule_id},
        headers=headers(key=key),
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_schedule_receipts_version_conflicts_and_operator_boundary(market):
    client = market[0]
    first = create_schedule(market)
    assert first["version"] == 1
    assert create_schedule(market) == first
    assert (
        client.post(
            "/api/v1/market/refresh-schedules",
            json=schedule_body(name="changed"),
            headers=headers(key="create"),
        ).status_code
        == 409
    )
    patch_headers = headers(key="patch") | {"If-Match": '"1"'}
    updated = client.patch(
        f"/api/v1/market/refresh-schedules/{first['id']}",
        json={"enabled": True},
        headers=patch_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert (
        client.patch(
            f"/api/v1/market/refresh-schedules/{first['id']}",
            json={"enabled": True},
            headers=patch_headers,
        ).json()
        == updated.json()
    )
    assert (
        client.patch(
            f"/api/v1/market/refresh-schedules/{first['id']}",
            json={"enabled": False},
            headers=headers(key="stale") | {"If-Match": '"1"'},
        ).status_code
        == 409
    )
    for route in ["refresh-schedules", "refresh-jobs"]:
        assert (
            client.get(
                "/api/v1/market/" + route, headers=headers("investor")
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/v1/market/" + route, params={"limit": 101}, headers=headers()
            ).status_code
            == 422
        )
    listing = client.get(
        "/api/v1/market/refresh-schedules", headers=headers(), params={"limit": 1}
    )
    assert listing.headers["X-Total-Count"] == "1"
    assert len(listing.json()) == 1
    assert (
        client.post(
            "/api/v1/market/refresh-jobs",
            json={"schedule_id": first["id"]},
            headers=headers("investor", "deny"),
        ).status_code
        == 403
    )


class WireProvider:
    """Only transport is replaced. Real adapter parsing + CSV quality are exercised."""

    def __init__(self, *, fail=False, partial=False):
        self.fail, self.partial, self.calls = fail, partial, []

    def fetch_raw(self, symbol, start, end, *, index=False):
        self.calls.append((symbol, start, end, index))
        if self.fail:
            raise OSError("upstream credentials and private response must not escape")
        dates = [FIRST, SECOND]
        dates = [d for d in dates if start <= d <= end]
        if self.partial and symbol == "HPG":
            dates = dates[:1]
        return json.dumps(
            {
                "data_day": [
                    {"t": d.isoformat() + "T00:00:00", "c": 12500} for d in dates
                ]
            }
        ).encode()


def run(market, provider, now=None):
    from market_service.refresh import run_once

    return run_once(market[1], provider, market[3] / "refresh", now=now or NOW)


def test_source_batch_passes_quality_before_snapshot_and_keeps_full_adjusted_history(
    market,
):
    from market_service.models import (
        RefreshJob,
        RefreshSchedule,
        QualityReport,
        PriceRevision,
        Snapshot,
    )
    from market_service.refresh import enqueue_job

    first = create_schedule(market)
    # Pin cutoff deterministically for the offline replay.
    accepted = enqueue(market, first["id"])
    with market[1].begin() as session:
        job = session.get(RefreshJob, accepted["id"])
        job.cutoff_date = SECOND
    provider = WireProvider()
    assert run(market, provider)
    result = (
        market[0]
        .get(f"/api/v1/market/refresh-jobs/{accepted['id']}", headers=headers())
        .json()
    )
    assert result["status"] == "SUCCEEDED", result
    assert result["snapshot_id"]
    assert result["source_manifest"]["sha256"]
    assert len(result["artifacts"]) == 3
    with market[1]() as session:
        assert session.scalar(select(func.count()).select_from(PriceRevision)) == 4
        snapshot = session.get(Snapshot, result["snapshot_id"])
        assert snapshot.manifest["provider"] == "kbs-direct-v1"
        assert snapshot.manifest["availability_basis"] == "ingestion"
        assert all(
            session.get(QualityReport, i).status == "PASS"
            for i in result["ingestion_job_ids"]
        )
        assert (
            session.get(RefreshSchedule, first["id"]).last_successful_cutoff == SECOND
        )
    assert not run(market, provider)
    with market[1].begin() as session:
        schedule = session.get(RefreshSchedule, first["id"])
        job = enqueue_job(session, schedule, "next-offline", NOW + timedelta(days=1))
        assert (
            job.start_date == FIRST
        )  # adjusted provider always reconciles initial history


def test_partial_batch_never_publishes_prices_or_snapshot(market):
    from market_service.models import RefreshJob, PriceRevision, Snapshot

    first = create_schedule(market)
    accepted = enqueue(market, first["id"])
    with market[1].begin() as session:
        session.get(RefreshJob, accepted["id"]).cutoff_date = SECOND
    run(market, WireProvider(partial=True))
    with market[1]() as session:
        job = session.get(RefreshJob, accepted["id"])
        assert job.status == "FAILED"
        assert job.error["code"] == "QUALITY_REJECTED"
        assert session.scalar(select(func.count()).select_from(PriceRevision)) == 0
        assert session.scalar(select(func.count()).select_from(Snapshot)) == 0


def test_provider_outage_retries_then_recovers_durable_job(market):
    from market_service.models import RefreshJob

    first = create_schedule(market)
    accepted = enqueue(market, first["id"])
    with market[1].begin() as session:
        session.get(RefreshJob, accepted["id"]).cutoff_date = SECOND
    now = NOW
    run(market, WireProvider(fail=True), now)
    with market[1]() as session:
        job = session.get(RefreshJob, accepted["id"])
        assert job.status == "QUEUED"
        assert job.attempts == 1
        assert job.error["code"] == "SOURCE_UNAVAILABLE"
        assert "credentials" not in json.dumps(job.error)
    assert not run(market, WireProvider(), now)
    assert run(market, WireProvider(), now + timedelta(minutes=5))
    with market[1]() as session:
        assert session.get(RefreshJob, accepted["id"]).status == "SUCCEEDED"


def test_duplicate_scheduler_ticks_and_expired_worker_lease(market):
    from market_service.models import RefreshJob, RefreshSchedule
    from market_service.refresh import tick, claim

    first = create_schedule(market, enabled=True)
    now = NOW
    with market[1].begin() as session:
        session.get(RefreshSchedule, first["id"]).next_run_at = now
    assert tick(market[1], now=now) == 1
    assert tick(market[1], now=now) == 0
    lease = claim(market[1], now=now)
    assert lease is not None
    assert claim(market[1], now=now) is None
    resumed = claim(market[1], now=now + timedelta(minutes=11))
    assert resumed.id == lease.id
    assert resumed.lease_token != lease.lease_token
    assert resumed.attempts == 2
    with market[1]() as session:
        assert session.scalar(select(func.count()).select_from(RefreshJob)) == 1


def test_kbs_adapter_rejects_tampered_artifact_and_current_daily_bar(market):
    from market_service.refresh_provider import (
        normalize,
        completed_cutoff,
        ArtifactStore,
    )

    assert completed_cutoff(datetime(2026, 1, 5, 17, 1, tzinfo=timezone.utc)) == date(
        2026, 1, 5
    )
    assert completed_cutoff(datetime(2026, 1, 5, 16, 59, tzinfo=timezone.utc)) == date(
        2026, 1, 4
    )
    with pytest.raises(ValueError):
        normalize(
            json.dumps({"data_day": [{"t": "2026-01-06", "c": 100}]}).encode(),
            "FPT",
            date(2026, 1, 2),
            date(2026, 1, 5),
        )
    store = ArtifactStore(market[3] / "immutable")
    artifact = store.put(b"first", "json")
    store.path(artifact).chmod(0o644)
    store.path(artifact).write_bytes(b"tampered")
    with pytest.raises(ValueError):
        store.read(artifact)


def test_active_manual_job_is_deduplicated_and_pins_schedule_version(market):
    from market_service.models import RefreshJob, RefreshSchedule

    first = create_schedule(market)
    job = enqueue(market, first["id"])
    assert enqueue(market, first["id"]) == job
    assert enqueue(market, first["id"], key="another-run")["id"] == job["id"]
    update = market[0].patch(
        f"/api/v1/market/refresh-schedules/{first['id']}",
        json={"asset_ids": ["VCB"]},
        headers=headers(key="new-assets") | {"If-Match": '"1"'},
    )
    assert update.status_code == 200
    with market[1]() as session:
        assert session.get(RefreshJob, job["id"]).config["asset_ids"] == ["FPT", "HPG"]
        assert session.get(RefreshSchedule, first["id"]).config["asset_ids"] == ["VCB"]


def test_retry_exhaustion_and_deadline_are_terminal(market):
    from market_service.models import RefreshJob

    first = create_schedule(market)
    accepted = enqueue(market, first["id"])
    for attempt in range(3):
        run(market, WireProvider(fail=True), NOW + timedelta(minutes=attempt * 5))
    with market[1]() as session:
        job = session.get(RefreshJob, accepted["id"])
        assert job.status == "FAILED"
        assert job.attempts == 3
        assert job.completed_at
    assert not run(market, WireProvider(), NOW + timedelta(hours=1))


def test_expired_worker_is_fenced_and_network_holds_no_sql_transaction(market):
    from market_service.refresh import claim, fetch_pack, finish
    from market_service.refresh_provider import ArtifactStore
    from market_service.models import RefreshJob, PriceRevision
    from sqlalchemy import event

    first = create_schedule(market)
    accepted = enqueue(market, first["id"])
    with market[1].begin() as session:
        session.get(RefreshJob, accepted["id"]).cutoff_date = SECOND
    active = set()
    engine = market[1].kw["bind"]
    event.listen(engine, "begin", lambda connection: active.add(connection))
    event.listen(engine, "commit", lambda connection: active.discard(connection))
    event.listen(engine, "rollback", lambda connection: active.discard(connection))

    class TransactionAwareSource(WireProvider):
        def fetch_raw(self, *args, **kwargs):
            assert not active, "Source networking must occur outside SQL transactions"
            return super().fetch_raw(*args, **kwargs)

    lease = claim(market[1], now=NOW)
    store = ArtifactStore(market[3] / "refresh")
    artifacts, packs, manifest = fetch_pack(lease, TransactionAwareSource(), store)
    replacement = claim(market[1], now=NOW + timedelta(minutes=11))
    assert replacement.lease_token != lease.lease_token
    assert not finish(
        market[1],
        lease,
        store,
        artifacts,
        packs,
        manifest,
        now=NOW + timedelta(minutes=11),
    )
    with market[1]() as session:
        assert session.scalar(select(func.count()).select_from(PriceRevision)) == 0


def test_refresh_schedule_rejects_unbounded_or_arbitrary_source_inputs(market):
    for changes in [
        {"asset_ids": ["FPT", "FPT"]},
        {"asset_ids": ["https://evil.example"]},
        {"interval_minutes": 1},
        {"overlap_days": 0},
        {"asset_ids": ["A" + str(i) for i in range(21)]},
        {"initial_start_date": utcnow().date().isoformat()},
        {"url": "https://evil.example"},
    ]:
        response = market[0].post(
            "/api/v1/market/refresh-schedules",
            json=schedule_body(**changes),
            headers=headers(key=str(uuid4())),
        )
        assert response.status_code == 422, response.text
    first = create_schedule(market)
    assert (
        market[0]
        .patch(
            f"/api/v1/market/refresh-schedules/{first['id']}",
            json={"enabled": False},
            headers=headers(key="missing-version"),
        )
        .status_code
        == 428
    )


def test_snapshot_provider_filter_preserves_legacy_manifest_when_absent(market):
    from market_service.snapshots import build_snapshot
    from portfolio_contracts.market import SnapshotRequest
    from test_market import submit, observation

    submit(market, {"observations": [observation(provider="original")]})
    body = {
        "asset_ids": ["AAA"],
        "start_date": utcnow().date(),
        "end_date": utcnow().date(),
        "as_of_date": utcnow().date(),
    }
    with market[1].begin() as session:
        old = build_snapshot(session, SnapshotRequest(**body))
        assert "provider" not in old.manifest
        old_hash = old.content_hash
    submit(market, {"observations": [observation(provider="second")]})
    with market[1].begin() as session:
        with pytest.raises(ValueError, match="Ambiguous provider"):
            build_snapshot(session, SnapshotRequest(**body))
        pinned = build_snapshot(session, SnapshotRequest(**body, provider="original"))
        assert pinned.manifest["provider"] == "original"
        assert all(row["provider"] == "original" for row in pinned.observations)
        assert (
            session.get(
                __import__("market_service.models", fromlist=["Snapshot"]).Snapshot,
                old.id,
            ).content_hash
            == old_hash
        )


def test_partial_refresh_exposes_durable_quarantine_and_source_pins(market):
    from market_service.models import RefreshJob, QualityReport

    first = create_schedule(market)
    accepted = enqueue(market, first["id"])
    with market[1].begin() as session:
        session.get(RefreshJob, accepted["id"]).cutoff_date = SECOND
    run(market, WireProvider(partial=True))
    result = (
        market[0]
        .get(f"/api/v1/market/refresh-jobs/{accepted['id']}", headers=headers())
        .json()
    )
    assert len(result["artifacts"]) == 3
    assert result["ingestion_job_ids"]
    with market[1]() as session:
        reports = [
            session.get(QualityReport, i).report for i in result["ingestion_job_ids"]
        ]
        assert all(r["status"] == "QUARANTINED" for r in reports)
        assert any(
            f["code"] == "MISSING_SESSIONS" for r in reports for f in r["findings"]
        )


def test_artifact_write_failure_does_not_poison_immutable_name(market, monkeypatch):
    from market_service.refresh_provider import ArtifactStore
    import os

    store = ArtifactStore(market[3] / "refresh")
    original = os.fsync

    def interrupted(fd):
        raise OSError("simulated disk interruption before publishing")

    monkeypatch.setattr(os, "fsync", interrupted)
    with pytest.raises(OSError):
        store.put(b"provider-byte-pack", "json")
    monkeypatch.setattr(os, "fsync", original)
    artifact = store.put(b"provider-byte-pack", "json")
    assert store.read(artifact) == b"provider-byte-pack"
    assert list(store.directory.iterdir()) == [store.path(artifact)]


def test_worker_cannot_finish_past_job_deadline_even_with_valid_lease(market):
    from market_service.refresh import claim, fetch_pack, finish
    from market_service.refresh_provider import ArtifactStore
    from market_service.models import RefreshJob, PriceRevision

    first = create_schedule(market)
    accepted = enqueue(market, first["id"])
    with market[1].begin() as session:
        row = session.get(RefreshJob, accepted["id"])
        row.deadline = NOW + timedelta(minutes=1)
        row.cutoff_date = SECOND
    lease = claim(market[1], now=NOW)
    store = ArtifactStore(market[3] / "refresh")
    artifacts, packs, manifest = fetch_pack(lease, WireProvider(), store)
    assert not finish(
        market[1],
        lease,
        store,
        artifacts,
        packs,
        manifest,
        now=NOW + timedelta(minutes=2),
    )
    with market[1]() as session:
        assert session.scalar(select(func.count()).select_from(PriceRevision)) == 0


def test_operator_polling_reports_expired_refresh_without_worker(market):
    from market_service.models import RefreshJob

    first = create_schedule(market)
    accepted = enqueue(market, first["id"])
    with market[1].begin() as session:
        row = session.get(RefreshJob, accepted["id"])
        row.deadline = utcnow() - timedelta(seconds=1)
    response = market[0].get(
        f"/api/v1/market/refresh-jobs/{accepted['id']}", headers=headers()
    )
    assert response.json()["status"] == "FAILED"
    assert response.json()["error"]["code"] == "DEADLINE_EXCEEDED"


def test_kbs_transport_uses_verified_fixed_route_and_bounded_response():
    import io
    import requests
    from urllib.parse import parse_qs, urlparse
    from market_service.refresh_provider import KbsProvider

    class FixtureTransport(requests.adapters.BaseAdapter):
        def __init__(self):
            self.requests = []
            self.status = 200
            self.body = b'{"data_day":[{"t":"2026-01-02T00:00:00","c":12500}]}'

        def send(self, request, **kwargs):
            self.requests.append((request, kwargs))
            response = requests.Response()
            response.status_code = self.status
            response.raw = io.BytesIO(self.body)
            response.request = request
            response.url = request.url
            return response

        def close(self):
            pass

    provider, transport = KbsProvider(), FixtureTransport()
    provider.session.mount("https://", transport)
    raw = provider.fetch_raw("FPT", date(2026, 1, 2), date(2026, 1, 5))
    assert raw == transport.body
    request, settings = transport.requests[0]
    parsed = urlparse(request.url)
    assert parsed.netloc == "kbbuddywts.kbsec.com.vn"
    assert parsed.path == "/iis-server/investment/stocks/FPT/data_day"
    assert parse_qs(parsed.query) == {"sdate": ["02-01-2026"], "edate": ["05-01-2026"]}
    assert settings["timeout"] == (5, 15)
    transport.status = 302
    with pytest.raises(OSError, match="Source unavailable"):
        provider.fetch_raw("VNINDEX", date(2026, 1, 2), date(2026, 1, 5), index=True)
    with pytest.raises(ValueError, match="Invalid source symbol"):
        provider.fetch_raw("https://evil.example", date(2026, 1, 2), date(2026, 1, 5))


def test_selected_schedule_can_reload_with_version_etag(market):
    first = create_schedule(market)
    route = f"/api/v1/market/refresh-schedules/{first['id']}"
    response = market[0].get(route, headers=headers())
    assert response.status_code == 200, response.text
    assert response.json() == first
    assert response.headers["ETag"] == '"1"'
    assert market[0].get(route, headers=headers("investor")).status_code == 403
    assert (
        market[0]
        .get(f"/api/v1/market/refresh-schedules/{uuid4()}", headers=headers())
        .status_code
        == 404
    )


def test_adjusted_history_reconciliation_revises_before_overlap_and_preserves_old_snapshot(
    market,
):
    from market_service.models import RefreshJob, Snapshot, PriceRevision, IngestionJob
    from market_service.refresh_provider import ArtifactStore

    initial = SECOND - timedelta(days=30)
    days = [initial + timedelta(days=step) for step in range(0, 31, 3)]

    class AdjustedSource(WireProvider):
        factor = 1

        def fetch_raw(self, symbol, start, end, *, index=False):
            self.calls.append((symbol, start, end, index))
            return json.dumps(
                {
                    "data_day": [
                        {
                            "t": day.isoformat(),
                            "c": (10000 + i * 100) * (1 if index else self.factor),
                        }
                        for i, day in enumerate(days)
                        if start <= day <= end
                    ]
                }
            ).encode()

    schedule = create_schedule(
        market, initial_start_date=initial.isoformat(), overlap_days=7
    )
    assert schedule["refresh_mode"] == "full-adjusted-reconciliation"
    source = AdjustedSource()
    first = enqueue(market, schedule["id"])
    assert run(market, source)
    with market[1]() as session:
        job = session.get(RefreshJob, first["id"])
        original = session.get(Snapshot, job.snapshot_id)
        old_id, old_hash, old_rows = (
            original.id,
            original.content_hash,
            original.observations,
        )
        old_artifacts = job.artifacts
        assert job.status == "SUCCEEDED"
    source.factor = (
        0.5  # Provider restates the complete past series after a corporate action.
    )
    second = enqueue(market, schedule["id"], key="corporate-action")
    assert second["start_date"] == initial.isoformat()
    assert second["refresh_mode"] == "full-adjusted-reconciliation"
    source.calls.clear()
    assert run(market, source)
    assert all(start == initial for _, start, _, _ in source.calls)
    with market[1]() as session:
        job = session.get(RefreshJob, second["id"])
        assert job.status == "SUCCEEDED"
        fresh = session.get(Snapshot, job.snapshot_id)
        assert fresh.id != old_id
        assert session.get(Snapshot, old_id).content_hash == old_hash
        assert session.get(Snapshot, old_id).observations == old_rows
        assert all(
            float(row["price_vnd"]) == float(old["price_vnd"]) / 2
            for row, old in zip(fresh.observations, old_rows)
        )
        assert session.scalar(
            select(func.count()).select_from(PriceRevision)
        ) == 2 * len(old_rows)
        new_id = fresh.id
    store = ArtifactStore(market[3] / "refresh")
    for artifact in old_artifacts:
        assert store.read(artifact["raw"])
        if artifact.get("normalized"):
            assert store.read(artifact["normalized"])
    third = enqueue(market, schedule["id"], key="unchanged-vintage")
    assert run(market, source)
    with market[1]() as session:
        job = session.get(RefreshJob, third["id"])
        assert job.snapshot_id == new_id
        assert all(
            session.get(IngestionJob, i).inserted_count == 0
            for i in job.ingestion_job_ids
        )
        assert session.scalar(
            select(func.count()).select_from(PriceRevision)
        ) == 2 * len(old_rows)


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING"])
@pytest.mark.parametrize("trigger", ["manual", "tick"])
def test_expired_refresh_is_reconciled_before_trigger_dedupe_without_polling(
    market, status, trigger
):
    from market_service.models import RefreshJob, RefreshSchedule
    from market_service.refresh import tick

    schedule = create_schedule(market, enabled=trigger == "tick")
    old = enqueue(market, schedule["id"])
    with market[1].begin() as session:
        job = session.get(RefreshJob, old["id"])
        job.status = status
        job.deadline = NOW - timedelta(minutes=1)
        if status == "RUNNING":
            job.lease_token = str(uuid4())
            job.lease_until = NOW + timedelta(minutes=5)
        session.get(RefreshSchedule, schedule["id"]).next_run_at = NOW - timedelta(
            minutes=1
        )
    if trigger == "manual":
        fresh = enqueue(market, schedule["id"], key="after-deadline")
        assert fresh["id"] != old["id"]
    else:
        assert tick(market[1], now=NOW) == 1
    with market[1]() as session:
        expired = session.get(RefreshJob, old["id"])
        assert expired.status == "FAILED"
        assert expired.error["code"] == "DEADLINE_EXCEEDED"
        assert expired.completed_at
        active = session.scalars(
            select(RefreshJob).where(RefreshJob.status == "QUEUED")
        ).all()
        assert len(active) == 1 and active[0].id != old["id"]
        if trigger == "tick":
            from portfolio_contracts import aware

            assert aware(session.get(RefreshSchedule, schedule["id"]).next_run_at) > NOW


def test_due_tick_does_not_consume_next_interval_for_already_active_manual_job(market):
    from market_service.models import RefreshSchedule
    from market_service.refresh import tick
    from portfolio_contracts import aware

    schedule = create_schedule(market, enabled=True)
    enqueue(market, schedule["id"])
    due = NOW - timedelta(minutes=1)
    with market[1].begin() as session:
        session.get(RefreshSchedule, schedule["id"]).next_run_at = due
    assert tick(market[1], now=NOW) == 0
    with market[1]() as session:
        assert aware(session.get(RefreshSchedule, schedule["id"]).next_run_at) == due


def test_full_reconciliation_refuses_old_rows_missing_from_current_provider_vintage(
    market,
):
    from market_service.models import RefreshJob, Snapshot

    initial = SECOND - timedelta(days=12)

    class RevisedCalendar(WireProvider):
        drop_oldest = False

        def fetch_raw(self, symbol, start, end, *, index=False):
            dates = [initial + timedelta(days=i) for i in range(0, 13, 3)]
            if self.drop_oldest:
                dates = dates[1:]
            return json.dumps(
                {
                    "data_day": [
                        {"t": day.isoformat(), "c": 10000}
                        for day in dates
                        if start <= day <= end
                    ]
                }
            ).encode()

    schedule = create_schedule(market, initial_start_date=initial.isoformat())
    source = RevisedCalendar()
    first = enqueue(market, schedule["id"])
    assert run(market, source)
    source.drop_oldest = True
    second = enqueue(market, schedule["id"], key="removed-historical-bar")
    assert run(market, source)
    with market[1]() as session:
        assert session.get(RefreshJob, first["id"]).status == "SUCCEEDED"
        assert session.get(RefreshJob, second["id"]).status == "FAILED"
        assert session.get(RefreshJob, second["id"]).snapshot_id is None
        assert session.scalar(select(func.count()).select_from(Snapshot)) == 1
