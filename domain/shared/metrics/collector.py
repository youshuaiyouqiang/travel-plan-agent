from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

_collectors: dict[str, Any] = {}


def _init_metrics():
    if not settings.metrics_enabled:
        return
    try:
        from prometheus_client import Counter, Histogram, Gauge

        _collectors["request_count"] = Counter(
            "claw_requests_total",
            "Total Claw chat requests",
            ["session_id", "intent", "status"],
        )
        _collectors["request_latency"] = Histogram(
            "claw_request_duration_seconds",
            "Request latency in seconds",
            ["intent"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
        )
        _collectors["tool_execution"] = Counter(
            "claw_tool_execution_total",
            "Total tool executions",
            ["tool_name", "status"],
        )
        # P2-4：移除 dead metric `active_sessions` Gauge（定义后从未 inc/dec）。
        _collectors["emotion_detected"] = Counter(
            "claw_emotion_detected_total",
            "Emotion detection results",
            ["emotion"],
        )
        logger.info("Prometheus metrics initialized")
    except ImportError:
        logger.warning("prometheus_client not installed, metrics disabled")


def record_request(session_id: str, intent: str, status: str) -> None:
    if "request_count" in _collectors:
        _collectors["request_count"].labels(session_id=session_id, intent=intent, status=status).inc()


def observe_latency(intent: str, duration: float) -> None:
    if "request_latency" in _collectors:
        _collectors["request_latency"].labels(intent=intent).observe(duration)


def record_tool_execution(tool_name: str, status: str) -> None:
    if "tool_execution" in _collectors:
        _collectors["tool_execution"].labels(tool_name=tool_name, status=status).inc()


def record_emotion(emotion: str) -> None:
    if "emotion_detected" in _collectors:
        _collectors["emotion_detected"].labels(emotion=emotion).inc()


@asynccontextmanager
async def track_request(session_id: str, intent: str):
    start = time.time()
    try:
        yield
        record_request(session_id, intent, "success")
    except Exception:
        record_request(session_id, intent, "error")
        raise
    finally:
        duration = time.time() - start
        observe_latency(intent, duration)


def start_metrics_server() -> None:
    if not settings.metrics_enabled:
        return
    try:
        from prometheus_client import start_http_server

        start_http_server(settings.metrics_port)
        logger.info("Metrics server started on port %s", settings.metrics_port)
    except Exception:
        logger.warning("Failed to start metrics server")


_init_metrics()
