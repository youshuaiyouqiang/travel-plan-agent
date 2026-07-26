"""记忆持久化端口。

P2.4 引入：将 ``long_term_memories`` / ``short_term_memories`` /
``conversations`` / ``memory_extractions`` 四张表的访问从 domain 层下沉到
infrastructure，领域层只消费此端口。

端口由消费方（domain）定义，由 ``infrastructure.persistence.repositories.memory``
提供 ``SqliteMemoryRepository`` 实现，在 ``init_db()`` 中装配默认实例。
测试可用 fake 实现替代，不创建 SQLite 文件。

注意：``memory_distiller`` 与 ``memory_extractor`` 对 ``infrastructure.llm.openai``
的依赖属于 LLM 端口（``domain/shared/llm/ports.py``）范畴，将在后续阶段统一反转，
不在 P2.4 范围内。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # 避免循环导入；Protocol 仅用于静态类型检查
    from domain.memory.manager import LongTermMemory, ShortTermMemory


@runtime_checkable
class MemoryRepositoryPort(Protocol):
    """记忆双层存储的读写端口。

    涵盖四类表的访问：
    1. ``long_term_memories`` — 长期记忆的读取、状态更新、蒸馏晋升。
    2. ``short_term_memories`` — 短期记忆的读取、去重插入、衰减删除。
    3. ``conversations`` — 会话记录的创建。
    4. ``memory_extractions`` — 记忆提取记录与会话关联。

    实现必须保证：
    - 所有 SQL 参数化；动态表名（``short_term_memories`` / ``long_term_memories``）
      只能来自硬编码白名单（``record_extraction`` 按 ``memory_type`` 选择）；
    - ``merge_stm_into_existing_ltm`` 与 ``promote_stm_to_ltm`` 各自是原子事务
     （UPDATE/INSERT + DELETE 在同一连接内提交），保证蒸馏过程中不会出现
      STM 与 LTM 并存的中间态；
    - ``record_extraction`` 的 INSERT + UPDATE 同样是原子事务；
    - 读操作返回领域对象或 ``dict[str, Any]``（供调用方做业务判定）。
    """

    # ── 长期记忆读取 ──────────────────────────────────────────

    def get_long_term_memories(self, user_id: str) -> list[LongTermMemory]:
        """加载用户全部 active 长期记忆，按 last_accessed_at/updated_at 倒序。"""
        ...

    def find_existing_ltm_id(self, user_id: str, category: str, content: str) -> int | None:
        """查找同 user/category/content 的 active LTM ID；不存在返回 None。"""
        ...

    def get_ltm_for_decay(self, user_id: str | None) -> list[dict[str, Any]]:
        """加载 LTM 的衰减判定字段（id/last_accessed_at/status）。

        ``user_id`` 为 None 时加载全量；供 ``run_decay`` 按 idle 天数判定状态变迁。
        """
        ...

    # ── 短期记忆读取 ──────────────────────────────────────────

    def get_recent_short_term_memories(self, user_id: str, limit: int) -> list[ShortTermMemory]:
        """加载用户最近 ``limit`` 条短期记忆（ORDER BY id DESC LIMIT ?）。"""
        ...

    def get_all_short_term_memories(self, user_id: str) -> list[ShortTermMemory]:
        """加载用户全部短期记忆（供 ``build_full_context`` 的 query 评分路径）。"""
        ...

    def get_stm_candidates(self, user_id: str, min_extractions: int) -> list[dict[str, Any]]:
        """加载 extraction_count >= min_extractions 的 STM 行（含 id/category/content/
        experience_tag/extraction_count/last_accessed_at），供蒸馏候选判定。"""
        ...

    def get_stm_for_decay(self, user_id: str | None) -> list[dict[str, Any]]:
        """加载 STM 的衰减判定字段（id/extraction_count/last_accessed_at）。"""
        ...

    def list_user_ids_with_short_term_memories(self) -> list[str]:
        """列出所有有短期记忆的去重 user_id（排除空字符串）。

        P2.6 引入：供 ``scheduler.run_memory_maintenance`` 枚举需蒸馏的用户，
        避免 application 层直接查询 ``short_term_memories`` 表。
        """
        ...

    def find_short_term_duplicate(self, user_id: str, category: str, content: str) -> dict[str, Any] | None:
        """查找同 user/category/content 的 STM 行；不存在返回 None。"""
        ...

    # ── 长期记忆写入 ──────────────────────────────────────────

    def touch_long_term_memories(self, ids: list[int], now: str) -> None:
        """批量更新 LTM 的 last_accessed_at。"""
        ...

    def update_ltm_status(self, ltm_id: int, status: str, now: str) -> None:
        """更新 LTM 状态（active → stale → deprecated）与 updated_at。"""
        ...

    def merge_stm_into_existing_ltm(self, stm_id: int, ltm_id: int, now: str) -> None:
        """原子事务：递增已有 LTM 的 extraction_count/last_accessed_at/updated_at，
        并删除源 STM 行。供蒸馏路径 A（已存在同内容 LTM）使用。"""
        ...

    def promote_stm_to_ltm(
        self,
        *,
        user_id: str,
        category: str,
        content: str,
        source_ids: list[int],
        experience_tag: str,
        extraction_count: int,
        last_accessed_at: str,
        stm_id: int,
        now: str,
    ) -> None:
        """原子事务：将 STM 蒸馏为新 LTM 行（status='active'），并删除源 STM。

        供蒸馏路径 B（无同内容 LTM，需新建）使用。``content`` 已由调用方完成
        LLM 压缩（如需），``source_ids`` 已解析完毕。
        """
        ...

    # ── 短期记忆写入 ──────────────────────────────────────────

    def touch_short_term_memories(self, ids: list[int], now: str) -> None:
        """批量更新 STM 的 last_accessed_at。"""
        ...

    def update_stm_source_conv(self, stm_id: int, conversation_id: int, now: str) -> None:
        """更新 STM 的 source_conv_id 与 last_accessed_at（去重命中已存在记忆时）。"""
        ...

    def insert_short_term(
        self,
        *,
        user_id: str,
        category: str,
        content: str,
        conversation_id: int,
        experience_tag: str,
        now: str,
    ) -> int:
        """插入新 STM 行，返回 lastrowid。"""
        ...

    def delete_short_term(self, stm_id: int) -> None:
        """按 ID 删除单条 STM。"""
        ...

    def delete_memory(self, *, user_id: str, memory_type: str, memory_id: int) -> bool:
        """按类型与 ID 删除单条记忆，校验所有权。

        P3.3b 引入：将 ``api/v1/memory.py`` 的 ``DELETE`` 路由裸 SQL 下沉到
        仓储层。``memory_type`` 仅接受 ``short_term`` / ``long_term``（由调用方
        先做白名单校验）；只删除属于 ``user_id`` 的行，避免 IDOR。

        Returns:
            ``True`` 表示命中并删除；``False`` 表示行不存在或不属于该用户。
        """
        ...

    # ── 会话与提取记录 ────────────────────────────────────────

    def save_conversation(self, session_id: str, user_id: str, summary: str, now: str) -> int:
        """插入 conversation 行，返回 lastrowid。summary 截断至 200 字。"""
        ...

    def record_extraction(
        self,
        *,
        conversation_id: int,
        memory_type: str,
        memory_id: int,
        relevance: float,
        now: str,
    ) -> None:
        """原子事务：插入 memory_extractions 行，并递增对应记忆的 extraction_count
        与 last_accessed_at。``memory_type`` 为 'short_term' 或 'long_term'，
        据此选择更新 ``short_term_memories`` 或 ``long_term_memories``。"""
        ...

    def get_distinct_conversation_ids_for_memory(self, memory_id: int) -> list[int]:
        """查询与某条 STM 关联的去重会话 ID 列表（供蒸馏候选的 min_conversations 判定）。"""
        ...


# ── 默认仓储装配（过渡方案，同 P2.1/P2.2/P2.3）─────────────

_default_repository: MemoryRepositoryPort | None = None


def configure_default_memory_repository(repository: MemoryRepositoryPort) -> None:
    """注册全局默认记忆仓储（由组合根调用）。"""
    global _default_repository
    _default_repository = repository


def get_default_memory_repository() -> MemoryRepositoryPort:
    """获取全局默认记忆仓储；未配置时抛 RuntimeError。"""
    if _default_repository is None:
        raise RuntimeError(
            "MemoryRepositoryPort 未配置：请在组合根调用 "
            "configure_default_memory_repository() 或显式注入 repository 参数。"
        )
    return _default_repository
