# Phase 3启动 - 基础设施层迁移

> **启动时间**: 2026-06-30 23:10
> **状态**: ⚠️ 即将开始基础设施层迁移
> **目标**: 将tools/skills/llm/persistence/external迁移到infrastructure层

---

## 一、Phase 3迁移范围

### infrastructure层包含:

1. **tools/** - 工具适配器
   - registry.py(工具注册表)
   - executor.py(工具执行器)
   - policy.py(工具策略)
   - catalog.py(工具目录)
   - base.py(工具基类)
   - adapters/(具体工具实现)
     - amap.py(高德地图)
     - fliggy.py(飞猪旅行)
     - http.py(HTTP工具)
     - interaction.py(交互工具)
   - travel.py(已迁移到domain/travel/tools/)

2. **skills/** - 技能定义
   - provider.py(Skill提供者)
   - builtin/(内置技能定义)
     - amap-maps/
     - fliggy-travel/

3. **llm/** - LLM适配器
   - core/llm.py → infrastructure/llm/openai.py

4. **persistence/** - 数据持久化
   - infra/db.py → infrastructure/persistence/database.py
   - infra/health.py → infrastructure/persistence/health.py

5. **external/** - 外部服务集成
   - mcps/ → infrastructure/external/mcp/servers/
   - core/mcp_catalog.py → infrastructure/external/mcp/catalog.py

---

## 二、迁移策略

### 优先级顺序:

1. **tools迁移**(优先) - 最复杂,影响面最大
2. **skills迁移** - 相对独立,影响面较小
3. **llm迁移** - 简单,但引用很多
4. **persistence迁移** - 简单,影响面中等
5. **external迁移** - 复杂,MCP集成

### 关键原则:

- **保持兼容性**: infrastructure层import路径更新后,需确保domain层能正常引用
- **批量更新**: 先迁移文件,最后统一更新import(效率更高)
- **验证驱动**: 每迁移完一个组件后立即验证

---

## 三、预计影响范围

### 文件数量:

| infrastructure组件 | 文件数 | 迁移难度 |
|-------------------|--------|----------|
| tools | 10+ | 高(引用很多) |
| skills | 5+ | 中(引用较少) |
| llm | 1 | 高(引用最多) |
| persistence | 2 | 中(引用中等) |
| external | 5+ | 中(MCP集成) |
| **总计** | **20+** | **中高** |

### Import更新预估:

| 组件 | 预估引用数 | 说明 |
|------|-----------|------|
| tools.executor | ~10 | domain.agent引用 |
| tools.registry | ~5 | domain.agent引用 |
| core.llm | ~20+ | 所有agent引用 |
| infra.db | ~10 | API层引用 |
| core.mcp_catalog | ~5 | domain.agent引用 |

---

## 四、Phase 3执行计划

### Phase 3-1: tools迁移(优先)

**迁移步骤**:
1. 移动tools目录下所有文件到infrastructure/tools/
2. 创建infrastructure/tools/adapters/子目录
3. 移动amap.py、fliggy.py等到adapters/
4. 更新所有import路径

**预计时间**: 30-45分钟

---

**生成时间**: 2026-06-30 23:10
**状态**: Phase 3 ⚠️ 即将启动