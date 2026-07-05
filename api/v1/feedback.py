from __future__ import annotations

from fastapi import APIRouter, Request

from application.dto.request import FeedbackRequest
from application.exceptions import UnauthorizedException

router = APIRouter(tags=["feedback"])


@router.post("")
async def submit_feedback(req: FeedbackRequest, request: Request) -> dict:
    """提交对话质量反馈（👍/👎）。"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    from domain.feedback.repository import FeedbackRepository

    repo = FeedbackRepository()
    feedback_id = repo.record(
        session_id=req.session_id,
        user_id=user_id,
        rating=req.rating,
        issue_type=req.issue_type,
        comment=req.comment,
        agent_id=req.agent_id,
        message_snippet=req.message_snippet,
    )
    return {"status": "ok", "id": feedback_id}
