"""新闻来源 LLM Rubric 评分器。

业务背景：
- 原 :class:`SourceCandidateScorer` 是纯启发式累加器，与 spec §5 要求的
  "AI 评分必须按 6 维度给分" 不符；评分理由只是一行拼接的维度标签，
  无法约束模型行为。
- 本模块用结构化 rubric prompt 让 LLM 必须按 6 维度给出 ``[0,1]`` 子分，
  解析失败 / 越界 / 缺键时回退到原启发式评分器，保证可用性。

子分明细（写入 ``ai_subscores`` JSON）供前端按维度展示，给管理员
"这个分数为什么是 0.7"的可解释性。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from application.news.models import SourceCandidateInput, SourceScore
from application.news.source_candidate_scorer import SourceCandidateScorer

logger = logging.getLogger(__name__)


# Rubric prompt（结构性重写）：
# 1) 强约束总分公式：总分 = 6 维子分之和，自动 clamp 到 [0, 1]；后端会再次校验。
# 2) 维度上限写为硬性 cap（解析层会拒绝越界值），明确每个维度的"档位"取值，
#    避免模型用浮点随便打。
# 3) 不确定时一律取"该维度的较低档位"——降低误给高分的概率。
# 4) 输出映射建议：总分 < 0.20 → blocked；< 0.40 → rejected / lead_only；
#    0.40~0.70 → needs_review；≥ 0.70 → pending 等待人工通过。
#    这一段仅作模型输出参考，不参与前端展示逻辑。
# 5) JSON 必须严格匹配键名（英文 snake_case），无任何额外文字。
RUBRIC_SYSTEM_PROMPT = """你是新闻来源评审员。任务：根据 6 个独立维度对候选来源打分。

【硬性规则】
1) 每个子分必须严格在 [0, 上限] 区间。超出上限的值会被系统拒收。
2) 总分 = 6 个子分之和（系统会 clamp 到 [0, 1]）。不要自己加权重或相乘。
3) 不确定时一律取"该维度的较低档位"——宁可低估，不要高估。
4) 严禁输出任何解释、前缀、后缀、Markdown 代码块。只输出严格 JSON。
5) 键名固定为下列英文 snake_case，顺序不限但不能缺键。

【6 个维度与离散档位】

A. publisher_authority（主体权威性，上限 0.30）
   - official（政府/学术/上市公司/央媒官网）→ 0.30
   - mainstream（主流市场化媒体）→ 0.20
   - aggregator（聚合站/转载站）→ 0.10
   - unknown（个人站/无法判断）→ 0.05
   - 任何低于 0.05 的推断都视为 0.00

B. domain_brand（域名-品牌一致性 + HTTPS + 反仿冒，上限 0.20）
   - 域名与品牌完全一致 + HTTPS 可用 + 无仿冒信号 → 0.20
   - 一项缺失 → 扣 0.07
   - 两项缺失 → 扣 0.14
   - 三项缺失 → 0.00

C. topic_relevance（领域相关性与地域/语言覆盖，上限 0.15）
   - 与中文新闻主题高度相关 + 覆盖中国大陆/港澳台/全球华语 → 0.15
   - 仅地域相关或仅主题相关（缺一项）→ 0.10
   - 主题勉强相关 → 0.05
   - 与中文新闻无关 → 0.00

D. editorial_standard（编辑标准 + 原始来源能力，上限 0.15）
   - 有公开编辑标准 + 大量一手原创报道 → 0.15
   - 有编辑流程但多为转载 → 0.08
   - 仅转载无原创 → 0.03
   - 不可考 → 0.00

E. accessibility（近期可访问性 + 转载率，上限 0.10）
   - 转载率 ≤ 0.3（近 7 天内多数为首发或一手）→ 0.10
   - 0.3 < 转载率 ≤ 0.6 → 0.05
   - 转载率 > 0.6 → 0.02
   - 站点无法访问或频繁 5xx → 0.00

F. risk_signals（异常内容信号，上限 0.10）
   - 0 个已知风险 → 0.10
   - 1 个已知风险（如标题党、错别字率高、曾被监管处罚）→ 0.07
   - 2 个已知风险 → 0.03
   - ≥ 3 个已知风险 → 0.00
   注：仅本维度被压到 0；其他维度不受此规则牵连。

【总分输出建议（仅供管理员参考，不参与系统计算）】
- 总分 < 0.20 → 建议 blocked（封禁）
- 0.20 ≤ 总分 < 0.40 → 建议 rejected / lead_only
- 0.40 ≤ 总分 < 0.70 → 建议 needs_review
- 总分 ≥ 0.70 → 建议 enabled（可作为 pending 候选等待人工通过）

【严格 JSON 输出示例】
{"publisher_authority": 0.20, "domain_brand": 0.20, "topic_relevance": 0.15, "editorial_standard": 0.08, "accessibility": 0.10, "risk_signals": 0.07}

现在请根据输入的 domain / name 给出 6 维子分。
"""


# 各维度上限（与 prompt 严格对应，用于解析层校验）
SUBSCORE_CAPS: dict[str, float] = {
    "publisher_authority": 0.30,
    "domain_brand": 0.20,
    "topic_relevance": 0.15,
    "editorial_standard": 0.15,
    "accessibility": 0.10,
    "risk_signals": 0.10,
}

# 档位表（与 prompt 严格对应）：用于测试 prompt 文本是否包含关键档位，
# 以及未来按需对照模型输出。开发期不变更，prompt 调整需同步更新此表。
SUBSCORE_TIERS: dict[str, list[float]] = {
    "publisher_authority": [0.30, 0.20, 0.10, 0.05, 0.00],
    "domain_brand": [0.20, 0.13, 0.06, 0.00],
    "topic_relevance": [0.15, 0.10, 0.05, 0.00],
    "editorial_standard": [0.15, 0.08, 0.03, 0.00],
    "accessibility": [0.10, 0.05, 0.02, 0.00],
    "risk_signals": [0.10, 0.07, 0.03, 0.00],
}


class LlmJsonClient(Protocol):
    """``OpenAILLM.complete_json`` 的最小协议；方便测试用 stub 注入。"""

    async def complete_json(self, *, system: str, user: str) -> dict[str, Any]: ...


class RubricParseError(ValueError):
    """Rubric 解析失败：缺键、类型错、越界、JSON 解析失败等。"""


def _parse_subscores(data: Any) -> dict[str, float]:
    """严格校验 LLM 返回的子分；任何不合规抛 :class:`RubricParseError`。

    校验规则：
    1. 必须是 dict；
    2. 必须包含全部 6 个键；
    3. 每个值必须是 ``int`` / ``float`` 且 ``>= 0``；
    4. 每个值必须 ``<= SUBSCORE_CAPS[key]``；
    5. 6 维之和必须 ``<= 1.0 + 1e-6``（浮点容差；理论上 caps 相加恰好为 1.0）。
    """
    if not isinstance(data, dict):
        raise RubricParseError(f"rubric response is not dict: {type(data).__name__}")
    missing = [k for k in SUBSCORE_CAPS if k not in data]
    if missing:
        raise RubricParseError(f"rubric response missing keys: {missing}")
    out: dict[str, float] = {}
    for key, cap in SUBSCORE_CAPS.items():
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RubricParseError(
                f"rubric[{key}] must be number, got {type(value).__name__}"
            )
        value = float(value)
        if value < 0:
            raise RubricParseError(f"rubric[{key}] must be >= 0, got {value}")
        if value > cap:
            raise RubricParseError(
                f"rubric[{key}]={value} exceeds cap {cap}"
            )
        out[key] = value
    total = sum(out.values())
    if total > 1.0 + 1e-6:
        raise RubricParseError(
            f"rubric total {total:.4f} exceeds 1.0 (caps not respected)"
        )
    return out


def _score_band(total: float) -> str:
    """把总分映射为决策建议标签；仅写入 ``SourceScore.reason`` 便于排查。

    与 prompt 中的【总分输出建议】表格严格对应：
    - < 0.20       → blocked
    - < 0.40       → rejected
    - < 0.70       → needs_review
    - >= 0.70      → enabled
    """
    if total < 0.20:
        return "建议 blocked"
    if total < 0.40:
        return "建议 rejected/lead_only"
    if total < 0.70:
        return "建议 needs_review"
    return "建议 enabled"


class SourceRubricScorer:
    """LLM Rubric 评分器；LLM 不可用或解析失败时回退到 :class:`SourceCandidateScorer`。

    使用方式：
    - ``SourceService.discover_candidate`` 在发现新候选时调用 :meth:`score`。
    - 启发式回退通过 :class:`SourceCandidateScorer`，行为与改造前一致。
    - ``llm=None`` 时直接走回退（不发起 LLM 调用）。
    """

    def __init__(self, llm: LlmJsonClient | None = None) -> None:
        self._llm = llm
        self._fallback = SourceCandidateScorer()

    async def score(self, candidate: SourceCandidateInput) -> SourceScore:
        """对候选来源评分；返回 :class:`SourceScore`。

        返回值的 ``subscores`` 字段：
        - LLM rubric 模式：6 维度 JSON 字符串。
        - 启发式回退：``"{}"``。
        """
        if self._llm is None:
            logger.info("SourceRubricScorer: no LLM configured, using heuristic")
            return self._fallback.score(candidate)

        user_payload = json.dumps(
            {"domain": candidate.domain, "name": candidate.name},
            ensure_ascii=False,
        )
        try:
            data = await self._llm.complete_json(
                system=RUBRIC_SYSTEM_PROMPT, user=user_payload
            )
            subscores = _parse_subscores(data)
        except Exception as e:  # noqa: BLE001 — 任何 LLM/解析失败都降级
            logger.warning(
                "SourceRubricScorer: LLM scoring failed for %s, falling back: %s",
                candidate.domain,
                e,
            )
            return self._fallback.score(candidate)

        total = sum(subscores.values())
        total = max(0.0, min(1.0, total))
        reason = f"LLM rubric · 总分 {total:.2f} · {_score_band(total)}"
        return SourceScore(
            score=total,
            reason=reason,
            subscores=json.dumps(subscores, ensure_ascii=False),
        )
