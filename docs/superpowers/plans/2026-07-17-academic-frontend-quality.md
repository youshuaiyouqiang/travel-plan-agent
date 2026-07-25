# 学术 Agent、前端收敛与质量门禁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将学术 Agent 收敛为论文数据库驱动的会话级写作助手，删除无业务价值的情感识别，并以可重复的前后端质量门禁阻断回归。

**Architecture:** 学术服务依赖受限 `PaperSearchPort`，研究主题切换创建新的内存会话段；草稿不会进入长期记忆或审计正文。前端 API 按领域拆分且共用 cookie 认证客户端；CI 使用单一 Python 锁文件和明确的静态、安全、测试检查。

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, React, TypeScript strict mode, Vitest, pytest, Ruff, mypy, Bandit.

## Global Constraints

- 学术事实检索只允许 arXiv 与论文数据库；禁止通用网页搜索。
- 用户草稿不得进入长期记忆、用户画像或审计日志正文。
- 删除情感识别的代码、配置、指标、测试和前端依赖，不能留下兼容开关或空实现。
- 只创建 `features/chat/api.ts`、`features/travel/api.ts`、`features/academic/api.ts` 和共享 `features/auth/client.ts`；`features/news/api.ts` 只由新闻计划维护。
- Python 依赖锁定文件固定为 `requirements.lock`；README、启动脚本和 CI 均使用 `pip install -r requirements.lock`。

---

### Task 1: 学术工具白名单与临时研究上下文

**Files:**
- Create: `application/academic/service.py`
- Create: `domain/academic/context.py`
- Create: `domain/academic/ports.py`
- Modify: `application/builtin_agents/academic.yaml`
- Modify: `domain/agent/factory.py`
- Modify: `infrastructure/tools/policy.py`
- Test: `tests/unit/test_academic_context.py`
- Test: `tests/unit/test_academic_tool_policy.py`

**Interfaces:**
- `PaperSearchPort.search(query: str) -> list[Paper]`
- `AcademicService.switch_topic(session_id: str, topic: str) -> ResearchContext`
- `ToolPolicy.is_allowed(agent_id: str, tool_name: str) -> bool`

- [ ] **Step 1: 写失败测试**

```python
def test_switch_topic_drops_previous_papers_and_draft(service):
    first = service.start_context("s1", topic="RAG", draft_text="private draft")
    first.papers = [Paper(id="p1", title="RAG")]
    second = service.switch_topic("s1", "diffusion models")
    assert second.segment_id != first.segment_id
    assert second.papers == []
    assert second.draft_text is None

def test_academic_policy_rejects_web_search(policy):
    assert policy.is_allowed("academic", "search_papers")
    assert not policy.is_allowed("academic", "web_search")
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest tests/unit/test_academic_context.py tests/unit/test_academic_tool_policy.py -v`

Expected: FAIL because the academic Agent exposes generic web search and has no segmented context.

- [ ] **Step 3: 实现上下文与白名单**

```python
class ToolPolicy:
    _AGENT_ALLOWLIST = {
        "academic": {"search_papers", "get_abstract", "citation_graph", "batch_abstracts"},
        "news": {"news_search", "source_lookup"},
    }

    def is_allowed(self, agent_id: str, tool_name: str) -> bool:
        return tool_name in self._AGENT_ALLOWLIST.get(agent_id, set())
```

Remove `web-search` from `academic.yaml`. Store draft text only in an expiring session context and redact it from trace and audit serializers.

- [ ] **Step 4: 验证通过**

Run: `pytest tests/unit/test_academic_context.py tests/unit/test_academic_tool_policy.py tests/unit/test_audit.py -v`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add application/academic domain/academic application/builtin_agents/academic.yaml domain/agent infrastructure/tools tests/unit/test_academic_context.py tests/unit/test_academic_tool_policy.py; git commit -m "feat: constrain academic context and tools"`

### Task 2: 删除情感识别和旅行耦合记忆

**Files:**
- Delete: `domain/user/emotion/`
- Modify: `app.py`
- Modify: `config/settings.py`
- Modify: `domain/travel/core.py`
- Modify: `domain/travel/services/context_preparer.py`
- Modify: `domain/shared/metrics/collector.py`
- Test: `tests/unit/test_agent_factory_without_emotion.py`

- [ ] **Step 1: 写会先失败的静态与启动测试**

```python
def test_emotion_module_is_absent_after_removal():
    assert not Path("domain/user/emotion").exists()
    for path in (Path("app.py"), Path("config/settings.py"), Path("domain/travel/core.py")):
        assert "domain.user.emotion" not in path.read_text(encoding="utf-8")
        assert "YUNHE_EMOTION_" not in path.read_text(encoding="utf-8")

def test_orchestrator_starts_without_emotion_components():
    container = build_orchestrator()
    assert container.orchestrator.name == "yunhe"
    assert "emotion" not in container.metrics.names()
```

- [ ] **Step 2: 运行失败测试**

Run: `pytest tests/unit/test_agent_factory_without_emotion.py -v`

Expected: FAIL because the emotion module, imports, settings or metrics still exist.

- [ ] **Step 3: 删除情感路径**

Delete detector and schema files, configuration, Prometheus collectors, prompts and frontend imports. Remove constructor parameters instead of retaining unused optional fields. Preserve only the current travel draft context; do not infer or persist emotional memory.

- [ ] **Step 4: 验证通过**

Run: `pytest tests/unit/test_agent_factory_without_emotion.py tests/unit/test_reasoning.py -v`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add -A domain/user/emotion app.py config domain/travel domain/shared tests; git commit -m "refactor: remove emotion detection"`

### Task 3: 前端按领域拆分 API 和状态

**Files:**
- Create: `frontend/src/features/chat/api.ts`
- Create: `frontend/src/features/chat/types.ts`
- Create: `frontend/src/features/travel/api.ts`
- Create: `frontend/src/features/academic/api.ts`
- Modify: `frontend/src/utils/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/NavSidebar.tsx`
- Test: `frontend/src/features/chat/api.test.ts`

**Interfaces:**
- `sendMessageStream(input: { session_id: string; message: string }) -> AsyncIterable<StreamEvent>`
- `StreamEvent = { type: "chunk"; data: string } | { type: "route"; data: { agent_id: string | null; delegated: boolean } } | { type: "error"; data: { code: string; message: string } } | { type: "done"; data: { handled_by: string; next_controller: "yunhe" | "locked_agent" } }`

- [ ] **Step 1: 写失败 API 契约测试**

```ts
it("does not send client user_id with chat requests", async () => {
  await sendMessageStream({ session_id: "s1", message: "hello" })
  expect(fetch).toHaveBeenCalledWith("/api/v1/chat/stream", expect.objectContaining({
    body: JSON.stringify({ session_id: "s1", message: "hello" }),
  }))
})
```

- [ ] **Step 2: 运行失败测试**

Run: `npm run test -- api.test.ts`

Expected: FAIL because the feature API modules do not exist; the platform plan has already installed Vitest.

- [ ] **Step 3: 拆分模块并收紧事件类型**

Move chat/session, travel and academic calls out of `utils/api.ts` to their domain modules, each using `features/auth/client.ts`. Do not create or modify `features/news/api.ts`. Remove album and compare navigation only after the travel removal plan passes. Do not alter the memory page because its product disposition remains outside this task.

- [ ] **Step 4: 验证前端类型和 lint**

Run: `npm run test -- api.test.ts; npm run check; npm run lint`

Expected: PASS.

- [ ] **Step 5: 提交**

Run: `git add frontend/src package.json package-lock.json; git commit -m "refactor: split frontend APIs by domain"`

### Task 4: 质量门禁与最终规范

**Files:**
- Modify: `pyproject.toml`
- Modify: `frontend/tsconfig.json`
- Modify: `frontend/package.json`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Create: `requirements.lock`
- Modify: `AGENTS.md` only after the preceding plans pass

- [ ] **Step 1: 记录当前质量基线**

Run: `python -m ruff check .; python -m mypy api application domain infrastructure; python -m pytest; npm run lint; npm run check; npm run test; npm run build`

Expected: record every failure before tightening configuration; no command may hide an error with `|| echo`.

- [ ] **Step 2: 固定依赖并开启严格检查**

```json
{
  "compilerOptions": {
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "forceConsistentCasingInFileNames": true
  }
}
```

Generate `requirements.lock` from the approved Python dependency set, make documentation and CI install it with `pip install -r requirements.lock`, and remove unused imports and `any` rather than weakening type rules.

Add `bandit>=1.7.0` and `pip-audit>=2.7.0` to the `dev` dependency group, then generate the lock with:

```bash
python -m pip install pip-tools
pip-compile --extra dev --output-file requirements.lock pyproject.toml
```

- [ ] **Step 3: 配置阻断式 CI**

```yaml
- run: pip install -r requirements.lock
- run: python -m ruff check .
- run: python -m mypy api application domain infrastructure
- run: python -m bandit -r api application domain infrastructure -lll
- run: python -m pytest --cov=api --cov=application --cov=domain --cov=infrastructure --cov-fail-under=70
- run: pip-audit -r requirements.lock
- uses: gitleaks/gitleaks-action@v2
- run: npm ci
  working-directory: frontend
- run: npm run lint && npm run check && npm run test && npm run build
  working-directory: frontend
```

Remove global ignored prompt tests and every bypass that turns a failed security command into success.

- [ ] **Step 4: 以落地规则重写 AGENTS.md**

Keep root `AGENTS.md` under about 150 lines. Include only verified directory boundaries, authorization entry points, required commands, data-handling rules and CI gates. Move examples to `docs/standards/`.

- [ ] **Step 5: 完整验证和提交**

Run: `python -m ruff check . && python -m mypy api application domain infrastructure && python -m bandit -r api application domain infrastructure -lll && python -m pytest && npm run lint && npm run check && npm run test && npm run build`

Expected: PASS before merge.

Run: `git add pyproject.toml frontend .github/workflows/ci.yml README.md AGENTS.md requirements.lock; git commit -m "build: enforce product quality gates"`
