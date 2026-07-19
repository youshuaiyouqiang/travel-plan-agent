# 旅行规划与确认存档 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将旅行能力收敛为单一当前草稿、手工编辑、显式信息更新和用户确认存档。

**Architecture:** `application/travel` 管理草稿与不可覆盖的存档；旅行 Agent 仅修改当前草稿；前端编辑器和确认页直接调用旅行用例。路线、天气和地点信息只在用户点击更新时查询。

**Tech Stack:** Python 3.11, FastAPI, SQLite migrations, Pydantic v2, React, TypeScript, pytest.

## Global Constraints

- 每个用户和旅行会话只有一份当前草稿。
- 已确认存档不可修改；继续编辑创建新草稿。
- Agent 不能覆盖手动编辑字段，除非用户在冲突界面明确应用变更。
- 删除相册、游记、比较、打卡、实际费用和交易流程。

---

### Task 1: 草稿与存档生命周期

**Files:**
- Create: `application/travel/models.py`
- Create: `application/travel/service.py`
- Create: `infrastructure/persistence/travel_repository.py`
- Modify: `infrastructure/persistence/database.py`
- Test: `tests/integration/test_travel_draft_archive.py`

**Interfaces:**
- `save_draft(user_id, session_id, plan) -> TravelDraft`
- `confirm(user_id, draft_id) -> TravelArchive`
- `start_draft_from_archive(user_id, archive_id) -> TravelDraft`

- [ ] **Step 1: 写失败生命周期测试**

```python
def test_confirmed_archive_is_immutable(service):
    draft = service.save_draft("u1", "s1", sample_plan())
    archive = service.confirm("u1", draft.id)
    with pytest.raises(ConflictException):
        service.edit_archive("u1", archive.id, {"title": "new"})
    next_draft = service.start_draft_from_archive("u1", archive.id)
    assert next_draft.source_archive_id == archive.id
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest tests/integration/test_travel_draft_archive.py -v`

Expected: FAIL because current itineraries mix mutable plans, multi-plan fields and confirmation state.

- [ ] **Step 3: 实现草稿/存档表和事务复制**

```python
@dataclass
class TravelDraft:
    id: str
    user_id: str
    session_id: str
    manual_edit_fields: set[str]

@dataclass(frozen=True)
class TravelArchive:
    id: str
    user_id: str
    source_draft_id: str
    confirmed_at: str
    plan_json: str
```

Add one migration for draft and archive records. `confirm` copies the complete draft in one transaction and marks the source draft read-only.

- [ ] **Step 4: 验证通过**

Run: `pytest tests/integration/test_travel_draft_archive.py -v`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add application/travel infrastructure/persistence/travel_repository.py infrastructure/persistence/database.py tests/integration/test_travel_draft_archive.py; git commit -m "feat: add travel draft and archive lifecycle"`

### Task 2: 手工编辑与显式刷新

**Files:**
- Create: `application/dto/request/travel.py`
- Modify: `application/travel/service.py`
- Create: `api/v1/travel.py`
- Modify: `api/v1/__init__.py`
- Test: `tests/integration/test_travel_draft_edits.py`

**Interfaces:**
- `PATCH /api/v1/travel/drafts/{draft_id}/activities/{activity_id}`
- `POST /api/v1/travel/drafts/{draft_id}/refresh-preview`
- `POST /api/v1/travel/drafts/{draft_id}/refresh-apply`

- [ ] **Step 1: 写失败手工编辑保护测试**

```python
def test_agent_proposal_preserves_manual_fields(service):
    draft = service.save_draft("u1", "s1", sample_plan())
    service.edit_activity("u1", draft.id, "a1", title="用户选定的博物馆")
    result = service.apply_agent_proposal("u1", draft.id, proposal_with_new_title())
    assert result.activity("a1").title == "用户选定的博物馆"
    assert result.conflicts[0].fields == {"title"}
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest tests/integration/test_travel_draft_edits.py -v`

Expected: FAIL because current direct updates overwrite fields.

- [ ] **Step 3: 实现 typed patch 和刷新预览**

```python
class EditActivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    time_slot: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=1000)
```

`refresh-preview` 是唯一调用外部 provider 的刷新入口；`refresh-apply` 只接收用户勾选的变化 ID。
Register the new router as `router.include_router(travel_router, prefix="/travel")`; do not add draft endpoints to the legacy `/itineraries` router.

- [ ] **Step 4: 验证通过**

Run: `pytest tests/integration/test_travel_draft_edits.py tests/integration/test_resource_authorization.py -v`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add application/travel application/dto/request/travel.py api/v1/travel.py api/v1/__init__.py tests/integration/test_travel_draft_edits.py; git commit -m "feat: preserve manual travel draft edits"`

### Task 3: 前端草稿编辑器、存档页与功能删除

**Files:**
- Replace: `frontend/src/pages/ItineraryOverview.tsx`
- Create: `frontend/src/components/travel/DraftEditor.tsx`
- Create: `frontend/src/components/travel/RefreshChangesDialog.tsx`
- Create: `frontend/src/pages/TravelArchive.tsx`
- Modify: `frontend/src/hooks/useItineraryStore.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `api/v1/itinerary.py`
- Delete: `frontend/src/pages/ComparePage.tsx`
- Delete: `frontend/src/pages/AlbumPage.tsx`
- Delete: `frontend/src/components/album/`
- Delete: `frontend/src/hooks/useAlbumStore.ts`
- Delete: `domain/travel/album/`
- Test: `frontend/src/components/travel/DraftEditor.test.tsx`
- Test: `tests/integration/test_removed_travel_features.py`

- [ ] **Step 1: 写编辑器和删除路由失败测试**

```tsx
it('marks an activity as manually edited after saving', async () => {
  render(<DraftEditor draft={draft} />)
  await userEvent.click(screen.getByRole('button', { name: '编辑景点' }))
  await userEvent.type(screen.getByLabelText('景点名称'), '博物馆')
  await userEvent.click(screen.getByRole('button', { name: '保存修改' }))
  expect(await screen.findByText('已手动调整')).toBeInTheDocument()
})
```

```python
@pytest.mark.asyncio
async def test_compare_route_is_not_exposed(client):
    assert (await client.post('/api/v1/itineraries/compare', json={'ids': ['a', 'b']})).status_code == 404

def test_travel_album_implementation_is_removed():
    assert not Path('domain/travel/album').exists()
    assert not Path('frontend/src/components/album').exists()
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest tests/integration/test_removed_travel_features.py -v && npm run test -- DraftEditor.test.tsx`

Expected: FAIL while comparison or album implementation remains. The API album-route assertion belongs to the earlier platform plan, which unmounts it before this task.

- [ ] **Step 3: 实现界面并移除非规划功能**

Remove comparison, check-in, actual-cost and album UI/domain paths. The platform plan has already unmounted album APIs; do not restore them. The editor has explicit `更新信息` and `确认行程` actions; confirmation navigates to immutable archive view with “基于此存档继续编辑”. Do not delete existing uploaded files until a reviewed retention/export decision exists; keep them unserved.

- [ ] **Step 4: 验证通过**

Run: `pytest tests/integration/test_removed_travel_features.py tests/integration/test_travel_draft_archive.py -v && npm run lint && npm run build`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add -A api/v1 domain/travel frontend/src application/dto infrastructure/persistence tests; git commit -m "refactor: focus travel on planning and archives"`
