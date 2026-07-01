# Claw 多智能体架构开发文档

> **目标**：构建通用智能体框架，实现"统一对话 + 智能体激活态 + 路由守卫 + Agent 中心 + 自定义智能体"的完整产品形态。本文档是可直接落地的开发任务书。

---

## 一、现有代码盘点（不改的部分）

### 1.1 后端保留不动

| 文件 | 作用 | 状态 |
|------|------|------|
| `core/agent.py` | Agent 主循环（chat / chat_stream） | **不改** |
| `core/reasoning.py` | ReAct 推理引擎 | **不改** |
| `core/memory*.py` | 双层记忆 + 提取 + 蒸馏 | **不改** |
| `core/intent/travel_classifier.py` | 旅行意图识别 | **不改** |
| `core/emotion/detector.py` | 情感检测 | **不改** |
| `core/profile/manager.py` | 用户画像 | **不改** |
| `core/audit/logger.py` | 审计日志 | **不改** |
| `tools/*` | 旅行/高德/飞猪/MCP 工具 | **不改** |
| `core/itinerary/*` | 行程 schema/repository/parser | **不改** |
| `core/album/*` | 相册 schema/repository/service | **不改** |

### 1.2 前端保留不动

| 文件 | 作用 | 状态 |
|------|------|------|
| `components/itinerary/*` | 行程子组件（DayBlinds/ActivityDetail/ItineraryMap 等） | **不改** |
| `components/album/*` | 相册子组件（PhotoGrid/PhotoMapView 等） | **不改** |
| `pages/ItineraryOverview.tsx` | 行程详情页（打卡/花费/分享） | **改路由路径，逻辑不改** |
| `pages/MemoryPage.tsx` | 记忆页（跨智能体，不归入 travel 守卫） | **改路由路径，逻辑不改** |
| `pages/AlbumPage.tsx` | 相册页 | **改路由路径，逻辑不改** |
| `pages/ComparePage.tsx` | 对比页 | **改路由路径，逻辑不改** |
| `pages/SharedItinerary.tsx` | 分享页 | **不改**（保持独立路由） |
| `pages/Login.tsx` | 登录页 | **不改** |

### 1.3 现有交互机制（可复用）

[ChatWindow.tsx](file:///c:/Users/29105/Desktop/claw7/frontend/src/components/ChatWindow.tsx) 已有两个关键机制：

1. **行程确认按钮** — `_isItineraryConfirmPrompt()` 检测到行程内容后显示"满意，生成概览"按钮
2. **行程跳转按钮** — `_extractItineraryId()` 提取行程 ID 后显示"查看行程概览"按钮，点击跳转 `/itinerary/:id`

**本次改造的思路**：把这两个硬编码机制升级为**通用的智能体操作卡片系统**。

---

## 二、架构分层总览

```
配置层（YAML 文件，与代码分离）
├─ agents/builtin/travel.yaml      内置旅行智能体配置
├─ agents/builtin/health.yaml      未来健康智能体配置
└─ skills/                         已有，skill 定义

模型层（schema.py，纯数据定义，无依赖）
├─ AgentConfig                     智能体配置（内置+自定义统一模型）
└─ SkillInfo                       技能信息

存储层（repository.py，只做 DB CRUD）
└─ CustomAgentRepository           返回 AgentConfig，不含业务逻辑

工厂层（factory.py，解耦 Orchestrator 与具体 Agent 实现）
└─ AgentFactory                    根据 AgentConfig 创建 BaseAgent 实例

运行时层（runtime.py，通用动态智能体）
└─ DynamicAgent                    由 AgentConfig 驱动

Skill 层（provider.py，抽象接口）
├─ SkillProvider（抽象基类）
└─ FileSkillProvider（文件系统实现）

路由层（orchestrator.py，LLM 路由）
└─ OrchestratorAgent               总调度，委派给专业智能体
```

**解耦原则**：
1. **配置与代码分离** — 内置智能体用 YAML 定义，不硬编码 Python
2. **统一模型** — `AgentConfig` 同时描述内置和自定义智能体
3. **工厂模式** — `AgentFactory` 根据配置创建实例，Orchestrator 不依赖任何具体类
4. **Repository 只做存储** — 返回 `AgentConfig`，不含业务逻辑
5. **Skill 抽象接口** — 支持文件/DB/远程等多种来源

---

## 三、后端开发任务

### 阶段 1：基础框架（4 个新文件）

#### 任务 1.1：创建统一智能体接口

**新建 `core/base_agent.py`**：

```python
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
        """同步对话，返回 {reply, active_agent, agent_actions, ...}"""

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
```

#### 任务 1.2：模型层 — 统一智能体配置

**新建 `core/agents/__init__.py`**（空文件）

**新建 `core/agents/schema.py`**：

```python
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
```

**验收标准**：
- [ ] `AgentConfig` 和 `SkillInfo` 可正常实例化
- [ ] 无外部依赖（纯数据类）

#### 任务 1.3：配置层 — 内置智能体用 YAML 定义

**新建 `agents/builtin/travel.yaml`**：

```yaml
# 内置旅行规划智能体配置
# 注意：source 字段不由 YAML 定义，由 BuiltinAgentLoader 硬编码为 "builtin"，
# 因为内置智能体的来源是确定的，不需要在配置里声明。
id: travel
name: 旅行规划助手
description: >
  旅行规划助手。处理行程规划、景点推荐、机票酒店搜索、
  地图导航、花费统计、相册管理、旅行记忆等所有旅行相关需求。
icon: "✈️"
system_prompt: ""  # 旅行智能体使用内置 PromptBuilder，不走 DynamicAgent，此处留空
skills:
  - amap-maps
  - fliggy-travel
welcome_message: "你好！我是旅行规划助手，告诉我你想去哪里？"
temperature: 0.7
```

**新建 `core/agents/builtin_loader.py`**：

```python
from __future__ import annotations
import logging
from pathlib import Path
import yaml

from core.agents.schema import AgentConfig

logger = logging.getLogger(__name__)


class BuiltinAgentLoader:
    """从 YAML 文件加载内置智能体配置。
    
    新增内置智能体只需在 agents/builtin/ 下加一个 YAML 文件，
    无需改任何代码。
    """

    def __init__(self, builtin_dir: Path) -> None:
        self._dir = builtin_dir

    def load_all(self) -> list[AgentConfig]:
        """扫描目录，加载所有 .yaml 配置文件。"""
        configs = []
        if not self._dir.exists():
            logger.warning("Builtin agents dir not found: %s", self._dir)
            return configs

        for yaml_file in sorted(self._dir.glob("*.yaml")):
            try:
                config = self._load_one(yaml_file)
                if config:
                    configs.append(config)
                    logger.info("Loaded builtin agent: %s", config.id)
            except Exception as e:
                logger.error("Failed to load %s: %s", yaml_file, e)

        return configs

    def _load_one(self, yaml_file: Path) -> AgentConfig | None:
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        return AgentConfig(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            icon=data.get("icon", "🤖"),
            system_prompt=data.get("system_prompt", ""),
            skills=data.get("skills", []),
            welcome_message=data.get("welcome_message", ""),
            temperature=data.get("temperature", 0.7),
            source="builtin",
        )
```

**验收标准**：
- [ ] `BuiltinAgentLoader.load_all()` 返回旅行智能体配置
- [ ] 新增内置智能体只需加 YAML 文件（零代码改动）

#### 任务 1.4：Skill 层 — 抽象接口 + 文件实现

**新建 `core/skills/provider.py`**：

```python
from __future__ import annotations
import os
import re
import logging
from abc import ABC, abstractmethod
from pathlib import Path
import yaml

from core.agents.schema import SkillInfo

logger = logging.getLogger(__name__)


class SkillProvider(ABC):
    """Skill 提供者抽象接口。
    
    当前实现：FileSkillProvider（从文件系统读取）
    未来可实现：DBSkillProvider（从数据库读取）
                RemoteSkillProvider（从远程市场读取）
    """

    @abstractmethod
    def list_skills(self) -> list[SkillInfo]:
        """返回所有 skill。"""

    @abstractmethod
    def get_skill(self, name: str) -> SkillInfo | None:
        """按名称获取 skill。"""


class FileSkillProvider(SkillProvider):
    """从 skills/ 目录读取 skill 定义。"""

    def __init__(self, skills_dir: Path) -> None:
        self._skills_dir = skills_dir
        self._skills: dict[str, SkillInfo] = {}
        self._load()

    def _load(self) -> None:
        if not self._skills_dir.exists():
            logger.warning("Skills dir not found: %s", self._skills_dir)
            return

        for skill_dir in self._skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill = self._parse_skill(skill_dir)
            if skill:
                self._skills[skill.name] = skill

    def _parse_skill(self, skill_dir: Path) -> SkillInfo | None:
        skill_md = skill_dir / "SKILL.md"
        yaml_file = skill_dir / "agents" / "openai.yaml"

        if not skill_md.exists():
            return None

        requires_env: list[str] = []
        skill_name = skill_dir.name
        description = ""

        try:
            content = skill_md.read_text(encoding="utf-8")
            fm_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
            if fm_match:
                fm = yaml.safe_load(fm_match.group(1))
                full_name = fm.get("name", "")
                skill_name = full_name.split("@")[-1] if "@" in full_name else full_name
                description = fm.get("description", "")
                requires_env = fm.get("requires", {}).get("env", [])
        except Exception as e:
            logger.error("Failed to parse %s: %s", skill_md, e)

        display_name = skill_name
        default_prompt = ""

        if yaml_file.exists():
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                interface = data.get("interface", {})
                display_name = interface.get("display_name", skill_name)
                default_prompt = interface.get("default_prompt", "")
                i18n = data.get("i18n", {})
                zh = i18n.get("zh", {})
                if zh.get("name"):
                    display_name = zh["name"]
                if zh.get("description"):
                    description = zh["description"]
            except Exception as e:
                logger.error("Failed to parse %s: %s", yaml_file, e)

        return SkillInfo(
            name=skill_name,
            display_name=display_name,
            description=description,
            default_prompt=default_prompt,
            requires_env=requires_env,
            env_configured=all(os.getenv(env) for env in requires_env),
            icon="🔧",
        )

    def list_skills(self) -> list[SkillInfo]:
        return list(self._skills.values())

    def get_skill(self, name: str) -> SkillInfo | None:
        return self._skills.get(name)
```

**验收标准**：
- [ ] `FileSkillProvider.list_skills()` 返回 skill 列表
- [ ] 每个 skill 包含 `env_configured` 状态

---

### 阶段 2：存储与工厂（3 个新文件）

#### 任务 2.1：数据库迁移

**修改 `infra/db.py`**，在 `_run_migrations` 中新增：

```python
conn.execute("""
    CREATE TABLE IF NOT EXISTS custom_agents (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        icon TEXT DEFAULT '🤖',
        system_prompt TEXT NOT NULL,
        skills TEXT DEFAULT '[]',
        welcome_message TEXT,
        temperature REAL DEFAULT 0.7,
        is_public INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
""")
conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_agents_user ON custom_agents(user_id)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_agents_public ON custom_agents(is_public)")
```

#### 任务 2.2：存储层 — Repository 只做 CRUD

**新建 `core/agents/repository.py`**：

```python
from __future__ import annotations
import json
import time
import secrets
from typing import Optional

from infra.db import get_connection  # 注意：实际函数名是 get_connection，不是 get_conn
from core.agents.schema import AgentConfig


class CustomAgentRepository:
    """自定义智能体的数据库操作。
    
    职责单一：只负责 AgentConfig 的持久化 CRUD。
    不包含任何业务逻辑（如 Prompt 构建、LLM 调用）。
    返回值统一为 AgentConfig，与内置智能体模型一致。
    
    注意：get_connection() 返回 sqlite3.Connection，不是上下文管理器，
    需要手动 commit() 和 close()。
    """

    _ALLOWED_FIELDS = {
        "name", "description", "icon", "system_prompt", "skills",
        "welcome_message", "temperature", "is_public",
    }

    def create(self, user_id: str, **fields) -> AgentConfig:
        agent_id = secrets.token_hex(8)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")

        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO custom_agents
                   (id, user_id, name, description, icon, system_prompt, skills,
                    welcome_message, temperature, is_public, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    agent_id, user_id,
                    fields.get("name", ""),
                    fields.get("description", ""),
                    fields.get("icon", "🤖"),
                    fields.get("system_prompt", ""),
                    json.dumps(fields.get("skills", [])),
                    fields.get("welcome_message", ""),
                    fields.get("temperature", 0.7),
                    fields.get("is_public", False),
                    now, now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get(agent_id)  # type: ignore

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM custom_agents WHERE id = ?", (agent_id,)
            ).fetchone()
        finally:
            conn.close()
        return self._row_to_config(row) if row else None

    def list_by_user(self, user_id: str) -> list[AgentConfig]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM custom_agents WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_config(row) for row in rows]

    def list_public(self) -> list[AgentConfig]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM custom_agents WHERE is_public = 1 ORDER BY created_at DESC"
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_config(row) for row in rows]

    def update(self, agent_id: str, **fields) -> Optional[AgentConfig]:
        # 白名单过滤，防止 SQL 注入
        safe_fields = {k: v for k, v in fields.items() if k in self._ALLOWED_FIELDS}
        if not safe_fields:
            return self.get(agent_id)

        if "skills" in safe_fields:
            safe_fields["skills"] = json.dumps(safe_fields["skills"])
        safe_fields["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

        set_clause = ", ".join(f"{k} = ?" for k in safe_fields)
        values = list(safe_fields.values()) + [agent_id]

        conn = get_connection()
        try:
            conn.execute(
                f"UPDATE custom_agents SET {set_clause} WHERE id = ?", values
            )
            conn.commit()
        finally:
            conn.close()
        return self.get(agent_id)

    def delete(self, agent_id: str) -> bool:
        conn = get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM custom_agents WHERE id = ?", (agent_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def _row_to_config(self, row) -> AgentConfig:
        """数据库行 → AgentConfig（统一模型）。"""
        return AgentConfig(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            icon=row["icon"],
            system_prompt=row["system_prompt"],
            skills=json.loads(row["skills"]),
            welcome_message=row["welcome_message"],
            temperature=row["temperature"],
            source="custom",
            is_public=bool(row["is_public"]),
            user_id=row["user_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
```

#### 任务 2.3：运行时层 — 通用动态智能体

**新建 `core/agents/runtime.py`**：

```python
from __future__ import annotations
import logging
from collections.abc import AsyncGenerator

from core.base_agent import BaseAgent
from core.llm import OpenAILLM
from core.skills.provider import SkillProvider
from core.agents.schema import AgentConfig

logger = logging.getLogger(__name__)


class DynamicAgent(BaseAgent):
    """通用动态智能体 — 由 AgentConfig 驱动，不硬编码任何字段。
    
    用于用户自定义智能体。
    构造函数只接收 AgentConfig + 依赖（LLM、SkillProvider），
    不再接收 10 个独立字段。
    
    【商用限制 — 当前实现的不足】
    1. 无会话记忆：每次调用都是独立的 system+user，不保留对话历史。
       商用产品应注入 SessionManager，维护多轮对话上下文。
    2. 无工具执行：_build_prompt 只把 skill 描述注入 prompt，
       但不实际调用 skill 对应的工具。用户配置了 amap-maps 也无法真正查地图。
       后续应接入 ToolExecutor，根据 skills 列表加载对应工具。
    3. 无审计：不记录 LLM 调用日志。
    
    这些是 MVP 阶段的已知限制，商用前必须补齐。
    """

    def __init__(
        self,
        *,
        config: AgentConfig,
        llm: OpenAILLM,
        skill_provider: SkillProvider,
    ) -> None:
        self._config = config
        self._llm = llm
        self._skill_provider = skill_provider

    @property
    def name(self) -> str:
        return self._config.id

    @property
    def description(self) -> str:
        return self._config.description

    async def chat(self, *, session_id: str, message: str, user_id: str | None = None, **kwargs) -> dict:
        prompt = self._build_prompt()
        # 注意：OpenAILLM 的方法是 complete / stream_complete，不是 chat / chat_stream
        reply = await self._llm.complete(
            system=prompt,
            messages=[{"role": "user", "content": message}],
        )
        return {
            "status": "completed",
            "reply": reply,
            "active_agent": self._config.id,
            "agent_actions": [],
        }

    async def chat_stream(self, *, session_id: str, message: str, user_id: str | None = None, **kwargs) -> AsyncGenerator[dict, None]:
        yield {"type": "route", "data": self._config.id}
        yield {"type": "status", "data": "thinking"}

        prompt = self._build_prompt()
        async for chunk in self._llm.stream_complete(
            system=prompt,
            messages=[{"role": "user", "content": message}],
        ):
            yield {"type": "chunk", "data": chunk}

        yield {"type": "done", "data": "completed"}

    def _build_prompt(self) -> str:
        """构建 system prompt，注入 skill 说明。"""
        prompt = self._config.system_prompt

        if self._config.skills:
            prompt += "\n\n## 可用技能\n"
            for skill_name in self._config.skills:
                skill = self._skill_provider.get_skill(skill_name)
                if skill:
                    prompt += f"\n### {skill.display_name}\n"
                    prompt += f"{skill.description}\n"
                    prompt += f"提示: {skill.default_prompt}\n"

        return prompt
```

#### 任务 2.4：工厂层 — 解耦 Orchestrator 与具体实现

**新建 `core/agents/factory.py`**：

```python
from __future__ import annotations
import logging
from collections.abc import Callable

from core.base_agent import BaseAgent
from core.llm import OpenAILLM
from core.skills.provider import SkillProvider
from core.agents.schema import AgentConfig
from core.agents.runtime import DynamicAgent

logger = logging.getLogger(__name__)


class AgentFactory:
    """智能体工厂 — 根据 AgentConfig 创建 BaseAgent 实例。
    
    解耦 OrchestratorAgent 与具体 Agent 实现类。
    Orchestrator 只依赖 BaseAgent 接口 + AgentFactory，
    不 import 任何具体的 Agent 类。
    
    新增智能体类型时：
    - 如果是配置驱动的 → 零改动（DynamicAgent 自动处理）
    - 如果需要特殊逻辑 → 在工厂中加一个分支
    """

    def __init__(
        self,
        *,
        llm: OpenAILLM,
        skill_provider: SkillProvider,
        # 内置智能体的特殊构造器（如 TravelAgent 需要完整 Agent 主循环）
        builtin_builders: dict[str, Callable[[AgentConfig], BaseAgent]] | None = None,
    ) -> None:
        self._llm = llm
        self._skill_provider = skill_provider
        self._builtin_builders = builtin_builders or {}

    def create(self, config: AgentConfig) -> BaseAgent:
        """根据配置创建智能体实例。"""
        # 内置智能体可能有特殊的构造逻辑（如 TravelAgent 包装完整 Agent）
        if config.source == "builtin" and config.id in self._builtin_builders:
            builder = self._builtin_builders[config.id]
            return builder(config)

        # 默认：用 DynamicAgent（配置驱动，零代码）
        return DynamicAgent(
            config=config,
            llm=self._llm,
            skill_provider=self._skill_provider,
        )
```

**验收标准**：
- [ ] `CustomAgentRepository` CRUD 正常，返回 `AgentConfig`
- [ ] `DynamicAgent` 由 `AgentConfig` 驱动，构造函数只接收 3 个参数
- [ ] `AgentFactory.create(config)` 能根据配置创建 `DynamicAgent`

---

### 阶段 3：包装与路由（2 个新文件）

#### 任务 3.1：包装现有 Agent 为 TravelAgent

**新建 `core/agents/travel_agent.py`**：

```python
from __future__ import annotations
import logging
from collections.abc import AsyncGenerator

from core.agent import Agent
from core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class TravelAgent(BaseAgent):
    """旅行规划智能体 — 包装现有 Agent，附加操作建议。
    
    现有 Agent 的所有旅游逻辑、工具、记忆、Prompt 全部保留。
    本类只做两件事：
    1. 委托 chat/chat_stream 给现有 Agent
    2. 从回复中提取行程 ID，生成"进入行程规划"的跳转建议
    
    【商用注意】行程 ID 提取不应依赖正则匹配自由文本（脆弱、易误匹配）。
    正确做法是让底层 Agent 在生成行程后，通过结构化字段返回 itinerary_id，
    而不是从回复文本中正则提取。本类提供两种方案的过渡实现：
    - 优先读取 result 中的结构化字段（result["itinerary_id"]）
    - 兜底用正则（仅作为过渡，后续应废弃）
    """

    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    @property
    def name(self) -> str:
        return "travel"

    @property
    def description(self) -> str:
        return (
            "旅行规划助手。处理行程规划、景点推荐、机票酒店搜索、"
            "地图导航、花费统计、相册管理、旅行记忆等所有旅行相关需求。"
        )

    def _extract_actions(self, reply: str, structured_data: dict | None = None) -> list[dict]:
        """从回复中提取行程 ID，生成跳转建议。
        
        优先使用结构化数据（商用推荐），兜底用正则（过渡方案）。
        """
        actions = []
        itinerary_id = None
        
        # 方案 1（推荐）：从结构化字段获取 — 需要底层 Agent 配合
        if structured_data and structured_data.get("itinerary_id"):
            itinerary_id = structured_data["itinerary_id"]
        
        # 方案 2（过渡兜底）：从文本中正则提取 — TODO 后期废弃
        if not itinerary_id:
            import re
            # 仅在明确包含"行程概览已生成"等关键词时才提取，降低误匹配
            if '行程概览已生成' in reply or 'itinerary_id' in reply:
                match = re.search(r'([a-f0-9]{16})', reply, re.IGNORECASE)
                if match:
                    itinerary_id = match.group(1)
        
        if itinerary_id:
            actions.append({
                "type": "navigate",
                "label": "进入完整行程规划",
                "path": f"/agent/travel/itinerary/{itinerary_id}",
                "agent": "travel",
                "description": "查看地图、编辑行程、管理花费、上传相册",
            })
        
        return actions

    async def chat(self, *, session_id: str, message: str, user_id: str | None = None, **kwargs) -> dict:
        result = await self._agent.chat(session_id=session_id, message=message, user_id=user_id)
        
        # 附加激活态和操作建议
        result["active_agent"] = "travel"
        result["agent_actions"] = self._extract_actions(
            result.get("reply", ""),
            structured_data=result,  # 传入完整 result，提取结构化字段
        )
        
        return result

    async def chat_stream(self, *, session_id: str, message: str, user_id: str | None = None, **kwargs) -> AsyncGenerator[dict, None]:
        # 先发路由事件
        yield {"type": "route", "data": "travel"}
        
        # 委托流式输出
        reply_text = ""
        async for event in self._agent.chat_stream(session_id=session_id, message=message, user_id=user_id):
            yield event
            if event.get("type") == "chunk":
                reply_text += event.get("data", "")
        
        # 流结束后发操作建议
        actions = self._extract_actions(reply_text)
        if actions:
            yield {"type": "actions", "data": actions}
```

#### 任务 3.2：实现总调度智能体

**新建 `core/agents/orchestrator.py`**：

```python
from __future__ import annotations
import logging
import time
from collections.abc import AsyncGenerator, Callable

from core.base_agent import BaseAgent
from core.llm import OpenAILLM
from core.agents.schema import AgentConfig
from core.agents.factory import AgentFactory
from core.agents.repository import CustomAgentRepository

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent):
    """总调度智能体 — LLM 路由 + 工厂创建。
    
    依赖关系（全部是抽象/接口，不依赖具体类）：
    - AgentFactory：创建 Agent 实例
    - CustomAgentRepository：读取用户自定义智能体配置
    - BaseAgent：统一接口
    
    不 import DynamicAgent、TravelAgent 等具体类。
    """

    # 智能体描述缓存时间（秒），避免每次路由都查数据库
    _DESC_CACHE_TTL = 60

    def __init__(
        self,
        *,
        llm: OpenAILLM,
        factory: AgentFactory,
        builtin_configs: list[AgentConfig],
        custom_repo: CustomAgentRepository,
        default_agent: str = "travel",
    ) -> None:
        self._llm = llm
        self._factory = factory
        self._builtin_configs = {c.id: c for c in builtin_configs}
        self._custom_repo = custom_repo
        self._default = default_agent
        # 缓存已创建的 Agent 实例（内置智能体常驻，自定义按需创建）
        # 【商用注意】无界缓存会导致内存泄漏。生产环境应使用 LRU 或 TTL 淘汰策略。
        # 简单方案：限制缓存大小，超过时淘汰最久未访问的。
        self._agent_cache: dict[str, BaseAgent] = {}
        self._MAX_CACHE_SIZE = 100  # 最多缓存 100 个 Agent 实例
        # 智能体描述缓存（避免每次路由都查 DB）
        self._desc_cache: dict[str, tuple[str, float]] = {}  # user_id -> (desc, timestamp)

    @property
    def name(self) -> str:
        return "orchestrator"

    @property
    def description(self) -> str:
        return "总调度智能体，负责将用户需求路由给专业智能体。"

    def _get_all_descriptions(self, user_id: str | None) -> str:
        """获取所有可用智能体的描述（供 LLM 路由），带缓存。"""
        cache_key = user_id or "anonymous"
        now = time.time()

        # 缓存命中
        if cache_key in self._desc_cache:
            desc, ts = self._desc_cache[cache_key]
            if now - ts < self._DESC_CACHE_TTL:
                return desc

        # 重新构建
        configs = list(self._builtin_configs.values())
        if user_id:
            configs += self._custom_repo.list_by_user(user_id)
        configs += self._custom_repo.list_public()
        desc = "\n".join(f"- {c.id}: {c.description}" for c in configs)

        self._desc_cache[cache_key] = (desc, now)
        return desc

    async def _route(self, message: str, user_id: str | None) -> str:
        """LLM 路由。"""
        if len(message.strip()) < 2:
            return self._default

        agents_desc = self._get_all_descriptions(user_id)
        prompt = (
            f"你是 Claw 系统的智能路由器。判断用户消息应该交给哪个专业智能体处理。\n\n"
            f"可用智能体：\n{agents_desc}\n\n"
            f"规则：只返回智能体 ID，不要解释。无法判断返回 {self._default}。\n\n"
            f"用户消息：{message}\n\n智能体 ID："
        )

        try:
            # OpenAILLM.complete(system=, messages=) — 没有 chat() 方法
            resp = await self._llm.complete(
                system="你是 Claw 系统的智能路由器。判断用户消息应该交给哪个专业智能体处理。只返回智能体 ID，不要解释。无法判断返回默认值。",
                messages=[{"role": "user", "content": f"可用智能体：\n{agents_desc}\n\n默认：{self._default}\n\n用户消息：{message}"}],
            )
            agent_id = resp.strip().lower()
            # 验证 ID 是否存在
            if not self._agent_exists(agent_id, user_id):
                agent_id = self._default
        except Exception as e:
            logger.error("Router failed: %s", e)
            agent_id = self._default

        return agent_id

    def _agent_exists(self, agent_id: str, user_id: str | None) -> bool:
        if agent_id in self._builtin_configs:
            return True
        if user_id:
            config = self._custom_repo.get(agent_id)
            if config and (config.user_id == user_id or config.is_public):
                return True
        return False

    def _get_or_create_agent(self, agent_id: str, user_id: str | None) -> BaseAgent:
        """获取或创建 Agent 实例（通过工厂，不直接 import 具体类）。"""
        if agent_id in self._agent_cache:
            return self._agent_cache[agent_id]

        # 获取配置
        if agent_id in self._builtin_configs:
            config = self._builtin_configs[agent_id]
        else:
            config = self._custom_repo.get(agent_id)

        if not config:
            # fallback
            config = self._builtin_configs[self._default]

        # 通过工厂创建（解耦关键点）
        agent = self._factory.create(config)

        # 缓存淘汰：超过上限时清空（简单 LRU 策略）
        if len(self._agent_cache) >= self._MAX_CACHE_SIZE:
            # 保留内置智能体，淘汰自定义智能体
            self._agent_cache = {
                k: v for k, v in self._agent_cache.items()
                if k in self._builtin_configs
            }
        self._agent_cache[agent_id] = agent
        return agent

    async def chat(self, *, session_id: str, message: str,
                   user_id: str | None = None, agent_id: str | None = None) -> dict:
        # 指定 agent_id 时直接使用
        if agent_id:
            agent = self._get_or_create_agent(agent_id, user_id)
        else:
            # LLM 自动路由
            routed_id = await self._route(message, user_id)
            agent = self._get_or_create_agent(routed_id, user_id)

        return await agent.chat(session_id=session_id, message=message, user_id=user_id)

    async def chat_stream(self, *, session_id: str, message: str,
                          user_id: str | None = None, agent_id: str | None = None) -> AsyncGenerator[dict, None]:
        if agent_id:
            agent = self._get_or_create_agent(agent_id, user_id)
        else:
            routed_id = await self._route(message, user_id)
            agent = self._get_or_create_agent(routed_id, user_id)

        async for event in agent.chat_stream(session_id=session_id, message=message, user_id=user_id):
            yield event
```

**为什么用 LLM 路由而不是关键词/正则**：

| 方案 | 问题 |
|------|------|
| 关键词匹配 | 每个智能体要维护关键词列表，不可扩展；"下周去大阪"没有"旅行"关键词但明显是旅行 |
| 正则匹配 | 同上，且维护成本更高 |
| 机器学习分类器 | 需要标注数据，新智能体上线要重新训练 |
| **LLM 路由** ✅ | 零维护，理解语义，新增智能体只需注册 description |

**路由成本优化**：
- 确定性输出 — 通过 system prompt 指定"只返回智能体 ID"，结果稳定
- 智能体描述缓存（60 秒 TTL）— 避免每次路由都查 DB
- 超短消息走默认 — "嗯"、"好的"等无需 LLM 判断
- 注意：`OpenAILLM.complete()` 当前不支持 `temperature`/`max_tokens` 参数，如需控制需扩展 LLM 类

**验收标准**：
- [ ] `TravelAgent` 包装现有 Agent，返回 `active_agent: "travel"`
- [ ] `OrchestratorAgent` 不 import `DynamicAgent`、`TravelAgent` 等具体类
- [ ] LLM 路由正常（调用 `self._llm.complete(system=, messages=)`）
- [ ] 智能体描述缓存生效（60 秒 TTL）
- [ ] `agent_id` 参数指定时直接使用对应智能体
- [ ] 不传 `agent_id` 时自动路由

---

### 阶段 4：组装与 API（2 个修改）

#### 任务 4.1：修改 app.py 组装方式

**修改 `app.py`**，把 `build_agent()` 改为 `build_orchestrator()`：

```python
from pathlib import Path
from core.agents.schema import AgentConfig
from core.agents.builtin_loader import BuiltinAgentLoader
from core.agents.repository import CustomAgentRepository
from core.agents.factory import AgentFactory
from core.agents.orchestrator import OrchestratorAgent
from core.agents.travel_agent import TravelAgent
from core.skills.provider import FileSkillProvider


def build_orchestrator() -> OrchestratorAgent:
    init_from_settings()
    init_db()

    # ===== 基础依赖 =====
    audit_logger = AuditLogger()
    llm = OpenAILLM(audit_logger=audit_logger)

    # ===== Skill 提供者（抽象接口，可替换实现） =====
    skill_provider = FileSkillProvider(
        skills_dir=Path(__file__).resolve().parents[0] / "skills"
    )

    # ===== 内置智能体配置（从 YAML 加载，零硬编码） =====
    builtin_loader = BuiltinAgentLoader(
        builtin_dir=Path(__file__).resolve().parents[0] / "agents" / "builtin"
    )
    builtin_configs = builtin_loader.load_all()

    # ===== 旅行智能体的特殊构造器（需要完整 Agent 主循环） =====
    # 先构建原有旅游 Agent（代码完全保留）
    travel_agent_core = _build_travel_agent_core(llm, audit_logger)

    def travel_builder(config: AgentConfig) -> TravelAgent:
        return TravelAgent(travel_agent_core)

    # ===== 工厂 =====
    factory = AgentFactory(
        llm=llm,
        skill_provider=skill_provider,
        builtin_builders={"travel": travel_builder},
    )

    # ===== 自定义智能体 Repository =====
    custom_repo = CustomAgentRepository()

    # ===== 总调度 =====
    orchestrator = OrchestratorAgent(
        llm=llm,
        factory=factory,
        builtin_configs=builtin_configs,
        custom_repo=custom_repo,
        default_agent="travel",
    )

    # ===== 依赖注入到 app.state（供 API 路由使用） =====
    # 注意：不能在这里 `from app import app`，因为 api/server.py 已经 import app.py，
    # 会造成循环导入。正确做法：在 api/server.py 中调用 build_orchestrator() 后，
    # 直接在 server.py 里设置 app.state。
    return orchestrator


def _build_travel_agent_core(llm, audit_logger):
    """构建原有旅游 Agent（所有原代码保留，抽成函数）。
    
    注意：实际 build_agent() 中 Agent 的构造参数远不止 llm 和 audit_logger，
    还包括 prompt_builder、session_store、tool_registry、tool_executor、
    mcp_catalog、mcp_runtime、ops_classifier、emotion_detector、profile_manager。
    这里应把 app.py 中 build_agent() 的完整构造逻辑搬过来。
    """
    # ... 原 app.py 中的旅游 Agent 构建代码（完整搬过来）...
    return Agent(llm=llm, ...)
```

**`api/server.py` 中的组装调整**：

```python
# api/server.py 顶部 — 注意：现有 server.py 已有 `import json as json_mod`，
# 流式接口里用 json_mod.dumps(event)。新增代码沿用现有别名，不要混用。
from app import build_orchestrator

# 替换原来的 agent = build_agent()
container = build_orchestrator()
agent = container.orchestrator  # 保持向后兼容，现有 /api/chat 代码不用改
app.state.skill_provider = container.skill_provider
app.state.builtin_configs = container.builtin_configs
app.state.custom_repo = container.custom_repo
```

**更优方案**：让 `build_orchestrator()` 返回一个包含所有依赖的容器对象：

```python
# app.py
@dataclass
class AppContainer:
    orchestrator: OrchestratorAgent
    skill_provider: SkillProvider
    builtin_configs: list[AgentConfig]
    custom_repo: CustomAgentRepository

def build_orchestrator() -> AppContainer:
    # ... 构建逻辑 ...
    return AppContainer(
        orchestrator=orchestrator,
        skill_provider=skill_provider,
        builtin_configs=builtin_configs,
        custom_repo=custom_repo,
    )

# api/server.py
container = build_orchestrator()
agent = container.orchestrator
app.state.skill_provider = container.skill_provider
app.state.builtin_configs = container.builtin_configs
app.state.custom_repo = container.custom_repo
```

#### 任务 4.2：修改 api/server.py

**修改 `api/server.py`**：

```python
from app import build_orchestrator
from fastapi import Request, HTTPException
from dataclasses import asdict
from pydantic import BaseModel, Field, field_validator

# 改为：
agent = build_orchestrator()

# 新增请求模型（含输入校验，商用必备）
class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=8000)
    user_id: str | None = None
    agent_id: str | None = None  # 新增：指定使用哪个智能体

class CreateAgentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field("", max_length=500)
    icon: str = Field("🤖", max_length=16)
    system_prompt: str = Field(..., min_length=1, max_length=8000)
    skills: list[str] = Field(default_factory=list, max_length=20)
    welcome_message: str = Field("", max_length=500)
    temperature: float = Field(0.7, ge=0.0, le=2.0)  # 商用必须校验范围
    is_public: bool = False

class UpdateAgentRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = Field(None, max_length=500)
    icon: str | None = Field(None, max_length=16)
    system_prompt: str | None = Field(None, min_length=1, max_length=8000)
    skills: list[str] | None = Field(None, max_length=20)
    welcome_message: str | None = Field(None, max_length=500)
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    is_public: bool | None = None

# 注意：本项目认证走中间件（api/server.py 的 auth_middleware），
# 通过 request.state.user_id 获取用户 ID，不使用 Depends(get_current_user)。

# 修改 chat 接口
@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    result = await agent.chat(
        session_id=req.session_id,
        message=req.message,
        user_id=user_id,
        agent_id=req.agent_id,  # 传递给 OrchestratorAgent
    )
    return result

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    async for event in agent.chat_stream(
        session_id=req.session_id,
        message=req.message,
        user_id=user_id,
        agent_id=req.agent_id,
    ):
        yield f"data: {json_mod.dumps(event)}\n\n"  # 沿用现有 json_mod 别名

# 新增 Agent CRUD 接口
@app.get("/api/skills")
async def list_skills(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    sp = request.app.state.skill_provider
    return {"skills": [asdict(s) for s in sp.list_skills()]}

@app.get("/api/agents")
async def list_agents(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    builtin = [asdict(c) for c in request.app.state.builtin_configs]
    custom = [asdict(c) for c in request.app.state.custom_repo.list_by_user(user_id)]
    public = [asdict(c) for c in request.app.state.custom_repo.list_public()]
    return {"builtin": builtin, "custom": custom, "public": public}

@app.post("/api/agents/custom")
async def create_custom_agent(req: CreateAgentRequest, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    # TODO: 商用应加速率限制（如每用户每天最多创建 N 个）
    config = request.app.state.custom_repo.create(user_id, **req.model_dump())
    return asdict(config)

@app.get("/api/agents/custom/{agent_id}")
async def get_custom_agent(agent_id: str, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    config = request.app.state.custom_repo.get(agent_id)
    if not config or (config.user_id != user_id and not config.is_public):
        raise HTTPException(404, "智能体不存在")
    return asdict(config)

@app.put("/api/agents/custom/{agent_id}")
async def update_custom_agent(agent_id: str, req: UpdateAgentRequest, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    repo = request.app.state.custom_repo
    config = repo.get(agent_id)
    if not config or config.user_id != user_id:
        raise HTTPException(403, "无权修改")
    updated = repo.update(agent_id, **req.model_dump(exclude_unset=True))
    return asdict(updated)

@app.delete("/api/agents/custom/{agent_id}")
async def delete_custom_agent(agent_id: str, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "未登录")
    repo = request.app.state.custom_repo
    config = repo.get(agent_id)
    if not config or config.user_id != user_id:
        raise HTTPException(403, "无权删除")
    repo.delete(agent_id)
    return {"status": "deleted"}
```

**验收标准**：
- [ ] 启动后端，`/api/chat` 正常返回
- [ ] 返回值包含 `active_agent: "travel"` 字段
- [ ] 生成行程后返回值包含 `agent_actions` 数组
- [ ] `/api/chat/stream` 先发 `{"type": "route", "data": "travel"}` 事件
- [ ] `GET /api/skills` 返回 skill 列表
- [ ] `GET /api/agents` 返回 builtin + custom + public
- [ ] `POST /api/agents/custom` 创建成功
- [ ] `PUT /api/agents/custom/{id}` 更新成功（权限校验）
- [ ] `DELETE /api/agents/custom/{id}` 删除成功（权限校验）

---

## 四、前端开发任务

### 阶段 5：智能体激活态（2 个新文件 + 2 个修改）

#### 任务 5.1：创建会话激活态 Store

**新建 `frontend/src/hooks/useSessionStore.ts`**：

```typescript
import { create } from 'zustand'

interface AgentAction {
  type: 'navigate'
  label: string
  path: string
  agent: string
  description: string
}

interface SessionState {
  activeAgent: string | null       // 当前激活的智能体
  agentActions: AgentAction[]      // 当前智能体建议的操作
  setActiveAgent: (agent: string | null) => void
  setAgentActions: (actions: AgentAction[]) => void
  clearAgentActions: () => void
}

export const useSessionStore = create<SessionState>((set) => ({
  activeAgent: null,
  agentActions: [],
  setActiveAgent: (agent) => set({ activeAgent: agent }),
  setAgentActions: (actions) => set({ agentActions: actions }),
  clearAgentActions: () => set({ agentActions: [] }),
}))
```

#### 任务 5.2：创建路由守卫组件

**新建 `frontend/src/components/AgentRouteGuard.tsx`**：

```typescript
import { Navigate } from 'react-router-dom'
import { useSessionStore } from '../hooks/useSessionStore'

interface Props {
  agent: string
  children: React.ReactNode
}

/** 智能体路由守卫：只有对应智能体激活时才放行 */
export function AgentRouteGuard({ agent, children }: Props) {
  const activeAgent = useSessionStore((s) => s.activeAgent)
  
  if (activeAgent !== agent) {
    // 智能体未激活，重定向回对话页
    return <Navigate to="/" replace />
  }
  
  return <>{children}</>
}
```

#### 任务 5.3：修改路由配置

**修改 `frontend/src/App.tsx`**：

```typescript
import { AgentRouteGuard } from './components/AgentRouteGuard'

// 路由改为：
<Route path="/login" element={<LoginPage />} />
<Route path="/shared/:token" element={<SharedItinerary />} />

{/* 主对话界面 */}
<Route path="/" element={
  <PrivateRoute><Home /></PrivateRoute>
} />

{/* Agent 中心 */}
<Route path="/agents" element={
  <PrivateRoute><AgentCenter /></PrivateRoute>
} />

{/* Agent 创建/编辑 */}
<Route path="/agents/create" element={
  <PrivateRoute><AgentEditor /></PrivateRoute>
} />
<Route path="/agents/edit/:agentId" element={
  <PrivateRoute><AgentEditor /></PrivateRoute>
} />

{/* 记忆页 — 保留现有路由，不归入 travel 守卫（记忆是跨智能体的） */}
<Route path="/memories" element={
  <PrivateRoute><MemoryPage /></PrivateRoute>
} />

{/* 旅行智能体专业页面（需 travel 激活） */}
<Route path="/agent/travel/itinerary/:id" element={
  <PrivateRoute>
    <AgentRouteGuard agent="travel">
      <ItineraryOverview />
    </AgentRouteGuard>
  </PrivateRoute>
} />
<Route path="/agent/travel/album/:id" element={
  <PrivateRoute>
    <AgentRouteGuard agent="travel">
      <AlbumPage />
    </AgentRouteGuard>
  </PrivateRoute>
} />
<Route path="/agent/travel/compare" element={
  <PrivateRoute>
    <AgentRouteGuard agent="travel">
      <ComparePage />
    </AgentRouteGuard>
  </PrivateRoute>
} />
```

#### 任务 5.4：修改页面内跳转路径

需要把现有代码中跳转到 `/itinerary/:id` 的地方改为 `/agent/travel/itinerary/:id`：

**修改 `frontend/src/components/ChatWindow.tsx`** 第 66 行：
```typescript
// 原来：
const handleViewItinerary = (itineraryId: string) => {
  navigate(`/itinerary/${itineraryId}`)
}

// 改为：
const handleViewItinerary = (itineraryId: string) => {
  navigate(`/agent/travel/itinerary/${itineraryId}`)
}
```

**全局搜索 `/itinerary/` 替换为 `/agent/travel/itinerary/`**（注意排除 `/shared/:token`）

**验收标准**：
- [ ] 直接访问 `/agent/travel/itinerary/xxx` 会重定向到 `/`（未激活）
- [ ] 对话中生成行程后，点击跳转按钮可正常进入行程页
- [ ] 行程页的打卡、花费、相册、分享功能正常

---

### 阶段 6：对话中的智能体交互（3 个新组件）

#### 任务 6.1：创建智能体激活提示组件

**新建 `frontend/src/components/AgentActivationBanner.tsx`**：

```typescript
import { Plane } from 'lucide-react'

// 注意：Tailwind 不支持动态类名（如 bg-${color}-50），生产构建时会被 purge。
// 必须用静态类名映射。
const AGENT_INFO: Record<string, { icon: typeof Plane; name: string; bg: string; text: string }> = {
  travel: { icon: Plane, name: '旅行规划助手', bg: 'bg-sky-50', text: 'text-sky-600' },
  // 未来扩展：
  // health: { icon: Heart, name: '健康助手', bg: 'bg-green-50', text: 'text-green-600' },
}

export function AgentActivationBanner({ agent }: { agent: string }) {
  const info = AGENT_INFO[agent]
  if (!info) return null
  
  const Icon = info.icon
  
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-md ${info.bg} ${info.text} text-sm my-2 max-w-3xl mx-auto`}>
      <Icon size={14} />
      <span>已切换至 {info.name}</span>
    </div>
  )
}
```

#### 任务 6.2：创建智能体操作卡片组件

**新建 `frontend/src/components/AgentActionCard.tsx`**：

```typescript
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Map } from 'lucide-react'
import { useSessionStore } from '../hooks/useSessionStore'

interface AgentAction {
  type: 'navigate'
  label: string
  path: string
  agent: string
  description: string
}

export function AgentActionCard({ action }: { action: AgentAction }) {
  const navigate = useNavigate()
  const setActiveAgent = useSessionStore((s) => s.setActiveAgent)
  
  const handleClick = () => {
    // 确保智能体已激活（守卫才能放行）
    setActiveAgent(action.agent)
    navigate(action.path)
  }
  
  return (
    <button
      onClick={handleClick}
      className="mt-3 flex items-center gap-3 px-5 py-3.5 bg-gradient-to-r from-sky-500 to-blue-600 text-white rounded-2xl text-sm font-medium hover:from-sky-600 hover:to-blue-700 transition-all shadow-lg shadow-sky-200/60 active:scale-[0.97] w-fit max-w-md"
    >
      <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center flex-shrink-0">
        <Map size={20} className="text-white" />
      </div>
      <div className="text-left flex-1">
        <div className="font-semibold text-[15px]">{action.label}</div>
        <div className="text-white/70 text-xs mt-0.5">{action.description}</div>
      </div>
      <ChevronRight size={16} className="text-white/60" />
    </button>
  )
}
```

#### 任务 6.3：在 ChatWindow 中集成激活态

> **合并注意**：以下是集成要点，不是完整代码。下一个 AI 需要理解现有 ChatWindow 的结构，把激活态和操作卡片嵌入到消息渲染流程中。

**修改 `frontend/src/components/ChatWindow.tsx`**：

1. **顶部新增 import**：
```typescript
import { useSessionStore } from '../hooks/useSessionStore'
import { AgentActivationBanner } from './AgentActivationBanner'
import { AgentActionCard } from './AgentActionCard'
```

2. **组件内获取 store 状态**（在 `export function ChatWindow(...)` 内部）：
```typescript
const activeAgent = useSessionStore((s) => s.activeAgent)
const setActiveAgent = useSessionStore((s) => s.setActiveAgent)
const agentActions = useSessionStore((s) => s.agentActions)
const setAgentActions = useSessionStore((s) => s.setAgentActions)
```

3. **处理流式事件**（在 Home.tsx 的 `handleSend` 流式循环中，不是在 ChatWindow 内）：
   - `route` 事件 → `setActiveAgent(event.data)`
   - `actions` 事件 → `setAgentActions(event.data)`
   - `chunk`/`done`/`error` 事件 → 现有逻辑不变

   **注意**：流式事件处理在 `Home.tsx` 的 `for await (const event of stream)` 循环中，不在 ChatWindow 中。ChatWindow 只负责渲染。需要在 Home.tsx 的事件 switch 中新增：
   ```typescript
   case 'route':
     setActiveAgent(event.data)
     break
   case 'actions':
     setAgentActions(event.data)
     break
   ```

4. **渲染激活提示和操作卡片**（在 ChatWindow 的消息列表渲染区域，`{messages.map(...)}` 之后）：
```typescript
{/* 智能体激活提示 — 显示在消息列表顶部或底部 */}
{activeAgent && (
  <div className="flex justify-center">
    <AgentActivationBanner agent={activeAgent} />
  </div>
)}

{/* 操作卡片 — 显示在最新一条助手消息之后 */}
{agentActions.length > 0 && (
  <div className="flex justify-start">
    {agentActions.map((action, i) => (
      <AgentActionCard key={i} action={action} />
    ))}
  </div>
)}
```

5. **保留现有行程跳转逻辑**：现有的 `_extractItineraryId` 和 `handleViewItinerary` 逻辑可以保留作为兜底，或逐步迁移到 `agent_actions` 机制。过渡期两者共存。

**验收标准**：
- [ ] 对话时显示"已切换至 旅行规划助手"提示
- [ ] 生成行程后显示"进入完整行程规划"卡片
- [ ] 点击卡片可跳转到行程页
- [ ] 现有的"满意，生成概览"按钮不被破坏

---

### 阶段 7：Agent 中心页面（2 个新页面 + 2 个 API 封装）

#### 任务 7.1：API 封装

> **合并注意**：以下代码追加到 `frontend/src/utils/api.ts` 末尾。`authHeaders()` 函数已存在于该文件（第 34 行），返回带 token 的 headers，直接复用即可。

**修改 `frontend/src/utils/api.ts`**：

```typescript
// 类型定义（字段与后端 AgentConfig 完全对齐）
export interface SkillInfo {
  name: string
  display_name: string
  description: string
  default_prompt: string
  requires_env: string[]
  env_configured: boolean
  icon: string
}

export interface AgentInfo {
  id: string
  name: string
  description: string
  icon: string
  source: 'builtin' | 'custom'    // 与后端 AgentConfig.source 对齐
  skills?: string[]
  is_public?: boolean
  created_at?: string
  system_prompt?: string
  welcome_message?: string
  temperature?: number
}

// 获取 skill 列表
export async function fetchSkills(): Promise<SkillInfo[]> {
  const res = await fetch('/api/skills', { headers: authHeaders() })
  const data = await res.json()
  return data.skills
}

// 获取智能体列表
export async function fetchAgents(): Promise<{
  builtin: AgentInfo[]
  custom: AgentInfo[]
  public: AgentInfo[]
}> {
  const res = await fetch('/api/agents', { headers: authHeaders() })
  return res.json()
}

// 创建自定义智能体
export async function createCustomAgent(data: Partial<AgentInfo>): Promise<AgentInfo> {
  const res = await fetch('/api/agents/custom', {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return res.json()
}

// 更新自定义智能体
export async function updateCustomAgent(agentId: string, data: Partial<AgentInfo>): Promise<AgentInfo> {
  const res = await fetch(`/api/agents/custom/${agentId}`, {
    method: 'PUT',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return res.json()
}

// 删除自定义智能体
export async function deleteCustomAgent(agentId: string): Promise<void> {
  await fetch(`/api/agents/custom/${agentId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
}
```

#### 任务 7.2：Agent 中心页面

**新建 `frontend/src/pages/AgentCenter.tsx`**：

```typescript
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Edit2, Trash2 } from 'lucide-react'
import { fetchAgents, deleteCustomAgent, AgentInfo } from '../utils/api'

export function AgentCenter() {
  const navigate = useNavigate()
  const [agents, setAgents] = useState<{
    builtin: AgentInfo[]
    custom: AgentInfo[]
    public: AgentInfo[]
  }>({ builtin: [], custom: [], public: [] })

  useEffect(() => {
    fetchAgents().then(setAgents)
  }, [])

  const handleUseAgent = (agentId: string) => {
    // 跳转到对话页，通过 query 参数指定智能体
    navigate(`/?agent=${agentId}`)
  }

  const handleDelete = async (agentId: string) => {
    if (!confirm('确定删除这个智能体？')) return
    await deleteCustomAgent(agentId)
    const updated = await fetchAgents()
    setAgents(updated)
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Agent 中心</h1>

      {/* 内置智能体 */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold mb-4">内置智能体</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {agents.builtin.map(agent => (
            <div key={agent.id} className="border rounded-lg p-4">
              <div className="text-4xl mb-2">{agent.icon}</div>
              <h3 className="font-semibold">{agent.name}</h3>
              <p className="text-sm text-gray-600 mb-3">{agent.description}</p>
              <button
                onClick={() => handleUseAgent(agent.id)}
                className="w-full bg-sky-500 text-white py-2 rounded hover:bg-sky-600"
              >
                使用
              </button>
            </div>
          ))}
          <div className="border-2 border-dashed rounded-lg p-4 flex flex-col items-center justify-center">
            <Plus size={32} className="text-gray-400 mb-2" />
            <button
              onClick={() => navigate('/agents/create')}
              className="text-sky-500 font-medium"
            >
              创建自定义智能体
            </button>
          </div>
        </div>
      </div>

      {/* 我的智能体 */}
      {agents.custom.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold mb-4">我的智能体</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {agents.custom.map(agent => (
              <div key={agent.id} className="border rounded-lg p-4">
                <div className="text-4xl mb-2">{agent.icon}</div>
                <h3 className="font-semibold">{agent.name}</h3>
                <p className="text-sm text-gray-600 mb-3">{agent.description}</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleUseAgent(agent.id)}
                    className="flex-1 bg-sky-500 text-white py-2 rounded hover:bg-sky-600"
                  >
                    使用
                  </button>
                  <button
                    onClick={() => navigate(`/agents/edit/${agent.id}`)}
                    className="p-2 border rounded hover:bg-gray-50"
                  >
                    <Edit2 size={16} />
                  </button>
                  <button
                    onClick={() => handleDelete(agent.id)}
                    className="p-2 border rounded hover:bg-red-50 text-red-500"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 社区智能体 */}
      {agents.public.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">社区智能体</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {agents.public.map(agent => (
              <div key={agent.id} className="border rounded-lg p-4">
                <div className="text-4xl mb-2">{agent.icon}</div>
                <h3 className="font-semibold">{agent.name}</h3>
                <p className="text-sm text-gray-600 mb-3">{agent.description}</p>
                <button
                  onClick={() => handleUseAgent(agent.id)}
                  className="w-full bg-sky-500 text-white py-2 rounded hover:bg-sky-600"
                >
                  使用
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

#### 任务 7.3：创建/编辑智能体页面

**新建 `frontend/src/pages/AgentEditor.tsx`**：

```typescript
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchSkills, fetchAgents, createCustomAgent, updateCustomAgent, SkillInfo, AgentInfo } from '../utils/api'

export function AgentEditor() {
  const navigate = useNavigate()
  const { agentId } = useParams()
  const isEdit = !!agentId

  const [form, setForm] = useState({
    name: '',
    description: '',
    icon: '🤖',
    system_prompt: '',
    skills: [] as string[],
    welcome_message: '',
    temperature: 0.7,
    is_public: false,
  })

  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchSkills().then(setSkills).catch(() => setError('加载 Skill 列表失败'))
    if (isEdit && agentId) {
      // 编辑模式：加载现有智能体数据
      fetchAgents().then(data => {
        const all = [...data.custom, ...data.public]
        const existing = all.find(a => a.id === agentId)
        if (existing) {
          setForm({
            name: existing.name || '',
            description: existing.description || '',
            icon: existing.icon || '🤖',
            system_prompt: existing.system_prompt || '',
            skills: existing.skills || [],
            welcome_message: existing.welcome_message || '',
            temperature: existing.temperature ?? 0.7,
            is_public: existing.is_public ?? false,
          })
        } else {
          setError('智能体不存在')
        }
      }).catch(() => setError('加载智能体失败'))
    }
  }, [agentId, isEdit])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      if (isEdit && agentId) {
        await updateCustomAgent(agentId, form)
      } else {
        await createCustomAgent(form)
      }
      navigate('/agents')
    } catch (err) {
      setError(isEdit ? '保存失败' : '创建失败')
    } finally {
      setLoading(false)
    }
  }

  const toggleSkill = (skillName: string) => {
    setForm(prev => ({
      ...prev,
      skills: prev.skills.includes(skillName)
        ? prev.skills.filter(s => s !== skillName)
        : [...prev.skills, skillName],
    }))
  }

  if (error) {
    return <div className="max-w-2xl mx-auto p-6 text-red-600">{error}</div>
  }

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">{isEdit ? '编辑智能体' : '创建智能体'}</h1>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* 基本信息 */}
        <div>
          <label className="block text-sm font-medium mb-2">图标</label>
          <input
            type="text"
            value={form.icon}
            onChange={e => setForm({ ...form, icon: e.target.value })}
            className="w-20 px-3 py-2 border rounded"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">名称</label>
          <input
            type="text"
            value={form.name}
            onChange={e => setForm({ ...form, name: e.target.value })}
            className="w-full px-3 py-2 border rounded"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">描述</label>
          <textarea
            value={form.description}
            onChange={e => setForm({ ...form, description: e.target.value })}
            className="w-full px-3 py-2 border rounded"
            rows={3}
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">系统提示词</label>
          <textarea
            value={form.system_prompt}
            onChange={e => setForm({ ...form, system_prompt: e.target.value })}
            className="w-full px-3 py-2 border rounded font-mono text-sm"
            rows={6}
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">温度 (0-1)</label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={form.temperature}
            onChange={e => setForm({ ...form, temperature: parseFloat(e.target.value) })}
            className="w-full"
          />
          <span className="text-sm text-gray-600">{form.temperature}</span>
        </div>

        {/* Skill 选择器 */}
        <div>
          <label className="block text-sm font-medium mb-2">选择 Skill</label>
          <div className="space-y-2">
            {skills.map(skill => (
              <div
                key={skill.name}
                className={`border rounded p-3 cursor-pointer ${
                  form.skills.includes(skill.name) ? 'border-sky-500 bg-sky-50' : ''
                }`}
                onClick={() => toggleSkill(skill.name)}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">{skill.display_name}</div>
                    <div className="text-sm text-gray-600">{skill.description}</div>
                  </div>
                  <div className="text-sm">
                    {skill.requires_env.length > 0 && (
                      <span className={skill.env_configured ? 'text-green-600' : 'text-orange-600'}>
                        {skill.env_configured ? '✓ 已配置' : '⚠ 未配置'}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 公开设置 */}
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="is_public"
            checked={form.is_public}
            onChange={e => setForm({ ...form, is_public: e.target.checked })}
          />
          <label htmlFor="is_public" className="text-sm">公开到社区</label>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-sky-500 text-white py-3 rounded-lg font-medium hover:bg-sky-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? '处理中...' : (isEdit ? '保存' : '创建')}
        </button>
      </form>
    </div>
  )
}
```

**验收标准**：
- [ ] Agent 中心展示内置智能体（旅行规划）
- [ ] `AgentInfo` 类型用 `source` 字段（与后端对齐）
- [ ] 点击"使用"跳转 `/?agent=xxx`
- [ ] 创建自定义智能体页面正常
- [ ] Skill 选择器展示后端 skill 列表
- [ ] 环境变量配置状态正确显示（✓/⚠）
- [ ] 编辑智能体页面可回填数据
- [ ] 创建后可在 Agent 中心看到
- [ ] 使用自定义智能体对话正常

#### 任务 7.4：Home 组件读取 `?agent=xxx` 参数（关键衔接，勿遗漏）

> **合并注意**：AgentCenter 的 `handleUseAgent` 跳转到 `/?agent=xxx`，但 Home 组件当前没有读取这个参数，也没有把 `agent_id` 传给后端。这一步是衔接 Agent 中心和对话页的关键，遗漏会导致"使用智能体"按钮无效。

**修改 `frontend/src/pages/Home.tsx`**：

```typescript
import { useSearchParams } from 'react-router-dom'
import { useSessionStore } from '../hooks/useSessionStore'

export function Home() {
  const [searchParams, setSearchParams] = useSearchParams()
  const setActiveAgent = useSessionStore((s) => s.setActiveAgent)
  // ...现有代码...

  // 读取 URL 中的 agent 参数，激活对应智能体
  useEffect(() => {
    const agentFromUrl = searchParams.get('agent')
    if (agentFromUrl) {
      setActiveAgent(agentFromUrl)
      // 用完即清，避免刷新后仍锁定
      searchParams.delete('agent')
      setSearchParams(searchParams, { replace: true })
    }
  }, [searchParams, setActiveAgent, setSearchParams])

  // 修改 sendMessageStream 调用，传入 agent_id
  const handleSend = async (text: string) => {
    // ...现有代码...
    const currentAgentId = useSessionStore.getState().activeAgent
    const stream = sendMessageStream(
      {
        session_id: currentSessionId,
        user_id: currentUserId,
        message: text,
        agent_id: currentAgentId,  // 新增：传给后端 OrchestratorAgent
      },
      controller.signal,
    )
    // ...现有代码...
  }
}
```

**同时修改 `frontend/src/utils/api.ts` 的 `sendMessageStream`**：

```typescript
// 现有 sendMessageStream 的参数类型需要加 agent_id
export async function* sendMessageStream(
  req: { session_id: string; user_id: string; message: string; agent_id?: string },
  signal?: AbortSignal,
): AsyncGenerator<any> {
  // 请求体中加入 agent_id
  const body = JSON.stringify(req)  // agent_id 已在 req 中
  // ...现有 fetch 逻辑...
}
```

**验收标准**：
- [ ] 从 Agent 中心点击"使用"后，对话页显示对应智能体激活态
- [ ] 对话请求的 payload 包含 `agent_id` 字段
- [ ] 后端 OrchestratorAgent 收到 `agent_id` 后直接使用对应智能体（不走 LLM 路由）

---

## 五、文件清单

### 5.1 新增文件（后端 — 分层架构）

| 文件 | 层 | 行数 | 说明 |
|------|----|------|------|
| `core/base_agent.py` | 接口层 | ~35 | `BaseAgent` 抽象基类 |
| `core/agents/__init__.py` | — | 0 | 包初始化 |
| `core/agents/schema.py` | 模型层 | ~40 | `AgentConfig` + `SkillInfo`（纯数据，无依赖） |
| `agents/builtin/travel.yaml` | 配置层 | ~15 | 旅行智能体 YAML 配置（与代码分离） |
| `core/agents/builtin_loader.py` | 配置层 | ~45 | 从 YAML 加载内置智能体配置 |
| `core/skills/provider.py` | Skill 层 | ~110 | `SkillProvider` 抽象 + `FileSkillProvider` 实现 |
| `core/agents/repository.py` | 存储层 | ~95 | 只做 DB CRUD，返回 `AgentConfig` |
| `core/agents/runtime.py` | 运行时层 | ~75 | `DynamicAgent`（由 `AgentConfig` 驱动） |
| `core/agents/factory.py` | 工厂层 | ~40 | `AgentFactory`（解耦 Orchestrator 与具体类） |
| `core/agents/travel_agent.py` | 包装层 | ~70 | `TravelAgent`（包装现有 Agent） |
| `core/agents/orchestrator.py` | 路由层 | ~120 | `OrchestratorAgent`（LLM 路由 + 工厂创建） |

### 5.2 新增文件（前端）

| 文件 | 行数 | 说明 |
|------|------|------|
| `frontend/src/hooks/useSessionStore.ts` | ~25 | 会话激活态 Store |
| `frontend/src/components/AgentRouteGuard.tsx` | ~20 | 路由守卫组件 |
| `frontend/src/components/AgentActivationBanner.tsx` | ~25 | 智能体激活提示 |
| `frontend/src/components/AgentActionCard.tsx` | ~45 | 操作卡片组件 |
| `frontend/src/pages/AgentCenter.tsx` | ~120 | Agent 中心页面 |
| `frontend/src/pages/AgentEditor.tsx` | ~200 | 创建/编辑页面 |

### 5.3 修改文件

| 文件 | 改动量 | 说明 |
|------|--------|------|
| `infra/db.py` | ~15 行 | 新增 `custom_agents` 表迁移 |
| `api/server.py` | ~70 行 | 新增 skill/agent CRUD 接口 + `agent_id` 参数 |
| `app.py` | ~35 行 | 依赖注入：组装各层组件 |
| `frontend/src/App.tsx` | ~15 行 | 新增路由 |
| `frontend/src/utils/api.ts` | ~60 行 | 新增 API 封装 |
| `frontend/src/components/ChatWindow.tsx` | ~20 行 | 集成激活态 + 操作卡片 |

### 5.4 依赖新增

`requirements.txt` 新增：
```
PyYAML>=6.0
```

### 5.5 架构依赖关系图

```
app.py（组装层，依赖注入）
  │
  ├── FileSkillProvider ──实现──→ SkillProvider（接口）
  │                                    ↑
  ├── BuiltinAgentLoader ──加载──→ AgentConfig（模型）
  │                                    ↑
  ├── CustomAgentRepository ──返回──→ AgentConfig
  │                                    ↑
  ├── AgentFactory ──创建──→ BaseAgent（接口）
  │                              ↑
  │              ┌───────────────┼───────────────┐
  │              │               │               │
  │        DynamicAgent      TravelAgent      未来新Agent
  │        （配置驱动）      （特殊构造）     （...）
  │
  └── OrchestratorAgent
        ├─ 依赖：AgentFactory（不依赖具体 Agent 类）
        ├─ 依赖：CustomAgentRepository（不依赖 DB 细节）
        └─ 依赖：BaseAgent 接口（不依赖具体实现）
```

**关键解耦点**：
- OrchestratorAgent **不 import** DynamicAgent、TravelAgent 等具体类
- DynamicAgent **不 import** Repository、Loader 等数据来源
- 新增内置智能体 → 加一个 YAML 文件，**零代码改动**
- 新增自定义智能体 → 用户通过 API 创建，Orchestrator 自动发现
- 新增智能体类型（非配置驱动）→ 只改 AgentFactory，**不改 Orchestrator**

---

## 六、开发顺序

```
第 1 步：基础框架（阶段 1）
  ├─ core/base_agent.py
  ├─ core/agents/schema.py
  ├─ agents/builtin/travel.yaml
  ├─ core/agents/builtin_loader.py
  ├─ core/skills/provider.py
  └─ 验收：BuiltinAgentLoader 加载配置，FileSkillProvider 返回 skill 列表

第 2 步：存储与工厂（阶段 2）
  ├─ 数据库迁移（custom_agents 表）
  ├─ core/agents/repository.py
  ├─ core/agents/runtime.py
  ├─ core/agents/factory.py
  └─ 验收：CRUD 正常，工厂能创建 DynamicAgent

第 3 步：包装与路由（阶段 3）
  ├─ core/agents/travel_agent.py
  ├─ core/agents/orchestrator.py
  └─ 验收：TravelAgent 包装正常，Orchestrator 路由正常

第 4 步：组装与 API（阶段 4）
  ├─ app.py 依赖注入
  ├─ api/server.py 新增接口
  └─ 验收：API 全部可用

第 5 步：前端激活态（阶段 5）
  ├─ useSessionStore
  ├─ AgentRouteGuard
  ├─ App.tsx 路由改造
  └─ 验收：路由守卫生效

第 6 步：前端对话交互（阶段 6）
  ├─ AgentActivationBanner
  ├─ AgentActionCard
  ├─ ChatWindow 集成
  └─ 验收：激活提示 + 操作卡片正常

第 7 步：前端 Agent 中心（阶段 7）
  ├─ API 封装
  ├─ AgentCenter.tsx
  ├─ AgentEditor.tsx
  └─ 验收：创建/编辑/使用自定义智能体正常
```

---

## 七、验收清单

**后端 — 模型与配置层**：
- [ ] `AgentConfig` 和 `SkillInfo` 在 `schema.py` 中定义，无外部依赖
- [ ] `agents/builtin/travel.yaml` 存在且格式正确
- [ ] `BuiltinAgentLoader.load_all()` 返回旅行智能体配置

**后端 — Skill 层**：
- [ ] `SkillProvider` 是抽象基类，`FileSkillProvider` 实现接口
- [ ] `GET /api/skills` 返回 skill 列表（含 `env_configured` 状态）

**后端 — 存储层**：
- [ ] `custom_agents` 表已迁移
- [ ] `CustomAgentRepository` CRUD 正常，返回 `AgentConfig`
- [ ] `update` 方法使用白名单过滤（不允许注入非法字段）

**后端 — 运行时与工厂**：
- [ ] `DynamicAgent` 由 `AgentConfig` 驱动，构造函数只接收 3 个参数
- [ ] `AgentFactory.create(config)` 能根据配置创建 `DynamicAgent`
- [ ] `AgentFactory` 的 `builtin_builders` 能正确创建 `TravelAgent`

**后端 — OrchestratorAgent**：
- [ ] 不 import `DynamicAgent`、`TravelAgent` 等具体类
- [ ] LLM 路由正常（调用 `self._llm.complete(system=, messages=)`，确定性输出）
- [ ] 智能体描述缓存生效（60 秒 TTL）
- [ ] `agent_id` 参数指定时直接使用对应智能体
- [ ] 不传 `agent_id` 时自动路由
- [ ] Agent 实例缓存有上限（`_MAX_CACHE_SIZE = 100`），不会无界增长

**后端 — API**：
- [ ] `GET /api/agents` 返回 builtin + custom + public，字段用 `source` 而非 `type`
- [ ] `POST /api/agents/custom` 创建成功
- [ ] `PUT /api/agents/custom/{id}` 更新成功（权限校验）
- [ ] `DELETE /api/agents/custom/{id}` 删除成功（权限校验）
- [ ] `POST /api/chat` 支持 `agent_id` 参数
- [ ] `app.state` 依赖注入正常

**前端**：
- [ ] Agent 中心展示内置智能体（旅行规划）
- [ ] `AgentInfo` 类型用 `source` 字段（与后端对齐）
- [ ] 点击"使用"跳转 `/?agent=xxx`
- [ ] 创建自定义智能体页面正常
- [ ] Skill 选择器展示后端 skill 列表
- [ ] 环境变量配置状态正确显示（✓/⚠）
- [ ] 编辑智能体页面可回填数据
- [ ] 创建后可在 Agent 中心看到
- [ ] 使用自定义智能体对话正常

**解耦验证**：
- [ ] OrchestratorAgent 不 import 任何具体 Agent 类
- [ ] DynamicAgent 不 import Repository 或 Loader
- [ ] 新增内置智能体只需加 YAML 文件（零代码改动）
- [ ] 新增自定义智能体通过 API 创建，Orchestrator 自动发现

---

*文档生成日期：2026-06-21*
*商用审核修订：2026-06-24*

---

## 八、商用审核备忘录（2026-06-24 修订）

> 本节记录对原文档的商用角度审核结果，以及已修订和待修订的问题。

### 8.1 已修订的阻断性问题（会导致代码无法运行）

| # | 问题 | 原因 | 修订内容 |
|---|------|------|----------|
| 1 | `OpenAILLM.chat()` / `chat_stream()` 不存在 | `OpenAILLM` 实际方法是 `complete(system, messages)` / `stream_complete(system, messages)`，且不接受 `temperature`/`max_tokens` 参数 | DynamicAgent 和 OrchestratorAgent 的 LLM 调用全部改为 `complete` / `stream_complete` |
| 2 | `from infra.db import get_conn` 函数不存在 | 实际函数名是 `get_connection`，且返回 `sqlite3.Connection`，不是上下文管理器 | 改为 `get_connection()` + `try/finally` 手动 `close()` |
| 3 | `Depends(get_current_user)` 不存在 | 本项目认证走中间件 `auth_middleware`，通过 `request.state.user_id` 获取用户 | 所有 API 改为 `getattr(request.state, "user_id", None)` |
| 4 | `from app import app` 循环导入 | `api/server.py` 已 import `app.py`，反向导入会循环 | 改为返回 `AppContainer` 容器对象，在 `server.py` 中设置 `app.state` |
| 5 | `BaseAgent.chat` 无 `agent_id` 但 `OrchestratorAgent.chat` 有 | 违反 LSP（里氏替换原则） | `BaseAgent` 加 `**kwargs`，所有子类统一接受 `**kwargs` |
| 6 | Tailwind 动态类名 `bg-${color}-50` | 生产构建时会被 purge，样式丢失 | 改为静态类名映射 `Record<string, { bg: string; text: string }>` |

### 8.2 已修订的商用问题

| # | 问题 | 修订内容 |
|---|------|----------|
| 7 | TravelAgent 用正则提取行程 ID，与文档"反对正则路由"的立场矛盾 | 改为优先读结构化字段 `result["itinerary_id"]`，正则仅作过渡兜底，并加注释标记 TODO 废弃 |
| 8 | AgentEditor 编辑模式 `// TODO: 加载现有智能体数据` 未实现 | 补全 `fetchAgents` 回填逻辑 + loading/error 状态 |
| 9 | API 请求模型无输入校验（name/system_prompt 无长度限制，temperature 无范围校验） | 所有 Pydantic 模型加 `Field(..., min_length, max_length, ge, le)` |
| 10 | OrchestratorAgent `_agent_cache` 无界增长，内存泄漏 | 加 `_MAX_CACHE_SIZE = 100` 限制，超限时保留内置、淘汰自定义 |
| 11 | DynamicAgent 无会话记忆、无工具执行、无审计 | 在类 docstring 中明确标注商用限制，列为 MVP 已知不足 |

### 8.3 待后续迭代解决的商用问题（不阻断当前开发）

| # | 问题 | 建议 | 优先级 |
|---|------|------|--------|
| 12 | DynamicAgent 无多轮对话记忆 | 注入 `SessionManager`，在 `chat` 中加载会话历史拼入 messages | 高 |
| 13 | DynamicAgent 的 skills 只注入 prompt 不执行工具 | 接入 `ToolExecutor`，根据 `config.skills` 加载对应工具并支持 function calling | 高 |
| 14 | 自定义智能体创建无速率限制 | 加 Redis 计数器，每用户每天最多创建 N 个 | 中 |
| 15 | `is_public=True` 无审核流程 | 社区智能体应先进入审核队列，管理员通过后才公开 | 中 |
| 16 | Agent 列表无分页 | `list_by_user` / `list_public` 加 `limit`/`offset` 参数 | 中 |
| 17 | ~~前端 `handleUseAgent` 跳转 `/?agent=xxx` 但未展示如何读取该参数~~ | ✅ 已修订：见任务 7.4，Home 组件用 `useSearchParams` 读取并传入 chat 请求 | 高 |
| 18 | 路由守卫仅前端校验，可绕过 | 商用产品应在后端 API 层也校验 `active_agent` 与请求的 resource 是否匹配 | 中 |
| 19 | `deleteCustomAgent` 等 API 封装未检查 HTTP 状态码 | 封装统一 `fetchWithCheck`，非 2xx 抛异常 | 中 |
| 20 | 无自动化测试 | 补充 AgentConfig / Repository / Factory / Orchestrator 的单元测试 | 高 |
| 21 | ~~`travel.yaml` 中 `source: builtin` 与 `BuiltinAgentLoader._load_one` 硬编码 `source="builtin"` 重复~~ | ✅ 已修订：YAML 不写 source，由 loader 注入 | 低 |
| 22 | LLM 路由每次都消耗一次 LLM 调用（即使有描述缓存） | 考虑对高频消息加本地分类缓存（相同消息 → 相同路由） | 低 |

### 8.4 合并质量评估

**优点**：
- 架构分层清晰（配置层 / 模型层 / 存储层 / 工厂层 / 运行时层 / 路由层）
- 解耦原则明确（Orchestrator 不依赖具体类、Repository 只做 CRUD、配置与代码分离）
- 文件清单和开发顺序完整，可直接落地

**合并遗留问题（2026-06-24 第二轮合并审核补充）**：
- ✅ 验收清单遗留旧描述 `temperature=0, max_tokens=20`（已修订）
- ✅ 前端 `?agent=xxx` 参数读取逻辑缺失，导致 AgentCenter"使用"按钮无效（已补全任务 7.4）
- ✅ ChatWindow 集成是伪代码片段，`event` 变量凭空出现，下一个 AI 无法落地（已改为分步说明）
- ✅ `travel.yaml` 的 `source` 字段与 loader 硬编码冗余（已删除 YAML 中的 source）
- ✅ `api/server.py` 用 `json.dumps` 但实际代码是 `json_mod` 别名（已统一）
- ✅ MemoryPage 路由在盘点表和 App.tsx 改造中遗漏，会导致记忆页功能丢失（已补全）
- ✅ 前端 API 封装未说明 `authHeaders()` 来源（已加注释）

**仍需注意的合并风险**：
- 部分代码片段与实际代码库 API 不一致（已在 8.1 修订）
- DynamicAgent 的商用完整性不足（已在 8.3 列出待办）
- 缺少错误处理和边界情况的统一说明（如 LLM 路由失败、DB 查询超时等）
