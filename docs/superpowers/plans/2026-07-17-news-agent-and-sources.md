# 新闻 Agent、热点池与来源治理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用可审核的来源库、后端缓存热点池和结构化证据卡片，实现由新闻 Agent 执行的可信新闻深度研判。

**Architecture:** `application/news` 管理来源、候选评分、热点和研判；SQLite 保存来源、审核与热点元数据但绝不保存新闻全文；定时器仅抓取已启用来源；新闻 Agent 只接收标题、来源、链接、摘要和发布时间。新闻计划独占前端新闻 API。

**Tech Stack:** Python 3.11, FastAPI, SQLite migrations, Pydantic v2, React, TypeScript, pytest, Vitest.

## Global Constraints

- 不抓取、保存或注入新闻全文；收藏仅保存标题、来源、URL、摘要、标签与时间。
- 正式事实结论和证据卡片只能由 `enabled` 来源支撑；未审核来源只能是 `unverified_leads`。
- 单一系统管理员由启动配置 `YUNHE_ADMIN_USERNAME` 确定，不从 HTTP 请求接收管理员 ID。
- `GET /hotspots` 只读缓存，严禁发起外部抓取。
- 新闻分析会话必须为 `news_analysis_locked`、锁定 Agent 为 `news`，并锚定 `news_id`。

---

### Task 1: 来源库、候选评分、管理员 API 与收藏迁移

**Files:**
- Create: `application/news/models.py`
- Create: `application/news/source_service.py`
- Create: `application/news/source_candidate_scorer.py`
- Create: `infrastructure/persistence/news_repository.py`
- Modify: `infrastructure/persistence/database.py`
- Modify: `api/v1/news.py`
- Create: `api/v1/admin_news.py`
- Modify: `api/v1/__init__.py`
- Modify: `config/settings.py`
- Test: `tests/integration/test_news_source_repository.py`
- Test: `tests/integration/test_news_admin_api.py`
- Test: `tests/integration/test_news_favorites_migration.py`

**Interfaces:**
- `SourceStatus = Literal["pending", "enabled", "lead_only", "rejected", "blocked", "needs_review"]`
- `SourceCandidateScorer.score(candidate: SourceCandidateInput) -> SourceScore`
- `SourceService.review_source(admin_id: str, source_id: str, decision: SourceStatus, reason: str) -> Source`
- `GET /api/v1/admin/news/sources`, `POST /api/v1/admin/news/sources/{source_id}/review`, `GET /api/v1/admin/news/source-audits`

- [ ] **Step 1: 写失败测试**

```python
def test_blocked_domain_is_not_recreated_as_candidate(service):
    source = service.create_candidate("blocked.example", 0.4, "risk")
    service.review_source("admin-1", source.id, "blocked", "impersonation")
    assert service.discover_candidate("blocked.example") is None

@pytest.mark.asyncio
async def test_only_admin_can_review_source(client, user_token, admin_token, source):
    forbidden = await client.post(f"/api/v1/admin/news/sources/{source.id}/review", headers=bearer(user_token), json={"decision": "enabled", "reason": "x"})
    accepted = await client.post(f"/api/v1/admin/news/sources/{source.id}/review", headers=bearer(admin_token), json={"decision": "enabled", "reason": "verified"})
    assert forbidden.status_code == 403
    assert accepted.status_code == 200

def test_favorite_migration_removes_full_content(database):
    migrate(database)
    assert "content" not in database.columns("news_favorites")
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest tests/integration/test_news_source_repository.py tests/integration/test_news_admin_api.py tests/integration/test_news_favorites_migration.py -v`

Expected: FAIL because governed sources, admin authorization and the metadata-only migration do not exist.

- [ ] **Step 3: 实现来源治理**

```sql
CREATE TABLE news_sources (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, domain TEXT NOT NULL UNIQUE,
    tier TEXT NOT NULL, status TEXT NOT NULL, ai_score REAL,
    ai_reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE news_source_audits (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL, admin_id TEXT NOT NULL,
    previous_status TEXT NOT NULL, decision TEXT NOT NULL, reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

Resolve `YUNHE_ADMIN_USERNAME` to exactly one user at startup; production startup fails if it is absent or unmatched. Score newly discovered, non-blocked domains from publisher type, domain-brand consistency, HTTPS, topic relevance, syndication ratio and risk signals, then create them as `pending`. Add a migration that rebuilds `news_favorites` without `content` and copies only allowed metadata; remove full-content reads, writes and memory injection.
Expose the three source-administration endpoints from `api/v1/admin_news.py`, and mount that router with `prefix="/admin/news"`; keep public hotspot routes in `api/v1/news.py` under `/news`.

- [ ] **Step 4: 验证通过**

Run: `pytest tests/integration/test_news_source_repository.py tests/integration/test_news_admin_api.py tests/integration/test_news_favorites_migration.py -v`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add application/news infrastructure/persistence/news_repository.py infrastructure/persistence/database.py api/v1/news.py api/v1/admin_news.py api/v1/__init__.py config/settings.py tests/integration; git commit -m "feat: govern news sources"`

### Task 2: 缓存热点池、锁定会话和证据化研判

**Files:**
- Create: `application/news/hotspot_service.py`
- Create: `application/news/analysis_service.py`
- Create: `infrastructure/news/fetchers.py`
- Create: `application/builtin_agents/news.yaml`
- Modify: `application/scheduler.py`
- Modify: `api/v1/news.py`
- Replace: `application/trending/manager.py`
- Test: `tests/integration/test_hotspot_pool.py`
- Test: `tests/integration/test_news_analysis_session.py`
- Test: `tests/unit/test_news_analysis_service.py`

**Interfaces:**
- `HotspotService.refresh() -> RefreshResult`
- `HotspotService.list_current(limit: int = 12) -> list[NewsItem]`
- `NewsAnalysisService.analyze(context: NewsAnchor, question: str) -> NewsAnalysisResponse`
- `EvidenceCard(source_name: str, url: str, claim: str, status: Literal["verified", "conflicted"])`
- `POST /api/v1/news/hotspots/{news_id}/analysis-sessions`

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_hotspot_read_uses_cache_without_external_fetch(service, fake_fetcher):
    service.repository.save_items([NewsItem(id="n1", title="A", source="S", url="https://s/a", summary="x")])
    assert [item.id for item in await service.list_current()] == ["n1"]
    assert fake_fetcher.calls == 0

def test_unreviewed_evidence_is_only_a_lead(analysis_service, anchor):
    response = analysis_service.analyze(anchor, "影响是什么？")
    assert response.evidence_cards == []
    assert response.unverified_leads
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest tests/integration/test_hotspot_pool.py tests/integration/test_news_analysis_session.py tests/unit/test_news_analysis_service.py -v`

Expected: FAIL because current reads fetch directly and analysis has no evidence contract.

- [ ] **Step 3: 实现刷新、分析与输出验证**

```python
async def refresh(self) -> RefreshResult:
    sources = self._sources.list_enabled_sources()
    batches = await asyncio.gather(*(self._fetcher.fetch(source) for source in sources))
    self._repository.replace_current(self._normalizer.normalize_and_deduplicate(batches), utc_now())
```

Run incremental refresh every 15 minutes and cleanup/reclustering every six hours. `GET /hotspots` never fetches. Create the locked session through `SessionService.create(..., "news_analysis_locked", "news", news_id)`. Validate that evidence is drawn from enabled sources; classify conflicting enabled evidence as `conflicted`; place all pending/lead-only material in `unverified_leads`; require an explicit user confirmation if the anchor changes.

- [ ] **Step 4: 验证通过**

Run: `pytest tests/integration/test_hotspot_pool.py tests/integration/test_news_analysis_session.py tests/unit/test_news_analysis_service.py -v`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add application/news infrastructure/news application/scheduler.py application/trending api/v1/news.py application/builtin_agents/news.yaml tests; git commit -m "feat: add cached evidence-based news analysis"`

### Task 3: 热点卡片、证据卡片与审核后台

**Files:**
- Create: `frontend/src/features/news/api.ts`
- Create: `frontend/src/components/news/HotspotCard.tsx`
- Create: `frontend/src/components/news/EvidenceCards.tsx`
- Create: `frontend/src/pages/NewsAdmin.tsx`
- Modify: `frontend/src/pages/Home.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/components/news/HotspotCard.test.tsx`
- Test: `frontend/src/components/news/EvidenceCards.test.tsx`

- [ ] **Step 1: 写失败组件测试**

```tsx
it('opens the original source without starting analysis', async () => {
  const onAnalyze = vi.fn()
  render(<HotspotCard item={item} onAnalyze={onAnalyze} />)
  await userEvent.click(screen.getByRole('link', { name: item.title }))
  expect(onAnalyze).not.toHaveBeenCalled()
})

it('does not render unverified leads as evidence cards', () => {
  render(<EvidenceCards cards={[]} unverifiedLeads={[lead]} />)
  expect(screen.queryByText(lead.claim)).not.toBeInTheDocument()
})
```

- [ ] **Step 2: 运行失败测试**

Run: `npm run test -- HotspotCard.test.tsx EvidenceCards.test.tsx`

Expected: FAIL because the news components and API contract do not exist; Vitest is supplied by the platform plan Task 4.

- [ ] **Step 3: 实现 UI**

Use a native source link plus a separate “AI 深度研判” button that creates the locked session and navigates to it. Render only verified/conflicted `EvidenceCard` objects from the API. Fetch review data through protected admin endpoints; hide the route for ordinary users and rely on the API's 403 as the authorization boundary.

- [ ] **Step 4: 验证通过**

Run: `npm run test -- HotspotCard.test.tsx EvidenceCards.test.tsx; npm run lint; npm run build`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add frontend/src package.json package-lock.json; git commit -m "feat: add governed news UI"`
