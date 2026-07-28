# stock-review skill

A股市场周期复盘方法论与工具集。

## 文件结构

```text
stock-review/
├── SKILL.md              # 方法论（必读）
├── agents/
│   ├── openai.yaml       # 工具清单 + display_name + i18n
│   └── memory.md         # 占位
├── scripts/
│   ├── memory.md         # 占位（工具实现待开发）
│   └── *.py              # 工具实现（待开发）
└── memory.md             # 本文件
```

## 当前状态

- ✅ 方法论（SKILL.md）已沉淀
- ✅ 工具清单（openai.yaml）已定义
- ⏳ 工具实现（scripts/*.py）待开发
- ⏳ 数据采集服务（infrastructure 层）待开发
- ⏳ 数据表（SQLite 迁移）待开发
- ⏳ stock agent yaml 待创建
- ⏳ 前端 /stock 页面待开发

## 下一步

方法论沉淀完成。下一步待与用户讨论：
- 数据表 DDL 设计
- 数据采集服务接口
- 工具实现代码结构
- stock agent yaml 配置
- 前端图表组件选型
