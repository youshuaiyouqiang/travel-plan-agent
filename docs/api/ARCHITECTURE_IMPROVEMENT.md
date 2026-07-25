# 云合项目架构改进开发文档

> **文档性质**：基于企业级标准的目录结构与工程化评估，给出问题清单与整改方案。
>
> **适用项目**：云合 多智能体系统（后端 Python/FastAPI + 前端 React/TS）
>
> **配套规范**：`AGENTS.md`（v2.1 长期开发规范）
>
> **评估日期**：2026-07-12
>
> **版本**：v1.0

---

## 📋 目录

1. [评估总览](#1-评估总览)
2. [问题清单与严重度](#2-问题清单与严重度)
3. [P0：领域层依赖方向解耦](#3-p0领域层依赖方向解耦)
4. [P0：测试覆盖率提升](#4-p0测试覆盖率提升)
5. [P1：超大文件拆分](#5-p1超大文件拆分)
6. [P1：根目录与遗留文件清理](#6-p1根目录与遗留文件清理)
7. [P1：编码乱码与错位文件修复](#7-p1编码乱码与错位文件修复)
8. [P2：CI/CD 工程化补全](#8-p2cicd-工程化补全)
9. [P2：容器化部署支持](#9-p2容器化部署支持)
10. [P3：文档与配置一致性](#10-p3文档与配置一致性)
11. [整改路线图与里程碑](#11-整改路线图与里程碑)
12. [验收检查清单](#12-验收检查清单)

---

## 1. 评估总览

### 1.1 评估方法

对照 `AGENTS.md` v2.1 规范与企业级工程通用实践，从以下维度检查项目目录结构与工程化水平：

- 分层架构（DDD 四层 + 依赖方向）
- 代码组织（文件大小、目录职责、冗余文件）
- 测试体系（分层、覆盖率、CI 集成）
- 工程化配置（CI/CD、容器化、依赖管理、文档一致性）

### 1.2 量化数据

| 维度 | 数据 |
|------|------|
| Python 源文件总数 | 175 个（api 23 + application 27 + domain 69 + infrastructure 35 + config 2 + tests 19） |
| 超过 400 行的文件 | **9 个**（最大 `domain/reasoning/engine.py` 1293 行） |
| 领域层依赖基础设施违规 | **54 处**（遍布 20+ 文件） |
| domain 模块数 | 41 个 |
| 有对应单元测试的 domain 模块 | **4 个**（覆盖率 ~10%） |
| 前端 TS/TSX 文件 | 45 个 |
| CI workflow | 1 个（仅后端 lint/test/security） |

### 1.3 总体结论

> **项目的"骨架"合格**：DDD 四层分层清晰、路由按资源拆分、安全基础设施（bcrypt、Redis 限流、版本化迁移）均已落地。
>
> **但"肌肉"不足**：核心的依赖倒置原则未被遵守（领域层 54 处直接依赖基础设施），导致可测试性差，测试覆盖率仅 ~10%，形成恶性循环。同时存在冗余文件、编码乱码、CI 缺前端等工程化短板。
>
> **定位**：当前处于"规范的 MVP 阶段"，距离企业级生产标准仍有技术债需偿还。

### 1.4 评分汇总

| 维度 | 评分 | 关键短板 |
|------|------|----------|
| 分层架构（DDD） | ⭐⭐⭐⭐☆ | 依赖方向 54 处违规 |
| 目录组织 | ⭐⭐⭐☆☆ | 冗余/遗留文件、根目录不够干净 |
| 代码规范执行 | ⭐⭐☆☆☆ | 9 文件超 400 行 |
| 测试体系 | ⭐⭐☆☆☆ | 覆盖率 ~10%，CI 主动跳过测试 |
| 工程化配置 | ⭐⭐⭐☆☆ | 无前端 CI、无容器化 |

---

## 2. 问题清单与严重度

| 编号 | 严重度 | 问题 | 所在章节 |
|------|--------|------|----------|
| ISS-01 | 🔴 P0 | 领域层大规模违反依赖方向（54 处 `domain → infrastructure`） | §3 |
| ISS-02 | 🔴 P0 | 测试覆盖率 ~10%，核心模块零测试 | §4 |
| ISS-03 | 🔴 P0 | CI 主动跳过测试（`--ignore-glob="*test_prompting*"`） | §8 |
| ISS-04 | 🟠 P1 | 9 个文件超过 400 行限制 | §5 |
| ISS-05 | 🟠 P1 | 根目录冗余文件（空 `requirements.txt`、`app.py`、空 `api/routes/`） | §6 |
| ISS-06 | 🟠 P1 | `api/intl_coords.py` 编码乱码 + 错位于 API 层 | §7 |
| ISS-07 | 🟠 P1 | `.dbg/` 调试日志目录未忽略 | §6 |
| ISS-08 | 🟠 P1 | `data/.gitkeep` 缺失，gitignore 规则失效 | §6 |
| ISS-09 | 🟡 P2 | CI 无前端构建/类型检查/lint | §8 |
| ISS-10 | 🟡 P2 | 无 Dockerfile / docker-compose，无法容器化部署 | §9 |
| ISS-11 | 🟡 P2 | 无 Python 多版本矩阵测试 | §8 |
| ISS-12 | 🟢 P3 | `pyproject.toml` name=`yunhe` 与项目名"云合"不一致 | §10 |
| ISS-13 | 🟢 P3 | AGENTS.md 引用已删除的 `DEVELOPMENT_SPECIFICATION.md` | §10 |
| ISS-14 | 🟢 P3 | `infrastructure/external/` 空目录未实现 | §10 |
| ISS-15 | 🟢 P3 | `domain/shared/` 下 audit/metrics/runtime 职责混杂 | §10 |

---

## 3. P0：领域层依赖方向解耦

### 3.1 问题描述

`AGENTS.md` §2.3 **严禁**领域层直接依赖基础设施层具体类。但实际检测到 **54 处违规**，分布如下：

| 违规文件 | 违规 import 示例 | 违规类型 |
|----------|------------------|----------|
| `domain/agent/dynamic_agent.py` | `from infrastructure.llm.openai import OpenAILLM` | LLM 具体类 |
| `domain/agent/dynamic_agent.py` | `from infrastructure.tools.executor import ToolExecutor` | 工具执行器 |
| `domain/agent/factory.py` | `from infrastructure.skills.provider import SkillProvider` | 技能提供者 |
| `domain/agent/orchestrator.py` | `from infrastructure.llm.openai import OpenAILLM` | LLM 具体类 |
| `domain/agent/repository.py` | `from infrastructure.persistence.database import get_connection` | 数据库连接 |
| `domain/memory/manager.py` | `from infrastructure.persistence.database import get_connection, _json_loads` | 数据库 + 私有函数 |
| `domain/memory/memory_distiller.py` | `from infrastructure.llm.openai import OpenAILLM` | LLM 具体类 |
| `domain/reasoning/engine.py` | `from infrastructure.tools.registry import ToolRegistry` | 工具注册表 |
| `domain/travel/core.py` | `from infrastructure.mcp.runtime import MCPProxyRuntime` | MCP 具体类 |
| `domain/travel/core.py` | `from infrastructure.persistence.session_repository import SessionRepository` | 仓储具体类 |
| `domain/travel/album/repository.py` | `from infrastructure.persistence.database import get_connection` | 数据库连接 |
| `domain/user/auth/auth.py` | `from infrastructure.security.password import hash_password` | 密码工具 |
| `domain/user/profile/manager.py` | `from infrastructure.persistence.database import _json_dumps` | 私有函数 |
| ... | （共 54 处，详见检测脚本输出） | ... |

### 3.2 根因分析

`domain/` 层缺少抽象接口定义，领域逻辑直接引用基础设施的具体实现类。这导致：

1. **无法单元测试**：测试领域层时必须 mock 具体类而非接口，且具体类可能带副作用（数据库连接、网络请求）。
2. **基础设施变更波及领域层**：如更换 LLM provider 或数据库引擎，需修改大量领域文件。
3. **违背依赖倒置原则（DIP）**：高层模块不应依赖低层模块，二者都应依赖抽象。

### 3.3 整改方案

#### 第一步：在 `domain/shared/` 下新增抽象接口层

```
domain/
└── shared/
    ├── ports/                      # 新增：抽象端口（接口定义）
    │   ├── __init__.py
    │   ├── llm_gateway.py          # ILLMGateway — LLM 调用抽象
    │   ├── tool_gateway.py         # IToolRegistry / IToolExecutor — 工具抽象
    │   ├── mcp_gateway.py          # IMCPRuntime / IMCPCatalog — MCP 抽象
    │   ├── skill_provider.py       # ISkillProvider — 技能提供者抽象
    │   ├── repository.py           # 通用仓储接口基类
    │   └── crypto.py               # IPasswordHasher — 密码哈希抽象
    ├── types.py                    # 已有
    ├── audit/                      # 已有
    ├── metrics/                    # 已有
    └── runtime/                    # 已有
```

#### 第二步：定义抽象接口（示例）

```python
# domain/shared/ports/llm_gateway.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponseDTO:
    """LLM 响应数据传输对象（领域层定义，基础设施层填充）。"""
    content: str
    tool_calls: list[dict] | None = None
    finish_reason: str | None = None
    usage: dict | None = None


class ILLMGateway(ABC):
    """LLM 调用网关抽象接口。

    领域层通过此接口调用 LLM，具体实现由 infrastructure/llm 提供。
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponseDTO:
        """同步对话。"""
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> "AsyncIterator[LLMResponseDTO]":
        """流式对话。"""
        ...
```

```python
# domain/shared/ports/repository.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class IRepository(ABC, Generic[T]):
    """通用仓储接口基类。

    领域层定义仓储接口，基础设施层提供具体实现（基于 SQLite）。
    """

    @abstractmethod
    def get_by_id(self, entity_id: str) -> T | None:
        ...

    @abstractmethod
    def save(self, entity: T) -> T:
        ...

    @abstractmethod
    def delete(self, entity_id: str) -> bool:
        ...
```

```python
# domain/shared/ports/crypto.py
from __future__ import annotations

from abc import ABC, abstractmethod


class IPasswordHasher(ABC):
    """密码哈希抽象接口。"""

    @abstractmethod
    def hash(self, password: str) -> str:
        ...

    @abstractmethod
    def verify(self, password: str, stored: str) -> bool:
        ...

    @abstractmethod
    def needs_upgrade(self, stored: str) -> bool:
        ...
```

#### 第三步：基础设施层实现接口

```python
# infrastructure/llm/openai.py
from domain.shared.ports.llm_gateway import ILLMGateway, LLMResponseDTO


class OpenAILLM(ILLMGateway):  # 实现领域层接口
    """OpenAI LLM 实现（实现 ILLMGateway）。"""

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponseDTO:
        # ... 原有实现 ...
        return LLMResponseDTO(content=..., tool_calls=..., ...)
```

#### 第四步：领域层改为依赖接口

```python
# domain/agent/dynamic_agent.py — 整改后
# ❌ 整改前：from infrastructure.llm.openai import OpenAILLM
# ✅ 整改后：
from domain.shared.ports.llm_gateway import ILLMGateway
from domain.shared.ports.tool_gateway import IToolExecutor, IToolRegistry


class DynamicAgent:
    def __init__(
        self,
        config: AgentConfig,
        llm: ILLMGateway,              # 依赖接口
        tool_executor: IToolExecutor,  # 依赖接口
        tool_registry: IToolRegistry,  # 依赖接口
        skill_provider: ISkillProvider,
        ...
    ):
        self._llm = llm
        ...
```

#### 第五步：依赖注入容器组装

```python
# app.py（或 application/container.py）中组装
def build_orchestrator() -> AppContainer:
    # 基础设施层创建具体实现
    llm: ILLMGateway = OpenAILLM(audit_logger=audit_logger)
    tool_registry: IToolRegistry = ToolRegistry()
    tool_executor: IToolExecutor = ToolExecutor(...)

    # 注入领域层（领域层只看到接口）
    orchestrator = OrchestratorAgent(
        llm=llm,
        factory=factory,
        ...
    )
```

### 3.4 需要定义的接口清单

| 接口名 | 文件 | 替代的基础设施依赖 | 涉及领域文件数 |
|--------|------|---------------------|----------------|
| `ILLMGateway` | `ports/llm_gateway.py` | `infrastructure.llm.openai.OpenAILLM` | 10+ |
| `IToolRegistry` | `ports/tool_gateway.py` | `infrastructure.tools.registry.ToolRegistry` | 6 |
| `IToolExecutor` | `ports/tool_gateway.py` | `infrastructure.tools.executor.ToolExecutor` | 5 |
| `IMCPRuntime` | `ports/mcp_gateway.py` | `infrastructure.mcp.runtime.MCPProxyRuntime` | 3 |
| `IMCPCatalog` | `ports/mcp_gateway.py` | `infrastructure.mcp.catalog.MCPCatalog` | 2 |
| `ISkillProvider` | `ports/skill_provider.py` | `infrastructure.skills.provider.SkillProvider` | 2 |
| `IPasswordHasher` | `ports/crypto.py` | `infrastructure.security.password` | 2 |
| `IUserRepository` | `ports/repository.py` | `infrastructure.persistence.database` | 8+ |
| `ISessionRepository` | `ports/repository.py` | `infrastructure.persistence.session_repository` | 3 |
| `IDatabase` / `IConnection` | `ports/database.py` | `infrastructure.persistence.database.get_connection` | 10+ |

### 3.5 验收标准

- [ ] `domain/` 下所有 `.py` 文件中，无任何 `from infrastructure.*` 或 `import infrastructure.*` 语句
- [ ] 检测脚本输出违规数 = 0
- [ ] 领域层单元测试可使用 `unittest.mock.Mock` 注入接口实现，无需启动真实数据库/网络

### 3.6 验证脚本

```bash
# 检查领域层是否还有对基础设施层的直接依赖
py -3 -X utf8 -c "
import os, re
violations = []
for r, d, files in os.walk('domain'):
    if '__pycache__' in r:
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fp = os.path.join(r, f)
        for i, line in enumerate(open(fp, encoding='utf-8').read().splitlines(), 1):
            s = line.strip()
            if s.startswith('#'):
                continue
            if re.search(r'from infrastructure\.|import infrastructure\.', s):
                violations.append((fp, i, s))
for fp, i, s in violations:
    print(f'{fp}:{i} {s}')
print(f'Total: {len(violations)}')
"
```

---

## 4. P0：测试覆盖率提升

### 4.1 现状

| 层 | 模块数 | 有对应测试 | 覆盖率 |
|----|--------|-----------|--------|
| `domain/` | 41 | **4** | **~10%** |
| `tests/unit/` | 9 个测试文件 | — | — |
| `tests/integration/` | 6 个测试文件 | — | — |

**已覆盖的 domain 模块**：`prompting`、`task_state`、`context_manager`、`types`

**零测试的核心模块**（按优先级排序）：

| 优先级 | 模块 | 行数 | 测试原因 |
|--------|------|------|----------|
| 🔴 最高 | `domain/reasoning/engine.py` | 1293 | 三层决策核心，全系统最关键逻辑 |
| 🔴 最高 | `domain/agent/orchestrator.py` | 609 | 总调度，委派逻辑复杂 |
| 🟠 高 | `domain/travel/core.py` | 441 | 旅行 Agent 主循环 |
| 🟠 高 | `domain/agent/factory.py` | — | 智能体工厂，影响实例化 |
| 🟡 中 | `domain/memory/manager.py` | — | 记忆管理 |
| 🟡 中 | `domain/memory/memory_distiller.py` | — | 记忆蒸馏 |
| 🟡 中 | `domain/user/auth/auth.py` | — | 认证核心（安全敏感） |

### 4.2 整改目标

| 阶段 | 覆盖率目标 | 期限 |
|------|-----------|------|
| 当前 | ~10% | — |
| 阶段一 | ≥ 40% | P0 解耦完成后 2 周内 |
| 阶段二 | ≥ 70%（规范底线） | 阶段一后 4 周内 |
| 阶段三 | ≥ 80%（规范建议） | 持续 |

### 4.3 整改方案

#### 前置条件

测试覆盖率提升**依赖 §3 依赖解耦完成**。只有领域层依赖接口而非具体类后，才能用 mock 注入进行单元测试。

#### 测试编写规范（遵循 AGENTS.md §8.3）

```python
# tests/unit/test_domain/test_orchestrator.py
import pytest
from unittest.mock import Mock
from domain.agent.orchestrator import OrchestratorAgent
from domain.shared.ports.llm_gateway import ILLMGateway  # 接口
from domain.shared.ports.tool_gateway import IToolExecutor


class TestOrchestratorAgent:
    """OrchestratorAgent 单元测试。"""

    def test_tier0_fast_path_returns_directly(self):
        """Tier0 快路径：简单问题直接回复，不委派。"""
        # Arrange
        mock_llm = Mock(spec=ILLMGateway)
        mock_llm.chat = Mock(return_value=LLMResponseDTO(content="你好！"))
        orchestrator = OrchestratorAgent(
            llm=mock_llm,
            factory=Mock(),
            builtin_configs=[],
            custom_repo=Mock(),
            default_agent="yunhe",
        )

        # Act
        result = orchestrator.route("你好", session_id="s1")

        # Assert
        assert "你好" in result.reply
        mock_llm.chat.assert_called_once()

    def test_tier1_delegates_to_travel_agent(self):
        """Tier1：旅行类问题委派给 travel agent。"""
        # Arrange
        mock_llm = Mock(spec=ILLMGateway)
        mock_factory = Mock()
        mock_factory.create.return_value = Mock()
        orchestrator = OrchestratorAgent(
            llm=mock_llm,
            factory=mock_factory,
            builtin_configs=[...],
            custom_repo=Mock(),
            default_agent="yunhe",
        )

        # Act
        orchestrator.route("帮我规划北京3日游", session_id="s1")

        # Assert
        mock_factory.create.assert_called_with(agent_id="travel")
```

#### 必须新增的测试文件清单

```
tests/unit/test_domain/
├── test_orchestrator.py          # ← 新增（覆盖 orchestrator.py）
├── test_engine.py               # ← 新增（覆盖 engine.py，含 Tier0/1/2）
├── test_dynamic_agent.py        # ← 新增
├── test_factory.py              # ← 新增
├── test_travel_core.py          # ← 新增（覆盖 travel/core.py）
├── test_auth_service.py         # ← 新增（覆盖 user/auth/auth.py）
├── test_memory_manager.py       # ← 新增
├── test_memory_distiller.py     # ← 新增
├── test_travel_classifier.py    # ← 新增
├── test_itinerary_parser.py     # ← 新增
└── test_album_service.py        # ← 新增
```

#### CI 跳过测试的修复

当前 CI 中存在：
```yaml
# .github/workflows/ci.yml (第 27 行)
- run: pytest --ignore-glob="*test_prompting*" --cov=. --cov-report=xml
```

**问题**：`test_prompting` 测试存在未修复的失败，CI 通过 `--ignore-glob` 主动跳过，掩盖问题。

**整改**：
1. 诊断 `tests/unit/test_prompting.py` 失败原因并修复
2. 移除 CI 中的 `--ignore-glob="*test_prompting*"`
3. 确保 `pytest` 无 `--ignore` 参数即可全量通过

### 4.4 验收标准

- [ ] `pytest --cov=. --cov-report=term-missing` 全量通过，无跳过
- [ ] domain 层覆盖率 ≥ 70%
- [ ] `orchestrator.py`、`engine.py`、`core.py`、`auth.py` 均有对应测试文件
- [ ] 测试遵循 AAA 模式，不依赖真实数据库/网络

---

## 5. P1：超大文件拆分

### 5.1 违规文件清单

AGENTS.md §2.1 规定单文件 ≤ 400 行。以下 **9 个文件超标**：

| 行数 | 文件 | 超标倍数 | 拆分建议 |
|------|------|----------|----------|
| **1293** | `domain/reasoning/engine.py` | 3.2× | 按 Tier0/Tier1/Tier2 拆分 |
| 662 | `infrastructure/persistence/database.py` | 1.7× | 迁移函数抽离到 `migrations/` |
| 661 | `domain/travel/intent/travel_classifier.py` | 1.7× | 按意图分类拆分 |
| 651 | `infrastructure/mcp/runtime.py` | 1.6× | 按协议处理拆分 |
| 609 | `domain/agent/orchestrator.py` | 1.5× | 按调度层拆分 |
| 461 | `domain/travel/services/context_preparer.py` | 1.2× | 按上下文准备阶段拆分 |
| 441 | `domain/travel/core.py` | 1.1× | 主循环 / 工具调用 / 消息处理 |
| 433 | `application/trending/manager.py` | 1.1× | 爬取 / 缓存 / 解析拆分 |
| 415 | `tests/unit/test_memory_extractor_distiller.py` | 1.0× | 按被测模块拆分 |

### 5.2 拆分方案（以 `engine.py` 为例）

`domain/reasoning/engine.py`（1293 行）是三层决策引擎，应按决策层拆分：

```
domain/reasoning/
├── engine.py              # 整改后：仅 Engine 入口 + 调度（< 200 行）
├── tier0_fast_path.py     # Tier0：快路径（简单问题直接回复）
├── tier1_function_call.py  # Tier1：function calling 委派
├── tier2_delegation.py    # Tier2：委派执行
├── context_builder.py     # 上下文构建（消息历史、工具列表）
├── response_parser.py     # LLM 响应解析
└── __init__.py
```

### 5.3 `database.py` 拆分方案

`infrastructure/persistence/database.py`（662 行）含 10 个迁移函数，应将迁移抽离：

```
infrastructure/persistence/
├── database.py            # 整改后：连接管理 + init_db（< 200 行）
├── connection.py          # 连接池 / get_connection
├── json_utils.py          # _json_dumps / _json_loads（被领域层引用，需先解耦）
└── migrations/
    ├── __init__.py         # 迁移注册
    ├── m001_to_m005.py     # 迁移 1-5
    └── m006_to_m010.py     # 迁移 6-10
```

> ⚠️ **注意**：`_json_dumps` / `_json_loads` 是 `database.py` 的私有函数，但被 `domain/memory/manager.py`、`domain/user/profile/manager.py` 等多处引用。这是 ISS-01 的子问题。解耦时应将其提升为公共工具或定义到 `domain/shared/` 下。

### 5.4 验收标准

- [ ] 无 `.py` 文件超过 400 行（ORM 模型聚合、配置表等需在文件头注释说明原因）
- [ ] `ruff check .` 无新增警告
- [ ] 拆分后功能不变，集成测试全量通过

---

## 6. P1：根目录与遗留文件清理

### 6.1 需清理的文件/目录

| 文件/目录 | 问题 | 处理方式 |
|-----------|------|----------|
| `requirements.txt` | 空文件（0 字节），项目用 `pyproject.toml` 管理依赖 | **删除** |
| `api/routes/` | 空目录（仅含 0 字节 `__init__.py`），重构遗留 | **删除整个目录** |
| `app.py` | 229 行依赖注入容器放在根目录，根目录应保持干净 | **移动**至 `application/container.py`，根目录 `app.py` 删除或保留极简入口 |
| `.dbg/` | 调试日志目录（含 `trae-debug-log-*.ndjson`）在仓库根 | **加入 `.gitignore`** + 删除已追踪文件 |
| `data/` | 无 `.gitkeep`，`.gitignore` 中 `!data/.gitkeep` 规则失效 | **创建** `data/.gitkeep`（空文件） |
| `__pycache__/`（根目录） | 根目录存在 `__pycache__` | **删除** + 确认 `.gitignore` 已覆盖 |

### 6.2 `app.py` 迁移方案

当前 `app.py` 是依赖注入容器（`AppContainer` + `build_orchestrator`），职责上是应用层组装逻辑。

**方案 A（推荐）**：移动到 `application/container.py`

```python
# application/container.py（从 app.py 迁移）
from dataclasses import dataclass, field
# ... 原有 imports ...

@dataclass
class AppContainer:
    """依赖注入容器。"""
    ...

def build_orchestrator() -> AppContainer:
    """组装多智能体架构。"""
    ...
```

更新引用处：
```python
# api/server.py
# ❌ 整改前：from app import build_orchestrator
# ✅ 整改后：
from application.container import build_orchestrator
```

根目录可保留极简入口（可选）：
```python
# app.py（整改后，可选）
"""项目入口 — 转发到 application.container。"""
from application.container import build_orchestrator  # noqa: F401
```

### 6.3 `.gitignore` 补充

```gitignore
# 在现有 .gitignore 中追加

# Debug artifacts
.dbg/

# Ensure data placeholder
!data/.gitkeep
```

### 6.4 验收标准

- [ ] 根目录无空 `requirements.txt`
- [ ] 根目录无空 `api/routes/`
- [ ] `app.py` 已迁移或精简
- [ ] `.dbg/` 在 `.gitignore` 中
- [ ] `data/.gitkeep` 存在

---

## 7. P1：编码乱码与错位文件修复

### 7.1 问题描述

`api/intl_coords.py` 存在两个问题：

1. **编码乱码**：文件以 GBK/GB2312 编码保存中文，但项目其他文件均为 UTF-8。在 UTF-8 环境下读取出现乱码（如 `"涓滀含"` 应为 `"东京"`）。
2. **错位**：国际坐标常量字典是领域知识数据，不应放在 `api/`（API 层），应放在 `domain/` 或 `infrastructure/`。

### 7.2 整改方案

#### 第一步：修复编码

将文件内容重新以 UTF-8 编码保存，修复所有乱码城市名。

#### 第二步：迁移到正确位置

```
# 迁移路径
api/intl_coords.py  →  domain/travel/geo/intl_coords.py
```

或放置在基础设施层（如果视为外部数据源）：
```
api/intl_coords.py  →  infrastructure/external/geo/intl_coords.py
```

**推荐**：放 `domain/travel/geo/`，因为坐标数据是旅行领域的领域知识。

#### 第三步：更新引用

```python
# api/v1/geocode.py
# ❌ 整改前：from api.intl_coords import lookup_intl_coords
# ✅ 整改后：
from domain.travel.geo.intl_coords import lookup_intl_coords
```

### 7.3 验收标准

- [ ] 文件以 UTF-8 编码保存，所有中文正确显示
- [ ] 文件不在 `api/` 层
- [ ] 所有引用处已更新
- [ ] `ruff check .` 无编码相关警告

---

## 8. P2：CI/CD 工程化补全

### 8.1 当前 CI 状态

```yaml
# .github/workflows/ci.yml（当前）
jobs:
  lint:        # 后端 ruff check
  test:        # 后端 pytest（跳过 test_prompting）
  security:    # bandit（非阻塞）
```

### 8.2 问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| 无前端 CI | 🟡 P2 | 前端构建/类型检查/lint 完全缺失 |
| CI 跳过测试 | 🔴 P0 | `--ignore-glob="*test_prompting*"` 掩盖失败 |
| 无多版本矩阵 | 🟡 P2 | 仅固定 Python 3.11，未验证 3.12 |
| mypy 未接入 CI | 🟢 P3 | 规范标注"可选"，企业级建议强制 |
| 无部署流程 | 🟡 P2 | 无 release / deploy workflow |

### 8.3 整改方案：CI 补全

```yaml
# .github/workflows/ci.yml（整改后）
name: CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  # ===== 后端 =====
  backend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install ruff
      - run: ruff check .

  backend-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]   # 多版本矩阵
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      # ❌ 整改前：- run: pytest --ignore-glob="*test_prompting*" --cov=. --cov-report=xml
      # ✅ 整改后：全量运行，不跳过
      - run: pytest --cov=. --cov-report=xml
      - uses: codecov/codecov-action@v4

  backend-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: mypy api application domain infrastructure

  backend-security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install bandit
      - run: bandit -r api application domain infrastructure

  # ===== 前端（新增）=====
  frontend-lint-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - run: cd frontend && npm ci
      - run: cd frontend && npm run lint
      - run: cd frontend && npm run check     # tsc 类型检查
      - run: cd frontend && npm run build      # 构建验证
```

### 8.4 验收标准

- [ ] CI 包含前端 lint + typecheck + build
- [ ] CI 无 `--ignore-glob` 跳过
- [ ] 后端测试支持 Python 3.11 + 3.12 矩阵
- [ ] mypy 接入 CI（可先设 `continue-on-error: true` 逐步收紧）

---

## 9. P2：容器化部署支持

### 9.1 现状

项目无 `Dockerfile`、无 `docker-compose.yml`，无法一键容器化部署。企业级项目通常需要容器化以保证环境一致性。

### 9.2 整改方案

#### Dockerfile（后端）

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 系统依赖（bcrypt 等可能需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装依赖
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# 复制源码
COPY api/ application/ config/ domain/ infrastructure/ ./

# 数据目录
RUN mkdir -p data/logs data/audit data/album

EXPOSE 8000

CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### Dockerfile（前端）

```dockerfile
# frontend/Dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

#### docker-compose.yml

```yaml
# docker-compose.yml
services:
  backend:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./.env:/app/.env:ro
    depends_on:
      - redis
    environment:
      - REDIS_URL=redis://redis:6379/0

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

volumes:
  redis-data:
```

### 9.3 验收标准

- [ ] `docker compose up` 可一键启动后端 + 前端 + Redis
- [ ] 后端容器健康检查通过
- [ ] 前端容器可访问并正确代理 API 请求

---

## 10. P3：文档与配置一致性

### 10.1 问题清单

| 编号 | 问题 | 处理方式 |
|------|------|----------|
| ISS-12 | `pyproject.toml` 中 `name = "yunhe"` 与项目名"云合"不一致 | 统一为 `yunhe` 或在文档说明 `yunhe` 为内部代号 |
| ISS-13 | `AGENTS.md` 引用 `DEVELOPMENT_SPECIFICATION.md` 作为配套文档，但该文件已被删除（git status: `D docs/DEVELOPMENT_SPECIFICATION.md`） | 更新 AGENTS.md 引用，指向本文档或恢复该文件 |
| ISS-14 | `infrastructure/external/` 空目录（仅 `__init__.py`），未实现 | 实现或删除占位 |
| ISS-15 | `domain/shared/` 下 `audit/`、`metrics/`、`runtime/` 职责混杂 | 评估是否需要重组（低优先级） |

### 10.2 AGENTS.md 引用修复

```markdown
<!-- AGENTS.md 当前（第 7 行）-->
**配套文档**：`DEVELOPMENT_STANDARDS.md`（现状评估 + 一次性重构路线图）。

<!-- 整改后 -->
**配套文档**：
- `docs/api/ARCHITECTURE_IMPROVEMENT.md`（架构改进开发文档）
- `docs/api/API.md`（前端接口参考）
```

### 10.3 验收标准

- [ ] `pyproject.toml` name 字段与项目命名一致或有文档说明
- [ ] AGENTS.md 中无失效文档引用
- [ ] 无空占位目录（除非有明确计划）

---

## 11. 整改路线图与里程碑

### 11.1 里程碑规划

```
M0（当前）          M1（P0 完成）        M2（P1 完成）        M3（P2 完成）
  │                    │                    │                    │
  ├─ ISS-01 解耦 ◄──────┤                    │                    │
  ├─ ISS-02 测试 ◄──────┤                    │                    │
  ├─ ISS-03 CI跳过 ◄───┤                    │                    │
  │                    ├─ ISS-04 拆分 ◄──────┤                    │
  │                    ├─ ISS-05 清理 ◄──────┤                    │
  │                    ├─ ISS-06 乱码 ◄──────┤                    │
  │                    ├─ ISS-07 .dbg ◄──────┤                    │
  │                    ├─ ISS-08 gitkeep ◄───┤                    │
  │                    │                    ├─ ISS-09 前端CI ◄────┤
  │                    │                    ├─ ISS-10 容器化 ◄───┤
  │                    │                    ├─ ISS-11 矩阵 ◄──────┤
  │                    │                    │                    ├─ ISS-12~15 ◄──
```

### 11.2 时间估算

| 里程碑 | 内容 | 估算工时 | 前置依赖 |
|--------|------|----------|----------|
| **M1** | P0：依赖解耦 + 测试覆盖率 ≥ 40% + CI 修复 | 5-8 人日 | 无 |
| **M2** | P1：文件拆分 + 根目录清理 + 乱码修复 | 3-5 人日 | M1 完成 |
| **M3** | P2：前端 CI + 容器化 + 多版本矩阵 | 2-3 人日 | 无（可与 M2 并行） |
| **M4** | P3：文档一致性 + 配置清理 | 1 人日 | 无 |

### 11.3 执行顺序建议

1. **先做 ISS-01（依赖解耦）**：这是所有其他改进的基础。解耦后测试才能 mock，文件拆分才能按接口边界划分。
2. **再做 ISS-02（测试）**：解耦后立即补测试，验证解耦正确性。
3. **并行做 ISS-04~08（清理与拆分）**：这些是独立的机械性工作。
4. **最后做 ISS-09~11（CI/容器化）**：工程化收尾。

---

## 12. 验收检查清单

### 12.1 架构与依赖

- [ ] `domain/` 下无任何 `from infrastructure.*` 语句（检测脚本违规数 = 0）
- [ ] `domain/shared/ports/` 下定义了 ILLMGateway、IToolRegistry 等抽象接口
- [ ] 基础设施层实现类均声明实现对应接口（`class OpenAILLM(ILLMGateway)`）
- [ ] 依赖注入在 `application/container.py` 中集中组装

### 12.2 代码组织

- [ ] 无 `.py` 文件超过 400 行（特殊文件有文件头注释说明）
- [ ] 根目录无空 `requirements.txt`
- [ ] 根目录无空 `api/routes/`
- [ ] `app.py` 已迁移至 `application/`
- [ ] `api/intl_coords.py` 已迁移至 `domain/travel/geo/` 并修复编码

### 12.3 测试

- [ ] `pytest` 全量通过，无 `--ignore` 跳过
- [ ] domain 屄覆盖率 ≥ 70%
- [ ] `orchestrator.py`、`engine.py`、`core.py`、`auth.py` 有对应测试文件
- [ ] 单元测试不依赖真实数据库/网络（使用 mock）

### 12.4 CI/CD

- [ ] CI 包含前端 lint + typecheck + build
- [ ] CI 后端测试支持 Python 3.11 + 3.12 矩阵
- [ ] CI 无 `--ignore-glob` 跳过
- [ ] mypy 接入 CI
- [ ] 存在 `Dockerfile` + `docker-compose.yml`
- [ ] `docker compose up` 可一键启动

### 12.5 配置与文档

- [ ] `.gitignore` 包含 `.dbg/`
- [ ] `data/.gitkeep` 存在
- [ ] AGENTS.md 无失效文档引用
- [ ] `pyproject.toml` name 与项目命名一致

---

## 附录：检测脚本汇总

### A. 检查依赖方向违规

```bash
py -3 -X utf8 -c "
import os, re
violations = []
for r, d, files in os.walk('domain'):
    if '__pycache__' in r:
        continue
    for f in files:
        if not f.endswith('.py'):
            continue
        fp = os.path.join(r, f)
        for i, line in enumerate(open(fp, encoding='utf-8').read().splitlines(), 1):
            s = line.strip()
            if s.startswith('#'):
                continue
            if re.search(r'from infrastructure\.|import infrastructure\.', s):
                violations.append((fp, i, s))
for fp, i, s in violations:
    print(f'{fp}:{i} {s}')
print(f'Total violations: {len(violations)}')
"
```

### B. 检查超过 400 行的文件

```bash
py -3 -X utf8 -c "
import os
violations = []
for top in ['api', 'application', 'domain', 'infrastructure', 'config', 'tests']:
    for r, d, files in os.walk(top):
        if '__pycache__' in r:
            continue
        for f in files:
            if f.endswith('.py'):
                fp = os.path.join(r, f)
                n = sum(1 for _ in open(fp, encoding='utf-8'))
                if n > 400:
                    violations.append((n, fp))
violations.sort(reverse=True)
for n, fp in violations:
    print(f'{n:5d}  {fp}')
print(f'Total: {len(violations)} files')
"
```

### C. 检查测试覆盖率

```bash
pytest --cov=. --cov-report=term-missing
```

---

**文档版本**：v1.0
**评估日期**：2026-07-12
**维护者**：云合开发团队
**关联规范**：`AGENTS.md` v2.1
