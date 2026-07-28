"""Task 4 失败测试：完整 7 步思维链跑通。

覆盖：
- 正常路径：fake data_source + mock LLM → 复盘文含 9 章节 + 不构成投资建议
- 降级路径：LLM 输出缺章节 → L2 重试 1 次 → 仍缺则降级 status="degraded"
- no_data 路径：data_source 全部返空 → status="no_data"，不调 LLM
- LLM 全部成功 → status="completed"，save_review_report 被调用

不访问真实网络——用 FakeStockDataSource 满足端口协议 + AsyncMock LLM。
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

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


REVIEW_MARKDOWN_MISSING_SECTION = """# 2026-07-28 A股周期复盘
## 一、周期定位
今日情绪阶段：弱修复
## 二、大盘与量能
上证 0.5%
"""


class FakeStockDataSource:
    """满足 StockDataSource 协议的内存假数据源。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def get_market_snapshot(self, trade_date: str):
        from domain.stock.models import MarketSnapshot

        self.calls.append(("get_market_snapshot", trade_date))
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

        self.calls.append(("get_emotion_indicators", trade_date))
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

        self.calls.append(("get_emotion_indicators_trend", end_date, days))
        return [
            EmotionIndicators(
                trade_date=end_date,
                limit_up_count=40,
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
            for _ in range(days)
        ]

    async def get_watchlist(self):
        from domain.stock.models import WatchlistStock

        self.calls.append(("get_watchlist",))
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

        self.calls.append(("get_stock_daily", stock_code, days))
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

        self.calls.append(("get_signal_stocks", trade_date))
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

        self.calls.append(("get_sector_rotation", trade_date))
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
        from domain.stock.models import SectorHeatDistribution

        self.calls.append(("get_sector_heat_distribution", trade_date))
        return [
            SectorHeatDistribution(
                trade_date=trade_date,
                sector_code="BK0001",
                sector_name="半导体",
                morning_limit_up=2,
                midday_limit_up=1,
                afternoon_limit_up=2,
            )
        ]

    async def get_strong_repair_leaders(self):
        self.calls.append(("get_strong_repair_leaders",))
        return []

    async def get_resistant_sectors(self, trade_date: str):
        self.calls.append(("get_resistant_sectors", trade_date))
        return []

    async def get_sector_leaders(self, sector_name: str):
        self.calls.append(("get_sector_leaders", sector_name))
        return []

    async def get_sector_divergence(self, trade_date: str):
        self.calls.append(("get_sector_divergence", trade_date))
        return []

    async def get_correlation(self, end_date: str, days: int):
        from domain.stock.models import CorrelationResult

        self.calls.append(("get_correlation", end_date, days))
        return CorrelationResult(end_date=end_date, window_days=days)

    async def get_sector_history(self, sector_name: str, days: int):
        self.calls.append(("get_sector_history", sector_name, days))
        return []

    async def get_limit_stocks(self, trade_date: str):
        self.calls.append(("get_limit_stocks", trade_date))
        return []


class EmptyStockDataSource(FakeStockDataSource):
    """全部返空的假数据源——用于 no_data 路径。"""

    async def get_market_snapshot(self, trade_date: str):  # type: ignore[override]
        from domain.stock.models import MarketSnapshot

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

    async def get_emotion_indicators_trend(  # type: ignore[override]
        self, end_date: str, days: int
    ):
        return []

    async def get_watchlist(self):  # type: ignore[override]
        return []

    async def get_signal_stocks(self, trade_date: str):  # type: ignore[override]
        return []

    async def get_sector_rotation(self, trade_date: str):  # type: ignore[override]
        return []


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_review_pipeline.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


@pytest.fixture
def skill_md_path(tmp_path) -> Path:
    """最小 SKILL.md 文本——服务只读全文作为 system prompt。"""
    p = tmp_path / "SKILL.md"
    p.write_text("# Stock Review Skill\n\n方法论见 §3\n", encoding="utf-8")
    return p


@pytest.mark.asyncio
async def test_review_pipeline_produces_9_sections(
    tmp_db, skill_md_path
) -> None:
    """正常路径：fake 数据 + mock LLM → 复盘文含 9 章节 + 不构成投资建议。"""
    from application.stock.review_service import StockReviewService

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=REVIEW_MARKDOWN_OK)
    data_source = FakeStockDataSource()
    cache_repo = AsyncMock()
    cache_repo.save_review_report = AsyncMock(
        return_value="report-id-1"
    )

    service = StockReviewService(
        data_source=data_source,
        llm=mock_llm,
        cache_repo=cache_repo,
        skill_md_path=skill_md_path,
    )
    report = await service.generate_review(
        user_id="user1", trade_date="20260728"
    )

    assert "## 一、周期定位" in report.content
    assert "## 九、方法论说明" in report.content
    assert "不构成投资建议" in report.content
    assert report.user_id == "user1"
    assert report.status == "completed"
    assert report.id == "report-id-1"
    # 章节必须全 9 个
    expected_sections = [
        "## 一、周期定位",
        "## 二、大盘与量能",
        "## 三、情绪指标详解",
        "## 四、板块轮动",
        "## 五、观察池复盘",
        "## 六、新信号扫描",
        "## 七、明日条件预判",
        "## 八、风险提示",
        "## 九、方法论说明",
    ]
    for section in expected_sections:
        assert section in report.content, f"缺失章节 {section}"


@pytest.mark.asyncio
async def test_review_pipeline_degraded_on_missing_sections(
    tmp_db, skill_md_path
) -> None:
    """降级路径：LLM 输出缺章节 → L2 重试 1 次 → 仍缺则 status='degraded'。"""
    from application.stock.review_service import StockReviewService

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(
        side_effect=[
            REVIEW_MARKDOWN_MISSING_SECTION,
            REVIEW_MARKDOWN_MISSING_SECTION,
        ]
    )
    data_source = FakeStockDataSource()
    cache_repo = AsyncMock()
    cache_repo.save_review_report = AsyncMock(return_value="report-id-2")

    service = StockReviewService(
        data_source=data_source,
        llm=mock_llm,
        cache_repo=cache_repo,
        skill_md_path=skill_md_path,
    )
    report = await service.generate_review(
        user_id="user1", trade_date="20260728"
    )

    assert report.status == "degraded"
    # 重试必须发生：LLM 被调 2 次
    assert mock_llm.complete.call_count == 2
    # degraded 仍尝试存档
    assert cache_repo.save_review_report.await_count >= 1


@pytest.mark.asyncio
async def test_review_pipeline_no_data_when_all_empty(
    tmp_db, skill_md_path
) -> None:
    """no_data 路径：data_source 关键数据全空 → 不调 LLM，status='no_data'。"""
    from application.stock.review_service import StockReviewService

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=REVIEW_MARKDOWN_OK)
    data_source = EmptyStockDataSource()
    cache_repo = AsyncMock()
    cache_repo.save_review_report = AsyncMock(return_value="report-id-3")

    service = StockReviewService(
        data_source=data_source,
        llm=mock_llm,
        cache_repo=cache_repo,
        skill_md_path=skill_md_path,
    )
    report = await service.generate_review(
        user_id="user1", trade_date="20260728"
    )

    assert report.status == "no_data"
    # no_data 不调 LLM（节约成本）
    assert mock_llm.complete.await_count == 0
    # no_data 仍存档（用户能查看到原因）
    assert cache_repo.save_review_report.await_count >= 1


@pytest.mark.asyncio
async def test_review_pipeline_loads_skill_md_as_system_prompt(
    tmp_db, skill_md_path
) -> None:
    """system prompt 必须从 skill_md_path 全文加载。"""
    from application.stock.review_service import StockReviewService

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=REVIEW_MARKDOWN_OK)
    data_source = FakeStockDataSource()
    cache_repo = AsyncMock()
    cache_repo.save_review_report = AsyncMock(return_value="report-id-4")

    service = StockReviewService(
        data_source=data_source,
        llm=mock_llm,
        cache_repo=cache_repo,
        skill_md_path=skill_md_path,
    )
    await service.generate_review(user_id="user1", trade_date="20260728")

    # 第一次 complete 调用的 system 参数
    call_kwargs = mock_llm.complete.call_args.kwargs
    assert "system" in call_kwargs
    assert "Stock Review Skill" in call_kwargs["system"]
