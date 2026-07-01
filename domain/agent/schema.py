from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """智能体配置 — 内置和自定义智能体的统一模型。

    内置智能体从 YAML 文件加载，自定义智能体从数据库加载，
    两者都转换为 AgentConfig，上层代码无需区分来源。
    """
    id: str                           # 智能体 ID
    name: str                         # 展示名称
    description: str                  # 能力描述（供 LLM 路由用）
    icon: str = "🤖"                  # 图标 emoji
    system_prompt: str = ""           # 系统提示词
    skills: list[str] = field(default_factory=list)  # 关联 skill 名称
    welcome_message: str = ""         # 欢迎语
    temperature: float = 0.7          # LLM 温度
    source: str = "builtin"           # 来源：builtin / custom
    is_public: bool = False           # 是否公开（仅自定义）
    user_id: str | None = None        # 创建者（仅自定义）
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SkillInfo:
    """Skill 元信息（与存储无关的纯数据）。"""
    name: str                         # skill 标识，如 'amap-maps'
    display_name: str                 # 展示名称
    description: str                  # 描述
    default_prompt: str               # 默认提示词
    requires_env: list[str]           # 需要的环境变量
    env_configured: bool = False      # 环境变量是否已配置
    icon: str = "🔧"                  # 图标
