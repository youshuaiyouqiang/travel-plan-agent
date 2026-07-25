# tests/unit/ — 模块记忆

## 职责定位
单元测试层（31 个文件）：覆盖领域逻辑与工具，全部使用 fake/stub/mock，禁止访问真实网络或生产数据。

## 代表性文件
- `test_audit.py` / `test_password.py`（bcrypt）/ `test_prompt_guard.py`：安全基础能力。
- `test_mcp_runtime.py` / `test_tool_adapters.py`（24KB）/ `test_travel_tools.py`：工具与 MCP。
- `test_academic_tool_policy.py`：学术 Agent 工具白名单（无 web_search）。
- `test_fallback_llm.py`：LLM 降级链。
- `test_context_manager.py` / `test_reasoning.py`：上下文裁剪与 ReAct 引擎。

## 业务边界要点
- 新增领域逻辑先在此写失败测试再实现。
- 严禁在单测中调用真实 LLM/外部 API。
