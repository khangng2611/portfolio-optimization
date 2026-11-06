"""Publish snapshot-derived immutable bundles outside Quant serving requests."""

import argparse
from datetime import datetime, time, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx

from portfolio_contracts import canonical_hash, utcnow
from .ml import ArtifactRef, ModelManifest, infer, read_artifact
from .model_worker import train_candidate
from .snapshot_inputs import SnapshotPanel


class MarketReader:
    def __init__(self, base_url, token, *, client=None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = client or httpx.Client(timeout=15, follow_redirects=False)

    def load(self, snapshot_id, expected_hash):
        identity = str(UUID(str(snapshot_id)))
        values = []
        for suffix in ["", "/observations"]:
            response = self.client.get(
                f"{self.base_url}/internal/v1/market/snapshots/{identity}{suffix}",
                headers={"Authorization": "Bearer " + self.token},
            )
            response.raise_for_status()
            if len(response.content) > 32_000_000:
                raise ValueError("Market snapshot response too large")
            values.append(response.json())
        if values[0]["id"] != identity or values[0]["content_hash"] != expected_hash:
            raise ValueError("Market response does not match requested snapshot pin")
        return tuple(values)


def _intent_filename(intent):
    return "market-intent-" + hashlib.sha256(intent.encode()).hexdigest() + ".json"


def _write_catalog(root, catalog):
    temporary = root / f"catalog-{uuid4()}.tmp"
    with temporary.open("x") as stream:
        json.dump(catalog, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(root / "catalog.json")
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _insert_publication(root, catalog, reference, value):
    # Recovery of an old intent must not replace a newer publication as the
    # latest resolver input. Existing history and hash pins remain untouched.
    position = 0
    decision = datetime.fromisoformat(value["decision_at"])
    for index, entry in enumerate(catalog["bundles"]):
        if entry.get("universe_id") != value["universe_id"]:
            continue
        previous = json.loads(
            read_artifact(root, {key: entry[key] for key in ("file", "sha256")})
        )
        if datetime.fromisoformat(previous["decision_at"]) > decision:
            position = index + 1
        else:
            break
    catalog["bundles"].insert(
        position,
        reference
        | {
            "universe_id": value["universe_id"],
            "bundle_id": value["bundle_id"],
            "demo": value["demo"],
            "publication_key": value["publication_key"],
        },
    )


def _recover_locked(root, intent, intent_hash, catalog):
    filename = _intent_filename(intent)
    path = root / filename
    if not path.exists():
        return None
    content = read_artifact(
        root,
        {"file": filename, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
    )
    value = json.loads(content)
    if (
        value.get("publication_intent") != intent
        or value.get("publication_intent_hash") != intent_hash
    ):
        raise ValueError("Publication intent pins conflict")
    reference = {"file": filename, "sha256": hashlib.sha256(content).hexdigest()}
    indexed = next(
        (entry for entry in catalog["bundles"] if entry["file"] == filename), None
    )
    if indexed is not None and indexed["sha256"] != reference["sha256"]:
        raise ValueError("Publication intent artifact changed")
    if indexed is None:
        _insert_publication(root, catalog, reference, value)
        _write_catalog(root, catalog)
    return reference | {"bundle_id": value["bundle_id"]}


def recover_publication(directory, publication_intent, intent_hash):
    """Return immutable committed output, repairing an interrupted catalog update.

    Expired output is still the same historical pin; serving checks its freshness.
    """
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".catalog.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = root / "catalog.json"
        catalog = json.loads(path.read_text()) if path.exists() else {"bundles": []}
        return _recover_locked(root, publication_intent, intent_hash, catalog)


def publish_snapshot(
    directory,
    snapshot,
    observations,
    *,
    expected_hash,
    universe_id,
    model=None,
    now=None,
    max_age_days=7,
    lookback=252,
    min_returns=60,
    renew=False,
    publication_intent=None,
    intent_hash=None,
):
    import re

    if not re.fullmatch(r"[A-Z0-9_-]{1,64}", universe_id) or universe_id == "DEMO":
        raise ValueError("A distinct registered real-data universe is required")
    if (publication_intent is None) != (intent_hash is None):
        raise ValueError("Publication intent and hash must be supplied together")
    if publication_intent:
        recovered = recover_publication(directory, publication_intent, intent_hash)
        if recovered:
            return recovered
    now = now or utcnow()
    panel = SnapshotPanel(
        snapshot,
        observations,
        expected_hash=expected_hash,
        now=now,
        max_age_days=max_age_days,
        lookback=lookback,
        min_returns=min_returns,
    )
    numerical, features, provenance = panel.inputs()
    model = ArtifactRef.model_validate(model).model_dump() if model else None
    request_key = canonical_hash(
        {
            "snapshot_hash": expected_hash,
            "universe_id": universe_id,
            "model": model,
            "builder": "market-snapshot-bundle-v1",
            "lookback": lookback,
            "min_returns": min_returns,
            "max_age_days": max_age_days,
        }
    )
    valid_until = min(
        now + timedelta(hours=24),
        datetime.combine(
            panel.dates[-1] + timedelta(days=max_age_days),
            time.max,
            tzinfo=timezone.utc,
        ),
    )
    value = {
        "schema_version": 1,
        "bundle_id": _intent_filename(publication_intent)[:-5]
        if publication_intent
        else "market-" + str(uuid4()),
        "universe_id": universe_id,
        "snapshot_id": snapshot["id"],
        "model_bundle_id": model["sha256"] if model else None,
        "as_of_date": panel.dates[-1].isoformat(),
        "decision_at": now.isoformat(),
        "valid_until": valid_until.isoformat(),
        "demo": False,
        "strategies": ["EW", "MVO"],
        "numerical": numerical,
        "features": features,
        "provenance": provenance,
        "publication_key": request_key,
    }
    if publication_intent:
        value["publication_intent"] = publication_intent
        value["publication_intent_hash"] = intent_hash
    if model:
        manifest = ModelManifest.model_validate_json(read_artifact(directory, model))
        if manifest.schema_version != 2 or manifest.demo:
            raise ValueError(
                "Real snapshot serving requires a provenance-complete v2 model"
            )
        value["ml_inference"] = features | {"manifest": model}
        infer(directory, value)
        value["strategies"].append("BL_ML")
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".catalog.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        catalog_file = root / "catalog.json"
        catalog = (
            json.loads(catalog_file.read_text())
            if catalog_file.exists()
            else {"bundles": []}
        )
        if publication_intent:
            recovered = _recover_locked(root, publication_intent, intent_hash, catalog)
            if recovered:
                return recovered
        for entry in catalog["bundles"]:
            if entry.get("universe_id") and entry["universe_id"] != universe_id:
                continue
            if "publication_key" in entry and (
                renew or entry["publication_key"] != request_key
            ):
                continue
            content = read_artifact(
                root, {key: entry[key] for key in ("file", "sha256")}
            )
            old = json.loads(content)
            entry.update(
                {
                    "universe_id": old["universe_id"],
                    "bundle_id": old["bundle_id"],
                    "demo": old["demo"],
                    "publication_key": old.get("publication_key"),
                }
            )
            if (
                old.get("publication_key") == request_key
                and not renew
                and not publication_intent
            ):
                if datetime.fromisoformat(old["valid_until"]) <= now:
                    raise ValueError(
                        "Publication expired; renew explicitly after freshness validation"
                    )
                return {
                    "file": entry["file"],
                    "sha256": entry["sha256"],
                    "bundle_id": old["bundle_id"],
                }
        content = json.dumps(value, sort_keys=True, allow_nan=False).encode()
        filename = value["bundle_id"] + ".json"
        # A crash cannot leave a truncated final artifact. Link publishes a fully
        # fsynced temporary inode without ever overwriting an immutable bundle.
        temporary_bundle = root / f"bundle-{uuid4()}.tmp"
        with temporary_bundle.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_bundle, root / filename)
        temporary_bundle.unlink()
        reference = {"file": filename, "sha256": hashlib.sha256(content).hexdigest()}
        _insert_publication(root, catalog, reference, value)
        _write_catalog(root, catalog)
        return reference | {"bundle_id": value["bundle_id"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--snapshot-hash", required=True)
    commands = parser.add_subparsers(dest="operation", required=True)
    train = commands.add_parser("train")
    train.add_argument("--cutoff", required=True)
    build = commands.add_parser("build")
    build.add_argument("--universe-id", required=True)
    build.add_argument("--model-file")
    build.add_argument("--model-sha256")
    build.add_argument("--renew", action="store_true")
    args = parser.parse_args()
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        response = client.post(
            os.environ["OIDC_TOKEN_URL"],
            data={
                "grant_type": "client_credentials",
                "client_id": "quant-publisher",
                "client_secret": os.environ["MARKET_READER_CLIENT_SECRET"],
                "scope": "market:snapshot:read",
            },
        )
        response.raise_for_status()
        reader = MarketReader(
            os.environ["MARKET_API_URL"], response.json()["access_token"], client=client
        )
        snapshot, rows = reader.load(args.snapshot_id, args.snapshot_hash)
        if args.operation == "train":
            from datetime import date

            panel = SnapshotPanel(snapshot, rows, expected_hash=args.snapshot_hash)
            result = train_candidate(
                args.directory, panel.training_data(date.fromisoformat(args.cutoff))
            )
        else:
            if bool(args.model_file) != bool(args.model_sha256):
                raise ValueError("Model file/hash must be supplied together")
            model = (
                {"file": args.model_file, "sha256": args.model_sha256}
                if args.model_file
                else None
            )
            result = publish_snapshot(
                args.directory,
                snapshot,
                rows,
                expected_hash=args.snapshot_hash,
                universe_id=args.universe_id,
                model=model,
                renew=args.renew,
            )
        print(json.dumps(result))


if __name__ == "__main__":
    main()
