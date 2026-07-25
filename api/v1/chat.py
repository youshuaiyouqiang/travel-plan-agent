from __future__ import annotations

import json as json_mod
import logging
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from application.dto.request import ChatRequest
from application.dto.response import ChatResponse
from application.news.anchor_prompt import build_news_full_context
from application.news.analysis_service import NewsAnalysisService
from application.news.models import EvidenceCard, NewsAnalysisResponse, NewsAnchor, NewsItem
from application.session.schema import SessionMode, SessionRecord
from application.session.service import SessionService
from domain.shared.audit.logger import AuditLogger

logger = logging.getLogger(__name__)
_api_audit = AuditLogger()

router = APIRouter(tags=["chat"])


def _get_agent(request: Request):
    return request.app.state.agent


def _get_session_service(request: Request) -> SessionService:
    """获取应用层 SessionService；若未注入则使用默认可锁定 Agent 构造一个。"""
    service = getattr(request.app.state, "session_service", None)
    if service is None:
        service = SessionService()
        request.app.state.session_service = service
    return service


def _get_hotspot_service(request: Request):
    """获取应用层 HotspotService；若未注入则返回 None，由调用方按需跳过。"""
    return getattr(request.app.state, "hotspot_service", None)


def _get_news_analysis_service(request: Request) -> NewsAnalysisService | None:
    """获取应用层 NewsAnalysisService；若未注入则返回 None。

    NewsAnalysisService 用于在 news_analysis_locked 会话下自动产出证据卡片与
    未核实线索，并注入到 user message。生产环境由 server.py 注入；测试通过
    覆盖此属性注入替身。
    """
    return getattr(request.app.state, "news_analysis_service", None)


def _resolve_session_mode(
    request: Request,
    user_id: str | None,
    session_id: str,
) -> tuple[SessionMode, str | None, SessionRecord | None]:
    """从 SessionService 读取会话模式、锁定 Agent 与完整会话记录。

    读取失败或会话不存在时退回 ``yunhe_default``，避免阻塞对话；并返回 ``None`` 的
    SessionRecord 以便调用方知晓本次未拿到真实会话。
    """
    if not user_id or not session_id:
        return "yunhe_default", None, None
    try:
        record = _get_session_service(request).require_owned(
            user_id=user_id, session_id=session_id
        )
    except Exception:  # noqa: BLE001 - 读取模式失败不应中断对话
        return "yunhe_default", None, None
    return record.mode, record.locked_agent_id, record


def _build_news_context_payload(
    message: str,
    record: SessionRecord | None,
    hotspot_service,
    analysis_service: NewsAnalysisService | None,
) -> tuple[str, NewsAnalysisResponse | None]:
    """在 news_analysis_locked 会话中，拼装完整研判上下文（锚点+证据+线索+用户问题）。

    返回 ``(effective_message, analysis)``：
    - ``effective_message`` 是给 agent 的完整 user message（含锚点/证据/线索/用户问题）。
    - ``analysis`` 是 :class:`NewsAnalysisService` 产出的结构化研判响应；非
      ``news_analysis_locked`` 模式或锚点不存在时为 ``None``。
      SSE 流用它在 agent 输出文本前先把 evidence 卡片独立推给前端。

    业务红线：
    - 仅在会话模式为 ``news_analysis_locked`` 且存在有效 ``news_id`` 时注入；
      其他模式返回 ``(message, None)``。
    - 锚点数据来源于 HotspotRepository（缓存），绝不抓取或保存新闻全文。
    - 锚点不存在时（缓存已失效）原样返回 message，让新闻 Agent 正常报错。
    - NewsAnalysisService 未注入时仍注入锚点但不带证据块（降级为锚点 + 用户问题），
      ``analysis`` 也为 ``None``，SSE 不推送 evidence 事件。
    - 证据按 NewsAnalysisService 实时分类为 verified/conflicted/unverified_leads；
      生产默认 ``EmptyEvidenceProvider`` 返回空列表时显式输出"暂无证据或线索"。
    """
    if record is None or record.mode != "news_analysis_locked":
        return message, None
    if not record.news_id or hotspot_service is None:
        return message, None
    anchor_item: NewsItem | None = hotspot_service.repository.get_by_id(record.news_id)
    if anchor_item is None:
        return message, None
    analysis: NewsAnalysisResponse | None = None
    if analysis_service is not None:
        try:
            analysis = analysis_service.analyze(
                context=_to_news_anchor(anchor_item),
                question=message,
            )
        except Exception as exc:  # noqa: BLE001 - 证据生成失败不应阻塞研判
            # 记录到日志便于排障；研判仍可基于锚点和占位继续进行
            logger.warning(
                "NewsAnalysisService.analyze failed: %s", exc, exc_info=True
            )
            analysis = None
    effective_message = build_news_full_context(anchor_item, message, analysis)
    return effective_message, analysis


# 保留旧函数名作为薄包装，供不需要 analysis 的调用方使用。
def _build_news_full_context(
    message: str,
    record: SessionRecord | None,
    hotspot_service,
    analysis_service: NewsAnalysisService | None,
) -> str:
    """向后兼容的薄包装：仅返回注入后的 user message。

    业务逻辑在 :func:`_build_news_context_payload`；新代码请直接使用它以同时获得
    ``NewsAnalysisResponse`` 用于 SSE 推送。
    """
    effective_message, _ = _build_news_context_payload(
        message, record, hotspot_service, analysis_service
    )
    return effective_message


def _to_news_anchor(item: NewsItem) -> NewsAnchor:
    """把 NewsItem 转换为 NewsAnchor（NewsAnalysisService.analyze 的入参）。"""
    return NewsAnchor(
        news_id=item.id,
        title=item.title,
        source=item.source,
        url=item.url,
        summary=item.summary,
        published_at=item.published_at,
    )


def _evidence_card_to_dict(card: EvidenceCard) -> dict:
    """将 EvidenceCard 转换为可序列化 dict，用于 SSE evidence 事件。

    字段与前端 ``EvidenceCard`` 接口保持一致；``source_id`` 用于跳转到该来源
    的人工审核页（``/admin/news?source=xxx``）。
    """
    return {
        "source_id": card.source_id,
        "source_name": card.source_name,
        "url": card.url,
        "claim": card.claim,
        "status": card.status,
    }


def _build_evidence_event(analysis: NewsAnalysisResponse) -> str:
    """根据 NewsAnalysisResponse 构造 SSE ``evidence`` 事件的 data 行。

    始终推送，即便 ``evidence_cards`` 为空——空数组让前端明确"无证据"，避免被误读
    为"事件丢失"。
    """
    payload = {
        "type": "evidence",
        "data": [_evidence_card_to_dict(card) for card in analysis.evidence_cards],
    }
    return f"data: {json_mod.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    agent = _get_agent(request)
    auth_user_id = getattr(request.state, "user_id", None)
    effective_user_id = auth_user_id or req.user_id
    trace_id = uuid.uuid4().hex[:16]
    start_time = time.monotonic()
    logger.info("API /chat request: session_id=%s user_id=%s trace_id=%s", req.session_id, effective_user_id, trace_id)
    _api_audit.log_api_boundary(
        session_id=req.session_id,
        user_id=effective_user_id or "",
        trace_id=trace_id,
        direction="request",
        endpoint="/api/chat",
        method="POST",
        payload=req.message,
        agent_id=req.agent_id or "",
    )
    mode, locked_agent_id, record = _resolve_session_mode(
        request, effective_user_id, req.session_id
    )
    effective_message = _build_news_full_context(
        req.message,
        record,
        _get_hotspot_service(request),
        _get_news_analysis_service(request),
    )
    result = await agent.chat(
        session_id=req.session_id,
        user_id=effective_user_id,
        message=effective_message,
        mode=mode,
        locked_agent_id=locked_agent_id,
        agent_id=req.agent_id,
        trace_id=trace_id,
    )
    duration_ms = int((time.monotonic() - start_time) * 1000)
    _api_audit.log_api_boundary(
        session_id=req.session_id,
        user_id=effective_user_id or "",
        trace_id=trace_id,
        direction="response",
        endpoint="/api/chat",
        method="POST",
        payload=result.get("reply", ""),
        duration_ms=duration_ms,
        agent_id=req.agent_id or "",
    )
    logger.info(
        "API /chat response: session_id=%s user_id=%s trace_id=%s duration_ms=%s",
        req.session_id,
        effective_user_id,
        trace_id,
        duration_ms,
    )
    return ChatResponse(status=result["status"], reply=result["reply"])


@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    agent = _get_agent(request)
    auth_user_id = getattr(request.state, "user_id", None)
    effective_user_id = auth_user_id or req.user_id
    trace_id = uuid.uuid4().hex[:16]
    start_time = time.monotonic()
    logger.info(
        "API /chat/stream request: session_id=%s user_id=%s trace_id=%s", req.session_id, effective_user_id, trace_id
    )
    _api_audit.log_api_boundary(
        session_id=req.session_id,
        user_id=effective_user_id or "",
        trace_id=trace_id,
        direction="request",
        endpoint="/api/chat/stream",
        method="POST",
        payload=req.message,
        agent_id=req.agent_id or "",
    )
    mode, locked_agent_id, record = _resolve_session_mode(
        request, effective_user_id, req.session_id
    )
    effective_message, news_analysis = _build_news_context_payload(
        req.message,
        record,
        _get_hotspot_service(request),
        _get_news_analysis_service(request),
    )
    full_reply = ""

    async def event_generator():
        nonlocal full_reply
        try:
            # 在调用 agent 之前，先把结构化 evidence 卡片独立推给前端。
            # 仅 news_analysis_locked + analysis 存在时推送；空数组也推送
            # （让前端明确"无证据"而非事件丢失）。
            if news_analysis is not None:
                yield _build_evidence_event(news_analysis)
            async for event in agent.chat_stream(
                session_id=req.session_id,
                user_id=effective_user_id,
                message=effective_message,
                mode=mode,
                locked_agent_id=locked_agent_id,
                agent_id=req.agent_id,
                trace_id=trace_id,
            ):
                if event.get("type") == "chunk":
                    full_reply += event.get("data", "")
                yield f"data: {json_mod.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("Stream error: trace_id=%s %s", trace_id, e, exc_info=True)
            error_event = json_mod.dumps({"type": "error", "data": str(e), "trace_id": trace_id}, ensure_ascii=False)
            yield f"data: {error_event}\n\n"

        duration_ms = int((time.monotonic() - start_time) * 1000)
        _api_audit.log_api_boundary(
            session_id=req.session_id,
            user_id=effective_user_id or "",
            trace_id=trace_id,
            direction="response",
            endpoint="/api/chat/stream",
            method="POST",
            payload=full_reply,
            duration_ms=duration_ms,
            agent_id=req.agent_id or "",
        )
        logger.info(
            "API /chat/stream done: session_id=%s trace_id=%s duration_ms=%s", req.session_id, trace_id, duration_ms
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
