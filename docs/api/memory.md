# docs/api/ — 模块记忆

## 职责定位
历史 API 文档与旧改造计划。**按 AGENTS.md 规定：只作风险参考，不得作为业务范围或实现方案的依据。**

## 文件
- `API.md`（50KB）：60 个接口的旧版完整文档（含 TS 类型、SSE 示例、错误码）——部分接口/字段已随重构变化，使用前需与 `api/v1/` 实际代码核对。
- `ARCHITECTURE_IMPROVEMENT.md`（35KB）：历史架构改进文档。
- `REFACTOR_EXECUTION_PLAN.md`（45KB）：历史重构执行计划（已被 superpowers/plans 取代）。

## 业务边界要点
- 涉及相册、情感识别、多方案比较、打卡花费等内容均已在产品基线中删除，勿据此实现。
