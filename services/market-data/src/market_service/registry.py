"""Registry pins are immutable and contain only server-selected source specs."""

from sqlalchemy.exc import IntegrityError

from portfolio_contracts import aware
from .models import RegisteredDataset


def metadata(dataset_id, spec, start=None, end=None):
    return {
        "dataset_id": dataset_id,
        "sha256": spec["sha256"],
        "asset_id": spec["asset_id"],
        "kind": spec["kind"],
        "source_unit": spec["source_unit"],
        "provider": spec["provider"],
        "data_origin": spec.get("data_origin", "unverified"),
        "price_basis": spec.get("price_basis", "unverified"),
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "calendar": "explicit-sessions"
        if spec.get("expected_sessions") is not None
        else "observed-sessions-only",
    }


def dataset_json(row):
    return metadata(row.dataset_id, row.spec, row.start_date, row.end_date) | {
        "registered_at": aware(row.registered_at).isoformat()
    }


def bootstrap(session, provider, dataset_id, actor_id, *, spec=None, coverage=None):
    row = session.get(RegisteredDataset, dataset_id)
    if row is None:
        spec = spec if spec is not None else provider.spec(dataset_id)
        # Compatibility ingestion may enqueue a changed source to obtain its persisted quarantine report.
        try:
            start, end = coverage if coverage is not None else provider.coverage(spec)
        except (ValueError, OSError, UnicodeError):
            start, end = None, None
        row = RegisteredDataset(
            dataset_id=dataset_id,
            sha256=spec["sha256"],
            spec=spec,
            start_date=start,
            end_date=end,
            registered_by=actor_id,
        )
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
        except IntegrityError:
            # A different operator can win the immutable dataset key while this
            # transaction is waiting on PostgreSQL's unique index. Only roll back
            # our insert, then use the committed winner without changing its pin.
            row = session.get(RegisteredDataset, dataset_id)
            if row is None:
                raise
    return row
