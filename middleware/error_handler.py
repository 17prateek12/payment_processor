from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
import logging

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI): 

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = []
        for error in exc.errors():
            errors.append({
                "field": " → ".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"]
            })

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": "Validation failed",
                "details": errors
            }
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.detail
            }
        )


    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        logger.error(f"DB integrity error: {exc}")
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "Data integrity violation",
                "detail": "The request conflicts with existing data"
            }
        )

    @app.exception_handler(OperationalError)
    async def db_operational_error_handler(request: Request, exc: OperationalError):
        logger.error(f"DB operational error: {exc}")
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "Database unavailable",
                "detail": "Service temporarily unavailable, please try again"
            }
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(
            f"Unhandled exception on {request.method} {request.url}: {exc}",
            exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Internal server error",
                "detail": "An unexpected error occurred"
            }
        )