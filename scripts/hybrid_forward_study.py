"""Run the preregistered HYBRID study on capture receipts without serving credentials."""
import argparse
from datetime import date, datetime, time, timedelta, timezone
import fcntl
from hashlib import sha256
import importlib.metadata
import json
import logging
from pathlib import Path
import platform
import sys
from time import sleep

from market_service.hybrid_forward_capture import (
    COLLECTION_HOUR, MAX_ATTEMPTS, DECISION_TIME, FIRST_DAY, LAST_DAY, SETTLE_UNTIL, VIETNAM,
    save_json, write_once,
)
from portfolio_contracts.hybrid import FORWARD_POLICY

PROJECT = Path(__file__).resolve().parents[1]
BASELINE = Path("outputs/step1/readiness_20261012/runs/availability-observed-contract-20261012T233110")
PROTOCOL_SHA = "2fe5db506685dfd31486562f016bcefb520bef5e837d5acbafb8360626efac54"


def digest(data):
    return sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def clock():
    return datetime.now(timezone.utc)


def still_open(day, now):
    local = now.astimezone(VIETNAM)
    return local.date() == day and COLLECTION_HOUR <= local.hour < DECISION_TIME.hour


def freeze(archive, output):
    protocol = (archive / "setup/protocol.md").read_bytes()
    if digest(protocol) != PROTOCOL_SHA:
        raise ValueError("Registered protocol hash mismatch")
    files = list((PROJECT / "scripts").glob("hybrid_forward_*.py"))
    files += [PROJECT / "scripts/eval_hybrid_policy.py", PROJECT / BASELINE / "run_config.json",
              PROJECT / BASELINE / "manifest.json"]
    for folder in (BASELINE / "source_snapshot", Path("packages/portfolio-core/src"),
                   Path("packages/contracts/src"), Path("services/market-data/src"), Path("services/quant-serving/src")):
        files.extend((PROJECT / folder).rglob("*.py"))
    store = output / "implementation"
    store.mkdir(parents=True, exist_ok=True)
    sources = {}
    for path in sorted(files):
        data = path.read_bytes()
        key = digest(data)
        write_once(store / key, data)
        sources[str(path.relative_to(PROJECT))] = key
    write_once(store / PROTOCOL_SHA, protocol)
    manifest = {
        "policy": FORWARD_POLICY, "protocol_sha256": PROTOCOL_SHA, "sources": sources,
        "runtime": {"python": sys.version, "platform": sys.platform, "architecture": platform.machine(),
                    "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}},
        "first_session_from": str(FIRST_DAY), "last_session_through": str(LAST_DAY),
        "settlement_through": str(SETTLE_UNTIL), "timezone": str(VIETNAM),
    }
    save_json(output / "manifest.json", manifest)
    return digest((output / "manifest.json").read_bytes())


def commit_row(folder, row):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (row["session"] + ".json")
    body = json.dumps(row, sort_keys=True, allow_nan=False).encode()
    save_json(path, {"decision": row, "sha256": digest(body)})


def read_rows(folder, sessions):
    rows = []
    for i, path in enumerate(sorted(folder.glob("*.json"))):
        receipt = read(path)
        row = receipt["decision"]
        if receipt["sha256"] != digest(json.dumps(row, sort_keys=True, allow_nan=False).encode()):
            raise ValueError(f"Corrupt decision receipt: {path.name}")
        offset = 5 * i
        if (offset >= len(sessions) or sessions[offset] != row["session"] or row["session_offset"] != offset
                or path.stem != row["session"]):
            raise ValueError("Calendar revision or missing earlier decision; reconciliation required")
        rows.append(row)
    return rows


def batches(archive, phases, end_day):
    return sorted((s.parent for phase in phases for s in (archive / phase).glob("*/*/summary.json")
                   if s.parent.parent.name <= str(end_day)),
                  key=lambda path: (path.parent.name, path.name), reverse=True)


def latest_calendar(archive, available, cutoff, *, rehearsal=False):
    from hybrid_forward_panel import load_calendar
    for batch in available:
        try:
            return batch, load_calendar(archive, batch, cutoff, rehearsal=rehearsal)
        except (ValueError, FileNotFoundError) as exc:
            logging.warning("Calendar unavailable for %s: %s", batch.name, exc)
    raise ValueError("No verified VNINDEX calendar available")


def prior_state(rows):
    return next((row["state"] for row in reversed(rows) if row.get("state")), {})


def record_decision(archive, run, batch, day, offset, cutoff, rows, pin, *, rehearsal=False):
    from hybrid_forward_panel import load_panel
    from hybrid_forward_decision import decision

    start = clock()
    row = {"session": str(day), "session_offset": offset, "started_at": start.isoformat(),
           "manifest_sha256": pin, "phase": "rehearsal" if rehearsal else "evaluation",
           "cutoff": cutoff.isoformat(), "status": "HOLD"}
    if batch:
        row["batch"] = str(batch.relative_to(archive))
        row["capture_sha256"] = digest((batch / "summary.json").read_bytes())
    if not rehearsal and not still_open(day, start):
        row["reason"] = "MISSED_DECISION_WINDOW"
    elif not batch:
        row["reason"] = "MISSING_CAPTURE"
    else:
        try:
            panel = load_panel(archive, batch, cutoff, rehearsal=rehearsal, prepare_only=True)
        except (ValueError, FileNotFoundError) as exc:
            row["reason"] = str(exc)
            row["invalid_source_evidence"] = not str(exc).startswith("MISSING_SESSIONS ")
        else:
            row["panel"] = panel["provenance"]
            model_dir = run / "artifacts"
            model_dir.mkdir(exist_ok=True, parents=True)
            result = decision(panel, str(day), offset, model_dir, prior_state(rows))
            if result.get("status") not in ("HOLD", "TARGET", "DECIDED"):
                raise ValueError("Unexpected research decision status")
            row.update(result)
            row["status"] = "HOLD" if result["status"] == "HOLD" else "DECIDED"
    end = clock()
    if not rehearsal and end > cutoff:
        row.pop("state", None)
        row.pop("weights", None)
        row.update(status="HOLD", reason="MISSED_DECISION_WINDOW")
    row.update(finished_at=end.isoformat(), timing_verified=not rehearsal and row["status"] == "DECIDED")
    commit_row(run / "ledger", row)
    return row


def backfill_holds(run, sessions, observed_through, pin):
    rows = read_rows(run / "ledger", sessions)
    for offset in range(len(rows) * 5, len(sessions), 5):
        day = date.fromisoformat(sessions[offset])
        cutoff = datetime.combine(day, DECISION_TIME, VIETNAM)
        if observed_through <= cutoff:
            break
        row = {"session": str(day), "session_offset": offset, "phase": "evaluation", "manifest_sha256": pin,
               "cutoff": cutoff.isoformat(), "finished_at": clock().isoformat(), "status": "HOLD",
               "timing_verified": False, "reason": "MISSED_DECISION_WINDOW"}
        commit_row(run / "ledger", row)
        rows.append(row)
    return rows


def tick(archive, run, now, pin):
    day = now.astimezone(VIETNAM).date()
    if not FIRST_DAY <= day <= LAST_DAY or not still_open(day, now):
        return {"status": "WAITING", "first_day": str(FIRST_DAY)}
    available = batches(archive, ["evaluation"], day)
    today = [b for b in available if b.parent.name == str(day)]
    if not today:
        return {"status": "WAITING_FOR_CAPTURE"}
    cutoff = datetime.combine(day, DECISION_TIME, VIETNAM)
    last = read(today[0] / "summary.json")
    if ((last["status"] == "partial" or last.get("recent_stock_gaps")) and len(today) < MAX_ATTEMPTS
            and now < cutoff - timedelta(minutes=2)):
        return {"status": "WAITING_FOR_SOURCE_RETRY"}
    batch, calendar = latest_calendar(archive, today, cutoff)
    sessions = [s for s in calendar if str(FIRST_DAY) <= s <= str(day)]
    rows = backfill_holds(run, sessions, now, pin)
    if not sessions or sessions[-1] != str(day) or (len(sessions) - 1) % 5:
        return {"status": "NO_DECISION_DUE"}
    if rows and rows[-1]["session"] == str(day):
        return {"status": "ALREADY_RECORDED", "session": str(day)}
    row = record_decision(archive, run, batch, day, len(sessions)-1, cutoff, rows, pin)
    return {k: row[k] for k in ("status", "session", "reason") if k in row}


def settlement_panel(archive, available, cutoff):
    import numpy as np
    import pandas as pd
    from hybrid_forward_panel import load_valuation

    _, calendar = latest_calendar(archive, available, cutoff)
    if not calendar or calendar[-1] <= str(LAST_DAY):
        raise ValueError("Settlement calendar does not cover the complete evaluation period")
    sessions = [s for s in calendar if str(FIRST_DAY) <= s <= str(LAST_DAY)]
    rejected = []
    for batch in available:
        try:
            panel = load_valuation(archive, batch, cutoff)
            observed = [s for s in panel["sessions"] if str(FIRST_DAY) <= s <= str(LAST_DAY)]
            if observed != sessions or panel["sessions"][-1] <= str(LAST_DAY):
                raise ValueError("Inconsistent settlement calendar")
            marks = panel["valuation"].reindex(index=pd.to_datetime(sessions), columns=panel["assets"]).to_numpy()
            if not np.isfinite(marks).all() or (marks <= 0).any():
                raise ValueError("Unresolved economic closes")
            return batch, sessions, panel, rejected
        except (ValueError, FileNotFoundError) as exc:
            rejected.append({"batch": str(batch.relative_to(archive)), "reason": str(exc)})
    raise ValueError(f"No complete verified settlement vintage; reconcile receipts: {rejected}")


def finalize(archive, run, now):
    if now.astimezone(VIETNAM).date() <= SETTLE_UNTIL:
        raise ValueError("Independent evaluation and settlement window still open")
    path = run / "final.json"
    if path.exists():
        return read(path)
    from hybrid_forward_score import score

    pin = digest((run / "manifest.json").read_bytes())
    available = batches(archive, ["settlement"], SETTLE_UNTIL)
    cutoff = datetime.combine(SETTLE_UNTIL + timedelta(days=1), time.min, VIETNAM)
    batch, sessions, panel, rejected = settlement_panel(archive, available, cutoff)
    rows = backfill_holds(run, sessions, now, pin)
    from hybrid_forward_decision import verify_state
    verified_models = set()
    for row in rows:
        if row["manifest_sha256"] != pin or row["phase"] != "evaluation":
            raise ValueError("Evaluation ledger provenance mismatch")
        if row.get("batch"):
            batch_day = archive / row["batch"]
            if (batch_day.resolve().parent != (archive / "evaluation" / row["session"]).resolve()
                    or digest((batch_day / "summary.json").read_bytes()) != row["capture_sha256"]
                    ):
                raise ValueError("Decision evidence mismatch")
        if row["status"] == "DECIDED" and (not row.get("batch") or not row["timing_verified"]
                or datetime.fromisoformat(row["finished_at"]) > datetime.fromisoformat(row["cutoff"])):
            raise ValueError("Decision outside the registered window")
        if row.get("panel"):
            from hybrid_forward_panel import load_panel
            recovered = load_panel(archive, archive / row["batch"], datetime.fromisoformat(row["cutoff"]), prepare_only=True)
            if recovered["provenance"] != row["panel"]:
                raise ValueError("Decision snapshot cannot be reproduced")
        state = row.get("state", {})
        state_hash = digest(json.dumps(state, sort_keys=True).encode())
        if state and state_hash not in verified_models:
            verify_state(run / "artifacts", state)
            verified_models.add(state_hash)
    evidence = {"manifest_sha256": pin, "settlement": str(batch.relative_to(archive)),
                "settlement_sha256": digest((batch / "summary.json").read_bytes()),
                "valuation": panel["provenance"], "sessions": sessions, "rejected_settlement_batches": rejected,
                "ledger": {r["session"]: digest((run / "ledger" / (r["session"] + ".json")).read_bytes()) for r in rows}}
    save_json(run / "scoring-inputs.json", evidence)
    report = score(rows, panel["valuation"], sessions, panel["assets"])
    unobserved = [r["session"] for r in rows if r.get("reason") == "MISSED_DECISION_WINDOW" or r.get("invalid_source_evidence")]
    if unobserved:
        report.update(status="INSUFFICIENT_EVIDENCE", unobserved_cutoffs=unobserved)
    save_json(path, report | {"policy": FORWARD_POLICY, "evaluation_period": [str(FIRST_DAY), str(LAST_DAY)],
                              "inputs_sha256": digest((run / "scoring-inputs.json").read_bytes())})
    return read(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["scheduled", "once", "finalize", "rehearsal"])
    parser.add_argument("--archive", type=Path, default=Path("/archive"))
    parser.add_argument("--output", type=Path, default=Path("/results"))
    args = parser.parse_args()
    now = clock()
    rehearsal = args.mode == "rehearsal"
    run = args.output / ("rehearsals/" + now.strftime("%Y%m%dT%H%M%S%fZ") if rehearsal else "evaluation")
    run.mkdir(parents=True, exist_ok=True)
    with (run / ".lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        pin = freeze(args.archive, run)
        if rehearsal:
            day = now.astimezone(VIETNAM).date()
            available = batches(args.archive, ["rehearsal"], day)
            batch, sessions = latest_calendar(args.archive, available, now, rehearsal=True)
            day = date.fromisoformat(sessions[-1])
            result = record_decision(args.archive, run, batch, day, 0, now, [], pin, rehearsal=True)
            print(json.dumps({k: result[k] for k in ("session", "status", "reason") if k in result}), flush=True)
            return
        if args.mode == "finalize":
            print(json.dumps(finalize(args.archive, run, now)))
            return
        print(json.dumps({"policy": FORWARD_POLICY, "manifest_sha256": pin, "status": "STARTED"}), flush=True)
        previous = None
        while True:
            now = clock()
            try:
                if now.astimezone(VIETNAM).date() > SETTLE_UNTIL:
                    result = finalize(args.archive, run, now)
                    if args.mode == "scheduled":
                        print(json.dumps({"status": result["status"]}), flush=True)
                        from threading import Event
                        Event().wait()
                else:
                    result = tick(args.archive, run, now, pin)
                if previous != result:
                    print(json.dumps(result), flush=True)
                previous = result
            except Exception:
                if args.mode != "scheduled":
                    raise
                logging.exception("Forward study tick failed")
            if args.mode != "scheduled":
                return
            sleep(3600 if now.astimezone(VIETNAM).date() > SETTLE_UNTIL else 30)


if __name__ == "__main__":
    main()
