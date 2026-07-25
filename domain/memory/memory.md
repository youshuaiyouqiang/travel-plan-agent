# domain/memory/ — 模块记忆

## 职责定位
用户记忆领域层：双层记忆（短期/长期）的读写、LLM 提取与精炼（蒸馏/衰减）。

## 关键文件
- `manager.py`：`DualLayerMemoryManager`（长/短期记忆查询、上下文构建、提取记账、会话保存）与 `SessionMemory`（基于会话摘要刷新）。
- `memory_extractor.py`：`MemoryExtractor`——用 LLM 从对话提取 preference/fact/experience 三类记忆并去重入库。
- `memory_distiller.py`：`MemoryDistiller`——短期记忆蒸馏进长期记忆并衰减（stale/deprecated 状态流转）。

## 业务规则
- 记忆固定三类：`preference` / `fact` / `experience`；experience 必须带 `experience_tag`（success/failure）。
- 蒸馏条件：`extraction_count >= 3` 且跨 ≥2 个会话、且 30 天内被访问。
- 衰减：长期记忆 >90 天（stale_days）转 stale，再 +30 天转 deprecated；短期记忆 >30 天且提取次数 <2 删除。
- 长期 `fact` 标注"待确认"；`experience` 带 ✓/✗ 标记。
- 学术草稿、新闻全文不进记忆（由上游边界保证）。

## 技术债
⚠️ 三个文件均直接依赖 `infrastructure.persistence.database` 与 `infrastructure.llm.openai`；`memory_distiller` 在独立线程用 `asyncio.run()` 调 LLM（调用方需 `to_thread`）。
