"""Tests for tools layer — base, registry, catalog, policy, executor, interaction"""
import pytest

from infrastructure.tools.base import ToolSpec, Tool, ToolHandler, bind_tool
from infrastructure.tools.registry import ToolRegistry
from infrastructure.tools.catalog import ToolCatalog
from infrastructure.tools.policy import ToolPolicy, PolicyMode, PolicyDecision
from infrastructure.tools.executor import ToolExecutor
from infrastructure.tools.adapters.interaction import get_interaction_specs, get_interaction_handlers
from domain.shared.types import ToolCall


# ── base.py ──

class TestToolSpec:
    def test_construction(self):
        spec = ToolSpec(name="run_shell", description="Run a shell command", category="Shell")
        assert spec.name == "run_shell"
        assert spec.description == "Run a shell command"
        assert spec.category == "Shell"


class TestTool:
    def test_properties(self):
        async def handler(args: dict) -> dict:
            return {"content": "ok"}

        spec = ToolSpec(name="test_tool", description="A test tool", category="Test")
        tool = Tool(spec=spec, handler=handler)
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.category == "Test"


class TestBindTool:
    @pytest.mark.asyncio
    async def test_bind_and_invoke(self):
        async def handler(args: dict) -> dict:
            return {"content": f"result: {args.get('input', '')}"}

        spec = ToolSpec(name="bound_tool", description="Bound test", category="Test")
        tool = bind_tool(spec, handler)
        assert tool.name == "bound_tool"

        result = await tool.handler({"input": "hello"})
        assert result["content"] == "result: hello"


# ── registry.py ──

class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()
        async def handler(args: dict) -> dict:
            return {"content": "ok"}

        spec = ToolSpec(name="my_tool", description="desc", category="Shell")
        registry.register(bind_tool(spec, handler))

        assert registry.has("my_tool")
        assert registry.get("my_tool").name == "my_tool"

    def test_has_returns_false_for_unknown(self):
        registry = ToolRegistry()
        assert registry.has("nonexistent") is False

    def test_list_names_no_hints(self):
        registry = ToolRegistry()
        async def handler(args: dict) -> dict:
            return {"content": "ok"}

        for name, cat in [("tool_a", "Shell"), ("tool_b", "File System"), ("tool_c", "Web")]:
            registry.register(bind_tool(ToolSpec(name=name, description="", category=cat), handler))

        names = registry.list_names()
        assert names == ["tool_a", "tool_b", "tool_c"]  # sorted

    def test_list_names_with_hints(self):
        registry = ToolRegistry()
        async def handler(args: dict) -> dict:
            return {"content": "ok"}

        for name, cat in [("shell_tool", "Shell"), ("fs_tool", "File System"), ("web_tool", "Web")]:
            registry.register(bind_tool(ToolSpec(name=name, description="", category=cat), handler))

        # Hint for Shell should prioritize shell_tool
        names = registry.list_names(hints=["Shell"])
        assert "shell_tool" in names

    def test_list_names_exclude_categories(self):
        registry = ToolRegistry()
        async def handler(args: dict) -> dict:
            return {"content": "ok"}

        for name, cat in [("shell_tool", "Shell"), ("fs_tool", "File System"), ("mcp_tool", "MCP")]:
            registry.register(bind_tool(ToolSpec(name=name, description="", category=cat), handler))

        names = registry.list_names(exclude_categories=["MCP"])
        assert "mcp_tool" not in names
        assert "shell_tool" in names
        assert "fs_tool" in names


# ── catalog.py ──

class TestToolCatalog:
    def test_register_and_list(self):
        catalog = ToolCatalog()
        spec1 = ToolSpec(name="tool_a", description="desc", category="Shell")
        spec2 = ToolSpec(name="tool_b", description="desc", category="File System")
        catalog.register(spec1)
        catalog.register(spec2)

        specs = catalog.list_specs()
        assert len(specs) == 2

    def test_get(self):
        catalog = ToolCatalog()
        spec = ToolSpec(name="my_tool", description="desc", category="Shell")
        catalog.register(spec)
        assert catalog.get("my_tool").name == "my_tool"

    def test_list_specs_with_categories(self):
        catalog = ToolCatalog()
        for name, cat in [("shell1", "Shell"), ("fs1", "File System")]:
            catalog.register(ToolSpec(name=name, description="", category=cat))

        specs = catalog.list_specs(categories=["Shell"])
        assert len(specs) == 1
        assert specs[0].name == "shell1"


# ── policy.py ──

class TestToolPolicy:
    def test_allow_normal_tool(self):
        policy = ToolPolicy()
        decision = policy.check("read_file", {"path": "test.txt"})
        assert decision.decision == PolicyMode.ALLOW
        assert decision.allowed is True

    def test_deny_dangerous_shell(self):
        policy = ToolPolicy()
        for cmd in ["rm -rf /", "mkfs", "shutdown", "reboot", ":(){:|:&};:"]:
            decision = policy.check("run_shell", {"command": cmd})
            assert decision.decision == PolicyMode.DENY

    def test_confirm_risky_shell(self):
        policy = ToolPolicy()
        for cmd in ["rm test.txt", "mv old new", "chmod 755 file", "sudo apt install", "git push --force"]:
            decision = policy.check("run_shell", {"command": cmd})
            assert decision.decision == PolicyMode.CONFIRM

    def test_deny_system_file_write(self):
        policy = ToolPolicy()
        decision = policy.check("write_file", {"path": "/etc/passwd", "content": "hacked"})
        assert decision.decision == PolicyMode.DENY

    def test_allow_normal_file_write(self):
        policy = ToolPolicy()
        decision = policy.check("write_file", {"path": "notes.txt", "content": "hello"})
        assert decision.decision == PolicyMode.ALLOW

    def test_allow_ask_user(self):
        policy = ToolPolicy()
        decision = policy.check("ask_user", {"question": "name?"})
        assert decision.decision == PolicyMode.ALLOW


class TestPolicyDecision:
    def test_allowed_property(self):
        allow = PolicyDecision(PolicyMode.ALLOW, "")
        assert allow.allowed is True

        deny = PolicyDecision(PolicyMode.DENY, "dangerous")
        assert deny.allowed is False

        confirm = PolicyDecision(PolicyMode.CONFIRM, "risky")
        assert confirm.allowed is False


# ── executor.py ──

class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_execute_allowed_tool(self):
        registry = ToolRegistry()
        policy = ToolPolicy()

        async def handler(args: dict) -> dict:
            return {"content": f"read: {args.get('path', '')}"}

        registry.register(bind_tool(ToolSpec(name="read_file", description="", category="File System"), handler))

        executor = ToolExecutor(registry=registry, policy=policy)
        calls = [ToolCall(name="read_file", arguments={"path": "test.txt"}, call_id="id1")]

        results = await executor.execute(calls)
        assert len(results) == 1
        assert results[0]["status"] == "ok"
        assert "test.txt" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_execute_denied_tool(self):
        registry = ToolRegistry()
        policy = ToolPolicy()

        executor = ToolExecutor(registry=registry, policy=policy)
        calls = [ToolCall(name="run_shell", arguments={"command": "rm -rf /"}, call_id="id1")]

        results = await executor.execute(calls)
        assert len(results) == 1
        assert results[0]["status"] == "denied"
        assert results[0]["is_error"] is True

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        policy = ToolPolicy()

        executor = ToolExecutor(registry=registry, policy=policy)
        calls = [ToolCall(name="nonexistent_tool", arguments={}, call_id="id1")]

        results = await executor.execute(calls)
        assert len(results) == 1
        assert results[0]["status"] == "unknown_tool"
        assert results[0]["is_error"] is True

    @pytest.mark.asyncio
    async def test_execute_confirmation_required(self):
        registry = ToolRegistry()
        policy = ToolPolicy()

        async def handler(args: dict) -> dict:
            return {"content": "command output"}

        registry.register(bind_tool(ToolSpec(name="run_shell", description="", category="Shell"), handler))

        executor = ToolExecutor(registry=registry, policy=policy)
        calls = [ToolCall(name="run_shell", arguments={"command": "rm test.txt"}, call_id="id1")]

        results = await executor.execute(calls)
        assert len(results) == 1
        assert results[0]["status"] == "needs_confirmation"
        assert results[0]["requires_confirmation"] is True

    @pytest.mark.asyncio
    async def test_execute_tool_error(self):
        registry = ToolRegistry()
        policy = ToolPolicy()

        async def handler(args: dict) -> dict:
            return {"is_error": True, "content": "file not found"}

        registry.register(bind_tool(ToolSpec(name="read_file", description="", category="File System"), handler))

        executor = ToolExecutor(registry=registry, policy=policy)
        calls = [ToolCall(name="read_file", arguments={"path": "missing.txt"}, call_id="id1")]

        results = await executor.execute(calls)
        assert len(results) == 1
        assert results[0]["status"] == "error"
        assert results[0]["is_error"] is True

    @pytest.mark.asyncio
    async def test_execute_multiple_calls(self):
        registry = ToolRegistry()
        policy = ToolPolicy()

        async def handler_a(args: dict) -> dict:
            return {"content": "result_a"}

        async def handler_b(args: dict) -> dict:
            return {"content": "result_b"}

        registry.register(bind_tool(ToolSpec(name="tool_a", description="", category="Test"), handler_a))
        registry.register(bind_tool(ToolSpec(name="tool_b", description="", category="Test"), handler_b))

        executor = ToolExecutor(registry=registry, policy=policy)
        calls = [
            ToolCall(name="tool_a", arguments={}, call_id="id1"),
            ToolCall(name="tool_b", arguments={}, call_id="id2"),
        ]

        results = await executor.execute(calls)
        assert len(results) == 2
        assert results[0]["content"] == "result_a"
        assert results[1]["content"] == "result_b"


# ── interaction.py ──

class TestInteraction:
    def test_specs(self):
        specs = get_interaction_specs()
        assert len(specs) == 1
        assert specs[0].name == "ask_user"
        assert specs[0].category == "Ask User"

    def test_handlers(self):
        handlers = get_interaction_handlers()
        assert "ask_user" in handlers

    @pytest.mark.asyncio
    async def test_ask_user_with_question(self):
        handler = get_interaction_handlers()["ask_user"]
        result = await handler({"question": "你的名字是什么？"})
        assert result["ask_user"] is True
        assert result["question"] == "你的名字是什么？"

    @pytest.mark.asyncio
    async def test_ask_user_missing_question(self):
        handler = get_interaction_handlers()["ask_user"]
        result = await handler({})
        assert result["is_error"] is True
        assert "missing" in result["content"]