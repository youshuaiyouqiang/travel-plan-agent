# application/travel/ — 模块记忆

## 职责定位
旅行草稿与存档生命周期应用服务：实现"需求收集 → 当前草稿 → 调整 → 确认 → 不可变存档"闭环，草稿与存档严格分离。

## 关键文件
- `models.py`：`TravelDraft` / `TravelArchive` / `Activity` / `FieldConflict` / `ApplyProposalResult` 领域模型。
- `service.py`：`TravelService`——保存/手工编辑草稿、应用 Agent 提议（手工字段保护）、确认生成存档、从存档续编新草稿。

## 业务边界要点
- 每用户每会话仅一份当前草稿，不生成多方案对比。
- 手工编辑的字段记入 `manual_edit_fields`，Agent 提议不可覆盖，冲突记入 `FieldConflict` 返回。
- 确认后草稿转只读，二次确认抛 Conflict（409）。
- 存档不可变：`edit_archive` 永远抛 Conflict；从存档继续编辑会创建新草稿，旧存档保持不变。
- 外部信息（天气/路线）只在用户点击"更新信息"时刷新，未勾选的变更不写入草稿。
- 所有权异常统一 404。
