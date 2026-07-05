from __future__ import annotations

from dataclasses import dataclass, field

from config import settings
from infrastructure.llm.openai import OpenAILLM
from infrastructure.llm.fallback import FallbackLLM
from domain.shared.runtime.logging import init_from_settings
from domain.travel.prompting import PromptBuilder
from infrastructure.tools.adapters.interaction import get_interaction_handlers, get_interaction_specs
from domain.user.session.manager import SessionManager
from infrastructure.tools.executor import ToolExecutor
from infrastructure.tools.adapters.http import get_http_handlers, get_http_specs
from domain.travel.tools.travel_tools import get_travel_handlers, get_travel_specs
from infrastructure.tools.adapters.amap import get_amap_handlers, get_amap_specs
from infrastructure.tools.adapters.fliggy import get_fliggy_handlers, get_fliggy_specs
from infrastructure.tools.adapters.qweather import get_qweather_handlers, get_qweather_specs
from infrastructure.tools.adapters.drive_cost import get_drive_cost_handlers, get_drive_cost_specs
from infrastructure.tools.adapters.shared import get_shared_handlers, get_shared_specs
from infrastructure.tools.policy import ToolPolicy
from infrastructure.tools.registry import ToolRegistry
from infrastructure.tools.catalog import ToolCatalog
from infrastructure.tools.base import bind_tool
from infrastructure.mcp.catalog import MCPCatalog
from infrastructure.mcp.runtime import MCPProxyRuntime
from domain.travel.intent.travel_classifier import TravelIntentClassifier
from domain.user.emotion.detector import EmotionDetector
from domain.user.profile.manager import ProfileManager
from domain.shared.audit.logger import AuditLogger
from domain.shared.metrics.collector import start_metrics_server
from infrastructure.persistence.database import init_db

from domain.travel.core import Agent
from domain.agent.schema import AgentConfig
from application.builtin_agents.loader import BuiltinAgentLoader
from domain.agent.repository import CustomAgentRepository
from domain.agent.factory import AgentFactory
from domain.agent.orchestrator import OrchestratorAgent
from domain.travel.agent import TravelAgent
from infrastructure.skills.provider import FileSkillProvider, SkillProvider


@dataclass
class AppContainer:
    """依赖注入容器 — 持有总调度及供 API 路由使用的依赖。"""

    orchestrator: OrchestratorAgent
    skill_provider: SkillProvider
    builtin_configs: list[AgentConfig] = field(default_factory=list)
    custom_repo: CustomAgentRepository = None  # type: ignore[assignment]
    mcp_runtime: MCPProxyRuntime = None  # type: ignore[assignment]
    mcp_catalog: MCPCatalog = None  # type: ignore[assignment]


def _build_tool_infrastructure(
    mcp_catalog: MCPCatalog,
    mcp_runtime: MCPProxyRuntime,
    audit_logger: AuditLogger,
) -> tuple[ToolRegistry, ToolExecutor]:
    """构建工具注册表和执行器（供 travel_agent 和 orchestrator 共享）。"""
    tool_catalog = ToolCatalog()
    tool_registry = ToolRegistry()
    tool_policy = ToolPolicy()

    all_specs = (
        get_http_specs()
        + get_interaction_specs()
        + get_travel_specs()
        + get_amap_specs()
        + get_fliggy_specs()
        + get_qweather_specs()
        + get_drive_cost_specs()
        + get_shared_specs()
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
    all_handlers.update(get_qweather_handlers())
    all_handlers.update(get_drive_cost_handlers())
    all_handlers.update(get_shared_handlers())
    all_handlers.update(mcp_runtime.build_handlers())

    for spec in tool_catalog.list_specs():
        tool_registry.register(bind_tool(spec, all_handlers[spec.name]))

    tool_executor = ToolExecutor(registry=tool_registry, policy=tool_policy, audit_logger=audit_logger)

    return tool_registry, tool_executor


def _build_travel_agent_core(
    llm: OpenAILLM,
    audit_logger: AuditLogger,
    tool_registry: ToolRegistry,
    tool_executor: ToolExecutor,
    session_store: SessionManager,
    mcp_catalog: MCPCatalog,
    mcp_runtime: MCPProxyRuntime,
    skip_init: bool = False,
) -> Agent:
    """构建原有旅游 Agent（依赖由外部注入，允许多 Agent 共享实例）。"""
    if not skip_init:
        init_from_settings()
        init_db()
    prompt_builder = PromptBuilder()

    travel_classifier = TravelIntentClassifier(llm=llm)
    emotion_detector = EmotionDetector(llm=llm)
    profile_manager = ProfileManager()

    if not skip_init:
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
    # P1-15：构建 LLM 降级链。主 provider 始终创建；若配置了 fallback_api_key，
    # 再追加备用 provider，用 FallbackLLM 包装。无 fallback 配置时退化为单实例。
    primary_llm = OpenAILLM(audit_logger=audit_logger)
    fallback_providers = []
    if settings.fallback_api_key:
        fallback_providers.append(
            OpenAILLM(
                audit_logger=audit_logger,
                api_key=settings.fallback_api_key,
                base_url=settings.fallback_base_url,
                model=settings.fallback_model or None,
            )
        )
    if fallback_providers:
        llm = FallbackLLM(providers=[primary_llm] + fallback_providers)
    else:
        llm = primary_llm

    # ===== Skill 提供者（抽象接口，可替换实现） =====
    skill_provider = FileSkillProvider(skills_dir=settings.skills_dir)

    # ===== MCP 基础设施 =====
    mcp_catalog = MCPCatalog(settings.mcp_servers_dir)
    mcp_runtime = MCPProxyRuntime(catalog=mcp_catalog)

    # ===== 工具基础设施（全局单例，供所有 Agent 共享） =====
    tool_registry, tool_executor = _build_tool_infrastructure(mcp_catalog, mcp_runtime, audit_logger)

    # ===== 会话管理（全局单例） =====
    session_store = SessionManager()

    # ===== 内置智能体配置（从 YAML 加载，零硬编码） =====
    builtin_loader = BuiltinAgentLoader(builtin_dir=settings.builtin_agents_dir)
    builtin_configs = builtin_loader.load_all()

    # ===== 旅行智能体的特殊构造器（需要完整 Agent 主循环） =====
    travel_agent_core = _build_travel_agent_core(
        llm=llm,
        audit_logger=audit_logger,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
        session_store=session_store,
        mcp_catalog=mcp_catalog,
        mcp_runtime=mcp_runtime,
        skip_init=True,
    )

    def travel_builder(config: AgentConfig) -> TravelAgent:
        return TravelAgent(travel_agent_core)

    # ===== 工厂（注入所有全局依赖） =====
    factory = AgentFactory(
        llm=llm,
        skill_provider=skill_provider,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
        session_store=session_store,
        mcp_runtime=mcp_runtime,
        audit_logger=audit_logger,
        builtin_builders={"travel": travel_builder},
    )

    # ===== 自定义智能体 Repository =====
    custom_repo = CustomAgentRepository()

    # ===== 总调度 =====
    # Phase 3: 默认智能体从 travel 切换为 yunhe（云合）。
    # yunhe 模式下，OrchestratorAgent 本身作为云合执行三层决策：
    # Tier 0（快路径）→ Tier 1（function calling 委派）→ Tier 2（委派执行）。
    # 如需灰度回退，将 default_agent 改回 "travel" 即可恢复 prompt 路由模式。
    orchestrator = OrchestratorAgent(
        llm=llm,
        factory=factory,
        builtin_configs=builtin_configs,
        custom_repo=custom_repo,
        default_agent="yunhe",
    )

    return AppContainer(
        orchestrator=orchestrator,
        skill_provider=skill_provider,
        builtin_configs=builtin_configs,
        custom_repo=custom_repo,
        mcp_runtime=mcp_runtime,
        mcp_catalog=mcp_catalog,
    )
