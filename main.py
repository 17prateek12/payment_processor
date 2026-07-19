from contextlib import asynccontextmanager
from fastapi import FastAPI
from config.db import init_db
from routers import events, transactions, reconciliation
from middleware.error_handler import register_error_handlers
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Payment Processor API",
    description="Payment lifecycle event ingestion and reconciliation service",
    version="1.0.0",
    lifespan=lifespan
)

# ── Error handlers ────────────────────────────────────────────
register_error_handlers(app)

# ── Routers ───────────────────────────────────────────────────
app.include_router(events.router)
app.include_router(transactions.router)
app.include_router(reconciliation.router)


# ── Health check ──────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}