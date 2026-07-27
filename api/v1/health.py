from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from config import settings

router = APIRouter(tags=["health"])


@router.get("")
async def health(request: Request) -> dict:
    # P7：health checker 由组合根注入；未注入时回退到 NoOp
    checker = getattr(request.app.state, "health_checker", None)
    if checker is None:
        return {"status": "ok", "details": {"checker": "noop"}}
    try:
        status = checker.check_health()
        return {"status": status.status, "details": status.details}
    except Exception as exc:
        return {"status": "degraded", "details": {"error": str(exc)}}


@router.get("/metrics")
async def metrics():
    if settings.metrics_enabled:
        try:
            from prometheus_client import generate_latest

            return Response(content=generate_latest(), media_type="text/plain")
        except ImportError:
            return {"detail": "prometheus_client not installed"}
    return {"detail": "metrics disabled"}
