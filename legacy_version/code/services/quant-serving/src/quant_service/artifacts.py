"""Read-only prepared input adapter; a future Market/ML resolver can replace it."""

import hashlib
import json
from pathlib import Path

from portfolio_contracts import ReadyInput, utcnow


class ArtifactCatalog:
    def __init__(self, directory, *, allow_demo=False):
        self.directory = Path(directory).resolve()
        self.allow_demo = allow_demo

    def _entries(self):
        try:
            catalog = json.loads((self.directory / "catalog.json").read_text())
            for entry in catalog["bundles"]:
                path = (self.directory / entry["file"]).resolve()
                if not path.is_relative_to(self.directory) or path.suffix != ".json":
                    raise ValueError("Invalid artifact path")
                if path.stat().st_size > 2_000_000:
                    raise ValueError("Artifact too large")
                data = path.read_bytes()
                checksum = hashlib.sha256(data).hexdigest()
                if checksum != entry["sha256"]:
                    raise ValueError("Artifact checksum mismatch")
                value = json.loads(data)
                if value["schema_version"] != 1 or (
                    value["demo"] and not self.allow_demo
                ):
                    raise ValueError("Artifact is not approved for this runtime")
                ready = ReadyInput(
                    bundle_id=value["bundle_id"],
                    bundle_hash=checksum,
                    snapshot_id=value["snapshot_id"],
                    model_bundle_id=value.get("model_bundle_id"),
                    asset_ids=value["numerical"]["asset_ids"],
                    as_of_date=value["as_of_date"],
                    valid_until=value["valid_until"],
                    demo=value["demo"],
                )
                yield value, ready
        except (OSError, KeyError, TypeError) as exc:
            raise ValueError("Prepared input catalog unavailable") from exc

    def _check(self, value, ready, strategy):
        if ready.valid_until <= utcnow():
            raise ValueError("Prepared input expired")
        if strategy not in value["strategies"]:
            raise ValueError("Strategy has no compatible prepared inputs")
        if strategy == "BL_ML" and (
            not ready.model_bundle_id
            or value.get("model_status") != "APPROVED"
            or not value["numerical"].get("views_p")
        ):
            raise ValueError("Approved ML model/views unavailable")

    def ready(self, universe_id, strategy):
        for value, ready in self._entries():
            if value["universe_id"] == universe_id:
                self._check(value, ready, strategy)
                return ready
        raise ValueError("No ready input for requested universe")

    def load(self, pinned: ReadyInput, strategy):
        for value, ready in self._entries():
            if ready.bundle_id == pinned.bundle_id:
                if ready.model_dump() != pinned.model_dump():
                    raise ValueError(
                        "Pinned input no longer matches immutable artifact"
                    )
                self._check(value, ready, strategy)
                return value["numerical"]
        raise ValueError("Pinned artifact unavailable")
