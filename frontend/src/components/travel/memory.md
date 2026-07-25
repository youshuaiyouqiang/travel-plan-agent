# frontend/src/components/travel/ — 模块记忆

## 职责定位
旅行草稿编辑态 UI，对应"草稿 → 确认存档"业务流程。

## 关键文件
- `DraftEditor.tsx`：草稿编辑器——按天/活动列出可编辑项，标注手工调整字段（manual_edit_fields），暴露"更新信息"/"确认行程"动作。
- `DraftEditor.test.tsx`：测试——保存后活动标记"已手动调整"。
- `RefreshChangesDialog.tsx`：刷新变更对话框（占位实现），列出外部变更供勾选应用。

## 业务边界要点
- 手工编辑字段标记 `manual`，Agent 提议不可覆盖。
- 确认后跳转不可变存档；外部信息仅在用户点击"更新信息"时查询，未勾选变更不写入草稿。
- 不含打卡/花费/相册（禁恢复清单）。
