"""Operator-only atomic full-universe refresh, using trusted staged seed files.

python -m market_service.phase1_full --seed /datasets/refresh/full-phase1/seed.json \
    --directory /datasets/refresh/full-phase1
The seed contains {"assets": {"file": "assets_1.json", "sha256": ...},
"gold": {"file": "gold_archive_daily.csv", "sha256": ...}}.
"""

import argparse
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from portfolio_contracts import canonical_hash, utcnow
from .models import Actor, IngestionJob, QualityReport, RegisteredDataset
from .phase1_sources import (
    GOLD_PROVIDER,
    GOLD_SEED_HASH,
    VFF_PROVIDER,
    MixedSource,
    frozen_gold,
    normalize_gold_archive,
    normalize_fmarket,
    verify_vff_identity,
    equity_missing_sessions,
    EQUITY_GAP_EVIDENCE,
)
from .providers import CsvProvider
from .quality import QualityFailure, finding, validate_batch, report_json
from .refresh_provider import (
    ArtifactStore,
    KbsProvider,
    PROVIDER,
    BASE,
    completed_cutoff,
    normalize,
    normalized_csv,
    MAX_BYTES,
)
from .runtime import sessions_from_env
from .snapshots import build_full_snapshot, snapshot_json
from .workflow import persist_observations

ASSETS_SEED_HASH = "17f8dcdc12e5bcc85636de55aace06f5ac9a438e35f130ee0718cf813f8f2a42"
START = date(2020, 1, 14)


def read_seed(seed_path, store):
    seed_path = Path(seed_path).resolve()
    if (
        not seed_path.is_relative_to(store.directory)
        or seed_path.stat().st_size > MAX_BYTES
    ):
        raise ValueError("Seed must be staged under artifact directory")
    seed = json.loads(seed_path.read_bytes())
    raw = {}
    for key, required in [("assets", ASSETS_SEED_HASH), ("gold", GOLD_SEED_HASH)]:
        ref = seed[key]
        target = (store.directory / ref["file"]).resolve()
        if (
            not target.is_relative_to(store.directory)
            or target.stat().st_size > MAX_BYTES
        ):
            raise ValueError("Seed reference escapes trusted directory")
        raw[key] = target.read_bytes()
        if (
            ref["sha256"] != required
            or hashlib.sha256(raw[key]).hexdigest() != required
        ):
            raise ValueError("Seed checksum mismatch")
    assets = json.loads(raw["assets"])
    equity = assets["vn30_universe"]
    if len(equity) != 30 or assets["default_selection"] != equity + ["GOLD", "VFF"]:
        raise ValueError("Frozen universe mismatch")
    return assets["default_selection"], equity, raw


def fetch_full_pack(seed_path, store, *, now=None, kbs=None, mixed=None):
    provenance = []
    try:
        return _fetch_full_pack(
            seed_path, store, now=now, kbs=kbs, mixed=mixed, provenance=provenance
        )
    except (ValueError, KeyError, TypeError, ArithmeticError, OSError) as exc:
        rejected = {
            "schema_version": 2,
            "status": "REJECTED",
            "artifacts": provenance,
            "failed_at": utcnow().isoformat(),
        }
        exc.source_manifest = store.put(
            json.dumps(rejected, sort_keys=True).encode(), "json"
        )
        raise


def _fetch_full_pack(seed_path, store, *, now=None, kbs=None, mixed=None, provenance):
    now = now or utcnow()
    local_now = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    as_of = local_now.date()
    cutoff = as_of if local_now.hour >= 18 else completed_cutoff(now)
    dataset_root = Path(
        os.environ.get("DATASET_DIRECTORY", str(store.directory))
    ).resolve()
    if not store.directory.is_relative_to(dataset_root):
        raise ValueError("Artifact directory must be under DATASET_DIRECTORY")
    assets, equity, seed = read_seed(seed_path, store)
    kbs, mixed = kbs or KbsProvider(), mixed or MixedSource()
    packs = []

    def keep(raw, request):
        ref = request | {"raw": store.put(raw, "json")}
        provenance.append(ref)
        return ref

    def stock(symbol, index=False):
        requested = utcnow().isoformat()
        start = date(2020, 1, 1) if index else START
        raw = kbs.fetch_raw(symbol, start, cutoff, index=index)
        ref = keep(
            raw,
            {
                "asset_id": symbol,
                "url": f"{BASE}/{'index' if index else 'stocks'}/{symbol}/data_day",
                "method": "GET",
                "params": {
                    "sdate": start.strftime("%d-%m-%Y"),
                    "edate": cutoff.strftime("%d-%m-%Y"),
                },
                "requested_at": requested,
                "received_at": utcnow().isoformat(),
            },
        )
        return normalize(raw, symbol, start, cutoff), ref

    calendar_rows, calendar_ref = stock("VNINDEX", True)
    calendar = [str(day) for day, _ in calendar_rows]
    if (as_of - calendar_rows[-1][0]).days > 7:
        raise ValueError("Stale observed calendar")

    def pack(symbol, kind, provider, basis, rows, metadata, refs, *, expected=None):
        source_start = (
            START
            if kind == "stock"
            else date(2020, 1, 1)
            if kind == "fund"
            else date(2019, 12, 1)
        )
        rows = [(day, price) for day, price in rows if source_start <= day <= cutoff]
        if (
            not rows
            or (as_of - rows[-1][0]).days > 7
            or (rows[0][0] - source_start).days > 7
        ):
            raise ValueError(f"Stale or missing start coverage for {symbol}")
        normalized = store.put(normalized_csv(rows, symbol), "csv")
        spec = {
            "path": str(
                (store.directory / normalized["file"]).relative_to(dataset_root)
            ),
            "sha256": normalized["sha256"],
            "asset_id": symbol,
            "kind": kind,
            "source_unit": {
                "stock": "VND/share",
                "gold": "VND/tael",
                "fund": "VND/unit",
            }[kind],
            "provider": provider,
            "data_origin": "real",
            "price_basis": basis,
            "price_type": "nav" if kind == "fund" else "close",
            "availability_basis": "ingestion",
            "availability_policy": "phase1-full-v1",
            "source_provenance": refs,
            "start_date": str(source_start),
        }
        if expected is not None:
            spec["expected_sessions"] = expected
        observations = CsvProvider(dataset_root).fetch(spec)
        findings = validate_batch(observations, spec)
        packs.append(
            {
                "spec": spec,
                "observations": observations,
                "metadata": metadata,
                "findings": findings,
                "provenance": refs,
                "normalized": normalized,
            }
        )

    missing_equity = {}
    equity_calendar = [d for d in calendar if d >= str(START)]
    for symbol in equity:
        rows, ref = stock(symbol)
        missing = equity_missing_sessions(symbol, rows, equity_calendar)
        if missing:
            missing_equity[symbol] = missing
        pack(
            symbol,
            "stock",
            PROVIDER,
            "provider_adjusted",
            rows,
            {},
            [ref],
            expected=[d for d in equity_calendar if d not in missing],
        )

    gold_rows, metadata = frozen_gold(seed["gold"])
    gold_ref = keep(
        seed["gold"],
        {
            "asset_id": "GOLD",
            "role": "frozen-canonical-through-2026-04-30",
            "received_at": utcnow().isoformat(),
            "historical_publication_verified": False,
        },
    )
    gold_refs = [gold_ref]
    for entry in metadata.values():
        entry["raw_source_hash"] = gold_ref["raw"]["sha256"]
    month = date(2026, 5, 1)
    while month <= cutoff:
        url = f"https://giavang.tv/lich-su/{month.year}/{month.month}"
        raw, request = mixed.fetch(url)
        ref = keep(raw, request | {"asset_id": "GOLD"})
        gold_refs.append(ref)
        rows, extra = normalize_gold_archive(raw, month.year, month.month)
        gold_rows.extend((day, price) for day, price in rows if day <= cutoff)
        for entry in extra.values():
            entry["raw_source_hash"] = ref["raw"]["sha256"]
        metadata.update(extra)
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    gold_rows.sort()
    gold_start = date(2019, 12, 1)
    expected_gold = [
        str(gold_start + timedelta(days=i))
        for i in range((cutoff - gold_start).days + 1)
    ]
    pack(
        "GOLD",
        "gold",
        GOLD_PROVIDER,
        "raw_close",
        gold_rows,
        metadata,
        gold_refs,
        expected=expected_gold,
    )

    raw, request = mixed.fetch(
        "https://api.fmarket.vn/res/products/filter",
        payload={
            "searchField": "VFF",
            "types": ["NEW_FUND", "TRADING_FUND"],
            "pageSize": 100,
        },
    )
    identity_ref = keep(raw, request | {"asset_id": "VFF", "role": "identity"})
    verify_vff_identity(raw)
    raw, request = mixed.fetch(
        "https://api.fmarket.vn/res/product/get-nav-history",
        payload={
            "isAllData": 1,
            "productId": 21,
            "fromDate": None,
            "toDate": cutoff.strftime("%Y%m%d"),
        },
    )
    nav_ref = keep(raw, request | {"asset_id": "VFF", "role": "all-history"})
    rows, metadata = normalize_fmarket(raw, date(2020, 1, 1), cutoff)
    pack("VFF", "fund", VFF_PROVIDER, "nav", rows, metadata, [identity_ref, nav_ref])
    manifest = {
        "schema_version": 2,
        "universe_id": "VN_PHASE1_FULL",
        "availability_policy": "phase1-full-v1",
        "assets_seed_sha256": ASSETS_SEED_HASH,
        "gold_seed_sha256": GOLD_SEED_HASH,
        "equity_missing_sessions": missing_equity,
        "equity_gap_evidence": EQUITY_GAP_EVIDENCE,
        "artifacts": provenance,
        "calendar_source": calendar_ref,
        "start_date": "2019-12-01",
        "panel_start_date": str(START),
        "end_date": str(cutoff),
        "retrieved_at": utcnow().isoformat(),
    }
    pin = store.put(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(), "json"
    )
    return {
        "asset_ids": assets,
        "candidate_equity_ids": equity,
        "start_date": date(2019, 12, 1),
        "panel_start_date": START,
        "end_date": cutoff,
        "as_of_date": as_of,
        "calendar_sessions": calendar,
        "equity_missing_sessions": missing_equity,
        "packs": packs,
        "source_manifest": pin,
    }


def persist_full_pack(sessions, store, batch):
    # All source I/O and whole-universe validation have completed before SQL begins.
    store.read(batch["source_manifest"])
    for pack in batch["packs"]:
        store.read(pack["normalized"])
        for ref in pack["provenance"]:
            store.read(ref["raw"])
    with sessions.begin() as session:
        actor = session.scalar(
            select(Actor)
            .where(Actor.issuer == "local-operator", Actor.subject == "phase1-full")
            .with_for_update()
        )
        if actor is None:
            actor = Actor(issuer="local-operator", subject="phase1-full")
            session.add(actor)
            session.flush()
        run_id = str(uuid4())
        for pack in batch["packs"]:
            spec, observations = pack["spec"], pack["observations"]
            dataset_id = "FULL_" + canonical_hash(spec)[:56].upper()
            if session.get(RegisteredDataset, dataset_id) is None:
                session.add(
                    RegisteredDataset(
                        dataset_id=dataset_id,
                        sha256=spec["sha256"],
                        spec=spec,
                        start_date=observations[0].observation_date,
                        end_date=observations[-1].observation_date,
                        registered_by=actor.id,
                    )
                )
            job = IngestionJob(
                actor_id=actor.id,
                idempotency_key=f"full:{run_id}:{spec['asset_id']}",
                request_hash=canonical_hash(spec),
                input={"dataset_spec": spec},
                deadline=utcnow() + timedelta(hours=1),
            )
            session.add(job)
            session.flush()
            job.inserted_count = persist_observations(
                session, observations, spec, job.id
            )
            job.status = "SUCCEEDED"
            report = report_json(
                job.id, "PASS", len(observations), pack["findings"], observations, spec
            ) | {
                "source_manifest": batch["source_manifest"],
                "scope": "atomic-phase1-full-batch",
            }
            session.add(QualityReport(job_id=job.id, status="PASS", report=report))
        session.flush()
        snapshot = build_full_snapshot(session, **batch)
        return snapshot_json(snapshot)


def quarantine_full_failure(sessions, *, batch=None, cause=None):
    """Record rejected batches after rollback; no revision can escape quarantine."""
    with sessions.begin() as session:
        actor = session.scalar(
            select(Actor).where(
                Actor.issuer == "local-operator", Actor.subject == "phase1-full"
            )
        )
        if actor is None:
            actor = Actor(issuer="local-operator", subject="phase1-full")
            session.add(actor)
            session.flush()
        pin = (
            batch["source_manifest"]
            if batch
            else getattr(cause, "source_manifest", None)
        )
        job = IngestionJob(
            actor_id=actor.id,
            idempotency_key="full-quarantine:" + str(uuid4()),
            request_hash=canonical_hash({"source_manifest": pin}),
            input={"source_manifest": pin, "universe_id": "VN_PHASE1_FULL"},
            status="FAILED",
            deadline=utcnow(),
            error={
                "code": "INVALID_DATASET",
                "message": "Full mixed source batch quarantined",
            },
        )
        session.add(job)
        session.flush()
        findings = (
            cause.findings
            if isinstance(cause, QualityFailure)
            else [finding("INVALID_SOURCE")]
        )
        session.add(
            QualityReport(
                job_id=job.id,
                status="QUARANTINED",
                report=report_json(job.id, "QUARANTINED", 0, findings)
                | {"scope": "atomic-phase1-full-batch", "source_manifest": pin},
            )
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    store = ArtifactStore(args.directory)
    sessions = sessions_from_env()
    batch = None
    try:
        batch = fetch_full_pack(args.seed, store)
        result = persist_full_pack(sessions, store, batch)
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        quarantine_full_failure(sessions, batch=batch, cause=exc)
        raise SystemExit(
            "Full source batch quarantined; inspect quality report and immutable raw artifacts"
        ) from exc
    print(
        json.dumps({k: result[k] for k in ("id", "content_hash", "observation_count")})
    )


if __name__ == "__main__":
    main()
