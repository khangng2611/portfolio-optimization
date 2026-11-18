"""Export implementation-owned HTTP and event schemas; no runtime credentials needed."""

import json
from pathlib import Path

from portfolio_contracts import Envelope, OptimizeCommand, OptimizeResult
from portfolio_contracts.market import IngestCommand, IngestionRequest, SnapshotRequest
from portfolio_contracts.selection import (
    AssetCatalogItem, SelectionRevision, SelectionReadiness, SelectionContext, SelectionProof,
)
from market_service.api import create_app as market_app
from portfolio_service.api import create_app as portfolio_app
from quant_service.main import create_app as quant_app
from ml_platform.main import create_app as ml_app
from chat_service.api import create_app as chat_app

from knowledge_service.api import create_app as knowledge_app

root = Path(__file__).resolve().parents[1] / "packages/contracts"
schemas = {
    "schemas/asset-catalog-item-v1.json": AssetCatalogItem.model_json_schema(),
    "schemas/selection-revision-v1.json": SelectionRevision.model_json_schema(),
    "schemas/selection-readiness-v1.json": SelectionReadiness.model_json_schema(),
    "schemas/selection-context-v1.json": SelectionContext.model_json_schema(),
    "schemas/selection-proof-v1.json": SelectionProof.model_json_schema(),
    "openapi/knowledge-v1.json": knowledge_app(sessions=None, verifier=None).openapi(),
    "openapi/chat-v1.json": chat_app(
        sessions=None, verifier=None, tools=None
    ).openapi(),
    "openapi/market-v1.json": market_app(
        sessions=None, verifier=None, provider=None
    ).openapi(),
    "openapi/portfolio-v1.json": portfolio_app(
        sessions=None, verifier=None, resolver=None
    ).openapi(),
    "openapi/quant-v1.json": quant_app(
        sessions=None, verifier=None, catalog=None
    ).openapi(),
    "openapi/ml-v1.json": ml_app(
        sessions=None, verifier=None, directory=None
    ).openapi(),
    "events/envelope-v1.json": Envelope.model_json_schema(),
    "events/optimize-command-v1.json": OptimizeCommand.model_json_schema(),
    "events/optimize-result-v1.json": OptimizeResult.model_json_schema(),
    "events/market-ingest-command-v1.json": IngestCommand.model_json_schema(),
    "events/market-ingestion-request-v1.json": IngestionRequest.model_json_schema(),
    "events/market-snapshot-request-v1.json": SnapshotRequest.model_json_schema(),
}
for name, schema in schemas.items():
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
print(f"Exported {len(schemas)} software contracts")
