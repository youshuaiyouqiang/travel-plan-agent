# tests/ — 模块记忆

## 职责定位
自动化测试根目录，按单元/集成/端到端三层组织；是"每个行为变更先写失败测试"（TDD）规范的落地。

## 子目录
- `unit/`：31 个单元测试（领域逻辑与工具，全部 fake/stub，不触真实网络）。
- `integration/`：22 个集成测试（API、授权、迁移、新闻证据、行程存档等关键边界）。
- `e2e/`：端到端层，**当前为空**（覆盖缺口）。

## 运行命令
```powershell
python -m pytest --cov=api --cov=application --cov=domain --cov=infrastructure --cov-fail-under=70
```

## 业务边界要点
- 认证、授权、迁移、新闻证据、行程存档必须有集成测试（AGENTS.md 第 6 节）。
- 禁止 skip、降覆盖率、continue-on-error 等绕过失败的手段。
- 覆盖率门槛 70%，CI 阻断式执行。
