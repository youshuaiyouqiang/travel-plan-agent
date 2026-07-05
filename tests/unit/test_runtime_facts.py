"""Tests for core/runtime_facts.py — current_datetime_text, answer_date_or_time_query"""
from domain.shared.runtime.facts import current_datetime_text, answer_date_or_time_query


class TestCurrentDatetimeText:
    def test_returns_non_empty(self):
        result = current_datetime_text()
        assert len(result) > 0

    def test_contains_date(self):
        result = current_datetime_text()
        # Should contain YYYY-MM-DD format
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}", result)

    def test_contains_time(self):
        result = current_datetime_text()
        # Should contain HH:MM:SS format
        import re
        assert re.search(r"\d{2}:\d{2}:\d{2}", result)

    def test_contains_weekday(self):
        result = current_datetime_text()
        # Should contain a Chinese weekday
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        assert any(wd in result for wd in weekdays)


class TestAnswerDateOrTimeQuery:
    def test_date_question_today(self):
        result = answer_date_or_time_query("今天几号")
        assert result is not None
        assert "年" in result
        assert "月" in result
        assert "日" in result

    def test_date_question_full(self):
        result = answer_date_or_time_query("今天几月几号")
        assert result is not None

    def test_date_question_alt(self):
        result = answer_date_or_time_query("今天是几月几号")
        assert result is not None

    def test_date_question_date_keyword(self):
        result = answer_date_or_time_query("date")
        assert result is not None

    def test_time_question_now(self):
        result = answer_date_or_time_query("现在几点")
        assert result is not None
        assert ":" in result  # should contain time format

    def test_time_question_current(self):
        result = answer_date_or_time_query("当前时间")
        assert result is not None

    def test_time_question_english(self):
        result = answer_date_or_time_query("time now")
        assert result is not None

    def test_time_question_current_time_english(self):
        result = answer_date_or_time_query("current time")
        assert result is not None

    def test_non_date_time_query(self):
        result = answer_date_or_time_query("帮我查一下新闻")
        assert result is None

    def test_empty_message(self):
        result = answer_date_or_time_query("")
        assert result is None

    def test_whitespace_message(self):
        result = answer_date_or_time_query("   ")
        assert result is None

    def test_answer_includes_weekday(self):
        result = answer_date_or_time_query("今天几号")
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        assert any(wd in result for wd in weekdays)