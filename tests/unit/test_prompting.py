"""Tests for domain/travel/prompting.py — PromptBuilder"""

from domain.travel.prompting import PromptBuilder
from domain.travel.prompt_context import PromptContext
from domain.travel.context_manager import PreparedContext
from domain.shared.types import IntentResult, IntentType


class TestPromptBuilder:
    @staticmethod
    def _make_context(
        intent_type=IntentType.TASK,
        goal="test goal",
        tools=None,
        memory_context="",
        mcp_context="",
        summary="",
        recent_turns=None,
        was_trimmed=False,
        tool_hints=None,
    ):
        prepared = PreparedContext(
            summary=summary,
            recent_turns=recent_turns or [],
            was_trimmed=was_trimmed,
        )
        intent = IntentResult(
            intent=intent_type,
            goal=goal,
            fast_reply=False,
            force_tool=True,
            tool_hints=tool_hints or [],
        )
        return PromptContext(
            prepared_context=prepared,
            intent=intent,
            tools=tools if tools is not None else ["run_shell"],
            memory_context=memory_context,
            mcp_context=mcp_context,
        )

    def test_build_fast_reply_chat(self):
        builder = PromptBuilder()
        intent = IntentResult(intent=IntentType.CHAT, goal="casual reply", fast_reply=True)
        result = builder.build_fast_reply_system(intent)
        assert "克劳" in result or "Claw" in result
        assert "旅行" in result or "简洁" in result

    def test_build_fast_reply_query(self):
        builder = PromptBuilder()
        intent = IntentResult(intent=IntentType.QUERY, goal="what is X", fast_reply=True)
        result = builder.build_fast_reply_system(intent)
        assert "克劳" in result or "Claw" in result

    def test_build_react_system_basic(self):
        builder = PromptBuilder()
        ctx = self._make_context(
            intent_type=IntentType.TASK,
            goal="search the web",
            tools=["web_search", "run_shell"],
        )
        result = builder.build_react_system(ctx)
        assert "## Identity" in result
        assert "## Execution Rules" in result
        assert "## Task" in result
        assert "## Tool Protocol" in result
        assert "web_search" in result
        assert "run_shell" in result

    def test_build_react_system_with_tool_hints(self):
        builder = PromptBuilder()
        ctx = self._make_context(
            intent_type=IntentType.TASK,
            goal="read a file",
            tools=["read_file"],
            tool_hints=["File System"],
        )
        result = builder.build_react_system(ctx)
        assert "首选工具组" in result
        assert "File System" in result

    def test_build_react_system_with_memory(self):
        builder = PromptBuilder()
        ctx = self._make_context(
            goal="test",
            tools=["run_shell"],
            memory_context="- 用户喜欢Python\n- 用户名字是小明",
        )
        result = builder.build_react_system(ctx)
        assert "相关记忆" in result
        assert "Python" in result

    def test_build_react_system_with_mcp(self):
        builder = PromptBuilder()
        ctx = self._make_context(
            goal="search news",
            tools=["mcp__web_search__web_search"],
            mcp_context="## Available MCP Proxy Tools\n- `mcp__web_search__web_search`",
        )
        result = builder.build_react_system(ctx)
        assert "MCP" in result

    def test_build_react_system_with_context(self):
        builder = PromptBuilder()
        ctx = self._make_context(
            goal="test",
            tools=["run_shell"],
            summary="用户之前询问了天气",
        )
        result = builder.build_react_system(ctx)
        assert "会话摘要" in result

    def test_build_react_system_trimmed_context(self):
        builder = PromptBuilder()
        ctx = self._make_context(
            goal="test",
            tools=["run_shell"],
            was_trimmed=True,
        )
        result = builder.build_react_system(ctx)
        assert "精简" in result

    def test_build_react_system_no_tools(self):
        builder = PromptBuilder()
        ctx = self._make_context(
            goal="test",
            tools=[],
        )
        result = builder.build_react_system(ctx)
        assert "## Tool Protocol" in result
        assert "Available tools: none" in result

    def test_build_react_system_with_itinerary_confirm_context(self):
        builder = PromptBuilder()
        ctx = self._make_context(
            goal="确认行程",
            tools=["generate_itinerary_overview"],
        )
        ctx.itinerary_confirm_context = (
            "用户确认满意当前行程方案。请立即调用 generate_itinerary_overview 工具，"
            "将以下行程内容作为 content 参数传入，生成行程概览卡片：\n\n"
            "第1天：初识成都\n09:00-11:00 宽窄巷子"
        )
        result = builder.build_react_system(ctx)
        assert "行程确认指令" in result
        assert "generate_itinerary_overview" in result
        assert "宽窄巷子" in result
