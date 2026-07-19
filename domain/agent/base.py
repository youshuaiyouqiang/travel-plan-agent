from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class BaseAgent(ABC):
    """所有智能体的统一接口。

    现有 Agent 类已具备 chat / chat_stream 方法，天然满足此接口。

    注意：agent_id 参数仅 OrchestratorAgent 使用（用于显式指定路由），
    普通智能体忽略此参数。所有子类必须接受 **kwargs 以保持 LSP 兼容。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """智能体唯一标识，如 'travel'"""

    @property
    @abstractmethod
    def description(self) -> str:
        """能力描述，供总调度做意图路由"""

    @abstractmethod
    async def chat(
        self,
        *,
        session_id: str,
        message: str,
        user_id: str | None = None,
        **kwargs,  # 接受 agent_id 等额外参数，子类按需使用
    ) -> dict:
        """同步对话。

        返回值约定：
        {
            "status": "final_answer" | "need_input" | "cannot_handle",
            "reply": "回复内容",
            "missing_info": ["field1", "field2"],  # 仅 need_input 时
            "active_agent": "agent_id",
            "agent_actions": [...],
        }

        说明：
        - "final_answer": 任务完成（默认值，向后兼容。TravelAgent 返回 "completed" 也会被云合兼容）
        - "need_input": 需要用户补充信息，云合保持委派上下文
        - "cannot_handle": 无法处理（如用户切换话题），云合释放委派并重新接手
        """

    @abstractmethod
    async def chat_stream(
        self,
        *,
        session_id: str,
        message: str,
        user_id: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """流式对话，yield {type, data, ...}"""
        # 仅为 mypy 标记：使该方法被识别为 async generator function。
        # 子类必须重写并提供实际 yield 实现；此处的 yield 永远不会执行。
        yield {}  # pragma: no cover
