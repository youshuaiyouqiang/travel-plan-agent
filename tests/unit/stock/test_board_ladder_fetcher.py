"""Task A2 失败测试：board_ladder_fetcher（从 limit_stocks_daily 聚合）。

设计要点：
- board_ladder_daily 表已建（v021 迁移）但无 fetcher，表一直 0 行
- Task A2 新增 fetcher，从 limit_stocks_daily 聚合按 consecutive_boards 分组：
  - 1 板：N 只
  - 2 板：M 只
  - 3 板：K 只
  - ...
- fetcher 不调 akshare（纯聚合），无需 mock akshare
- 不需要 asyncio.to_thread（无同步 IO）
- 4 类场景：成功 / 无涨停股 / 空分组 / adapter 协议
- 验证 board_ladder_daily 表按连板高度正确分组 + stock_codes 列表完整
"""

from __future__ import annotations

import os

import pytest

from infrastructure.persistence.database import init_db, reset_connection
from infrastructure.persistence.connection import get_connection


# ── fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_board_ladder_fetcher.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _seed_limit_stocks(repo, trade_date: str) -> None:
    """塞 limit_stocks_daily 多只涨停股，含不同连板高度。

    构造数据：
    - 1 板：3 只（000001 / 000002 / 000003）
    - 2 板：2 只（600001 / 600002）
    - 3 板：1 只（300001）
    共 6 只涨停股，应聚合为 3 行 board_ladder。
    """
    from domain.stock.models import LimitStock

    repo.upsert_limit_stocks(
        trade_date=trade_date,
        stocks=[
            # 1 板 × 3
            LimitStock(
                trade_date=trade_date, stock_code="000001", stock_name="股1",
                limit_type="up", consecutive_boards=1,
                first_limit_time="10:00", last_limit_time="10:00",
                open_count=0, is_valid_limit_up=True,
            ),
            LimitStock(
                trade_date=trade_date, stock_code="000002", stock_name="股2",
                limit_type="up", consecutive_boards=1,
                first_limit_time="10:00", last_limit_time="10:00",
                open_count=0, is_valid_limit_up=True,
            ),
            LimitStock(
                trade_date=trade_date, stock_code="000003", stock_name="股3",
                limit_type="up", consecutive_boards=1,
                first_limit_time="10:00", last_limit_time="10:00",
                open_count=0, is_valid_limit_up=True,
            ),
            # 2 板 × 2
            LimitStock(
                trade_date=trade_date, stock_code="600001", stock_name="股4",
                limit_type="up", consecutive_boards=2,
                first_limit_time="10:00", last_limit_time="10:00",
                open_count=0, is_valid_limit_up=True,
            ),
            LimitStock(
                trade_date=trade_date, stock_code="600002", stock_name="股5",
                limit_type="up", consecutive_boards=2,
                first_limit_time="10:00", last_limit_time="10:00",
                open_count=0, is_valid_limit_up=True,
            ),
            # 3 板 × 1
            LimitStock(
                trade_date=trade_date, stock_code="300001", stock_name="股6",
                limit_type="up", consecutive_boards=3,
                first_limit_time="10:00", last_limit_time="10:00",
                open_count=0, is_valid_limit_up=True,
            ),
        ],
    )


# ── TestBoardLadderFetcherSuccess ───────────────────────


class TestBoardLadderFetcherSuccess:
    """limit_stocks_daily 有数据 → 聚合写入 board_ladder_daily。"""

    @pytest.mark.asyncio
    async def test_aggregates_by_consecutive_boards(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.board_ladder_fetcher_adapter import (
            BoardLadderFetcherAdapter,
        )

        adapter = BoardLadderFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        _seed_limit_stocks(repo, trade_date="20260730")

        count = await adapter.run(trade_date="20260730", repo=repo)

        # 6 只涨停股 → 聚合为 3 行（1 板 / 2 板 / 3 板）
        assert count == 3

        rows = repo.select_board_ladder(trade_date="20260730")
        assert len(rows) == 3
        # 按 boards 升序排列方便断言
        by_boards = {r.boards: r for r in rows}
        assert set(by_boards.keys()) == {1, 2, 3}

        # 1 板：3 只
        r1 = by_boards[1]
        assert r1.trade_date == "20260730"
        assert r1.count == 3
        assert set(r1.stock_codes) == {"000001", "000002", "000003"}

        # 2 板：2 只
        r2 = by_boards[2]
        assert r2.count == 2
        assert set(r2.stock_codes) == {"600001", "600002"}

        # 3 板：1 只
        r3 = by_boards[3]
        assert r3.count == 1
        assert r3.stock_codes == ["300001"]


# ── TestBoardLadderFetcherEmpty ─────────────────────────


class TestBoardLadderFetcherEmpty:
    """limit_stocks_daily 该日无数据 → 返 0，board_ladder 不写。"""

    @pytest.mark.asyncio
    async def test_no_limit_stocks_returns_zero(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.board_ladder_fetcher_adapter import (
            BoardLadderFetcherAdapter,
        )

        adapter = BoardLadderFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        # 不塞任何 limit_stocks_daily 数据

        count = await adapter.run(trade_date="20260730", repo=repo)

        assert count == 0
        rows = repo.select_board_ladder(trade_date="20260730")
        assert rows == []


# ── TestBoardLadderFetcherIdempotent ────────────────────


class TestBoardLadderFetcherIdempotent:
    """重复调用应幂等（INSERT OR REPLACE 覆盖旧数据，不重复）。"""

    @pytest.mark.asyncio
    async def test_repeat_run_overwrites_not_duplicates(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.board_ladder_fetcher_adapter import (
            BoardLadderFetcherAdapter,
        )

        adapter = BoardLadderFetcherAdapter()
        repo = CacheRepository(conn=get_connection())
        _seed_limit_stocks(repo, trade_date="20260730")

        # 第一次跑
        await adapter.run(trade_date="20260730", repo=repo)
        # 第二次跑（应覆盖，不重复）
        await adapter.run(trade_date="20260730", repo=repo)

        rows = repo.select_board_ladder(trade_date="20260730")
        # 仍是 3 行（不重复为 6 行）
        assert len(rows) == 3


# ── TestBoardLadderFetcherAdapter ───────────────────────


class TestBoardLadderFetcherAdapter:
    """BoardLadderFetcherAdapter 走 Fetcher 协议。"""

    @pytest.mark.asyncio
    async def test_adapter_runs_through_pipeline(self, tmp_db) -> None:
        from infrastructure.stock.cache_repository import CacheRepository
        from infrastructure.stock.board_ladder_fetcher_adapter import (
            BoardLadderFetcherAdapter,
        )

        adapter = BoardLadderFetcherAdapter()
        # 协议 duck-type 校验
        assert adapter.name == "board_ladder_fetcher"
        assert callable(adapter.run)

        repo = CacheRepository(conn=get_connection())
        _seed_limit_stocks(repo, trade_date="20260730")
        written = await adapter.run(trade_date="20260730", repo=repo)

        assert written == 3
