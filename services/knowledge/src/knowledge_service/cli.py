"""Operator lifecycle CLI. Token via environment; never accepts a remote corpus URL."""

import argparse
import json
import os
import time
from pathlib import Path
import httpx
from .corpus import load_manifest
from datetime import datetime


def indexing_manifest(root, version=None, available_at=None):
    manifest = load_manifest(root)
    if version is not None:
        if version < 1 or not available_at:
            raise ValueError(
                "Versioned indexing requires a stable explicit available_at"
            )
        stamp = datetime.fromisoformat(available_at)
        if stamp.tzinfo is None:
            raise ValueError("available_at requires timezone")
        for document in manifest.documents:
            document.version, document.available_at = version, stamp
        manifest.name += "-index-v" + str(version)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "action",
        choices=[
            "validate",
            "index",
            "list",
            "activate",
            "deactivate",
            "verify-receipt",
        ],
    )
    p.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2] / "corpus"
    )
    p.add_argument("--corpus-id")
    p.add_argument("--version", type=int)
    p.add_argument(
        "--available-at",
        help="Stable timezone-aware timestamp required for versioned index replay",
    )
    p.add_argument("--key")
    p.add_argument("--reason")
    p.add_argument(
        "--receipt",
        type=Path,
        default=Path("infra/local/.generated/knowledge-receipt.json"),
    )
    a = p.parse_args()
    if a.action == "validate":
        manifest = load_manifest(a.root)
        print(
            json.dumps(
                {
                    "valid": True,
                    "documents": len(manifest.documents),
                    "claims": sum(len(d.claims) for d in manifest.documents),
                }
            )
        )
        return
    token = os.environ.get("KNOWLEDGE_OPERATOR_TOKEN")
    if not token:
        p.error(
            "KNOWLEDGE_OPERATOR_TOKEN required; do not pass credentials in arguments"
        )
    with httpx.Client(
        base_url=os.environ.get("KNOWLEDGE_API_URL", "http://localhost:8006"),
        headers={"Authorization": "Bearer " + token},
        timeout=5,
        follow_redirects=False,
    ) as c:

        def checked(r):
            if r.status_code >= 400:
                raise SystemExit(
                    "Knowledge operation failed: HTTP " + str(r.status_code)
                )
            return r.json()

        if a.action in ("list", "verify-receipt"):
            rows = checked(c.get("/api/v1/knowledge/corpora", params={"limit": 100}))
            if a.action == "verify-receipt":
                receipt = json.loads(a.receipt.read_text())
                row = next((r for r in rows if r["id"] == receipt["id"]), None)
                if not row or any(row.get(k) != v for k, v in receipt.items()):
                    raise SystemExit(
                        "Receipt mismatch (no new indexing/activation performed)"
                    )
                print("PASS: same corpus receipt")
            else:
                print(json.dumps(rows, ensure_ascii=False))
            return
        if not a.key:
            p.error("--key required")
        h = {"Idempotency-Key": a.key}
        if a.action == "index":
            manifest = indexing_manifest(a.root, a.version, a.available_at)
            result = checked(
                c.post(
                    "/api/v1/knowledge/indexing-jobs",
                    json=manifest.model_dump(mode="json"),
                    headers=h,
                )
            )
            until = time.monotonic() + 60
            while (
                result["status"] in ("DRAFT", "INDEXING") and time.monotonic() < until
            ):
                time.sleep(0.5)
                result = checked(
                    c.get("/api/v1/knowledge/indexing-jobs/" + result["id"])
                )
            print(json.dumps(result))
            return
        if not a.corpus_id or not a.version or not a.reason:
            p.error("--corpus-id, --version, --reason required")
        result = checked(
            c.post(
                "/api/v1/knowledge/corpora/" + a.corpus_id + "/" + a.action,
                json={"reason": a.reason},
                headers=h | {"If-Match": '"' + str(a.version) + '"'},
            )
        )
        a.receipt.parent.mkdir(parents=True, exist_ok=True)
        a.receipt.write_text(json.dumps(result, indent=2))
        a.receipt.chmod(0o600)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
