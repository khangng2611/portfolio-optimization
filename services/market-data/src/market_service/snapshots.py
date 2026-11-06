from datetime import datetime, time, timezone

from sqlalchemy import select

from portfolio_contracts import aware, canonical_hash, utcnow
from .models import Asset, PriceRevision, Snapshot, QualityReport
from portfolio_contracts.market import UNITS


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


def build_snapshot(session, request):
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
        if any(
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
