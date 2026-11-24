"""Preflight buffered snapshots and enqueue through the normal publication worker."""

from datetime import datetime, timedelta
import json
import logging
import os
from pathlib import Path
import time
from uuid import UUID

from portfolio_contracts import canonical_hash, utcnow
from portfolio_contracts.assets import EQUITY_IDS
from .ml import parse_manifest, read_artifact
from .publication_api import CredentialModelResolver, ModelResolutionUnavailable
from .publication_worker import CredentialMarketReader, PublicationQueue
from .runtime import sessions_from_env
from .selection_catalog import SelectionCatalog, UNIVERSE
from .selection_panel import SelectionDataError, SelectionPanel
from .selection_ready import check_equity_model_inputs, fit_index

HANDOFF = Path("/refresh/hybrid-automation/snapshot.json")
BUFFERED = "user-selection-data-v1"


def approved_model(directory, panel, equities):
    resolver = CredentialModelResolver()
    epoch = panel.dates[fit_index(panel.decision_index)]
    for path in sorted(
        (directory / "ml-models").glob("*/*/*.approved.json"), reverse=True
    ):
        # File names discover candidates only. ML registry resolves the actual pin.
        identity = str(UUID(path.name.split(".")[0]))
        try:
            ref = resolver.resolve(identity)
        except ModelResolutionUnavailable:
            continue
        manifest = parse_manifest(read_artifact(directory, ref))
        if (
            manifest.schema_version != 5
            or manifest.status != "APPROVED"
            or manifest.demo
            or manifest.fit_epoch != epoch
        ):
            continue
        try:
            check_equity_model_inputs(manifest, panel, equities, panel.decision_index)
        except (SelectionDataError, ValueError):
            continue
        return identity, ref
    raise ValueError("MODEL_REVIEW_OR_COMPATIBILITY_REQUIRED")


def eligible_assets(panel, now):
    available = []
    issues = {}
    for asset in panel.ids:
        try:
            panel.project([asset], now)
            available.append(asset)
        except SelectionDataError as exc:
            issues[asset] = {"reason": exc.code, **exc.details}
    return available, issues


def enqueue(pin, directory, now):
    age = now - datetime.fromisoformat(pin["refreshed_at"])
    if not timedelta(0) <= age < timedelta(hours=5):
        raise ValueError("REFRESH_OVERDUE")
    snapshot, observations = CredentialMarketReader().load(
        pin["snapshot_id"], pin["snapshot_hash"]
    )
    if snapshot["availability_policy"] != BUFFERED or snapshot["max_age_days"] != 7:
        raise ValueError("WRONG_AVAILABILITY_POLICY")
    panel = SelectionPanel(
        snapshot, observations, expected_hash=pin["snapshot_hash"], now=now
    )
    available, issues = eligible_assets(panel, now)
    print(json.dumps({"snapshot": pin["snapshot_id"], "issues": issues}), flush=True)
    equities = [asset for asset in available if asset in EQUITY_IDS]
    if not equities:
        raise ValueError("NO_FRESH_EQUITIES")
    catalog = SelectionCatalog(directory)
    # Avoid replacing a usable asset with a failed provider refresh. Compare like policies.
    try:
        prior = catalog.latest()
    except (ValueError, FileNotFoundError):
        prior = None
    if prior and prior.valid_until > now:
        _, old = catalog.load_resource(prior)
        if old.dates[old.decision_index] > panel.dates[panel.decision_index]:
            raise ValueError("OLDER_SNAPSHOT")
        prior_assets, _ = eligible_assets(old, now)
        lost = set(prior_assets) - set(available)
        if old.snapshot["availability_policy"] != BUFFERED:
            lost.discard("VFF")  # The old, unbuffered NAV cannot certify VFF freshness.
        if lost:
            raise ValueError("COVERAGE_REGRESSION " + ",".join(sorted(lost)))
    model_id, model = approved_model(directory, panel, equities)
    request = dict(
        snapshot_id=pin["snapshot_id"],
        snapshot_hash=pin["snapshot_hash"],
        approved_model_id=model_id,
        model=model,
        universe_id=UNIVERSE,
        max_age_days=7,
    )
    queue = PublicationQueue(sessions_from_env())
    job = queue.enqueue("hybrid-auto:" + canonical_hash(request), request)
    return job.id, queue


def main():
    done = None
    while True:
        try:
            if HANDOFF.exists():
                pin = json.loads(HANDOFF.read_text())
                if done != pin["snapshot_id"]:
                    job_id, queue = enqueue(
                        pin, Path(os.environ["BUNDLE_DIRECTORY"]), utcnow()
                    )
                    for _ in range(120):
                        job = queue.get(job_id)
                        if job.status in {"FAILED", "SUCCEEDED"}:
                            print(
                                json.dumps(
                                    {
                                        "job_id": job_id,
                                        "status": job.status,
                                        "error": job.safe_error,
                                    }
                                ),
                                flush=True,
                            )
                            if job.status == "SUCCEEDED":
                                done = pin["snapshot_id"]
                            break
                        time.sleep(2)
        except ValueError as error:
            logging.warning("Publication held: %s", str(error)[:160])
        except Exception as error:
            logging.error("Publication check failed (%s)", type(error).__name__)
        time.sleep(60)


if __name__ == "__main__":
    main()
