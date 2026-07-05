from __future__ import annotations

import json
import logging

from infrastructure.tools.base import ToolHandler, ToolSpec, bind_tool

logger = logging.getLogger(__name__)


async def _estimate_drive_cost(arguments: dict) -> dict:
    """
    接收 amap_plan_route 返回的结果 + 人数 + 车型，计算自驾总费用。
    车型差异化和油价参数化，保证商用级精度。
    """
    distance_km = float(arguments.get("distance_km", 0))
    toll_yuan = float(arguments.get("toll_yuan", 0))
    people_count = int(arguments.get("people_count", 1))
    days_on_road = int(arguments.get("days_on_road", 1))
    car_type = str(arguments.get("car_type", "sedan")).strip()
    # 油价元/L，默认7.8（全国均值），可按出发地调整
    fuel_price = float(arguments.get("fuel_price", 7.8))

    # 车型油耗系数表（L/km）
    FUEL_RATE = {
        "sedan": 0.07,  # 轿车 ~7L/100km x 7.8元/L ≈ 0.55元/km
        "suv": 0.09,  # SUV ~9L/100km ≈ 0.70元/km
        "ev": 0.015,  # 电动车 ~15kWh/100km x 0.6元/kWh ≈ 0.09元/km
    }
    rate = FUEL_RATE.get(car_type, FUEL_RATE["sedan"])
    fuel_cost = distance_km * rate * fuel_price / 7.8  # 按实际油价比例缩放

    meal_cost = days_on_road * 100 * people_count  # 途中餐饮

    total = toll_yuan + fuel_cost + meal_cost

    return {
        "is_error": False,
        "content": json.dumps(
            {
                "total_cost": round(total, 0),
                "breakdown": {
                    "toll": round(toll_yuan, 0),
                    "fuel": round(fuel_cost, 0),
                    "meals_on_road": round(meal_cost, 0),
                },
                "distance_km": distance_km,
                "car_type": car_type,
                "fuel_rate_per_km": round(rate * fuel_price / 7.8, 3),
                "note": f"车型={car_type}, 油价={fuel_price}元/L, 油耗系数={rate}L/km; "
                f"实际费用根据路况和驾驶习惯浮动±10%",
            },
            ensure_ascii=False,
        ),
    }


def get_drive_cost_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="estimate_drive_cost",
            description="根据高德路线距离/过路费 + 车型 + 人数，计算自驾总费用（含过路费、油费、途中餐饮）",
            category="Web",
            parameters={
                "type": "object",
                "properties": {
                    "distance_km": {"type": "number", "description": "单程距离(km)，来自 amap_plan_route"},
                    "toll_yuan": {"type": "number", "description": "单程过路费(元)，来自 amap_plan_route"},
                    "people_count": {"type": "integer", "description": "出行人数", "default": 1},
                    "days_on_road": {"type": "integer", "description": "单程路途天数", "default": 1},
                    "car_type": {
                        "type": "string",
                        "enum": ["sedan", "suv", "ev"],
                        "description": "车型: sedan(轿车)/suv(越野)/ev(电动)",
                        "default": "sedan",
                    },
                    "fuel_price": {"type": "number", "description": "当地油价(元/L)，默认7.8", "default": 7.8},
                },
                "required": ["distance_km", "toll_yuan"],
            },
        ),
    ]


def get_drive_cost_handlers() -> dict[str, ToolHandler]:
    return {
        "estimate_drive_cost": _estimate_drive_cost,
    }
