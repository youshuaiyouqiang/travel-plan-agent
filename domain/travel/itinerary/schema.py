from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Activity:
    id: int = 0
    day_id: int = 0
    activity_index: int = 0
    time_slot: str = ""
    title: str = ""
    location: str = ""
    description: str = ""
    image_url: str = ""
    cost: float = 0.0
    actual_cost: float = 0.0
    tips: str = ""
    checked_in: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "day_id": self.day_id,
            "activity_index": self.activity_index,
            "time_slot": self.time_slot,
            "title": self.title,
            "location": self.location,
            "description": self.description,
            "image_url": self.image_url,
            "cost": self.cost,
            "actual_cost": self.actual_cost,
            "tips": self.tips,
            "checked_in": self.checked_in,
    }

    @classmethod
    def from_row(cls, row: dict) -> Activity:
        return cls(
            id=row.get("id", 0),
            day_id=row.get("day_id", 0),
            activity_index=row.get("activity_index", 0),
            time_slot=row.get("time_slot", ""),
            title=row.get("title", ""),
            location=row.get("location", ""),
            description=row.get("description", ""),
            image_url=row.get("image_url", ""),
            cost=float(row.get("cost", 0)),
            actual_cost=float(row.get("actual_cost", 0)),
            tips=row.get("tips", ""),
            checked_in=bool(row.get("checked_in", 0)),
        )


@dataclass
class DayPlan:
    id: int = 0
    itinerary_id: str = ""
    day_index: int = 0
    date: str = ""
    title: str = ""
    summary: str = ""
    activities: list[Activity] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "itinerary_id": self.itinerary_id,
            "day_index": self.day_index,
            "date": self.date,
            "title": self.title,
            "summary": self.summary,
            "activities": [a.to_dict() for a in self.activities],
        }

    @classmethod
    def from_row(cls, row: dict, activities: list[Activity] | None = None) -> DayPlan:
        return cls(
            id=row.get("id", 0),
            itinerary_id=row.get("itinerary_id", ""),
            day_index=row.get("day_index", 0),
            date=row.get("date", ""),
            title=row.get("title", ""),
            summary=row.get("summary", ""),
            activities=activities or [],
        )


@dataclass
class Itinerary:
    id: str = ""
    user_id: str = ""
    session_id: str = ""
    title: str = ""
    destination: str = ""
    start_date: str = ""
    end_date: str = ""
    budget: str = ""
    status: str = "planning"
    raw_content: str = ""
    created_at: str = ""
    updated_at: str = ""
    days: list[DayPlan] = field(default_factory=list)

    def to_dict(self, include_days: bool = True) -> dict:
        result = {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "title": self.title,
            "destination": self.destination,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "budget": self.budget,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_days:
            result["days"] = [d.to_dict() for d in self.days]
        return result

    def to_list_dict(self) -> dict:
        return self.to_dict(include_days=False)

    @classmethod
    def from_row(cls, row: dict, days: list[DayPlan] | None = None) -> Itinerary:
        return cls(
            id=row.get("id", ""),
            user_id=row.get("user_id", ""),
            session_id=row.get("session_id", ""),
            title=row.get("title", ""),
            destination=row.get("destination", ""),
            start_date=row.get("start_date", ""),
            end_date=row.get("end_date", ""),
            budget=row.get("budget", ""),
            status=row.get("status", "planning"),
            raw_content=row.get("raw_content", ""),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
            days=days or [],
        )
