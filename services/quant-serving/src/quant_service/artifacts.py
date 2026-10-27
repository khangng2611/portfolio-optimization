"""Read-only prepared input adapter; a future Market/ML resolver can replace it."""

import hashlib
import json
import re
from datetime import date
from pathlib import Path

from portfolio_contracts import ModelUnavailable, ReadyInput, utcnow
from portfolio_core import validate_numerical_inputs
from .ml import infer


class ArtifactCatalog:
    def __init__(self, directory, *, allow_demo=False):
        self.directory = Path(directory).resolve()
        self.allow_demo = allow_demo

    def _entries(
        self, *, universe_id=None, bundle_id=None, skip_universes=None, entries=None
    ):
        try:
            if entries is None:
                entries = json.loads((self.directory / "catalog.json").read_text())[
                    "bundles"
                ]
            for entry in entries:
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
            return infer(self.directory, value, allow_demo=self.allow_demo)
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

    @staticmethod
    def _readiness_result(universe_id, checked_at, reason, *, ready=None):
        if not isinstance(universe_id, str) or not re.fullmatch(
            r"[A-Z0-9_-]{1,64}", universe_id
        ):
            raise ValueError("Invalid universe identity")
        status = {"READY": "READY", "INPUT_EXPIRED": "EXPIRED"}.get(
            reason, "UNAVAILABLE"
        )
        provenance = ready.provenance or {} if ready is not None else {}
        origin = provenance.get("data_origin", "unverified")
        if ready is not None and ready.demo:
            origin = "synthetic"
        if origin not in {"real", "synthetic", "unverified"}:
            origin = "unverified"
        return {
            "universe_id": universe_id,
            "asset_ids": ready.asset_ids if ready is not None else [],
            "as_of_date": ready.as_of_date if ready is not None else None,
            "valid_until": ready.valid_until.isoformat() if ready is not None else None,
            "demo": ready.demo if ready is not None else False,
            "data_origin": origin,
            "status": status,
            "reason_code": reason,
            "strategies": [
                {"strategy": strategy, "available": False, "reason_code": reason}
                for strategy in ("EW", "MVO", "BL_ML")
            ],
            "next_action": {"READY": "NONE", "INPUT_EXPIRED": "REFRESH_DATA"}.get(
                reason, "CONTACT_OPERATOR"
            ),
            "checked_at": checked_at.isoformat(),
        }

    def _entry_readiness(self, entry, universe_id, checked_at):
        try:
            value, ready = next(self._entries(universe_id=universe_id, entries=[entry]))
            date.fromisoformat(ready.as_of_date)
            validate_numerical_inputs(value["numerical"])
            if not isinstance(value["strategies"], list) or any(
                strategy not in {"EW", "MVO", "BL_ML"}
                for strategy in value["strategies"]
            ):
                raise ValueError("Invalid strategies")
            if entry.get("universe_id", universe_id) != value["universe_id"]:
                raise ValueError("Catalog identity mismatch")
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            reason = (
                "INPUT_UNAVAILABLE"
                if isinstance(exc.__cause__, OSError)
                else "INPUT_INVALID"
            )
            return self._readiness_result(universe_id, checked_at, reason)
        reason = "INPUT_EXPIRED" if ready.valid_until <= checked_at else "READY"
        result = self._readiness_result(universe_id, checked_at, reason, ready=ready)
        if reason != "READY":
            return result
        for strategy in result["strategies"]:
            name = strategy["strategy"]
            try:
                # The same approval, hash, feature order and decision-time checks as execution.
                inferred = self._check(value, ready, name)
                if name == "BL_ML":
                    numerical = (
                        inferred[0] if inferred is not None else value["numerical"]
                    )
                    validate_numerical_inputs(numerical, strategy=name)
            except ModelUnavailable:
                code = "MODEL_UNAVAILABLE"
            except (ValueError, KeyError, TypeError, IndexError, OverflowError):
                code = "MODEL_INVALID" if name == "BL_ML" else "INPUT_INVALID"
            else:
                code = "READY"
            strategy.update(available=code == "READY", reason_code=code)
        return result

    def readiness(self, universe_id=None):
        """Safe diagnostics for each latest catalog entry, including expired inputs.

        Catalog order is publication order (newest first), as used by ready().
        An invalid or expired latest entry is never replaced by an older bundle.
        """
        checked_at = utcnow()
        try:
            entries = json.loads((self.directory / "catalog.json").read_text())[
                "bundles"
            ]
            if not isinstance(entries, list):
                raise ValueError("Invalid catalog")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if universe_id is None:
                raise ValueError("Prepared input catalog unavailable") from exc
            reason = (
                "INPUT_UNAVAILABLE" if isinstance(exc, OSError) else "INPUT_INVALID"
            )
            return self._readiness_result(universe_id, checked_at, reason)
        results, seen = [], set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Invalid catalog entry")
            identity, demo = entry.get("universe_id"), entry.get("demo")
            if identity is not None and not isinstance(identity, str):
                raise ValueError("Invalid universe identity")
            if identity in seen or (
                universe_id is not None and identity and identity != universe_id
            ):
                continue
            try:
                if demo is not None and not isinstance(demo, bool):
                    raise ValueError("Invalid demo metadata")
                # Legacy catalogs omit identity metadata; read only to identify the
                # entry. Nothing from this unverified value is returned publicly.
                if not identity or demo is None:
                    path = (self.directory / entry["file"]).resolve()
                    if (
                        not path.is_relative_to(self.directory)
                        or path.suffix != ".json"
                    ):
                        raise ValueError("Invalid artifact path")
                    if path.stat().st_size > 2_000_000:
                        raise ValueError("Artifact too large")
                    raw = json.loads(path.read_bytes())
                    identity = identity or raw["universe_id"]
                    demo = raw.get("demo")
                if not isinstance(demo, bool):
                    raise ValueError("Invalid demo metadata")
                if not isinstance(identity, str) or not re.fullmatch(
                    r"[A-Z0-9_-]{1,64}", identity
                ):
                    raise ValueError("Invalid universe identity")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                if identity is None:
                    if universe_id is None:
                        raise ValueError("Prepared input catalog unavailable") from exc
                    identity = universe_id
                reason = (
                    "INPUT_UNAVAILABLE" if isinstance(exc, OSError) else "INPUT_INVALID"
                )
                result = self._readiness_result(identity, checked_at, reason)
            else:
                if identity in seen or (
                    universe_id is not None and identity != universe_id
                ):
                    continue
                if universe_id is None and demo and not self.allow_demo:
                    seen.add(identity)
                    continue
                result = self._entry_readiness(entry, identity, checked_at)
            seen.add(identity)
            if universe_id is not None:
                return result
            results.append(result)
        if universe_id is not None:
            return self._readiness_result(universe_id, checked_at, "INPUT_UNAVAILABLE")
        return results
