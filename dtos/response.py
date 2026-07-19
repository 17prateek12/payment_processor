from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# ── POST /events ──────────────────────────────────────────────

class IngestEventResponse(BaseModel):
    success: bool
    message: str
    event_id: str
    transaction_id: str
    is_duplicate: bool

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Event ingested successfully",
                "event_id": "9e8da688-a544-469a-b012-a44055766fcc",
                "transaction_id": "7be49e52-8829-42fd-b65e-d7b777e980f0",
                "is_duplicate": False
            }
        }


# ── GET /transactions ─────────────────────────────────────────

class TransactionSummary(BaseModel):
    id: str
    merchant_id: str
    merchant_name: str
    amount: float
    currency: str
    payment_status: str
    settlement_status: str
    version: int
    created_at: datetime
    updated_at: datetime


class PaginatedTransactionsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    data: list[TransactionSummary]


# ── GET /transactions/:id ─────────────────────────────────────

class EventHistory(BaseModel):
    event_id: str
    event_type: str
    event_timestamp: datetime
    received_at: datetime


class TransactionDetailResponse(BaseModel):
    id: str
    merchant_id: str
    merchant_name: str
    amount: float
    currency: str
    payment_status: str
    settlement_status: str
    version: int
    created_at: datetime
    updated_at: datetime
    event_history: list[EventHistory]


# ── GET /reconciliation/summary ───────────────────────────────

class ReconciliationSummaryItem(BaseModel):
    merchant_id: str
    merchant_name: str
    date: str
    payment_status: str
    settlement_status: str
    total_transactions: int
    total_amount: float


class ReconciliationSummaryResponse(BaseModel):
    data: list[ReconciliationSummaryItem]


# ── GET /reconciliation/discrepancies ────────────────────────

class DiscrepancyItem(BaseModel):
    transaction_id: str
    merchant_id: str
    merchant_name: str
    amount: float
    currency: str
    payment_status: str
    settlement_status: str
    version: int
    discrepancy_reason: str
    created_at: datetime
    updated_at: datetime


class ReconciliationDiscrepanciesResponse(BaseModel):
    total: int
    data: list[DiscrepancyItem]