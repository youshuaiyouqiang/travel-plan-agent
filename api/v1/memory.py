from __future__ import annotations

from fastapi import APIRouter, Request

from application.exceptions import UnauthorizedException, ValidationException, NotFoundException
from domain.memory.manager import DualLayerMemoryManager

router = APIRouter(tags=["memories"])


def _get_memory_manager(request: Request) -> DualLayerMemoryManager:
    """从组合根容器获取记忆管理器。

    P3.3b：原路由在函数内 ``from domain.memory.manager import DualLayerMemoryManager``
    并 ``DualLayerMemoryManager()`` 构造；现改为从 ``app.state.container`` 取用，
    消除路由对具体实现的临时构造。兼容未设置 container 的测试（回退到
    ``app.state.memory_repo`` 或默认构造）。
    """
    container = getattr(request.app.state, "container", None)
    if container is not None and container.memory_repo is not None:
        return container.memory_repo
    mgr = getattr(request.app.state, "memory_repo", None)
    if mgr is not None:
        return mgr
    return DualLayerMemoryManager()


@router.get("")
async def get_memories(request: Request) -> dict:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise UnauthorizedException()

    mgr = _get_memory_manager(request)
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

    # P3.3b：原裸 SQL 下沉到 MemoryRepositoryPort.delete_memory，校验所有权
    mgr = _get_memory_manager(request)
    deleted = mgr.delete_memory(user_id=user_id, memory_type=memory_type, memory_id=memory_id)
    if not deleted:
        raise NotFoundException("记忆", memory_id)
    return {"detail": "已删除"}
