"""Shared prepared resource publication and exact-pin selection reader."""

from datetime import datetime, time, timedelta
import json
from pathlib import Path
from uuid import uuid4

from portfolio_contracts import ReadyInput, canonical_hash, utcnow
from portfolio_core.assets import ASSET_IDS
from .full import TZ
from .ml import ArtifactRef, parse_manifest, read_artifact, validate_native_files
from .selection_panel import SelectionPanel, SelectionDataError, save_panel, load_panel

UNIVERSE = "VN_USER_SELECTION"


def publish_selection_resource(
    directory,
    snapshot,
    observations,
    *,
    expected_hash,
    universe_id,
    model=None,
    now=None,
    max_age_days=7,
    renew=False,
    publication_intent=None,
    intent_hash=None,
):
    from .snapshot_publisher import _commit_publication, _intent_filename

    now = now or utcnow()
    if max_age_days != 7:
        raise ValueError("Selection freshness must remain 7 days")
    if universe_id != UNIVERSE or snapshot.get("schema_version") != 3:
        raise ValueError("Selection source/resource family mismatch")
    panel = SelectionPanel(snapshot, observations, expected_hash=expected_hash, now=now)
    if model:
        model = ArtifactRef.model_validate(model).model_dump()
        manifest = parse_manifest(read_artifact(directory, model))
        if (
            manifest.schema_version != 5
            or manifest.status != "APPROVED"
            or manifest.demo
        ):
            raise ValueError("Selection requires an approved asset ensemble v5")
        if manifest.trained_at > now or manifest.approved_at > now:
            raise ValueError("Selection model unavailable at publication")
        validate_native_files(
            (Path(directory) / model["file"]).resolve().parent, manifest, load=True
        )
        from .selection_ready import fit_index
        from .asset_ensemble import validate_coverage

        validate_coverage(manifest, [], panel.dates[fit_index(panel.decision_index)])
    name, digest = save_panel(directory, panel)
    request_key = canonical_hash(
        dict(
            snapshot_hash=expected_hash,
            universe_id=UNIVERSE,
            model=model,
            builder="user-selection-market-v1",
            max_age_days=7,
        )
    )
    value = dict(
        schema_version=2,
        family="user-selection-market-v1",
        bundle_id=_intent_filename(publication_intent)[:-5]
        if publication_intent
        else "market-" + str(uuid4()),
        universe_id=UNIVERSE,
        snapshot_id=snapshot["id"],
        model_bundle_id=model["sha256"] if model else None,
        as_of_date=str(panel.dates[panel.decision_index]),
        decision_at=now.isoformat(),
        valid_until=min(
            now + timedelta(hours=24),
            datetime.combine(
                panel.dates[panel.decision_index] + timedelta(days=8), time(), TZ
            ),
        ).isoformat(),
        demo=False,
        strategies=[],
        asset_ids=list(ASSET_IDS),
        model=model,
        panel=dict(file=name, sha256=digest),
        provenance=dict(
            snapshot_id=snapshot["id"],
            snapshot_hash=expected_hash,
            panel_hash=panel.panel_hash,
            data_origin="real",
            return_unit="daily_simple_fraction",
            data_policy_id=snapshot["availability_policy"],
            max_data_age_days=7,
            historical_publication_verified=False,
        ),
        publication_key=request_key,
    )
    if publication_intent:
        value.update(
            publication_intent=publication_intent, publication_intent_hash=intent_hash
        )
    return _commit_publication(
        directory, value, request_key, now, renew, publication_intent, intent_hash
    )


class SelectionCatalog:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()

    def _entries(self):
        try:
            entries = json.loads((self.directory / "catalog.json").read_text())[
                "bundles"
            ]
        except (OSError, KeyError, TypeError):
            raise ValueError("Selection resource unavailable") from None
        for entry in entries:
            if entry.get("universe_id") != UNIVERSE:
                continue
            value = json.loads(
                read_artifact(self.directory, {k: entry[k] for k in ("file", "sha256")})
            )
            if (
                value.get("schema_version") != 2
                or value.get("family") != "user-selection-market-v1"
                or value.get("asset_ids") != list(ASSET_IDS)
                or value.get("universe_id") != UNIVERSE
                or value.get("demo") is not False
                or value.get("strategies") != []
            ):
                raise ValueError("Invalid selection resource")
            ready = ReadyInput(
                bundle_id=value["bundle_id"],
                bundle_hash=entry["sha256"],
                snapshot_id=value["snapshot_id"],
                model_bundle_id=value.get("model_bundle_id"),
                asset_ids=value["asset_ids"],
                as_of_date=value["as_of_date"],
                valid_until=value["valid_until"],
                demo=False,
                provenance=value["provenance"],
            )
            yield value, ready

    def latest(self):
        for value, ready in self._entries():
            return ready
        raise ValueError("No selection resource")

    def load_resource(self, pin):
        for value, ready in self._entries():
            if ready.bundle_id != pin.bundle_id:
                continue
            if ready.model_dump() != pin.model_dump():
                raise ValueError("Selection resource pin mismatch")
            panel = load_panel(
                self.directory, value["panel"]["file"], value["panel"]["sha256"]
            )
            if (
                panel.snapshot["id"] != str(ready.snapshot_id)
                or panel.snapshot["content_hash"] != ready.provenance["snapshot_hash"]
                or panel.snapshot["availability_policy"]
                != ready.provenance["data_policy_id"]
            ):
                raise ValueError("Selection snapshot pin mismatch")
            return value, panel
        raise ValueError("Pinned selection resource unavailable")

    def model(self, value, *, load=False):
        ref = value.get("model")
        if not ref:
            raise SelectionDataError("MODEL_UNAVAILABLE")
        if ref["sha256"] != value["model_bundle_id"]:
            raise ValueError("Selection model pin mismatch")
        manifest = parse_manifest(read_artifact(self.directory, ref))
        if (
            manifest.schema_version != 5
            or manifest.status != "APPROVED"
            or manifest.demo
        ):
            raise SelectionDataError("MODEL_REVIEW_PENDING")
        from .snapshot_inputs import timestamp

        if max(manifest.trained_at, manifest.approved_at) > timestamp(
            value["decision_at"]
        ):
            raise ValueError("Selection model unavailable at publication")
        folder = (self.directory / ref["file"]).resolve().parent
        validate_native_files(folder, manifest, load=load)
        return folder, manifest

    def asset_status(self, now=None):
        now = now or utcnow()
        pin = self.latest()
        value, panel = self.load_resource(pin)
        t = panel.index_at(now)
        try:
            _, model = self.model(value)
        except SelectionDataError:
            model = None
        statuses = {}
        for asset in ASSET_IDS:
            coverage = panel.snapshot["asset_coverage"][asset]
            status = dict(
                data_status="MISSING",
                checked_at=now.isoformat(),
                latest_observation_date=coverage.get("latest_observation_date"),
                ml_status="COVERED"
                if model and asset in model.asset_ids
                else "NOT_COVERED",
                approved_model_id=str(model.model_id) if model else None,
                model_manifest_hash=value["model_bundle_id"] if model else None,
            )
            if coverage["status"] == "QUARANTINED":
                status["data_status"] = "QUARANTINED"
            elif coverage["status"] == "AVAILABLE":
                try:
                    item = panel.availability(asset, t, now)
                    status.update(
                        eligible_observation_date=item["observation_date"],
                        available_at=item["available_at"],
                        age_days=item["age_days"],
                    )
                    status["data_status"] = (
                        "FRESH"
                        if 0 <= item["age_days"] <= 7
                        and max(
                            panel.known_seconds[t, panel.ids.index(asset)],
                            panel.policy_seconds[t, panel.ids.index(asset)],
                        )
                        <= now.timestamp()
                        else "STALE"
                    )
                except SelectionDataError:
                    pass
            if model and asset in model.covered_asset_ids:
                from .selection_ready import check_equity_model_inputs

                try:
                    check_equity_model_inputs(model, panel, [asset], t)
                except (ValueError, KeyError, TypeError):
                    status["ml_status"] = "NOT_COVERED"
            statuses[asset] = status
        return statuses
