"""application/scheduler.py 单元测试。

覆盖后台调度任务的核心循环逻辑。使用 monkeypatch 替换模块级 sleep 函数。
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from application import scheduler


class TestRunHotspotRefresh:
    @pytest.mark.asyncio
    async def test_calls_service_refresh(self, monkeypatch):
        """首次 sleep 立即返回；第二次 sleep 抛 CancelledError 退出循环。"""
        call_count = {"n": 0}

        async def _fake_sleep(seconds):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                raise asyncio.CancelledError()

        # 关键：只 patch scheduler 模块内的 sleep 引用，而非 asyncio.sleep 本身
        # scheduler.py 用 `asyncio.sleep(...)`，所以替换 scheduler.asyncio.sleep 会影响全局
        # 改用 patch asyncio.sleep 但限定在 scheduler 模块的引用：
        # 实际上 scheduler 模块直接调用 asyncio.sleep，无法局部 patch
        # 解决：让 _fake_sleep 替换 asyncio.sleep，并在测试结束后由 monkeypatch 自动恢复
        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.count = 5
        mock_result.sources_used = ["baidu", "weibo"]
        mock_service.refresh = MagicMock(return_value=mock_result)

        monkeypatch.setattr(
            "application.news.hotspot_service.get_default_service",
            lambda: mock_service,
        )

        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_hotspot_refresh()

        mock_service.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_swallows_service_exception(self, monkeypatch):
        call_count = {"n": 0}

        async def _fake_sleep(seconds):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                raise asyncio.CancelledError()

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

        mock_service = MagicMock()
        mock_service.refresh = MagicMock(side_effect=RuntimeError("network down"))

        monkeypatch.setattr(
            "application.news.hotspot_service.get_default_service",
            lambda: mock_service,
        )

        # 异常被吞，正常退出（抛 CancelledError 退出）
        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_hotspot_refresh()


class TestRunHotspotCleanup:
    @pytest.mark.asyncio
    async def test_logs_placeholder_message(self, monkeypatch, caplog):
        call_count = {"n": 0}

        async def _fake_sleep(seconds):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                raise asyncio.CancelledError()

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

        with caplog.at_level("INFO"):
            with pytest.raises(asyncio.CancelledError):
                await scheduler.run_hotspot_cleanup()

        # 应记录 placeholder 日志
        assert any("Hotspot cleanup cycle: no-op" in r.message for r in caplog.records)


class TestRunMemoryMaintenance:
    @pytest.mark.asyncio
    async def test_handles_exception_in_cycle(self, monkeypatch):
        call_count = {"n": 0}

        async def _fake_sleep(seconds):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                raise asyncio.CancelledError()

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

        # 让 OpenAILLM 构造抛错
        def _raise_init(*args, **kwargs):
            raise RuntimeError("init failed")

        monkeypatch.setattr(scheduler.OpenAILLM, "__init__", _raise_init)

        # 异常被吞，应正常退出循环（抛 CancelledError 退出）
        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_memory_maintenance()

    @pytest.mark.asyncio
    async def test_runs_distillation_for_each_user(self, monkeypatch):
        call_count = {"n": 0}

        async def _fake_sleep(seconds):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                raise asyncio.CancelledError()

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

        # mock OpenAILLM
        monkeypatch.setattr(scheduler.OpenAILLM, "__init__", lambda self, **kw: None)

        # mock get_connection 返回 2 个 user_rows
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            {"user_id": "u1"},
            {"user_id": "u2"},
        ]
        monkeypatch.setattr(scheduler, "get_connection", lambda: mock_conn)

        # mock MemoryDistiller
        mock_distiller = MagicMock()
        mock_distiller.run_distillation = MagicMock(return_value=0)
        mock_distiller.run_decay = MagicMock(return_value=0)
        monkeypatch.setattr(scheduler, "MemoryDistiller", lambda **kwargs: mock_distiller)

        # to_thread 调用同步函数，需要包装
        async def _fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_memory_maintenance()

        # 应对每个用户调用 run_distillation
        assert mock_distiller.run_distillation.call_count >= 2
