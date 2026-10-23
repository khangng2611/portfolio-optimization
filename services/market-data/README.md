# Market Data owner service

Market owns `market_db`: asset master, append-only price revisions, ingestion
jobs, inbox/outbox and immutable snapshots. It shares wire types and JWT
verification primitives with other services, never their ORM/database access.

Use the [setup/API guide](../../docs/software/SETUP_AND_API_TESTING.md) for the
local stack and Swagger at `http://localhost:8003/docs`. Runtime requires
`DATABASE_URL`, `OIDC_ISSUER`, `OIDC_JWKS_URL`, `DATASET_DIRECTORY`. Separate
migration containers use `MIGRATION_DATABASE_URL`; workers additionally use
their own `BROKER_URL`. AMQPS verifies the certificate and hostname and accepts
an optional `BROKER_CA_FILE`. Each service image runs as UID 10001.

`POST /api/v1/market/ingestions` requires `data-operator`, `market:write` and an
`Idempotency-Key`. It atomically queues a persisted job and outbox command;
the dispatcher publishes to durable `market.ingest.v1` with broker confirms.
Consumer commits inbox deduplication, all revisions and terminal job state
before ack. Failed batch validation rolls back every asset/price write. Quorum
delivery limits and a dead-letter queue bound transient SQL/delivery retries;
jobs still pending after 15 minutes become FAILED. Replays return the same job;
reusing a key for another request returns 409. Only the creator can read a job.

The request supplies either validated observations or a registered `dataset_id`.
The server-side CSV catalog is `DATASET_DIRECTORY/catalog.json`:

```json
{
  "IMPORT_STOCK": {
    "path": "stock.csv",
    "sha256": "<SHA-256 of exact CSV bytes>",
    "asset_id": "AAA",
    "kind": "stock",
    "source_unit": "thousand_VND/share",
    "provider": "approved-import-v1",
    "price_column": "price",
    "price_type": "close"
  }
}
```

CSV columns: `date` (ISO date), the registered price column, optional `symbol`
matching the asset, and optional timezone-aware `published_at`. Encoding is UTF-8
(BOM supported). A dataset is one asset/provider/price convention, at most 4 MiB
and 5000 observations. Registry/checksum is pinned when the job is accepted.
Relative paths must stay inside the registry directory, including symlinks.
Mount input artifacts read-only and create a new registered identity for a new
file version. The public API accepts no arbitrary path/URL.

Units are explicit: stock `VND/share`, fund `VND/unit`, gold `VND/tael`;
`thousand_` prefixes convert by exactly 1000. Prices retain six decimal places.
No forward fill or silent EW/data fallback is performed. An unchanged latest
value deduplicates; corrections append a revision, including a correction that
returns to an earlier price. Price conventions (`close`, `nav`, `bid`, `ask`,
`midpoint`) stay separate. Publication metadata is optional; the service records
availability at ingestion, never invents historical publication time for CSVs.

`POST /api/v1/market/snapshots` pins ordered assets, revision IDs, date range,
content/observation hashes and immutable observation JSON. It rejects absent,
stale or ambiguous provider/convention input. Coverage and interior calendar
gaps are bounded by `max_age_days` (an interior gap is allowed at least one day).
The calendar is explicitly `observed-sessions-only`; it does not certify a full
exchange trading calendar. Repeated identical content returns the same snapshot.
Later corrections preserve old snapshots. As-of filtering uses actual ingestion
availability, so importing old prices today cannot establish that those prices
were available in an earlier historical snapshot.

Reads require a human role and `market:read` with audience `market-api`. Health
is public. Shared assets/prices/snapshots are separate from creator-scoped jobs.
OpenAPI/events are exported under `packages/contracts`.

This milestone supplies durable CSV/normalized-data ingestion for stock/fund/gold.
Live upstream crawling, exchange calendars/corporate actions, and automatic Quant
bundle construction from Market snapshots remain separate work. The local
`DEMO_STOCK` dataset is synthetic and is not the Quant `DEMO` numerical universe.
