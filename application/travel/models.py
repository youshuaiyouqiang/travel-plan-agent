"""旅行草稿与存档领域模型。

设计要点：
- ``TravelDraft`` 是可编辑的当前草稿；确认后 ``is_read_only`` 置 True，不可再确认或编辑。
- ``TravelArchive`` 是不可变的确认存档快照，``frozen=True`` 保证内存中不被修改。
- 草稿记录 ``manual_edit_fields``，保护用户手工编辑不被 Agent 覆盖。
- 存档只保存行程 JSON 快照与来源草稿 id，不保存原始外部数据。
- ``Activity`` / ``FieldConflict`` / ``ApplyProposalResult`` 用于手工编辑保护与冲突呈现。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Activity:
    """行程中单个活动的只读视图。"""

    id: str
    title: str = ""
    time_slot: str = ""
    location: str = ""
    note: str = ""


@dataclass
class TravelDraft:
    """旅行草稿：每个用户和会话只有一份当前草稿。

    ``is_read_only`` 在 ``confirm`` 后置为 True；只读草稿不可再确认或编辑，
    继续编辑需通过 ``start_draft_from_archive`` 创建新草稿。
    ``source_archive_id`` 仅在该草稿由存档续编而来时非空。
    """

    id: str
    user_id: str
    session_id: str
    plan: dict
    manual_edit_fields: set[str] = field(default_factory=set)
    is_read_only: bool = False
    source_archive_id: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def activity(self, activity_id: str) -> Activity:
        """按 id 取出活动视图；未找到抛 ``ValueError``。"""
        for day in self.plan.get("days", []):
            for act in day.get("activities", []):
                if act.get("id") == activity_id:
                    return Activity(
                        id=act["id"],
                        title=act.get("title", ""),
                        time_slot=act.get("time_slot", ""),
                        location=act.get("location", ""),
                        note=act.get("note", ""),
                    )
        raise ValueError(f"activity not found: {activity_id}")


@dataclass(frozen=True)
class TravelArchive:
    """旅行确认存档：不可变的行程快照。

    ``plan_json`` 是确认时刻草稿内容的完整 JSON 字符串快照；
    ``source_draft_id`` 指向被确认的那份草稿。
    """

    id: str
    user_id: str
    source_draft_id: str
    confirmed_at: str
    plan_json: str


@dataclass
class FieldConflict:
    """Agent 提议与用户手工编辑冲突的字段集合。"""

    activity_id: str
    fields: set[str]


@dataclass
class ApplyProposalResult:
    """Agent 提议应用结果：更新后的草稿与未应用的冲突字段。"""

    draft: TravelDraft
    conflicts: list[FieldConflict]

    def activity(self, activity_id: str) -> Activity:
        """从结果草稿中按 id 取出活动视图。"""
        return self.draft.activity(activity_id)
