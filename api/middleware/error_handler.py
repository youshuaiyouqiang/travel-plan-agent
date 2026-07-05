from __future__ import annotations

import logging
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse

from application.exceptions.base import ClawException

logger = logging.getLogger(__name__)


async def claw_exception_handler(request: Request, exc: ClawException) -> JSONResponse:
    """Handle all ClawException subclasses."""
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 500001,
            "message": "服务器内部错误",
            "details": {"error": str(exc)} if logger.isEnabledFor(logging.DEBUG) else {},
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )
