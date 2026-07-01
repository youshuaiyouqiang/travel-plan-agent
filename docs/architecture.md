# Claw项目DDD架构说明

> **架构模式**: 领域驱动设计(DDD)
> **分层架构**: Domain + Infrastructure + API + Application + Config
> **完成时间**: 2026-06-30
> **版本**: v2.0-DDD架构

---

## 一、架构概览

Claw项目采用**领域驱动设计(DDD)**分层架构,将复杂业务逻辑与技术实现解耦,实现高可维护性和高可扩展性。

### 核心设计原则:

1. **领域层(Domain)优先**: 核心业务逻辑独立,不依赖技术实现
2. **基础设施层(Infrastructure)支撑**: 技术实现服务于业务
3. **API层对外**: 对外接口统一管理
4. **应用层(Application)编排**: 组装各层实现业务场景
5. **配置层(Config)独立**: 配置管理集中化

---

## 二、分层架构详解

### 1. Domain层(领域层) - 核心业务逻辑

**目录结构**:
```
domain/
├── agent/           # 智能体领域(多Agent架构)
│   ├── orchestrator.py   # 总调度(LLM路由)
│   ├── travel_agent.py   # 旅行智能体包装
│   ├── dynamic_agent.py  # 动态智能体(配置驱动)
│   ├── factory.py        # 工厂模式
│   ├── repository.py     # 智能体存储
│   ├── schema.py         # 配置模型
│   ├── base.py           # 基类
│   └── travel_core.py    # Agent主循环
│
├── travel/          # 旅行业务(intent+itinerary+album聚合)
│   ├── intent/          # 旅行意图识别
│   ├── itinerary/       # 行程管理
│   ├── album/           # 相册管理
│   └── tools/           # 旅行工具
│
├── memory/          # 记忆系统(双层记忆)
│   ├── manager.py       # 记忆管理
│   ├── extractor.py     # 记忆提取
│   └ distiller.py       # 记忆蒸馏
│
├── reasoning/       # 推理引擎(ReAct)
│   ├── engine.py        # 推理引擎
│   ├── prompting.py     # Prompt构建
│   ├── context.py       # Prompt上下文
│   └ context_manager.py # 上下文管理
│
├── user/            # 用户领域(auth+profile+emotion+session聚合)
│   ├── auth/           # 用户认证
│   ├── profile/        # 用户画像
│   ├── emotion/        # 情感检测
│   └ session/          # 会话管理
│
└── shared/          # 共享组件
    ├── audit/          # 审计日志
    ├── metrics/        # 监控指标
    └ runtime/          # 运行时组件
```

**核心职责**:
- 定义核心业务实体和领域服务
- 不依赖任何技术实现细节
- 可独立测试和验证
- 封装业务规则和约束

---

### 2. Infrastructure层(基础设施层) - 技术实现

**目录结构**:
```
infrastructure/
├── tools/           # 工具适配器
│   ├── registry.py      # 工具注册表
│   ├── executor.py      # 工具执行器
│   ├── policy.py        # 工具策略
│   ├── catalog.py       # 工具目录
│   ├── base.py          # 工具基类
│   └ adapters/          # 具体工具实现
│       ├── amap.py         # 高德地图
│       ├── fliggy.py        # 飞猪旅行
│       ├── http.py          # HTTP工具
│       └ interaction.py    # 交互工具
│
├── skills/          # 技能定义
│   ├── provider.py      # Skill提供者
│   └ builtin/           # 内置技能
│       ├── amap-maps/
│       ├── fliggy-travel/
│       └ zhangxuefeng-skill-main/
│
├── llm/             # LLM适配器
│   └ openai.py          # OpenAI客户端
│
├── persistence/     # 数据持久化
│   ├── database.py      # SQLite数据库
│   └ health.py          # 健康检查
│
└── external/        # 外部服务集成
    └ mcp/              # MCP工具代理
        ├── servers/      # MCP服务器配置
        ├── runtime.py    # MCP运行时
        ├── catalog.py    # MCP目录
```

**核心职责**:
- 实现技术细节(数据库/API/工具)
- 为domain层提供基础设施支撑
- 不包含业务逻辑
- 可替换实现(如更换数据库)

---

### 3. API层(API层) - 对外接口

**目录结构**:
```
api/
├── server.py        # FastAPI主入口(组装路由)
├── middleware/      # 中间件
│   ├── auth.py         # 认证中间件
│   ├── rate_limit.py   # 速率限制(可选)
├── routes/          # 路由模块(待拆分)
│   ├── chat.py         # Chat接口
│   ├── agents.py       # Agents接口
│   ├── skills.py       # Skills接口
│   ├── auth.py         # Auth接口
│   ├── itinerary.py    # Itinerary接口
│   ├── album.py        # Album接口
│   ├── memory.py       # Memory接口
│   ├── shared.py       # Shared接口
│   ├── trending.py     # Trending接口
│   ├── health.py       # Health接口
│   └ static.py         # 静态文件接口
└── intl_coords.py   # 国际坐标转换
```

**核心职责**:
- 对外暴露HTTP接口
- 处理请求/响应转换
- 调用domain层业务逻辑
- 不包含业务逻辑

---

### 4. Application层(应用层) - 业务编排

**目录结构**:
```
application/
├── builtin_agents/  # 内置智能体配置
│   ├── travel.yaml     # 旅行智能体配置
│   ├── loader.py       # 配置加载器
│
├── trending/        # 热门推荐管理
│   ├── manager.py      # 推荐管理
│
└── cli/             # 命令行工具
    ├── main.py         # CLI入口
```

**核心职责**:
- 组装domain和infrastructure层
- 实现完整业务场景
- 配置管理(YAML配置)
- 不包含核心业务逻辑

---

### 5. Config层(配置层) - 配置管理

**目录结构**:
```
config/
├── settings.py      # 配置管理(原config.py)
├── .env.example     # 环境变量模板
└── __init__.py      # 导出settings
```

**核心职责**:
- 集中管理配置
- 环境变量管理
- 配置验证
- 配置加载

---

## 三、依赖关系图

```
┌─────────────────────────────────────┐
│         API层(api/server.py)         │
│   - 对外接口                          │
│   - 调用domain+infrastructure         │
└──────────────────┬──────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
┌───────▼────────┐   ┌────────▼─────────┐
│  Domain层       │   │ Infrastructure层 │
│  - 核心业务     │◄──│  - 技术实现       │
│  - 独立可测试   │   │  - 工具/LLM/DB    │
└────────────────┘   └──────────────────┘
        │                     │
        └──────────┬──────────┘
                   │
          ┌────────▼─────────┐
          │ Application层     │
          │  - 业务编排       │
          │  - 配置管理       │
          └──────────────────┘
                   │
          ┌────────▼─────────┐
          │   Config层        │
          │  - 配置管理       │
          └──────────────────┘
```

---

## 四、跨层引用规则

### 允许的引用:
- ✅ **domain → infrastructure**: 业务逻辑使用技术实现
- ✅ **api → domain**: API调用业务逻辑
- ✅ **api → infrastructure**: API使用技术组件
- ✅ **application → domain**: 应用层编排业务
- ✅ **application → infrastructure**: 应用层使用技术
- ✅ **application → config**: 应用层读取配置

### 禁止的引用:
- ❌ **infrastructure → domain**: 技术不应依赖业务
- ❌ **domain → api**: 业务不应依赖API
- ❌ **domain → application**: 业务不应依赖应用层
- ❌ **domain → config**: 业务不应直接依赖配置(通过参数传递)

---

## 五、关键设计模式

### 1. 多Agent架构(Domain层)

**设计**: OrchestratorAgent(总调度) + TravelAgent/DynamicAgent(专业智能体)

**策略**:
- OrchestratorAgent使用LLM判断用户意图
- 路由到合适的专业智能体
- 支持配置驱动的动态智能体

**优势**:
- 解耦路由逻辑
- 易于扩展新智能体
- 统一对话入口

---

### 2. ReAct推理引擎(Domain层)

**设计**: Reason-Act-Observe循环

**流程**:
```
用户消息 → 意图识别 → ReAct循环 → 工具调用 → 观察结果 → 生成回复
```

**优势**:
- 自动化推理决策
- 支持多轮工具调用
- 流式输出推理过程

---

### 3. 双层记忆系统(Domain层)

**设计**: 短期记忆 → 长期记忆(蒸馏机制)

**流程**:
```
对话 → 提取记忆(短期) → 蒸馏记忆(长期) → 持久化存储
```

**优势**:
- 自动提取用户偏好
- 长期记忆跨会话有效
- 减少冗余信息

---

### 4. 工具适配器模式(Infrastructure层)

**设计**: 工具注册表 + 工具执行器 + 工具策略

**优势**:
- 统一工具接口
- 动态加载工具
- 权限控制策略

---

### 5. 配置驱动(Domain层+Application层)

**设计**: YAML配置 + 配置加载器

**优势**:
- 新增智能体只需YAML配置
- 零代码改动
- 支持自定义智能体

---

## 六、迁移成果总结

### 文件迁移统计:

| Phase | 层 | 文件数 | Import更新 |
|-------|---|--------|-----------|
| Phase 1 | 目录创建 | 20+目录 | - |
| Phase 2 | Domain层 | 40+文件 | ~60处 |
| Phase 3 | Infrastructure层 | 20+文件 | ~41处 |
| Phase 4 | API层中间件 | 2文件 | - |
| Phase 5 | Application层 | 4文件 | - |
| Phase 6 | Config层 | 2文件 | - |
| **总计** | **全项目** | **70+文件** | **~101处** |

---

## 七、后续优化建议

### 1. API层拆分(Phase 4-1待执行):
- server.py拆分到routes/*.py(43接口)
- 提取更多中间件

### 2. 依赖注入:
- 引入DI容器
- 解耦组装逻辑

### 3. 接口抽象:
- 为关键领域定义接口协议
- 支持多种实现

### 4. 领域事件:
- 引入EventBus
- 解耦领域间通信

### 5. Repository模式:
- 统一数据访问接口
- 支持多种数据源

---

## 八、文档索引

### 架构文档:
- docs/architecture.md - 本文档
- docs/overview.md - 项目概览

### 模块文档(docs/modules/):
- agent.md - Agent领域文档
- travel.md - Travel领域文档
- memory.md - Memory领域文档
- reasoning.md - Reasoning领域文档
- user.md - User领域文档
- shared.md - Shared领域文档
- tools.md - Infrastructure工具文档
- llm.md - Infrastructure LLM文档
- persistence.md - Infrastructure持久化文档

### 开发文档:
- docs/development/multi_agent.md - 多智能体开发文档
- docs/api/README.md - API文档

---

**生成时间**: 2026-06-30
**架构版本**: v2.0-DDD架构
**完成状态**: Phase 1-7完成 ✅(server.py拆分待Phase 4-1手动执行)