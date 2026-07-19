from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime

class IngestEventRequest(BaseModel):
    event_id: str = Field(..., description="Unique event identifier - used for idempotency")
    event_type: Literal[
        "payment_initiated",
        "payment_processed",
        "payment_failed",
        "settled"
    ] = Field(..., description="Type of payment lifecycle event")
    transaction_id: str = Field(..., description="Transaction this event belongs to")
    merchant_id: str = Field(..., description="Merchant identifier e.g. merchant_2")
    merchant_name: str = Field(..., description="Human readable merchant name")
    amount: float = Field(..., gt=0, description="Transaction amount, must be positive")
    currency: str = Field(..., min_length=3, max_length=10, description="Currency code e.g. INR")
    timestamp: datetime = Field(..., description="When this event occurred in the payment system")