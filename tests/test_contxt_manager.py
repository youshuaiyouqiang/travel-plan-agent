"""Tests for core/contxt_manager.py — ContextManager, PreparedContext"""
import pytest

from domain.reasoning.context_manager import ContextManager, PreparedContext
from domain.user.session.manager import Session, Turn


class TestPreparedContext:
    def test_defaults(self):
        ctx = PreparedContext(summary="short summary")
        assert ctx.summary == "short summary"
        assert ctx.recent_turns == []
        assert ctx.was_trimmed is False


class TestContextManager:
    def test_prepare_basic(self):
        session = Session(session_id="s1")
        session.append("user", "hello")
        session.append("assistant", "hi")

        manager = ContextManager()
        result = manager.prepare(session, current_message="hello")

        # Since current_message matches the last turn, it should be excluded
        assert len(result.recent_turns) <= 2
        assert result.was_trimmed is False

    def test_prepare_excludes_current_message(self):
        """The current user message is passed separately to the reasoning loop,
        so it should be excluded from context to avoid duplication.
        The code only removes the LAST turn if it's a user turn matching current_message."""
        session = Session(session_id="s1")
        session.append("assistant", "previous reply")
        session.append("user", "search weather")  # this IS the last turn

        manager = ContextManager()
        result = manager.prepare(session, current_message="search weather")

        # The last user turn matching current_message should be excluded
        assert len(result.recent_turns) == 1
        assert result.recent_turns[0].role == "assistant"

    def test_prepare_no_current_message(self):
        session = Session(session_id="s1")
        session.append("user", "hello")
        session.append("assistant", "hi")

        manager = ContextManager()
        result = manager.prepare(session)  # no current_message

        assert len(result.recent_turns) == 2

    def test_prepare_trimming_by_turns(self):
        """When turns exceed max_context_turns, older turns should be trimmed."""
        session = Session(session_id="s1")
        for i in range(20):
            session.append("user", f"message {i}")

        manager = ContextManager()
        result = manager.prepare(session)

        assert result.was_trimmed is True
        # Should keep at most max_context_turns (default 16)
        from config import settings
        assert len(result.recent_turns) <= settings.max_context_turns

    def test_prepare_trimming_by_chars(self):
        """When total chars exceed max_context_chars, turns should be trimmed from the beginning."""
        session = Session(session_id="s1")
        # Add turns with very long content to exceed char limit
        for i in range(5):
            session.append("user", "x" * 100000)  # each turn 100k chars

        manager = ContextManager()
        result = manager.prepare(session)

        assert result.was_trimmed is True
        # Total chars should be within limit
        total_chars = sum(len(turn.content) for turn in result.recent_turns)
        from config import settings
        assert total_chars <= settings.max_context_chars

    def test_prepare_preserves_summary(self):
        session = Session(session_id="s1")
        session.summary = "user asked about weather"
        session.append("user", "weather?")
        session.append("assistant", "it's sunny")

        manager = ContextManager()
        result = manager.prepare(session)

        assert result.summary == "user asked about weather"

    def test_prepare_empty_session(self):
        session = Session(session_id="s1")

        manager = ContextManager()
        result = manager.prepare(session)

        assert result.recent_turns == []
        assert result.was_trimmed is False