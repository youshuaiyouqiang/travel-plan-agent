from __future__ import annotations

from fastapi import APIRouter, Request

from application.exceptions import UnauthorizedException, ValidationException, NotFoundException

router = APIRouter(tags=["memories"])


@router.get("")
async def get_memories(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    from domain.memory.manager import DualLayerMemoryManager

    mgr = DualLayerMemoryManager()
    ltm_list = mgr.get_long_term_memories(user_id)
    stm_list = mgr.get_short_term_memories(user_id, limit=20)

    category_labels = {"preference": "偏好", "fact": "事实", "experience": "经验"}

    def _serialize(m) -> dict:
        return {
            "id": m.id,
            "category": m.category,
            "category_label": category_labels.get(m.category, m.category),
            "content": m.content,
            "experience_tag": m.experience_tag,
            "extraction_count": m.extraction_count,
            "last_accessed_at": m.last_accessed_at,
            "created_at": m.created_at,
        }

    long_term = [_serialize(m) for m in ltm_list]
    short_term = [_serialize(m) for m in stm_list]
    all_memories = long_term + short_term

    return {
        "long_term": long_term,
        "short_term": short_term,
        "summary": {
            "total_ltm": len(long_term),
            "total_stm": len(short_term),
            "preferences": len([m for m in all_memories if m["category"] == "preference"]),
            "facts": len([m for m in all_memories if m["category"] == "fact"]),
            "experiences": len([m for m in all_memories if m["category"] == "experience"]),
        },
    }


@router.delete("/{memory_type}/{memory_id}")
async def delete_memory(memory_type: str, memory_id: int, request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    if memory_type not in ("short_term", "long_term"):
        raise ValidationException("无效的记忆类型")

    from infrastructure.persistence.database import get_connection

    conn = get_connection()
    # f-string SQL is safe: `table` is derived from whitelist check above
    table = "short_term_memories" if memory_type == "short_term" else "long_term_memories"
    row = conn.execute(
        f"SELECT id FROM {table} WHERE id = ? AND user_id = ?",
        (memory_id, user_id),
    ).fetchone()
    if not row:
        raise NotFoundException("记忆", memory_id)
    conn.execute(f"DELETE FROM {table} WHERE id = ?", (memory_id,))
    conn.commit()
    return {"detail": "已删除"}
