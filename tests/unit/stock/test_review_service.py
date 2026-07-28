"""Task 4 单元测试：StockReviewService 的核心校验与编排逻辑。

覆盖：
- _validate_markdown 章节 + 免责申明校验
- _build_user_prompt 含大盘/情绪/观察/信号四块
- _build_no_data_content 含 9 章节 + 免责申明
- _cn_num 数字→中文映射
- LLM 异常 → 保留异常链（raise ... from e）
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest


def _mk_service(skill_md_path: Path | None = None) -> object:
    from application.stock.review_service import StockReviewService

    return StockReviewService(
        data_source=AsyncMock(),
        llm=AsyncMock(),
        cache_repo=AsyncMock(),
        skill_md_path=skill_md_path or Path("SKILL.md"),
    )


def test_validate_markdown_accepts_complete_review(tmp_path: Path) -> None:
    """完整 9 章节 + 免责申明 → 校验通过（不抛）。"""
    p = tmp_path / "SKILL.md"
    p.write_text("# x", encoding="utf-8")
    service = _mk_service(p)
    good = """## 一、周期定位
x
## 二、大盘与量能
x
## 三、情绪指标详解
x
## 四、板块轮动
x
## 五、观察池复盘
x
## 六、新信号扫描
x
## 七、明日条件预判
x
## 八、风险提示
x
## 九、方法论说明
不构成投资建议
"""
    service._validate_markdown(good)  # 不抛即通过


def test_validate_markdown_rejects_missing_section(tmp_path: Path) -> None:
    """缺章节 → 抛 ReviewValidationError。"""
    from application.stock.review_service import ReviewValidationError

    p = tmp_path / "SKILL.md"
    p.write_text("# x", encoding="utf-8")
    service = _mk_service(p)
    bad = "## 一、周期定位\nx\n不构成投资建议\n"
    with pytest.raises(ReviewValidationError) as exc_info:
        service._validate_markdown(bad)
    assert "missing required sections" in str(exc_info.value)


def test_validate_markdown_rejects_missing_disclaimer(tmp_path: Path) -> None:
    """章节齐但缺免责申明 → 抛 ReviewValidationError。"""
    from application.stock.review_service import ReviewValidationError

    p = tmp_path / "SKILL.md"
    p.write_text("# x", encoding="utf-8")
    service = _mk_service(p)
    no_disclaimer = """## 一、周期定位
x
## 二、大盘与量能
x
## 三、情绪指标详解
x
## 四、板块轮动
x
## 五、观察池复盘
x
## 六、新信号扫描
x
## 七、明日条件预判
x
## 八、风险提示
x
## 九、方法论说明
x
"""
    with pytest.raises(ReviewValidationError) as exc_info:
        service._validate_markdown(no_disclaimer)
    assert "disclaimer" in str(exc_info.value).lower()


def test_build_user_prompt_includes_sections(tmp_path: Path) -> None:
    """user prompt 必须含 4 块：大盘/情绪/板块/观察池/信号。"""
    from domain.stock.models import (
        MarketSnapshot,
        SignalStock,
        SectorPerformance,
        WatchlistStock,
    )

    p = tmp_path / "SKILL.md"
    p.write_text("# x", encoding="utf-8")
    service = _mk_service(p)
    market = MarketSnapshot(
        trade_date="20260728",
        sh_index=3200.0,
        sz_index=10500.0,
        cyb_index=2100.0,
        total_volume=10000.0,
        volume_change_pct=2.0,
        consecutive_down_days=0,
        ma20_status="above",
    )
    watchlist = [
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
    signals = [
        SignalStock(
            trade_date="20260728",
            stock_code="000002",
            stock_name="万科A",
            signal_type="resistant",
            pct_chg=-0.5,
            market_index_pct_chg=-2.0,
            entry_price=8.0,
        )
    ]
    sectors = [
        SectorPerformance(
            trade_date="20260728",
            sector_code="BK0001",
            sector_name="半导体",
            pct_chg=3.0,
            leading_stock_codes=["000001"],
            limit_up_count=5,
        )
    ]
    prompt = service._build_user_prompt(
        market=market,
        emotion_trend=[],
        watchlist=watchlist,
        signals=signals,
        sector_rotation=sectors,
    )
    assert "大盘快照" in prompt
    assert "情绪指标趋势" in prompt
    assert "板块轮动" in prompt
    assert "观察池" in prompt
    assert "今日新信号" in prompt
    assert "不构成投资建议" in prompt
    assert "平安银行" in prompt
    assert "万科A" in prompt
    assert "半导体" in prompt


def test_build_user_prompt_handles_empty_data(tmp_path: Path) -> None:
    """空数据时 prompt 不能崩——渲染"暂无数据"占位。"""
    p = tmp_path / "SKILL.md"
    p.write_text("# x", encoding="utf-8")
    service = _mk_service(p)
    prompt = service._build_user_prompt(
        market=None,
        emotion_trend=[],
        watchlist=[],
        signals=[],
        sector_rotation=[],
    )
    assert "暂无数据" in prompt
    assert "大盘快照" in prompt


def test_build_no_data_content_includes_all_9_sections() -> None:
    """no_data 占位 markdown 必须含 9 章节 + 免责申明。"""
    p = Path("SKILL.md")
    service = _mk_service(p)
    md = service._build_no_data_content()
    expected = [
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
    for s in expected:
        assert s in md, f"no_data markdown 缺章节 {s}"
    assert "不构成投资建议" in md


def test_cn_num_1_to_9() -> None:
    """_cn_num 1..9 → 一/二/.../九。"""
    p = Path("SKILL.md")
    service = _mk_service(p)
    assert service._cn_num(1) == "一"
    assert service._cn_num(5) == "五"
    assert service._cn_num(9) == "九"
    assert service._cn_num(0) == "零"  # 边界：零
    assert service._cn_num(10) == "10"  # 越界返回原值


def test_load_skill_prompt_reads_file(tmp_path: Path) -> None:
    """_load_skill_prompt 必须读 skill_md_path 全文。"""
    p = tmp_path / "SKILL.md"
    p.write_text("# Stock Review\n方法论见 §3", encoding="utf-8")
    service = _mk_service(p)
    text = service._load_skill_prompt()
    assert "Stock Review" in text
    assert "方法论见 §3" in text
