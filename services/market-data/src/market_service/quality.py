"""Safe, persisted findings; validate the complete batch before writing prices."""

from datetime import date

from portfolio_contracts import aware, utcnow
from portfolio_contracts.market import UNITS


MESSAGES = {
    "QUALITY_NOT_CHECKED": (
        "Quality checks did not run for this terminal ingestion.",
        "Review the job error or resubmit the trusted source with a new idempotency key.",
    ),
    "CHECKSUM_MISMATCH": (
        "Source bytes differ from the registered checksum.",
        "Restore the pinned source or register a new dataset ID.",
    ),
    "INVALID_SOURCE": (
        "The trusted source cannot be read safely.",
        "Check the server inventory file and encoding.",
    ),
    "INVALID_ROW": (
        "A source row has invalid required fields or price.",
        "Correct the source row and register a new dataset ID.",
    ),
    "INVALID_KNOWN_AT": (
        "Publication time is invalid or precedes the observation.",
        "Provide an available timezone-aware publication timestamp.",
    ),
    "DUPLICATE_OBSERVATION": (
        "The batch contains duplicate observation keys.",
        "Remove duplicate rows before ingestion.",
    ),
    "MISSING_SESSIONS": (
        "The batch does not cover its declared sessions.",
        "Supply all declared sessions or correct the trusted calendar.",
    ),
    "UNIT_MISMATCH": (
        "The source unit conflicts with the asset or registry.",
        "Correct the trusted source unit and conversion.",
    ),
    "BASIS_MISMATCH": (
        "The price basis conflicts with the asset or registry.",
        "Correct the trusted price basis.",
    ),
    "UNKNOWN_BASIS": (
        "The source has no verified price basis.",
        "Verify the price basis before research publication.",
    ),
    "INGESTION_KNOWN_AT": (
        "Availability is based on ingestion time.",
        "Use ingestion availability for historical cutoffs.",
    ),
    "ASSET_MISMATCH": (
        "The source conflicts with the registered asset.",
        "Correct the source symbol or asset definition.",
    ),
    "EMPTY_DATASET": (
        "The source contains no observations.",
        "Provide a nonempty source dataset.",
    ),
    "LIMIT_EXCEEDED": (
        "The source exceeds bounded import limits.",
        "Split the source into smaller trusted datasets.",
    ),
}


def finding(code, row_number=None, severity="ERROR"):
    message, action = MESSAGES[code]
    value = {"code": code, "severity": severity, "message": message, "action": action}
    if row_number is not None:
        value["row_number"] = row_number
    return value


class QualityFailure(ValueError):
    def __init__(self, findings, row_count=0):
        super().__init__("Source quality validation failed")
        self.findings = findings[:100]
        self.row_count = row_count


def validate_batch(observations, spec=None):
    findings, keys = [], set()
    for index, row in enumerate(observations, 2):
        key = (row.asset_id, row.observation_date, row.provider, row.price_type)
        if key in keys:
            findings.append(finding("DUPLICATE_OBSERVATION", index))
        keys.add(key)
        if row.source_unit not in {UNITS[row.kind], "thousand_" + UNITS[row.kind]}:
            findings.append(finding("UNIT_MISMATCH", index))
        allowed = {
            "stock": {"raw_close", "provider_adjusted", "unverified"},
            "fund": {"nav", "unverified"},
            "gold": {"raw_close", "unverified"},
        }
        if row.price_basis not in allowed[row.kind]:
            findings.append(finding("BASIS_MISMATCH", index))
    if spec and spec.get("expected_sessions") is not None:
        try:
            expected = {date.fromisoformat(d) for d in spec["expected_sessions"]}
        except (TypeError, ValueError):
            findings.append(finding("MISSING_SESSIONS"))
        else:
            if expected != {r.observation_date for r in observations}:
                findings.append(finding("MISSING_SESSIONS"))
    if findings:
        raise QualityFailure(findings, len(observations))
    warnings = []
    if any(r.price_basis == "unverified" for r in observations):
        warnings.append(finding("UNKNOWN_BASIS", severity="WARNING"))
    if any(r.published_at is None for r in observations):
        warnings.append(finding("INGESTION_KNOWN_AT", severity="WARNING"))
    return warnings


def report_json(job_id, status, row_count, findings, observations=None, spec=None):
    dates = [r.observation_date for r in observations or []]
    return {
        "job_id": job_id,
        "status": status,
        "row_count": row_count,
        "findings": findings[:100],
        "calendar": "explicit-sessions"
        if spec and spec.get("expected_sessions") is not None
        else "observed-sessions-only",
        "start_date": min(dates).isoformat() if dates else None,
        "end_date": max(dates).isoformat() if dates else None,
        "checked_at": utcnow().isoformat(),
    }


def reconcile_deadline(session, job):
    """Expire overdue work even when only operator polling is available.

    Refresh under the same row lock used by the worker before changing status;
    an ingestion that committed successfully while we waited must stay successful.
    """
    from sqlalchemy import select
    from .models import IngestionJob

    if job.status == "QUEUED" and aware(job.deadline) <= utcnow():
        job = session.scalar(
            select(IngestionJob)
            .where(IngestionJob.id == job.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job.status == "QUEUED" and aware(job.deadline) <= utcnow():
            job.status = "FAILED"
            job.error = {
                "code": "DEADLINE_EXCEEDED",
                "message": "Ingestion deadline exceeded",
            }
    return job


def terminal_quality(session, job):
    """Missing checks on terminal jobs cannot remain pending or imply approval."""
    from sqlalchemy.exc import IntegrityError
    from .models import QualityReport

    job = reconcile_deadline(session, job)
    quality = session.get(QualityReport, job.id)
    if quality is None and job.status != "QUEUED":
        quality = QualityReport(
            job_id=job.id,
            status="NOT_CHECKED",
            report=report_json(
                job.id,
                "NOT_CHECKED",
                0,
                [finding("QUALITY_NOT_CHECKED", severity="WARNING")],
            ),
        )
        try:
            with session.begin_nested():
                session.add(quality)
                session.flush()
        except IntegrityError:
            quality = session.get(QualityReport, job.id)
            if quality is None:
                raise
    return quality
