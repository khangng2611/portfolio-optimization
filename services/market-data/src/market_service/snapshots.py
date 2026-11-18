from datetime import date, datetime, time, timezone

from sqlalchemy import select

from portfolio_contracts import aware, canonical_hash, utcnow
from .models import Asset, PriceRevision, Snapshot, QualityReport
from portfolio_contracts.market import UNITS
from .quality import QualityFailure, finding


def observation_json(row):
    return {
        "revision_id": row.id,
        "asset_id": row.asset_id,
        "observation_date": row.observation_date.isoformat(),
        "price_vnd": str(row.price_vnd),
        "unit": row.unit,
        "provider": row.provider,
        "price_type": row.price_type,
        "revision": row.revision,
        "content_hash": row.content_hash,
        "published_at": aware(row.published_at).isoformat()
        if row.published_at
        else None,
        "available_at": aware(row.available_at).isoformat(),
        "ingested_at": aware(row.ingested_at).isoformat(),
        "availability_basis": "ingestion",
        "source_hash": row.source_hash,
        "data_origin": row.data_origin,
        "price_basis": row.price_basis,
    }


def build_snapshot(session, request, *, observed_sessions=None):
    cutoff = min(
        utcnow(), datetime.combine(request.as_of_date, time.max, tzinfo=timezone.utc)
    )
    rows = list(
        session.scalars(
            select(PriceRevision)
            .where(
                PriceRevision.asset_id.in_(request.asset_ids),
                PriceRevision.observation_date.between(
                    request.start_date, request.end_date
                ),
                PriceRevision.available_at <= cutoff,
                *(
                    [PriceRevision.provider == request.provider]
                    if request.provider
                    else []
                ),
            )
            .order_by(
                PriceRevision.available_at, PriceRevision.revision, PriceRevision.id
            )
        )
    )
    latest = {}
    for row in rows:
        # Keep each provider/price convention separate; never silently mix sources.
        latest[(row.asset_id, row.observation_date, row.provider, row.price_type)] = row
    observations = []
    for asset_id in request.asset_ids:
        selected = [row for row in latest.values() if row.asset_id == asset_id]
        if not selected:
            raise ValueError(f"Missing observations for {asset_id}")
        if len({(row.provider, row.price_type) for row in selected}) != 1:
            raise ValueError(f"Ambiguous provider/price convention for {asset_id}")
        selected.sort(key=lambda row: row.observation_date)
        # Refresh has an explicit observed calendar, including exchange holidays.
        if (
            observed_sessions is not None
            and {row.observation_date.isoformat() for row in selected}
            != observed_sessions
        ):
            raise QualityFailure([finding("MISSING_SESSIONS")], len(selected))
        if observed_sessions is None and any(
            (right.observation_date - left.observation_date).days
            > max(1, request.max_age_days)
            for left, right in zip(selected, selected[1:])
        ):
            raise ValueError(f"Missing interval coverage for {asset_id}")
        if (
            request.as_of_date - selected[-1].observation_date
        ).days > request.max_age_days:
            raise ValueError(f"Stale observations for {asset_id}")
        if (
            selected[0].observation_date - request.start_date
        ).days > request.max_age_days:
            raise ValueError(f"Missing start coverage for {asset_id}")
        asset = session.get(Asset, asset_id)
        for row in selected:
            if (
                not row.price_vnd.is_finite()
                or row.price_vnd <= 0
                or asset is None
                or row.unit != UNITS[asset.kind]
            ):
                raise ValueError(f"Invalid selected price quality for {asset_id}")
            if row.published_at and (
                aware(row.published_at) > cutoff
                or aware(row.published_at).date() < row.observation_date
            ):
                raise ValueError(f"Invalid selected availability for {asset_id}")
            if row.ingestion_job_id:
                report = session.get(QualityReport, row.ingestion_job_id)
                if report is None or report.status != "PASS":
                    raise ValueError(
                        f"Selected observations have not passed quality for {asset_id}"
                    )
        if len({(row.unit, row.price_basis, row.data_origin) for row in selected}) != 1:
            raise ValueError(
                f"Inconsistent selected units, basis or origin for {asset_id}"
            )
        observations.extend(observation_json(row) for row in selected)
    request_manifest = request.model_dump(mode="json")
    if request.provider is None:
        request_manifest.pop(
            "provider", None
        )  # Preserve historical manifest/hash semantics.
    manifest = request_manifest | {
        "schema_version": 1,
        "status": "READY",
        "quality_status": "PASS",
        "quality_basis": "validated-selected-revisions",
        "calendar": "observed-sessions-only",
        "observation_count": len(observations),
        "revision_ids": [row["revision_id"] for row in observations],
        "observation_hash": canonical_hash({"observations": observations}),
        "availability_basis": "ingestion",
        "currency": "VND",
        "data_origin": "real"
        if all(o["data_origin"] == "real" for o in observations)
        else "synthetic"
        if any(o["data_origin"] == "synthetic" for o in observations)
        else "unverified",
    }
    content_hash = canonical_hash(manifest)
    existing = session.scalar(
        select(Snapshot).where(Snapshot.content_hash == content_hash)
    )
    if existing:
        return existing
    # Serialize hash insertion with the unique index while allowing safe replay.
    from sqlalchemy.exc import IntegrityError

    try:
        with session.begin_nested():
            snapshot = Snapshot(
                content_hash=content_hash, manifest=manifest, observations=observations
            )
            session.add(snapshot)
            session.flush()
    except IntegrityError:
        snapshot = session.scalar(
            select(Snapshot).where(Snapshot.content_hash == content_hash)
        )
        if snapshot is None:
            raise
    return snapshot


def snapshot_json(snapshot):
    return snapshot.manifest | {
        "id": snapshot.id,
        "content_hash": snapshot.content_hash,
        "created_at": aware(snapshot.created_at).isoformat(),
    }


def build_full_snapshot(
    session,
    *,
    asset_ids,
    candidate_equity_ids,
    start_date,
    end_date,
    as_of_date,
    calendar_sessions,
    packs,
    source_manifest,
    panel_start_date=None,
    equity_missing_sessions=None,
    max_age_days=7,
):
    """Schema 2 pins mixed raw observations; availability joins belong to Quant."""
    if (
        len(candidate_equity_ids) != 30
        or len(set(candidate_equity_ids)) != 30
        or asset_ids != candidate_equity_ids + ["GOLD", "VFF"]
    ):
        raise ValueError("Invalid fixed Phase 1 universe order")
    if [p["spec"]["asset_id"] for p in packs] != asset_ids:
        raise ValueError("Incomplete full source pack")
    observations = []
    for pack in packs:
        spec = pack["spec"]
        rows = list(
            session.scalars(
                select(PriceRevision)
                .where(
                    PriceRevision.asset_id == spec["asset_id"],
                    PriceRevision.provider == spec["provider"],
                    PriceRevision.price_type == spec["price_type"],
                    PriceRevision.observation_date.between(
                        date.fromisoformat(spec["start_date"]), end_date
                    ),
                )
                .order_by(PriceRevision.revision)
            )
        )
        latest = {r.observation_date: r for r in rows}
        expected = {r.observation_date: r for r in pack["observations"]}
        # Never splice a prior provider response into the accepted complete batch.
        if set(latest) != set(expected):
            raise ValueError(f"Incomplete selected revisions for {spec['asset_id']}")
        if spec["kind"] == "stock":
            from .phase1_sources import equity_missing_sessions as validate_equity_gaps

            actual_gaps = validate_equity_gaps(
                spec["asset_id"],
                [(day, None) for day in expected],
                [
                    d
                    for d in calendar_sessions
                    if d >= str(panel_start_date or start_date)
                ],
            )
            if actual_gaps != (equity_missing_sessions or {}).get(spec["asset_id"], []):
                raise ValueError(
                    f"Undeclared equity calendar gaps for {spec['asset_id']}"
                )
        if (as_of_date - max(expected)).days > max_age_days:
            raise ValueError(f"Stale raw source for {spec['asset_id']}")
        for day in sorted(expected):
            row = latest[day]
            report = (
                session.get(QualityReport, row.ingestion_job_id)
                if row.ingestion_job_id
                else None
            )
            if (
                report is None
                or report.status != "PASS"
                or row.price_vnd != expected[day].price
                or row.data_origin != "real"
                or row.unit != UNITS[spec["kind"]]
            ):
                raise ValueError(
                    f"Invalid full selected quality for {spec['asset_id']}"
                )
            observations.append(
                observation_json(row)
                | {
                    "source_metadata": pack["metadata"].get(str(day), {}),
                    "source_manifest_sha256": source_manifest["sha256"],
                    "raw_source_hash": pack["metadata"]
                    .get(str(day), {})
                    .get("raw_source_hash", pack["provenance"][-1]["raw"]["sha256"]),
                }
            )
    manifest = {
        "schema_version": 2,
        "universe_id": "VN_PHASE1_FULL",
        "asset_ids": asset_ids,
        "candidate_equity_ids": candidate_equity_ids,
        "start_date": str(start_date),
        "panel_start_date": str(panel_start_date or start_date),
        "end_date": str(end_date),
        "as_of_date": str(as_of_date),
        "max_age_days": max_age_days,
        "calendar": "kbs-observed-vnindex-sessions",
        "calendar_verified": False,
        "calendar_sessions": calendar_sessions,
        "equity_missing_sessions": equity_missing_sessions or {},
        "availability_policy": "phase1-full-v1",
        "availability_basis": "ingestion",
        "historical_publication_verified": False,
        "status": "READY",
        "quality_status": "PASS",
        "quality_basis": "validated-complete-mixed-source-batch",
        "currency": "VND",
        "data_origin": "real",
        "observation_count": len(observations),
        "revision_ids": [o["revision_id"] for o in observations],
        "observation_hash": canonical_hash({"observations": observations}),
        "source_manifest": source_manifest,
        "source_provenance": {p["spec"]["asset_id"]: p["provenance"] for p in packs},
    }
    content_hash = canonical_hash(manifest)
    existing = session.scalar(
        select(Snapshot).where(Snapshot.content_hash == content_hash)
    )
    if existing:
        return existing
    snapshot = Snapshot(
        content_hash=content_hash, manifest=manifest, observations=observations
    )
    session.add(snapshot)
    session.flush()
    return snapshot
