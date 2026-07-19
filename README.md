# Payment Processor Service

A backend service for ingesting payment lifecycle events, maintaining transaction state, and identifying reconciliation discrepancies.

Built with FastAPI + PostgreSQL.

---

## Architecture Overview

```
POST /events
     │
     ▼
Event Service (process_event)
     │
     ├── Upsert Merchant
     ├── Upsert Transaction + update status (timestamp-guarded)
     └── Insert Event (idempotency via PRIMARY KEY)
          │
          └── Commit (all three or none)

GET /transactions
GET /transactions/:id
GET /reconciliation/summary
GET /reconciliation/discrepancies
     │
     ▼
SQL queries directly against PostgreSQL
(all filtering, sorting, pagination, aggregation in SQL — no Python loops)
```

### Key design decisions

**Events as source of truth.** Every incoming event is stored in the `events` table regardless of whether it changes transaction state. The events table is append-only and never modified. Discrepancies are detected at read time by querying event history — not by rejecting events at ingestion.

**Materialized transaction status.** `payment_status` and `settlement_status` are stored directly on the `transactions` row and updated on each event. This makes `GET /transactions?status=failed` a simple indexed lookup instead of a recomputed aggregation over event history on every read.

**Three tables, no more.** Reconciliation state is not a separate table — it's two columns (`payment_status`, `settlement_status`) on `transactions`, updated atomically with each event. Discrepancy queries read event history using `INTERSECT`, `EXCEPT`, and `HAVING COUNT > 1` entirely in SQL.

---

## Local Setup

### Prerequisites

- Docker + Docker Compose
- Python 3.12+

### 1. Clone and set up environment

```bash
git clone https://github.com/17prateek12/payment_processor
cd payment_processor
cp .env.example .env
```

`.env` contents:
```
DATABASE_URL=postgresql://admin:admin123@localhost:5435/setu_db
```

### 2. Start PostgreSQL

```bash
docker-compose up -d
```

This starts:
- PostgreSQL 15 on port `5435`
- Adminer (DB browser) on port `8082`

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the server

```bash
uvicorn main:app --reload
```

Schema is auto-created on startup. Server runs at `http://localhost:8000`.

### 5. Seed sample data

```bash
python seed.py
```

Loads `sample_events.json` (~10,355 events) via `POST /events`. Takes about 90 seconds. Expected output:

```
Seed Complete
-----------------------------------------
Total events  : 10355
Inserted      : 10165
Duplicates    : 190     ← handled correctly, not errors
Failed        : 0
-----------------------------------------
```

### 6. Browse DB (optional)

Open `http://localhost:8082` and log in:

| Field    | Value    |
|----------|----------|
| System   | PostgreSQL |
| Server   | postgres |
| Username | admin    |
| Password | admin123 |
| Database | setu_db  |

---

## API Documentation

Interactive docs available at `http://localhost:8000/docs` after startup.

### POST /events

Ingest a payment lifecycle event.

**Request body:**
```json
{
  "event_id": "9e8da688-a544-469a-b012-a44055766fcc",
  "event_type": "payment_initiated",
  "transaction_id": "7be49e52-8829-42fd-b65e-d7b777e980f0",
  "merchant_id": "merchant_3",
  "merchant_name": "UrbanEats",
  "amount": 33113.09,
  "currency": "INR",
  "timestamp": "2026-01-09T10:49:40.287497+00:00"
}
```

**Supported event types:** `payment_initiated` | `payment_processed` | `payment_failed` | `settled`

**Status codes:**
- `201` — new event ingested successfully
- `200` — duplicate `event_id`, safely ignored
- `422` — validation error (missing field, invalid event type)
- `500` — unexpected server error

**Response:**
```json
{
  "success": true,
  "message": "Event ingested successfully",
  "event_id": "9e8da688-a544-469a-b012-a44055766fcc",
  "transaction_id": "7be49e52-8829-42fd-b65e-d7b777e980f0",
  "is_duplicate": false
}
```

---

### GET /transactions

List transactions with filters, sorting and pagination.

**Query params:**

| Param              | Type   | Default      | Description                              |
|--------------------|--------|--------------|------------------------------------------|
| `merchant_id`      | string | —            | Filter by merchant e.g. `merchant_2`     |
| `payment_status`   | string | —            | `initiated` / `processed` / `failed`     |
| `settlement_status`| string | —            | `unsettled` / `settled`                  |
| `date_from`        | string | —            | `YYYY-MM-DD` — created on or after       |
| `date_to`          | string | —            | `YYYY-MM-DD` — created on or before      |
| `page`             | int    | `1`          | Page number                              |
| `page_size`        | int    | `20`         | Rows per page (max 100)                  |
| `sort_by`          | string | `created_at` | `created_at` / `updated_at` / `amount`   |
| `sort_order`       | string | `desc`       | `asc` / `desc`                           |

**Example:**
```
GET /transactions?merchant_id=merchant_2&payment_status=failed&page=1&page_size=20
```

**Response:**
```json
{
  "total": 142,
  "page": 1,
  "page_size": 20,
  "total_pages": 8,
  "data": [
    {
      "id": "7be49e52-...",
      "merchant_id": "merchant_2",
      "merchant_name": "FreshBasket",
      "amount": 15732.16,
      "currency": "INR",
      "payment_status": "failed",
      "settlement_status": "unsettled",
      "version": 2,
      "created_at": "2026-01-09T10:50:54Z",
      "updated_at": "2026-01-09T10:59:54Z"
    }
  ]
}
```

The `version` field increments on every status update. Clients can use it to detect whether a transaction changed between two separate reads.

---

### GET /transactions/{transaction_id}

Fetch full details for a single transaction including complete event history.

**Response:**
```json
{
  "id": "7be49e52-...",
  "merchant_id": "merchant_2",
  "merchant_name": "FreshBasket",
  "amount": 15732.16,
  "currency": "INR",
  "payment_status": "processed",
  "settlement_status": "settled",
  "version": 3,
  "created_at": "2026-01-09T10:50:54Z",
  "updated_at": "2026-01-09T11:30:00Z",
  "event_history": [
    {
      "event_id": "e06cbe07-...",
      "event_type": "payment_initiated",
      "event_timestamp": "2026-01-09T10:50:54Z",
      "received_at": "2026-01-09T10:50:55Z"
    },
    {
      "event_id": "dc58d280-...",
      "event_type": "payment_processed",
      "event_timestamp": "2026-01-09T10:59:54Z",
      "received_at": "2026-01-09T10:59:55Z"
    },
    {
      "event_id": "00e74fbe-...",
      "event_type": "settled",
      "event_timestamp": "2026-01-09T11:30:00Z",
      "received_at": "2026-01-09T11:30:01Z"
    }
  ]
}
```

**Status codes:** `200` success, `404` transaction not found

---

### GET /reconciliation/summary

Returns transaction counts and amounts grouped by merchant, date and status.

**Query params:** `merchant_id`, `date_from`, `date_to` (same as above)

**Response:**
```json
{
  "total_groups": 24,
  "data": [
    {
      "merchant_id": "merchant_2",
      "merchant_name": "FreshBasket",
      "date": "2026-01-09",
      "payment_status": "processed",
      "settlement_status": "settled",
      "total_transactions": 142,
      "total_amount": 1842500.50
    }
  ]
}
```

---

### GET /reconciliation/discrepancies

Returns transactions where payment state and settlement state are inconsistent. Discrepancies are detected by querying event history directly — not just transaction status columns.

**Query params:** `merchant_id`, `date_from`, `date_to`

**Discrepancy types:**

| `discrepancy_reason`        | What it means                                                    |
|-----------------------------|------------------------------------------------------------------|
| `PROCESSED_NOT_SETTLED`     | Payment succeeded but settlement never arrived                   |
| `FAILED_BUT_SETTLED`        | Settlement recorded for a payment that failed                    |
| `DOUBLE_SETTLED`            | Two separate `settled` events received for the same transaction  |
| `FAILED_AFTER_PROCESSED`    | Transaction has both `payment_processed` and `payment_failed`    |
| `SETTLED_WITHOUT_PROCESSING`| Settlement arrived but no `payment_processed` event exists       |

**Response:**
```json
{
  "total": 47,
  "data": [
    {
      "transaction_id": "c2d2bfa1-...",
      "merchant_id": "merchant_4",
      "merchant_name": "TechBazaar",
      "amount": 12745.93,
      "currency": "INR",
      "payment_status": "processed",
      "settlement_status": "unsettled",
      "discrepancy_reason": "PROCESSED_NOT_SETTLED",
      "created_at": "2026-01-09T19:57:41Z",
      "updated_at": "2026-01-09T19:57:41Z"
    }
  ]
}
```

---

### GET /health

```json
{ "status": "ok" }
```

---

## Schema

```sql
merchants        → id (PK), merchant_name, created_at
transactions     → id (PK), merchant_id (FK), amount, currency,
                   payment_status, settlement_status, version,
                   created_at, updated_at
events           → event_id (PK), transaction_id (FK),
                   event_type, event_timestamp, received_at
```

**Indexes:**
- `idx_transactions_merchant_status_date` on `(merchant_id, payment_status, created_at)` — covers merchant filter + status filter + date sort in one scan
- `idx_events_transaction_id` on `events(transaction_id)` — covers event history lookup in `GET /transactions/:id`

Standalone indexes on `payment_status` and `settlement_status` were intentionally avoided — they are low cardinality columns (3 and 2 distinct values respectively) and Postgres would ignore them in favour of a sequential scan anyway.

---

## Deployment

Deployed on Railway at: `<your-url-here>`

The service runs as a single Docker container with PostgreSQL managed separately. Schema is auto-created on startup via `init_db()` in `config/db.py`.

**To deploy your own instance:**

```bash
# Build image
docker build -t payment-processor .

# Run with DB connection
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql://user:pass@host:5432/dbname \
  payment-processor
```

---

## Assumptions and Tradeoffs

**Transaction amount is immutable.**
A transaction either goes through completely or it does not — there is no partial amount scenario. So we store amount once on the transaction table and do not repeat it on every event. Any event for a transaction shares the same amount, fetched via join when needed.

**Event table is source of truth.**
We never reject an event at ingestion based on business logic. If a `payment_failed` arrives after `payment_processed`, both are stored. Discrepancies are identified at read time via `GET /reconciliation/discrepancies` — not silently dropped at write time. This keeps the event history honest and fully auditable.

**Idempotency at DB level, handled gracefully at application level.**
`event_id` is the PRIMARY KEY on the events table. If the same event arrives twice, Postgres rejects it with a `UniqueViolation`. The application catches this specific error and returns `is_duplicate: true` with a `200` instead of a `500`. Any other `IntegrityError` (FK violation, NOT NULL) is re-raised so real bugs are not masked as false duplicates.

**Optimistic locking via version column.**
The `version` column on transactions increments on every status update. This prevents the stale read problem — if a user reads a transaction as `payment_initiated` and a concurrent write changes it to `payment_failed`, the client can detect the change by comparing versions between reads. This is simpler and cheaper than database-level `REPEATABLE READ` isolation.

**Out-of-order events do not corrupt state.**
The transaction upsert includes `WHERE transactions.updated_at < :updated_at`. If a late-arriving event has an older timestamp than what is already stored, the status update is skipped. The event is still recorded in history — state just does not regress.

**Composite index instead of indexing every column individually.**
We index `(merchant_id, payment_status, created_at)` together rather than separately. Indexing `payment_status` or `settlement_status` alone is not useful — they have very low cardinality (3 and 2 distinct values). Postgres would skip those indexes and do a sequential scan anyway. The composite index lets `merchant_id` do the heavy narrowing first, then filters status within that already-small set.

**No Kafka for this assignment.**
The assignment scope is SQL schema design, idempotency handling, and query correctness — not high-throughput ingestion. The sample data is a one-time batch of ~10k events, not a live stream. That said, at production scale handling 10,000 events per second, Kafka would absolutely be needed for buffering and backpressure. The core ingestion logic lives in `process_event()` which is already written transport-agnostically — a Kafka consumer would call the same function with zero changes to the processing logic.

---

## AI Tool Disclosure

I used Claude (Anthropic) as a thinking partner while building this — mainly to challenge and validate my own decisions, not to generate code.

A few specific examples:

**Schema design.** Claude initially suggested a schema. I came back with my own version — three clean tables, no redundant columns — and we finalized mine. One specific discussion was whether to put `merchant_id` on the events table directly, so that event could be a single source without needing a two-hop join (event → transaction → merchant). We decided against it because it introduces denormalization and data integrity risk with minimal real-world performance gain, especially since we already have indexes covering the join path.

**Amount in events table.** Claude suggested storing amount on every event row to detect amount drift. I pushed back — a transaction is atomic, amount never changes mid-lifecycle, and we can always join back to the transaction for it. My reasoning held and we dropped it.

**Idempotency.** I proposed making `event_id` the PRIMARY KEY rather than adding a separate UNIQUE constraint. Claude confirmed it and explained the `UniqueViolation` vs generic `IntegrityError` distinction, which I then implemented to avoid masking real DB errors.

**Stale read problem.** I raised the scenario where a user reads a transaction, and a concurrent update changes its state before they read again. Claude confirmed `REPEATABLE READ` isolation does not fix HTTP-level staleness and suggested the `version` column for optimistic locking, which I added.

All architectural decisions, tradeoffs, and the final direction of the implementation are my own. The conversation helped me think faster, not think differently.