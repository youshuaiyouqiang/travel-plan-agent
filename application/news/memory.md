# application/news/ — 模块记忆

## 职责定位
新闻域应用层：来源库治理（候选评分/管理员审核）、热点缓存池、证据化研判分类。是新闻业务红线的核心执行层。

## 关键文件
- `models.py`：新闻领域模型——来源记录、审计事件、候选评分、热点条目、新闻锚点、证据卡片、研判响应。
- `source_candidate_scorer.py`：`SourceCandidateScorer`，对新发现域名做多维 0~1 建议评分（发布者类型、HTTPS、品牌一致性、主题相关性、转载率惩罚、风险信号）；AI 只建议，不自动入库。
- `source_service.py`：`SourceService`——候选创建（幂等）、新域名发现（blocked 域名不再入池）、管理员审核（每次写审计事件）、来源列表。
- `hotspot_service.py`：`HotspotRepository` / `HotspotNormalizer` / `HotspotService`——热点池缓存管理；refresh 只抓 `enabled` 来源；list 绝不触发抓取。
- `analysis_service.py`：`NewsAnalysisService`——按来源当前状态把检索结果分类为正式证据卡片或未核实线索，并检测来源间冲突。

## 业务边界要点
- 只有 `enabled` 来源可支撑正式证据卡片；`pending`/`lead_only`/`rejected`/`blocked` 一律归入未核实线索。
- 多个 enabled 来源对同一 claim 结论不一致时标记 `conflicted`，不由模型裁决。
- 来源状态在研判时实时查询（管理员拉黑立即生效）。
- 全链路不保存、不传递新闻全文；热点池只存标题/来源/URL/摘要/时间/主题/指纹。
