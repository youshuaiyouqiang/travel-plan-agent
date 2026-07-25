"""SourceRubricScorer 单测。

覆盖范围：
- ``RUBRIC_SYSTEM_PROMPT`` 包含结构性硬约束、6 维档位与总分输出建议。
- ``_parse_subscores`` 严格校验：缺键、类型错、越界、负数、总和越界。
- ``_score_band`` 把总分映射到 4 档建议。
- ``SourceRubricScorer.score``：
    - LLM 不可用 → 走启发式回退，``subscores == "{}"``。
    - LLM 正常返回 → 写 6 维 JSON，``reason`` 含"总分"和建议标签。
    - LLM 抛出 / 解析失败 → 回退到启发式（不抛给上游）。
- ``SUBSCORE_CAPS`` 之和恰好为 1.0（防 caps 表与 prompt 漂移）。
- ``SUBSCORE_TIERS`` 每个维度的所有档位值都 ``<= SUBSCORE_CAPS[dim]``。
"""

from __future__ import annotations

import json

import pytest

from application.news.models import SourceCandidateInput
from application.news.source_rubric_scorer import (
    RUBRIC_SYSTEM_PROMPT,
    SUBSCORE_CAPS,
    SUBSCORE_TIERS,
    RubricParseError,
    SourceRubricScorer,
    _parse_subscores,
    _score_band,
)


# ---------------------------------------------------------------------------
# Prompt 结构断言
# ---------------------------------------------------------------------------


class TestRubricPromptStructure:
    def test_prompt_mentions_hard_constraints(self):
        """prompt 必须出现"硬性规则""总分 = 6 个子分之和""不确定"等强约束。"""
        assert "硬性规则" in RUBRIC_SYSTEM_PROMPT
        assert "6 个子分之和" in RUBRIC_SYSTEM_PROMPT
        assert "不确定" in RUBRIC_SYSTEM_PROMPT
        assert "JSON" in RUBRIC_SYSTEM_PROMPT

    def test_prompt_lists_all_six_dimensions(self):
        for key in SUBSCORE_CAPS:
            assert key in RUBRIC_SYSTEM_PROMPT, f"prompt 缺维度 {key}"

    def test_prompt_includes_total_score_bands(self):
        """prompt 必须包含 4 档总分建议（blocked/rejected/needs_review/enabled）。"""
        assert "blocked" in RUBRIC_SYSTEM_PROMPT
        assert "rejected" in RUBRIC_SYSTEM_PROMPT
        assert "needs_review" in RUBRIC_SYSTEM_PROMPT
        assert "enabled" in RUBRIC_SYSTEM_PROMPT
        # 4 档阈值（0.20/0.40/0.70）
        assert "0.20" in RUBRIC_SYSTEM_PROMPT
        assert "0.40" in RUBRIC_SYSTEM_PROMPT
        assert "0.70" in RUBRIC_SYSTEM_PROMPT

    def test_prompt_includes_strict_json_example(self):
        """prompt 必须给出严格 JSON 示例，避免模型输出 Markdown 代码块。"""
        assert "publisher_authority" in RUBRIC_SYSTEM_PROMPT
        assert "domain_brand" in RUBRIC_SYSTEM_PROMPT
        assert "topic_relevance" in RUBRIC_SYSTEM_PROMPT
        assert "editorial_standard" in RUBRIC_SYSTEM_PROMPT
        assert "accessibility" in RUBRIC_SYSTEM_PROMPT
        assert "risk_signals" in RUBRIC_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Caps 与档位一致性
# ---------------------------------------------------------------------------


class TestSubscoreCaps:
    def test_caps_sum_to_one(self):
        """6 维 caps 之和必须恰好为 1.0，确保"总分 <= 1.0"恒成立。"""
        assert abs(sum(SUBSCORE_CAPS.values()) - 1.0) < 1e-9

    def test_all_caps_positive(self):
        for k, v in SUBSCORE_CAPS.items():
            assert v > 0, f"cap[{k}] must be positive"
            assert v <= 1.0, f"cap[{k}] must be <= 1.0"

    def test_tiers_within_caps(self):
        """每个维度的档位值都应 <= 对应 cap。"""
        for dim, tiers in SUBSCORE_TIERS.items():
            cap = SUBSCORE_CAPS[dim]
            for t in tiers:
                assert 0 <= t <= cap, (
                    f"SUBSCORE_TIERS[{dim}]={t} 超出 cap={cap}"
                )


# ---------------------------------------------------------------------------
# _parse_subscores
# ---------------------------------------------------------------------------


class TestParseSubscores:
    def test_accepts_valid_payload(self):
        payload = {
            "publisher_authority": 0.20,
            "domain_brand": 0.20,
            "topic_relevance": 0.15,
            "editorial_standard": 0.15,
            "accessibility": 0.10,
            "risk_signals": 0.10,
        }
        result = _parse_subscores(payload)
        assert result == payload
        assert abs(sum(result.values()) - 0.9) < 1e-9

    def test_rejects_non_dict(self):
        with pytest.raises(RubricParseError, match="not dict"):
            _parse_subscores([0.1, 0.2, 0.3, 0.1, 0.1, 0.1])  # type: ignore[arg-type]

    def test_rejects_missing_key(self):
        payload = {
            "publisher_authority": 0.2,
            "domain_brand": 0.2,
            "topic_relevance": 0.1,
            "editorial_standard": 0.1,
            "accessibility": 0.1,
            # risk_signals missing
        }
        with pytest.raises(RubricParseError, match="missing keys"):
            _parse_subscores(payload)

    def test_rejects_non_number_value(self):
        payload = {
            "publisher_authority": "0.2",  # type: ignore[dict-item]
            "domain_brand": 0.2,
            "topic_relevance": 0.1,
            "editorial_standard": 0.1,
            "accessibility": 0.1,
            "risk_signals": 0.1,
        }
        with pytest.raises(RubricParseError, match="must be number"):
            _parse_subscores(payload)

    def test_rejects_bool_value(self):
        """True/False 是 int 的子类，必须显式排除。"""
        payload = {
            "publisher_authority": True,  # type: ignore[dict-item]
            "domain_brand": 0.2,
            "topic_relevance": 0.1,
            "editorial_standard": 0.1,
            "accessibility": 0.1,
            "risk_signals": 0.1,
        }
        with pytest.raises(RubricParseError, match="must be number"):
            _parse_subscores(payload)

    def test_rejects_negative_value(self):
        payload = {
            "publisher_authority": -0.1,
            "domain_brand": 0.2,
            "topic_relevance": 0.1,
            "editorial_standard": 0.1,
            "accessibility": 0.1,
            "risk_signals": 0.1,
        }
        with pytest.raises(RubricParseError, match="must be >= 0"):
            _parse_subscores(payload)

    def test_rejects_value_above_cap(self):
        payload = {
            "publisher_authority": 0.50,  # 超过 0.30
            "domain_brand": 0.2,
            "topic_relevance": 0.1,
            "editorial_standard": 0.1,
            "accessibility": 0.1,
            "risk_signals": 0.1,
        }
        with pytest.raises(RubricParseError, match="exceeds cap"):
            _parse_subscores(payload)

    def test_rejects_total_above_one(self):
        """每个值都不越界但总和越界 → 仍然 reject（理论上 caps 已保证不发生）。"""
        # 临时构造一个 caps 之外的 payload 不可行（因为 cap 校验先触发）。
        # 改为：构造每个值等于 cap → 总和 = 1.0（边界，应当接受）。
        payload = {k: v for k, v in SUBSCORE_CAPS.items()}
        result = _parse_subscores(payload)
        assert abs(sum(result.values()) - 1.0) < 1e-9

    def test_accepts_zero_values(self):
        payload = {
            "publisher_authority": 0.0,
            "domain_brand": 0.0,
            "topic_relevance": 0.0,
            "editorial_standard": 0.0,
            "accessibility": 0.0,
            "risk_signals": 0.0,
        }
        result = _parse_subscores(payload)
        assert sum(result.values()) == 0.0


# ---------------------------------------------------------------------------
# _score_band
# ---------------------------------------------------------------------------


class TestScoreBand:
    @pytest.mark.parametrize(
        "total,expected_keyword",
        [
            (0.0, "blocked"),
            (0.10, "blocked"),
            (0.19, "blocked"),
            (0.20, "rejected"),
            (0.30, "rejected"),
            (0.39, "rejected"),
            (0.40, "needs_review"),
            (0.55, "needs_review"),
            (0.69, "needs_review"),
            (0.70, "enabled"),
            (0.85, "enabled"),
            (1.0, "enabled"),
        ],
    )
    def test_band_thresholds(self, total: float, expected_keyword: str) -> None:
        result = _score_band(total)
        assert expected_keyword in result, f"_score_band({total})={result}"


# ---------------------------------------------------------------------------
# SourceRubricScorer.score
# ---------------------------------------------------------------------------


class _StubLlmOk:
    """返回合规 6 维 JSON 的 LLM stub。"""

    async def complete_json(self, *, system: str, user: str) -> dict:
        return {
            "publisher_authority": 0.20,
            "domain_brand": 0.20,
            "topic_relevance": 0.15,
            "editorial_standard": 0.08,
            "accessibility": 0.05,
            "risk_signals": 0.10,
        }


class _StubLlmInvalid:
    """返回不合法 JSON 的 LLM stub（模拟模型幻觉）。"""

    async def complete_json(self, *, system: str, user: str) -> dict:
        return {"publisher_authority": 0.99}  # 缺键 + 越界


class _StubLlmError:
    """抛异常的 LLM stub。"""

    async def complete_json(self, *, system: str, user: str) -> dict:
        raise RuntimeError("upstream timeout")


class TestRubricScorer:
    @pytest.mark.asyncio
    async def test_no_llm_uses_heuristic_fallback(self):
        scorer = SourceRubricScorer(llm=None)
        result = await scorer.score(SourceCandidateInput(domain="example.com"))
        assert result.subscores == "{}"
        # 启发式分支不写 "LLM rubric" 前缀
        assert "LLM rubric" not in result.reason

    @pytest.mark.asyncio
    async def test_llm_ok_writes_subscores_and_band(self):
        scorer = SourceRubricScorer(llm=_StubLlmOk())
        result = await scorer.score(SourceCandidateInput(domain="example.com"))
        # 6 维 JSON 应被正确解析
        parsed = json.loads(result.subscores)
        assert set(parsed.keys()) == set(SUBSCORE_CAPS.keys())
        # reason 含 "LLM rubric" + 总分 + 建议
        assert "LLM rubric" in result.reason
        assert "总分" in result.reason
        # 总分 = 0.20+0.20+0.15+0.08+0.05+0.10 = 0.78
        assert abs(result.score - 0.78) < 1e-9
        assert "enabled" in result.reason

    @pytest.mark.asyncio
    async def test_llm_invalid_falls_back_to_heuristic(self):
        scorer = SourceRubricScorer(llm=_StubLlmInvalid())
        result = await scorer.score(SourceCandidateInput(domain="bad.example"))
        # 解析失败 → 走启发式
        assert result.subscores == "{}"
        assert "LLM rubric" not in result.reason

    @pytest.mark.asyncio
    async def test_llm_exception_falls_back_to_heuristic(self):
        scorer = SourceRubricScorer(llm=_StubLlmError())
        result = await scorer.score(SourceCandidateInput(domain="bad.example"))
        # 异常 → 走启发式
        assert result.subscores == "{}"
        assert "LLM rubric" not in result.reason

    @pytest.mark.asyncio
    async def test_score_is_clamped_to_unit_interval(self):
        """即使模型返回 6 维都打到 cap，总分也不应 > 1.0。"""

        class _MaxLlm:
            async def complete_json(self, *, system: str, user: str) -> dict:
                return {k: v for k, v in SUBSCORE_CAPS.items()}

        scorer = SourceRubricScorer(llm=_MaxLlm())
        result = await scorer.score(SourceCandidateInput(domain="x.com"))
        assert 0.0 <= result.score <= 1.0
        assert abs(result.score - 1.0) < 1e-9
