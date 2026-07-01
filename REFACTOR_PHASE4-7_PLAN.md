# Phase 4-7启动计划 - 完成DDD架构迁移的最后阶段

> **启动时间**: 2026-06-30 23:35
> **状态**: ⚠️ 即将开始最后4个阶段
> **目标**: 完成API层拆分、应用层迁移、配置整理、文档补充,实现DDD架构100%完成

---

## 一、Phase 4-7整体规划

### Phase 4: API层拆分(预计45分钟)

**目标**: 将server.py的43个接口拆分到routes/*.py,提取中间件

**拆分策略**:
1. 按业务功能分组(chat/agents/skills/auth/itinerary/album/memory/shared/trending)
2. 提取认证中间件
3. 提取速率限制中间件(可选)
4. server.py仅保留路由组装逻辑

**预计文件数**: 10+路由文件 + 2中间件文件

---

### Phase 5: 应用层迁移(预计30分钟)

**目标**: 迁移配置、CLI工具、热门推荐到application层

**迁移组件**:
1. agents/builtin/ → application/builtin_agents/ (YAML配置)
2. core/agents/builtin_loader.py → application/builtin_agents/loader.py (配置加载)
3. core/trending.py → application/trending/manager.py (热门推荐)
4. main.py → application/cli/main.py (命令行工具)

**预计文件数**: 5+配置文件 + 3Python文件

---

### Phase 6: 配置整理(预计15分钟)

**目标**: 整理配置文件到config目录

**迁移组件**:
1. config.py → config/settings.py
2. .env.example → config/.env.example
3. 创建config/__init__.py导出settings

**预计文件数**: 3文件

---

### Phase 7: 文档补充(预计20分钟)

**目标**: 补充架构文档和领域文档

**文档列表**:
1. docs/architecture.md - 整体架构说明(新增)
2. docs/modules/agent.md - Agent领域文档
3. docs/modules/travel.md - Travel领域文档
4. docs/modules/memory.md - Memory领域文档
5. docs/modules/reasoning.md - Reasoning领域文档
6. docs/modules/user.md - User领域文档
7. docs/modules/shared.md - Shared领域文档
8. docs/modules/tools.md - Infrastructure工具文档
9. docs/modules/llm.md - Infrastructure LLM文档

**预计文档数**: 9文档

---

## 二、当前项目状态

### ✅ 已完成(Phase 1-3):

- ✅ Phase 1: DDD目录结构创建(100%)
- ✅ Phase 2: Domain层迁移(40+文件,60+import) + 验证通过
- ✅ Phase 3: Infrastructure层迁移(20+文件,41+import) + import更新完成

### ⚠️ 待完成(Phase 4-7):

- ⚠️ Phase 4: API层拆分(server.py 43接口拆分)
- ⚠️ Phase 5: Application层迁移(配置/CLI/trending)
- ⚠️ Phase 6: Config配置整理
- ⚠️ Phase 7: Documentation文档补充

---

## 三、执行策略

### 高效策略:

1. **批量执行**: Phase 4-6合并执行(文件迁移为主)
2. **Import更新**: Phase 4-6完成后统一更新import
3. **文档补充**: Phase 7最后执行(手动编写文档)
4. **Git提交**: 每Phase完成后提交备份

### 验证策略:

- Phase 4验证: 启动后端测试API接口
- Phase 5验证: 测试应用层功能(配置加载/CLI)
- Phase 6验证: 测试配置导入
- Phase 7验证: 检查文档完整性

---

## 四、预计完成时间

| Phase | 预计时间 | 说明 |
|-------|---------|------|
| Phase 4 | 45分钟 | API层拆分(最复杂) |
| Phase 5 | 30分钟 | 应用层迁移(中等) |
| Phase 6 | 15分钟 | 配置整理(简单) |
| Phase 7 | 20分钟 | 文档补充(手动) |
| **总计** | **110分钟** | **约2小时** |

---

## 五、Phase 4详细规划(API层拆分)

### server.py当前状态(43接口):

**接口分类**:
1. **Chat接口**(3个): /api/chat, /api/chat/stream, /api/history
2. **Agents接口**(8个): /api/agents(GET/POST/PUT/DELETE), /api/agents/builtin, /api/agents/custom
3. **Skills接口**(3个): /api/skills, /api/skills/builtin, /api/skills/mcp
4. **Auth接口**(5个): /api/auth/signup, /api/auth/login, /api/auth/logout, /api/auth/me, /api/auth/token
5. **Itinerary接口**(8个): /api/itinerary(GET/POST/PUT/DELETE), /api/itinerary/search, /api/itinerary/:id
6. **Album接口**(4个): /api/album(GET/POST/DELETE), /api/album/:id
7. **Memory接口**(2个): /api/memory, /api/memory/:id
8. **Shared接口**(2个): /api/shared, /api/shared/:id
9. **Trending接口**(2个): /api/trending, /api/trending/refresh
10. **Health接口**(1个): /api/health
11. **静态文件接口**(3个): index.html, favicon.ico, catch-all

### 拆分方案:

```
api/routes/
├── chat.py          # Chat接口(3个)
├── agents.py        # Agents接口(8个)
├── skills.py        # Skills接口(3个)
├── auth.py          # Auth接口(5个)
├── itinerary.py     # Itinerary接口(8个)
├── album.py         # Album接口(4个)
├── memory.py        # Memory接口(2个)
├── shared.py        # Shared接口(2个)
├── trending.py      # Trending接口(2个)
├── health.py        # Health接口(1个)
└── static.py        # 静态文件接口(3个)

api/middleware/
├── auth.py          # 认证中间件(提取)
└── rate_limit.py    # 速率限制中间件(可选)
```

---

## 六、Phase 5详细规划(Application层迁移)

### 迁移清单:

```
agents/builtin/travel.yaml          → application/builtin_agents/travel.yaml
core/agents/builtin_loader.py       → application/builtin_agents/loader.py
core/trending.py                    → application/trending/manager.py
main.py                             → application/cli/main.py
app.py                              → application/main.py (改名)
```

---

## 七、Phase 6详细规划(Config配置整理)

### 迁移清单:

```
config.py                           → config/settings.py
.env.example                        → config/.env.example
```

---

## 八、Phase 7详细规划(Documentation补充)

### 文档列表:

1. **architecture.md** - 整体架构说明
   - DDD分层架构介绍
   - 各层职责说明
   - 依赖关系图
   - 目录结构说明

2. **modules/*.md** - 领域文档(9个)
   - agent.md: Agent领域说明(多Agent架构/路由策略)
   - travel.md: Travel领域说明(intent/itinerary/album聚合)
   - memory.md: Memory领域说明(双层记忆/蒸馏机制)
   - reasoning.md: Reasoning领域说明(ReAct推理引擎)
   - user.md: User领域说明(auth/profile/emotion/session聚合)
   - shared.md: Shared领域说明(audit/metrics/runtime)
   - tools.md: Infrastructure工具说明(适配器模式)
   - llm.md: Infrastructure LLM说明(OpenAI客户端)
   - persistence.md: Infrastructure持久化说明(SQLite数据库)

---

**生成时间**: 2026-06-30 23:35
**状态**: Phase 4-7 ⚠️ 即将启动