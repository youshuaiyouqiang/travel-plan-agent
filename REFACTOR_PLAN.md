# Claw 项目重构计划 - DDD分层架构迁移

> **目标**: 将现有混合结构迁移到清晰的领域驱动设计(DDD)分层架构
> **时间**: 2026-06-30
> **影响范围**: 后端Python代码 + import路径 + 测试 + 文档

---

## 一、架构对比

### 当前结构(混乱)

```
core/                   # 包含所有业务逻辑,职责不清
  ├── agent.py         # 单Agent主循环
  ├── agents/          # 多Agent架构(新增)
  ├── intent/          # 旅行意图
  ├── itinerary/       # 行程管理
  ├── album/           # 相册管理
  ├── memory*.py       # 记忆系统(分散文件)
  ├── reasoning.py     # 推理引擎
  ├── auth/profile/    # 用户相关(分散)
tools/                  # 工具层(与skills重叠)
agents/builtin/         # YAML配置(与core/agents重复)
```

### 目标结构(清晰分层)

```
domain/                 # 【领域层】核心业务逻辑
  ├── agent/           # 智能体领域(统一管理)
  ├── travel/          # 旅行领域(intent+itinerary+album聚合)
  ├── reasoning/       # 推理领域
  ├── memory/          # 记忆领域
  ├── user/            # 用户领域(auth+profile+emotion+session聚合)
  └── shared/          # 共享领域(audit+metrics)

infrastructure/         # 【基础设施层】技术实现
  ├── tools/           # 工具适配器
  ├── skills/          # 技能定义
  ├── llm/             # LLM适配器
  ├── persistence/     # 数据持久化
  └── external/        # 外部服务集成

api/                    # 【API层】对外接口(拆分路由)
application/            # 【应用层】编排与配置
```

---

## 二、文件迁移清单

### 2.1 领域层(domain/)

#### agent领域

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `core/agents/orchestrator.py` | `domain/agent/orchestrator.py` | 总调度 |
| `core/agents/travel_agent.py` | `domain/agent/travel_agent.py` | 旅行智能体 |
| `core/agents/runtime.py` | `domain/agent/dynamic_agent.py` | 动态智能体(改名) |
| `core/agents/factory.py` | `domain/agent/factory.py` | 工厂 |
| `core/agents/repository.py` | `domain/agent/repository.py` | 智能体存储 |
| `core/agents/schema.py` | `domain/agent/schema.py` | 配置模型 |
| `core/agents/builtin_loader.py` | `application/builtin_agents/loader.py` | 配置加载(移到应用层) |
| `core/base_agent.py` | `domain/agent/base.py` | 基类 |
| `core/agent.py` | `domain/agent/travel_core.py` | 原Agent主循环(保留) |

#### travel领域(合并intent+itinerary+album)

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `core/intent/` | `domain/travel/intent/` | 旅行意图识别 |
| `core/itinerary/` | `domain/travel/itinerary/` | 行程管理 |
| `core/album/` | `domain/travel/album/` | 相册管理 |
| `tools/travel.py` | `domain/travel/tools/travel_tools.py` | 旅行工具(移入领域) |

#### reasoning领域

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `core/reasoning.py` | `domain/reasoning/engine.py` | 推理引擎(改名) |
| `core/prompting.py` | `domain/reasoning/prompting.py` | Prompt构建 |
| `core/prompt_context.py` | `domain/reasoning/context.py` | Prompt上下文(改名) |
| `core/contxt_manager.py` | `domain/reasoning/context_manager.py` | 上下文管理(改名) |

#### memory领域

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `core/memory.py` | `domain/memory/manager.py` | 记忆管理 |
| `core/memory_extractor.py` | `domain/memory/extractor.py` | 记忆提取 |
| `core/memory_distiller.py` | `domain/memory/distiller.py` | 记忆蒸馏 |

#### user领域(合并auth+profile+emotion+session)

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `core/auth.py` | `domain/user/auth/manager.py` | 用户认证 |
| `core/token.py` | `domain/user/auth/token.py` | Token管理 |
| `core/profile/` | `domain/user/profile/` | 用户画像 |
| `core/emotion/` | `domain/user/emotion/` | 情感检测 |
| `core/session.py` | `domain/user/session/manager.py` | 会话管理 |
| `core/task_state.py` | `domain/user/session/task_state.py` | 任务状态 |

#### shared领域(合并audit+metrics+runtime)

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `core/audit/` | `domain/shared/audit/` | 审计日志 |
| `core/metrics/` | `domain/shared/metrics/` | 监控指标 |
| `core/runtime_facts.py` | `domain/shared/runtime/facts.py` | 运行时事实 |
| `core/trace.py` | `domain/shared/runtime/trace.py` | 运行追踪 |
| `core/logging_config.py` | `domain/shared/runtime/logging.py` | 日志配置 |
| `core/types.py` | `domain/shared/types.py` | 共享类型 |

---

### 2.2 基础设施层(infrastructure/)

#### tools适配器

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `tools/registry.py` | `infrastructure/tools/registry.py` | 工具注册表 |
| `tools/executor.py` | `infrastructure/tools/executor.py` | 工具执行器 |
| `tools/policy.py` | `infrastructure/tools/policy.py` | 工具策略 |
| `tools/catalog.py` | `infrastructure/tools/catalog.py` | 工具目录 |
| `tools/base.py` | `infrastructure/tools/base.py` | 工具基类 |
| `tools/amap.py` | `infrastructure/tools/adapters/amap.py` | 高德适配器(移入adapters子目录) |
| `tools/fliggy.py` | `infrastructure/tools/adapters/fliggy.py` | 飞猪适配器 |
| `tools/http.py` | `infrastructure/tools/adapters/http.py` | HTTP工具 |
| `tools/interaction.py` | `infrastructure/tools/adapters/interaction.py` | 交互工具 |
| `tools/mcp.py` | `infrastructure/external/mcp/runtime.py` | MCP代理(移入external) |

#### skills定义

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `skills/` | `infrastructure/skills/builtin/` | 内置技能定义(移入子目录) |
| `core/skills/provider.py` | `infrastructure/skills/provider.py` | Skill提供者 |

#### LLM适配器

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `core/llm.py` | `infrastructure/llm/openai.py` | OpenAI客户端 |

#### 持久化

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `infra/db.py` | `infrastructure/persistence/database.py` | SQLite数据库 |
| `infra/health.py` | `infrastructure/persistence/health.py` | 健康检查 |

#### 外部服务

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `mcps/` | `infrastructure/external/mcp/servers/` | MCP服务器配置 |
| `core/mcp_catalog.py` | `infrastructure/external/mcp/catalog.py` | MCP目录 |

---

### 2.3 API层(api/)

#### 路由拆分(拆分server.py 43个接口)

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `api/server.py` | `api/server.py` | FastAPI主入口(仅组装路由) |
| - | `api/routes/chat.py` | 对话接口(/api/chat, /api/chat/stream) |
| - | `api/routes/agents.py` | 智能体接口(/api/agents) |
| - | `api/routes/skills.py` | 技能接口(/api/skills) |
| - | `api/routes/auth.py` | 认证接口(/api/auth) |
| - | `api/routes/itinerary.py` | 行程接口(/api/itinerary) |
| - | `api/routes/album.py` | 相册接口(/api/album) |
| - | `api/routes/memory.py` | 记忆接口(/api/memory) |
| - | `api/routes/shared.py` | 分享接口(/api/shared) |
| - | `api/routes/trending.py` | 热门推荐(/api/trending) |
| - | `api/middleware/auth.py` | 认证中间件(提取) |
| - | `api/middleware/rate_limit.py` | 速率限制中间件(提取) |
| `api/intl_coords.py` | `api/routes/intl_coords.py` | 国际坐标(保留) |

---

### 2.4 应用层(application/)

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `app.py` | `application/main.py` | 应用组装入口 |
| `agents/builtin/travel.yaml` | `application/builtin_agents/travel.yaml` | 内置智能体配置 |
| `core/agents/builtin_loader.py` | `application/builtin_agents/loader.py` | 配置加载器 |
| `core/trending.py` | `application/trending/manager.py` | 热门推荐(移入应用层) |
| `main.py` | `application/cli/main.py` | CLI入口 |

---

### 2.5 配置层(config/)

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `config.py` | `config/settings.py` | 配置管理(移入config目录) |
| `.env.example` | `config/.env.example` | 环境变量模板 |

---

### 2.6 文档层(docs/)

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| - | `docs/architecture.md` | 整体架构说明(新增) |
| `docs/README.md` | `docs/overview.md` | 项目概览 |
| `docs/MULTI_AGENT_DEV.md` | `docs/development/multi_agent.md` | 多智能体开发文档 |
| `docs/API.md` | `docs/api/README.md` | API文档 |
| - | `docs/modules/agent.md` | Agent模块文档(新增) |
| - | `docs/modules/travel.md` | Travel模块文档(新增) |
| - | `docs/modules/memory.md` | Memory模块文档(新增) |

---

### 2.7 测试层(tests/)

| 原路径 | 新路径 | 说明 |
|-------|--------|------|
| `tests/test_agent*.py` | `tests/domain/agent/` | Agent领域测试 |
| `tests/test_memory*.py` | `tests/domain/memory/` | Memory领域测试 |
| `tests/test_reasoning.py` | `tests/domain/reasoning/` | Reasoning领域测试 |
| `tests/test_itinerary.py` | `tests/domain/travel/` | Travel领域测试 |
| `tests/test_tools*.py` | `tests/infrastructure/tools/` | Tools基础设施测试 |
| `tests/test_mcp*.py` | `tests/infrastructure/external/` | External基础设施测试 |
| `tests/test_api.py` | `tests/api/` | API层测试 |

---

## 三、Import路径更新规则

### 3.1 领域层引用规则

```python
# 原import
from core.agent import Agent
from core.memory import MemoryManager
from core.reasoning import ReasoningEngine

# 新import
from domain.agent.travel_core import Agent
from domain.memory.manager import MemoryManager
from domain.reasoning.engine import ReasoningEngine
```

### 3.2 基础设施层引用规则

```python
# 原import
from tools.executor import ToolExecutor
from core.llm import OpenAILLM
from infra.db import get_connection

# 新import
from infrastructure.tools.executor import ToolExecutor
from infrastructure.llm.openai import OpenAILLM
from infrastructure.persistence.database import get_connection
```

### 3.3 跨层引用规则

- **domain → infrastructure**: 允许(domain依赖基础设施实现)
- **domain → domain**: 允许(领域间依赖)
- **infrastructure → domain**: ❌禁止(基础设施不应依赖领域)
- **api → domain**: 允许(API调用领域逻辑)
- **api → infrastructure**: 允许(API调用基础设施)
- **application → domain/infrastructure**: 允许(应用层组装所有层)

---

## 四、迁移脚本示例

### 4.1 目录创建脚本

```bash
#!/bin/bash
# create_dirs.sh

# 创建DDD分层目录
mkdir -p domain/{agent,travel,reasoning,memory,user,shared}
mkdir -p domain/travel/{intent,itinerary,album,tools}
mkdir -p domain/user/{auth,profile,emotion,session}
mkdir -p domain/shared/{audit,metrics,runtime}

mkdir -p infrastructure/{tools,skills,llm,persistence,external}
mkdir -p infrastructure/tools/adapters
mkdir -p infrastructure/external/mcp/servers

mkdir -p api/{routes,middleware}
mkdir -p application/{builtin_agents,cli,trending}
mkdir -p config
mkdir -p docs/{modules,api,development}
mkdir -p tests/{domain,infrastructure,api}
```

### 4.2 文件迁移脚本

```bash
#!/bin/bash
# move_files.sh

# Agent领域迁移
mv core/agents/orchestrator.py domain/agent/
mv core/agents/travel_agent.py domain/agent/
mv core/agents/runtime.py domain/agent/dynamic_agent.py
mv core/agents/factory.py domain/agent/
mv core/agents/repository.py domain/agent/
mv core/agents/schema.py domain/agent/
mv core/base_agent.py domain/agent/base.py
mv core/agent.py domain/agent/travel_core.py

# Travel领域迁移
mv core/intent/* domain/travel/intent/
mv core/itinerary/* domain/travel/itinerary/
mv core/album/* domain/travel/album/
mv tools/travel.py domain/travel/tools/travel_tools.py

# Reasoning领域迁移
mv core/reasoning.py domain/reasoning/engine.py
mv core/prompting.py domain/reasoning/
mv core/prompt_context.py domain/reasoning/context.py
mv core/contxt_manager.py domain/reasoning/context_manager.py

# Memory领域迁移
mv core/memory.py domain/memory/manager.py
mv core/memory_extractor.py domain/memory/extractor.py
mv core/memory_distiller.py domain/memory/distiller.py

# User领域迁移
mv core/auth.py domain/user/auth/manager.py
mv core/token.py domain/user/auth/
mv core/profile/* domain/user/profile/
mv core/emotion/* domain/user/emotion/
mv core/session.py domain/user/session/manager.py
mv core/task_state.py domain/user/session/

# Shared领域迁移
mv core/audit/* domain/shared/audit/
mv core/metrics/* domain/shared/metrics/
mv core/runtime_facts.py domain/shared/runtime/facts.py
mv core/trace.py domain/shared/runtime/
mv core/logging_config.py domain/shared/runtime/logging.py
mv core/types.py domain/shared/

# 基础设施层迁移
mv tools/registry.py infrastructure/tools/
mv tools/executor.py infrastructure/tools/
mv tools/policy.py infrastructure/tools/
mv tools/catalog.py infrastructure/tools/
mv tools/base.py infrastructure/tools/
mv tools/amap.py infrastructure/tools/adapters/
mv tools/fliggy.py infrastructure/tools/adapters/
mv tools/http.py infrastructure/tools/adapters/
mv tools/interaction.py infrastructure/tools/adapters/
mv tools/mcp.py infrastructure/external/mcp/runtime.py

mv skills/* infrastructure/skills/builtin/
mv core/skills/provider.py infrastructure/skills/

mv core/llm.py infrastructure/llm/openai.py
mv infra/db.py infrastructure/persistence/database.py
mv infra/health.py infrastructure/persistence/
mv mcps/* infrastructure/external/mcp/servers/
mv core/mcp_catalog.py infrastructure/external/mcp/

# 应用层迁移
mv app.py application/main.py
mv agents/builtin/travel.yaml application/builtin_agents/
mv core/agents/builtin_loader.py application/builtin_agents/loader.py
mv core/trending.py application/trending/manager.py
mv main.py application/cli/

# 配置迁移
mv config.py config/settings.py
mv .env.example config/

# 文档迁移
mv docs/MULTI_AGENT_DEV.md docs/development/multi_agent.md
mv docs/API.md docs/api/README.md
mv docs/README.md docs/overview.md
```

---

## 五、风险与注意事项

### 5.1 高风险点

1. **Import路径断裂**: 需全局搜索并更新所有import语句
2. **循环依赖**: 部分模块可能存在隐藏的循环引用
3. **测试失效**: 测试import路径需同步更新
4. **API兼容性**: 外部API调用可能受影响(如`/api/agents`)

### 5.2 安全措施

1. **先备份**: 执行前备份整个项目
2. **分阶段迁移**: 按领域逐个迁移,每阶段验证
3. **自动化测试**: 每阶段运行测试确保功能正常
4. **兼容性保持**: 保留旧路径别名(过渡期)

### 5.3 迁移顺序(推荐)

```
Phase 1: 创建新目录结构(不影响现有代码)
  └─ 执行 create_dirs.sh
  └─ 验证: 目录树正确

Phase 2: 迁移domain层(核心业务)
  └─ 2.1: domain/agent (优先,多Agent核心)
  └─ 2.2: domain/travel (旅行业务)
  └─ 2.3: domain/memory (记忆系统)
  └─ 2.4: domain/reasoning (推理引擎)
  └─ 2.5: domain/user (用户相关)
  └─ 2.6: domain/shared (共享组件)
  └─ 每阶段验证: 运行领域单元测试

Phase 3: 迁移infrastructure层(基础设施)
  └─ 3.1: infrastructure/tools
  └─ 3.2: infrastructure/llm
  └─ 3.3: infrastructure/persistence
  └─ 3.4: infrastructure/external
  └─ 验证: 运行工具测试

Phase 4: 迁移api层(拆分路由)
  └─ 4.1: 提取中间件
  └─ 4.2: 拆分路由
  └─ 4.3: 更新server.py(组装)
  └─ 验证: 运行API测试 + 手动测试接口

Phase 5: 迁移application层(组装)
  └─ 5.1: 更新app.py → application/main.py
  └─ 5.2: 迁移内置配置
  └─ 验证: 启动后端,运行全链路测试

Phase 6: 更新文档和测试
  └─ 6.1: 更新import路径文档
  └─ 6.2: 迁移测试文件
  └─ 6.3: 补充架构文档
  └─ 验证: 所有测试通过

Phase 7: 清理旧目录
  └─ 7.1: 删除空的旧目录
  └─ 7.2: 更新.gitignore
  └─ 验证: 项目启动正常
```

---

## 六、验收清单

### 阶段验收标准

- [ ] **Phase 1**: 新目录结构创建完成,不影响现有代码
- [ ] **Phase 2**: Domain层迁移完成,领域单元测试通过
- [ ] **Phase 3**: Infrastructure层迁移完成,工具测试通过
- [ ] **Phase 4**: API层拆分完成,接口测试通过
- [ ] **Phase 5**: Application层迁移完成,全链路测试通过
- [ ] **Phase 6**: 文档和测试更新完成,所有测试通过
- [ ] **Phase 7**: 旧目录清理完成,项目正常运行

### 最终验收标准

- [ ] 所有Python文件import路径更新正确
- [ ] 所有测试文件import路径更新正确
- [ ] 后端服务启动正常
- [ ] 所有API接口测试通过
- [ ] 前端调用后端正常
- [ ] 文档更新完整(架构文档 + API文档)
- [ ] 无遗留旧路径引用
- [ ] 目录结构符合DDD分层架构

---

## 七、预计影响范围

### 文件数量统计

| 层 | 文件数 | 迁移难度 |
|----|--------|----------|
| domain | 45+ | 高(核心业务) |
| infrastructure | 20+ | 中(技术实现) |
| api | 1 → 10+ | 中(拆分路由) |
| application | 5+ | 低(组装逻辑) |
| tests | 17 | 中(同步更新) |
| docs | 6+ | 低(文档补充) |
| **总计** | **90+** | **高** |

### 时间预估

- **Phase 1-2**: 2-3小时(domain迁移+验证)
- **Phase 3**: 1-2小时(infrastructure迁移)
- **Phase 4**: 2-3小时(API拆分+验证)
- **Phase 5**: 1小时(application迁移)
- **Phase 6**: 2小时(文档+测试更新)
- **Phase 7**: 1小时(清理+最终验证)
- **总计**: 8-12小时

---

## 八、后续优化建议

迁移完成后可进一步优化:

1. **依赖注入**: 引入DI容器,解耦组装逻辑
2. **接口抽象**: 为关键领域定义接口协议
3. **领域事件**: 引入EventBus,解耦领域间通信
4. **Repository模式**: 统一数据访问接口
5. **测试金字塔**: 补充集成测试/E2E测试

---

**生成时间**: 2026-06-30
**文档版本**: v1.0
**下次更新**: 迁移执行后补充实际遇到的问题