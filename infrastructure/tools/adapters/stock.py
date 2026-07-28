"""股票复盘工具适配器 — 注册 15 个 stock 工具到 ToolRegistry。

设计要点（AGENTS.md §8.1 端口先于实现 + §8.4 工具入站）：
- 与 stock-review skill (infra/skills/builtin/stock-review/agents/openai.yaml)
  的 ``interface.tools`` 字段保持严格一一对应
- 工具集按 domain.stock.tools.build_stock_tools("daily") 装配；周复盘
  的 get_correlation 仍注册到 ToolRegistry，但 DynamicAgent 会按 session
  上下文调用
- 15 个 spec 覆盖：大盘 / 情绪 / 板块 / 个股 / 周复盘
- Handler 直接调 SqliteStockDataSource（同层 infrastructure，无
  application 反向依赖），序列化 DTO 为 markdown-friendly JSON

边界：
- handler 调 SqliteStockDataSource，**禁止**直接 import akshare
  （AGENTS.md §3 业务红线：复盘链路只读缓存）
- 不接 application 层 StockQueryService（避免 infrastructure → application 反向耦合）
- 表名走 SqliteStockDataSource._ALLOWED_TABLES 白名单
- 数据全空返回 is_error=False + 占位说明，让 DynamicAgent 走"框架性复盘"模式
"""

from __future__ import annotations

import json
import logging
from typing import Any

from domain.shared.tools.base import ToolHandler, ToolSpec

logger = logging.getLogger(__name__)


# ── DataSource 单例（懒加载） ────────────────────────────

_data_source: Any = None


def _get_data_source() -> Any:
    """懒加载 SqliteStockDataSource 单例。init_db 已在 app.py 启动期调用。"""
    global _data_source
    if _data_source is None:
        from infrastructure.persistence.connection import get_connection
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        _data_source = SqliteStockDataSource(conn=get_connection())
    return _data_source


# ── 辅助：DTO → dict / 异常处理 ──────────────────────────


def _dumps(value: Any) -> str:
    """序列化 Pydantic v2 DTO 列表为紧凑 JSON。失败时退化为 repr。"""
    try:
        if hasattr(value, "model_dump"):
            return value.model_dump_json()
        if isinstance(value, list) and value and hasattr(value[0], "model_dump"):
            return "[" + ",".join(v.model_dump_json() for v in value) + "]"
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning("Failed to serialize stock tool result: %s", e)
        return repr(value)[:2000]


async def _call(coro: Any) -> dict:
    """统一异常处理：捕获具体异常并保留异常链（AGENTS.md §5）。"""
    try:
        result = await coro
    except Exception as e:
        logger.exception("stock tool execution failed: %s", e)
        return {"is_error": True, "content": f"数据查询失败: {type(e).__name__}: {e}"}
    return {"is_error": False, "content": _dumps(result)}


# ── Handlers（15 个） ────────────────────────────────────


async def _get_market_snapshot(arguments: dict) -> dict:
    trade_date = str(arguments.get("trade_date", "")).strip()
    if not trade_date:
        return {"is_error": True, "content": "missing trade_date"}
    ds = _get_data_source()
    return await _call(ds.get_market_snapshot(trade_date))


async def _get_emotion_indicators(arguments: dict) -> dict:
    trade_date = str(arguments.get("trade_date", "")).strip()
    if not trade_date:
        return {"is_error": True, "content": "missing trade_date"}
    ds = _get_data_source()
    return await _call(ds.get_emotion_indicators(trade_date))


async def _get_emotion_indicators_trend(arguments: dict) -> dict:
    end_date = str(arguments.get("end_date", "")).strip()
    days = int(arguments.get("days", 10) or 10)
    if not end_date:
        return {"is_error": True, "content": "missing end_date"}
    ds = _get_data_source()
    return await _call(ds.get_emotion_indicators_trend(end_date, days))


async def _get_strong_repair_leaders(_arguments: dict) -> dict:
    ds = _get_data_source()
    return await _call(ds.get_strong_repair_leaders())


async def _get_sector_rotation(arguments: dict) -> dict:
    trade_date = str(arguments.get("trade_date", "")).strip()
    if not trade_date:
        return {"is_error": True, "content": "missing trade_date"}
    ds = _get_data_source()
    return await _call(ds.get_sector_rotation(trade_date))


async def _get_sector_heat_distribution(arguments: dict) -> dict:
    trade_date = str(arguments.get("trade_date", "")).strip()
    if not trade_date:
        return {"is_error": True, "content": "missing trade_date"}
    ds = _get_data_source()
    return await _call(ds.get_sector_heat_distribution(trade_date))


async def _get_resistant_sectors(arguments: dict) -> dict:
    trade_date = str(arguments.get("trade_date", "")).strip()
    if not trade_date:
        return {"is_error": True, "content": "missing trade_date"}
    ds = _get_data_source()
    return await _call(ds.get_resistant_sectors(trade_date))


async def _get_sector_leaders(arguments: dict) -> dict:
    sector_name = str(arguments.get("sector_name", "")).strip()
    if not sector_name:
        return {"is_error": True, "content": "missing sector_name"}
    ds = _get_data_source()
    return await _call(ds.get_sector_leaders(sector_name))


async def _get_sector_divergence(arguments: dict) -> dict:
    trade_date = str(arguments.get("trade_date", "")).strip()
    if not trade_date:
        return {"is_error": True, "content": "missing trade_date"}
    ds = _get_data_source()
    return await _call(ds.get_sector_divergence(trade_date))


async def _get_sector_history(arguments: dict) -> dict:
    sector_name = str(arguments.get("sector_name", "")).strip()
    days = int(arguments.get("days", 10) or 10)
    ds = _get_data_source()
    return await _call(ds.get_sector_history(sector_name, days))


async def _get_watchlist(_arguments: dict) -> dict:
    ds = _get_data_source()
    return await _call(ds.get_watchlist())


async def _get_stock_daily(arguments: dict) -> dict:
    stock_code = str(arguments.get("stock_code", "")).strip()
    days = int(arguments.get("days", 30) or 30)
    if not stock_code:
        return {"is_error": True, "content": "missing stock_code"}
    ds = _get_data_source()
    return await _call(ds.get_stock_daily(stock_code, days))


async def _get_signal_stocks(arguments: dict) -> dict:
    trade_date = str(arguments.get("trade_date", "")).strip()
    if not trade_date:
        return {"is_error": True, "content": "missing trade_date"}
    ds = _get_data_source()
    return await _call(ds.get_signal_stocks(trade_date))


async def _get_limit_stocks(arguments: dict) -> dict:
    trade_date = str(arguments.get("trade_date", "")).strip()
    if not trade_date:
        return {"is_error": True, "content": "missing trade_date"}
    ds = _get_data_source()
    return await _call(ds.get_limit_stocks(trade_date))


async def _get_correlation(arguments: dict) -> dict:
    end_date = str(arguments.get("end_date", "")).strip()
    days = int(arguments.get("days", 5) or 5)
    if not end_date:
        return {"is_error": True, "content": "missing end_date"}
    ds = _get_data_source()
    return await _call(ds.get_correlation(end_date, days))


# ── Specs（15 个，与 stock-review/openai.yaml 一一对应） ──


def get_stock_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="get_market_snapshot",
            description="拉取大盘快照（上证/深证/创业板三大指数 + 两市成交额 + 量能环比 + MA20 位置）。参数 trade_date=YYYY-MM-DD。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "trade_date": {"type": "string", "description": "交易日期 YYYY-MM-DD"},
                },
                "required": ["trade_date"],
            },
        ),
        ToolSpec(
            name="get_emotion_indicators",
            description="拉取当日情绪指标（涨停数 / 跌停数 / 炸板率 / 最高连板 / 昨日涨停今日溢价）。参数 trade_date=YYYY-MM-DD。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "trade_date": {"type": "string", "description": "交易日期 YYYY-MM-DD"},
                },
                "required": ["trade_date"],
            },
        ),
        ToolSpec(
            name="get_emotion_indicators_trend",
            description="拉取最近 N 天的情绪指标趋势（按 trade_date DESC）。建议 days≥5 看多日趋势而非单日截面。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "end_date": {"type": "string", "description": "截止日期 YYYY-MM-DD"},
                    "days": {"type": "integer", "description": "天数,默认10,范围1-60", "default": 10},
                },
                "required": ["end_date"],
            },
        ),
        ToolSpec(
            name="get_strong_repair_leaders",
            description="拉取强修复领涨板块（强势修复龙头候选）。无参数。",
            category="Stock",
            parameters={"type": "object", "properties": {}},
        ),
        ToolSpec(
            name="get_sector_rotation",
            description="拉取当日板块轮动表现（按涨跌幅排序）。参数 trade_date=YYYY-MM-DD。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "trade_date": {"type": "string", "description": "交易日期 YYYY-MM-DD"},
                },
                "required": ["trade_date"],
            },
        ),
        ToolSpec(
            name="get_sector_heat_distribution",
            description="拉取板块涨停时段分布（用于分析板块高潮/退潮节奏）。参数 trade_date=YYYY-MM-DD。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "trade_date": {"type": "string", "description": "交易日期 YYYY-MM-DD"},
                },
                "required": ["trade_date"],
            },
        ),
        ToolSpec(
            name="get_resistant_sectors",
            description="拉取抗跌板块（大盘下跌时相对抗跌的板块）。参数 trade_date=YYYY-MM-DD。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "trade_date": {"type": "string", "description": "交易日期 YYYY-MM-DD"},
                },
                "required": ["trade_date"],
            },
        ),
        ToolSpec(
            name="get_sector_leaders",
            description="拉取指定板块的龙头股候选。参数 sector_name=板块名。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "sector_name": {"type": "string", "description": "板块名,如'半导体'"},
                },
                "required": ["sector_name"],
            },
        ),
        ToolSpec(
            name="get_sector_divergence",
            description="拉取板块高潮后分歧数据。参数 trade_date=YYYY-MM-DD。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "trade_date": {"type": "string", "description": "交易日期 YYYY-MM-DD"},
                },
                "required": ["trade_date"],
            },
        ),
        ToolSpec(
            name="get_sector_history",
            description="拉取板块多日表现数据。sector_name 为空时返回全板块。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "sector_name": {"type": "string", "description": "板块名(空字符串=全板块)"},
                    "days": {"type": "integer", "description": "天数,默认10,范围1-60", "default": 10},
                },
            },
        ),
        ToolSpec(
            name="get_watchlist",
            description="拉取当前活跃的观察池（用户关注/系统标记的活跃股票）。无参数。",
            category="Stock",
            parameters={"type": "object", "properties": {}},
        ),
        ToolSpec(
            name="get_stock_daily",
            description="拉取个股多日 K 线数据。参数 stock_code=股票代码, days=天数(默认30)。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "股票代码,如'000001'"},
                    "days": {"type": "integer", "description": "天数,默认30,范围1-60", "default": 30},
                },
                "required": ["stock_code"],
            },
        ),
        ToolSpec(
            name="get_signal_stocks",
            description="拉取今日新信号股（系统检测到的潜在机会）。参数 trade_date=YYYY-MM-DD。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "trade_date": {"type": "string", "description": "交易日期 YYYY-MM-DD"},
                },
                "required": ["trade_date"],
            },
        ),
        ToolSpec(
            name="get_limit_stocks",
            description="拉取当日涨停股池（含连板数、炸板、首封/末封时间、有效涨停判定）。参数 trade_date=YYYY-MM-DD。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "trade_date": {"type": "string", "description": "交易日期 YYYY-MM-DD"},
                },
                "required": ["trade_date"],
            },
        ),
        ToolSpec(
            name="get_correlation",
            description="庄股/抱团股识别（周复盘专用）。参数 end_date=YYYY-MM-DD, days=回看天数(默认5)。",
            category="Stock",
            parameters={
                "type": "object",
                "properties": {
                    "end_date": {"type": "string", "description": "截止日期 YYYY-MM-DD"},
                    "days": {"type": "integer", "description": "回看天数,默认5,范围1-30", "default": 5},
                },
                "required": ["end_date"],
            },
        ),
    ]


def get_stock_handlers() -> dict[str, ToolHandler]:
    return {
        "get_market_snapshot": _get_market_snapshot,
        "get_emotion_indicators": _get_emotion_indicators,
        "get_emotion_indicators_trend": _get_emotion_indicators_trend,
        "get_strong_repair_leaders": _get_strong_repair_leaders,
        "get_sector_rotation": _get_sector_rotation,
        "get_sector_heat_distribution": _get_sector_heat_distribution,
        "get_resistant_sectors": _get_resistant_sectors,
        "get_sector_leaders": _get_sector_leaders,
        "get_sector_divergence": _get_sector_divergence,
        "get_sector_history": _get_sector_history,
        "get_watchlist": _get_watchlist,
        "get_stock_daily": _get_stock_daily,
        "get_signal_stocks": _get_signal_stocks,
        "get_limit_stocks": _get_limit_stocks,
        "get_correlation": _get_correlation,
    }
