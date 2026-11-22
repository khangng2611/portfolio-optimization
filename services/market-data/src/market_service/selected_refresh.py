"""Independent, bounded operator refresh for the shared selected-assets resource."""

import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import select

from portfolio_contracts import canonical_hash, utcnow
from portfolio_contracts.assets import ASSET_IDS, canonical_candidates, supported_assets
from .models import Actor, IngestionJob, QualityReport, RegisteredDataset
from .phase1_full import START, read_seed
from .phase1_sources import (
    GOLD_PROVIDER,
    VFF_PROVIDER,
    MixedSource,
    frozen_gold,
    normalize_gold_archive,
    normalize_fmarket,
    verify_vff_identity,
    equity_missing_sessions,
)
from .providers import CsvProvider
from .quality import QualityFailure, finding, report_json, validate_batch
from .refresh_provider import (
    ArtifactStore,
    BASE,
    KbsProvider,
    PROVIDER,
    normalize,
    normalized_csv,
)
from .runtime import sessions_from_env
from .workflow import persist_observations

FAMILY = "user-selection-market-v1"
POLICY = "user-selection-data-v1"


def completed_selected_cutoff(now):
    local = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    return local.date() if local.hour >= 18 else local.date() - timedelta(days=1)


def artifact_ref(store, root, raw, suffix="json"):
    ref = store.put(raw, suffix)
    return ref | {"path": str((store.directory / ref["file"]).relative_to(root))}


def read_artifact(directory, ref):
    return CsvProvider(directory)._raw(ref)


def operator_actor(session):
    actor = session.scalar(
        select(Actor)
        .where(Actor.issuer == "local-operator", Actor.subject == FAMILY)
        .with_for_update()
    )
    if actor is None:
        actor = Actor(issuer="local-operator", subject=FAMILY)
        session.add(actor)
        session.flush()
    return actor


def persist_selected_asset(sessions, store, root, pack):
    spec, observations = pack["spec"], pack["observations"]
    read_artifact(root, spec["source_metadata_ref"])
    if spec.get("calendar_source"):
        read_artifact(root, spec["calendar_source"]["raw"])
    for ref in pack["provenance"]:
        read_artifact(root, ref["raw"])
    # Read accepted CSV bytes again before entering the asset's transaction.
    CsvProvider(root).fetch(spec)
    with sessions.begin() as session:
        actor = operator_actor(session)
        dataset_id = "SELECTED_" + canonical_hash(spec)[:55].upper()
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
            idempotency_key="selected:" + str(uuid4()),
            request_hash=canonical_hash(spec),
            deadline=utcnow() + timedelta(hours=1),
            input={
                "source_family": FAMILY,
                "selected_asset_id": spec["asset_id"],
                "dataset_spec": spec,
            },
        )
        session.add(job)
        session.flush()
        job.inserted_count = persist_observations(session, observations, spec, job.id)
        job.status = "SUCCEEDED"
        report = report_json(
            job.id, "PASS", len(observations), pack["findings"], observations, spec
        ) | {
            "source_metadata_ref": spec["source_metadata_ref"],
            "source_family": FAMILY,
            "source_provenance": pack["provenance"],
            "calendar_source": spec["calendar_source"],
        }
        session.add(QualityReport(job_id=job.id, status="PASS", report=report))
        return {
            "asset_id": spec["asset_id"],
            "status": "AVAILABLE",
            "quality_status": "PASS",
            "job_id": job.id,
            "inserted_count": job.inserted_count,
            "source_metadata_ref": spec["source_metadata_ref"],
        }


def persist_failure(sessions, asset, provenance, calendar_source, store, root, exc):
    invalid = not isinstance(exc, (OSError, requests.RequestException))
    status = "QUARANTINED" if invalid else "MISSING"
    quality = "QUARANTINED" if invalid else "NOT_CHECKED"
    rejected = artifact_ref(
        store,
        root,
        json.dumps(
            {
                "asset_id": asset,
                "status": status,
                "source_family": FAMILY,
                "source_provenance": provenance,
                "calendar_source": calendar_source,
                "checked_at": utcnow().isoformat(),
            },
            sort_keys=True,
        ).encode(),
    )
    with sessions.begin() as session:
        actor = operator_actor(session)
        job = IngestionJob(
            actor_id=actor.id,
            idempotency_key="selected-failure:" + str(uuid4()),
            request_hash=canonical_hash(rejected),
            status="FAILED",
            deadline=utcnow(),
            input={
                "source_family": FAMILY,
                "selected_asset_id": asset,
                "source_metadata_ref": rejected,
            },
            error={
                "code": "INVALID_DATASET" if invalid else "SOURCE_UNAVAILABLE",
                "message": "Selected asset source unavailable",
            },
        )
        session.add(job)
        session.flush()
        findings = (
            exc.findings
            if isinstance(exc, QualityFailure)
            else [finding("INVALID_SOURCE")]
        )
        session.add(
            QualityReport(
                job_id=job.id,
                status=quality,
                report=report_json(
                    job.id, quality, getattr(exc, "row_count", 0), findings
                )
                | {
                    "source_metadata_ref": rejected,
                    "calendar_source": calendar_source,
                    "source_family": FAMILY,
                    "source_provenance": provenance,
                },
            )
        )
        return {
            "asset_id": asset,
            "status": status,
            "quality_status": quality,
            "job_id": job.id,
            "reason_code": "ASSET_DATA_MISSING" if not invalid else "INPUT_INVALID",
            "source_metadata_ref": rejected,
        }


def refresh_selected(
    asset_ids,
    cutoff,
    store,
    *,
    sessions=None,
    kbs=None,
    mixed=None,
    seed=None,
    now=None,
):
    now = now or utcnow()
    assets = canonical_candidates(asset_ids)
    cutoff = date.fromisoformat(cutoff) if isinstance(cutoff, str) else cutoff
    if not START <= cutoff <= completed_selected_cutoff(now):
        raise ValueError("Selected refresh requires a completed bounded source cutoff")
    if (cutoff - START).days > 3650:
        raise ValueError("Selected refresh exceeds bounded history")
    root = Path(os.environ.get("DATASET_DIRECTORY", str(store.directory))).resolve()
    if not store.directory.is_relative_to(root):
        raise ValueError("Artifact directory must be under DATASET_DIRECTORY")
    sessions, kbs, mixed = (
        sessions or sessions_from_env(),
        kbs or KbsProvider(),
        mixed or MixedSource(),
    )
    registry = {a["asset_id"]: a for a in supported_assets()}

    def keep(raw, request, refs):
        ref = request | {"raw": artifact_ref(store, root, raw)}
        refs.append(ref)
        return ref

    def stock(symbol, refs, index=False):
        start = date(2020, 1, 1) if index else START
        requested = utcnow().isoformat()
        raw = kbs.fetch_raw(symbol, start, cutoff, index=index)
        ref = keep(
            raw,
            {
                "asset_id": symbol,
                "url": f"{BASE}/{'index' if index else 'stocks'}/{symbol}/data_day",
                "requested_at": requested,
                "received_at": utcnow().isoformat(),
                "method": "GET",
                "params": {
                    "sdate": start.strftime("%d-%m-%Y"),
                    "edate": cutoff.strftime("%d-%m-%Y"),
                },
            },
            refs,
        )
        return normalize(raw, symbol, start, cutoff), ref

    calendar_source, calendar, calendar_error = None, [], None
    try:
        cal_rows, calendar_source = stock("VNINDEX", [], True)
        calendar = [str(day) for day, _ in cal_rows]
    except (
        OSError,
        requests.RequestException,
        ValueError,
        KeyError,
        TypeError,
        ArithmeticError,
    ) as exc:
        calendar_error = exc
    receipts = {}
    for asset in assets:
        refs, metadata, gaps = [], {}, []
        try:
            kind = registry[asset]["kind"]
            if kind == "stock":
                if calendar_error:
                    raise calendar_error
                rows, _ = stock(asset, refs)
                gaps = equity_missing_sessions(
                    asset, rows, [d for d in calendar if d >= str(START)]
                )
                provider, basis, start = PROVIDER, "provider_adjusted", START
                expected = [d for d in calendar if d >= str(START) and d not in gaps]
            elif kind == "gold":
                if seed is None:
                    raise ValueError("GOLD requires the trusted frozen seed")
                _, _, seeds = read_seed(seed, store)
                rows, metadata = frozen_gold(seeds["gold"])
                frozen_ref = keep(
                    seeds["gold"],
                    {
                        "asset_id": asset,
                        "role": "frozen-canonical-through-2026-04-30",
                        "received_at": utcnow().isoformat(),
                    },
                    refs,
                )
                for entry in metadata.values():
                    entry["raw_source_hash"] = frozen_ref["raw"]["sha256"]
                month = date(2026, 5, 1)
                while month <= cutoff:
                    raw, request = mixed.fetch(
                        f"https://giavang.tv/lich-su/{month.year}/{month.month}"
                    )
                    ref = keep(raw, request | {"asset_id": asset}, refs)
                    monthly, extra = normalize_gold_archive(
                        raw, month.year, month.month
                    )
                    rows.extend(monthly)
                    for entry in extra.values():
                        entry["raw_source_hash"] = ref["raw"]["sha256"]
                    metadata.update(extra)
                    month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
                provider, basis, start = GOLD_PROVIDER, "raw_close", date(2019, 12, 1)
                expected = [
                    str(start + timedelta(days=i))
                    for i in range((cutoff - start).days + 1)
                ]
            else:
                raw, request = mixed.fetch(
                    "https://api.fmarket.vn/res/products/filter",
                    payload={
                        "searchField": "VFF",
                        "types": ["NEW_FUND", "TRADING_FUND"],
                        "pageSize": 100,
                    },
                )
                keep(raw, request | {"asset_id": asset, "role": "identity"}, refs)
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
                keep(raw, request | {"asset_id": asset, "role": "all-history"}, refs)
                rows, metadata = normalize_fmarket(raw, date(2020, 1, 1), cutoff)
                provider, basis, start, expected = (
                    VFF_PROVIDER,
                    "nav",
                    date(2020, 1, 1),
                    None,
                )
            rows = sorted((day, price) for day, price in rows if start <= day <= cutoff)
            normalized = artifact_ref(store, root, normalized_csv(rows, asset), "csv")
            spec = {
                "path": normalized["path"],
                "sha256": normalized["sha256"],
                "asset_id": asset,
                "kind": kind,
                "source_unit": registry[asset]["unit"],
                "provider": provider,
                "price_basis": basis,
                "price_type": "nav" if kind == "fund" else "close",
                "data_origin": "real",
                "availability_basis": "ingestion",
                "availability_policy": POLICY,
                "start_date": str(start),
                "end_date": str(cutoff),
                "calendar_source": calendar_source,
                "source_provenance": refs,
            }
            if expected is not None:
                spec["expected_sessions"] = expected
            observations = CsvProvider(root).fetch(spec)
            findings = validate_batch(observations, spec)
            metadata_ref = artifact_ref(
                store,
                root,
                json.dumps(
                    {
                        "schema_version": 1,
                        "asset_id": asset,
                        "source_family": FAMILY,
                        "availability_policy": POLICY,
                        "metadata_by_date": metadata,
                        "normalized_ref": normalized,
                        "source_provenance": refs,
                        "calendar_source": calendar_source,
                        "calendar_sessions": calendar,
                        "equity_missing_sessions": gaps,
                    },
                    sort_keys=True,
                ).encode(),
            )
            spec["source_metadata_ref"] = metadata_ref
            pack = {
                "spec": spec,
                "observations": observations,
                "findings": findings,
                "provenance": refs,
            }
            receipts[asset] = persist_selected_asset(sessions, store, root, pack)
        except (
            OSError,
            requests.RequestException,
            ValueError,
            KeyError,
            TypeError,
            ArithmeticError,
        ) as exc:
            receipts[asset] = persist_failure(
                sessions, asset, refs, calendar_source, store, root, exc
            )
    return {
        "asset_receipts": receipts,
        "calendar_sessions": calendar,
        "calendar_source": calendar_source,
        "cutoff_date": str(cutoff),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-ids", nargs="+", default=list(ASSET_IDS))
    parser.add_argument("--directory", required=True)
    parser.add_argument(
        "--seed",
        help="Trusted Phase 1 seed under the artifact directory, required for GOLD",
    )
    args = parser.parse_args()
    now, sessions = utcnow(), sessions_from_env()
    store = ArtifactStore(args.directory)
    result = refresh_selected(
        args.asset_ids,
        completed_selected_cutoff(now),
        store,
        sessions=sessions,
        seed=args.seed,
        now=now,
    )
    from .selected_snapshots import build_selected_snapshot
    from .snapshots import snapshot_json

    with sessions.begin() as session:
        snapshot = build_selected_snapshot(
            session,
            args.asset_ids,
            result["calendar_sessions"],
            now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date(),
            directory=os.environ["DATASET_DIRECTORY"],
        )
        result["snapshot"] = {
            k: snapshot_json(snapshot)[k]
            for k in ("id", "content_hash", "observation_count")
        }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
