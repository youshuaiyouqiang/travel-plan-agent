"""Task 17 失败测试：fetcher 同步阻塞事件循环修复。

背景：4 个 fetcher 的 _fetch 内部调用 akshare（同步 requests）但没有
asyncio.to_thread 包装，导致 warmup 任务在后台跑时把整个事件循环卡住，
uvicorn 的 startup body（绑定端口等）永远轮不到执行 → lifespan yield 之后
uvicorn 仍卡在 "Waiting for application startup"，前端登录报"服务器响应异常"。

验证：每个 _fetch 在执行时，事件循环上排队的 probe 任务必须能继续推进。
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from infrastructure.persistence.database import init_db, reset_connection


# ── fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_fetcher_nonblocking.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()
    if db_path.exists():
        os.unlink(db_path)


# ── 工具：探测事件循环进度 ──────────────────────────────────


async def _assert_event_loop_responsive(
    fetcher_coro: Any,
    *,
    min_probe_ticks: int = 3,
    blocker_seconds: float = 0.4,
) -> None:
    """运行 fetcher_coro；期间用 probe 任务测量事件循环是否被阻塞。

    Args:
        fetcher_coro: 待测的 fetcher coroutine。
        min_probe_ticks: probe 任务至少应推进的 tick 数。同步阻塞时这个值
            会远小于期望；非阻塞时 0.4s 至少能跑 4-8 个 tick。
        blocker_seconds: 在 mock 的 akshare 内部 sleep 多久来模拟同步阻塞。
    """
    ticks: list[float] = []
    stop = asyncio.Event()

    async def probe() -> None:
        # 探针：每 0.05s 记录一次时间戳，直到 stop
        while not stop.is_set():
            ticks.append(time.monotonic())
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.05)
            except TimeoutError:
                continue

    probe_task = asyncio.create_task(probe())
    # 让 probe 至少启动一次再开 fetcher
    await asyncio.sleep(0)
    await fetcher_coro
    stop.set()
    await probe_task
    # 同步阻塞 fetcher 下，ticks 只会有 fetcher 启动前的那 1-2 个；
    # 非阻塞 fetcher 下，ticks 应 >= min_probe_ticks。
    assert len(ticks) >= min_probe_ticks, (
        f"fetcher 阻塞事件循环：probe 只推进了 {len(ticks)} 次（期望 ≥ {min_probe_ticks}）"
    )


# ── market_index_fetcher ──────────────────────────────────


def _patch_ak_slow_sleep(mock_ak: Any, seconds: float) -> None:
    """让 mock ak.stock_zh_index_daily 在调起时同步 sleep（模拟 requests 阻塞）。"""
    def _slow(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
        time.sleep(seconds)
        return pd.DataFrame(
            [
                {"date": "2026-07-30", "open": 2410.0, "close": 2410.0,
                 "high": 2410.0, "low": 2410.0, "volume": 0},
            ]
        )
    mock_ak.stock_zh_index_daily.side_effect = _slow


class TestMarketIndexFetcherNonBlocking:
    @pytest.mark.asyncio
    async def test__fetch_does_not_block_event_loop(self, tmp_db) -> None:
        from infrastructure.stock.market_index_fetcher import _fetch

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            _patch_ak_slow_sleep(mock_ak, 0.4)
            await _assert_event_loop_responsive(_fetch("20260730"))


# ── sector_daily_fetcher ──────────────────────────────────


class TestSectorDailyFetcherNonBlocking:
    @pytest.mark.asyncio
    async def test__fetch_does_not_block_event_loop(self, tmp_db) -> None:
        from infrastructure.stock.sector_daily_fetcher import _fetch

        def _slow_sectors() -> pd.DataFrame:
            time.sleep(0.4)
            return pd.DataFrame(
                [
                    {
                        "板块名称": "半导体",
                        "板块代码": "BK1004",
                        "涨跌幅": 2.35,
                        "领涨股": "中芯国际",
                        "领涨股代码": "688981",
                    }
                ]
            )

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_board_industry_name_em.side_effect = _slow_sectors
            await _assert_event_loop_responsive(_fetch("20260730"))


# ── stock_daily_fetcher ──────────────────────────────────


class TestStockDailyFetcherNonBlocking:
    @pytest.mark.asyncio
    async def test__fetch_does_not_block_event_loop(self, tmp_db) -> None:
        from infrastructure.stock.stock_daily_fetcher import _fetch

        def _slow_hist(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
            time.sleep(0.4)
            return pd.DataFrame(
                [{"日期": "2026-07-30", "股票代码": "000001",
                  "开盘": 12.5, "收盘": 13.0, "最高": 13.2,
                  "最低": 12.3, "成交量": 1000000, "成交额": 12.95e6,
                  "振幅": 0.0, "涨跌幅": 4.0, "涨跌额": 0.5, "换手率": 0.0}]
            )

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_zh_a_hist.side_effect = _slow_hist
            await _assert_event_loop_responsive(_fetch("000001", "20260730"))


# ── emotion_daily_fetcher ──────────────────────────────────


class TestEmotionDailyFetcherNonBlocking:
    @pytest.mark.asyncio
    async def test__fetch_does_not_block_event_loop(self, tmp_db) -> None:
        from infrastructure.stock.emotion_daily_fetcher import _fetch

        def _slow_activity() -> pd.DataFrame:
            time.sleep(0.4)
            return pd.DataFrame(
                [
                    {"item": "涨停", "value": 4},
                    {"item": "跌停", "value": 1},
                    {"item": "炸板", "value": 1},
                ]
            )

        def _slow_index_spot() -> pd.DataFrame:
            time.sleep(0.4)
            return pd.DataFrame([{"code": "sh000001", "成交额": 1.2e12}])

        with patch("infrastructure.stock.akshare_client.ak") as mock_ak:
            mock_ak.stock_market_activity_legu.side_effect = _slow_activity
            mock_ak.stock_zh_index_spot_em.side_effect = _slow_index_spot
            await _assert_event_loop_responsive(_fetch("20260730"))
