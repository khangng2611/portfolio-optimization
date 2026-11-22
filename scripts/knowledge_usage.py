"""Read token-free invocation aggregates from the two owner databases; no provider calls."""

import argparse
import json
from decimal import Decimal
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def summarize(records):
    result = {}
    for row in records:
        purpose = row["purpose"]
        g = result.setdefault(
            purpose,
            {
                "reservations": 0,
                "uncertain_reservations": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "reserved_usd": "0",
                "estimated_usd": "0",
            },
        )
        d = row.get("details") or {}
        g["reservations"] += 1
        g["uncertain_reservations"] += int("input_tokens" not in d)
        g["input_tokens"] += d.get("input_tokens", 0)
        g["output_tokens"] += d.get("output_tokens", 0)
        g["reserved_usd"] = str(
            Decimal(g["reserved_usd"]) + Decimal(row.get("reserved_usd", "0"))
        )
        g["estimated_usd"] = str(
            Decimal(g["estimated_usd"]) + Decimal(str(d.get("estimated_cost_usd", 0)))
        )
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--since")
    p.add_argument("--approval-id")
    a = p.parse_args()
    rows = []
    for name, model, purpose in [
        ("chat", "ProviderInvocation", None),
        ("knowledge", "EmbeddingInvocation", "ingestion_embedding"),
    ]:
        code = f"""import json,sys
from datetime import datetime
from {name}_service.runtime import sessions_from_env
from {name}_service.models import {model}
from sqlalchemy import select
options=json.loads(sys.argv[1])
with sessions_from_env()() as s:
 q=select({model})
 if options['since']:q=q.where({model}.created_at>=datetime.fromisoformat(options['since']))
 if options['approval']:q=q.where({model}.budget_id==options['approval'])
 print(json.dumps([{{'purpose':{repr(purpose)} or r.purpose,'details':r.details,'reserved_usd':r.reserved_usd}} for r in s.scalars(q)]))
"""
        cmd = [
            "docker",
            "compose",
            "--env-file",
            str(ROOT / "infra/local/.generated/.env"),
            "-f",
            str(ROOT / "infra/local/compose.yaml"),
            "exec",
            "-T",
            name + "-api",
            "python",
            "-",
            json.dumps({"since": a.since, "approval": a.approval_id}),
        ]
        r = subprocess.run(cmd, input=code, text=True, capture_output=True, timeout=20)
        if r.returncode:
            raise SystemExit("Usage query failed; raw DB output suppressed")
        rows.extend(json.loads(r.stdout))
    print(
        json.dumps(
            {
                "scope": {"since": a.since, "approval_id": a.approval_id},
                "usage": summarize(rows),
                "provider_calls_made_by_report": 0,
                "estimate_is_bill": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
