"""股市复盘 API 路由——13 端点单文件。

端点清单（与 plan §7 Task 5 对齐）：
1.  GET  /api/v1/stock/market/snapshot       — 大盘快照
2.  GET  /api/v1/stock/charts/emotion         — 情绪多日曲线
3.  GET  /api/v1/stock/charts/sector          — 板块轮动多日曲线
4.  GET  /api/v1/stock/charts/watchlist       — 观察池多日
5.  GET  /api/v1/stock/watchlist              — 观察池当前
6.  POST /api/v1/stock/watchlist              — 入/出池
7.  GET  /api/v1/stock/signals                — 新信号
8.  GET  /api/v1/stock/sectors                — 板块表现
9.  GET  /api/v1/stock/sector-leaders         — 板块龙头
10. POST /api/v1/stock/review                 — 触发复盘（异步）
11. GET  /api/v1/stock/review/tasks/{task_id} — 复盘任务状态
12. GET  /api/v1/stock/reports                — 复盘文列表
13. GET  /api/v1/stock/reports/{report_id}    — 复盘文详情
14. GET  /api/v1/stock/correlation            — 周复盘庄股/抱团（仅周复盘模式）

业务红线（AGENTS.md §3 / §4 / §8）：
- 身份从 request.state.user_id 取得；未认证 → 401
- 跨用户访问 /reports/{id} → 404（不是 403）
- /correlation 仅 weekly 模式；日复盘调用 → 409 CORRELATION_WEEKLY_ONLY
- 缓存未就绪 → 409 CORRELATION_NOT_READY
- POST /watchlist 字段由 Pydantic DTO 校验；非法值 → 422
- 所有 DTO 使用 ConfigDict(extra="forbid")（AGENTS.md §5）
- 不写日志含 stock_code / 价格（AGENTS.md §4）
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from application.exceptions.auth import UnauthorizedException
from application.exceptions.conflict import ConflictException
from application.exceptions.not_found import NotFoundException
from application.stock.review_task_registry import (
    ReviewTaskRegistry,
    ReviewTaskStatus,
)
from domain.stock.models import (
    CorrelationResult,
    EmotionIndicators,
    LimitStock,
    MarketSnapshot,
    ReviewReport,
    SectorLeader,
    SectorPerformance,
    SignalStock,
    WatchlistStock,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stock"])


# ── 依赖取用 helper ──────────────────────────────────


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    """安全取 app.state / container 属性；未设置时返回 default。"""
    if obj is None:
        return default
    return getattr(obj, name, default)


def _require_user_id(request: Request) -> str:
    """从认证上下文取 user_id；不存在 → 401。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()
    return user_id


def _get_query_service(request: Request) -> Any:
    """从 app.state 取得 StockQueryService。"""
    return _get_attr(request.app.state, "stock_query_service")


def _get_report_service(request: Request) -> Any:
    return _get_attr(request.app.state, "stock_report_service")


def _get_review_service(request: Request) -> Any:
    return _get_attr(request.app.state, "stock_review_service")


def _get_correlation_service(request: Request) -> Any:
    return _get_attr(request.app.state, "stock_correlation_service")


def _get_task_registry(request: Request) -> ReviewTaskRegistry | None:
    return _get_attr(request.app.state, "stock_task_registry")


def _get_cache_repo(request: Request) -> Any:
    return _get_attr(request.app.state, "stock_cache_repo")


# ── DTO（Pydantic v2 + extra=forbid，AGENTS.md §5） ─────


class WatchlistActionRequest(BaseModel):
    """观察池增/删请求体。"""

    model_config = ConfigDict(extra="forbid")
    action: Literal["add", "remove"]
    stock_code: str = Field(min_length=1, max_length=16)
    stock_name: str | None = None
    category: int | None = Field(default=None, ge=1, le=5)
    entry_date: str | None = None
    entry_price: float | None = None
    notes: str = ""


class TriggerReviewRequest(BaseModel):
    """触发复盘请求体。"""

    model_config = ConfigDict(extra="forbid")
    trade_date: str = Field(min_length=8, max_length=8, pattern=r"^\d{8}$")


# ── 响应序列化辅助 ──────────────────────────────────


def _market_snapshot_dict(snapshot: MarketSnapshot) -> dict[str, Any]:
    return {
        "trade_date": snapshot.trade_date,
        "sh_index": snapshot.sh_index,
        "sz_index": snapshot.sz_index,
        "cyb_index": snapshot.cyb_index,
        "total_volume": snapshot.total_volume,
        "volume_change_pct": snapshot.volume_change_pct,
        "consecutive_down_days": snapshot.consecutive_down_days,
        "ma20_status": snapshot.ma20_status,
    }


def _emotion_dict(e: EmotionIndicators) -> dict[str, Any]:
    return {
        "trade_date": e.trade_date,
        "limit_up_count": e.limit_up_count,
        "limit_down_count": e.limit_down_count,
        "valid_limit_up_count": e.valid_limit_up_count,
        "broken_limit_ratio": e.broken_limit_ratio,
        "max_consecutive_boards": e.max_consecutive_boards,
        "yesterday_limit_up_today_premium": e.yesterday_limit_up_today_premium,
        "total_volume": e.total_volume,
        "volume_change_pct": e.volume_change_pct,
        "phase": e.phase,
        "phase_confidence": e.phase_confidence,
        "phase_reason": e.phase_reason,
    }


def _signal_dict(s: SignalStock) -> dict[str, Any]:
    return {
        "trade_date": s.trade_date,
        "stock_code": s.stock_code,
        "stock_name": s.stock_name,
        "signal_type": s.signal_type,
        "pct_chg": s.pct_chg,
        "market_index_pct_chg": s.market_index_pct_chg,
        "entry_price": s.entry_price,
    }


def _sector_dict(s: SectorPerformance) -> dict[str, Any]:
    return {
        "trade_date": s.trade_date,
        "sector_code": s.sector_code,
        "sector_name": s.sector_name,
        "pct_chg": s.pct_chg,
        "leading_stock_codes": s.leading_stock_codes,
        "limit_up_count": s.limit_up_count,
    }


def _sector_leader_dict(s: SectorLeader) -> dict[str, Any]:
    return {
        "trade_date": s.trade_date,
        "sector_code": s.sector_code,
        "sector_name": s.sector_name,
        "stock_code": s.stock_code,
        "stock_name": s.stock_name,
        "pct_chg": s.pct_chg,
        "leader_kind": s.leader_kind,
    }


def _watchlist_dict(w: WatchlistStock) -> dict[str, Any]:
    return {
        "stock_code": w.stock_code,
        "stock_name": w.stock_name,
        "category": w.category,
        "entry_date": w.entry_date,
        "entry_price": w.entry_price,
        "status": w.status,
        "market_index_snapshot": w.market_index_snapshot,
        "notes": w.notes,
    }


def _limit_stock_dict(s: LimitStock) -> dict[str, Any]:
    return {
        "trade_date": s.trade_date,
        "stock_code": s.stock_code,
        "stock_name": s.stock_name,
        "limit_type": s.limit_type,
        "consecutive_boards": s.consecutive_boards,
        "first_limit_time": s.first_limit_time,
        "last_limit_time": s.last_limit_time,
        "open_count": s.open_count,
        "is_valid_limit_up": s.is_valid_limit_up,
    }


def _report_dict(r: ReviewReport) -> dict[str, Any]:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "trade_date": r.trade_date,
        "content": r.content,
        "status": r.status,
        "llm_metadata": r.llm_metadata,
        "created_at": r.created_at,
    }


def _correlation_dict(c: CorrelationResult) -> dict[str, Any]:
    return {
        "end_date": c.end_date,
        "window_days": c.window_days,
        "individual_stocks": [
            {
                "stock_code": s.stock_code,
                "stock_name": s.stock_name,
                "market_correlation": s.market_correlation,
                "sector_correlation": s.sector_correlation,
                "is_independent": s.is_independent,
            }
            for s in c.individual_stocks
        ],
        "clustered_groups": [
            {
                "members": g.members,
                "intra_correlation": g.intra_correlation,
            }
            for g in c.clustered_groups
        ],
    }


# ── 1. GET /market/snapshot ──────────────────────────────


@router.get("/market/snapshot")
async def get_market_snapshot(
    request: Request,
    trade_date: Annotated[str, Query(pattern=r"^\d{8}$")],
) -> dict[str, Any]:
    """大盘快照——上证/深证/创业板/成交额/连续下跌天数/MA20 状态。"""
    _require_user_id(request)
    svc = _get_query_service(request)
    if svc is None:
        raise NotFoundException("stock", "query_service")
    snapshot = await svc.get_market_snapshot(trade_date)
    return _market_snapshot_dict(snapshot)


# ── 2. GET /charts/emotion ────────────────────────────────


@router.get("/charts/emotion")
async def get_emotion_chart(
    request: Request,
    end_date: Annotated[str, Query(pattern=r"^\d{8}$")],
    days: Annotated[int, Query(ge=1, le=60)] = 10,
) -> dict[str, Any]:
    """情绪多日曲线（默认 10 日）。"""
    _require_user_id(request)
    svc = _get_query_service(request)
    if svc is None:
        raise NotFoundException("stock", "query_service")
    rows = await svc.get_emotion_trend(end_date, days)
    return {
        "series": [_emotion_dict(r) for r in rows],
        "window_days": days,
        "end_date": end_date,
    }


# ── 3. GET /charts/sector ─────────────────────────────────


@router.get("/charts/sector")
async def get_sector_chart(
    request: Request,
    end_date: Annotated[str, Query(pattern=r"^\d{8}$")],
    days: Annotated[int, Query(ge=1, le=60)] = 10,
) -> dict[str, Any]:
    """板块轮动多日曲线（默认 10 日）。"""
    _require_user_id(request)
    svc = _get_query_service(request)
    if svc is None:
        raise NotFoundException("stock", "query_service")
    rows = await svc.get_sector_chart(end_date, days)
    # rows 可能是 SectorDaily 或 SectorPerformance；按字段判断
    serialized: list[dict[str, Any]] = []
    for r in rows:
        if hasattr(r, "leading_stock_codes"):
            serialized.append(_sector_dict(r))  # type: ignore[arg-type]
        else:
            serialized.append(
                {
                    "trade_date": r.trade_date,
                    "sector_code": r.sector_code,
                    "sector_name": r.sector_name,
                    "pct_chg": r.pct_chg,
                    "leading_stock_codes": [],
                    "limit_up_count": r.limit_up_count,
                }
            )
    return {
        "series": serialized,
        "window_days": days,
        "end_date": end_date,
    }


# ── 4. GET /charts/watchlist ──────────────────────────────


@router.get("/charts/watchlist")
async def get_watchlist_chart(
    request: Request,
    end_date: Annotated[str, Query(pattern=r"^\d{8}$")],
    days: Annotated[int, Query(ge=1, le=60)] = 10,
) -> dict[str, Any]:
    """观察池多日趋势。"""
    _require_user_id(request)
    svc = _get_query_service(request)
    if svc is None:
        raise NotFoundException("stock", "query_service")
    rows = await svc.get_watchlist_chart(end_date, days)
    return {
        "items": [_watchlist_dict(r) for r in rows],
        "window_days": days,
        "end_date": end_date,
    }


# ── 5. GET /watchlist ─────────────────────────────────────


@router.get("/watchlist")
async def get_watchlist(request: Request) -> dict[str, Any]:
    """观察池当前（活跃股票）。"""
    _require_user_id(request)
    svc = _get_query_service(request)
    if svc is None:
        raise NotFoundException("stock", "query_service")
    rows = await svc.get_watchlist()
    return {"items": [_watchlist_dict(r) for r in rows]}


# ── 6. POST /watchlist ────────────────────────────────────


@router.post("/watchlist")
async def post_watchlist(
    body: WatchlistActionRequest, request: Request
) -> dict[str, Any]:
    """观察池增/删。"""
    _require_user_id(request)
    cache_repo = _get_cache_repo(request)
    if cache_repo is None:
        raise NotFoundException("stock", "cache_repo")
    if body.action == "add":
        from domain.stock.models import WatchlistStock

        stock = WatchlistStock(
            stock_code=body.stock_code,
            stock_name=body.stock_name or body.stock_code,
            category=body.category or 1,
            entry_date=body.entry_date or "",
            entry_price=body.entry_price,
            status="active",
            market_index_snapshot=None,
            notes=body.notes,
        )
        await cache_repo.add_watchlist_stock(stock=stock)
        return {"status": "added", "stock_code": body.stock_code}
    # remove
    await cache_repo.remove_watchlist_stock(stock_code=body.stock_code)
    return {"status": "removed", "stock_code": body.stock_code}


# ── 7. GET /signals ───────────────────────────────────────


@router.get("/signals")
async def get_signals(
    request: Request,
    trade_date: Annotated[str, Query(pattern=r"^\d{8}$")],
) -> dict[str, Any]:
    """新信号股。"""
    _require_user_id(request)
    svc = _get_query_service(request)
    if svc is None:
        raise NotFoundException("stock", "query_service")
    rows = await svc.get_signal_stocks(trade_date)
    return {"items": [_signal_dict(r) for r in rows]}


# ── 8. GET /sectors ───────────────────────────────────────


@router.get("/sectors")
async def get_sectors(
    request: Request,
    trade_date: Annotated[str, Query(pattern=r"^\d{8}$")],
) -> dict[str, Any]:
    """板块表现。"""
    _require_user_id(request)
    svc = _get_query_service(request)
    if svc is None:
        raise NotFoundException("stock", "query_service")
    rows = await svc.get_sector_rotation(trade_date)
    return {"items": [_sector_dict(r) for r in rows]}


# ── 9. GET /sector-leaders ────────────────────────────────


@router.get("/sector-leaders")
async def get_sector_leaders(
    request: Request,
    sector_name: Annotated[str, Query(min_length=1, max_length=64)],
) -> dict[str, Any]:
    """板块龙头。"""
    _require_user_id(request)
    svc = _get_query_service(request)
    if svc is None:
        raise NotFoundException("stock", "query_service")
    rows = await svc.get_sector_leaders(sector_name)
    return {"items": [_sector_leader_dict(r) for r in rows]}


# ── 10. POST /review ──────────────────────────────────────


@router.post("/review", status_code=202)
async def trigger_review(
    body: TriggerReviewRequest, request: Request
) -> dict[str, Any]:
    """触发复盘——创建/复用 task，异步跑 7 步思维链。

    幂等：同 user + trade_date 在 pending/running 状态下返回同一 task_id。
    """
    user_id = _require_user_id(request)
    registry = _get_task_registry(request)
    review_svc = _get_review_service(request)
    if registry is None or review_svc is None:
        raise NotFoundException("stock", "registry")

    task_id = registry.create_task(
        user_id=user_id, trade_date=body.trade_date
    )
    # 立即标记 RUNNING（同步处理在背景任务跑完前用户可轮询）
    try:
        registry.update_status(task_id, ReviewTaskStatus.RUNNING)
    except KeyError:
        pass

    # 异步执行 7 步思维链
    asyncio.create_task(
        _run_review_in_background(
            registry=registry,
            review_svc=review_svc,
            user_id=user_id,
            trade_date=body.trade_date,
            task_id=task_id,
        )
    )

    return {
        "task_id": task_id,
        "trade_date": body.trade_date,
        "status": ReviewTaskStatus.RUNNING.value,
    }


async def _run_review_in_background(
    *,
    registry: ReviewTaskRegistry,
    review_svc: Any,
    user_id: str,
    trade_date: str,
    task_id: str,
) -> None:
    """后台跑 7 步思维链；完成后更新 task 状态。"""
    try:
        report = await review_svc.generate_review(
            user_id=user_id, trade_date=trade_date
        )
        # report.status 决定 task 最终状态
        status_str = getattr(report, "status", "completed")
        status_map = {
            "completed": ReviewTaskStatus.COMPLETED,
            "degraded": ReviewTaskStatus.DEGRADED,
            "no_data": ReviewTaskStatus.NO_DATA,
            "failed": ReviewTaskStatus.FAILED,
        }
        final_status = status_map.get(status_str, ReviewTaskStatus.COMPLETED)
        try:
            registry.update_status(
                task_id,
                final_status,
                report_id=getattr(report, "id", None),
            )
        except KeyError:
            logger.warning("task %s expired before completion", task_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("review background failed: %s", e)
        try:
            registry.update_status(
                task_id, ReviewTaskStatus.FAILED, error=str(e)
            )
        except KeyError:
            pass


# ── 11. GET /review/tasks/{task_id} ───────────────────────


@router.get("/review/tasks/{task_id}")
async def get_review_task_status(
    request: Request, task_id: str
) -> dict[str, Any]:
    """复盘任务状态——轮询用。跨用户访问 → 404。"""
    user_id = _require_user_id(request)
    registry = _get_task_registry(request)
    if registry is None:
        raise NotFoundException("stock", "registry")
    task = registry.get_task(task_id)
    if task is None or task.user_id != user_id:
        raise NotFoundException("review_task", task_id)
    return task.to_dict()


# ── 12. GET /reports ──────────────────────────────────────


@router.get("/reports")
async def list_reports(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """复盘文列表——仅含本人。"""
    user_id = _require_user_id(request)
    svc = _get_report_service(request)
    if svc is None:
        raise NotFoundException("stock", "report_service")
    reports = await svc.list_reports(requester_id=user_id, limit=limit)
    return {"items": [_report_dict(r) for r in reports]}


# ── 13. GET /reports/{report_id} ──────────────────────────


@router.get("/reports/{report_id}")
async def get_report(
    request: Request, report_id: str
) -> dict[str, Any]:
    """复盘文详情——跨用户访问 → 404（不暴露存在性）。"""
    user_id = _require_user_id(request)
    svc = _get_report_service(request)
    if svc is None:
        raise NotFoundException("stock", "report_service")
    report = await svc.get_report(
        report_id=report_id, requester_id=user_id
    )
    if report is None:
        raise NotFoundException("review_report", report_id)
    return _report_dict(report)


# ── 14. GET /correlation ──────────────────────────────────


@router.get("/correlation")
async def get_correlation(
    request: Request,
    end_date: Annotated[str, Query(pattern=r"^\d{8}$")],
    days: Annotated[int, Query(ge=1, le=30)] = 7,
    mode: Annotated[str, Query(pattern=r"^(daily|weekly)$")] = "weekly",
) -> dict[str, Any]:
    """庄股/抱团识别——仅周复盘模式（mode=weekly）。"""
    _require_user_id(request)
    svc = _get_correlation_service(request)
    if svc is None:
        raise NotFoundException("stock", "correlation_service")
    try:
        result = await svc.get_weekly_correlation(
            end_date=end_date, days=days, mode=mode
        )
    except ConflictException:
        raise
    return _correlation_dict(result)
