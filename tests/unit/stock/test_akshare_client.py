"""Task 2 失败测试：akshare 客户端 + StockDataSource 协议 + 启发式判定。

覆盖：
- is_valid_limit_up 一次性封死 vs 炸板回封
- fetch_zt_pool 把 akshare DataFrame 转为 LimitStock DTO
- akshare 抛具体异常时，包装为 AkshareFetchError 并保留异常链
- StockDataSource 协议定义 15 个方法（含周复盘专用 get_correlation）

不访问真实网络——全部 mock akshare 函数。
运行前 domain/stock/ports.py、domain/stock/models.py、
infrastructure/stock/akshare_client.py 不存在，本测试应全部失败。
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest


def test_is_valid_limit_up_one_shot_seal() -> None:
    """一次性封死（炸板次数=0 且 首封=末封时间）→ 有效涨停。"""
    from infrastructure.stock.akshare_client import is_valid_limit_up

    assert (
        is_valid_limit_up(open_count=0, first_time="09:30:00", last_time="09:30:00")
        is True
    )


def test_is_valid_limit_up_broken_and_resealed() -> None:
    """炸板后回封（首封≠末封）→ 无效涨停。"""
    from infrastructure.stock.akshare_client import is_valid_limit_up

    assert (
        is_valid_limit_up(open_count=1, first_time="09:30:00", last_time="14:20:00")
        is False
    )


def test_is_valid_limit_up_missing_times_returns_false() -> None:
    """首末时间为空 → 无效涨停。"""
    from infrastructure.stock.akshare_client import is_valid_limit_up

    assert is_valid_limit_up(open_count=0, first_time=None, last_time=None) is False
    assert is_valid_limit_up(open_count=0, first_time="09:30:00", last_time=None) is False


def test_fetch_zt_pool_converts_dataframe_to_dto() -> None:
    """fetch_zt_pool 必须把 akshare DataFrame 转换为 LimitStock DTO 列表。"""
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
                "首次封板时间": "10:00:00",
                "最后封板时间": "14:30:00",
                "炸板次数": 2,
                "连板数": 3,
            },
        ]
    )
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_em.return_value = fake_df
        from infrastructure.stock.akshare_client import fetch_zt_pool

        result = fetch_zt_pool("20260728")

    assert len(result) == 2
    assert result[0].stock_code == "000001"
    assert result[0].stock_name == "平安银行"
    assert result[0].consecutive_boards == 1
    assert result[0].is_valid_limit_up is True
    assert result[1].stock_code == "000002"
    assert result[1].is_valid_limit_up is False


def test_fetch_zt_pool_akshare_error_preserves_chain() -> None:
    """akshare 抛具体异常时必须捕获并包装为 AkshareFetchError，保留异常链。"""
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_em.side_effect = ValueError("network error")
        from infrastructure.stock.akshare_client import AkshareFetchError, fetch_zt_pool

        with pytest.raises(AkshareFetchError) as exc_info:
            fetch_zt_pool("20260728")
    assert isinstance(exc_info.value.__cause__, ValueError)
    assert "network error" in str(exc_info.value.__cause__)


def test_fetch_zt_pool_request_error_preserves_chain() -> None:
    """网络层 requests.RequestException 也必须被包装保留异常链。"""
    import requests

    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_em.side_effect = requests.ConnectionError("timeout")
        from infrastructure.stock.akshare_client import AkshareFetchError, fetch_zt_pool

        with pytest.raises(AkshareFetchError) as exc_info:
            fetch_zt_pool("20260728")
    assert isinstance(exc_info.value.__cause__, requests.ConnectionError)


def test_stock_data_source_protocol_has_required_methods() -> None:
    """StockDataSource 协议必须定义 16 个方法（含 Task 18 新增的非交易日回退）。"""
    from domain.stock.ports import StockDataSource

    required = {
        "get_market_snapshot",
        "get_emotion_indicators",
        "get_emotion_indicators_trend",
        "get_watchlist",
        "get_stock_daily",
        "get_signal_stocks",
        "get_sector_rotation",
        "get_sector_heat_distribution",
        "get_strong_repair_leaders",
        "get_resistant_sectors",
        "get_sector_leaders",
        "get_sector_divergence",
        "get_correlation",
        "get_sector_history",
        "get_limit_stocks",
        "get_latest_trade_date_with_data",  # Task 18
    }
    methods = set(dir(StockDataSource))
    missing = required - methods
    assert not missing, f"StockDataSource 缺失方法: {missing}"


def test_akshare_client_implements_protocol() -> None:
    """AkshareClient 必须结构上满足 StockDataSource 协议（含 16 个方法名）。"""
    from infrastructure.stock.akshare_client import AkshareClient

    client = AkshareClient()
    expected = {
        "get_market_snapshot",
        "get_emotion_indicators",
        "get_emotion_indicators_trend",
        "get_watchlist",
        "get_stock_daily",
        "get_signal_stocks",
        "get_sector_rotation",
        "get_sector_heat_distribution",
        "get_strong_repair_leaders",
        "get_resistant_sectors",
        "get_sector_leaders",
        "get_sector_divergence",
        "get_correlation",
        "get_sector_history",
        "get_limit_stocks",
        "get_latest_trade_date_with_data",  # Task 18 stub
    }
    missing = {m for m in expected if not hasattr(client, m)}
    assert not missing, f"AkshareClient 缺方法: {missing}"
