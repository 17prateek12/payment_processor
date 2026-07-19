from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from config.db import get_db
from services.reconciliation_service import (
    get_reconciliation_summary,
    get_reconciliation_discrepancies
)

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])


@router.get(
    "/summary",
    summary="Reconciliation summary",
    description="""
    Returns transaction summaries grouped by merchant, date and status.

    Each row in the response represents a unique combination of:
    - merchant
    - date (day)
    - payment_status
    - settlement_status

    With aggregated `total_transactions` and `total_amount` for that group.

    **Filters:**
    - `merchant_id` → narrow to specific merchant
    - `date_from`   → YYYY-MM-DD
    - `date_to`     → YYYY-MM-DD
    """
)
def reconciliation_summary(
    merchant_id: Optional[str] = Query(None, description="Filter by merchant ID"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    return get_reconciliation_summary(
        db=db,
        merchant_id=merchant_id,
        date_from=date_from,
        date_to=date_to
    )


@router.get(
    "/discrepancies",
    summary="Reconciliation discrepancies",
    description="""
    Returns transactions where payment state and settlement state are inconsistent.

    **Three discrepancy types detected:**

    - `PROCESSED_NOT_SETTLED` → payment went through but settlement never arrived
    - `FAILED_BUT_SETTLED`    → settlement recorded for a payment that failed
    - `DUPLICATE_EVENT_TYPE`  → transaction received more than one event of the same type

    **Filters:**
    - `merchant_id` → narrow to specific merchant
    - `date_from`   → YYYY-MM-DD
    - `date_to`     → YYYY-MM-DD
    """
)
def reconciliation_discrepancies(
    merchant_id: Optional[str] = Query(None, description="Filter by merchant ID"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    return get_reconciliation_discrepancies(
        db=db,
        merchant_id=merchant_id,
        date_from=date_from,
        date_to=date_to
    )