"""limit_broken_fetcher 单元测试——mock akshare 验证 limit_type='broken' 写入。

设计要点（AGENTS.md §6）：
- 与 limit_fetcher.test_fetchers.py 同构：patch akshare_client.ak 函数
- 用 tmp_path + init_db 走真实 SQL upsert 路径
- 验证 DTO 字段映射：limit_type='broken', consecutive_boards=0, is_valid_limit_up=False
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pandas as pd
import pytest

from infrastructure.persistence.connection import get_connection
from infrastructure.persistence.database import init_db, reset_connection


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_limit_broken_fetcher.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def _fake_broken_df() -> pd.DataFrame:
    """akshare.stock_zt_pool_dtgc_em 返回的模拟 DataFrame。"""
    return pd.DataFrame(
        [
            {
                "代码": "600000",
                "名称": "浦发银行",
                "涨跌幅": 9.5,
                "最新价": 12.5,
                "最后封板时间": "14:35:21",
                "开板次数": 2,
            },
            {
                "代码": "600001",
                "名称": "邯郸钢铁",
                "涨跌幅": 9.8,
                "最新价": 5.5,
                "最后封板时间": "13:12:45",
                "开板次数": 1,
            },
            {
                "代码": "600002",
                "名称": "齐鲁石化",
                "涨跌幅": 9.9,
                "最新价": 6.8,
                "最后封板时间": "10:30:00",
                "开板次数": 3,
            },
        ]
    )


@pytest.mark.asyncio
async def test_limit_broken_fetcher_writes_broken_stocks(tmp_db) -> None:
    """fetcher 正常路径：akshare 返 3 行炸板 → upsert → 返回 3。"""
    from infrastructure.stock.cache_repository import CacheRepository
    from infrastructure.stock.limit_broken_fetcher import run

    repo = CacheRepository(get_connection(tmp_db))
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_dtgc_em.return_value = _fake_broken_df()
        count = await run("20260731", repo)

    assert count == 3
    rows = repo.select_limit_stocks(trade_date="20260731")
    assert len(rows) == 3
    assert {r.stock_code for r in rows} == {"600000", "600001", "600002"}
    for row in rows:
        assert row.limit_type == "broken"
        assert row.consecutive_boards == 0
        assert row.is_valid_limit_up is False
        assert row.first_limit_time is None
    assert rows[0].last_limit_time == "14:35:21"
    assert rows[0].open_count == 2


@pytest.mark.asyncio
async def test_limit_broken_fetcher_handles_empty_result(tmp_db) -> None:
    """fetcher 对空数据（非交易日/数据未同步）返回 0 且不污染 cache。"""
    from infrastructure.stock.cache_repository import CacheRepository
    from infrastructure.stock.limit_broken_fetcher import run

    repo = CacheRepository(get_connection(tmp_db))
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_dtgc_em.return_value = pd.DataFrame()
        count = await run("20260731", repo)

    assert count == 0
    assert repo.select_limit_stocks(trade_date="20260731") == []


@pytest.mark.asyncio
async def test_limit_broken_fetcher_returns_zero_on_akshare_error(tmp_db) -> None:
    """fetcher 容错：akshare 抛具体异常 → 包 AkshareFetchError → 返回 0。"""
    from infrastructure.stock.cache_repository import CacheRepository
    from infrastructure.stock.limit_broken_fetcher import run

    repo = CacheRepository(get_connection(tmp_db))
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_dtgc_em.side_effect = ValueError("network down")
        count = await run("20260731", repo)

    assert count == 0
    assert repo.select_limit_stocks(trade_date="20260731") == []


@pytest.mark.asyncio
async def test_limit_broken_fetcher_is_idempotent_on_replay(tmp_db) -> None:
    """fetcher 重放同 trade_date 应 upsert（覆盖式），不重复写入。"""
    from infrastructure.stock.cache_repository import CacheRepository
    from infrastructure.stock.limit_broken_fetcher import run

    repo = CacheRepository(get_connection(tmp_db))
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_dtgc_em.return_value = _fake_broken_df()
        await run("20260731", repo)
        first_count = len(repo.select_limit_stocks(trade_date="20260731"))

        await run("20260731", repo)
        second_count = len(repo.select_limit_stocks(trade_date="20260731"))

    assert first_count == 3
    assert second_count == 3  # upsert：仍是 3 行
