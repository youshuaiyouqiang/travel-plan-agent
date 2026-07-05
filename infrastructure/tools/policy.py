from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PolicyMode(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    CONFIRM = "confirm"


@dataclass
class PolicyDecision:
    decision: PolicyMode
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision == PolicyMode.ALLOW


class ToolPolicy:
    """工具执行策略 — 带安全检查和频率限制。

    Phase 4 扩展：
    - 联动 ToolSpec.confirm_required（高风险工具弹确认框）
    - 简单频率限制（每分钟/每小时，不使用外部缓存）
    - 保留 run_shell / write_file 硬编码规则
    """

    def __init__(self) -> None:
        # P2-11：简单内存频率计数器（key = f"{user_id}:{tool_name}" → list[timestamp]）。
        # 限制：多进程部署时各进程独立计数，无法跨进程共享限额。
        # 如需跨进程限流，可改为 Redis（参考 P1-9 限流中间件）。
        self._call_log: dict[str, list[float]] = {}
        self._max_calls_per_minute = 30  # 每工具每分钟上限
        self._max_calls_per_hour = 200  # 每工具每小时上限
        self._tool_specs: dict[str, Any] = {}  # tool_name → ToolSpec（外部注入）

    def register_spec(self, tool_name: str, spec: Any) -> None:
        """注册工具 spec（用于 confirm_required 检查）。"""
        self._tool_specs[tool_name] = spec

    def check(
        self,
        tool_name: str,
        arguments: dict,
        user_id: str = "",
    ) -> PolicyDecision:
        """检查工具调用是否允许。

        Args:
            tool_name: 工具名
            arguments: 工具参数
            user_id: 用户 ID（用于频率限制）
        """
        # ① run_shell 硬编码规则
        if tool_name == "run_shell":
            command = str(arguments.get("command", ""))
            blocked = ["rm -rf /", "mkfs", "shutdown", "reboot", ":(){:|:&};:"]
            if any(bad in command for bad in blocked):
                return PolicyDecision(PolicyMode.DENY, "高危shell指令已被拦截")
            risky = ["rm ", "mv ", "chmod ", "chown ", "git push --force", "sudo "]
            if any(item in command for item in risky):
                return PolicyDecision(PolicyMode.CONFIRM, "高风险 shell 命令需要确认")

        # ② write_file 硬编码规则
        if tool_name == "write_file":
            path = str(arguments.get("path", ""))
            if path.startswith("/etc/"):
                return PolicyDecision(PolicyMode.DENY, "禁止写入系统文件")

        # ③ confirm_required 联动（读取 ToolSpec）
        spec = self._tool_specs.get(tool_name)
        if spec is not None and getattr(spec, "confirm_required", False):
            return PolicyDecision(
                PolicyMode.CONFIRM,
                f"工具 {tool_name} 需要用户确认",
            )

        # ④ 频率检查
        if user_id:
            rate_decision = self._check_rate(tool_name, user_id)
            if rate_decision:
                return rate_decision

        # ⑤ ask_user 始终允许
        if tool_name == "ask_user":
            return PolicyDecision(PolicyMode.ALLOW, "")

        return PolicyDecision(PolicyMode.ALLOW, "")

    def _check_rate(self, tool_name: str, user_id: str) -> PolicyDecision | None:
        """频率限制检查。"""
        key = f"{user_id}:{tool_name}"
        now = time.time()

        if key not in self._call_log:
            self._call_log[key] = []

        # 清理过期记录
        one_hour_ago = now - 3600
        self._call_log[key] = [t for t in self._call_log[key] if t > one_hour_ago]

        # 检查每分钟上限
        one_minute_ago = now - 60
        recent_minute = [t for t in self._call_log[key] if t > one_minute_ago]
        if len(recent_minute) >= self._max_calls_per_minute:
            return PolicyDecision(
                PolicyMode.DENY, f"工具 {tool_name} 调用频率超限（{self._max_calls_per_minute}次/分钟）"
            )

        # 检查每小时上限
        if len(self._call_log[key]) >= self._max_calls_per_hour:
            return PolicyDecision(
                PolicyMode.DENY, f"工具 {tool_name} 调用频率超限（{self._max_calls_per_hour}次/小时）"
            )

        # 记录本次调用
        self._call_log[key].append(now)
        return None
