"""Task 1.1 失败测试：stock.yaml + stock tools adapter 注册。

覆盖范围（修复 Bug 1）：
- ``application/builtin_agents/stock.yaml`` 必须存在且可被 BuiltinAgentLoader 加载
- stock agent 必须引用 stock-review skill（被 FileSkillProvider 加载）
- ``infrastructure/tools/adapters/stock.py`` 必须导出 15 个 spec 和 15 个 handler
- ``app.py`` 必须把 stock tools 装配到全局 ToolRegistry

设计要点：
- 仅静态扫描 + 模块导入断言，不发起真实 LLM/网络调用
- 不依赖数据库（SqliteStockDataSource 实例化需要 init_db，本测试用 Module-level 检查）
"""

from __future__ import annotations

import importlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BUILTIN_DIR = ROOT / "application" / "builtin_agents"
STOCK_YAML = BUILTIN_DIR / "stock.yaml"
STOCK_ADAPTER = ROOT / "infrastructure" / "tools" / "adapters" / "stock.py"


# ── 1. stock.yaml 存在性 + 字段完整性 ───────────────────────


def test_stock_yaml_exists():
    """stock.yaml 必须存在（Bug 1 直接根因：缺失导致 stock agent 不可见）。"""
    assert STOCK_YAML.exists(), f"stock.yaml 缺失: {STOCK_YAML}"


def test_stock_yaml_required_fields():
    """stock.yaml 必含字段：id / name / description / skills / welcome_message。"""
    data = yaml.safe_load(STOCK_YAML.read_text(encoding="utf-8"))
    assert data["id"] == "stock", f"id 应为 stock，实际 {data.get('id')}"
    assert data["name"], "name 字段必填"
    assert data["description"], "description 字段必填（云合 LLM 路由依赖此字段做意图匹配）"
    assert "stock-review" in data.get("skills", []), "skills 必须包含 stock-review"


def test_stock_yaml_description_contains_routing_keywords():
    """description 必须包含云合 LLM 路由可识别的股市/复盘关键词。"""
    data = yaml.safe_load(STOCK_YAML.read_text(encoding="utf-8"))
    desc = data["description"]
    # 关键路由关键词：缺少这些词，云合 LLM 无法把"点评股市"路由到 stock
    required = ["股市", "复盘"]
    missing = [kw for kw in required if kw not in desc]
    assert not missing, f"description 缺少路由关键词: {missing}"


# ── 2. BuiltinAgentLoader 集成 ───────────────────────────────


def test_stock_agent_loaded_by_builtin_loader():
    """BuiltinAgentLoader 加载后必须包含 stock agent。"""
    from application.builtin_agents.loader import BuiltinAgentLoader
    from domain.agent.schema import AgentConfig

    loader = BuiltinAgentLoader(builtin_dir=BUILTIN_DIR)
    configs = loader.load_all()
    ids = {c.id for c in configs}
    assert "stock" in ids, f"BuiltinAgentLoader 加载后不含 stock: {ids}"
    stock_cfg = next(c for c in configs if c.id == "stock")
    assert isinstance(stock_cfg, AgentConfig)
    assert stock_cfg.source == "builtin"


# ── 3. stock tools adapter 注册 ──────────────────────────────


def test_stock_adapter_module_exists():
    """infrastructure/tools/adapters/stock.py 必须存在。"""
    assert STOCK_ADAPTER.exists(), f"stock tools adapter 缺失: {STOCK_ADAPTER}"


def test_stock_adapter_exposes_specs_and_handlers():
    """stock adapter 必须导出 get_stock_specs() 和 get_stock_handlers()。"""
    mod = importlib.import_module("infrastructure.tools.adapters.stock")
    assert hasattr(mod, "get_stock_specs"), "缺少 get_stock_specs()"
    assert hasattr(mod, "get_stock_handlers"), "缺少 get_stock_handlers()"


def test_stock_adapter_has_15_tools():
    """stock adapter 必须注册 17 个工具 spec（与 stock-review/openai.yaml 对齐；Task E 之后从 16 增至 17）。"""
    from infrastructure.tools.adapters.stock import get_stock_specs

    specs = get_stock_specs()
    assert len(specs) == 17, f"期望 17 个 stock 工具，实际 {len(specs)}"


def test_stock_adapter_handler_keys_match_spec_names():
    """每个 spec.name 必须在 handler 字典里有对应 handler。"""
    from infrastructure.tools.adapters.stock import get_stock_handlers, get_stock_specs

    specs = get_stock_specs()
    handlers = get_stock_handlers()
    spec_names = {s.name for s in specs}
    handler_names = set(handlers.keys())
    assert spec_names == handler_names, (
        f"spec/handler 名称不一致: "
        f"spec-only={spec_names - handler_names}, handler-only={handler_names - spec_names}"
    )


def test_stock_adapter_tool_names_match_stock_review_skill():
    """stock adapter 注册的工具名必须与 stock-review skill 的 tools 字段一致。"""
    from config import settings
    from infrastructure.tools.adapters.stock import get_stock_specs
    from infrastructure.skills.provider import FileSkillProvider

    provider = FileSkillProvider(skills_dir=settings.skills_dir)
    skill = provider.get_skill("stock-review")
    assert skill is not None, "stock-review skill 未加载"
    skill_tools = set(skill.tools)
    spec_tools = {s.name for s in get_stock_specs()}
    assert spec_tools == skill_tools, (
        f"stock adapter 工具名与 stock-review skill 不一致: "
        f"adapter-only={spec_tools - skill_tools}, skill-only={skill_tools - spec_tools}"
    )


# ── 4. app.py 集成 ─────────────────────────────────────────


def test_app_includes_stock_tools():
    """app.py 必须 import get_stock_specs + get_stock_handlers，并加入 tool infra。"""
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "get_stock_specs" in app_text, "app.py 未引用 get_stock_specs"
    assert "get_stock_handlers" in app_text, "app.py 未引用 get_stock_handlers"
