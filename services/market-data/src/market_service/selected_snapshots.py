"""Immutable schema 3 manifests describe source coverage without promising freshness."""

from datetime import date, datetime, time, timezone
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from portfolio_contracts import StrictModel, aware, canonical_hash, utcnow
from portfolio_contracts.selection import LIVE_NAV_POLICY
from portfolio_contracts.assets import (
    ASSET_IDS,
    EQUITY_IDS,
    CATALOG_VERSION,
    canonical_candidates,
)
from .models import IngestionJob, PriceRevision, QualityReport, Snapshot
from .phase1_full import START
from .phase1_sources import GOLD_PROVIDER, VFF_PROVIDER, equity_missing_sessions
from .providers import CsvProvider
from .refresh_provider import PROVIDER, normalize
from .selected_refresh import FAMILY, POLICY, read_artifact
from .snapshots import observation_json


class SelectedSnapshotRequest(StrictModel):
    as_of_date: date | None = None


def latest_selected_jobs(session, knowledge_cutoff=None):
    jobs = {}
    for asset in ASSET_IDS:
        job = session.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.input["source_family"].as_string() == FAMILY,
                IngestionJob.input["selected_asset_id"].as_string() == asset,
                *(
                    [IngestionJob.created_at <= knowledge_cutoff]
                    if knowledge_cutoff is not None
                    else []
                ),
            )
            .order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc())
            .limit(1)
        )
        if job:
            jobs[asset] = job
    return jobs


def _accepted_rows(session, asset, job, report, directory, knowledge_cutoff):
    spec = job.input["dataset_spec"]
    ref = spec["source_metadata_ref"]
    if report.report.get("source_metadata_ref") != ref:
        raise ValueError("Source metadata pin differs from quality receipt")
    metadata = json.loads(read_artifact(directory, ref))
    if (
        metadata.get("asset_id") != asset
        or metadata.get("source_family") != FAMILY
        or metadata.get("availability_policy") != POLICY
    ):
        raise ValueError("Source metadata identity mismatch")
    if metadata["normalized_ref"]["sha256"] != spec["sha256"]:
        raise ValueError("Normalized source pin mismatch")
    for source in metadata["source_provenance"]:
        read_artifact(directory, source["raw"])
    calendar_source = metadata.get("calendar_source")
    if calendar_source:
        calendar_raw = read_artifact(directory, calendar_source["raw"])
        observed = normalize(
            calendar_raw,
            "VNINDEX",
            date(2020, 1, 1),
            date.fromisoformat(spec["end_date"]),
        )
        if calendar_source.get("asset_id") != "VNINDEX" or metadata[
            "calendar_sessions"
        ] != [str(day) for day, _ in observed]:
            raise ValueError("Selected observed calendar identity mismatch")
    expected = CsvProvider(directory).fetch(spec)
    dates = {row.observation_date: row for row in expected}
    provider = (
        PROVIDER
        if asset in EQUITY_IDS
        else GOLD_PROVIDER
        if asset == "GOLD"
        else VFF_PROVIDER
    )
    if spec["provider"] != provider or spec["asset_id"] != asset:
        raise ValueError("Unexpected selected provider")
    rows = list(
        session.scalars(
            select(PriceRevision)
            .join(QualityReport, PriceRevision.ingestion_job_id == QualityReport.job_id)
            .where(
                PriceRevision.asset_id == asset,
                PriceRevision.provider == provider,
                PriceRevision.price_type == spec["price_type"],
                PriceRevision.observation_date.between(
                    date.fromisoformat(spec["start_date"]),
                    date.fromisoformat(spec["end_date"]),
                ),
                PriceRevision.available_at <= knowledge_cutoff,
                QualityReport.status == "PASS",
            )
            .order_by(PriceRevision.revision)
        )
    )
    selected = {row.observation_date: row for row in rows}
    if set(selected) != set(dates):
        raise ValueError("Missing accepted source revisions")
    if asset in EQUITY_IDS:
        gaps = equity_missing_sessions(
            asset,
            [(day, None) for day in selected],
            [d for d in metadata["calendar_sessions"] if d >= str(START)],
        )
        if gaps != metadata["equity_missing_sessions"]:
            raise ValueError("Undeclared equity source gap")
    observations = []
    for day in sorted(selected):
        row = selected[day]
        if (
            row.price_vnd != dates[day].price
            or row.data_origin != "real"
            or row.unit != spec["source_unit"]
            or row.price_basis != spec["price_basis"]
        ):
            raise ValueError("Selected source revision quality mismatch")
        source_metadata = metadata["metadata_by_date"].get(str(day), {})
        if asset == "VFF" and source_metadata.get("product_id") != 21:
            raise ValueError("VFF metadata identity missing")
        if asset == "GOLD" and not isinstance(
            source_metadata.get("provider_carry_flag"), bool
        ):
            raise ValueError("GOLD carry metadata missing")
        observations.append(
            observation_json(row)
            | {
                "source_metadata": source_metadata,
                "source_metadata_ref": ref,
                "raw_source_hash": source_metadata.get(
                    "raw_source_hash",
                    metadata["source_provenance"][-1]["raw"]["sha256"],
                ),
            }
        )
    return observations, metadata, ref


def build_selected_snapshot(
    session, asset_ids=None, calendar=None, as_of=None, *, directory=None, availability_policy=LIVE_NAV_POLICY
):
    """Build the shared catalog resource; refresh selections never shrink its order."""
    if availability_policy not in (POLICY, LIVE_NAV_POLICY):
        raise ValueError("Unknown NAV availability policy")
    canonical_candidates(list(asset_ids) if asset_ids is not None else list(ASSET_IDS))
    as_of = as_of or utcnow().astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    as_of = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    if as_of > utcnow().astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date():
        raise ValueError("Future selected snapshot as-of date")
    knowledge_cutoff = min(
        utcnow(),
        datetime.combine(
            as_of, time.max, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")
        ).astimezone(timezone.utc),
    )
    directory = Path(directory or os.environ["DATASET_DIRECTORY"]).resolve()
    jobs = latest_selected_jobs(session, knowledge_cutoff=knowledge_cutoff)
    loaded, coverage, observations, missing_equity = {}, {}, [], {}
    fallback = session.scalar(
        select(Snapshot)
        .where(Snapshot.manifest["schema_version"].as_integer() == 2)
        .order_by(Snapshot.created_at.desc())
        .limit(1)
    )
    if fallback is not None and (
        canonical_hash(fallback.manifest) != fallback.content_hash
        or canonical_hash({"observations": fallback.observations})
        != fallback.manifest["observation_hash"]
    ):
        fallback = None
    for asset in ASSET_IDS:
        job = jobs.get(asset)
        report = session.get(QualityReport, job.id) if job else None
        entry = {
            "status": "MISSING",
            "quality_status": "NOT_CHECKED",
            "reason_code": "ASSET_DATA_MISSING",
            "observation_count": 0,
            "revision_ids": [],
            "observation_hash": canonical_hash({"observations": []}),
            "source_metadata_ref": None,
            "raw_artifact_refs": [],
            "latest_observation_date": None,
            "checked_at": aware(report.checked_at).isoformat() if report else None,
        }
        rows, metadata, ref = [], {}, None
        try:
            if job:
                entry["source_metadata_ref"] = (
                    report.report.get("source_metadata_ref")
                    if report
                    else job.input.get("source_metadata_ref")
                )
                if (
                    job.status != "SUCCEEDED"
                    or report is None
                    or report.status != "PASS"
                ):
                    if report and report.status == "QUARANTINED":
                        entry.update(
                            status="QUARANTINED",
                            quality_status="QUARANTINED",
                            reason_code="INPUT_INVALID",
                        )
                    coverage[asset] = entry
                    continue
                rows, metadata, ref = _accepted_rows(
                    session, asset, job, report, directory, knowledge_cutoff
                )
                loaded[asset] = metadata
            elif fallback is not None:
                rows = [
                    dict(row)
                    for row in fallback.observations
                    if row["asset_id"] == asset
                    and datetime.fromisoformat(row["available_at"]) <= knowledge_cutoff
                ]
                if rows:
                    ref = {
                        "kind": "market-snapshot",
                        "snapshot_id": fallback.id,
                        "content_hash": fallback.content_hash,
                        "observation_hash": fallback.manifest["observation_hash"],
                    }
                    metadata = {
                        "source_provenance": fallback.manifest.get(
                            "source_provenance", {}
                        ).get(asset, []),
                        "equity_missing_sessions": fallback.manifest.get(
                            "equity_missing_sessions", {}
                        ).get(asset, []),
                    }
            if rows:
                entry.update(
                    status="AVAILABLE",
                    quality_status="PASS",
                    reason_code=None,
                    observation_count=len(rows),
                    revision_ids=[r["revision_id"] for r in rows],
                    observation_hash=canonical_hash({"observations": rows}),
                    source_metadata_ref=ref,
                    raw_artifact_refs=metadata["source_provenance"],
                    latest_observation_date=rows[-1]["observation_date"],
                )
                observations.extend(rows)
                if asset in EQUITY_IDS and metadata.get("equity_missing_sessions"):
                    missing_equity[asset] = metadata["equity_missing_sessions"]
        except (ValueError, KeyError, TypeError, OSError, ArithmeticError):
            entry.update(
                status="QUARANTINED",
                quality_status="QUARANTINED",
                reason_code="INPUT_INVALID",
            )
        coverage[asset] = entry
    if calendar is None:
        calendars = [
            m["calendar_sessions"]
            for m in loaded.values()
            if m.get("calendar_sessions")
        ]
        if fallback is not None:
            calendars.append(fallback.manifest["calendar_sessions"])
        calendar = max(calendars, key=lambda values: values[-1]) if calendars else []
        calendar = [d for d in calendar if date.fromisoformat(d) <= as_of]
    calendar = [str(day) for day in calendar]
    if (
        calendar != sorted(set(calendar))
        or len(calendar) > 10000
        or any(date.fromisoformat(d) > as_of for d in calendar)
    ):
        raise ValueError("Invalid selected observed calendar")
    manifest = {
        "schema_version": 3,
        "universe_id": "VN_USER_SELECTION",
        "catalog_version": CATALOG_VERSION,
        "asset_ids": list(ASSET_IDS),
        "candidate_equity_ids": list(EQUITY_IDS),
        "availability_policy": availability_policy,
        "availability_basis": "ingestion",
        "historical_publication_verified": False,
        "status": "READY",
        "quality_status": "PER_ASSET",
        "currency": "VND",
        "data_origin": "real",
        "calendar": "kbs-observed-vnindex-sessions",
        "calendar_verified": False,
        "calendar_sessions": calendar,
        "calendar_status": "AVAILABLE" if calendar else "MISSING",
        "as_of_date": str(as_of),
        "start_date": min(
            (r["observation_date"] for r in observations), default=str(START)
        ),
        "panel_start_date": str(START),
        "end_date": calendar[-1] if calendar else str(as_of),
        "max_age_days": 7,
        "asset_coverage": coverage,
        "equity_missing_sessions": missing_equity,
        "observation_count": len(observations),
        "revision_ids": [r["revision_id"] for r in observations],
        "observation_hash": canonical_hash({"observations": observations}),
    }
    digest = canonical_hash(manifest)
    existing = session.scalar(select(Snapshot).where(Snapshot.content_hash == digest))
    if existing:
        return existing
    try:
        with session.begin_nested():
            snapshot = Snapshot(
                content_hash=digest, manifest=manifest, observations=observations
            )
            session.add(snapshot)
            session.flush()
    except IntegrityError:
        snapshot = session.scalar(
            select(Snapshot).where(Snapshot.content_hash == digest)
        )
        if snapshot is None:
            raise
    return snapshot
