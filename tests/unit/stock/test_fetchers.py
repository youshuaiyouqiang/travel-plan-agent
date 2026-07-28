"""Task 3 失败测试：fetcher 模块——以 limit_fetcher 为样本。

覆盖：
- 正常路径：akshare 返 DataFrame → 写 cache → 返回条数
- 错误路径：akshare 抛异常 → 任务不抛异常，返回 0

不访问真实网络——mock akshare。
运行前 infrastructure/stock/limit_fetcher.py 不存在，本测试应全部失败。
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
    db_path = tmp_path / "test_fetcher.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_limit_fetcher_writes_to_cache(tmp_db) -> None:
    """limit_fetcher.run：akshare → cache → 返回条数。"""
    from infrastructure.stock.cache_repository import CacheRepository
    from infrastructure.stock.limit_fetcher import run

    fake_df = pd.DataFrame(
        [
            {
                "代码": "000001",
                "名称": "平安银行",
                "涨跌幅": 10.0,
                "最新价": 15.0,
                "封板资金": 1000000,
                "首次封板时间": "09:30:00",
                "最后封板时间": "09:30:00",
                "炸板次数": 0,
                "连板数": 1,
            },
            {
                "代码": "000002",
                "名称": "万科A",
                "涨跌幅": 10.0,
                "最新价": 8.0,
                "封板资金": 500000,
                "首次封板时间": "09:30:00",
                "最后封板时间": "14:20:00",
                "炸板次数": 1,
                "连板数": 2,
            },
        ]
    )
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_em.return_value = fake_df
        repo = CacheRepository(get_connection(tmp_db))
        count = await run("20260728", repo)

    assert count == 2
    rows = repo.select_limit_stocks(trade_date="20260728")
    assert len(rows) == 2
    assert {r.stock_code for r in rows} == {"000001", "000002"}


@pytest.mark.asyncio
async def test_limit_fetcher_returns_zero_on_akshare_error(tmp_db) -> None:
    """akshare 抛具体异常时：包装→AkshareFetchError→fetcher 返回 0，不中断。"""
    from infrastructure.stock.cache_repository import CacheRepository
    from infrastructure.stock.limit_fetcher import run

    repo = CacheRepository(get_connection(tmp_db))
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_em.side_effect = ValueError("network down")
        count = await run("20260728", repo)
    assert count == 0
    # 确认 cache 没被脏写
    assert repo.select_limit_stocks(trade_date="20260728") == []
