"""``ItineraryRepositoryPort`` 的 SQLite 实现。

P2.5 将原 ``domain/travel/itinerary/repository.py`` 的全部 SQL 收敛到此。
SQL 文本与参数化方式完全保留；不改变表结构或迁移版本。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from domain.travel.itinerary.schema import Activity, DayPlan, Itinerary
from infrastructure.persistence.connection import get_connection

logger = logging.getLogger(__name__)


class SqliteItineraryRepository:
    """``ItineraryRepositoryPort`` 的 SQLite 实现。

    无状态，可单例复用。通过 ``get_connection()`` 获取当前线程连接，
    支持测试隔离的 ``reset_connection()`` 模式。
    """

    def create_itinerary(
        self,
        user_id: str,
        title: str,
        destination: str,
        start_date: str,
        end_date: str,
        session_id: str = "",
        budget: str = "",
        raw_content: str = "",
        status: str = "planning",
    ) -> Itinerary:
        conn = get_connection()
        now = datetime.utcnow().isoformat()
        itinerary_id = uuid.uuid4().hex[:16]
        conn.execute(
            "INSERT INTO itineraries "
            "(id, user_id, session_id, title, destination, start_date, end_date, "
            "budget, status, raw_content, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                itinerary_id,
                user_id,
                session_id,
                title,
                destination,
                start_date,
                end_date,
                budget,
                status,
                raw_content,
                now,
                now,
            ),
        )
        conn.commit()
        return Itinerary(
            id=itinerary_id,
            user_id=user_id,
            session_id=session_id,
            title=title,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            budget=budget,
            status=status,
            raw_content=raw_content,
            created_at=now,
            updated_at=now,
        )

    def get_itinerary(self, itinerary_id: str) -> Itinerary | None:
        conn = get_connection()
        row = conn.execute("SELECT * FROM itineraries WHERE id = ?", (itinerary_id,)).fetchone()
        if not row:
            return None
        itinerary = Itinerary.from_row(dict(row))
        itinerary.days = self._load_days(itinerary_id)
        return itinerary

    def list_itineraries(self, user_id: str) -> list[Itinerary]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM itineraries WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
        return [Itinerary.from_row(dict(r)) for r in rows]

    def update_itinerary(self, itinerary_id: str, **kwargs: object) -> bool:
        conn = get_connection()
        sets: list[str] = []
        vals: list[Any] = []
        for key in ("title", "destination", "start_date", "end_date", "budget", "status", "raw_content"):
            if key in kwargs:
                sets.append(f"{key} = ?")
                vals.append(kwargs[key])
        if not sets:
            return False
        now = datetime.utcnow().isoformat()
        sets.append("updated_at = ?")
        vals.append(now)
        vals.append(itinerary_id)
        conn.execute(f"UPDATE itineraries SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
        return True

    def delete_itinerary(self, itinerary_id: str) -> bool:
        conn = get_connection()
        cursor = conn.execute("DELETE FROM itineraries WHERE id = ?", (itinerary_id,))
        conn.commit()
        return cursor.rowcount > 0

    def add_day(
        self,
        itinerary_id: str,
        day_index: int,
        date: str = "",
        title: str = "",
        summary: str = "",
    ) -> DayPlan:
        conn = get_connection()
        cursor = conn.execute(
            "INSERT INTO itinerary_days (itinerary_id, day_index, date, title, summary) VALUES (?, ?, ?, ?, ?)",
            (itinerary_id, day_index, date, title, summary),
        )
        conn.commit()
        day_id = cursor.lastrowid or 0
        return DayPlan(
            id=day_id,
            itinerary_id=itinerary_id,
            day_index=day_index,
            date=date,
            title=title,
            summary=summary,
        )

    def add_activity(
        self,
        day_id: int,
        activity_index: int,
        time_slot: str = "",
        title: str = "",
        location: str = "",
        description: str = "",
        image_url: str = "",
        cost: float = 0.0,
        tips: str = "",
    ) -> Activity:
        conn = get_connection()
        cursor = conn.execute(
            "INSERT INTO itinerary_activities "
            "(day_id, activity_index, time_slot, title, location, description, "
            "image_url, cost, tips) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (day_id, activity_index, time_slot, title, location, description, image_url, cost, tips),
        )
        conn.commit()
        activity_id = cursor.lastrowid or 0
        return Activity(
            id=activity_id,
            day_id=day_id,
            activity_index=activity_index,
            time_slot=time_slot,
            title=title,
            location=location,
            description=description,
            image_url=image_url,
            cost=cost,
            tips=tips,
        )

    def delete_activity(self, activity_id: int) -> bool:
        conn = get_connection()
        cursor = conn.execute("DELETE FROM itinerary_activities WHERE id = ?", (activity_id,))
        conn.commit()
        return cursor.rowcount > 0

    def get_activity(self, activity_id: int) -> Activity | None:
        conn = get_connection()
        row = conn.execute("SELECT * FROM itinerary_activities WHERE id = ?", (activity_id,)).fetchone()
        if not row:
            return None
        return Activity.from_row(dict(row))

    def get_day_itinerary_id(self, day_id: int) -> str | None:
        """按 day_id 反查所属 itinerary_id。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT itinerary_id FROM itinerary_days WHERE id = ?",
            (day_id,),
        ).fetchone()
        if not row:
            return None
        return row["itinerary_id"]

    def save_full_itinerary(self, itinerary: Itinerary) -> Itinerary:
        created = self.create_itinerary(
            user_id=itinerary.user_id,
            title=itinerary.title,
            destination=itinerary.destination,
            start_date=itinerary.start_date,
            end_date=itinerary.end_date,
            session_id=itinerary.session_id,
            budget=itinerary.budget,
            raw_content=itinerary.raw_content,
            status=itinerary.status,
        )
        for day in itinerary.days:
            day_record = self.add_day(
                itinerary_id=created.id,
                day_index=day.day_index,
                date=day.date,
                title=day.title,
                summary=day.summary,
            )
            for act in day.activities:
                self.add_activity(
                    day_id=day_record.id,
                    activity_index=act.activity_index,
                    time_slot=act.time_slot,
                    title=act.title,
                    location=act.location,
                    description=act.description,
                    image_url=act.image_url,
                    cost=act.cost,
                    tips=act.tips,
                )
        saved = self.get_itinerary(created.id)
        # create_itinerary 已成功写入；get_itinerary 仅在数据库异常时返回 None，
        # 此处返回 created 作为兜底以保证契约。
        return saved if saved is not None else created

    def create_share_link(self, itinerary_id: str, user_id: str, expires_at: str = "") -> str:
        conn = get_connection()
        token = uuid.uuid4().hex[:12]
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO shared_links (token, itinerary_id, user_id, expires_at, view_count, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (token, itinerary_id, user_id, expires_at, now),
        )
        conn.commit()
        return token

    def get_share_link(self, token: str) -> dict[str, Any] | None:
        conn = get_connection()
        row = conn.execute("SELECT * FROM shared_links WHERE token = ?", (token,)).fetchone()
        if not row:
            return None
        result = dict(row)
        conn.execute(
            "UPDATE shared_links SET view_count = view_count + 1 WHERE token = ?",
            (token,),
        )
        conn.commit()
        return result

    def list_share_links(self, itinerary_id: str) -> list[dict[str, Any]]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM shared_links WHERE itinerary_id = ? ORDER BY created_at DESC",
            (itinerary_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_share_link(self, token: str) -> bool:
        conn = get_connection()
        cursor = conn.execute("DELETE FROM shared_links WHERE token = ?", (token,))
        conn.commit()
        return cursor.rowcount > 0

    # ── 辅助 ─────────────────────────────────────────────────

    def _load_days(self, itinerary_id: str) -> list[DayPlan]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM itinerary_days WHERE itinerary_id = ? ORDER BY day_index",
            (itinerary_id,),
        ).fetchall()
        days: list[DayPlan] = []
        for r in rows:
            day = DayPlan.from_row(dict(r))
            day.activities = self._load_activities(day.id)
            days.append(day)
        return days

    def _load_activities(self, day_id: int) -> list[Activity]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM itinerary_activities WHERE day_id = ? ORDER BY activity_index",
            (day_id,),
        ).fetchall()
        return [Activity.from_row(dict(r)) for r in rows]


__all__ = ["SqliteItineraryRepository"]
