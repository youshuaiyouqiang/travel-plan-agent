"""Task 18 失败测试：get_latest_trade_date_with_data 端口 + 工具。

Issue 2：stock agent 在周六/节假日拿到"今天"是空数据时，应该
自动回退到"最近一个有数据的交易日"，但目前 port 缺少该查询，
工具集没注册，LLM 只能硬着头皮写"今日复盘（数据缺失）"。

覆盖：
- port 方法存在：domain.stock.ports.StockDataSource
- SqliteStockDataSource 实现：从 market_index_daily 取 MAX(trade_date)，
  无数据返 None
- AkshareClient 至少有 stub（NotImplementedError），不阻塞其他协议检查
- 工具 spec/handler：get_stock_specs/get_stock_handlers 注册到位
- 工具调用：handler 返回 ``{"latest_trade_date": "YYYYMMDD"}`` JSON
- yaml 注册：interface.tools 含此工具
- domain/stock/tools.build_stock_tools：日/周复盘都含此工具
- 协议方法计数：test_akshare_client.py 的 required 集合与之一致
"""
from __future__ import annotations

import inspect
import json
import os
from typing import Any

import pytest
import yaml

from config import settings
from domain.stock.ports import StockDataSource
from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import init_db, reset_connection


# ── fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_latest_trade_date.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _seed_market_index(conn, dates: list[str]) -> None:
    """往 market_index_daily 塞指定日期的 3 个指数（最新日期必须在 dates 末尾）。"""
    for td in dates:
        for code in ("000001", "399001", "399006"):
            conn.execute(
                "INSERT OR REPLACE INTO market_index_daily "
                "(trade_date, index_code, close, pct_chg) "
                "VALUES (?, ?, ?, ?)",
                (td, code, 3000.0 + int(code), 1.5),
            )
    conn.commit()


# ── 1. port 协议方法存在 ─────────────────────────────────


class TestPortContract:
    def test_port_declares_method(self) -> None:
        """StockDataSource 协议必须声明 get_latest_trade_date_with_data。"""
        assert hasattr(StockDataSource, "get_latest_trade_date_with_data"), (
            "StockDataSource 端口缺 get_latest_trade_date_with_data 方法"
        )

    def test_port_method_signature(self) -> None:
        """get_latest_trade_date_with_data 必须是无参的 async 方法。"""
        method = getattr(StockDataSource, "get_latest_trade_date_with_data", None)
        assert method is not None
        sig = inspect.signature(method)
        # 仅 self，无必填参数
        required_params = [
            p for p in sig.parameters.values()
            if p.default is inspect.Parameter.empty and p.name != "self"
        ]
        assert required_params == [], (
            f"get_latest_trade_date_with_data 必须无参数，意外参数: "
            f"{[p.name for p in required_params]}"
        )

    def test_akshare_client_has_stub(self) -> None:
        """AkshareClient 至少要有 stub（NotImplementedError）以满足协议。"""
        from infrastructure.stock.akshare_client import AkshareClient

        client = AkshareClient()
        assert hasattr(client, "get_latest_trade_date_with_data"), (
            "AkshareClient 缺 get_latest_trade_date_with_data 方法"
        )


# ── 2. SqliteStockDataSource 实现 ────────────────────────


class TestSqliteLatestTradeDate:
    @pytest.mark.asyncio
    async def test_returns_max_trade_date(self, tmp_db) -> None:
        """多日数据 → 返回 MAX(trade_date)（不一定是最近的日历日）。"""
        _seed_market_index(
            get_connection(),
            ["20260728", "20260729", "20260730", "20260731"],
        )

        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        ds = SqliteStockDataSource(conn=get_connection())
        result = await ds.get_latest_trade_date_with_data()
        assert result == "20260731"

    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self, tmp_db) -> None:
        """market_index_daily 空 → 返 None（不要抛错或返 ''）。"""
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        ds = SqliteStockDataSource(conn=get_connection())
        result = await ds.get_latest_trade_date_with_data()
        assert result is None

    @pytest.mark.asyncio
    async def test_ignores_non_market_index_tables(self, tmp_db) -> None:
        """只查 market_index_daily；其它表有更新日期时不应影响返回值。"""
        conn = get_connection()
        # market_index_daily 最新到 20260725
        _seed_market_index(conn, ["20260723", "20260725"])
        # 其它表更新到更晚日期（不应影响）
        conn.execute(
            "INSERT INTO sector_daily (trade_date, sector_code, sector_name) "
            "VALUES (?, ?, ?)",
            ("20260730", "BK0001", "测试板块"),
        )
        conn.commit()

        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        ds = SqliteStockDataSource(conn=get_connection())
        result = await ds.get_latest_trade_date_with_data()
        # 必须从 market_index_daily 取，不被 sector_daily 干扰
        assert result == "20260725"


# ── 3. handler + spec ────────────────────────────────────


class TestToolSpecAndHandler:
    def test_spec_exists(self) -> None:
        """get_stock_specs 必须包含 get_latest_trade_date_with_data。"""
        from infrastructure.tools.adapters.stock import get_stock_specs

        names = [s.name for s in get_stock_specs()]
        assert "get_latest_trade_date_with_data" in names, (
            f"get_stock_specs 缺工具: {names}"
        )

    def test_spec_no_parameters(self) -> None:
        """无参数工具：properties 必须为空对象。"""
        from infrastructure.tools.adapters.stock import get_stock_specs

        spec = next(
            s for s in get_stock_specs()
            if s.name == "get_latest_trade_date_with_data"
        )
        params = spec.parameters or {}
        # 无必填字段
        assert params.get("required", []) == []
        # properties 为空（不接受 trade_date 等参数）
        assert params.get("properties", {}) == {}

    def test_handler_exists(self) -> None:
        """get_stock_handlers 必须包含 get_latest_trade_date_with_data。"""
        from infrastructure.tools.adapters.stock import get_stock_handlers

        handlers = get_stock_handlers()
        assert "get_latest_trade_date_with_data" in handlers

    @pytest.mark.asyncio
    async def test_handler_returns_json_with_date(
        self, tmp_db, monkeypatch
    ) -> None:
        """handler 必须返 is_error=False + content 为含 latest_trade_date 的 JSON。"""
        _seed_market_index(get_connection(), ["20260730", "20260731"])
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource
        from infrastructure.tools.adapters import stock as stock_tools

        test_ds = SqliteStockDataSource(conn=get_connection())
        monkeypatch.setattr(stock_tools, "_get_data_source", lambda: test_ds)

        handler = stock_tools.get_stock_handlers()[
            "get_latest_trade_date_with_data"
        ]
        result = await handler({})
        assert result["is_error"] is False
        # 解析 JSON 内容
        payload = json.loads(result["content"])
        assert payload == {"latest_trade_date": "20260731"}

    @pytest.mark.asyncio
    async def test_handler_returns_null_when_empty(
        self, tmp_db, monkeypatch
    ) -> None:
        """缓存无数据时返 latest_trade_date=null（不要报错）。"""
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource
        from infrastructure.tools.adapters import stock as stock_tools

        test_ds = SqliteStockDataSource(conn=get_connection())
        monkeypatch.setattr(stock_tools, "_get_data_source", lambda: test_ds)

        handler = stock_tools.get_stock_handlers()[
            "get_latest_trade_date_with_data"
        ]
        result = await handler({})
        assert result["is_error"] is False
        payload = json.loads(result["content"])
        assert payload == {"latest_trade_date": None}


# ── 4. yaml / domain.stock.tools 装配 ────────────────────


class TestToolWiring:
    def test_yaml_contains_tool(self) -> None:
        """stock-review/agents/openai.yaml 必须列出此工具。"""
        path = (
            settings.skills_dir
            / "stock-review"
            / "agents"
            / "openai.yaml"
        )
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        tools = data["interface"]["tools"]
        assert "get_latest_trade_date_with_data" in tools, (
            f"openai.yaml 缺工具: {tools}"
        )

    def test_build_stock_tools_common_contains(self) -> None:
        """daily + weekly 都必须含此工具（不依赖 session_mode 切换）。"""
        from domain.stock.tools import build_stock_tools

        daily = build_stock_tools(session_mode="daily")
        weekly = build_stock_tools(session_mode="weekly")
        assert "get_latest_trade_date_with_data" in daily
        assert "get_latest_trade_date_with_data" in weekly
        # 不能影响原有的 daily/weekly 数量断言（仍是 14 + 1）
        assert len(daily) == 15
        assert len(weekly) == 16


# ── 5. prompt 必须有非交易日回退说明 ──────────────────────


class TestPromptMentionsNonTradingDay:
    def test_skill_md_mentions_non_trading_day(self) -> None:
        """SKILL.md 必须明确指示 LLM 在非交易日调本工具。"""
        path = (
            settings.skills_dir
            / "stock-review"
            / "SKILL.md"
        )
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # 关键短语必须出现
        for keyword in ("非交易日", "get_latest_trade_date_with_data"):
            assert keyword in content, (
                f"SKILL.md 缺关键词: {keyword!r}"
            )

    def test_stock_yaml_system_prompt_mentions(self) -> None:
        """application/builtin_agents/stock.yaml system_prompt 必须含回退说明。"""
        path = settings.builtin_agents_dir / "stock.yaml"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        prompt = data["system_prompt"]
        # system_prompt 必须同时提到工具名 + 触发条件
        assert "get_latest_trade_date_with_data" in prompt, (
            "stock.yaml system_prompt 未引用 get_latest_trade_date_with_data"
        )
        assert "非交易日" in prompt, (
            "stock.yaml system_prompt 未说明非交易日回退"
        )
