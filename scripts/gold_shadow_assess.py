"""Refresh the private paper-performance report from committed observer receipts."""
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep

from sqlalchemy import create_engine, text

from scripts.gold_shadow_marks import Captures
from scripts.gold_shadow_score import report, PROTOCOL_SHA256
from portfolio_contracts import canonical_hash
from quant_service.gold_shadow_receipt import confirmed_receipt


def refresh(engine, captures, target):
    now = datetime.now(timezone.utc)
    rows = []
    pending = 0
    with engine.connect() as connection:
        for receipt, seen, digest in connection.execute(text(
            "SELECT d.receipt, w.witnessed_at, w.receipt_sha256 FROM gold_shadow_decision AS d "
            "LEFT JOIN gold_shadow_witness AS w ON w.job_id = d.job_id ORDER BY d.job_id"
        )):
            if seen is None or seen > now:
                pending += 1
            else:
                rows.append(confirmed_receipt(receipt, seen, digest))
    result = report(rows, Captures(captures, now), now)
    result.update(receipt_count=len(rows), awaiting_durability_witness=pending,
                  ordered_receipts_sha256=canonical_hash([r["receipt_sha256"] for r in rows]))
    if result["protocol_sha256"] != PROTOCOL_SHA256:
        raise ValueError("Unexpected assessment protocol")
    with NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as stream:
        tmp = Path(stream.name)
        try:
            json.dump(result, stream, sort_keys=True, allow_nan=False, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
    return {k: result[k] for k in ("as_of", "receipt_count", "mature_context_dates", "status")}


if __name__ == "__main__":
    database = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    while True:
        try:
            print(json.dumps(refresh(database, Path("/archive"), Path("/results/latest.json"))), flush=True)
        except Exception:
            logging.exception("Could not refresh GOLD shadow assessment")
        sleep(3600)
