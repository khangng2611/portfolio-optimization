"""Read-only v5 timestamp/revision audit; never certifies or changes a model."""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, time
from decimal import Decimal
import gzip
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryFile

from portfolio_contracts import canonical_hash, utcnow
from portfolio_core.assets import EQUITY_IDS
from quant_service.full import TZ
from quant_service.snapshot_inputs import timestamp

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "infra/local/.generated"


def key(row):
    return tuple(
        row[name] for name in ("asset_id", "observation_date", "provider", "price_type")
    )


def known_at(row, job):
    times = [timestamp(row["ingested_at"]), timestamp(row["available_at"])]
    for value in (row.get("published_at"), job.get("quality_checked_at")):
        if value:
            times.append(timestamp(value))
    return max(times)


def audit_snapshot(snapshot, observations, revisions, jobs, *, decision_at, nominal_at):
    decision, nominal = timestamp(decision_at), timestamp(nominal_at)
    created = timestamp(snapshot["created_at"])
    manifest = {
        k: v
        for k, v in snapshot.items()
        if k not in {"id", "content_hash", "created_at"}
    }
    if (
        canonical_hash(manifest) != snapshot["content_hash"]
        or canonical_hash({"observations": observations})
        != snapshot["observation_hash"]
        or len(observations) != snapshot["observation_count"]
        or [r["revision_id"] for r in observations] != snapshot["revision_ids"]
    ):
        raise ValueError("Snapshot/observation hash mismatch")
    by_id = {r["revision_id"]: r for r in revisions}
    if len(by_id) != len(revisions):
        raise ValueError("Duplicate revision identity")
    groups = defaultdict(list)
    for row in revisions:
        groups[key(row)].append(row)
    visible = {}
    counts = Counter(
        {
            k: 0
            for k in (
                "missing_revision",
                "row_mismatch",
                "invalid_clock_order",
                "known_after_snapshot",
                "known_after_decision",
                "newer_visible_revision",
                "source_hash_mismatch",
                "revision_chain_invalid",
                "quality_not_evidenced",
                "source_not_evidenced",
            )
        }
    )
    for identity, rows in groups.items():
        ordered = sorted(rows, key=lambda r: r["revision"])
        if [r["revision"] for r in ordered] != list(range(1, len(ordered) + 1)) or any(
            timestamp(a["ingested_at"]) > timestamp(b["ingested_at"])
            for a, b in zip(ordered, ordered[1:])
        ):
            counts["revision_chain_invalid"] += 1
        accepted = [
            r
            for r in rows
            if jobs.get(r.get("ingestion_job_id"), {}).get("quality_status") == "PASS"
            and jobs.get(r.get("ingestion_job_id"), {}).get("quality_checked_at")
            and known_at(r, jobs[r["ingestion_job_id"]]) <= created
        ]
        if accepted:
            visible[identity] = max(accepted, key=lambda r: r["revision"])["revision"]
    assets = {}
    clocks = {"available_at", "ingested_at", "published_at"}
    fields = (
        "asset_id",
        "observation_date",
        "provider",
        "price_type",
        "price_vnd",
        "unit",
        "revision",
        "content_hash",
        "available_at",
        "ingested_at",
        "published_at",
        "source_hash",
        "data_origin",
        "price_basis",
    )
    for selected in observations:
        item = assets.setdefault(
            selected["asset_id"],
            {
                "selected": 0,
                "missing_publication": 0,
                "first_seen_after_observation_close": 0,
                "unavailable_by_nominal_epoch": 0,
                "first_seen_min": None,
                "first_seen_max": None,
                "max_revision": 0,
            },
        )
        item["selected"] += 1
        row = by_id.get(selected["revision_id"])
        if row is None:
            counts["missing_revision"] += 1
            continue

        def value(record, field):
            v = record.get(field)
            return (
                timestamp(v)
                if field in clocks and v
                else Decimal(v)
                if field == "price_vnd"
                else v
            )

        if any(value(selected, k) != value(row, k) for k in fields):
            counts["row_mismatch"] += 1
        job = jobs.get(row.get("ingestion_job_id"), {})
        if job.get("quality_status") != "PASS" or not job.get("quality_checked_at"):
            counts["quality_not_evidenced"] += 1
        if not job.get("source_hash") or not row.get("source_hash"):
            counts["source_not_evidenced"] += 1
        elif job["source_hash"] != row["source_hash"]:
            counts["source_hash_mismatch"] += 1
        known = known_at(row, job)
        first = timestamp(row["ingested_at"])
        if timestamp(row["available_at"]) < first:
            counts["invalid_clock_order"] += 1
        counts["known_after_snapshot"] += known > created
        counts["known_after_decision"] += known > decision
        counts["newer_visible_revision"] += (
            visible.get(key(row), row["revision"]) > row["revision"]
        )
        observed_close = datetime.combine(
            date.fromisoformat(row["observation_date"]), time(18), TZ
        )
        item["missing_publication"] += row.get("published_at") is None
        item["first_seen_after_observation_close"] += first > observed_close
        item["unavailable_by_nominal_epoch"] += known > nominal
        item["max_revision"] = max(item["max_revision"], row["revision"])
        stamp = first.isoformat()
        item["first_seen_min"] = min(item["first_seen_min"] or stamp, stamp)
        item["first_seen_max"] = max(item["first_seen_max"] or stamp, stamp)
    missing = counts["quality_not_evidenced"] + counts["source_not_evidenced"]
    errors = sum(
        v
        for k, v in counts.items()
        if k not in {"quality_not_evidenced", "source_not_evidenced"}
    )
    errors += created > decision
    return {
        "snapshot_id": snapshot["id"],
        "content_hash": snapshot["content_hash"],
        "created_at": snapshot["created_at"],
        "decision_at": decision_at,
        "nominal_at": nominal_at,
        "live_integrity": "FAIL" if errors else "NOT_EVIDENCED" if missing else "PASS",
        "observation_count": len(observations),
        "counts": dict(counts),
        "assets": assets,
        "first_seen_after_observation_close": sum(
            a["first_seen_after_observation_close"] for a in assets.values()
        ),
        "unavailable_by_nominal_epoch": sum(
            a["unavailable_by_nominal_epoch"] for a in assets.values()
        ),
        "historical_publication": "NOT_EVIDENCED",
        "point_in_time_certified": False,
    }


def audit_timeline(
    model, *, training_created_at, serving_created_at, published_at, decision_at
):
    known, trained, approved = (
        timestamp(model[k])
        for k in ("training_knowledge_cutoff", "trained_at", "approved_at")
    )
    publication, decision = timestamp(published_at), timestamp(decision_at)
    fit = datetime.combine(date.fromisoformat(model["fit_epoch"]), time(18), TZ)
    valid = (
        max(known, timestamp(training_created_at))
        <= trained
        <= approved
        <= publication
        <= decision
        and timestamp(serving_created_at) <= publication
    )
    return {
        "live_integrity": "PASS" if valid else "FAIL",
        "training_knowledge_cutoff": model["training_knowledge_cutoff"],
        "trained_at": model["trained_at"],
        "approved_at": model["approved_at"],
        "published_at": published_at,
        "decision_at": decision_at,
        "nominal_fit_at": fit.isoformat(),
        "model_available_at_nominal_epoch": max(trained, approved) <= fit,
        "point_in_time_certified": False,
    }


MARKET_EXPORT = """import json,sys
from sqlalchemy import select,text
from sqlalchemy.orm import load_only
from portfolio_contracts import aware
from market_service.runtime import sessions_from_env
from market_service.models import Snapshot,PriceRevision,IngestionJob,QualityReport
from market_service.snapshots import snapshot_json,observation_json
ids=json.loads(sys.argv[1])
with sessions_from_env()() as db:
 db.execute(text('SET TRANSACTION READ ONLY'))
 indexed={s.id:s for s in db.scalars(select(Snapshot).where(Snapshot.id.in_(ids)).options(load_only(Snapshot.id,Snapshot.content_hash,Snapshot.manifest,Snapshot.created_at)))}
 snaps=[indexed[i] for i in ids]
 observations={}
 for s in snaps:
  digest=s.manifest['observation_hash']
  if digest not in observations: observations[digest]=s.observations
 keys={(r['asset_id'],r['observation_date'],r['provider'],r['price_type']) for rows in observations.values() for r in rows}
 assets={a for s in snaps for a in s.manifest['asset_ids']}
 rows=[r for r in db.scalars(select(PriceRevision).where(PriceRevision.asset_id.in_(assets))) if (r.asset_id,str(r.observation_date),r.provider,r.price_type) in keys]
 jobids={r.ingestion_job_id for r in rows if r.ingestion_job_id}
 jobs={r.id:r for r in db.scalars(select(IngestionJob).where(IngestionJob.id.in_(jobids)))}
 quality={r.job_id:r for r in db.scalars(select(QualityReport).where(QualityReport.job_id.in_(jobids)))}
 data={'snapshots':[snapshot_json(s) for s in snaps], 'observations_by_hash':observations,
  'revisions':[observation_json(r)|{'ingestion_job_id':r.ingestion_job_id} for r in rows],
  'jobs':{identity:{'status':r.status,'created_at':aware(r.created_at).isoformat(),
   'source_hash':r.input.get('dataset_spec',{}).get('sha256'),
   'normalized_ref':{k:r.input.get('dataset_spec',{})[k] for k in ('path','sha256') if k in r.input.get('dataset_spec',{})},
   'source_provenance':r.input.get('dataset_spec',{}).get('source_provenance',[]),
   'quality_status':quality[identity].status if identity in quality else None,
   'quality_checked_at':aware(quality[identity].checked_at).isoformat() if identity in quality else None,
   'source_metadata_ref':quality[identity].report.get('source_metadata_ref') if identity in quality else None}
   for identity,r in jobs.items()}}
 json.dump(data,sys.stdout)
"""


def audit_artifacts(jobs, directory):
    from market_service.selected_refresh import read_artifact

    counts = Counter(
        normalized_sources_verified=0,
        metadata_verified=0,
        raw_sources_verified=0,
        jobs_without_metadata_sidecar=0,
        jobs_without_fetch_metadata=0,
        fetch_after_quality=0,
        artifact_errors=0,
    )
    for job in jobs.values():
        try:
            read_artifact(directory, job["normalized_ref"])
            counts["normalized_sources_verified"] += 1
            refs = job.get("source_provenance", [])
            if job.get("source_metadata_ref"):
                metadata = json.loads(
                    read_artifact(directory, job["source_metadata_ref"])
                )
                if metadata["normalized_ref"]["sha256"] != job["source_hash"]:
                    raise ValueError("Source metadata pin differs from ingestion")
                counts["metadata_verified"] += 1
                refs = metadata["source_provenance"]
            else:
                counts["jobs_without_metadata_sidecar"] += 1
            if not any(s.get("requested_at") and s.get("received_at") for s in refs):
                counts["jobs_without_fetch_metadata"] += 1
            for source in refs:
                ref = source["raw"]
                if "path" not in ref:
                    # Legacy full refresh stores raw files beside its normalized CSV.
                    if Path(ref["file"]).name != ref["file"]:
                        raise ValueError("Invalid legacy raw filename")
                    ref = ref | {
                        "path": str(
                            Path(job["normalized_ref"]["path"]).parent / ref["file"]
                        )
                    }
                read_artifact(directory, ref)
                counts["raw_sources_verified"] += 1
                if (
                    source.get("requested_at")
                    and source.get("received_at")
                    and job.get("quality_checked_at")
                ):
                    if (
                        not timestamp(source["requested_at"])
                        <= timestamp(source["received_at"])
                        <= timestamp(job["quality_checked_at"])
                    ):
                        counts["fetch_after_quality"] += 1
        except (ValueError, KeyError, TypeError, OSError):
            counts["artifact_errors"] += 1
    return {
        "byte_integrity": "FAIL"
        if counts["artifact_errors"] or counts["fetch_after_quality"]
        else "PASS",
        **counts,
    }


def capture_market(ids):
    from uuid import UUID

    ids = [str(UUID(identity)) for identity in ids]
    command = [
        "docker",
        "compose",
        "-p",
        "portfolio-auth-demo",
        "--env-file",
        str(GENERATED / ".env"),
        "-f",
        str(ROOT / "infra/local/compose.yaml"),
        "exec",
        "-T",
        "market-api",
        "python",
        "-",
        json.dumps(ids),
    ]
    try:
        with TemporaryFile(mode="w+t") as stream:
            subprocess.run(
                command,
                input=MARKET_EXPORT,
                stdout=stream,
                stderr=subprocess.PIPE,
                text=True,
                timeout=180,
                check=True,
            )
            stream.seek(0)
            return json.load(stream)
    except (subprocess.SubprocessError, ValueError, OSError):
        raise RuntimeError(
            "Read-only Market owner export failed; raw DB details suppressed"
        ) from None


def main():
    from local_auth import login
    from smoke_chat import get, PORTFOLIO
    from quant_service.selection_catalog import SelectionCatalog
    from quant_service.ml import parse_manifest, read_artifact, validate_native_files
    from quant_service.selection_ready import fit_index

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipt",
        type=Path,
        default=ROOT / "output/bl-ml-epoch-20261116/chat-flow-receipt.json",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "output/point-in-time-v5")
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text())["cases"]["fresh"]
    if receipt.get("strategy") != "BL_ML":
        raise ValueError("This audit requires the original BL_ML receipt")
    facts = get(
        PORTFOLIO,
        "/api/v1/recommendations/" + receipt["recommendation_id"],
        login("alice"),
    )
    if canonical_hash(facts) != receipt["facts_hash"]:
        raise ValueError("Original recommendation hash changed")
    catalog = SelectionCatalog(GENERATED / "bundles")
    bundle, pin = next(
        (v, p) for v, p in catalog._entries() if p.bundle_hash == facts["bundle_hash"]
    )
    _, panel = catalog.load_resource(pin)
    model = parse_manifest(read_artifact(GENERATED, bundle["model"]))
    validate_native_files((GENERATED / bundle["model"]["file"]).parent, model)
    if (
        model.schema_version != 5
        or model.model_id != facts["diagnostics"]["inference"]["model_id"]
    ):
        raise ValueError("Original v5 model pin changed")
    ids = list(dict.fromkeys([model.training_snapshot_id, facts["data_snapshot_id"]]))
    evidence = capture_market(ids)
    snapshots = [
        {
            "snapshot": s,
            "observations": evidence["observations_by_hash"][s["observation_hash"]],
        }
        for s in evidence["snapshots"]
    ]
    by_id = {v["snapshot"]["id"]: v for v in snapshots}
    training, serving = (
        by_id[model.training_snapshot_id],
        by_id[facts["data_snapshot_id"]],
    )
    if (
        training["snapshot"]["content_hash"] != model.training_snapshot_hash
        or serving["snapshot"]["content_hash"]
        != facts["selection_proof"]["snapshot_hash"]
    ):
        raise ValueError("Model/snapshot pins differ from the original receipt")
    model_data = model.model_dump(mode="json")
    decision = facts["selection_context"]["decision_at"]
    timeline = audit_timeline(
        model_data,
        training_created_at=training["snapshot"]["created_at"],
        serving_created_at=serving["snapshot"]["created_at"],
        published_at=bundle["decision_at"],
        decision_at=decision,
    )
    reports = [
        audit_snapshot(
            v["snapshot"],
            v["observations"],
            evidence["revisions"],
            evidence["jobs"],
            decision_at=decision,
            nominal_at=timeline["nominal_fit_at"],
        )
        for v in snapshots
    ]
    stop = fit_index(panel.dates.index(model.fit_epoch)) - 5
    dates = set(map(str, panel.dates[:stop]))
    used = {
        (asset, str(date.fromordinal(int(day))))
        for j, asset in enumerate(EQUITY_IDS)
        for day in panel.observation_days[:stop, j]
    }
    prefix = [
        r
        for r in training["observations"]
        if (r["asset_id"], r["observation_date"]) in used
    ]
    ledger = {r["revision_id"]: r for r in evidence["revisions"]}
    prefix_known = [
        known_at(
            ledger[r["revision_id"]],
            evidence["jobs"].get(ledger[r["revision_id"]].get("ingestion_job_id"), {}),
        )
        for r in prefix
    ]
    artifacts = audit_artifacts(evidence["jobs"], GENERATED / "datasets")
    report = {
        "schema": 1,
        "audited_at": utcnow().isoformat(),
        "scope": "Timestamp/revision audit of the original v5 receipt; not a historical walk-forward certification",
        "model_id": model.model_id,
        "approved_manifest_hash": bundle["model"]["sha256"],
        "recommendation_id": facts["id"],
        "facts_hash": receipt["facts_hash"],
        "timeline": timeline,
        "snapshots": reports,
        "ledger_revisions": len(evidence["revisions"]),
        "ingestion_jobs": len(evidence["jobs"]),
        "max_recorded_revision": max(r["revision"] for r in evidence["revisions"]),
        "source_artifacts": artifacts,
        "training_prefix": {
            "unique_source_observations": len(prefix),
            "price_cells": stop * len(EQUITY_IDS),
            "declared_missing_sessions": sum(
                d in dates
                for days in training["snapshot"]
                .get("equity_missing_sessions", {})
                .values()
                for d in days
            ),
            "carried_cells": sum(
                int(day) != panel.dates[i].toordinal()
                for j in range(len(EQUITY_IDS))
                for i, day in enumerate(panel.observation_days[:stop, j])
            ),
            "dates": len(dates),
            "known_after_nominal_epoch": sum(
                t > timestamp(timeline["nominal_fit_at"]) for t in prefix_known
            ),
            "known_after_actual_training": sum(
                t > timestamp(model_data["trained_at"]) for t in prefix_known
            ),
            "known_at_basis": "max(ingested_at, available_at, published_at if present, quality_checked_at)",
            "known_at_min": min(prefix_known).isoformat(),
            "known_at_max": max(prefix_known).isoformat(),
        },
        "point_in_time_certified": False,
        "protocol_limitations": [
            "Reported validation MAE/RMSE use the same fold as early stopping; it is not an independent holdout.",
            "Declared missing equity sessions are carried in the price panel; this is not proof of historical tradability.",
        ],
        "not_evidenced": [
            "Historical provider release/revision vintages before system first-seen; published_at is not inferred from observation_date or raw provider createdAt.",
            "Point-in-time corporate-action adjustment factors and historical universe membership.",
            "Historical publication of NAV/GOLD carried by policy; live v2 valuation alignment is not a replay publication record.",
            "Untouched rolling out-of-sample replay, hyperparameter-selection independence, execution/costs and prospective performance.",
        ],
        "not_run": [
            "Full historical walk-forward replay",
            "Forward/paper performance test",
            "Paid provider calls",
            "Training or model approval",
        ],
        "read_only": True,
    }
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, value in [("market-evidence.json.gz", evidence), ("report.json", report)]:
        path = args.output / name
        context = path.open("w") if name == "report.json" else gzip.open(path, "wt")
        with context as stream:
            json.dump(
                value,
                stream,
                ensure_ascii=False,
                indent=2 if name == "report.json" else None,
            )
            stream.write("\n")
        path.chmod(0o600)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "model_id",
                    "recommendation_id",
                    "training_prefix",
                    "source_artifacts",
                    "point_in_time_certified",
                )
            },
            ensure_ascii=False,
        )
    )
    if (
        timeline["live_integrity"] == "FAIL"
        or any(r["live_integrity"] == "FAIL" for r in reports)
        or artifacts["byte_integrity"] == "FAIL"
    ):
        raise SystemExit("Audit found inconsistent evidence; review the private report")


if __name__ == "__main__":
    main()
