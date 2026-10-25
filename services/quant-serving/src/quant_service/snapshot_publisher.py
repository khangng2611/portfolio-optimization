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
):
    import re

    if not re.fullmatch(r"[A-Z0-9_-]{1,64}", universe_id) or universe_id == "DEMO":
        raise ValueError("A distinct registered real-data universe is required")
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
        "bundle_id": "market-" + str(uuid4()),
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
            if old.get("publication_key") == request_key and not renew:
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
        with (root / filename).open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        reference = {"file": filename, "sha256": hashlib.sha256(content).hexdigest()}
        catalog["bundles"].insert(
            0,
            reference
            | {
                "universe_id": universe_id,
                "bundle_id": value["bundle_id"],
                "demo": False,
                "publication_key": request_key,
            },
        )
        temporary = root / f"catalog-{uuid4()}.tmp"
        with temporary.open("x") as stream:
            json.dump(catalog, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(catalog_file)
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
