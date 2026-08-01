"""Task 3 失败测试：观察池扫描器（多类别）。

覆盖：
- 抗跌股识别：大盘下跌时，跌幅显著小于大盘的股票被选出
- 板块分歧后抗跌股识别：曾判定板块高潮的板块分歧后，找出抗跌个股
- 扫描结果应能 upsert 到 watchlist_stocks

运行前 infrastructure/stock/watchlist_scanner.py 不存在，本测试应全部失败。
"""

from __future__ import annotations

import os

import pytest

from infrastructure.persistence.database import init_db, reset_connection
from domain.stock.models import StockDaily, SectorDivergence


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_watchlist.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


def test_identify_resistant_stocks_basic() -> None:
    """大盘跌 2% 时，跌幅 < 1% 的视为抗跌。"""
    from infrastructure.stock.watchlist_scanner import identify_resistant_stocks

    market_pct_chg = -2.0
    stocks = [
        StockDaily(
            trade_date="20260728", stock_code="001", open=10, close=9.5,
            high=10, low=9.5, volume=1000, pct_chg=-0.5, turnover=0.0,
        ),  # 抗跌
        StockDaily(
            trade_date="20260728", stock_code="002", open=10, close=9,
            high=10, low=9, volume=1000, pct_chg=-2.0, turnover=0.0,
        ),  # 跟跌（恰好等于大盘，不算"显著小于"）
        StockDaily(
            trade_date="20260728", stock_code="003", open=10, close=10.5,
            high=10.5, low=10, volume=1000, pct_chg=1.0, turnover=0.0,
        ),  # 上涨
        StockDaily(
            trade_date="20260728", stock_code="004", open=10, close=9.2,
            high=10, low=9.2, volume=1000, pct_chg=-3.5, turnover=0.0,
        ),  # 跟跌更狠
    ]
    resistant = identify_resistant_stocks(stocks, market_pct_chg, threshold_ratio=0.5)
    codes = {s.stock_code for s in resistant}
    assert "001" in codes
    assert "002" not in codes  # 跌幅等于大盘不入选
    assert "003" in codes  # 上涨也算抗跌
    assert "004" not in codes


def test_identify_resistant_stocks_no_market_drop_returns_empty() -> None:
    """大盘没跌（pct_chg >= 0）时，抗跌股扫描无意义，返回空列表。"""
    from infrastructure.stock.watchlist_scanner import identify_resistant_stocks

    stocks = [
        StockDaily(
            trade_date="20260728", stock_code="001", open=10, close=10.5,
            high=10.5, low=10, volume=1000, pct_chg=0.5, turnover=0.0,
        )
    ]
    assert identify_resistant_stocks(stocks, market_pct_chg=0.5) == []


def test_extract_post_divergence_resistant() -> None:
    """板块分歧后抗跌：曾高潮的板块分歧，板块内抗跌个股入选。"""
    from infrastructure.stock.watchlist_scanner import extract_post_divergence_resistant

    divergences = [
        SectorDivergence(
            trade_date="20260728", sector_code="BK0001", sector_name="半导体",
            was_high_phase=True, sector_pct_chg=-3.0, leading_stock_pct_chg=-5.0,
            broken_limit_ratio=0.4,
        ),
    ]
    sector_stocks = {
        "半导体": [
            StockDaily(
                trade_date="20260728", stock_code="S1", open=100, close=98,
                high=100, low=98, volume=1000, pct_chg=-1.0, turnover=0.0,
            ),  # 板块跌 3% 但个股只跌 1%，抗跌
            StockDaily(
                trade_date="20260728", stock_code="S2", open=100, close=95,
                high=100, low=95, volume=1000, pct_chg=-3.0, turnover=0.0,
            ),  # 跟跌
        ],
    }
    result = extract_post_divergence_resistant(divergences, sector_stocks)
    assert "S1" in result
    assert "S2" not in result
