from datetime import date, datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from market_service.models import Base, IngestionJob, PriceRevision, QualityReport
from market_service.refresh_provider import ArtifactStore
from market_service.selected_refresh import refresh_selected
from market_service.selected_snapshots import build_selected_snapshot
from market_service.snapshots import snapshot_json

NOW = datetime(2026, 11, 12, 8, tzinfo=timezone.utc)
END = date(2026, 11, 11)
# Frozen source dates do not backdate rows inserted by the real ORM clock.
TODAY = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
AUDIT = (
    Path(__file__).resolve().parents[2] / "outputs/step1/source-audit-20261111T230659"
)


@pytest.fixture
def owner(tmp_path, monkeypatch):
    monkeypatch.setenv("DATASET_DIRECTORY", str(tmp_path))
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False), ArtifactStore(
        tmp_path / "refresh" / "selected"
    )


class Kbs:
    def fetch_raw(self, symbol, start, end, index=False):
        days = (
            ["2020-01-02", "2020-01-14", str(END)]
            if index
            else ["2020-01-14", str(END)]
        )
        return json.dumps(
            {
                "symbol": symbol,
                "data_day": [{"t": day, "c": "12345.123456"} for day in days],
            }
        ).encode()


class Vff:
    def __init__(self, failure=None):
        self.failure = failure

    def fetch(self, url, payload=None):
        if self.failure:
            raise self.failure
        name = "fmarket-identity.json" if "/filter" in url else "fmarket-nav.json"
        return (AUDIT / name).read_bytes(), {
            "url": url,
            "requested_at": NOW.isoformat(),
            "received_at": NOW.isoformat(),
            "payload": payload,
        }


def test_vff_failure_does_not_abort_stock_refresh(owner):
    sessions, store = owner
    result = refresh_selected(
        ["VFF", "FPT"],
        END,
        store,
        sessions=sessions,
        kbs=Kbs(),
        mixed=Vff(OSError("source unavailable")),
        now=NOW,
    )
    assert result["asset_receipts"]["FPT"]["status"] == "AVAILABLE"
    assert result["asset_receipts"]["VFF"]["status"] == "MISSING"
    with sessions() as session:
        assert {r.asset_id for r in session.scalars(select(PriceRevision))} == {"FPT"}
        assert {r.status for r in session.scalars(select(QualityReport))} == {
            "PASS",
            "NOT_CHECKED",
        }
    with sessions.begin() as session:
        snapshot = build_selected_snapshot(
            session,
            ["FPT", "VFF"],
            result["calendar_sessions"],
            TODAY,
            directory=store.directory.parent.parent,
        )
        value = snapshot_json(snapshot)
        assert value["schema_version"] == 3
        assert len(value["asset_ids"]) == 32
        assert value["quality_status"] == "PER_ASSET"
        assert value["asset_coverage"]["FPT"]["status"] == "AVAILABLE"
        assert value["asset_coverage"]["VFF"]["status"] == "MISSING"
        assert value["asset_coverage"]["GOLD"]["status"] == "MISSING"
        assert {r["asset_id"] for r in snapshot.observations} == {"FPT"}
        assert snapshot.observations[0]["availability_basis"] == "ingestion"
        assert snapshot.observations[0]["ingested_at"][:10] >= "2026-11-12"


def test_vff_metadata_is_hash_pinned_and_snapshot_rejects_tampering(owner):
    sessions, store = owner
    result = refresh_selected(
        ["VFF"], END, store, sessions=sessions, kbs=Kbs(), mixed=Vff(), now=NOW
    )
    receipt = result["asset_receipts"]["VFF"]
    assert receipt["status"] == "AVAILABLE"
    with sessions.begin() as session:
        snapshot = build_selected_snapshot(
            session,
            ["VFF"],
            result["calendar_sessions"],
            TODAY,
            directory=store.directory.parent.parent,
        )
        row = snapshot.observations[-1]
        assert row["price_vnd"] == "27249.210000"
        assert row["source_metadata"]["product_id"] == 21
        assert (
            row["source_metadata"]["provider_record_created_at"]
            == "2026-11-10T09:53:54.847000+00:00"
        )
        assert row["published_at"] is None
    path = store.directory.parent.parent / receipt["source_metadata_ref"]["path"]
    path.chmod(0o644)
    path.write_bytes(b'{"tampered":true}')
    with sessions.begin() as session:
        snapshot = build_selected_snapshot(
            session,
            ["VFF"],
            result["calendar_sessions"],
            TODAY,
            directory=store.directory.parent.parent,
        )
        assert snapshot.manifest["asset_coverage"]["VFF"]["status"] == "QUARANTINED"
        assert not snapshot.observations
    with sessions() as session:
        assert list(session.scalars(select(PriceRevision)))


def test_wrong_vff_identity_quarantines_only_that_asset(owner):
    class WrongVff(Vff):
        def fetch(self, url, payload=None):
            raw, ref = super().fetch(url, payload)
            if "/get-nav-history" in url:
                value = json.loads(raw)
                value["data"][0]["productId"] = 22
                raw = json.dumps(value).encode()
            return raw, ref

    sessions, store = owner
    result = refresh_selected(
        ["FPT", "VFF"],
        END,
        store,
        sessions=sessions,
        kbs=Kbs(),
        mixed=WrongVff(),
        now=NOW,
    )
    assert result["asset_receipts"]["FPT"]["status"] == "AVAILABLE"
    assert result["asset_receipts"]["VFF"]["status"] == "QUARANTINED"
    with sessions() as session:
        assert {r.asset_id for r in session.scalars(select(PriceRevision))} == {"FPT"}
        assert session.scalar(
            select(IngestionJob).where(IngestionJob.status == "FAILED")
        )


def test_selected_refresh_rejects_unknown_and_future_cutoff_before_source_io(owner):
    sessions, store = owner
    with pytest.raises(ValueError):
        refresh_selected(
            ["DEMO_STOCK"],
            END,
            store,
            sessions=sessions,
            kbs=Kbs(),
            mixed=Vff(),
            now=NOW,
        )
    with pytest.raises(ValueError):
        refresh_selected(
            ["FPT"],
            date(2026, 11, 13),
            store,
            sessions=sessions,
            kbs=Kbs(),
            mixed=Vff(),
            now=NOW,
        )


def test_selected_snapshot_api_is_operator_only_and_keeps_legacy_gets(owner):
    from fastapi.testclient import TestClient
    from market_service.api import create_app
    from market_service.providers import CsvProvider
    from service_auth import Principal

    class Identities:
        def verify(self, token):
            return Principal(
                "issuer",
                token,
                frozenset({"data-operator" if token == "operator" else "investor"}),
                frozenset({"market:read", "market:write"}),
            )

    sessions, store = owner
    root = store.directory.parent.parent
    refresh_selected(
        ["FPT"], END, store, sessions=sessions, kbs=Kbs(), mixed=Vff(), now=NOW
    )
    (root / "catalog.json").write_text("{}")
    client = TestClient(
        create_app(sessions=sessions, verifier=Identities(), provider=CsvProvider(root))
    )
    route = "/api/v1/market/selected-snapshots"
    assert (
        client.post(
            route, json={}, headers={"Authorization": "Bearer investor"}
        ).status_code
        == 403
    )
    response = client.post(route, json={}, headers={"Authorization": "Bearer operator"})
    assert response.status_code == 201, response.text
    snapshot = response.json()
    assert snapshot["schema_version"] == 3
    fetched = client.get(
        "/api/v1/market/snapshots/" + snapshot["id"],
        headers={"Authorization": "Bearer investor"},
    )
    assert fetched.json() == snapshot
    assert (
        client.get(
            "/api/v1/market/snapshots/" + snapshot["id"] + "/observations",
            headers={"Authorization": "Bearer investor"},
        ).json()[0]["asset_id"]
        == "FPT"
    )


def test_calendar_hash_tampering_quarantines_that_source(owner):
    sessions, store = owner
    result = refresh_selected(
        ["FPT"], END, store, sessions=sessions, kbs=Kbs(), mixed=Vff(), now=NOW
    )
    root = store.directory.parent.parent
    calendar = root / result["calendar_source"]["raw"]["path"]
    calendar.chmod(0o644)
    calendar.write_bytes(b'{"wrong":true}')
    with sessions.begin() as session:
        snapshot = build_selected_snapshot(
            session, ["FPT"], result["calendar_sessions"], TODAY, directory=root
        )
        assert snapshot.manifest["asset_coverage"]["FPT"]["status"] == "QUARANTINED"
        assert not snapshot.observations


def test_selected_equity_gaps_keep_only_native_observations(owner):
    class GapKbs:
        def fetch_raw(self, symbol, start, end, index=False):
            days = (
                [
                    "2020-12-01",
                    "2020-12-02",
                    "2020-12-03",
                    "2020-12-04",
                    "2020-12-07",
                    "2020-12-08",
                    "2020-12-09",
                ]
                if index
                else ["2020-12-01", "2020-12-09"]
            )
            return json.dumps(
                {"symbol": symbol, "data_day": [{"t": d, "c": 8832} for d in days]}
            ).encode()

    sessions, store = owner
    result = refresh_selected(
        ["ACB", "BID"],
        END,
        store,
        sessions=sessions,
        kbs=GapKbs(),
        mixed=Vff(),
        now=NOW,
    )
    assert result["asset_receipts"]["ACB"]["status"] == "AVAILABLE"
    assert result["asset_receipts"]["BID"]["status"] == "QUARANTINED"
    with sessions.begin() as session:
        snapshot = build_selected_snapshot(
            session,
            ["ACB", "BID"],
            result["calendar_sessions"],
            TODAY,
            directory=store.directory.parent.parent,
        )
        assert len(snapshot.observations) == 2
        assert snapshot.manifest["equity_missing_sessions"]["ACB"] == [
            "2020-12-02",
            "2020-12-03",
            "2020-12-04",
            "2020-12-07",
            "2020-12-08",
        ]
        assert snapshot.manifest["max_age_days"] == 7


def test_gold_uses_frozen_seed_archive_carry_and_metadata_pins(owner):
    from market_service.phase1_full import ASSETS_SEED_HASH
    from market_service.phase1_sources import GOLD_SEED_HASH

    sessions, store = owner
    baseline = AUDIT.parent / "readiness_20261012"
    for source in [
        baseline / "gold_archive_daily.csv",
        baseline
        / "runs/availability-observed-contract-20261012T233110/source_snapshot/assets_1.json",
    ]:
        (store.directory / source.name).write_bytes(source.read_bytes())
    seed = store.directory / "seed.json"
    seed.write_text(
        json.dumps(
            {
                "assets": {"file": "assets_1.json", "sha256": ASSETS_SEED_HASH},
                "gold": {"file": "gold_archive_daily.csv", "sha256": GOLD_SEED_HASH},
            }
        )
    )

    class Gold:
        def fetch(self, url, payload=None):
            year, month = url.split("/")[-2:]
            return (AUDIT / f"gold-{year}-{int(month):02}.html").read_bytes(), {
                "url": url,
                "requested_at": NOW.isoformat(),
                "received_at": NOW.isoformat(),
            }

    result = refresh_selected(
        ["GOLD"],
        END,
        store,
        sessions=sessions,
        kbs=Kbs(),
        mixed=Gold(),
        seed=seed,
        now=NOW,
    )
    assert result["asset_receipts"]["GOLD"]["status"] == "AVAILABLE"
    with sessions.begin() as session:
        snapshot = build_selected_snapshot(
            session,
            ["GOLD"],
            result["calendar_sessions"],
            TODAY,
            directory=store.directory.parent.parent,
        )
        assert snapshot.observations[-1]["price_vnd"] == "140000000.000000"
        assert snapshot.observations[0]["observation_date"] == "2019-12-01"
        assert any(
            r["source_metadata"]["provider_carry_flag"] for r in snapshot.observations
        )
        job = session.scalar(select(IngestionJob))
        report = session.get(QualityReport, job.id)
        assert (
            job.input["dataset_spec"]["source_metadata_ref"]
            == report.report["source_metadata_ref"]
        )


def test_invalid_normalized_hash_never_writes_revision(owner):
    class CorruptStore(ArtifactStore):
        def put(self, raw, suffix):
            ref = super().put(raw, suffix)
            return ref | {"sha256": "0" * 64} if suffix == "csv" else ref

    sessions, original = owner
    store = CorruptStore(original.directory)
    result = refresh_selected(
        ["FPT"], END, store, sessions=sessions, kbs=Kbs(), mixed=Vff(), now=NOW
    )
    assert result["asset_receipts"]["FPT"]["status"] == "QUARANTINED"
    with sessions() as session:
        assert session.scalar(select(PriceRevision)) is None
        report = session.scalar(select(QualityReport))
        assert report.report["findings"][0]["code"] == "CHECKSUM_MISMATCH"


def test_schema2_metadata_can_supply_unrefreshed_assets_without_http(owner):
    from portfolio_contracts import canonical_hash
    from market_service.models import Snapshot

    sessions, store = owner
    result = refresh_selected(
        ["FPT", "VFF"], END, store, sessions=sessions, kbs=Kbs(), mixed=Vff(), now=NOW
    )
    root = store.directory.parent.parent
    with sessions.begin() as session:
        current = build_selected_snapshot(
            session, ["FPT"], result["calendar_sessions"], TODAY, directory=root
        )
        old_manifest = dict(
            current.manifest,
            schema_version=2,
            universe_id="VN_PHASE1_FULL",
            quality_status="PASS",
            availability_policy="phase1-full-v1",
        )
        legacy = Snapshot(
            content_hash=canonical_hash(old_manifest),
            manifest=old_manifest,
            observations=current.observations,
        )
        session.add(legacy)
        for job in session.scalars(select(IngestionJob)):
            job.input = dict(job.input, source_family="legacy-full-source")
    with sessions.begin() as session:
        snapshot = build_selected_snapshot(
            session, ["FPT"], result["calendar_sessions"], TODAY, directory=root
        )
        assert snapshot.manifest["asset_coverage"]["VFF"]["status"] == "AVAILABLE"
        assert (
            snapshot.manifest["asset_coverage"]["VFF"]["source_metadata_ref"]["kind"]
            == "market-snapshot"
        )
        assert [r for r in snapshot.observations if r["asset_id"] == "VFF"][-1][
            "source_metadata"
        ]["product_id"] == 21
    with sessions.begin() as session:
        legacy = session.get(Snapshot, legacy.id)
        legacy.observations = [dict(legacy.observations[0], price_vnd="999999")]
    with sessions.begin() as session:
        snapshot = build_selected_snapshot(
            session, ["FPT"], result["calendar_sessions"], TODAY, directory=root
        )
        assert snapshot.manifest["asset_coverage"]["VFF"]["status"] == "MISSING"
        assert not snapshot.observations


def test_postgres_selected_source_date_bind():
    """Opt-in backend check executes the production read path in a read-only transaction."""
    import os
    from sqlalchemy import text
    from portfolio_contracts import utcnow
    from market_service.selected_snapshots import _accepted_rows, latest_selected_jobs

    url = os.environ.get("MARKET_SELECTED_DATABASE_URL")
    directory = os.environ.get("MARKET_SELECTED_DATASET_DIRECTORY")
    if not url or not directory:
        pytest.skip(
            "Set MARKET_SELECTED_DATABASE_URL and MARKET_SELECTED_DATASET_DIRECTORY for PostgreSQL source verification"
        )
    engine = create_engine(url)
    assert engine.dialect.name == "postgresql", "This check requires real PostgreSQL"
    with sessionmaker(engine)() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        jobs = latest_selected_jobs(session)
        accepted = [job for job in jobs.values() if job.status == "SUCCEEDED"]
        if not accepted:
            pytest.skip(
                "Refresh one selected source before the PostgreSQL read-path check"
            )
        job = accepted[0]
        report = session.get(QualityReport, job.id)
        rows, metadata, ref = _accepted_rows(
            session,
            job.input["selected_asset_id"],
            job,
            report,
            Path(directory),
            utcnow(),
        )
        assert rows and metadata["asset_id"] == job.input["selected_asset_id"]
        assert ref == report.report["source_metadata_ref"]


def test_historical_snapshot_ignores_later_selected_jobs_without_backdating(owner):
    from portfolio_contracts import canonical_hash
    from market_service.models import Snapshot
    from market_service.selected_snapshots import latest_selected_jobs

    sessions, store = owner
    result = refresh_selected(
        ["FPT"], END, store, sessions=sessions, kbs=Kbs(), mixed=Vff(), now=NOW
    )
    root = store.directory.parent.parent
    old_known = "2026-11-11T16:00:00+00:00"
    cutoff = datetime(2026, 11, 11, 16, 59, 59, 999999, tzinfo=timezone.utc)
    with sessions.begin() as session:
        current = build_selected_snapshot(
            session, ["FPT"], result["calendar_sessions"], TODAY, directory=root
        )
        original_times = [
            (r.id, r.available_at, r.ingested_at)
            for r in session.scalars(select(PriceRevision))
        ]
        old_rows = [
            dict(
                row,
                available_at=old_known,
                ingested_at=old_known,
                price_vnd="9000.000000",
            )
            for row in current.observations
        ]
        old_manifest = dict(
            current.manifest,
            schema_version=2,
            universe_id="VN_PHASE1_FULL",
            quality_status="PASS",
            availability_policy="phase1-full-v1",
            observation_hash=canonical_hash({"observations": old_rows}),
        )
        legacy = Snapshot(
            content_hash=canonical_hash(old_manifest),
            manifest=old_manifest,
            observations=old_rows,
        )
        session.add(legacy)
    with sessions.begin() as session:
        assert "FPT" not in latest_selected_jobs(session, knowledge_cutoff=cutoff)
        historical = build_selected_snapshot(
            session, ["FPT"], result["calendar_sessions"], END, directory=root
        )
        assert historical.manifest["asset_coverage"]["FPT"]["status"] == "AVAILABLE"
        assert (
            historical.manifest["asset_coverage"]["FPT"]["source_metadata_ref"][
                "snapshot_id"
            ]
            == legacy.id
        )
        assert {r["price_vnd"] for r in historical.observations} == {"9000.000000"}
        assert {r["available_at"] for r in historical.observations} == {old_known}
        today = build_selected_snapshot(
            session, ["FPT"], result["calendar_sessions"], TODAY, directory=root
        )
        assert today.manifest["asset_coverage"]["FPT"]["status"] == "AVAILABLE"
        assert {r["price_vnd"] for r in today.observations} == {"12345.123456"}
        assert [
            (r.id, r.available_at, r.ingested_at)
            for r in session.scalars(select(PriceRevision))
        ] == original_times


def test_historical_inferred_calendar_is_trimmed_but_explicit_future_calendar_rejected(
    owner,
):
    from portfolio_contracts import canonical_hash
    from market_service.models import Snapshot

    sessions, store = owner
    root = store.directory.parent.parent
    future_calendar = ["2020-01-02", "2020-01-14", "2026-11-11", "2026-11-12"]
    manifest = {
        "schema_version": 2,
        "calendar_sessions": future_calendar,
        "observation_hash": canonical_hash({"observations": []}),
    }
    with sessions.begin() as session:
        session.add(
            Snapshot(
                content_hash=canonical_hash(manifest),
                manifest=manifest,
                observations=[],
            )
        )
    with sessions.begin() as session:
        historical = build_selected_snapshot(session, as_of=END, directory=root)
        assert historical.manifest["calendar_sessions"] == future_calendar[:-1]
        assert historical.manifest["end_date"] == str(END)
    with sessions.begin() as session:
        with pytest.raises(ValueError, match="calendar"):
            build_selected_snapshot(
                session, calendar=future_calendar, as_of=END, directory=root
            )


def test_current_snapshot_keeps_all_32_latest_sources_available(owner):
    from portfolio_contracts.assets import ASSET_IDS
    from market_service.phase1_full import ASSETS_SEED_HASH
    from market_service.phase1_sources import GOLD_SEED_HASH

    sessions, store = owner
    baseline = AUDIT.parent / "readiness_20261012"
    for source in [
        baseline / "gold_archive_daily.csv",
        baseline
        / "runs/availability-observed-contract-20261012T233110/source_snapshot/assets_1.json",
    ]:
        (store.directory / source.name).write_bytes(source.read_bytes())
    seed = store.directory / "seed.json"
    seed.write_text(
        json.dumps(
            {
                "assets": {"file": "assets_1.json", "sha256": ASSETS_SEED_HASH},
                "gold": {"file": "gold_archive_daily.csv", "sha256": GOLD_SEED_HASH},
            }
        )
    )

    class AllSources(Vff):
        def fetch(self, url, payload=None):
            if "/lich-su/" not in url:
                return super().fetch(url, payload)
            year, month = url.split("/")[-2:]
            return (AUDIT / f"gold-{year}-{int(month):02}.html").read_bytes(), {
                "url": url,
                "requested_at": NOW.isoformat(),
                "received_at": NOW.isoformat(),
            }

    result = refresh_selected(
        list(ASSET_IDS),
        END,
        store,
        sessions=sessions,
        kbs=Kbs(),
        mixed=AllSources(),
        seed=seed,
        now=NOW,
    )
    assert {r["status"] for r in result["asset_receipts"].values()} == {"AVAILABLE"}
    with sessions.begin() as session:
        snapshot = build_selected_snapshot(
            session, as_of=TODAY, directory=store.directory.parent.parent
        )
        assert list(snapshot.manifest["asset_coverage"]) == list(ASSET_IDS)
        assert {r["status"] for r in snapshot.manifest["asset_coverage"].values()} == {
            "AVAILABLE"
        }
        assert {
            r["quality_status"] for r in snapshot.manifest["asset_coverage"].values()
        } == {"PASS"}
        assert {r["asset_id"] for r in snapshot.observations} == set(ASSET_IDS)
