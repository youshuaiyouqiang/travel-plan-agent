from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from core.agent import Agent
from infrastructure.llm.openai import OpenAILLM
from domain.shared.runtime.logging import init_from_settings
from core.prompting import PromptBuilder
from infrastructure.tools.adapters.interaction import get_interaction_handlers, get_interaction_specs
from core.session import SessionManager
from infrastructure.tools.executor import ToolExecutor
from infrastructure.tools.adapters.http import get_http_handlers, get_http_specs
from domain.travel.tools.travel_tools import get_travel_handlers, get_travel_specs
from infrastructure.tools.adapters.amap import get_amap_handlers, get_amap_specs
from infrastructure.tools.adapters.fliggy import get_fliggy_handlers, get_fliggy_specs
from infrastructure.tools.policy import ToolPolicy
from infrastructure.tools.registry import ToolRegistry
from infrastructure.tools.catalog import ToolCatalog
from infrastructure.tools.base import bind_tool
from infrastructure.external.mcp.catalog import MCPCatalog
from infrastructure.external.mcp.runtime import MCPProxyRuntime
from core.intent.travel_classifier import TravelIntentClassifier
from core.emotion.detector import EmotionDetector
from core.profile.manager import ProfileManager
from core.audit.logger import AuditLogger
from core.metrics.collector import start_metrics_server
from infrastructure.persistence.database import init_db

from domain.agent.travel_core import Agent
from domain.agent.schema import AgentConfig
from core.agents.builtin_loader import BuiltinAgentLoader  # TODO: 后续迁移到application层
from domain.agent.repository import CustomAgentRepository
from domain.agent.factory import AgentFactory
from domain.agent.orchestrator import OrchestratorAgent
from domain.agent.travel_agent import TravelAgent
from core.skills.provider import FileSkillProvider, SkillProvider


@dataclass
class AppContainer:
    """依赖注入容器 — 持有总调度及供 API 路由使用的依赖。"""
    orchestrator: OrchestratorAgent
    skill_provider: SkillProvider
    builtin_configs: list[AgentConfig] = field(default_factory=list)
    custom_repo: CustomAgentRepository = None  # type: ignore[assignment]


def build_agent() -> Agent:
    """保留原有 build_agent()，向后兼容（仅构建旅游 Agent 主循环）。"""
    return _build_travel_agent_core(
        AuditLogger(),
        OpenAILLM(audit_logger=AuditLogger()),
    )


def _build_travel_agent_core(llm: OpenAILLM, audit_logger: AuditLogger) -> Agent:
    """构建原有旅游 Agent（所有原代码保留，抽成函数）。"""
    init_from_settings()
    init_db()
    prompt_builder = PromptBuilder()
    session_store = SessionManager()
    tool_catalog = ToolCatalog()
    tool_registry = ToolRegistry()
    tool_policy = ToolPolicy()
    mcp_catalog = MCPCatalog(Path(__file__).resolve().parents[0] / "mcps")
    mcp_runtime = MCPProxyRuntime(catalog=mcp_catalog)

    travel_classifier = TravelIntentClassifier(llm=llm)
    emotion_detector = EmotionDetector(llm=llm)
    profile_manager = ProfileManager()

    all_specs = (
        get_http_specs()
        + get_interaction_specs()
        + get_travel_specs()
        + get_amap_specs()
        + get_fliggy_specs()
        + mcp_runtime.build_specs()
    )
    for spec in all_specs:
        tool_catalog.register(spec)

    all_handlers = {}
    all_handlers.update(get_http_handlers())
    all_handlers.update(get_interaction_handlers())
    all_handlers.update(get_travel_handlers())
    all_handlers.update(get_amap_handlers())
    all_handlers.update(get_fliggy_handlers())
    all_handlers.update(mcp_runtime.build_handlers())

    for spec in tool_catalog.list_specs():
        tool_registry.register(bind_tool(spec, all_handlers[spec.name]))

    tool_executor = ToolExecutor(registry=tool_registry, policy=tool_policy, audit_logger=audit_logger)

    start_metrics_server()

    return Agent(
        llm=llm,
        prompt_builder=prompt_builder,
        session_store=session_store,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
        mcp_catalog=mcp_catalog,
        mcp_runtime=mcp_runtime,
        ops_classifier=travel_classifier,
        emotion_detector=emotion_detector,
        profile_manager=profile_manager,
        audit_logger=audit_logger,
    )


def build_orchestrator() -> AppContainer:
    """组装多智能体架构，返回依赖注入容器。"""
    init_from_settings()
    init_db()

    # ===== 基础依赖 =====
    audit_logger = AuditLogger()
    llm = OpenAILLM(audit_logger=audit_logger)

    # ===== Skill 提供者（抽象接口，可替换实现） =====
    skill_provider = FileSkillProvider(
        skills_dir=Path(__file__).resolve().parents[0] / "skills"
    )

    # ===== 内置智能体配置（从 YAML 加载，零硬编码） =====
    builtin_loader = BuiltinAgentLoader(
        builtin_dir=Path(__file__).resolve().parents[0] / "agents" / "builtin"
    )
    builtin_configs = builtin_loader.load_all()

    # ===== 旅行智能体的特殊构造器（需要完整 Agent 主循环） =====
    # 先构建原有旅游 Agent（代码完全保留）
    travel_agent_core = _build_travel_agent_core(llm, audit_logger)

    def travel_builder(config: AgentConfig) -> TravelAgent:
        return TravelAgent(travel_agent_core)

    # ===== 工厂 =====
    factory = AgentFactory(
        llm=llm,
        skill_provider=skill_provider,
        builtin_builders={"travel": travel_builder},
    )

    # ===== 自定义智能体 Repository =====
    custom_repo = CustomAgentRepository()

    # ===== 总调度 =====
    orchestrator = OrchestratorAgent(
        llm=llm,
        factory=factory,
        builtin_configs=builtin_configs,
        custom_repo=custom_repo,
        default_agent="travel",
    )

    return AppContainer(
        orchestrator=orchestrator,
        skill_provider=skill_provider,
        builtin_configs=builtin_configs,
        custom_repo=custom_repo,
    )
