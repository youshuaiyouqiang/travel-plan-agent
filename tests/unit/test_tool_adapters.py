"""工具适配器测试 — amap / qweather / fliggy / http / drive_cost。

通过 monkeypatch ``subprocess.run`` 与 ``httpx.AsyncClient`` 避免真实外部调用，
覆盖参数校验、错误分支与 JSON 解析路径。
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

import pytest

from infrastructure.tools.adapters import amap, fliggy, qweather, http, drive_cost


# ---------------------------------------------------------------------------
# amap
# ---------------------------------------------------------------------------


@dataclass
class _FakeCompletedProcess:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class TestAmap:
    @pytest.mark.asyncio
    async def test_run_amap_missing_key(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "")
        result = await amap._search_poi({"keywords": "餐厅"})
        assert result["is_error"] is True
        assert "AMAP_WEBSERVICE_KEY" in result["content"]

    @pytest.mark.asyncio
    async def test_search_poi_missing_keywords(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")
        result = await amap._search_poi({})
        assert result["is_error"] is True
        assert "keywords" in result["content"]

    @pytest.mark.asyncio
    async def test_search_poi_success_with_city(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")

        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            return _FakeCompletedProcess(stdout=json.dumps({"status": "1", "pois": []}))

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = await amap._search_poi({"keywords": "餐厅", "city": "北京"})
        assert result["is_error"] is False
        assert "pois" in result["content"]
        assert "poi" in captured["cmd"]
        assert "--city" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_search_poi_amap_business_error(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _FakeCompletedProcess(
                stdout=json.dumps({"status": "0", "infocode": "10001", "info": "INVALID_USER_KEY"})
            ),
        )
        result = await amap._search_poi({"keywords": "餐厅"})
        assert result["is_error"] is True
        assert "高德地图服务暂不可用" in result["content"]

    @pytest.mark.asyncio
    async def test_run_amap_nonzero_returncode(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _FakeCompletedProcess(returncode=2, stderr="boom"),
        )
        result = await amap._search_poi({"keywords": "餐厅"})
        assert result["is_error"] is True
        assert "高德地图调用失败" in result["content"]

    @pytest.mark.asyncio
    async def test_run_amap_invalid_json_falls_back_to_text(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _FakeCompletedProcess(stdout="not-json-raw"),
        )
        result = await amap._search_poi({"keywords": "餐厅"})
        assert result["is_error"] is False
        assert result["content"] == "not-json-raw"

    @pytest.mark.asyncio
    async def test_run_amap_timeout(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")

        def _raise(*a, **k):
            raise subprocess.TimeoutExpired(cmd=["python"], timeout=30)

        monkeypatch.setattr(subprocess, "run", _raise)
        result = await amap._search_poi({"keywords": "餐厅"})
        assert result["is_error"] is True
        assert "超时" in result["content"]

    @pytest.mark.asyncio
    async def test_search_nearby_missing_coords(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")
        result = await amap._search_nearby({"keywords": "x"})
        assert result["is_error"] is True
        assert "lng/lat" in result["content"]

    @pytest.mark.asyncio
    async def test_search_nearby_success(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")

        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            return _FakeCompletedProcess(stdout=json.dumps({"status": "1"}))

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = await amap._search_nearby({"lng": "116.4", "lat": "39.9", "keywords": "餐厅"})
        assert result["is_error"] is False
        assert "around" in captured["cmd"]
        assert "--keywords" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_plan_route_missing_args(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")
        result = await amap._plan_route({"from": ""})
        assert result["is_error"] is True
        assert "origin or destination" in result["content"]

    @pytest.mark.asyncio
    async def test_plan_route_walk_mode(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            return _FakeCompletedProcess(stdout=json.dumps({"status": "1"}))

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = await amap._plan_route({"from": "A", "to": "B", "mode": "walk"})
        assert result["is_error"] is False
        assert "walk" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_plan_route_drive_mode(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            return _FakeCompletedProcess(stdout=json.dumps({"status": "1"}))

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = await amap._plan_route({"from": "A", "to": "B", "mode": "drive"})
        assert result["is_error"] is False
        assert "drive" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_get_weather_missing_city(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")
        result = await amap._get_weather({})
        assert result["is_error"] is True
        assert "city" in result["content"]

    @pytest.mark.asyncio
    async def test_geocode_missing_address(self, monkeypatch):
        monkeypatch.setattr(amap, "AMAP_KEY", "fake-key")
        result = await amap._geocode({})
        assert result["is_error"] is True
        assert "address" in result["content"]

    def test_get_amap_specs_and_handlers(self):
        specs = amap.get_amap_specs()
        handlers = amap.get_amap_handlers()
        spec_names = {s.name for s in specs}
        assert spec_names == {
            "amap_search_poi",
            "amap_search_nearby",
            "amap_plan_route",
            "amap_get_weather",
            "amap_geocode",
        }
        assert set(handlers.keys()) == spec_names


# ---------------------------------------------------------------------------
# qweather
# ---------------------------------------------------------------------------


class TestQweather:
    def test_validate_location_missing(self):
        assert qweather._validate_location("") == "missing location"

    def test_validate_location_too_long(self):
        assert qweather._validate_location("a" * 51) == "location too long (max 50 chars)"

    def test_validate_location_invalid_chars(self):
        assert qweather._validate_location("北京;rm -rf") == "location contains invalid characters"

    def test_validate_location_valid(self):
        assert qweather._validate_location("北京") is None
        assert qweather._validate_location("beijing-1") is None

    def test_check_qweather_key_missing(self, monkeypatch):
        monkeypatch.setattr(qweather, "QWEATHER_KEY", "")
        assert qweather._check_qweather_key() is not None

    def test_check_qweather_key_present(self, monkeypatch):
        monkeypatch.setattr(qweather, "QWEATHER_KEY", "fake")
        assert qweather._check_qweather_key() is None

    @pytest.mark.asyncio
    async def test_qweather_now_invalid_location(self, monkeypatch):
        monkeypatch.setattr(qweather, "QWEATHER_KEY", "fake")
        result = await qweather._qweather_now({"location": "x;y"})
        assert result["is_error"] is True
        assert "invalid characters" in result["content"]

    @pytest.mark.asyncio
    async def test_qweather_now_success(self, monkeypatch):
        monkeypatch.setattr(qweather, "QWEATHER_KEY", "fake")
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            return _FakeCompletedProcess(stdout=json.dumps({"now": {"temp": "25"}}))

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = await qweather._qweather_now({"location": "北京"})
        assert result["is_error"] is False
        assert "now" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_qweather_forecast_invalid_days_falls_back(self, monkeypatch):
        monkeypatch.setattr(qweather, "QWEATHER_KEY", "fake")
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            return _FakeCompletedProcess(stdout=json.dumps({"daily": []}))

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = await qweather._qweather_forecast({"location": "北京", "days": 5})
        assert result["is_error"] is False
        assert "--days" in captured["cmd"]
        # 5 不是允许值，回退到 7
        days_idx = captured["cmd"].index("--days")
        assert captured["cmd"][days_idx + 1] == "7"

    @pytest.mark.asyncio
    async def test_qweather_run_error_returncode(self, monkeypatch):
        monkeypatch.setattr(qweather, "QWEATHER_KEY", "fake")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _FakeCompletedProcess(returncode=1, stderr="boom"),
        )
        result = await qweather._qweather_now({"location": "北京"})
        assert result["is_error"] is True
        assert "和风天气调用失败" in result["content"]

    @pytest.mark.asyncio
    async def test_qweather_run_timeout(self, monkeypatch):
        monkeypatch.setattr(qweather, "QWEATHER_KEY", "fake")

        def _raise(*a, **k):
            raise subprocess.TimeoutExpired(cmd=["python"], timeout=30)

        monkeypatch.setattr(subprocess, "run", _raise)
        result = await qweather._qweather_now({"location": "北京"})
        assert result["is_error"] is True
        assert "超时" in result["content"]

    def test_qweather_specs_and_handlers(self):
        specs = qweather.get_qweather_specs()
        handlers = qweather.get_qweather_handlers()
        spec_names = {s.name for s in specs}
        assert spec_names == {"qweather_forecast", "qweather_now"}
        assert set(handlers.keys()) == spec_names


# ---------------------------------------------------------------------------
# fliggy
# ---------------------------------------------------------------------------


class TestFliggy:
    def test_find_flyai_missing(self, monkeypatch):
        monkeypatch.setattr(fliggy, "os", type("E", (), {"environ": {"FLYAI_BIN": ""}})())
        monkeypatch.setattr(fliggy.shutil, "which", lambda _: None)
        assert fliggy._find_flyai() is None

    def test_find_flyai_from_env(self, monkeypatch, tmp_path):
        fake_bin = tmp_path / "flyai.exe"
        fake_bin.write_text("x")
        monkeypatch.setattr(fliggy.os, "environ", {"FLYAI_BIN": str(fake_bin)})
        assert fliggy._find_flyai() == str(fake_bin)

    @pytest.mark.asyncio
    async def test_run_flyai_missing_binary(self, monkeypatch):
        monkeypatch.setattr(fliggy, "_find_flyai", lambda: None)
        result = await fliggy._search_flight({"origin": "A", "destination": "B", "date": "2026-01-01"})
        assert result["is_error"] is True
        assert "flyai-cli 未安装" in result["content"]

    @pytest.mark.asyncio
    async def test_search_flight_missing_args(self, monkeypatch):
        result = await fliggy._search_flight({"origin": "A"})
        assert result["is_error"] is True
        assert "origin/destination/date" in result["content"]

    @pytest.mark.asyncio
    async def test_search_flight_success(self, monkeypatch):
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            return _FakeCompletedProcess(stdout=json.dumps({"flights": []}))

        monkeypatch.setattr(fliggy, "_find_flyai", lambda: "/fake/flyai")
        monkeypatch.setattr(subprocess, "run", fake_run)
        result = await fliggy._search_flight(
            {"from": "北京", "to": "上海", "dep_date": "2026-01-01"}
        )
        assert result["is_error"] is False
        assert "search-flight" in captured["cmd"]
        assert "--origin" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_search_train_success(self, monkeypatch):
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            return _FakeCompletedProcess(stdout=json.dumps({"trains": []}))

        monkeypatch.setattr(fliggy, "_find_flyai", lambda: "/fake/flyai")
        monkeypatch.setattr(subprocess, "run", fake_run)
        result = await fliggy._search_train(
            {"origin": "北京", "destination": "上海", "date": "2026-01-01"}
        )
        assert result["is_error"] is False
        assert "search-train" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_search_hotel_missing_args(self, monkeypatch):
        result = await fliggy._search_hotel({"destination": "上海"})
        assert result["is_error"] is True
        assert "destination/check_in/check_out" in result["content"]

    @pytest.mark.asyncio
    async def test_search_hotel_success(self, monkeypatch):
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            return _FakeCompletedProcess(stdout=json.dumps({"hotels": []}))

        monkeypatch.setattr(fliggy, "_find_flyai", lambda: "/fake/flyai")
        monkeypatch.setattr(subprocess, "run", fake_run)
        result = await fliggy._search_hotel(
            {"city": "上海", "checkIn": "2026-01-01", "checkOut": "2026-01-03"}
        )
        assert result["is_error"] is False
        assert "search-hotel" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_keyword_search_missing_query(self, monkeypatch):
        result = await fliggy._keyword_search({})
        assert result["is_error"] is True
        assert "query" in result["content"]

    @pytest.mark.asyncio
    async def test_ai_search_success(self, monkeypatch):
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            return _FakeCompletedProcess(stdout=json.dumps({"results": []}))

        monkeypatch.setattr(fliggy, "_find_flyai", lambda: "/fake/flyai")
        monkeypatch.setattr(subprocess, "run", fake_run)
        result = await fliggy._ai_search({"query": "去三亚度假"})
        assert result["is_error"] is False
        assert "ai-search" in captured["cmd"]

    @pytest.mark.asyncio
    async def test_run_flyai_empty_output(self, monkeypatch):
        monkeypatch.setattr(fliggy, "_find_flyai", lambda: "/fake/flyai")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _FakeCompletedProcess(stdout="", stderr=""),
        )
        result = await fliggy._keyword_search({"query": "test"})
        assert result["is_error"] is True
        assert "无结果" in result["content"]

    @pytest.mark.asyncio
    async def test_run_flyai_invalid_json(self, monkeypatch):
        monkeypatch.setattr(fliggy, "_find_flyai", lambda: "/fake/flyai")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _FakeCompletedProcess(stdout="plain text"),
        )
        result = await fliggy._keyword_search({"query": "test"})
        assert result["is_error"] is False
        assert result["content"] == "plain text"

    @pytest.mark.asyncio
    async def test_run_flyai_timeout(self, monkeypatch):
        monkeypatch.setattr(fliggy, "_find_flyai", lambda: "/fake/flyai")

        def _raise(*a, **k):
            raise subprocess.TimeoutExpired(cmd=["flyai"], timeout=30)

        monkeypatch.setattr(subprocess, "run", _raise)
        result = await fliggy._keyword_search({"query": "test"})
        assert result["is_error"] is True
        assert "超时" in result["content"]

    def test_normalize_transport_args_variants(self):
        result = fliggy._normalize_transport_args(
            {"from": "A", "destination": "B", "dep_date": "2026-01-01"}
        )
        assert result == {"origin": "A", "destination": "B", "date": "2026-01-01"}

    def test_normalize_hotel_args_variants(self):
        result = fliggy._normalize_hotel_args(
            {"city": "上海", "checkInDate": "2026-01-01", "checkOutDate": "2026-01-03"}
        )
        assert result == {
            "destination": "上海",
            "check_in": "2026-01-01",
            "check_out": "2026-01-03",
        }

    def test_fliggy_specs_and_handlers(self):
        specs = fliggy.get_fliggy_specs()
        handlers = fliggy.get_fliggy_handlers()
        spec_names = {s.name for s in specs}
        assert spec_names == {
            "fliggy_search_flight",
            "fliggy_search_train",
            "fliggy_search_hotel",
            "fliggy_keyword_search",
            "fliggy_ai_search",
        }
        assert set(handlers.keys()) == spec_names


# ---------------------------------------------------------------------------
# http
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, *, status_code: int, text: str, content_type: str = "text/html", url: str = "http://x"):
        self.status_code = status_code
        self._text = text
        self.headers = {"content-type": content_type}
        self.url = url

    @property
    def text(self) -> str:
        return self._text

    def json(self) -> Any:
        return json.loads(self._text)


class _FakeAsyncClient:
    def __init__(self, *, response: _FakeResponse, exc: Exception | None = None):
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        if self._exc:
            raise self._exc
        return self._response


class TestHttpAdapter:
    @pytest.mark.asyncio
    async def test_fetch_url_disabled(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "allow_http", False)
        result = await http._fetch_url({"url": "https://example.com"})
        assert result["is_error"] is True
        assert result["content"] == "http disabled"

    @pytest.mark.asyncio
    async def test_fetch_url_invalid_scheme(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "allow_http", True)
        result = await http._fetch_url({"url": "ftp://x"})
        assert result["is_error"] is True
        assert "invalid url" in result["content"]

    @pytest.mark.asyncio
    async def test_fetch_url_http_error(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "allow_http", True)
        import httpx as _httpx

        def fake_client(*args, **kwargs):
            return _FakeAsyncClient(response=None, exc=_httpx.HTTPError("network down"))

        monkeypatch.setattr(_httpx, "AsyncClient", fake_client)
        result = await http._fetch_url({"url": "https://example.com"})
        assert result["is_error"] is True
        assert "http request failed" in result["content"]

    @pytest.mark.asyncio
    async def test_fetch_url_html_success(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "allow_http", True)
        import httpx as _httpx

        response = _FakeResponse(status_code=200, text="<html>hello</html>", content_type="text/html")
        monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(response=response))
        result = await http._fetch_url({"url": "https://example.com"})
        assert result["is_error"] is False
        assert "hello" in result["content"]
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_fetch_url_json_content_type(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "allow_http", True)
        import httpx as _httpx

        response = _FakeResponse(
            status_code=200,
            text=json.dumps({"key": "value"}),
            content_type="application/json",
        )
        monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(response=response))
        result = await http._fetch_url({"url": "https://example.com"})
        assert result["is_error"] is False
        assert "key" in result["content"]

    @pytest.mark.asyncio
    async def test_fetch_url_4xx_is_error(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "allow_http", True)
        import httpx as _httpx

        response = _FakeResponse(status_code=404, text="Not Found", content_type="text/plain")
        monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(response=response))
        result = await http._fetch_url({"url": "https://example.com"})
        assert result["is_error"] is True
        assert result["status_code"] == 404

    def test_http_specs_and_handlers(self):
        specs = http.get_http_specs()
        handlers = http.get_http_handlers()
        assert [s.name for s in specs] == ["fetch_url"]
        assert list(handlers.keys()) == ["fetch_url"]

    def test_build_http_tools(self):
        tools = http.build_http_tools()
        assert len(tools) == 1
        assert tools[0].name == "fetch_url"


# ---------------------------------------------------------------------------
# drive_cost
# ---------------------------------------------------------------------------


class TestDriveCost:
    def test_specs_and_handlers(self):
        specs = drive_cost.get_drive_cost_specs()
        handlers = drive_cost.get_drive_cost_handlers()
        assert len(specs) >= 1
        assert set(handlers.keys()) == {s.name for s in specs}

    @pytest.mark.asyncio
    async def test_estimate_drive_cost_default_sedan(self):
        result = await drive_cost._estimate_drive_cost({"distance_km": 100, "toll_yuan": 50})
        assert result["is_error"] is False
        assert "total_cost" in result["content"]
        # sedan: 100 * 0.07 * 7.8/7.8 = 7.0 油费；过路费 50；餐费 1*100*1=100；合计 157
        assert "157" in result["content"]

    @pytest.mark.asyncio
    async def test_estimate_drive_cost_suv_with_people(self):
        result = await drive_cost._estimate_drive_cost(
            {"distance_km": 200, "toll_yuan": 80, "people_count": 3, "days_on_road": 2, "car_type": "suv"}
        )
        assert result["is_error"] is False
        # suv: 200 * 0.09 * 7.8/7.8 = 18 油费；过路费 80；餐费 2*100*3=600；合计 698
        assert "698" in result["content"]

    @pytest.mark.asyncio
    async def test_estimate_drive_cost_unknown_car_type_falls_back_to_sedan(self):
        result = await drive_cost._estimate_drive_cost(
            {"distance_km": 100, "toll_yuan": 0, "car_type": "truck"}
        )
        assert result["is_error"] is False
        assert "truck" in result["content"]
