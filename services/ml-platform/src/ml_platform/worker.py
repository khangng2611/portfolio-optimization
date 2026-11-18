"""Manual training worker reusing the existing versioned Quant pure trainer.

The transitional portfolio-quant-service dependency supplies SnapshotPanel and
train_candidate unchanged. No Quant database, catalog or serving state is used.
"""

from datetime import date
import json
import os
from pathlib import Path
import time
import httpx
import xgboost as xgb
from sqlalchemy import select, update
from portfolio_contracts import canonical_hash, utcnow
from quant_service.snapshot_inputs import (
    SnapshotPanel,
    FEATURE_DEFINITION,
    FEATURE_SCHEMA,
    FEATURE_NAMES,
)
from quant_service import phase1
from quant_service.snapshot_publisher import MarketReader
from quant_service.model_worker import TrainingData, train_candidate, approve_candidate
from quant_service.ml import parse_manifest, read_artifact, validate_native_files
from .models import Model, Review, TrainingJob
from .queue import TrainingQueue


def validated_candidate(directory, ref):
    manifest = parse_manifest(read_artifact(directory, ref))
    if (
        manifest.schema_version not in (2, 3, 4, 5)
        or manifest.demo
        or manifest.status != "CANDIDATE"
    ):
        raise ValueError("Provenance-complete candidate required")
    if manifest.xgboost_version != xgb.__version__:
        raise ValueError("Unsupported model runtime")
    root = (Path(directory) / ref["file"]).resolve().parent
    validate_native_files(root, manifest, load=True)
    if manifest.schema_version in (3, 4, 5):
        return manifest
    if (
        manifest.feature_schema_version != FEATURE_SCHEMA
        or manifest.feature_names != FEATURE_NAMES
    ):
        raise ValueError("Unsupported model runtime or feature schema")
    metrics = manifest.validation
    import math

    for key in ("mae", "rmse"):
        if (
            type(metrics.get(key)) not in (int, float)
            or not math.isfinite(metrics[key])
            or metrics[key] < 0
        ):
            raise ValueError("Invalid validation metrics")
    if (
        metrics.get("method") != "chronological-80-20-label-embargo-v1"
        or metrics.get("train_rows", 0) < 5
        or metrics.get("validation_rows", 0) < 2
        or metrics.get("train_label_end", "9999") >= metrics.get("validation_start", "")
    ):
        raise ValueError("Invalid chronological validation")
    return manifest


def _register(session, directory, job, ref, provenance):
    manifest = validated_candidate(directory, ref)
    if (
        (manifest.schema_version == 5)
        != (job.request.get("model_family") == "phase1-asset-ensemble-v5")
        or manifest.training_snapshot_id != job.request["snapshot_id"]
        or manifest.training_snapshot_hash != job.request["snapshot_hash"]
        or manifest.training_cutoff.isoformat() != job.request["training_cutoff"]
        or manifest.training_data_hash != provenance["training_data_hash"]
    ):
        raise ValueError("Candidate training pins conflict")
    existing = session.scalar(select(Model).where(Model.training_job_id == job.id))
    if existing is not None:
        return {"model_id": existing.id}
    session.add(
        Model(
            id=manifest.model_id,
            training_job_id=job.id,
            status="CANDIDATE",
            version=1,
            manifest=manifest.model_dump(mode="json"),
            provenance=provenance,
            candidate_ref=ref,
            created_at=utcnow(),
        )
    )
    return {"model_id": manifest.model_id}


def _recover(directory, session, job):
    receipt = Path(directory) / job.id / "candidate-receipt.json"
    if not receipt.exists():
        return None
    saved = json.loads(receipt.read_text())
    if saved["body_hash"] != job.body_hash:
        raise ValueError("Training receipt conflict")
    ref = {
        "file": job.id + "/" + saved["reference"]["file"],
        "sha256": saved["reference"]["sha256"],
    }
    return _register(session, directory, job, ref, saved["provenance"])


def _durable_receipt(root, name, value):
    # Artifacts and receipt survive a worker/container crash before the SQL commit.
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".ubj"}:
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        elif path.is_dir():
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    temporary = root / (name + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(root / name)
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def process_one(queue, directory, reader, *, now=None):
    now = now or utcnow()
    job = queue.claim(
        now=now,
        lease_seconds=600,
        recover=lambda expired, session: _recover(directory, session, expired),
    )
    if job is None:
        return False
    try:
        owned, recovered = queue.publish_owned(
            job, lambda session: _recover(directory, session, job), now=now
        )
        if not owned or recovered is not None:
            return True
        request = job.request
        snapshot, rows = reader.load(request["snapshot_id"], request["snapshot_hash"])
        is_asset = request.get("model_family") == "phase1-asset-ensemble-v5"
        cutoff = date.fromisoformat(request["training_cutoff"])
        if is_asset:
            from quant_service.selection_panel import SelectionPanel
            from .selected_train import train_asset_candidate, fit_state

            if snapshot.get("schema_version") != 3 or request["max_age_days"] != 7:
                raise ValueError(
                    "Asset ensemble requires selected source schema 3 and freshness 7"
                )
            panel = SelectionPanel(
                snapshot, rows, expected_hash=request["snapshot_hash"], now=now
            )
            state = fit_state(panel)
            if str(state["training_cutoff"]) != str(cutoff):
                raise ValueError("Asset ensemble cutoff conflicts with the fit epoch")
            provenance = {
                "snapshot_id": snapshot["id"],
                "snapshot_hash": snapshot["content_hash"],
                "trainer": "phase1-asset-ensemble-v5",
                "data_origin": "real",
                "fit_epoch": str(state["fit_epoch"]),
                "training_equity_hash": state["training_equity_hash"],
                "training_data_hash": state["training_data_hash"],
                "point_in_time_certified": False,
            }
        else:
            is_full = snapshot.get("schema_version") == 2
            if is_full:
                from quant_service.full import MixedPanel
                from .full_train import train_full_candidate, training_hash

            panel = (MixedPanel if is_full else SnapshotPanel)(
                snapshot,
                rows,
                expected_hash=request["snapshot_hash"],
                now=now,
                max_age_days=request["max_age_days"],
                lookback=request["lookback"],
                min_returns=request["min_returns"],
            )
            cutoff = date.fromisoformat(request["training_cutoff"])
            if is_full:
                if str(cutoff) != panel.selection_state()["training_cutoff"]:
                    raise ValueError(
                        "Full training cutoff conflicts with the fit schedule"
                    )
                _, _, provenance = panel.inputs()
                provenance |= {
                    "trainer": "phase1-full-native-ensemble-v1",
                    "feature_schema_hash": canonical_hash(
                        {
                            "feature_schema_version": "phase1-full-features-v1",
                            "feature_names": phase1.FEATURES,
                        }
                    ),
                    "training_data_hash": training_hash(panel),
                }
            else:
                training = panel.training_data(cutoff)
                _, _, provenance = panel.inputs()
                provenance |= {
                    "trainer": "quant-model-worker-v1",
                    "feature_schema_hash": canonical_hash(FEATURE_DEFINITION),
                    "training_data_hash": canonical_hash(
                        TrainingData.model_validate(training).model_dump(mode="json")
                    ),
                }
        # Training and artifact creation occur under the fenced job transaction.
        # A lost worker cannot overwrite a candidate already registered by recovery.
        with queue.sessions() as session:
            fenced = session.execute(
                update(TrainingJob)
                .where(
                    TrainingJob.id == job.id,
                    TrainingJob.status == "RUNNING",
                    TrainingJob.lease_token == job.lease_token,
                    TrainingJob.lease_until > now,
                )
                .values(updated_at=now)
            )
            if fenced.rowcount != 1:
                session.rollback()
                return True
            existing = session.scalar(
                select(Model).where(Model.training_job_id == job.id)
            )
            if existing:
                result = {"model_id": existing.id}
            else:
                root = Path(directory) / job.id
                receipt = root / "candidate-receipt.json"
                if receipt.exists():
                    saved = json.loads(receipt.read_text())
                    if saved["body_hash"] != job.body_hash:
                        raise ValueError("Training receipt conflict")
                    local = saved["reference"]
                else:
                    if is_asset:
                        local = train_asset_candidate(root, panel, state["fit_epoch"])
                    else:
                        local = (
                            train_full_candidate(root, panel, cutoff)
                            if is_full
                            else train_candidate(root, training)
                        )
                    # Full bytes are complete before the atomic receipt rename.
                    _durable_receipt(
                        root,
                        "candidate-receipt.json",
                        {
                            "body_hash": job.body_hash,
                            "reference": local,
                            "provenance": provenance,
                        },
                    )
                ref = {"file": job.id + "/" + local["file"], "sha256": local["sha256"]}
                result = _register(session, directory, job, ref, provenance)
            session.execute(
                update(TrainingJob)
                .where(TrainingJob.id == job.id)
                .values(
                    status="SUCCEEDED",
                    result=result,
                    safe_error=None,
                    lease_token=None,
                    lease_until=None,
                    updated_at=now,
                )
            )
            session.commit()
    except (ValueError, KeyError):
        queue.fail(job, "TRAINING_INVALID", now=now, permanent=True)
    except httpx.HTTPError:
        queue.fail(job, "MARKET_UNAVAILABLE", now=now)
    except Exception:
        queue.fail(job, "TRAINING_UNAVAILABLE", now=now)
    return True


def materialize_approvals(sessions, directory):
    count = 0
    with sessions() as session:
        models = session.scalars(
            select(Model)
            .where(Model.status == "APPROVED", Model.approved_ref.is_(None))
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        for model in models:
            try:
                with session.begin_nested():
                    review = session.scalar(
                        select(Review).where(Review.model_id == model.id)
                    )
                    candidate = validated_candidate(directory, model.candidate_ref)
                    if review is None or review.decision != "APPROVED":
                        raise ValueError("Recorded approval required")
                    root = Path(directory) / Path(model.candidate_ref["file"]).parent
                    receipt = root / "approval-receipt.json"
                    if receipt.exists():
                        local = json.loads(receipt.read_text())
                    else:
                        # The persisted decision, including actor, authorizes this one artifact.
                        local = approve_candidate(
                            root,
                            {
                                "file": Path(model.candidate_ref["file"]).name,
                                "sha256": model.candidate_ref["sha256"],
                            },
                            reviewer=review.actor,
                            registry_review=True,
                        )
                        _durable_receipt(root, "approval-receipt.json", local)
                    approved = parse_manifest(read_artifact(root, local))
                    if (
                        approved.model_id != model.id
                        or approved.status != "APPROVED"
                        or approved.approved_by != review.actor
                        or (
                            candidate.schema_version in (3, 4, 5)
                            and approved.model_dump(
                                exclude={"status", "approved_at", "approved_by"}
                            )
                            != candidate.model_dump(
                                exclude={"status", "approved_at", "approved_by"}
                            )
                        )
                    ):
                        raise ValueError("Approval conflict")
                    model.approved_ref = {
                        "file": str(
                            Path(model.candidate_ref["file"]).parent / local["file"]
                        ),
                        "sha256": local["sha256"],
                    }
                count += 1
            except Exception:
                # One corrupt/unavailable candidate cannot starve healthy approvals.
                # The persisted decision stays immutable; resolution fails closed.
                continue
        session.commit()
    return count


class CredentialMarketReader:
    def load(self, snapshot_id, snapshot_hash):
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.post(
                os.environ["OIDC_TOKEN_URL"],
                data={
                    "grant_type": "client_credentials",
                    "client_id": "ml-worker",
                    "client_secret": os.environ["ML_MARKET_READER_CLIENT_SECRET"],
                    "scope": "market:snapshot:read",
                },
            )
            response.raise_for_status()
            return MarketReader(
                os.environ["MARKET_API_URL"],
                response.json()["access_token"],
                client=client,
            ).load(snapshot_id, snapshot_hash)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    from .runtime import sessions_from_env
    from service_observability import configure

    configure("ml-worker")
    sessions = sessions_from_env()
    queue = TrainingQueue(sessions)
    while True:
        try:
            materialize_approvals(sessions, os.environ["ML_ARTIFACT_DIRECTORY"])
        except Exception:
            pass  # Retry materialization; no raw exceptions or secrets in logs.
        worked = process_one(
            queue, os.environ["ML_ARTIFACT_DIRECTORY"], CredentialMarketReader()
        )
        if args.once:
            break
        if not worked:
            time.sleep(2)


if __name__ == "__main__":
    main()
