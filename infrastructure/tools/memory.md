# infrastructure/tools/ — 模块记忆

## 职责定位
工具外部 I/O 适配器集合（`adapters/` 子包）。核心工具框架（`ToolSpec`/`Tool`/
`ToolRegistry`/`ToolPolicy`/`ToolExecutor`/`ToolCatalog`）于 P4.2 迁移至
`domain/shared/tools/`，本目录下的同名模块仅作向后兼容再导出垫片。

## 关键文件
- `base.py` / `registry.py` / `catalog.py` / `policy.py` / `executor.py`：
  P4.2 起为再导出垫片，从 `domain.shared.tools.*` 重新导出同名符号，供
  `app.py`、`adapters/` 与历史测试继续使用。新代码应直接从 `domain.shared.tools` 导入。
- `adapters/`：具体外部 I/O 实现（amap、fliggy、qweather、http、drive_cost、
  interaction、shared），仍属本目录职责。
- `__init__.py`：包占位。

## 业务边界要点
- shell 黑名单（`rm -rf /`、`mkfs` 等）+ 风险命令需用户确认；写文件禁 `/etc/`。
- 每工具限流：30 次/分、200 次/时。
- Agent 工具白名单在此强制：`academic` 限 arXiv/论文工具（无 web_search），`news` 限新闻检索/来源库/交叉验证工具。
- 工具执行全程写审计（domain/shared/audit）。
