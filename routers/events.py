from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from config.db import get_db
from dtos.request import IngestEventRequest
from dtos.response import IngestEventResponse
from services.event_service import ingest_event

router = APIRouter(prefix="/events", tags=["Events"])


@router.post(
    "",
    response_model=IngestEventResponse,
    status_code=200,
    summary="Ingest a payment lifecycle event",
    description="""
    Accepts a single payment lifecycle event and updates transaction state accordingly.

    **Idempotency:** Submitting the same `event_id` more than once is safe.
    Duplicate events are detected at DB level (event_id PRIMARY KEY) and ignored
    gracefully — no state is corrupted, no 500 error returned.

    **Supported event types:**
    - `payment_initiated` → sets payment_status to initiated
    - `payment_processed` → sets payment_status to processed
    - `payment_failed`   → sets payment_status to failed
    - `settled`          → sets settlement_status to settled
    """
)
def post_event(
    payload: IngestEventRequest,
    db: Session = Depends(get_db)
):
    try:
        result = ingest_event(db, payload)
        status_code = 200 if result.is_duplicate else 201
        return JSONResponse(
            status_code=status_code,
            content=result.model_dump()
        )
 
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")