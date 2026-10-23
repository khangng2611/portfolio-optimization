"""Export implementation-owned HTTP and event schemas; no runtime credentials needed."""

import json
from pathlib import Path

from portfolio_contracts import Envelope, OptimizeCommand, OptimizeResult
from portfolio_service.api import create_app as portfolio_app
from quant_service.main import create_app as quant_app

root = Path(__file__).resolve().parents[1] / "packages/contracts"
schemas = {
    "openapi/portfolio-v1.json": portfolio_app(
        sessions=None, verifier=None, resolver=None
    ).openapi(),
    "openapi/quant-v1.json": quant_app(
        sessions=None, verifier=None, catalog=None
    ).openapi(),
    "events/envelope-v1.json": Envelope.model_json_schema(),
    "events/optimize-command-v1.json": OptimizeCommand.model_json_schema(),
    "events/optimize-result-v1.json": OptimizeResult.model_json_schema(),
}
for name, schema in schemas.items():
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
print(f"Exported {len(schemas)} software contracts")
