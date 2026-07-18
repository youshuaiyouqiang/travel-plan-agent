"""Academic Agent 工具白名单测试。

业务红线（来源：plans/2026-07-17-academic-frontend-quality.md Task 1）：
- 学术 Agent 只允许 arxiv 相关工具（search_papers / get_abstract /
  citation_graph / batch_abstracts）；
- 明确禁止 web_search / news_search 等通用网页检索工具；
- 其它 Agent（如 yunhe 主调度）默认走原有 check() 路径，不受白名单影响。
"""

from __future__ import annotations

import pytest

from infrastructure.tools.policy import ToolPolicy


@pytest.fixture
def policy() -> ToolPolicy:
    return ToolPolicy()


class TestAcademicToolPolicy:
    def test_academic_policy_rejects_web_search(self, policy: ToolPolicy) -> None:
        assert policy.is_allowed("academic", "search_papers")
        assert not policy.is_allowed("academic", "web_search")

    def test_academic_policy_allows_arxiv_tools(self, policy: ToolPolicy) -> None:
        for tool in ("search_papers", "get_abstract", "citation_graph", "batch_abstracts"):
            assert policy.is_allowed("academic", tool), f"{tool} should be allowed for academic"

    def test_news_agent_does_not_get_academic_tools(self, policy: ToolPolicy) -> None:
        # news Agent 的白名单不包含学术工具
        assert not policy.is_allowed("news", "search_papers")
        assert not policy.is_allowed("news", "citation_graph")

    def test_unknown_agent_returns_false(self, policy: ToolPolicy) -> None:
        assert policy.is_allowed("unknown_agent", "search_papers") is False
        assert policy.is_allowed("unknown_agent", "anything") is False

    def test_is_allowed_does_not_break_existing_check(self, policy: ToolPolicy) -> None:
        """新增 is_allowed 不应影响既有 check() 路径。"""
        from infrastructure.tools.policy import PolicyMode

        decision = policy.check("read_file", {"path": "test.txt"})
        assert decision.decision == PolicyMode.ALLOW

        decision = policy.check("run_shell", {"command": "rm -rf /"})
        assert decision.decision == PolicyMode.DENY
