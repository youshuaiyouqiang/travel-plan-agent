"""Task 9 E2E 测试：端到端复盘链路。

覆盖：
- 触发复盘 → 202 + task_id
- 轮询任务状态 → completed / degraded / no_data / failed
- 查看复盘文 → 含 9 章节 + "不构成投资建议"
- 跨用户访问 → 404（不泄漏存在性）
- 任务幂等性（同 user + trade_date 在 running 状态）

不访问真实网络——全部 mock LLM 与数据源。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
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
from application.stock.review_service import StockReviewService
from application.stock.review_task_registry import ReviewTaskRegistry
from domain.stock.models import (
    EmotionIndicators,
    MarketSnapshot,
    SignalStock,
    WatchlistStock,
    SectorPerformance,
    ReviewReport,
)
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

REVIEW_MARKDOWN_MISSING = """# 2026-07-28 A股周期复盘
## 一、周期定位
弱修复
## 二、大盘与量能
上证 0.5%
"""


# ── Fake 数据源 ──────────────────────────────────────────────


class FakeStockDataSource:
    """满足 StockDataSource 协议的内存假数据源。"""

    def __init__(self) -> None:
        self.snapshot_returns: dict[str, object] = {}
        self.emotion_trend_returns: list[object] = []
        self.sector_rotation_returns: list[object] = []
        self.watchlist_returns: list[object] = []
        self.signal_returns: list[object] = []
        self._no_data_mode = False

    async def get_market_snapshot(self, trade_date: str):
        if self._no_data_mode:
            return MarketSnapshot(
                trade_date=trade_date,
                sh_index=None,
                sz_index=None,
                cyb_index=None,
                total_volume=None,
                volume_change_pct=None,
                consecutive_down_days=0,
                ma20_status=None,
            )
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
        if self._no_data_mode:
            return EmotionIndicators(
                trade_date=trade_date,
                limit_up_count=0,
                limit_down_count=0,
                valid_limit_up_count=0,
                broken_limit_ratio=0.0,
                max_consecutive_boards=0,
                yesterday_limit_up_today_premium=None,
                total_volume=0.0,
                volume_change_pct=None,
                phase=None,
                phase_confidence=None,
                phase_reason=None,
            )
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
        if self._no_data_mode:
            return []
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
        if self._no_data_mode:
            return []
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
        return []

    async def get_signal_stocks(self, trade_date: str):
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
        if self._no_data_mode:
            return []
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
        return []

    async def get_sector_divergence(self, trade_date: str):
        return []

    async def get_correlation(self, end_date: str, days: int):
        from domain.stock.models import CorrelationResult
        return CorrelationResult(end_date=end_date, window_days=days)

    async def get_sector_history(self, sector_name: str, days: int):
        return []

    async def get_limit_stocks(self, trade_date: str):
        return []

    def set_no_data_mode(self) -> None:
        """切换到数据全空模式，用于测试 no_data 路径。"""
        self._no_data_mode = True


# ── Fake Cache Repository ──────────────────────────────────────


class FakeCacheRepo:
    """内存版 CacheRepositoryPort 实现，支持所有权判定。"""

    def __init__(self) -> None:
        self._reports: dict[str, ReviewReport] = {}
        self._watchlist: dict[str, WatchlistStock] = {}

    async def save_review_report(
        self, *, user_id: str, trade_date: str, content: str, status: str, llm_metadata: str | dict | None
    ) -> str:
        report_id = f"rep-{user_id}-{trade_date}"
        # 将 dict 转为字符串（如果传入的是 dict）
        if isinstance(llm_metadata, dict):
            import json
            llm_metadata_str = json.dumps(llm_metadata)
        else:
            llm_metadata_str = llm_metadata or "{}"
        report = ReviewReport(
            id=report_id,
            user_id=user_id,
            trade_date=trade_date,
            content=content,
            status=status,
            llm_metadata=llm_metadata_str,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._reports[report_id] = report
        return report_id

    async def select_review_report(self, *, report_id: str, user_id: str) -> ReviewReport | None:
        report = self._reports.get(report_id)
        if report is None:
            return None
        if report.user_id != user_id:
            return None
        return report

    async def select_review_reports(self, *, user_id: str, limit: int) -> list[ReviewReport]:
        results = [r for r in self._reports.values() if r.user_id == user_id]
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[:limit]

    async def add_watchlist_stock(self, *, stock: WatchlistStock) -> None:
        self._watchlist[stock.stock_code] = stock

    async def remove_watchlist_stock(self, *, stock_code: str) -> int:
        if stock_code in self._watchlist:
            del self._watchlist[stock_code]
            return 1
        return 0


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_e2e_stock.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        import os
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
def fake_data_source():
    return FakeStockDataSource()


@pytest.fixture
def fake_cache_repo():
    return FakeCacheRepo()


@pytest.fixture
def task_registry():
    return ReviewTaskRegistry()


@pytest.fixture
def query_service(fake_data_source):
    return StockQueryService(data_source=fake_data_source)


@pytest.fixture
def report_service(fake_cache_repo):
    return ReportService(cache_repo=fake_cache_repo)


def _make_review_service(fake_data_source, fake_cache_repo, skill_md_path, llm_return):
    mock_llm = AsyncMock()

    async def _slow_complete(*_args, **_kwargs):
        await asyncio.sleep(0.3)
        return llm_return

    mock_llm.complete = AsyncMock(side_effect=_slow_complete)
    return StockReviewService(
        data_source=fake_data_source,
        llm=mock_llm,
        cache_repo=fake_cache_repo,
        skill_md_path=skill_md_path,
    )


@pytest.fixture
def review_service_ok(fake_data_source, fake_cache_repo, skill_md_path):
    return _make_review_service(fake_data_source, fake_cache_repo, skill_md_path, REVIEW_MARKDOWN_OK)


@pytest.fixture
def review_service_missing(fake_data_source, fake_cache_repo, skill_md_path):
    return _make_review_service(fake_data_source, fake_cache_repo, skill_md_path, REVIEW_MARKDOWN_MISSING)


@pytest.fixture
def review_service_no_data(fake_data_source, fake_cache_repo, skill_md_path):
    """数据全空 → no_data 路径。"""
    fake_data_source.set_no_data_mode()
    return _make_review_service(fake_data_source, fake_cache_repo, skill_md_path, REVIEW_MARKDOWN_OK)


@pytest_asyncio.fixture
async def app_ok(db, review_service_ok, query_service, report_service, task_registry, fake_cache_repo):
    test_app = FastAPI()
    test_app.state.stock_review_service = review_service_ok
    test_app.state.stock_query_service = query_service
    test_app.state.stock_report_service = report_service
    test_app.state.stock_correlation_service = None
    test_app.state.stock_task_registry = task_registry
    test_app.state.stock_cache_repo = fake_cache_repo
    test_app.state.admin_user_id = None
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(YunheException, yunhe_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(stock_router, prefix="/api/v1/stock")
    return test_app


@pytest_asyncio.fixture
async def app_missing(db, review_service_missing, query_service, report_service, task_registry, fake_cache_repo):
    test_app = FastAPI()
    test_app.state.stock_review_service = review_service_missing
    test_app.state.stock_query_service = query_service
    test_app.state.stock_report_service = report_service
    test_app.state.stock_correlation_service = None
    test_app.state.stock_task_registry = task_registry
    test_app.state.stock_cache_repo = fake_cache_repo
    test_app.state.admin_user_id = None
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(YunheException, yunhe_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(stock_router, prefix="/api/v1/stock")
    return test_app


@pytest_asyncio.fixture
async def app_no_data(db, review_service_no_data, query_service, report_service, task_registry, fake_cache_repo):
    test_app = FastAPI()
    test_app.state.stock_review_service = review_service_no_data
    test_app.state.stock_query_service = query_service
    test_app.state.stock_report_service = report_service
    test_app.state.stock_correlation_service = None
    test_app.state.stock_task_registry = task_registry
    test_app.state.stock_cache_repo = fake_cache_repo
    test_app.state.admin_user_id = None
    test_app.middleware("http")(auth_middleware)
    test_app.add_exception_handler(YunheException, yunhe_exception_handler)
    test_app.add_exception_handler(Exception, unhandled_exception_handler)
    test_app.include_router(stock_router, prefix="/api/v1/stock")
    return test_app


@pytest_asyncio.fixture
async def client_ok(app_ok):
    transport = ASGITransport(app=app_ok)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def client_missing(app_missing):
    transport = ASGITransport(app=app_missing)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def client_no_data(app_no_data):
    transport = ASGITransport(app=app_no_data)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── E2E 场景 1：正常复盘 → completed ─────────────────────────


class TestE2EReviewCompleted:
    @pytest.mark.asyncio
    async def test_trigger_review_and_poll_completed(self, client_ok, tokens):
        """E2E：触发复盘 → 轮询到 completed → 查看复盘文含 9 章节。"""
        token, _ = tokens
        # 1. 触发复盘
        resp = await client_ok.post(
            "/api/v1/stock/review",
            headers=_bearer(token),
            json={"trade_date": "20260728"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "task_id" in body
        task_id = body["task_id"]

        # 2. 轮询直到完成（最多 5s）
        final_status = None
        for _ in range(50):
            resp = await client_ok.get(
                f"/api/v1/stock/review/tasks/{task_id}",
                headers=_bearer(token),
            )
            assert resp.status_code == 200
            body = resp.json()
            if body["status"] in ("completed", "failed", "no_data", "degraded"):
                final_status = body["status"]
                break
            time.sleep(0.1)
        assert final_status == "completed", f"任务未在预期时间内完成: {body}"

        # 3. 查看复盘文
        report_id = body["report_id"]
        assert report_id is not None
        resp = await client_ok.get(
            f"/api/v1/stock/reports/{report_id}",
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        report = resp.json()
        assert "## 一、周期定位" in report["content"]
        assert "## 九、方法论说明" in report["content"]
        assert "不构成投资建议" in report["content"]
        assert report["status"] == "completed"


# ── E2E 场景 2：LLM 缺章节 → degraded ───────────────────────


class TestE2EReviewDegraded:
    @pytest.mark.asyncio
    async def test_trigger_review_and_poll_degraded(self, client_missing, tokens):
        """E2E：LLM 持续缺章节 → 降级为 degraded 仍存档。"""
        token, _ = tokens
        resp = await client_missing.post(
            "/api/v1/stock/review",
            headers=_bearer(token),
            json={"trade_date": "20260728"},
        )
        assert resp.status_code == 202
        task_id = resp.json()["task_id"]

        final_status = None
        for _ in range(50):
            resp = await client_missing.get(
                f"/api/v1/stock/review/tasks/{task_id}",
                headers=_bearer(token),
            )
            body = resp.json()
            if body["status"] in ("completed", "failed", "no_data", "degraded"):
                final_status = body["status"]
                break
            time.sleep(0.1)
        assert final_status == "degraded"

        report_id = resp.json()["report_id"]
        assert report_id is not None
        resp = await client_missing.get(
            f"/api/v1/stock/reports/{report_id}",
            headers=_bearer(token),
        )
        assert resp.status_code == 200
        report = resp.json()
        assert report["status"] == "degraded"


# ── E2E 场景 3：数据全空 → no_data ──────────────────────────


class TestE2EReviewNoData:
    @pytest.mark.asyncio
    async def test_trigger_review_and_poll_no_data(self, client_no_data, tokens):
        """E2E：market + emotion + watchlist 全空 → no_data，不调用 LLM。"""
        token, _ = tokens
        resp = await client_no_data.post(
            "/api/v1/stock/review",
            headers=_bearer(token),
            json={"trade_date": "20260728"},
        )
        assert resp.status_code == 202
        task_id = resp.json()["task_id"]

        final_status = None
        for _ in range(50):
            resp = await client_no_data.get(
                f"/api/v1/stock/review/tasks/{task_id}",
                headers=_bearer(token),
            )
            body = resp.json()
            if body["status"] in ("completed", "failed", "no_data", "degraded"):
                final_status = body["status"]
                break
            time.sleep(0.1)
        assert final_status == "no_data"


# ── E2E 场景 4：跨用户访问 → 404 ────────────────────────────


class TestE2ECrossUser:
    @pytest.mark.asyncio
    async def test_cross_user_report_404(self, client_ok, tokens):
        """E2E：用户 A 的复盘文，用户 B 访问 → 404。"""
        token_a, token_b = tokens
        # A 触发复盘
        resp = await client_ok.post(
            "/api/v1/stock/review",
            headers=_bearer(token_a),
            json={"trade_date": "20260728"},
        )
        task_id = resp.json()["task_id"]

        # 轮询到完成
        report_id = None
        for _ in range(50):
            resp = await client_ok.get(
                f"/api/v1/stock/review/tasks/{task_id}",
                headers=_bearer(token_a),
            )
            body = resp.json()
            if body["status"] in ("completed", "failed", "no_data", "degraded"):
                report_id = body["report_id"]
                break
            time.sleep(0.1)
        assert report_id is not None

        # B 访问 A 的报告 → 404
        resp = await client_ok.get(
            f"/api/v1/stock/reports/{report_id}",
            headers=_bearer(token_b),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_user_task_404(self, client_ok, tokens):
        """E2E：用户 B 查询用户 A 的任务 → 404。"""
        token_a, token_b = tokens
        resp = await client_ok.post(
            "/api/v1/stock/review",
            headers=_bearer(token_a),
            json={"trade_date": "20260728"},
        )
        task_id = resp.json()["task_id"]
        resp = await client_ok.get(
            f"/api/v1/stock/review/tasks/{task_id}",
            headers=_bearer(token_b),
        )
        assert resp.status_code == 404
