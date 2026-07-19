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
    transition = STATUS_TRANSITIONS[payload.event_type]
    now = datetime.now(timezone.utc)

    try:
        # ── Step 1: Upsert merchant ───────────────────────────
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

        if transition["payment_status"] and transition["settlement_status"]:
            status_set_clause = """
                payment_status = :payment_status,
                settlement_status = :settlement_status,
                version = transactions.version + 1,
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
                version = transactions.version + 1,
                updated_at = :updated_at
            """
            status_params = {
                "payment_status": transition["payment_status"],
                "updated_at": payload.timestamp
            }
        else:
            status_set_clause = """
                settlement_status = :settlement_status,
                version = transactions.version + 1,
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
                    payment_status, settlement_status, version,
                    created_at, updated_at
                ) VALUES (
                    :id, :merchant_id, :amount, :currency,
                    :payment_status, :settlement_status, 1,
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
    return process_event(db, payload)

