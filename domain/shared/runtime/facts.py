from __future__ import annotations

from datetime import datetime


def current_datetime_text() -> str:
    now = datetime.now().astimezone()
    weekday_map = {
        0: "星期一",
        1: "星期二",
        2: "星期三",
        3: "星期四",
        4: "星期五",
        5: "星期六",
        6: "星期日",
    }
    weekday = weekday_map[now.weekday()]
    return (
        f"当前本地时间为 {now.year:04d}-{now.month:02d}-{now.day:02d} "
        f"{now.hour:02d}:{now.minute:02d}:{now.second:02d} "
        f"{weekday}。"
    )


def answer_date_or_time_query(message: str) -> str | None:
    text = message.strip()
    if not text:
        return None

    lowered = text.lower()
    now = datetime.now().astimezone()
    weekday_map = {
        0: "星期一",
        1: "星期二",
        2: "星期三",
        3: "星期四",
        4: "星期五",
        5: "星期六",
        6: "星期日",
    }
    weekday = weekday_map[now.weekday()]

    date_markers = ("今天几号", "今天几月几号", "今天是几号", "今天是几月几号", "今天日期", "今天多少号")
    time_markers = ("现在几点", "现在时间", "当前时间", "几点了", "time now", "current time")

    if any(marker in text for marker in date_markers) or "date" == lowered:
        return f"今天是{now.year}年{now.month}月{now.day}日，{weekday}。"
    if any(marker in text for marker in time_markers):
        return (
            f"现在是{now.year}年{now.month}月{now.day}日 {now.hour:02d}:{now.minute:02d}:{now.second:02d}，{weekday}。"
        )
    return None
