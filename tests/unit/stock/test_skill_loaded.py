"""Task 8 失败测试：skill 加载与工具边界。

覆盖范围：
- FileSkillProvider 必须加载 stock-review skill
- yaml 工具名必须与 StockDataSource 端口方法一一对应
- get_correlation 仅周复盘会话注册（装配层过滤）
"""
from __future__ import annotations

import yaml

from config import settings
from domain.stock.ports import StockDataSource
from infrastructure.skills.provider import FileSkillProvider


# ── 辅助 ──


def _yaml_tools() -> set[str]:
    """从 openai.yaml 读取 tools 列表。"""
    path = settings.skills_dir / "stock-review" / "agents" / "openai.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return set(data["interface"]["tools"])


def _port_methods() -> set[str]:
    """从 StockDataSource Protocol 读取 get_ 前缀方法名。"""
    return {
        m
        for m in dir(StockDataSource)
        if m.startswith("get_") and callable(getattr(StockDataSource, m, None))
    }


# ── 测试 ──


def test_stock_skill_loaded_by_provider():
    """FileSkillProvider 必须加载 stock-review skill。"""
    provider = FileSkillProvider(skills_dir=settings.skills_dir)
    skill = provider.get_skill("stock-review")
    assert skill is not None


def test_yaml_tools_match_port_methods():
    """yaml 工具名必须与 StockDataSource 端口方法一一对应。"""
    tools = _yaml_tools()
    methods = _port_methods()
    assert tools == methods, f"yaml 与端口不一致: yaml-only={tools - methods}, port-only={methods - tools}"
    # Task 18 之后：15 个 get_* + 1 个 get_latest_trade_date_with_data = 16
    assert len(tools) == 16, f"期望 16 个工具，实际 {len(tools)}: {tools}"


def test_daily_session_excludes_correlation_tool():
    """日复盘会话的工具清单不得包含 get_correlation；周复盘会话包含。"""
    from domain.stock.tools import build_stock_tools

    daily_tools = build_stock_tools(session_mode="daily")
    weekly_tools = build_stock_tools(session_mode="weekly")
    daily_names = set(daily_tools)
    weekly_names = set(weekly_tools)
    assert "get_correlation" not in daily_names
    assert "get_correlation" in weekly_names
    # Task 18 之后：日复盘 15 工具（含 get_latest_trade_date_with_data），
    # 周复盘 16 工具
    assert len(daily_tools) == 15, f"日复盘应 15 个工具，实际 {len(daily_tools)}: {daily_tools}"
    assert len(weekly_tools) == 16, f"周复盘应 16 个工具，实际 {len(weekly_tools)}: {weekly_tools}"
