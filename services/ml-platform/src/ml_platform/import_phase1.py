"""Register a staged native Phase 1 manifest using the ML worker's local credentials."""

import argparse
import json
import os
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from quant_service.ml import ArtifactRef
from .models import Model
from .runtime import sessions_from_env
from .worker import validated_candidate


def import_candidate(sessions, directory, reference):
    ref = ArtifactRef.model_validate(reference).model_dump()
    manifest = validated_candidate(directory, ref)
    if manifest.schema_version not in (3, 4, 5):
        raise ValueError("Offline import requires a Phase 1 candidate")
    expected = f"phase1-{manifest.model_id}/manifest.json"
    if ref["file"] != expected or (Path(directory).resolve() / expected).resolve() != (
        Path(directory).resolve() / expected
    ):
        raise ValueError("Stage the candidate at its canonical Phase 1 manifest path")
    with sessions() as session:
        try:
            session.add(
                Model(
                    id=manifest.model_id,
                    status="CANDIDATE",
                    manifest=manifest.model_dump(mode="json"),
                    candidate_ref=ref,
                    provenance={
                        "source": "phase1-offline-fit",
                        "baseline_run_id": manifest.baseline_run_id,
                        "baseline_manifest_sha256": manifest.baseline_manifest_sha256,
                        "training_data_hash": manifest.training_data_hash,
                        "point_in_time_certified": False,
                    },
                )
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            existing = session.get(Model, manifest.model_id)
            if (
                existing is None
                or existing.training_job_id is not None
                or existing.candidate_ref != ref
            ):
                raise ValueError(
                    "Phase 1 model ID already registered with different pins"
                ) from None
    return manifest.model_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", required=True, help="Path relative to ML_ARTIFACT_DIRECTORY"
    )
    parser.add_argument(
        "--sha256", required=True, help="Expected candidate manifest SHA-256"
    )
    args = parser.parse_args()
    model_id = import_candidate(
        sessions_from_env(),
        os.environ["ML_ARTIFACT_DIRECTORY"],
        {"file": args.manifest, "sha256": args.sha256},
    )
    print(json.dumps({"model_id": model_id}))


if __name__ == "__main__":
    main()
