from sqlalchemy.orm import Session
from sqlalchemy import text


def get_reconciliation_summary(
    db: Session,
    merchant_id: str = None,
    date_from: str = None,
    date_to: str = None
):
    """
    Returns transaction summaries grouped by merchant, date and status.

    All aggregation happens in SQL — GROUP BY with COUNT and SUM.
    No Python loops over rows.

    Filters:
    - merchant_id → narrow to specific merchant
    - date_from   → YYYY-MM-DD
    - date_to     → YYYY-MM-DD
    """

    filters = []
    params = {}

    if merchant_id:
        filters.append("t.merchant_id = :merchant_id")
        params["merchant_id"] = merchant_id

    if date_from:
        filters.append("t.created_at >= :date_from")
        params["date_from"] = date_from

    if date_to:
        filters.append("t.created_at <= :date_to")
        params["date_to"] = date_to

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    query = text(f"""
        SELECT
            t.merchant_id,
            m.merchant_name,
            DATE(t.created_at)      AS date,
            t.payment_status,
            t.settlement_status,
            COUNT(*)                AS total_transactions,
            SUM(t.amount)           AS total_amount
        FROM transactions t
        JOIN merchants m ON t.merchant_id = m.id
        {where_clause}
        GROUP BY
            t.merchant_id,
            m.merchant_name,
            DATE(t.created_at),
            t.payment_status,
            t.settlement_status
        ORDER BY
            t.merchant_id,
            date DESC,
            t.payment_status
    """)

    rows = db.execute(query, params).mappings().fetchall()

    return {
        "total_groups": len(rows),
        "data": [dict(row) for row in rows]
    }


def get_reconciliation_discrepancies(
    db: Session,
    merchant_id: str = None,
    date_from: str = None,
    date_to: str = None
):
    filters = []
    params = {}

    if merchant_id:
        filters.append("t.merchant_id = :merchant_id")
        params["merchant_id"] = merchant_id

    if date_from:
        filters.append("t.created_at >= :date_from")
        params["date_from"] = date_from

    if date_to:
        filters.append("t.created_at <= :date_to")
        params["date_to"] = date_to

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""
    and_clause = ("AND " + " AND ".join(filters)) if filters else ""

    query = text(f"""
        -- ── Type 1: PROCESSED_NOT_SETTLED ──────────────────────────────
        -- payment went through but settlement never arrived
        SELECT
            t.id                        AS transaction_id,
            t.merchant_id,
            m.merchant_name,
            t.amount,
            t.currency,
            t.payment_status,
            t.settlement_status,
            'PROCESSED_NOT_SETTLED'     AS discrepancy_reason,
            t.created_at,
            t.updated_at
        FROM transactions t
        JOIN merchants m ON t.merchant_id = m.id
        {where_clause}
        {"AND" if filters else "WHERE"} t.payment_status = 'processed'
        AND t.settlement_status = 'unsettled'

        UNION ALL

        -- ── Type 2: FAILED_BUT_SETTLED ──────────────────────────────────
        -- settlement recorded for a payment that failed
        SELECT
            t.id                        AS transaction_id,
            t.merchant_id,
            m.merchant_name,
            t.amount,
            t.currency,
            t.payment_status,
            t.settlement_status,
            'FAILED_BUT_SETTLED'        AS discrepancy_reason,
            t.created_at,
            t.updated_at
        FROM transactions t
        JOIN merchants m ON t.merchant_id = m.id
        {where_clause}
        {"AND" if filters else "WHERE"} t.payment_status = 'failed'
        AND t.settlement_status = 'settled'

        UNION ALL

        -- ── Type 3a: DOUBLE_SETTLED ──────────────────────────────────────
        -- same transaction received more than one settled event
        -- different event_ids so both passed idempotency check
        -- detected by counting settled events per transaction in event history
        SELECT
            t.id                        AS transaction_id,
            t.merchant_id,
            m.merchant_name,
            t.amount,
            t.currency,
            t.payment_status,
            t.settlement_status,
            'DOUBLE_SETTLED'            AS discrepancy_reason,
            t.created_at,
            t.updated_at
        FROM transactions t
        JOIN merchants m ON t.merchant_id = m.id
        WHERE t.id IN (
            SELECT transaction_id
            FROM events
            WHERE event_type = 'settled'
            GROUP BY transaction_id
            HAVING COUNT(*) > 1
        )
        {and_clause}

        UNION ALL

        -- ── Type 3b: FAILED_AFTER_PROCESSED ─────────────────────────────
        -- transaction has both payment_processed and payment_failed events
        -- payment cannot fail after it already succeeded
        -- source of truth: event history, not just current transaction status
        SELECT
            t.id                        AS transaction_id,
            t.merchant_id,
            m.merchant_name,
            t.amount,
            t.currency,
            t.payment_status,
            t.settlement_status,
            'FAILED_AFTER_PROCESSED'    AS discrepancy_reason,
            t.created_at,
            t.updated_at
        FROM transactions t
        JOIN merchants m ON t.merchant_id = m.id
        WHERE t.id IN (
            SELECT transaction_id FROM events WHERE event_type = 'payment_processed'
            INTERSECT
            SELECT transaction_id FROM events WHERE event_type = 'payment_failed'
        )
        {and_clause}

        UNION ALL

        -- ── Type 3c: SETTLED_WITHOUT_PROCESSING ─────────────────────────
        -- transaction has a settled event but no payment_processed event
        -- settlement arrived for a payment that was never confirmed processed
        SELECT
            t.id                        AS transaction_id,
            t.merchant_id,
            m.merchant_name,
            t.amount,
            t.currency,
            t.payment_status,
            t.settlement_status,
            'SETTLED_WITHOUT_PROCESSING' AS discrepancy_reason,
            t.created_at,
            t.updated_at
        FROM transactions t
        JOIN merchants m ON t.merchant_id = m.id
        WHERE t.id IN (
            SELECT transaction_id FROM events WHERE event_type = 'settled'
            EXCEPT
            SELECT transaction_id FROM events WHERE event_type = 'payment_processed'
        )
        {and_clause}

        ORDER BY created_at DESC
    """)

    rows = db.execute(query, params).mappings().fetchall()

    return {
        "total": len(rows),
        "data": [dict(row) for row in rows]
    }