from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from config.db import get_db
from dtos.response import PaginatedTransactionsResponse, TransactionDetailResponse
from services.transaction_service import get_transactions, get_transaction_by_id

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.get(
    "",
    response_model=PaginatedTransactionsResponse,
    summary="List transactions",
    description="""
    Returns a paginated list of transactions with optional filters.

    **Filters:**
    - `merchant_id`       → filter by specific merchant e.g. merchant_2
    - `payment_status`    → initiated | processed | failed
    - `settlement_status` → unsettled | settled
    - `date_from`         → YYYY-MM-DD, transactions created on or after
    - `date_to`           → YYYY-MM-DD, transactions created on or before

    **Pagination:**
    - `page`      → page number, default 1
    - `page_size` → rows per page, default 20, max 100

    **Sorting:**
    - `sort_by`    → created_at | updated_at | amount, default created_at
    - `sort_order` → asc | desc, default desc
    """
)
def list_transactions(
    merchant_id: Optional[str] = Query(None, description="Filter by merchant ID"),
    payment_status: Optional[str] = Query(None, description="initiated | processed | failed"),
    settlement_status: Optional[str] = Query(None, description="unsettled | settled"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Rows per page"),
    sort_by: str = Query("created_at", description="created_at | updated_at | amount"),
    sort_order: str = Query("desc", description="asc | desc"),
    db: Session = Depends(get_db)
):
    return get_transactions(
        db=db,
        merchant_id=merchant_id,
        payment_status=payment_status,
        settlement_status=settlement_status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order
    )


@router.get(
    "/{transaction_id}",
    response_model=TransactionDetailResponse,
    summary="Get transaction details",
    description="""
    Returns full details for a single transaction including:
    - Transaction details and current status
    - Merchant information
    - Complete event history in chronological order
    """
)
def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db)
):
    return get_transaction_by_id(db, transaction_id)