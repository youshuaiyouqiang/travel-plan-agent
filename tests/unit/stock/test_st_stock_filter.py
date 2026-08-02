"""ST 过滤单测——Bug⑨ 修复。

设计要点（AGENTS.md §6 TDD + §3 业务边界）：
- ``is_st_stock`` 判定函数：含 "ST" / "*ST" / "退" / "退市" / "退整理期" 的股票名
- fetcher 写 limit_stocks_daily 前过滤 ST（普涨停数 = 涨停数 - ST 数）
- emotion_daily 聚合逻辑：天然基于 limit_stocks_daily 自动剔除
"""
from __future__ import annotations



def test_is_st_stock_true_for_st_prefix() -> None:
    """含 ST / *ST 的股名识别为 ST 股。"""
    from domain.stock.heuristics import is_st_stock

    assert is_st_stock("ST 浦发") is True
    assert is_st_stock("*ST 浦发") is True
    assert is_st_stock("ST 国安") is True


def test_is_st_stock_true_for_delisted() -> None:
    """含 退 / 退市 / 退整理期 的股名识别为退市股（不计入涨停数）。"""
    from domain.stock.heuristics import is_st_stock

    assert is_st_stock("退市海润") is True
    assert is_st_stock("退市股") is True
    assert is_st_stock("退整理期 XX") is True


def test_is_st_stock_false_for_normal() -> None:
    """普通股名不识别为 ST。"""
    from domain.stock.heuristics import is_st_stock

    assert is_st_stock("浦发银行") is False
    assert is_st_stock("东方通信") is False
    assert is_st_stock("长盈精密") is False


def test_is_st_stock_false_for_empty() -> None:
    """空股名不识别为 ST（边界：fetcher 容错）。"""
    from domain.stock.heuristics import is_st_stock

    assert is_st_stock("") is False
    assert is_st_stock(None) is False  # type: ignore[arg-type]


def test_akshare_client_fetch_zt_pool_filters_st() -> None:
    """fetch_zt_pool 写入 LimitStock 列表前过滤 ST 股。"""
    from infrastructure.stock.akshare_client import fetch_zt_pool
    import pandas as pd

    fake_df = pd.DataFrame(
        [
            {"代码": "600000", "名称": "浦发银行", "涨跌幅": 10.0,
             "最新价": 12.5, "成交额": 1e8, "振幅": 0,
             "流通市值": 1e10, "总市值": 1e10, "市净率": 1.0,
             "封板资金": 0, "封单量": 0, "封成比": 0,
             "换手率": 1.0, "连板数": 1, "炸板次数": 0,
             "涨停统计": 1, "几天几板": 1, "开板次数": 0,
             "首次封板时间": "10:00:00", "最后封板时间": "10:00:00"},
            {"代码": "600001", "名称": "ST 浦发", "涨跌幅": 5.0,
             "最新价": 12.5, "成交额": 1e8, "振幅": 0,
             "流通市值": 1e10, "总市值": 1e10, "市净率": 1.0,
             "封板资金": 0, "封单量": 0, "封成比": 0,
             "换手率": 1.0, "连板数": 1, "炸板次数": 0,
             "涨停统计": 1, "几天几板": 1, "开板次数": 0,
             "首次封板时间": "10:00:00", "最后封板时间": "10:00:00"},
            {"代码": "600002", "名称": "*ST 国安", "涨跌幅": 5.0,
             "最新价": 12.5, "成交额": 1e8, "振幅": 0,
             "流通市值": 1e10, "总市值": 1e10, "市净率": 1.0,
             "封板资金": 0, "封单量": 0, "封成比": 0,
             "换手率": 1.0, "连板数": 1, "炸板次数": 0,
             "涨停统计": 1, "几天几板": 1, "开板次数": 0,
             "首次封板时间": "10:00:00", "最后封板时间": "10:00:00"},
            {"代码": "600003", "名称": "东方通信", "涨跌幅": 10.0,
             "最新价": 12.5, "成交额": 1e8, "振幅": 0,
             "流通市值": 1e10, "总市值": 1e10, "市净率": 1.0,
             "封板资金": 0, "封单量": 0, "封成比": 0,
             "换手率": 1.0, "连板数": 1, "炸板次数": 0,
             "涨停统计": 1, "几天几板": 1, "开板次数": 0,
             "首次封板时间": "10:00:00", "最后封板时间": "10:00:00"},
        ]
    )
    from unittest.mock import patch
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_em.return_value = fake_df
        result = fetch_zt_pool("20260731")

    codes = {s.stock_code for s in result}
    # 2 只普通股保留，2 只 ST/*ST 过滤
    assert codes == {"600000", "600003"}
    assert all(s.stock_name in {"浦发银行", "东方通信"} for s in result)


def test_akshare_client_fetch_zt_pool_dtgc_filters_st() -> None:
    """fetch_zt_pool_dtgc 同样过滤 ST 股（一致性）。"""
    from infrastructure.stock.akshare_client import fetch_zt_pool_dtgc
    import pandas as pd

    fake_df = pd.DataFrame(
        [
            {"代码": "600000", "名称": "浦发银行", "涨跌幅": 9.5,
             "最新价": 12.5, "最后封板时间": "14:35:21", "开板次数": 2},
            {"代码": "600001", "名称": "*ST 国安", "涨跌幅": 5.0,
             "最新价": 12.5, "最后封板时间": "14:35:21", "开板次数": 2},
            {"代码": "600002", "名称": "退市海润", "涨跌幅": 5.0,
             "最新价": 12.5, "最后封板时间": "14:35:21", "开板次数": 2},
            {"代码": "600003", "名称": "东方通信", "涨跌幅": 9.5,
             "最新价": 12.5, "最后封板时间": "14:35:21", "开板次数": 2},
        ]
    )
    from unittest.mock import patch
    with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
        mock_ak.stock_zt_pool_dtgc_em.return_value = fake_df
        result = fetch_zt_pool_dtgc("20260731")

    codes = {s.stock_code for s in result}
    # ST / 退市股 都过滤
    assert codes == {"600000", "600003"}
