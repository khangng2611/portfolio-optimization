from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from market_service.phase1_sources import (
    normalize_fmarket,
    normalize_gold_archive,
    frozen_gold,
)

AUDIT = (
    Path(__file__).resolve().parents[2] / "outputs/step1/source-audit-20261111T230659"
)
START, END = date(2020, 1, 14), date(2026, 11, 10)


def read_research_source(path):
    if not path.is_file():
        pytest.skip(f"Optional frozen research source unavailable: {path.name}")
    return path.read_bytes()


def vff_nav():
    return json.dumps(
        {
            "status": 200,
            "data": [
                {
                    "productId": 21,
                    "navDate": str(END),
                    "nav": "27249.21",
                    "createdAt": 1794304434847,
                }
            ],
        }
    ).encode()


def test_gold_archive_normalizes_prices_and_preserves_carry():
    raw = (
        "Vàng SJC 1L, 10L, 1KG · Hồ Chí Minh<table>"
        "<tr><td>10/11/2026</td><td>138,5</td><td>139,5</td></tr>"
        "<tr><td>11/11/2026 không đổi</td><td>138,5</td><td>139,5</td></tr>"
        "</table>"
    ).encode()
    rows, metadata = normalize_gold_archive(raw, 2026, 11)
    assert rows[-1] == (date(2026, 11, 11), Decimal("139500000.0"))
    assert len(rows) == 2
    assert any(v["provider_carry_flag"] for v in metadata.values())
    assert metadata["2026-11-11"]["historical_publication_verified"] is False


def test_fmarket_full_precision_identity_duplicate_conflict():
    rows, metadata = normalize_fmarket(vff_nav(), START, END)
    assert rows[-1] == (END, Decimal("27249.21"))
    assert (
        metadata[str(END)]["raw_fund_record_created_at"]
        == "2026-11-10T09:53:54.847000+00:00"
    )
    bad = {
        "status": 200,
        "data": [
            {"productId": 21, "navDate": str(END), "nav": "123.123456"},
            {"productId": 21, "navDate": str(END), "nav": "123.123455"},
        ],
    }
    with pytest.raises(ValueError, match="conflicting"):
        normalize_fmarket(json.dumps(bad).encode(), START, END)
    bad["data"][1]["productId"] = 22
    with pytest.raises(ValueError, match="identity"):
        normalize_fmarket(json.dumps(bad).encode(), START, END)


def test_frozen_gold_hash_unit_and_calendar():
    path = AUDIT.parent / "readiness_20261012/gold_archive_daily.csv"
    raw = read_research_source(path)
    rows, metadata = frozen_gold(raw)
    assert (
        hashlib.sha256(raw).hexdigest()
        == "122a1100daac668883854040dc139c5c6a01131b8fa4a9bab93447a9f3e1dc73"
    )
    assert rows[0] == (date(2019, 12, 1), Decimal("41500000.0"))
    assert rows[-1][0] == date(2026, 4, 30)
    assert len(rows) == 2343
    with pytest.raises(ValueError, match="checksum"):
        frozen_gold(raw + b"\n")


@pytest.fixture
def full_pack(tmp_path, monkeypatch):
    monkeypatch.setenv("DATASET_DIRECTORY", str(tmp_path.parent))
    from datetime import datetime, timezone
    from market_service.phase1_full import fetch_full_pack, ASSETS_SEED_HASH
    from market_service.refresh_provider import ArtifactStore
    from market_service.phase1_sources import GOLD_SEED_HASH

    baseline = AUDIT.parent / "readiness_20261012"
    (tmp_path / "assets_1.json").write_bytes(
        read_research_source(
            baseline
            / "runs/availability-observed-contract-20261012T233110/source_snapshot/assets_1.json"
        )
    )
    (tmp_path / "gold_archive_daily.csv").write_bytes(
        read_research_source(baseline / "gold_archive_daily.csv")
    )
    (tmp_path / "seed.json").write_text(
        json.dumps(
            {
                "assets": {"file": "assets_1.json", "sha256": ASSETS_SEED_HASH},
                "gold": {"file": "gold_archive_daily.csv", "sha256": GOLD_SEED_HASH},
            }
        )
    )

    class Kbs:
        def fetch_raw(self, symbol, start, end, index=False):
            days = (
                ["2020-01-02", "2020-01-14", "2026-11-10"]
                if index
                else ["2020-01-14", "2026-11-10"]
            )
            return json.dumps(
                {"data_day": [{"t": d, "c": 12345} for d in days]}
            ).encode()

    class Mixed:
        def fetch(self, url, payload=None):
            if "/lich-su/" in url:
                parts = url.split("/")
                name = f"gold-{parts[-2]}-{int(parts[-1]):02}.html"
            else:
                name = (
                    "fmarket-identity.json" if "/filter" in url else "fmarket-nav.json"
                )
            return read_research_source(AUDIT / name), {
                "url": url,
                "requested_at": "2026-11-11T16:30:00+00:00",
                "received_at": "2026-11-11T16:30:01+00:00",
                "payload": payload,
            }

    store = ArtifactStore(tmp_path)
    batch = fetch_full_pack(
        tmp_path / "seed.json",
        store,
        now=datetime(2026, 11, 11, 16, 30, tzinfo=timezone.utc),
        kbs=Kbs(),
        mixed=Mixed(),
    )
    return store, batch


def test_full_batch_snapshot_preserves_mixed_dates_ingestion_truth_and_order(full_pack):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from market_service.models import Base, Snapshot, PriceRevision, QualityReport
    from market_service.phase1_full import persist_full_pack

    store, batch = full_pack
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    result = persist_full_pack(sessions, store, batch)
    assert result["schema_version"] == 2
    assert batch["packs"][0]["spec"]["path"].startswith(store.directory.name + "/")
    assert result["calendar_sessions"][0] == "2020-01-02"
    assert result["panel_start_date"] == "2020-01-14"
    assert result["asset_ids"] == result["candidate_equity_ids"] + ["GOLD", "VFF"]
    assert result["availability_policy"] == "phase1-full-v1"
    assert result["max_age_days"] == 7
    with sessions() as session:
        snapshot = session.get(Snapshot, result["id"])
        gold = [o for o in snapshot.observations if o["asset_id"] == "GOLD"]
        fund = [o for o in snapshot.observations if o["asset_id"] == "VFF"]
        assert gold[0]["observation_date"] == "2019-12-01"
        assert fund[0]["observation_date"] == "2020-01-07"
        assert gold[0]["ingested_at"][:10] >= "2026-11-11"
        assert fund[-1]["source_metadata"]["provider_record_created_at"].endswith(
            "+00:00"
        )
        assert session.scalar(select(PriceRevision).limit(1)).available_at.year == 2026
        assert len(list(session.scalars(select(QualityReport)))) == 32
        revision_count = len(list(session.scalars(select(PriceRevision.id))))
    repeated = persist_full_pack(sessions, store, batch)
    assert repeated["id"] == result["id"]
    with sessions() as session:
        assert len(list(session.scalars(select(PriceRevision.id)))) == revision_count


def test_full_batch_corrupt_pin_rejected_before_sql(full_pack):
    from market_service.phase1_full import persist_full_pack

    store, batch = full_pack
    batch["source_manifest"] = dict(batch["source_manifest"], sha256="f" * 64)
    with pytest.raises(ValueError, match="checksum"):
        persist_full_pack(None, store, batch)


def test_failed_full_batch_has_quarantine_report_without_revisions():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from market_service.models import Base, PriceRevision, QualityReport, Snapshot
    from market_service.phase1_full import quarantine_full_failure

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    quarantine_full_failure(sessions, cause=ValueError("bad source"))
    with sessions() as session:
        assert session.scalar(select(QualityReport)).status == "QUARANTINED"
        assert session.scalar(select(PriceRevision)) is None
        assert session.scalar(select(Snapshot)) is None


def test_incomplete_universe_rolls_back_all_accepted_state(full_pack):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from market_service.models import Base, PriceRevision, QualityReport, Snapshot
    from market_service.phase1_full import persist_full_pack

    store, batch = full_pack
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    batch["asset_ids"] = batch["asset_ids"][:-1]
    with pytest.raises(ValueError, match="universe order"):
        persist_full_pack(sessions, store, batch)
    with sessions() as session:
        assert session.scalar(select(PriceRevision)) is None
        assert session.scalar(select(QualityReport)) is None
        assert session.scalar(select(Snapshot)) is None


def test_only_pinned_baseline_equity_gaps_are_accepted():
    from market_service.phase1_sources import (
        equity_missing_sessions,
        EQUITY_GAP_ALLOWLIST,
    )
    from market_service.quality import QualityFailure

    calendar = [
        "2020-12-01",
        "2020-12-02",
        "2020-12-03",
        "2020-12-04",
        "2020-12-07",
        "2020-12-08",
        "2020-12-09",
    ]
    rows = [(date(2020, 12, 1), Decimal("8832")), (date(2020, 12, 9), Decimal("9000"))]
    assert equity_missing_sessions("ACB", rows, calendar) == EQUITY_GAP_ALLOWLIST["ACB"]
    with pytest.raises(QualityFailure):
        equity_missing_sessions("BID", rows, calendar)
    with pytest.raises(QualityFailure):
        equity_missing_sessions("ACB", rows, calendar + ["2026-11-11"])


def test_equity_gap_allowlist_matches_hash_pinned_frozen_sources():
    import csv
    from market_service.phase1_sources import EQUITY_GAP_ALLOWLIST, EQUITY_GAP_EVIDENCE

    root = AUDIT.parents[2]
    calendar_path = root / "trusted_baseline/datasets/indices/full/VNINDEX.csv"
    assert (
        hashlib.sha256(read_research_source(calendar_path)).hexdigest()
        == EQUITY_GAP_EVIDENCE["calendar_sha256"]
    )
    calendar = {
        r["date"]
        for r in csv.DictReader(calendar_path.open(encoding="utf-8-sig"))
        if "2020-01-14" <= r["date"] <= "2026-04-30"
    }
    actual = {}
    for symbol, expected_hash in EQUITY_GAP_EVIDENCE["raw_source_sha256"].items():
        path = (
            AUDIT.parent
            / f"blocker_evidence_20261012/raw/kbs_verified_full_{symbol}.json"
        )
        raw = read_research_source(path)
        assert hashlib.sha256(raw).hexdigest() == expected_hash
        observed = {r["t"][:10] for r in json.loads(raw)["data_day"]}
        actual[symbol] = sorted(calendar - observed)
    assert actual == EQUITY_GAP_ALLOWLIST
