"""Read-only prepared input adapter; a future Market/ML resolver can replace it."""

import hashlib
import json
from pathlib import Path

from portfolio_contracts import ModelUnavailable, ReadyInput, utcnow
from .ml import infer


class ArtifactCatalog:
    def __init__(self, directory, *, allow_demo=False):
        self.directory = Path(directory).resolve()
        self.allow_demo = allow_demo

    def _entries(self, *, universe_id=None, bundle_id=None, skip_universes=None):
        try:
            catalog = json.loads((self.directory / "catalog.json").read_text())
            for entry in catalog["bundles"]:
                if (
                    skip_universes is not None
                    and entry.get("universe_id") in skip_universes
                ):
                    continue
                if (
                    not self.allow_demo
                    and entry.get("demo")
                    and not universe_id
                    and not bundle_id
                ):
                    continue
                if (
                    universe_id
                    and entry.get("universe_id")
                    and entry["universe_id"] != universe_id
                ):
                    continue
                if (
                    bundle_id
                    and entry.get("bundle_id")
                    and entry["bundle_id"] != bundle_id
                ):
                    continue
                path = (self.directory / entry["file"]).resolve()
                if not path.is_relative_to(self.directory) or path.suffix != ".json":
                    raise ValueError("Invalid artifact path")
                if path.stat().st_size > 2_000_000:
                    raise ValueError("Artifact too large")
                data = path.read_bytes()
                value = json.loads(data)
                if (
                    skip_universes is not None
                    and value["universe_id"] in skip_universes
                ):
                    continue
                if universe_id and value["universe_id"] != universe_id:
                    continue
                if bundle_id and value["bundle_id"] != bundle_id:
                    continue
                if (
                    not universe_id
                    and not bundle_id
                    and value.get("demo")
                    and not self.allow_demo
                ):
                    continue
                checksum = hashlib.sha256(data).hexdigest()
                if checksum != entry["sha256"]:
                    raise ValueError("Artifact checksum mismatch")
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
                    provenance=value.get("provenance"),
                )
                yield value, ready
        except (OSError, KeyError, TypeError) as exc:
            raise ValueError("Prepared input catalog unavailable") from exc

    def _check(self, value, ready, strategy):
        if ready.valid_until <= utcnow():
            raise ValueError("Prepared input expired")
        if strategy not in value["strategies"]:
            if strategy == "BL_ML":
                raise ModelUnavailable("No compatible model strategy")
            raise ValueError("Strategy has no compatible prepared inputs")
        if strategy == "BL_ML" and value.get("ml_inference"):
            infer(self.directory, value, allow_demo=self.allow_demo)
            return
        if strategy == "BL_ML" and (
            not ready.model_bundle_id
            or value.get("model_status") != "APPROVED"
            or not value["numerical"].get("views_p")
        ):
            raise ModelUnavailable("Approved ML model/views unavailable")

    def ready(self, universe_id, strategy):
        for value, ready in self._entries(universe_id=universe_id):
            if value["universe_id"] == universe_id:
                self._check(value, ready, strategy)
                return ready
        raise ValueError("No ready input for requested universe")

    def load(self, pinned: ReadyInput, strategy):
        for value, ready in self._entries(bundle_id=pinned.bundle_id):
            if ready.bundle_id == pinned.bundle_id:
                if ready.model_dump() != pinned.model_dump():
                    raise ValueError(
                        "Pinned input no longer matches immutable artifact"
                    )
                self._check(value, ready, strategy)
                if strategy == "BL_ML" and value.get("ml_inference"):
                    numerical, provenance = infer(
                        self.directory, value, allow_demo=self.allow_demo
                    )
                    return numerical | {"inference_provenance": provenance}
                return value["numerical"]
        raise ValueError("Pinned artifact unavailable")

    def universes(self):
        values, seen = [], set()
        for value, ready in self._entries(skip_universes=seen):
            identity = value["universe_id"]
            if identity in seen:
                continue
            seen.add(identity)
            if ready.valid_until <= utcnow():
                continue
            values.append(
                {
                    "universe_id": identity,
                    "asset_ids": ready.asset_ids,
                    "as_of_date": ready.as_of_date,
                    "demo": ready.demo,
                    "bundle_id": ready.bundle_id,
                    "strategies": value["strategies"],
                    "provenance": ready.provenance,
                }
            )
        return values
