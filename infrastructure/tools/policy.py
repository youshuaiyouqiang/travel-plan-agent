from __future__ import  annotations

from dataclasses import dataclass
from enum import Enum


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
    def check(self, tool_name: str, arguments: dict) -> PolicyDecision:
        if tool_name == "run_shell":
            command = str(arguments.get("command", ""))
            blocked = ["rm -rf /", "mkfs", "shutdown", "reboot", ":(){:|:&};:"]
            if any(bad in command for bad in blocked):
                return PolicyDecision(PolicyMode.DENY, "高危shell指令已被拦截")

            risky = ["rm ", "mv ", "chmod ", "chown ", "git push --force", "sudo "]
            if any(item in command for item in risky):
                return PolicyDecision(
                    PolicyMode.CONFIRM,
                    "risky shell command requires confirmation",
                )

        if tool_name == "write_file":
            path = str(arguments.get("path", ""))
            if path.startswith("/etc/"):
                return PolicyDecision(PolicyMode.DENY, "禁止写入系统文件")
        if tool_name == "ask_user":
            return PolicyDecision(PolicyMode.ALLOW, "")
        return PolicyDecision(PolicyMode.ALLOW, "")



