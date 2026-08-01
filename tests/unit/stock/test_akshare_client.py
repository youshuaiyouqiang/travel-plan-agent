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


# ── Task A：pct_chg 自算测试 ────────────────────────────────────


def _fake_real_index_df(symbol: str) -> pd.DataFrame:
    """模拟 akshare 真实返回的指数日线（无 pct_chg 字段）。

    akshare ``stock_zh_index_daily`` 实际返回的列：
    ['date', 'open', 'high', 'low', 'close', 'volume']
    不含 pct_chg 字段——这是 v1.0 文档里根因 B 的 bug 触发场景。
    """
    base_close = {
        "sh000001": 3500.0,
        "sz399001": 11800.0,
        "sz399006": 2400.0,
    }
    c0 = base_close.get(symbol, 3500.0)
    # 构造 3 行：前日 close 3500 → 当日 close 3520 → 涨跌幅应 = +0.5714%
    return pd.DataFrame(
        [
            {"date": "2026-07-28", "open": c0 - 10, "high": c0 + 5,
             "low": c0 - 15, "close": c0, "volume": 4.0e10},
            {"date": "2026-07-29", "open": c0, "high": c0 + 10,
             "low": c0 - 5, "close": c0 + 5, "volume": 4.2e10},
            {"date": "2026-07-30", "open": c0 + 5, "high": c0 + 30,
             "low": c0 - 10, "close": c0 + 20, "volume": 4.5e10},
        ]
    )


class TestFetchMarketIndexPctChgCalc:
    """Task A：akshare 不返回 pct_chg 时必须自己计算。

    现有测试 mock 数据带 pct_chg 字段（不真实），掩盖了 bug。
    本测试用 akshare 真实返回结构（无 pct_chg 列）断言：
    - pct_chg 不能是 None
    - pct_chg 必须等于 (close - prev_close) / prev_close * 100
    - 第一行（无前日）pct_chg 应为 None
    """

    def test_pct_chg_is_calculated_when_akshare_omits_field(self) -> None:
        """akshare 真实返回（无 pct_chg 列）→ 必须自己算 pct_chg。"""
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_index_daily.side_effect = _fake_real_index_df
            from infrastructure.stock.akshare_client import fetch_market_index

            rows = fetch_market_index("20260730")

        assert len(rows) == 3
        # 各指数 base close 不同，pct_chg 也不同；按 index_code 校验
        # _fake_real_index_df: 前日 close=base+5, 当日 close=base+20
        # pct_chg = (base+20 - (base+5)) / (base+5) * 100 = 15/(base+5)*100
        base_close = {"sh000001": 3500.0, "sz399001": 11800.0, "sz399006": 2400.0}
        for r in rows:
            # 当日（2026-07-30）必须有 pct_chg，不能是 None
            if r.trade_date == "20260730":
                assert r.pct_chg is not None, (
                    f"pct_chg 不能为 None（index_code={r.index_code}）"
                )
                base = base_close[r.index_code]
                expected = 15.0 / (base + 5.0) * 100
                assert abs(r.pct_chg - expected) < 0.001, (
                    f"pct_chg 计算错误（index_code={r.index_code}, "
                    f"expected≈{expected}, got={r.pct_chg})"
                )

    def test_pct_chg_none_for_first_row_without_prev(self) -> None:
        """第一行无前日 close → pct_chg 应为 None（不能算）。"""
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            # 让 df 只返回 1 行（首日无前日）
            mock_ak.stock_zh_index_daily.return_value = pd.DataFrame(
                [{"date": "2026-07-30", "open": 3500.0, "high": 3530.0,
                  "low": 3490.0, "close": 3520.0, "volume": 4.5e10}]
            )
            from infrastructure.stock.akshare_client import fetch_market_index

            rows = fetch_market_index("20260730")

        assert len(rows) == 3
        # 第一行（无前日）pct_chg 应为 None
        first_row = rows[0]
        assert first_row.pct_chg is None, (
            f"首行无前日 close，pct_chg 应为 None，got={first_row.pct_chg}"
        )

    def test_pct_chg_zero_when_close_unchanged(self) -> None:
        """当日 close 等于前日 close → pct_chg 应为 0.0（非 None）。"""
        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_index_daily.return_value = pd.DataFrame(
                [
                    {"date": "2026-07-29", "open": 3500.0, "high": 3510.0,
                     "low": 3490.0, "close": 3500.0, "volume": 4.0e10},
                    {"date": "2026-07-30", "open": 3500.0, "high": 3505.0,
                     "low": 3495.0, "close": 3500.0, "volume": 4.2e10},
                ]
            )
            from infrastructure.stock.akshare_client import fetch_market_index

            rows = fetch_market_index("20260730")

        assert len(rows) == 3
        for r in rows:
            if r.trade_date == "20260730":
                assert r.pct_chg == 0.0, (
                    f"close 不变时 pct_chg 应为 0.0，got={r.pct_chg}"
                )
