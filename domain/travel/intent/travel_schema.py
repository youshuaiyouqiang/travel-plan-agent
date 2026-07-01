from __future__ import annotations

from enum import Enum


class TravelIntentType(str, Enum):
    TRIP_PLANNING = "trip_planning"
    DESTINATION_SEARCH = "destination_search"
    FLIGHT_SEARCH = "flight_search"
    HOTEL_SEARCH = "hotel_search"
    ATTRACTION_SEARCH = "attraction_search"
    WEATHER_CHECK = "weather_check"
    BUDGET_CALC = "budget_calc"
    ITINERARY_ADJUST = "itinerary_adjust"
    ITINERARY_CONFIRM = "itinerary_confirm"
    VISA_INFO = "visa_info"
    FOOD_RECOMMEND = "food_recommend"
    TRAVEL_TIPS = "travel_tips"
    CURRENCY_CONVERT = "currency_convert"
    TRAVEL_COMPANION = "travel_companion"
    EMERGENCY_HELP = "emergency_help"
    GENERAL_CHAT = "general_chat"


INTENT_TOOL_HINTS: dict[TravelIntentType, list[str]] = {
    TravelIntentType.TRIP_PLANNING: ["Web", "File System"],
    TravelIntentType.DESTINATION_SEARCH: ["Web"],
    TravelIntentType.FLIGHT_SEARCH: ["Web"],
    TravelIntentType.HOTEL_SEARCH: ["Web"],
    TravelIntentType.ATTRACTION_SEARCH: ["Web"],
    TravelIntentType.WEATHER_CHECK: ["Web"],
    TravelIntentType.BUDGET_CALC: ["Web"],
    TravelIntentType.ITINERARY_ADJUST: ["Web", "File System"],
    TravelIntentType.ITINERARY_CONFIRM: ["Travel"],
    TravelIntentType.VISA_INFO: ["Web"],
    TravelIntentType.FOOD_RECOMMEND: ["Web"],
    TravelIntentType.TRAVEL_TIPS: ["Web"],
    TravelIntentType.CURRENCY_CONVERT: ["Web"],
    TravelIntentType.TRAVEL_COMPANION: ["Web"],
    TravelIntentType.EMERGENCY_HELP: ["Web"],
    TravelIntentType.GENERAL_CHAT: [],
}

INTENT_RAG_KEYWORDS: dict[TravelIntentType, list[str]] = {
    TravelIntentType.TRIP_PLANNING: ["旅行规划", "行程安排", "旅游攻略"],
    TravelIntentType.DESTINATION_SEARCH: ["目的地推荐", "旅游地点", "去哪玩"],
    TravelIntentType.FLIGHT_SEARCH: ["机票", "航班", "机票查询"],
    TravelIntentType.HOTEL_SEARCH: ["酒店", "住宿", "民宿"],
    TravelIntentType.ATTRACTION_SEARCH: ["景点", "打卡", "必去"],
    TravelIntentType.WEATHER_CHECK: ["天气", "气温", "穿衣"],
    TravelIntentType.BUDGET_CALC: ["预算", "花费", "费用"],
    TravelIntentType.ITINERARY_ADJUST: ["行程调整", "改行程", "换计划"],
    TravelIntentType.ITINERARY_CONFIRM: ["行程确认", "确认行程", "生成概览"],
    TravelIntentType.VISA_INFO: ["签证", "护照", "入境"],
    TravelIntentType.FOOD_RECOMMEND: ["美食", "餐厅", "小吃"],
    TravelIntentType.TRAVEL_TIPS: ["注意事项", "旅行贴士", "避坑"],
    TravelIntentType.CURRENCY_CONVERT: ["汇率", "换汇", "货币"],
    TravelIntentType.TRAVEL_COMPANION: ["结伴", "同行", "拼团"],
    TravelIntentType.EMERGENCY_HELP: ["紧急", "求助", "大使馆"],
    TravelIntentType.GENERAL_CHAT: [],
}
