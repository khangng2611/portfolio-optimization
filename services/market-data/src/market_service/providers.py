"""Trusted CSV adapter. The filesystem is inventory; SQL stores accepted pins."""

import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re

from pydantic import ValidationError
from portfolio_contracts.market import Observation
from .quality import QualityFailure, finding


class CsvProvider:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()

    def inventory_ids(self):
        registry = json.loads((self.directory / "catalog.json").read_text())
        if not isinstance(registry, dict) or len(registry) > 10000:
            raise ValueError("Invalid trusted inventory")
        return sorted(key for key in registry if re.fullmatch(r"[A-Z0-9_-]{1,64}", key))

    def spec(self, dataset_id):
        registry = json.loads((self.directory / "catalog.json").read_text())
        spec = registry[dataset_id]
        self._path(spec)
        if not re.fullmatch(r"[a-f0-9]{64}", spec["sha256"]):
            raise ValueError("Dataset checksum required")
        # Validate server-owned identity and interpretation before accepting a pin.
        Observation(
            asset_id=spec["asset_id"],
            kind=spec["kind"],
            observation_date=date.today(),
            price="1",
            source_unit=spec["source_unit"],
            provider=spec["provider"],
            data_origin=spec.get("data_origin", "unverified"),
            price_basis=spec.get("price_basis", "unverified"),
            price_type=spec.get(
                "price_type", "nav" if spec["kind"] == "fund" else "close"
            ),
        )
        return spec

    def _path(self, spec):
        path = (self.directory / spec["path"]).resolve()
        if path == self.directory or not path.is_relative_to(self.directory):
            raise ValueError("Dataset path escapes registry directory")
        return path

    def _raw(self, spec):
        path = self._path(spec)
        if path.stat().st_size > 4 * 1024 * 1024:
            raise QualityFailure([finding("LIMIT_EXCEEDED")])
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
            raise QualityFailure([finding("CHECKSUM_MISMATCH")])
        return raw

    def coverage(self, spec):
        """Observed range only; invalid rows remain the ingestion quality gate's job."""
        dates = []
        reader = csv.DictReader(io.StringIO(self._raw(spec).decode("utf-8-sig")))
        for index, row in enumerate(reader):
            if index >= 5000:
                break
            try:
                dates.append(date.fromisoformat(row.get("date", "")))
            except (TypeError, ValueError):
                pass
        return (min(dates), max(dates)) if dates else (None, None)

    def fetch(self, spec):
        raw = self._raw(spec)
        try:
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), strict=True)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)) or not {
                "date",
                spec.get("price_column", "price"),
            } <= set(fields):
                raise QualityFailure([finding("INVALID_ROW")])
            rows, findings = [], []
            for index, row in enumerate(reader, 2):
                if index > 5001:
                    raise QualityFailure([finding("LIMIT_EXCEEDED")], len(rows))
                if None in row or any(value is None for value in row.values()):
                    findings.append(finding("INVALID_ROW", index))
                    continue
                if row.get("symbol") and row["symbol"] != spec["asset_id"]:
                    findings.append(finding("ASSET_MISMATCH", index))
                    continue
                if row.get("source_unit") and row["source_unit"] != spec["source_unit"]:
                    findings.append(finding("UNIT_MISMATCH", index))
                    continue
                if row.get("price_basis") and row["price_basis"] != spec.get(
                    "price_basis", "unverified"
                ):
                    findings.append(finding("BASIS_MISMATCH", index))
                    continue
                try:
                    rows.append(
                        Observation(
                            asset_id=spec["asset_id"],
                            kind=spec["kind"],
                            observation_date=row["date"],
                            price=row[spec.get("price_column", "price")],
                            source_unit=spec["source_unit"],
                            provider=spec["provider"],
                            data_origin=spec.get("data_origin", "unverified"),
                            price_basis=spec.get("price_basis", "unverified"),
                            published_at=row.get("published_at") or None,
                            price_type=spec.get(
                                "price_type",
                                "nav" if spec["kind"] == "fund" else "close",
                            ),
                        )
                    )
                except ValidationError as exc:
                    publication = any(
                        e["loc"] == ("published_at",) or "Publication" in e["msg"]
                        for e in exc.errors()
                    )
                    findings.append(
                        finding(
                            "INVALID_KNOWN_AT" if publication else "INVALID_ROW", index
                        )
                    )
                if len(findings) >= 100:
                    break
            if findings:
                raise QualityFailure(findings, len(rows) + len(findings))
            if not rows:
                raise QualityFailure([finding("EMPTY_DATASET")])
            return rows
        except (UnicodeError, csv.Error) as exc:
            raise QualityFailure([finding("INVALID_SOURCE")]) from exc
