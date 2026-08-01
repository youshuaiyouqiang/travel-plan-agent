"""Task 11 失败测试：stock tool 格式归一化。

覆盖（4-step 模式：先失败再实现）：
- 全部 15 个 tool spec 的 ``trade_date`` / ``end_date`` 描述必须说
  YYYYMMDD（与 DB / fetcher 一致），且不应再写 YYYY-MM-DD
- handler 入口对 dashed 输入 "2026-07-30" 必须归一化为 compact "20260730"
  并命中 DB（不只是不报错，而是要真的查到行）
- 非法格式必须显式返回 is_error=True
- compact 输入维持原行为不变
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from domain.stock.models import LimitStock
from infrastructure.persistence.database import init_db, reset_connection
from infrastructure.stock.cache_repository import CacheRepository
from infrastructure.tools.adapters import stock as stock_tools


# ── fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_tool_format.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _seed_limit_stocks(repo: CacheRepository, trade_date: str, count: int) -> None:
    """往指定交易日塞 count 行 limit_stocks_daily 数据。"""
    stocks = [
        LimitStock(
            trade_date=trade_date,
            stock_code=f"{600000 + i:06d}",
            stock_name=f"测试{i}",
            limit_type="up",
            consecutive_boards=1,
            first_limit_time="10:00:00",
            last_limit_time="10:00:00",
            open_count=0,
            is_valid_limit_up=True,
        )
        for i in range(count)
    ]
    repo.upsert_limit_stocks(trade_date=trade_date, stocks=stocks)


def _seed_market_index(repo: CacheRepository, trade_date: str) -> None:
    """塞 3 个指数到 market_index_daily（get_market_snapshot 依赖）。"""
    from infrastructure.persistence.connection import get_connection

    conn = get_connection()
    # emotion_daily 走 raw SQL；market_index_daily 同理（cache_repo 没有
    # public upsert_index 接口）
    for code in ("000001", "399001", "399006"):
        conn.execute(
            "INSERT OR REPLACE INTO market_index_daily "
            "(trade_date, index_code, close, pct_chg) VALUES (?, ?, ?, ?)",
            (trade_date, code, 3000.0 + int(code), 1.5),
        )
    conn.commit()


# ── spec 描述：必须是 YYYYMMDD ──────────────────────────


class TestToolSpecFormat:
    """所有 15 个 tool 的 spec 描述必须说 YYYYMMDD（与 DB 一致）。"""

    def test_all_trade_date_specs_use_compact_format(self) -> None:
        specs = stock_tools.get_stock_specs()
        # 至少 15 个 spec（与 stock_tools.get_stock_handlers 对齐）
        assert len(specs) >= 15

        violations: list[str] = []
        for spec in specs:
            params = spec.parameters.get("properties", {})
            for param_name, param_spec in params.items():
                if param_name in ("trade_date", "end_date"):
                    desc = param_spec.get("description", "")
                    if "YYYYMMDD" not in desc:
                        violations.append(
                            f"{spec.name}/{param_name}: 缺少 YYYYMMDD 描述"
                        )
                    if "YYYY-MM-DD" in desc:
                        violations.append(
                            f"{spec.name}/{param_name}: 不应再说 YYYY-MM-DD"
                        )

        assert violations == [], (
            "ToolSpec 参数描述必须改为 YYYYMMDD（与 DB / fetcher 一致）。\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


# ── handler 归一化：dashed → compact ────────────────────


class TestHandlerNormalizationLimitStocks:
    """get_limit_stocks 必须对 dashed "2026-07-30" 归一化为 "20260730"。"""

    @pytest.mark.asyncio
    async def test_dashed_input_hits_db(
        self, tmp_db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from infrastructure.persistence.connection import get_connection
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        conn = get_connection()
        repo = CacheRepository(conn=conn)
        _seed_limit_stocks(repo, trade_date="20260730", count=52)

        test_ds = SqliteStockDataSource(conn=conn)
        monkeypatch.setattr(stock_tools, "_get_data_source", lambda: test_ds)

        # 用 dashed 格式调 handler（模拟 LLM 按 spec 传 "2026-07-30"）
        result = await stock_tools._get_limit_stocks(
            {"trade_date": "2026-07-30"}
        )
        assert result["is_error"] is False
        rows = json.loads(result["content"])
        assert len(rows) == 52, (
            f"dashed 输入应归一化后命中 52 行，实际 {len(rows)} 行 "
            f"（说明 handler 没归一化）"
        )

    @pytest.mark.asyncio
    async def test_compact_input_still_works(
        self, tmp_db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from infrastructure.persistence.connection import get_connection
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        conn = get_connection()
        repo = CacheRepository(conn=conn)
        _seed_limit_stocks(repo, trade_date="20260730", count=52)

        test_ds = SqliteStockDataSource(conn=conn)
        monkeypatch.setattr(stock_tools, "_get_data_source", lambda: test_ds)

        result = await stock_tools._get_limit_stocks(
            {"trade_date": "20260730"}
        )
        assert result["is_error"] is False
        rows = json.loads(result["content"])
        assert len(rows) == 52


class TestHandlerNormalizationMarketSnapshot:
    """get_market_snapshot 必须对 dashed 归一化。"""

    @pytest.mark.asyncio
    async def test_dashed_input_hits_db(
        self, tmp_db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from infrastructure.persistence.connection import get_connection
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        conn = get_connection()
        repo = CacheRepository(conn=conn)
        _seed_market_index(repo, trade_date="20260730")

        test_ds = SqliteStockDataSource(conn=conn)
        monkeypatch.setattr(stock_tools, "_get_data_source", lambda: test_ds)

        result = await stock_tools._get_market_snapshot(
            {"trade_date": "2026-07-30"}
        )
        assert result["is_error"] is False
        snapshot = json.loads(result["content"])
        # 命中 DB 应有 sh_index (000001) / sz_index (399001) / cyb_index (399006)
        assert snapshot["sh_index"] is not None, (
            "dashed 输入应归一化后命中 sh_index；为 None 说明未归一化"
        )


class TestHandlerNormalizationEmotion:
    """get_emotion_indicators 必须对 dashed 归一化。"""

    @pytest.mark.asyncio
    async def test_dashed_input_uses_default_emotion_when_no_data(
        self, tmp_db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """emotion_daily 暂无 fetcher；dashed 输入不应抛错，应返回默认 0 行 DTO。"""
        from infrastructure.persistence.connection import get_connection
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        conn = get_connection()
        test_ds = SqliteStockDataSource(conn=conn)
        monkeypatch.setattr(stock_tools, "_get_data_source", lambda: test_ds)

        # emotion_daily 表为空，handler 应返回默认 DTO（不抛错）
        result = await stock_tools._get_emotion_indicators(
            {"trade_date": "2026-07-30"}
        )
        assert result["is_error"] is False
        d = json.loads(result["content"])
        # limit_up_count 等默认 0
        assert d["limit_up_count"] == 0


class TestHandlerNormalizationInvalid:
    """非法格式必须显式返回 is_error=True。"""

    @pytest.mark.asyncio
    async def test_invalid_format_returns_error(
        self, tmp_db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from infrastructure.persistence.connection import get_connection
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        conn = get_connection()
        test_ds = SqliteStockDataSource(conn=conn)
        monkeypatch.setattr(stock_tools, "_get_data_source", lambda: test_ds)

        # 带斜杠不是 YYYY-MM-DD 也不是 YYYYMMDD
        result = await stock_tools._get_limit_stocks(
            {"trade_date": "2026/07/30"}
        )
        assert result["is_error"] is True
        assert "trade_date" in result["content"]

    @pytest.mark.asyncio
    async def test_wrong_length_returns_error(
        self, tmp_db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from infrastructure.persistence.connection import get_connection
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        conn = get_connection()
        test_ds = SqliteStockDataSource(conn=conn)
        monkeypatch.setattr(stock_tools, "_get_data_source", lambda: test_ds)

        result = await stock_tools._get_limit_stocks(
            {"trade_date": "2026073"}  # 7 位
        )
        assert result["is_error"] is True


# ── 端到端：agent 风格的 dashed 输入应能命中 ──────────────


class TestEndToEndAgentStyle:
    """模拟 LLM 按 spec 传 dashed 输入，验证整链路通畅。"""

    @pytest.mark.asyncio
    async def test_full_pipeline_dashed_input(
        self, tmp_db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from infrastructure.persistence.connection import get_connection
        from infrastructure.stock.sqlite_data_source import SqliteStockDataSource

        conn = get_connection()
        repo = CacheRepository(conn=conn)
        _seed_limit_stocks(repo, trade_date="20260730", count=52)

        test_ds = SqliteStockDataSource(conn=conn)
        monkeypatch.setattr(stock_tools, "_get_data_source", lambda: test_ds)

        # 模拟 LLM 一次性调 4 个工具，全用 dashed 输入
        for tool_name, args in [
            ("_get_limit_stocks", {"trade_date": "2026-07-30"}),
            ("_get_market_snapshot", {"trade_date": "2026-07-30"}),
            ("_get_emotion_indicators", {"trade_date": "2026-07-30"}),
            ("_get_sector_rotation", {"trade_date": "2026-07-30"}),
        ]:
            handler = getattr(stock_tools, tool_name)
            result = await handler(args)
            assert result["is_error"] is False, (
                f"{tool_name} dashed 输入应归一化后命中；got {result}"
            )
