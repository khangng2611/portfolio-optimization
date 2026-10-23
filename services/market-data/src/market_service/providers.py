"""Hash-pinned import registry. Never import legacy crawler globals or paths."""

import csv
import hashlib
import io
import json
from pathlib import Path

from portfolio_contracts.market import Observation


class CsvProvider:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()

    def spec(self, dataset_id):
        registry = json.loads((self.directory / "catalog.json").read_text())
        spec = registry[dataset_id]
        self._path(spec)
        if len(spec["sha256"]) != 64:
            raise ValueError("Dataset checksum required")
        return spec

    def _path(self, spec):
        path = (self.directory / spec["path"]).resolve()
        if path == self.directory or not path.is_relative_to(self.directory):
            raise ValueError("Dataset path escapes registry directory")
        return path

    def fetch(self, spec):
        path = self._path(spec)
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Dataset exceeds 4 MiB import limit")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
            raise ValueError("Dataset checksum mismatch")
        rows = []
        for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
            if row.get("symbol") and row["symbol"] != spec["asset_id"]:
                raise ValueError("Dataset contains another asset")
            rows.append(
                Observation(
                    asset_id=spec["asset_id"],
                    kind=spec["kind"],
                    observation_date=row["date"],
                    price=row[spec.get("price_column", "price")],
                    source_unit=spec["source_unit"],
                    provider=spec["provider"],
                    published_at=row.get("published_at") or None,
                    price_type=spec.get(
                        "price_type", "nav" if spec["kind"] == "fund" else "close"
                    ),
                )
            )
            if len(rows) > 5000:
                raise ValueError("Dataset exceeds 5000 observation limit")
        if not rows:
            raise ValueError("Dataset contains no observations")
        return rows
