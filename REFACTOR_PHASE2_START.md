# Phase 2 启动提醒 - Domain层迁移开始

> **启动时间**: 2026-06-30 22:17
> **状态**: ⚠️ 即将执行文件迁移
> **风险**: 中(需更新import路径,可能影响现有代码)

---

## ⚠️ 重要提醒

### 执行前必做:

1. **✅ Git提交**: 建议先提交Phase 1成果,创建备份分支
2. **⚠️ IDE缓存清理**: PyCharm/VSCode需清理缓存避免旧路径干扰
3. **⚠️ 测试备份**: 记录当前测试状态,迁移后对比验证

### 迁移策略:

- **渐进式执行**: 每迁移一个领域立即验证,发现问题立即回滚
- **import更新同步**: 文件迁移后立即更新所有引用路径
- **测试驱动**: 每领域迁移后运行对应测试确保功能正常

---

## Phase 2 执行计划

### 优先级顺序(从最独立到最依赖):

#### 1. domain/agent(优先,相对独立)

**迁移文件**:
- `core/agents/orchestrator.py` → `domain/agent/orchestrator.py`
- `core/agents/travel_agent.py` → `domain/agent/travel_agent.py`
- `core/agents/runtime.py` → `domain/agent/dynamic_agent.py` (改名)
- `core/agents/factory.py` → `domain/agent/factory.py`
- `core/agents/repository.py` → `domain/agent/repository.py`
- `core/agents/schema.py` → `domain/agent/schema.py`
- `core/base_agent.py` → `domain/agent/base.py`
- `core/agent.py` → `domain/agent/travel_core.py` (保留旧Agent主循环)

**预计影响**:
- 影响文件: app.py, api/server.py, tests/test_agent*.py
- import更新: ~15处

**验收标准**:
- 所有agent文件迁移完成
- import路径更新正确
- Agent创建/路由功能正常

#### 2. domain/shared(被其他领域依赖)

**迁移文件**:
- `core/audit/*` → `domain/shared/audit/*`
- `core/metrics/*` → `domain/shared/metrics/*`
- `core/runtime_facts.py` → `domain/shared/runtime/facts.py`
- `core/trace.py` → `domain/shared/runtime/trace.py`
- `core/logging_config.py` → `domain/shared/runtime/logging.py`
- `core/types.py` → `domain/shared/types.py`

**预计影响**:
- 影响文件: 所有domain层文件(共享组件)
- import更新: ~30处

**验收标准**:
- 共享组件迁移完成
- audit/metrics功能正常

#### 3. domain/memory

**迁移文件**:
- `core/memory.py` → `domain/memory/manager.py`
- `core/memory_extractor.py` → `domain/memory/extractor.py`
- `core/memory_distiller.py` → `domain/memory/distiller.py`

**预计影响**:
- 影响文件: domain/agent/travel_core.py, domain/reasoning/*
- import更新: ~10处

**验收标准**:
- 记忆系统迁移完成
- 记忆提取/蒸馏功能正常

#### 4. domain/reasoning

**迁移文件**:
- `core/reasoning.py` → `domain/reasoning/engine.py`
- `core/prompting.py` → `domain/reasoning/prompting.py`
- `core/prompt_context.py` → `domain/reasoning/context.py`
- `core/contxt_manager.py` → `domain/reasoning/context_manager.py`

**预计影响**:
- 影响文件: domain/agent/travel_core.py
- import更新: ~8处

**验收标准**:
- 推理引擎迁移完成
- ReAct循环功能正常

#### 5. domain/travel(大领域,最后迁移)

**迁移文件**:
- `core/intent/*` → `domain/travel/intent/*`
- `core/itinerary/*` → `domain/travel/itinerary/*`
- `core/album/*` → `domain/travel/album/*`
- `tools/travel.py` → `domain/travel/tools/travel_tools.py`

**预计影响**:
- 影响文件: api/server.py(行程接口), domain/agent/travel_core.py
- import更新: ~20处

**验收标准**:
- 旅行业务迁移完成
- 行程生成/查询功能正常

#### 6. domain/user(大领域,最后迁移)

**迁移文件**:
- `core/auth.py` → `domain/user/auth/manager.py`
- `core/token.py` → `domain/user/auth/token.py`
- `core/profile/*` → `domain/user/profile/*`
- `core/emotion/*` → `domain/user/emotion/*`
- `core/session.py` → `domain/user/session/manager.py`
- `core/task_state.py` → `domain/user/session/task_state.py`

**预计影响**:
- 影响文件: api/server.py(认证接口), domain/agent/travel_core.py
- import更新: ~15处

**验收标准**:
- 用户领域迁移完成
- 认证/会话功能正常

---

## 风险控制措施

### 每领域迁移后立即验证:

1. **文件迁移**: 移动文件到新位置
2. **import更新**: 全局搜索替换旧路径
3. **运行测试**: `pytest tests/test_<domain>.py`
4. **手动验证**: 启动后端测试关键接口
5. **记录状态**: 记录迁移前后对比

### 发现问题立即回滚:

- 使用Git回滚到Phase 1提交点
- 重新分析问题原因
- 调整迁移策略后再执行

---

## Import路径更新规则

### 全局搜索关键词:

```bash
# 搜索旧路径
from core.agent import
from core.agents.
from core.base_agent import
from core.memory import
from core.reasoning import
from core.intent.
from core.itinerary.
from core.album.
from core.auth import
from core.token import
from core.profile.
from core.emotion.
from core.session import
from core.audit.
from core.metrics.
from core.runtime_facts import
from core.trace import
from core.logging_config import
from core.types import
```

### 替换新路径:

```python
# Agent领域
from core.agent import Agent → from domain.agent.travel_core import Agent
from core.agents.orchestrator import → from domain.agent.orchestrator import
from core.base_agent import → from domain.agent.base import

# Memory领域
from core.memory import → from domain.memory.manager import
from core.memory_extractor import → from domain.memory.extractor import

# Reasoning领域
from core.reasoning import → from domain.reasoning.engine import
from core.prompting import → from domain.reasoning.prompting import

# Travel领域
from core.intent.travel_classifier import → from domain.travel.intent.travel_classifier import
from core.itinerary.repository import → from domain.travel.itinerary.repository import
from core.album.service import → from domain.travel.album.service import

# User领域
from core.auth import → from domain.user.auth.manager import
from core.token import → from domain.user.auth.token import
from core.profile.manager import → from domain.user.profile.manager import
from core.emotion.detector import → from domain.user.emotion.detector import
from core.session import → from domain.user.session.manager import

# Shared领域
from core.audit.logger import → from domain.shared.audit.logger import
from core.metrics.collector import → from domain.shared.metrics.collector import
from core.runtime_facts import → from domain.shared.runtime.facts import
from core.types import → from domain.shared.types import
```

---

## 预计完成时间

- **Phase 2-1(domain/agent)**: 30分钟
- **Phase 2-2(domain/shared)**: 20分钟
- **Phase 2-3(domain/memory)**: 15分钟
- **Phase 2-4(domain/reasoning)**: 15分钟
- **Phase 2-5(domain/travel)**: 30分钟
- **Phase 2-6(domain/user)**: 30分钟
- **Phase 2-7(import更新)**: 30分钟
- **Phase 2-8(测试验证)**: 30分钟

**总计**: 2.5-3小时

---

**生成时间**: 2026-06-30 22:17
**状态**: Phase 2 ⚠️ 即将启动