from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PlanType(str, Enum):
    SIGHTSEEING = "sightseeing"   # 景点打卡型
    BUDGET = "budget"             # 经济实惠型
    SINGLE = "single"             # 单方案（兼容旧数据/降级场景）


class TransportMode(str, Enum):
    FLIGHT = "flight"
    TRAIN = "train"
    DRIVE = "drive"


@dataclass
class CostBreakdown:
    """费用明细分项"""
    transport: float = 0          # 往返交通
    hotel: float = 0              # 住宿
    tickets: float = 0            # 景点门票
    meals: float = 0              # 餐饮
    local_transport: float = 0    # 市内交通
    other: float = 0              # 其他
    total: float = 0              # 总计

    def to_dict(self) -> dict:
        return {
            "transport": self.transport,
            "hotel": self.hotel,
            "tickets": self.tickets,
            "meals": self.meals,
            "local_transport": self.local_transport,
            "other": self.other,
            "total": self.total,
        }

    @classmethod
    def from_row(cls, row: dict) -> CostBreakdown:
        return cls(
            transport=float(row.get("transport", 0)),
            hotel=float(row.get("hotel", 0)),
            tickets=float(row.get("tickets", 0)),
            meals=float(row.get("meals", 0)),
            local_transport=float(row.get("local_transport", 0)),
            other=float(row.get("other", 0)),
            total=float(row.get("total", 0)),
        )


@dataclass
class TransportOption:
    """出行方式选项"""
    mode: TransportMode = TransportMode.FLIGHT
    duration_hours: float = 0
    cost_yuan: float = 0
    detail: str = ""              # 如"CA1234 08:00-10:30"
    weather_risk: str = ""        # 天气影响评估

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "duration_hours": self.duration_hours,
            "cost_yuan": self.cost_yuan,
            "detail": self.detail,
            "weather_risk": self.weather_risk,
        }

    @classmethod
    def from_row(cls, row: dict) -> TransportOption:
        return cls(
            mode=TransportMode(row.get("mode", "flight")),
            duration_hours=float(row.get("duration_hours", 0)),
            cost_yuan=float(row.get("cost_yuan", 0)),
            detail=str(row.get("detail", "")),
            weather_risk=str(row.get("weather_risk", "")),
        )


@dataclass
class Plan:
    """一套完整的出行方案"""
    plan_type: PlanType = PlanType.SINGLE
    transport: TransportOption = field(default_factory=TransportOption)
    hotel_name: str = ""
    hotel_cost_per_night: float = 0
    hotel_reason: str = ""
    days: list[DayPlan] = field(default_factory=list)
    cost_breakdown: CostBreakdown = field(default_factory=CostBreakdown)
    version: int = 1  # ★ 修改版本号，每次更新递增

    def to_dict(self) -> dict:
        return {
            "plan_type": self.plan_type.value,
            "transport": self.transport.to_dict(),
            "hotel_name": self.hotel_name,
            "hotel_cost_per_night": self.hotel_cost_per_night,
            "hotel_reason": self.hotel_reason,
            "days": [d.to_dict() for d in self.days],
            "cost_breakdown": self.cost_breakdown.to_dict(),
            "version": self.version,
        }

    @classmethod
    def from_row(cls, row: dict, days: list[DayPlan] | None = None) -> Plan:
        transport_data = row.get("transport", {})
        transport = TransportOption.from_row(transport_data) if isinstance(transport_data, dict) else TransportOption()
        cost_data = row.get("cost_breakdown", {})
        cost_breakdown = CostBreakdown.from_row(cost_data) if isinstance(cost_data, dict) else CostBreakdown()
        return cls(
            plan_type=PlanType(row.get("plan_type", "single")),
            transport=transport,
            hotel_name=str(row.get("hotel_name", "")),
            hotel_cost_per_night=float(row.get("hotel_cost_per_night", 0)),
            hotel_reason=str(row.get("hotel_reason", "")),
            days=days or [],
            cost_breakdown=cost_breakdown,
            version=int(row.get("version", 1)),
        )


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


@dataclass
class MultiPlanItinerary:
    """统一行程模型（旧 Itinerary 等价于 plans=[单个Plan]）"""
    id: str = ""
    session_id: str = ""
    user_id: str = ""
    destination: str = ""
    start_date: str = ""
    end_date: str = ""
    plans: list[Plan] = field(default_factory=list)
    recommended_plan: PlanType | None = None
    confirmed_plan: PlanType | None = None
    confirmed_at: str = ""
    created_at: str = ""

    @property
    def is_multi_plan(self) -> bool:
        """是否为多方案（plans 长度 > 1）"""
        return len(self.plans) > 1

    @property
    def active_plan(self) -> Plan:
        """获取当前生效的方案（已确认的优先，否则取第一个）"""
        if self.confirmed_plan:
            for p in self.plans:
                if p.plan_type == self.confirmed_plan:
                    return p
        return self.plans[0] if self.plans else Plan()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "destination": self.destination,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "plans": [p.to_dict() for p in self.plans],
            "recommended_plan": self.recommended_plan.value if self.recommended_plan else None,
            "confirmed_plan": self.confirmed_plan.value if self.confirmed_plan else None,
            "confirmed_at": self.confirmed_at,
            "created_at": self.created_at,
            "is_multi_plan": self.is_multi_plan,
        }

    @classmethod
    def from_legacy_itinerary(cls, old: Itinerary) -> MultiPlanItinerary:
        """旧 Itinerary → MultiPlanItinerary 转换（plans=[单个Plan]）"""
        return cls(
            id=old.id,
            session_id=old.session_id,
            user_id=old.user_id,
            destination=old.destination,
            start_date=old.start_date,
            end_date=old.end_date,
            plans=[Plan(
                plan_type=PlanType.SINGLE,
                days=old.days,
            )],
            created_at=old.created_at,
        )
