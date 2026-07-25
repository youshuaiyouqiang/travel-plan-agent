"""SourceRubricScorer 单元测试。

覆盖：
- 合法 JSON → 解析 + 子分区间校验 + 总分 = sum(subscores) 钳制 [0,1]
- 子分越界 → raise → fallback 路径
- 缺键 → raise → fallback
- LLM 抛错 → fallback
- llm=None → 直接走 fallback
- 解析为非 dict / 错误类型 → fallback
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from application.news.models import SourceCandidateInput, SourceScore
from application.news.source_rubric_scorer import (
    SUBSCORE_CAPS,
    SourceRubricScorer,
    _parse_subscores,
)


# ---------------------------------------------------------------------------
# _parse_subscores
# ---------------------------------------------------------------------------


class TestParseSubscores:
    def test_valid_returns_dict(self):
        data = {k: cap for k, cap in SUBSCORE_CAPS.items()}
        out = _parse_subscores(data)
        assert out == data

    def test_missing_key_raises(self):
        data = {k: 0.0 for k in SUBSCORE_CAPS}
        data.pop("publisher_authority")
        with pytest.raises(ValueError):
            _parse_subscores(data)

    def test_extra_key_ignored(self):
        data = {k: 0.0 for k in SUBSCORE_CAPS}
        data["extra"] = 99.0
        out = _parse_subscores(data)
        assert "extra" not in out
        assert set(out.keys()) == set(SUBSCORE_CAPS.keys())

    def test_negative_raises(self):
        data = {k: 0.0 for k in SUBSCORE_CAPS}
        data["risk_signals"] = -0.1
        with pytest.raises(ValueError):
            _parse_subscores(data)

    def test_exceeds_cap_raises(self):
        data = {k: 0.0 for k in SUBSCORE_CAPS}
        data["publisher_authority"] = SUBSCORE_CAPS["publisher_authority"] + 0.01
        with pytest.raises(ValueError):
            _parse_subscores(data)

    def test_non_number_raises(self):
        data = {k: 0.0 for k in SUBSCORE_CAPS}
        data["publisher_authority"] = "0.30"  # type: ignore[assignment]
        with pytest.raises(ValueError):
            _parse_subscores(data)

    def test_not_dict_raises(self):
        with pytest.raises(ValueError):
            _parse_subscores([0.1, 0.2])  # type: ignore[arg-type]

    def test_bool_treated_as_invalid_number(self):
        """Python ``True``/``False`` 是 ``int`` 子类；本 scorer 拒绝避免误判。"""
        data = {k: 0.0 for k in SUBSCORE_CAPS}
        data["publisher_authority"] = True  # type: ignore[assignment]
        with pytest.raises(ValueError):
            _parse_subscores(data)


# ---------------------------------------------------------------------------
# SourceRubricScorer.score
# ---------------------------------------------------------------------------


def _valid_rubric_payload() -> dict:
    return {
        "publisher_authority": 0.30,
        "domain_brand": 0.20,
        "topic_relevance": 0.15,
        "editorial_standard": 0.15,
        "accessibility": 0.10,
        "risk_signals": 0.10,
    }


class TestSourceRubricScorer:
    @pytest.mark.asyncio
    async def test_no_llm_uses_heuristic(self):
        scorer = SourceRubricScorer(llm=None)
        result = await scorer.score(SourceCandidateInput(domain="x.com"))
        # 启发式默认 unknown + 无 https/brand/topic → 0.05
        assert result.score < 0.1
        assert result.subscores == "{}"
        assert result.reason != "LLM rubric"

    @pytest.mark.asyncio
    async def test_valid_llm_response_uses_rubric(self):
        llm = AsyncMock()
        llm.complete_json = AsyncMock(return_value=_valid_rubric_payload())
        scorer = SourceRubricScorer(llm=llm)
        result = await scorer.score(SourceCandidateInput(domain="x.com"))
        assert result.score == pytest.approx(1.0, abs=1e-6)
        # reason 既要标识 LLM rubric 路径，也要带总分与决策建议，便于审计追溯
        assert result.reason.startswith("LLM rubric")
        assert "总分" in result.reason
        assert "建议" in result.reason
        assert "publisher_authority" in result.subscores
        llm.complete_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_out_of_cap_falls_back(self):
        bad = _valid_rubric_payload()
        bad["publisher_authority"] = 0.99  # 超过 0.30
        llm = AsyncMock()
        llm.complete_json = AsyncMock(return_value=bad)
        scorer = SourceRubricScorer(llm=llm)
        result = await scorer.score(SourceCandidateInput(domain="x.com"))
        # 解析失败应走 fallback
        assert result.reason != "LLM rubric"
        assert result.subscores == "{}"

    @pytest.mark.asyncio
    async def test_missing_key_falls_back(self):
        bad = _valid_rubric_payload()
        bad.pop("risk_signals")
        llm = AsyncMock()
        llm.complete_json = AsyncMock(return_value=bad)
        scorer = SourceRubricScorer(llm=llm)
        result = await scorer.score(SourceCandidateInput(domain="x.com"))
        assert result.reason != "LLM rubric"
        assert result.subscores == "{}"

    @pytest.mark.asyncio
    async def test_llm_exception_falls_back(self):
        llm = AsyncMock()
        llm.complete_json = AsyncMock(side_effect=RuntimeError("network down"))
        scorer = SourceRubricScorer(llm=llm)
        result = await scorer.score(SourceCandidateInput(domain="x.com"))
        assert result.reason != "LLM rubric"
        assert isinstance(result, SourceScore)

    @pytest.mark.asyncio
    async def test_non_dict_response_falls_back(self):
        llm = AsyncMock()
        llm.complete_json = AsyncMock(return_value="not a dict")
        scorer = SourceRubricScorer(llm=llm)
        result = await scorer.score(SourceCandidateInput(domain="x.com"))
        assert result.reason != "LLM rubric"

    @pytest.mark.asyncio
    async def test_subscores_serialized_as_json(self):
        llm = AsyncMock()
        llm.complete_json = AsyncMock(return_value=_valid_rubric_payload())
        scorer = SourceRubricScorer(llm=llm)
        result = await scorer.score(SourceCandidateInput(domain="x.com"))
        import json

        parsed = json.loads(result.subscores)
        assert parsed["publisher_authority"] == 0.30
        assert parsed["domain_brand"] == 0.20

    @pytest.mark.asyncio
    async def test_total_is_clamped(self):
        """每个子分都在上限内，sum 可能超过 1.0；钳制到 [0,1]。"""
        llm = AsyncMock()
        llm.complete_json = AsyncMock(return_value=_valid_rubric_payload())
        scorer = SourceRubricScorer(llm=llm)
        result = await scorer.score(SourceCandidateInput(domain="x.com"))
        assert 0.0 <= result.score <= 1.0
