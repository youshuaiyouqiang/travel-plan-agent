from __future__ import annotations

import logging
from dataclasses import dataclass, field

from config import settings
from infrastructure.llm.openai import OpenAILLM
from infrastructure.llm.fallback import FallbackLLM
from domain.shared.runtime.logging import init_from_settings
from domain.shared.llm.ports import LLMPort, configure_default_llm
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
# P3.1：收敛 server.py 中的应用服务构造到组合根
from application.authz import AuthorizationService
from application.news.analysis_service import NewsAnalysisService
from application.news.empty_evidence_provider import EmptyEvidenceProvider
from application.news.hotspot_service import HotspotService, get_default_service as get_default_hotspot_service
from application.news.source_service import SourceService
from application.session.service import SessionService
from application.session.confirm_plan_service import ConfirmPlanService
from domain.user.auth.auth import UserStore
# P3.3a：api 层 domain repository 导入清除 — container 持有仓储实例供路由取用
from domain.feedback.repository import FeedbackRepository
from domain.memory.manager import DualLayerMemoryManager
from domain.travel.itinerary.repository import ItineraryRepository
# P3.3b：api 层 get_connection 直接 SQL 清除 — news favorites 端口
from application.news.ports import NewsFavoriteRepositoryPort


@dataclass
class AppContainer:
    """依赖注入容器 — 持有总调度及供 API 路由使用的依赖。"""

    orchestrator: OrchestratorAgent
    skill_provider: SkillProvider
    builtin_configs: list[AgentConfig] = field(default_factory=list)
    custom_repo: CustomAgentRepository = None  # type: ignore[assignment]
    mcp_runtime: MCPProxyRuntime = None  # type: ignore[assignment]
    mcp_catalog: MCPCatalog = None  # type: ignore[assignment]
    # P3.1：以下服务原在 api/server.py 模块级构造，现收敛到组合根
    session_service: SessionService | None = None
    authz_service: AuthorizationService | None = None
    news_analysis_service: NewsAnalysisService | None = None
    hotspot_service: HotspotService | None = None
    admin_user_id: str | None = None
    # P3.3a：api 层 domain repository 导入清除 — 路由通过 container 取用
    feedback_repo: FeedbackRepository | None = None
    itinerary_repo: ItineraryRepository | None = None
    # P3.3b：api 层 get_connection 直接 SQL 清除 — memory/news_favorites/session_confirm
    memory_repo: DualLayerMemoryManager | None = None
    news_favorite_repo: NewsFavoriteRepositoryPort | None = None
    confirm_plan_service: ConfirmPlanService | None = None


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
    llm: LLMPort,
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
        profile_manager=profile_manager,
        audit_logger=audit_logger,
    )


def resolve_admin_user_id() -> str | None:
    """启动期解析 ``YUNHE_ADMIN_USERNAME`` → ``admin_user_id``。

    P3.1：从 ``api/server.py`` 迁移到组合根，消除 server.py 对
    ``UserStore`` 的直接依赖。行为保持不变：

    - 生产环境（``settings.environment == "production"``）下，
      ``YUNHE_ADMIN_USERNAME`` 为空或对应用户不存在时必须 fail-fast
      抛 ``RuntimeError``，禁止静默降级到无管理员状态。
    - 开发环境允许缺失/找不到，仅记录 warning，返回 None。
    """
    logger = logging.getLogger(__name__)
    username = settings.admin_username
    is_production = settings.environment == "production"

    if not username:
        if is_production:
            raise RuntimeError(
                "YUNHE_ADMIN_USERNAME is not configured; production deployments "
                "must define a system administrator before startup."
            )
        logger.info("YUNHE_ADMIN_USERNAME not configured; admin API disabled (development mode)")
        return None

    user = UserStore().get_by_username(username)
    if user is None:
        if is_production:
            raise RuntimeError(
                f"YUNHE_ADMIN_USERNAME={username!r} does not match any existing user; "
                "production deployments must reference a valid administrator account."
            )
        logger.warning(
            "YUNHE_ADMIN_USERNAME=%s 不存在对应用户；管理员 API 将不可用（开发模式降级）",
            username,
        )
        return None

    logger.info("Admin resolved: username=%s user_id=%s", username, user.user_id)
    return user.user_id


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
    # llm 在运行时可能是 OpenAILLM 或 FallbackLLM；二者均满足 LLMPort。
    # P4.1：消费者按 LLMPort 接口编码，不再需要 type: ignore[arg-type]。
    llm: LLMPort
    if fallback_providers:
        llm = FallbackLLM(providers=[primary_llm] + fallback_providers)
    else:
        llm = primary_llm

    # P4.1：注册全局默认 LLM，供 ItineraryParser / TravelIntentClassifier
    # 等未显式注入的领域组件回退取用（与 P2 仓储端口模式一致）。
    configure_default_llm(llm)

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

    # P3.1：原在 api/server.py 模块级构造的应用服务，现收敛到组合根。
    # Task 1: 会话模式应用服务。可锁定的 Agent 来自内置配置（排除调度员 yunhe）。
    # news Agent 由新闻研判流程内部锁定（news_analysis_locked），不进入用户可选白名单。
    _lockable_agent_ids = {
        c.id for c in builtin_configs if c.id not in {"yunhe", "news"}
    }
    session_service = SessionService(available_agent_ids=_lockable_agent_ids)
    # Task 2: 集中式对象级授权服务；复用同一 SessionService 保证会话所有权判定一致。
    authz_service = AuthorizationService(session_service=session_service)
    # 路由通过 request.app.state.hotspot_service 取用；未配置时 GET /hotspots 返回空列表。
    hotspot_service = get_default_hotspot_service()
    # 新闻研判分析服务：调用 analyze 把证据按来源状态分类为 verified / conflicted
    # / unverified_leads。当前生产默认使用空证据提供者（未接入真实证据通道）。
    news_analysis_service = NewsAnalysisService(
        sources=SourceService(), evidence_provider=EmptyEvidenceProvider()
    )
    # 启动期解析 YUNHE_ADMIN_USERNAME → admin_user_id。
    # 生产环境缺失或找不到对应用户时 fail-fast，禁止静默降级。
    admin_user_id = resolve_admin_user_id()
    # P3.3a：构造 domain 仓储委托实例供 api 路由取用（端口已在 init_db 配置）
    feedback_repo = FeedbackRepository()
    itinerary_repo = ItineraryRepository()
    # P3.3b：memory 路由通过 container 取用 DualLayerMemoryManager
    memory_repo = DualLayerMemoryManager()
    # P3.3b：news favorites 路由通过 container 取用仓储端口
    from infrastructure.persistence.repositories.news_favorite import SqliteNewsFavoriteRepository

    news_favorite_repo = SqliteNewsFavoriteRepository()
    # P3.3b：confirm-plan 路由通过 container 取用协调服务
    confirm_plan_service = ConfirmPlanService()

    return AppContainer(
        orchestrator=orchestrator,
        skill_provider=skill_provider,
        builtin_configs=builtin_configs,
        custom_repo=custom_repo,
        mcp_runtime=mcp_runtime,
        mcp_catalog=mcp_catalog,
        session_service=session_service,
        authz_service=authz_service,
        news_analysis_service=news_analysis_service,
        hotspot_service=hotspot_service,
        admin_user_id=admin_user_id,
        feedback_repo=feedback_repo,
        itinerary_repo=itinerary_repo,
        memory_repo=memory_repo,
        news_favorite_repo=news_favorite_repo,
        confirm_plan_service=confirm_plan_service,
    )
