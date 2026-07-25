# frontend/src/components/news/ — 模块记忆

## 职责定位
新闻 Agent 前端展示组件：热点卡片与证据卡片，执行"不渲染未审核线索为证据"的安全红线。

## 关键文件
- `HotspotCard.tsx`：热点卡片——标题为原生 `<a target="_blank" rel="noopener noreferrer">` 直跳原文（不调用 Agent）；"AI 深度研判"为独立按钮（仅传标题等元数据，不传全文）。
- `HotspotCard.test.tsx`：测试——标题为原生 anchor、点击不触发分析、不渲染全文。
- `EvidenceCards.tsx`：证据卡片集合——只渲染 `verified`/`conflicted`（conflicted 带可见标识）；`unverified_leads` 绝不渲染 claim，仅数量提示。
- `EvidenceCards.test.tsx`：测试——verified/conflicted 渲染、冲突标识、未审核线索不呈现。

## 业务边界要点
- 热点卡片不接收/不传递新闻全文（content 字段）。
- 未审核来源线索不得进入正式证据展示（对应产品设计基线第 5 节）。
