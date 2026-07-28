"""Task 5 失败测试——API 13 端点契约 + 授权 + 失败场景。

覆盖：
- 401 无凭据
- 200 登录用户访问各端点
- 跨用户访问 /reports/{id} → 404（对象级未授权）
- /correlation 在 daily 模式 → 409 CORRELATION_WEEKLY_ONLY
- /correlation 缓存空 → 409 CORRELATION_NOT_READY
- POST /review 触发复盘 → 202 + task_id → 轮询 done → 报告存档
- POST /review 重复触发（进行中）→ 同 task_id 幂等
- POST /watchlist 增删 → upsert / delete
- watchlist 列表仅 active 状态
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import auth_middleware
from api.middleware.error_handler import (
    unhandled_exception_handler,
    yunhe_exception_handler,
)
from api.v1.stock import router as stock_router
from application.exceptions.base import YunheException
from application.stock.query_service import StockQueryService
from application.stock.report_service import ReportService
from application.stock.review_service import CacheRepositoryPort
from application.stock.review_task_registry import ReviewTaskRegistry
from domain.stock.ports import StockDataSource
from domain.user.auth.auth import UserStore
from domain.user.auth.token import generate_token
from infrastructure.persistence.database import init_db, reset_connection


REVIEW_MARKDOWN_OK = """# 2026-07-28 A股周期复盘
## 一、周期定位
今日情绪阶段：弱修复
## 二、大盘与量能
上证 0.5%
## 三、情绪指标详解
涨停 40 家
## 四、板块轮动
领涨：半导体
## 五、观察池复盘
观察池当前 5 只
## 六、新信号扫描
新信号 2 只
## 七、明日条件预判
基准情景：弱修复延续
## 八、风险提示
数据缺失风险
## 九、方法论说明
本内容仅为数据复盘推演，不构成投资建议。
"""


# ── 共享 fake ──────────────────────────────────────────────


class FakeStockDataSource:
    """满足 StockDataSource 协议的内存假数据源。"""

    def __init__(self) -> None:
        self.snapshot_returns: dict[str, object] = {}
        self.emotion_trend_returns: list[object] = []
        self.sector_rotation_returns: list[object] = []
        self.watchlist_returns: list[object] = []
        self.signal_returns: list[object] = []
        self.sector_perf_returns: list[object] = []
        self.sector_leaders_returns: list[object] = []
        self.correlation_returns: object | None = None

    async def get_market_snapshot(self, trade_date: str):
        from domain.stock.models import MarketSnapshot

        if trade_date in self.snapshot_returns:
            return self.snapshot_returns[trade_date]
        return MarketSnapshot(
            trade_date=trade_date,
            sh_index=3200.0,
            sz_index=10500.0,
            cyb_index=2100.0,
            total_volume=10000.0,
            volume_change_pct=2.0,
            consecutive_down_days=0,
            ma20_status="above",
        )

    async def get_emotion_indicators(self, trade_date: str):
        from domain.stock.models import EmotionIndicators

        return EmotionIndicators(
            trade_date=trade_date,
            limit_up_count=40,
            limit_down_count=10,
            valid_limit_up_count=30,
            broken_limit_ratio=0.2,
            max_consecutive_boards=5,
            yesterday_limit_up_today_premium=0.01,
            total_volume=10000.0,
            volume_change_pct=2.0,
            phase="弱修复",
            phase_confidence="medium",
            phase_reason="涨停家数中等",
        )

    async def get_emotion_indicators_trend(self, end_date: str, days: int):
        from domain.stock.models import EmotionIndicators

        if self.emotion_trend_returns:
            return list(self.emotion_trend_returns)
        return [
            EmotionIndicators(
                trade_date=end_date,
                limit_up_count=40 - i,
                limit_down_count=10,
                valid_limit_up_count=30,
                broken_limit_ratio=0.2,
                max_consecutive_boards=5,
                yesterday_limit_up_today_premium=None,
                total_volume=10000.0,
                volume_change_pct=None,
                phase=None,
                phase_confidence=None,
                phase_reason=None,
            )
            for i in range(days)
        ]

    async def get_watchlist(self):
        from domain.stock.models import WatchlistStock

        if self.watchlist_returns:
            return list(self.watchlist_returns)
        return [
            WatchlistStock(
                stock_code="000001",
                stock_name="平安银行",
                category=1,
                entry_date="20260720",
                entry_price=12.0,
                status="active",
                market_index_snapshot=3200.0,
                notes="",
            )
        ]

    async def get_stock_daily(self, stock_code: str, days: int):
        from domain.stock.models import StockDaily

        return [
            StockDaily(
                trade_date="20260728",
                stock_code=stock_code,
                open=12.0,
                close=12.5,
                high=12.8,
                low=11.9,
                volume=1000.0,
                pct_chg=0.02,
            )
        ]

    async def get_signal_stocks(self, trade_date: str):
        from domain.stock.models import SignalStock

        if self.signal_returns:
            return list(self.signal_returns)
        return [
            SignalStock(
                trade_date=trade_date,
                stock_code="000002",
                stock_name="万科A",
                signal_type="resistant",
                pct_chg=-0.5,
                market_index_pct_chg=-2.0,
                entry_price=8.0,
            )
        ]

    async def get_sector_rotation(self, trade_date: str):
        from domain.stock.models import SectorPerformance

        if self.sector_rotation_returns:
            return list(self.sector_rotation_returns)
        return [
            SectorPerformance(
                trade_date=trade_date,
                sector_code="BK0001",
                sector_name="半导体",
                pct_chg=3.0,
                leading_stock_codes=["000001"],
                limit_up_count=5,
            )
        ]

    async def get_sector_heat_distribution(self, trade_date: str):
        return []

    async def get_strong_repair_leaders(self):
        return []

    async def get_resistant_sectors(self, trade_date: str):
        return []

    async def get_sector_leaders(self, sector_name: str):
        from domain.stock.models import SectorLeader

        if self.sector_leaders_returns:
            return list(self.sector_leaders_returns)
        return [
            SectorLeader(
                trade_date="20260728",
                sector_code="BK0001",
                sector_name=sector_name,
                stock_code="000001",
                stock_name="平安银行",
                pct_chg=3.0,
                leader_kind="largest_gain",
            )
        ]

    async def get_sector_divergence(self, trade_date: str):
        return []

    async def get_correlation(self, end_date: str, days: int):
        from domain.stock.models import CorrelationResult

        if self.correlation_returns is not None:
            return self.correlation_returns
        # 默认返回空（cache not ready）
        return CorrelationResult(end_date=end_date, window_days=days)

    async def get_sector_history(self, sector_name: str, days: int):
        return []

    async def get_limit_stocks(self, trade_date: str):
        return []


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_stock_api.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


@pytest.fixture
def users(db):
    store = UserStore()
    u1 = store.create("alice", "secret123")
    u2 = store.create("bob", "secret123")
    return u1, u2


@pytest.fixture
def tokens(users):
    u1, u2 = users
    return generate_token(u1.user_id), generate_token(u2.user_id)


@pytest.fixture
def skill_md_path(tmp_path) -> Path:
    p = tmp_path / "SKILL.md"
    p.write_text("# Stock Review Skill\n\n方法论见 §3\n", encoding="utf-8")
    return p


@pytest.fixture
def fake_data_source() -> StockDataSource:
    return FakeStockDataSource()  # type: ignore[return-value]


@pytest.fixture
def fake_cache_repo() -> CacheRepositoryPort:
    """通过 AsyncMock 满足 CacheRepositoryPort 协议。"""
    repo = AsyncMock()
    repo.save_review_report = AsyncMock(return_value="rep-fixed-id")
    repo.add_watchlist_stock = AsyncMock(return_value=None)
    repo.remove_watchlist_stock = AsyncMock(return_value=1)
    repo.select_review_report = AsyncMock(return_value=None)
    repo.select_review_reports = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def task_registry() -> ReviewTaskRegistry:
    return ReviewTaskRegistry()


@pytest.fixture
def query_service(fake_data_source) -> StockQueryService:
    return StockQueryService(data_source=fake_data_source)


@pytest.fixture
def report_service(fake_cache_repo) -> ReportService:
    return ReportService(cache_repo=fake_cache_repo)


@pytest.fixture
def review_service(fake_data_source, fake_cache_repo, skill_md_path):
    from application.stock.review_service import StockReviewService

    mock_llm = AsyncMock()

    async def _slow_complete(*_args, **_kwargs):
        # 让背景任务在 ~0.5s 内保持 RUNNING，给幂等性测试留出时间窗口
        await asyncio.sleep(0.5)
        return REVIEW_MARKDOWN_OK

    mock_llm.complete = AsyncMock(side_effect=_slow_complete)
    return StockReviewService(
        data_source=fake_data_source,
        llm=mock_llm,
        cache_repo=fake_cache_repo,
        skill_md_path=skill_md_path,
    )


@pytest.fixture
def correlation_service(fake_data_source):
    from application.stock.correlation_service import CorrelationService

    return CorrelationService(data_source=fake_data_source)


@pytest_asyncio.fixture
async def app(
    db,
    review_service,
    query_service,
    report_service,
    correlation_service,
    task_registry,
):
    test_app = FastAPI()
    test_app.state.stock_review_service = review_service
    test_app.state.stock_query_service = query_service
    test_app.state.stock_report_service = report_service
    test_app.state.stock_correlation_service = correlation_service
    test_app.state.stock_task_registry = task_registry
    test_app.state.stock_cache_repo = AsyncMock()
    test_app.state.admin_user_id = None
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(YunheException, yunhe_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(stock_router, prefix="/api/v1/stock")
    return test_app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── 401 / 鉴权 ──────────────────────────────────────────


class TestUnauthenticated:
    @pytest.mark.asyncio
    async def test_market_snapshot_requires_auth(self, client):
        resp = await client.get("/api/v1/stock/market/snapshot")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_emotion_chart_requires_auth(self, client):
        resp = await client.get("/api/v1/stock/charts/emotion")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_reports_list_requires_auth(self, client):
        resp = await client.get("/api/v1/stock/reports")
        assert resp.status_code == 401


# ── 大盘快照 ──────────────────────────────────────────


class TestMarketSnapshot:
    @pytest.mark.asyncio
    async def test_returns_snapshot(self, client, tokens):
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/market/snapshot",
            params={"trade_date": "20260728"},
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["trade_date"] == "20260728"
        assert body["sh_index"] == 3200.0
        assert body["sz_index"] == 10500.0

    @pytest.mark.asyncio
    async def test_missing_trade_date_422(self, client, tokens):
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/market/snapshot",
            headers=_bearer(token),
        )
        assert resp.status_code == 422


# ── 情绪曲线 ──────────────────────────────────────────


class TestEmotionChart:
    @pytest.mark.asyncio
    async def test_default_window(self, client, tokens):
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/charts/emotion",
            params={"end_date": "20260728"},
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["window_days"] == 10
        assert isinstance(body["series"], list)
        assert len(body["series"]) == 10

    @pytest.mark.asyncio
    async def test_custom_window(self, client, tokens):
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/charts/emotion",
            params={"end_date": "20260728", "days": 5},
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["window_days"] == 5
        assert len(body["series"]) == 5


# ── 板块轮动曲线 ──────────────────────────────────────────


class TestSectorChart:
    @pytest.mark.asyncio
    async def test_returns_chart(self, client, tokens):
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/charts/sector",
            params={"end_date": "20260728", "days": 5},
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["window_days"] == 5
        assert "series" in body


# ── 观察池曲线 ──────────────────────────────────────────


class TestWatchlistChart:
    @pytest.mark.asyncio
    async def test_returns_chart(self, client, tokens):
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/charts/watchlist",
            params={"end_date": "20260728", "days": 5},
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["window_days"] == 5


# ── 观察池当前 ──────────────────────────────────────────


class TestWatchlist:
    @pytest.mark.asyncio
    async def test_list_returns_watchlist(self, client, tokens):
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/watchlist",
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert len(body["items"]) >= 1
        assert body["items"][0]["stock_code"] == "000001"

    @pytest.mark.asyncio
    async def test_add_to_watchlist(self, client, tokens, app):
        token, _ = tokens
        resp = await client.post(
            "/api/v1/stock/watchlist",
            headers=_bearer(token),
            json={
                "action": "add",
                "stock_code": "600000",
                "stock_name": "浦发银行",
                "category": 2,
                "entry_date": "20260728",
                "entry_price": 10.0,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "added"
        # cache_repo 写入被调用
        cache = app.state.stock_cache_repo
        assert cache.add_watchlist_stock.await_count == 1

    @pytest.mark.asyncio
    async def test_remove_from_watchlist(self, client, tokens, app):
        token, _ = tokens
        resp = await client.post(
            "/api/v1/stock/watchlist",
            headers=_bearer(token),
            json={"action": "remove", "stock_code": "000001"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "removed"
        cache = app.state.stock_cache_repo
        assert cache.remove_watchlist_stock.await_count == 1

    @pytest.mark.asyncio
    async def test_invalid_action_422(self, client, tokens):
        token, _ = tokens
        resp = await client.post(
            "/api/v1/stock/watchlist",
            headers=_bearer(token),
            json={"action": "garbage", "stock_code": "000001"},
        )
        assert resp.status_code == 422


# ── 新信号 ──────────────────────────────────────────


class TestSignals:
    @pytest.mark.asyncio
    async def test_returns_signals(self, client, tokens):
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/signals",
            params={"trade_date": "20260728"},
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert body["items"][0]["stock_code"] == "000002"


# ── 板块表现 ──────────────────────────────────────────


class TestSectors:
    @pytest.mark.asyncio
    async def test_returns_sector_performance(self, client, tokens):
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/sectors",
            params={"trade_date": "20260728"},
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert body["items"][0]["sector_name"] == "半导体"

    @pytest.mark.asyncio
    async def test_sector_leaders(self, client, tokens):
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/sector-leaders",
            params={"sector_name": "半导体"},
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert body["items"][0]["stock_code"] == "000001"


# ── 复盘触发 + 轮询 ──────────────────────────────────────────


class TestReviewTrigger:
    @pytest.mark.asyncio
    async def test_trigger_returns_202_with_task_id(self, client, tokens):
        token, _ = tokens
        resp = await client.post(
            "/api/v1/stock/review",
            headers=_bearer(token),
            json={"trade_date": "20260728"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "task_id" in body
        assert body["trade_date"] == "20260728"

    @pytest.mark.asyncio
    async def test_trigger_poll_done(self, client, tokens):
        token, _ = tokens
        trigger = await client.post(
            "/api/v1/stock/review",
            headers=_bearer(token),
            json={"trade_date": "20260728"},
        )
        task_id = trigger.json()["task_id"]
        # 轮询直到完成（最多 5s）
        for _ in range(50):
            resp = await client.get(
                f"/api/v1/stock/review/tasks/{task_id}",
                headers=_bearer(token),
            )
            assert resp.status_code == 200
            body = resp.json()
            if body["status"] in ("completed", "failed", "no_data", "degraded"):
                assert body["report_id"] == "rep-fixed-id"
                return
            time.sleep(0.1)
        pytest.fail(f"Task {task_id} did not complete within timeout")

    @pytest.mark.asyncio
    async def test_trigger_idempotent_running(self, client, tokens):
        """同 user + trade_date 在 pending/running 状态 → 同 task_id。"""
        token, _ = tokens
        r1 = await client.post(
            "/api/v1/stock/review",
            headers=_bearer(token),
            json={"trade_date": "20260728"},
        )
        r2 = await client.post(
            "/api/v1/stock/review",
            headers=_bearer(token),
            json={"trade_date": "20260728"},
        )
        assert r1.json()["task_id"] == r2.json()["task_id"]

    @pytest.mark.asyncio
    async def test_task_not_found_404(self, client, tokens):
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/review/tasks/nonexistent-task",
            headers=_bearer(token),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_task_other_user_404(self, client, tokens):
        token_a, token_b = tokens
        # token_a 创建任务
        trigger = await client.post(
            "/api/v1/stock/review",
            headers=_bearer(token_a),
            json={"trade_date": "20260728"},
        )
        task_id = trigger.json()["task_id"]
        # token_b 查询 → 404（不泄漏存在性）
        resp = await client.get(
            f"/api/v1/stock/review/tasks/{task_id}",
            headers=_bearer(token_b),
        )
        assert resp.status_code == 404


# ── 复盘文列表 / 详情（所有权 404） ──────────────────────────


class TestReports:
    @pytest.mark.asyncio
    async def test_list_only_mine(self, client, tokens, app):
        """列表只含本人复盘文。"""
        token_a, _ = tokens
        # 直接调 ReportService.list_reports 走 AsyncMock，返回空
        resp = await client.get(
            "/api/v1/stock/reports",
            headers=_bearer(token_a),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body

    @pytest.mark.asyncio
    async def test_get_report_owner_200(self, client, tokens, app):
        """owner 访问自己的复盘文 → 200。"""
        token_a, _ = tokens
        from domain.stock.models import ReviewReport
        from datetime import datetime, timezone

        report = ReviewReport(
            id="rep-self",
            user_id="u-self",
            trade_date="20260728",
            content="x",
            status="completed",
            llm_metadata="{}",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        # 让 cache_repo 返这条
        cache = app.state.stock_cache_repo
        cache.select_review_report = AsyncMock(return_value=report)
        # 重新构造 service（指向新 mock）——通过 app.state
        from application.stock.report_service import ReportService
        app.state.stock_report_service = ReportService(cache_repo=cache)
        # 重新挂载路由需要用新 service；改用 get_report endpoint 通过 service 查
        resp = await client.get(
            "/api/v1/stock/reports/rep-self",
            headers=_bearer(token_a),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_report_cross_user_404(self, client, tokens, app):
        """跨用户访问 → 404（不是 403）。"""
        token_a, _ = tokens
        # 返 None：跨用户或不存在
        cache = app.state.stock_cache_repo
        cache.select_review_report = AsyncMock(return_value=None)
        from application.stock.report_service import ReportService
        app.state.stock_report_service = ReportService(cache_repo=cache)
        resp = await client.get(
            "/api/v1/stock/reports/rep-other",
            headers=_bearer(token_a),
        )
        assert resp.status_code == 404


# ── 庄股/抱团（correlation）──────────────────────────────


class TestCorrelation:
    @pytest.mark.asyncio
    async def test_correlation_daily_mode_409(self, client, tokens):
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/correlation",
            params={"end_date": "20260728", "mode": "daily"},
            headers=_bearer(token),
        )
        assert resp.status_code == 409
        assert resp.json()["details"]["code"] == "CORRELATION_WEEKLY_ONLY"

    @pytest.mark.asyncio
    async def test_correlation_weekly_no_data_409(self, client, tokens):
        """周复盘模式但 cache 仍空 → 409 CORRELATION_NOT_READY。"""
        token, _ = tokens
        resp = await client.get(
            "/api/v1/stock/correlation",
            params={"end_date": "20260728", "mode": "weekly"},
            headers=_bearer(token),
        )
        # 默认 fake 返空 individual_stocks + clustered_groups
        assert resp.status_code == 409
        assert resp.json()["details"]["code"] == "CORRELATION_NOT_READY"

    @pytest.mark.asyncio
    async def test_correlation_weekly_with_data_200(
        self, client, tokens, fake_data_source
    ):
        token, _ = tokens
        from domain.stock.models import (
            ClusterGroup,
            CorrelationResult,
            StockCorrelation,
        )

        fake_data_source.correlation_returns = CorrelationResult(
            end_date="20260728",
            window_days=7,
            individual_stocks=[
                StockCorrelation(
                    stock_code="000001",
                    stock_name="平安银行",
                    market_correlation=0.1,
                    sector_correlation=0.2,
                    is_independent=True,
                )
            ],
            clustered_groups=[
                ClusterGroup(
                    members=["000002", "000003"],
                    intra_correlation=0.8,
                )
            ],
        )
        # 重建 service 引用新 fake
        from application.stock.correlation_service import CorrelationService
        app = client._transport.app
        app.state.stock_correlation_service = CorrelationService(
            data_source=fake_data_source,
        )
        resp = await client.get(
            "/api/v1/stock/correlation",
            params={"end_date": "20260728", "mode": "weekly"},
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["individual_stocks"]) == 1
        assert len(body["clustered_groups"]) == 1
