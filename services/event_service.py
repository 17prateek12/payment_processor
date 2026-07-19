from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
import psycopg2.errors
from dtos.request import IngestEventRequest
from dtos.response import IngestEventResponse


# ── Status transition rules ───────────────────────────────────
# Defines how each event_type updates payment_status and settlement_status
# on the transaction row. None means "do not update that column."
#
# To add a new lifecycle event in future (e.g. "refund_initiated"):
# just add a new entry here — no other code needs to change.

STATUS_TRANSITIONS = {
    "payment_initiated": {
        "payment_status": "initiated",
        "settlement_status": None
    },
    "payment_processed": {
        "payment_status": "processed",
        "settlement_status": None
    },
    "payment_failed": {
        "payment_status": "failed",
        "settlement_status": None
    },
    "settled": {
        "payment_status": None,
        "settlement_status": "settled"
    },
}


def process_event(db: Session, payload: IngestEventRequest) -> IngestEventResponse:
    """
    Core event processing logic — transport agnostic.

    This function is intentionally decoupled from HTTP.
    It can be called from:
      - POST /events handler (current)
      - Kafka consumer (future) — same function, zero changes needed

    Flow:
      1. Upsert merchant
      2. Upsert transaction + update status (only if event is newer than current state)
      3. Insert event row (PRIMARY KEY on event_id enforces idempotency at DB level)
      4. Commit all as one atomic DB transaction
      5. If UniqueViolation → duplicate event_id, rollback and return gracefully
         If any other IntegrityError → real DB bug, re-raise it

    Bug fixes applied:
      FIX 1 — Out-of-order events:
        UPDATE transactions only if payload.timestamp > transactions.updated_at
        A late-arriving event will never regress transaction state

      FIX 2 — Loose IntegrityError catching:
        We now check specifically for psycopg2.errors.UniqueViolation
        Any other IntegrityError (FK violation, NOT NULL, etc.) is re-raised
        so the global error handler catches it properly instead of masking it
    """

    transition = STATUS_TRANSITIONS[payload.event_type]
    now = datetime.now(timezone.utc)

    try:
        # ── Step 1: Upsert merchant ───────────────────────────
        # ON CONFLICT DO NOTHING — safe to call on every event
        db.execute(
            text("""
                INSERT INTO merchants (id, merchant_name)
                VALUES (:id, :merchant_name)
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": payload.merchant_id,
                "merchant_name": payload.merchant_name
            }
        )

        # ── Step 2: Upsert transaction ────────────────────────
        # INSERT → new transaction, set initial status from this event
        # ON CONFLICT (id) DO UPDATE → transaction exists:
        #   only update status if this event's timestamp is NEWER than
        #   what we already have — prevents out-of-order late arrivals
        #   from regressing transaction state backwards
        #
        # Example: payment_initiated arrives after payment_processed
        #   → updated_at check fails → UPDATE is skipped → state stays correct

        if transition["payment_status"] and transition["settlement_status"]:
            status_set_clause = """
                payment_status = :payment_status,
                settlement_status = :settlement_status,
                updated_at = :updated_at
            """
            status_params = {
                "payment_status": transition["payment_status"],
                "settlement_status": transition["settlement_status"],
                "updated_at": payload.timestamp
            }
        elif transition["payment_status"]:
            status_set_clause = """
                payment_status = :payment_status,
                updated_at = :updated_at
            """
            status_params = {
                "payment_status": transition["payment_status"],
                "updated_at": payload.timestamp
            }
        else:
            status_set_clause = """
                settlement_status = :settlement_status,
                updated_at = :updated_at
            """
            status_params = {
                "settlement_status": transition["settlement_status"],
                "updated_at": payload.timestamp
            }

        db.execute(
            text(f"""
                INSERT INTO transactions (
                    id, merchant_id, amount, currency,
                    payment_status, settlement_status,
                    created_at, updated_at
                ) VALUES (
                    :id, :merchant_id, :amount, :currency,
                    :payment_status, :settlement_status,
                    :created_at, :updated_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    {status_set_clause}
                WHERE transactions.updated_at < :updated_at
            """),
            {
                "id": payload.transaction_id,
                "merchant_id": payload.merchant_id,
                "amount": payload.amount,
                "currency": payload.currency,
                "payment_status": transition["payment_status"] or "initiated",
                "settlement_status": transition["settlement_status"] or "unsettled",
                "created_at": payload.timestamp,
                "updated_at": payload.timestamp,
                **status_params
            }
        )

        # ── Step 3: Insert event ──────────────────────────────
        # event_id is PRIMARY KEY — duplicate insert raises UniqueViolation
        # which is a subtype of IntegrityError, caught specifically below
        # We always insert the event regardless of whether the transaction
        # status was updated — event history is always preserved (Option B)
        db.execute(
            text("""
                INSERT INTO events (
                    event_id, transaction_id, event_type,
                    event_timestamp, received_at
                ) VALUES (
                    :event_id, :transaction_id, :event_type,
                    :event_timestamp, :received_at
                )
            """),
            {
                "event_id": payload.event_id,
                "transaction_id": payload.transaction_id,
                "event_type": payload.event_type,
                "event_timestamp": payload.timestamp,
                "received_at": now
            }
        )

        # ── Step 4: Commit ────────────────────────────────────
        # merchant upsert + transaction upsert + event insert
        # all commit together or all roll back — no partial state possible
        db.commit()

        return IngestEventResponse(
            success=True,
            message="Event ingested successfully",
            event_id=payload.event_id,
            transaction_id=payload.transaction_id,
            is_duplicate=False
        )

    except IntegrityError as e:
        db.rollback()

        # ── FIX 2: Check specifically which constraint fired ──
        # UniqueViolation = duplicate event_id → expected, handle gracefully
        # Anything else = real DB bug (FK violation, NOT NULL, etc.)
        #   → re-raise so global error handler catches it properly
        #   → never silently swallow real errors as "duplicate"
        if isinstance(e.orig, psycopg2.errors.UniqueViolation):
            return IngestEventResponse(
                success=True,
                message="Duplicate event, ignored",
                event_id=payload.event_id,
                transaction_id=payload.transaction_id,
                is_duplicate=True
            )
        else:
            raise


def ingest_event(db: Session, payload: IngestEventRequest) -> IngestEventResponse:
    """
    HTTP entry point — called by POST /events router.

    Thin wrapper around process_event().
    When Kafka is added, create a consumer that calls process_event() directly
    with the same IngestEventRequest payload — this function stays HTTP-only.
    """
    return process_event(db, payload)

