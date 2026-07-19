"""Prometheus metrics collector 单元测试。"""

from __future__ import annotations

import pytest

from domain.shared.metrics import collector


@pytest.fixture(autouse=True)
def _reset_collectors(monkeypatch):
    """每个测试前后重置全局 _collectors，避免污染。"""
    saved = dict(collector._collectors)
    collector._collectors.clear()
    yield
    collector._collectors.clear()
    collector._collectors.update(saved)


class TestMetricsCollector:
    def test_init_metrics_disabled(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "metrics_enabled", False)
        collector._init_metrics()
        assert collector._collectors == {}

    def test_init_metrics_enabled_import_error(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "metrics_enabled", True)
        # 模拟 prometheus_client 未安装
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "prometheus_client":
                raise ImportError("simulated")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        collector._init_metrics()
        assert collector._collectors == {}

    def test_record_request_no_collectors(self):
        # 没有注册 collectors 时不抛错
        collector.record_request("s1", "task", "success")
        collector.record_request("s1", "task", "error")

    def test_observe_latency_no_collectors(self):
        collector.observe_latency("task", 0.5)

    def test_record_tool_execution_no_collectors(self):
        collector.record_tool_execution("echo", "success")

    @pytest.mark.asyncio
    async def test_track_request_success(self):
        async with collector.track_request("s1", "task"):
            pass
        # 不抛错即视为通过

    @pytest.mark.asyncio
    async def test_track_request_error_propagates(self):
        with pytest.raises(ValueError):
            async with collector.track_request("s1", "task"):
                raise ValueError("boom")

    def test_start_metrics_server_disabled(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "metrics_enabled", False)
        # 不抛错即通过
        collector.start_metrics_server()

    def test_start_metrics_server_error_swallowed(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "metrics_enabled", True)

        def boom(*args, **kwargs):
            raise RuntimeError("port in use")

        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "prometheus_client":
                class _M:
                    @staticmethod
                    def start_http_server(port):
                        raise RuntimeError("port in use")

                return _M
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        # 异常被吞掉
        collector.start_metrics_server()
