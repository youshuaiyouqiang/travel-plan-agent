from __future__ import annotations

import datetime
import json
import time
from pathlib import Path

import pytest

from domain.shared.audit.sanitizer import sanitize, sanitize_dict
from domain.shared.audit.logger import AuditLogger


class TestSanitizer:
    def test_phone_masking(self):
        result = sanitize("我的手机号是13812345678")
        assert "13812345678" not in result
        assert "PHONE_MASKED" in result

    def test_email_masking(self):
        result = sanitize("邮箱是test@example.com")
        assert "test@example.com" not in result
        assert "EMAIL_MASKED" in result

    def test_id_card_masking(self):
        result = sanitize("身份证号110101199001011234")
        assert "110101199001011234" not in result

    def test_sanitize_dict(self):
        data = {"phone": "13812345678", "name": "张三"}
        result = sanitize_dict(data)
        assert "13812345678" not in result["phone"]
        assert result["name"] == "张三"

    def test_no_match(self):
        result = sanitize("普通文本没有敏感信息")
        assert result == "普通文本没有敏感信息"


def _today_log_file(tmp_path: Path) -> Path:
    return tmp_path / f"audit-{datetime.datetime.utcnow().strftime('%Y-%m-%d')}.jsonl"


def _read_events(log_file: Path) -> list[dict]:
    if not log_file.exists():
        return []
    events: list[dict] = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


class TestAuditLogger:
    def test_log_event(self, tmp_path: Path):
        audit = AuditLogger(log_dir=tmp_path)
        audit.log(
            event_type="tool_call",
            session_id="test_session",
            user_id="test_user",
            tool_name="run_shell",
            action="ls -la",
            risk_level="low",
            trace_id="trace-1",
        )
        log_file = _today_log_file(tmp_path)
        assert log_file.exists()
        line = log_file.read_text(encoding="utf-8").strip()
        event = json.loads(line)
        assert event["trace_id"] == "trace-1"
        assert event["event_type"] == "tool_call"

    def test_log_disabled(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("config.settings.audit_enabled", False)
        audit = AuditLogger(log_dir=tmp_path)
        audit.log(
            event_type="test",
            session_id="s1",
            user_id="u1",
        )
        log_file = _today_log_file(tmp_path)
        assert not log_file.exists()


class TestAuditLoggerHelpers:
    """覆盖 AuditLogger 的高层 helper 方法。"""

    def test_log_tool_call_run_shell_high_risk(self, tmp_path: Path):
        audit = AuditLogger(log_dir=tmp_path)
        audit.log_tool_call(
            session_id="s1",
            user_id="u1",
            tool_name="run_shell",
            arguments={"cmd": "ls"},
            result_summary="file1\nfile2",
            duration_ms=10,
            trace_id="t1",
        )
        events = _read_events(_today_log_file(tmp_path))
        assert events
        assert events[0]["event_type"] == "tool_call"
        assert events[0]["risk_level"] == "high"
        assert events[0]["tool_name"] == "run_shell"

    def test_log_tool_call_error_medium_risk(self, tmp_path: Path):
        audit = AuditLogger(log_dir=tmp_path)
        audit.log_tool_call(
            session_id="s1",
            user_id="u1",
            tool_name="fetch_url",
            arguments={"url": "https://x"},
            result_summary="failed",
            is_error=True,
            error_traceback="ValueError: boom",
            trace_id="t1",
        )
        events = _read_events(_today_log_file(tmp_path))
        assert events[0]["risk_level"] == "medium"
        assert events[0]["metadata"]["error_traceback"] == "ValueError: boom"

    def test_log_llm_call(self, tmp_path: Path):
        audit = AuditLogger(log_dir=tmp_path)
        audit.log_llm_call(
            session_id="s1",
            user_id="u1",
            model="gpt-4",
            system_prompt="你是助手",
            messages=[{"role": "user", "content": "hi"}],
            response="hello",
            duration_ms=200,
            tool_calls_mode=True,
            trace_id="t1",
        )
        events = _read_events(_today_log_file(tmp_path))
        assert events[0]["event_type"] == "llm_call"
        assert events[0]["metadata"]["model"] == "gpt-4"
        assert events[0]["metadata"]["tool_calls_mode"] is True
        assert "hi" in events[0]["llm_input"]

    def test_log_intent_classify(self, tmp_path: Path):
        audit = AuditLogger(log_dir=tmp_path)
        audit.log_intent_classify(
            session_id="s1",
            user_id="u1",
            message="想去旅游",
            intent="task",
            goal="plan trip",
            confidence=0.92,
            classifier="travel",
            trace_id="t1",
        )
        events = _read_events(_today_log_file(tmp_path))
        assert events[0]["event_type"] == "intent_classify"
        assert events[0]["metadata"]["intent"] == "task"
        assert events[0]["metadata"]["confidence"] == 0.92

    def test_log_reasoning_step(self, tmp_path: Path):
        audit = AuditLogger(log_dir=tmp_path)
        audit.log_reasoning_step(
            session_id="s1",
            user_id="u1",
            iteration=1,
            decision_type="tool_calls",
            text="calling tool",
            tool_calls=[{"name": "echo", "arguments": {}}],
            tool_results=[{"name": "echo", "status": "ok", "is_error": False, "content": "ok"}],
            system_note="retry",
            trace_id="t1",
        )
        events = _read_events(_today_log_file(tmp_path))
        assert events[0]["event_type"] == "reasoning_step"
        assert events[0]["risk_level"] == "medium"
        assert events[0]["metadata"]["iteration"] == 1
        assert events[0]["metadata"]["tool_results"][0]["name"] == "echo"

    def test_log_context_built(self, tmp_path: Path):
        audit = AuditLogger(log_dir=tmp_path)
        audit.log_context_built(
            session_id="s1",
            user_id="u1",
            trace_id="t1",
            system_prompt="you are an agent",
            tools=["echo"],
            memory_context="mem",
            dual_memory_context="dmem",
            mcp_context="",
            profile_context="profile",
            selected_mcp_tools=["mcp1"],
            connected_mcp_tools=["mcp1"],
        )
        events = _read_events(_today_log_file(tmp_path))
        assert events[0]["event_type"] == "context_built"
        assert events[0]["metadata"]["has_memory"] is True
        assert events[0]["metadata"]["has_mcp"] is False
        assert events[0]["metadata"]["selected_mcp_tools"] == ["mcp1"]

    def test_log_session_complete(self, tmp_path: Path):
        audit = AuditLogger(log_dir=tmp_path)
        audit.log_session_complete(
            session_id="s1",
            user_id="u1",
            user_message="hi",
            reply="hello",
            intent="chat",
            total_duration_ms=500,
            trace_summary="iter=1 type=final_answer",
            trace_id="t1",
        )
        events = _read_events(_today_log_file(tmp_path))
        assert events[0]["event_type"] == "session_complete"
        assert events[0]["duration_ms"] == 500
        assert events[0]["metadata"]["intent"] == "chat"

    def test_log_api_boundary_request(self, tmp_path: Path):
        audit = AuditLogger(log_dir=tmp_path)
        audit.log_api_boundary(
            session_id="s1",
            user_id="u1",
            trace_id="t1",
            direction="request",
            endpoint="/api/v1/chat",
            method="POST",
            payload="hello",
            agent_id="yunhe",
        )
        events = _read_events(_today_log_file(tmp_path))
        assert events[0]["event_type"] == "api_request"
        assert events[0]["metadata"]["endpoint"] == "/api/v1/chat"
        assert events[0]["metadata"]["agent_id"] == "yunhe"

    def test_log_api_boundary_response(self, tmp_path: Path):
        audit = AuditLogger(log_dir=tmp_path)
        audit.log_api_boundary(
            session_id="s1",
            user_id="u1",
            trace_id="t1",
            direction="response",
            endpoint="/api/v1/chat",
            method="POST",
            payload="reply",
            status_code=200,
            duration_ms=120,
        )
        events = _read_events(_today_log_file(tmp_path))
        assert events[0]["event_type"] == "api_response"
        assert events[0]["metadata"]["status_code"] == 200
        assert events[0]["duration_ms"] == 120

    def test_cleanup_expired_logs(self, tmp_path: Path, monkeypatch):
        # 创建一个过期的日志文件
        old_file = tmp_path / "audit-2020-01-01.jsonl"
        old_file.write_text('{"event_type": "old"}\n')
        # 修改 mtime 为 60 天前
        old_time = time.time() - 60 * 86400
        import os

        os.utime(old_file, (old_time, old_time))

        # retention_days=30，应该删除
        monkeypatch.setattr("config.settings.audit_retention_days", 30)
        AuditLogger(log_dir=tmp_path)
        assert not old_file.exists()

    def test_cleanup_disabled_when_retention_zero(self, tmp_path: Path, monkeypatch):
        old_file = tmp_path / "audit-2020-01-01.jsonl"
        old_file.write_text('{"event_type": "old"}\n')
        old_time = time.time() - 365 * 86400
        import os

        os.utime(old_file, (old_time, old_time))
        monkeypatch.setattr("config.settings.audit_retention_days", 0)
        AuditLogger(log_dir=tmp_path)
        # retention=0 不清理
        assert old_file.exists()

    def test_write_failure_swallowed(self, tmp_path: Path, monkeypatch):
        audit = AuditLogger(log_dir=tmp_path)

        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("builtins.open", boom)
        # 不抛错即通过
        audit.log(
            event_type="test",
            session_id="s1",
            user_id="u1",
        )

