from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException


def get_transactions(
    db: Session,
    merchant_id: str = None,
    payment_status: str = None,
    settlement_status: str = None,
    date_from: str = None,
    date_to: str = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc"
):
    # Validate inputs 

    valid_payment_statuses = {"initiated", "processed", "failed"}
    valid_settlement_statuses = {"unsettled", "settled"}
    valid_sort_by = {"created_at", "updated_at", "amount"}
    valid_sort_order = {"asc", "desc"}

    if payment_status and payment_status not in valid_payment_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid payment_status. Must be one of: {valid_payment_statuses}"
        )

    if settlement_status and settlement_status not in valid_settlement_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid settlement_status. Must be one of: {valid_settlement_statuses}"
        )

    if sort_by not in valid_sort_by:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by. Must be one of: {valid_sort_by}"
        )

    if sort_order not in valid_sort_order:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_order. Must be one of: {valid_sort_order}"
        )

    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")

    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="page_size must be between 1 and 100")

    # Build WHERE clause dynamically 
    
    filters = []
    params = {}

    if merchant_id:
        filters.append("t.merchant_id = :merchant_id")
        params["merchant_id"] = merchant_id

    if payment_status:
        filters.append("t.payment_status = :payment_status")
        params["payment_status"] = payment_status

    if settlement_status:
        filters.append("t.settlement_status = :settlement_status")
        params["settlement_status"] = settlement_status

    if date_from:
        filters.append("t.created_at >= :date_from")
        params["date_from"] = date_from

    if date_to:
        filters.append("t.created_at <= :date_to")
        params["date_to"] = date_to

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    # Total count query

    count_query = text(f"""
        SELECT COUNT(*) as total
        FROM transactions t
        JOIN merchants m ON t.merchant_id = m.id
        {where_clause}
    """)

    total = db.execute(count_query, params).scalar()

    # Main data query 
  
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    data_query = text(f"""
        SELECT
            t.id,
            t.merchant_id,
            m.merchant_name,
            t.amount,
            t.currency,
            t.payment_status,
            t.settlement_status,
            t.created_at,
            t.updated_at
        FROM transactions t
        JOIN merchants m ON t.merchant_id = m.id
        {where_clause}
        ORDER BY t.{sort_by} {sort_order}
        LIMIT :limit OFFSET :offset
    """)

    rows = db.execute(data_query, params).mappings().fetchall()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "data": [dict(row) for row in rows]
    }


def get_transaction_by_id(db: Session, transaction_id: str):
    """
    Fetch a single transaction with its full event history.

    Returns:
    - transaction details
    - merchant info
    - event history ordered chronologically (oldest first)
    """

    # Fetch transaction + merchant
    txn_query = text("""
        SELECT
            t.id,
            t.merchant_id,
            m.merchant_name,
            t.amount,
            t.currency,
            t.payment_status,
            t.settlement_status,
            t.created_at,
            t.updated_at
        FROM transactions t
        JOIN merchants m ON t.merchant_id = m.id
        WHERE t.id = :transaction_id
    """)

    txn = db.execute(txn_query, {"transaction_id": transaction_id}).mappings().fetchone()

    if not txn:
        raise HTTPException(
            status_code=404,
            detail=f"Transaction {transaction_id} not found"
        )

    # Fetch event history
    events_query = text("""
        SELECT
            event_id,
            event_type,
            event_timestamp,
            received_at
        FROM events
        WHERE transaction_id = :transaction_id
        ORDER BY event_timestamp ASC
    """)

    events = db.execute(
        events_query,
        {"transaction_id": transaction_id}
    ).mappings().fetchall()

    return {
        **dict(txn),
        "event_history": [dict(e) for e in events]
    }