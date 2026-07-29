"""Domain/agent/dynamic_agent.py 单元测试 — 日期前缀注入。

Bug 修复：用户问"点评今天的股市"时 stock agent 凭训练数据猜错日期
（trade_date=2025-04-18）。根因：DynamicAgent._build_system_prompt()
没有注入服务器当前日期。本测试覆盖：
- _current_date_prefix() 格式与 CST 时区使用
- _build_system_prompt() 顶部自动注入前缀
- 与既有 skills / MCP 段追加顺序兼容
- 空 config.system_prompt 边界
"""

from __future__ import annotations

import re
from datetime import datetime
from unittest.mock import MagicMock

from domain.agent.dynamic_agent import (
    DynamicAgent,
    _CST,
    _current_date_prefix,
)
from domain.agent.schema import AgentConfig, SkillInfo


# ── 1. _current_date_prefix 纯函数 ─────────────────────────


def test_current_date_prefix_format():
    """前缀格式：📅 今天是YYYY年M月D日，星期X。"""
    prefix = _current_date_prefix()
    pattern = r"^📅 今天是\d{4}年\d{1,2}月\d{1,2}日，星期[一二三四五六日]。$"
    assert re.match(pattern, prefix), f"格式不匹配: {prefix!r}"
    # sanity: 年份合理
    year = int(re.search(r"(\d{4})年", prefix).group(1))
    assert 2024 <= year <= 2030, f"年份越界: {year}"


def test_current_date_prefix_uses_cst_timezone(monkeypatch):
    """datetime.now 必须传 _CST，避免被宿主机时区污染。"""
    captured: dict = {}

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            captured["tz"] = tz
            return datetime(2026, 7, 29, 10, 0, 0, tzinfo=tz)

    monkeypatch.setattr("domain.agent.dynamic_agent.datetime", _FakeDatetime)
    prefix = _current_date_prefix()
    assert captured["tz"] is _CST
    assert prefix == "📅 今天是2026年7月29日，星期三。"


# ── 2. _build_system_prompt 集成 ──────────────────────────


def _make_agent(config: AgentConfig) -> DynamicAgent:
    """构造最小可用的 DynamicAgent，不依赖 DB / 真实 LLM。"""
    from domain.shared.llm.ports import LLMPort
    from domain.shared.audit.logger import AuditLogger
    from domain.shared.mcp.ports import MCPCatalogPort
    from domain.user.session.manager import SessionManager
    from infrastructure.tools.executor import ToolExecutor
    from infrastructure.tools.policy import ToolPolicy
    from infrastructure.tools.registry import ToolRegistry

    tool_executor = MagicMock(spec=ToolExecutor)
    tool_executor.policy = ToolPolicy()  # 真实 policy，filter_allowed_tools 跑得动
    return DynamicAgent(
        config=config,
        llm=MagicMock(spec=LLMPort),
        skill_provider=MagicMock(),
        tool_registry=ToolRegistry(),
        tool_executor=tool_executor,
        session_store=MagicMock(spec=SessionManager),
        mcp_catalog=MagicMock(spec=MCPCatalogPort),
        audit_logger=MagicMock(spec=AuditLogger),
    )


def test_build_system_prompt_prepends_today(monkeypatch):
    """_build_system_prompt 顶部必须有日期前缀，原 system_prompt 内容保留在后面。"""
    monkeypatch.setattr(
        "domain.agent.dynamic_agent._current_date_prefix",
        lambda: "📅 今天是2026年7月29日，星期三。",
    )
    cfg = AgentConfig(
        id="stock",
        name="股票复盘",
        description="A股复盘",
        system_prompt="你是股票复盘助手。",
    )
    agent = _make_agent(cfg)
    result = agent._build_system_prompt()
    assert result.startswith("📅 今天是2026年7月29日，星期三。\n\n")
    idx_prefix = result.index("📅 今天是2026年7月29日，星期三。")
    idx_body = result.index("你是股票复盘助手。")
    assert idx_prefix < idx_body, "前缀必须在 config.system_prompt 之前"


def test_build_system_prompt_works_with_skills_and_mcp(monkeypatch):
    """日期前缀 + skills + MCP 段顺序正确：日期 → 原 prompt → skills → MCP。"""
    monkeypatch.setattr(
        "domain.agent.dynamic_agent._current_date_prefix",
        lambda: "📅 今天是2026年7月29日，星期三。",
    )
    skill_info = SkillInfo(
        name="stock-review",
        display_name="股票复盘",
        description="d",
        default_prompt="p",
        requires_env=[],
        tools=["t1"],
    )
    cfg = AgentConfig(
        id="stock",
        name="股票复盘",
        description="A股复盘",
        system_prompt="你是股票复盘助手。",
        skills=["stock-review"],
        mcp_servers=["srv-a"],
    )
    agent = _make_agent(cfg)
    agent._skill_provider.get_skill = MagicMock(return_value=skill_info)  # type: ignore[attr-defined]

    result = agent._build_system_prompt()
    assert result.index("📅 今天是2026年7月29日，星期三。") < result.index("你是股票复盘助手。")
    assert result.index("你是股票复盘助手。") < result.index("## 可用技能")
    assert result.index("## 可用技能") < result.index("## 可用 MCP 服务")
    assert "股票复盘" in result
    assert "srv-a" in result


def test_build_system_prompt_handles_empty_config_prompt(monkeypatch):
    """空 config.system_prompt 仍能产出合法 system_prompt（仅含前缀）。"""
    monkeypatch.setattr(
        "domain.agent.dynamic_agent._current_date_prefix",
        lambda: "📅 今天是2026年7月29日，星期三。",
    )
    cfg = AgentConfig(id="x", name="x", description="x", system_prompt="")
    agent = _make_agent(cfg)
    result = agent._build_system_prompt()
    assert result == "📅 今天是2026年7月29日，星期三。\n\n"
