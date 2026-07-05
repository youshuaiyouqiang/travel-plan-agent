from __future__ import annotations

from pathlib import Path

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
        import datetime, json

        log_file = tmp_path / f"audit-{datetime.datetime.utcnow().strftime('%Y-%m-%d')}.jsonl"
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
        import datetime

        log_file = tmp_path / f"audit-{datetime.datetime.utcnow().strftime('%Y-%m-%d')}.jsonl"
        assert not log_file.exists()
