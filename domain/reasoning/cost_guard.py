"""成本守卫 — 在 ReAct 循环中检查 token / 工具调用预算。

社区版的核心价值：防止 API 费用失控（自用/分享都有成本）。
"""

from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CostGuard:
    """成本守卫 — 在 ReAct 循环中检查预算。

    用法：每轮迭代前调用 can_continue()，调用后 consume() 记录消耗。
    """

    token_budget: int = 50000
    tokens_used: int = 0
    tool_calls_used: int = 0
    max_tool_calls: int = 20
    max_iterations: int = 15
    iterations: int = 0

    # 预警阈值（用于前端提醒）
    warning_threshold: float = 0.8  # 80% 时预警

    def can_continue(self) -> bool:
        """检查是否可在预算内继续。"""
        if self.iterations >= self.max_iterations:
            return False
        if self.tool_calls_used >= self.max_tool_calls:
            return False
        if self.tokens_used >= self.token_budget:
            return False
        return True

    def consume(self, tokens: int = 0, tool_call: bool = False) -> None:
        """记录一次消耗。"""
        self.tokens_used += tokens
        self.iterations += 1
        if tool_call:
            self.tool_calls_used += 1

    def is_near_limit(self) -> bool:
        """是否接近预算上限（可用于缩短 LLM 回复）。"""
        token_ratio = self.tokens_used / max(self.token_budget, 1)
        tool_ratio = self.tool_calls_used / max(self.max_tool_calls, 1)
        iter_ratio = self.iterations / max(self.max_iterations, 1)
        return max(token_ratio, tool_ratio, iter_ratio) >= self.warning_threshold

    def summary(self) -> str:
        """成本摘要（供日志/调试）。"""
        return (
            f"tokens={self.tokens_used}/{self.token_budget} "
            f"tool_calls={self.tool_calls_used}/{self.max_tool_calls} "
            f"iterations={self.iterations}/{self.max_iterations}"
        )

    def exceeded_detail(self) -> str:
        """返回超出上限的详细信息。"""
        reasons = []
        if self.tokens_used >= self.token_budget:
            reasons.append("token 预算已用完")
        if self.tool_calls_used >= self.max_tool_calls:
            reasons.append("工具调用次数已达上限")
        if self.iterations >= self.max_iterations:
            reasons.append("推理迭代次数已达上限")
        return "；".join(reasons) if reasons else "正常"
