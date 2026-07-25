"""新闻锚点 prompt 构造器。

设计要点：
- 仅使用新闻元数据（标题、来源、URL、发布时间、摘要）拼装 prompt 段；
  绝不注入新闻全文。
- 返回的字符串是给新闻 Agent 的"工作上下文"，既要让 LLM 知道当前锚点是哪条新闻，
  又要在 session 历史中可识别为锚点而非用户原文，以便 UI 区分渲染。
- 纯函数，依赖 NewsItem 数据类；便于单元测试覆盖（不依赖数据库/HTTP/异步）。
"""

from __future__ import annotations

from application.news.evidence_prompt import (
    build_empty_evidence_block,
    build_evidence_block,
)
from application.news.models import NewsAnalysisResponse, NewsItem

ANCHOR_HEADER = "[新闻锚点]"
USER_QUESTION_HEADER = "[用户问题]"


def build_news_anchor_prompt(anchor: NewsItem) -> str:
    """构造新闻锚点 prompt 段。

    字段顺序与 ``NewsItem`` 字段顺序保持一致（id / title / source / url /
    summary / published_at）。``summary`` 允许为空；为空时不写"摘要"行，
    避免无意义空字段。``published_at`` 允许为空字符串，统一显示"未知"。

    返回的多行文本以 ``[新闻锚点]`` 开头，便于下游或前端解析识别锚点边界。
    """
    lines: list[str] = [ANCHOR_HEADER]
    lines.append(f"- 标题：{anchor.title}")
    lines.append(f"- 来源：{anchor.source}")
    lines.append(f"- 链接：{anchor.url}")
    if anchor.summary:
        lines.append(f"- 摘要：{anchor.summary}")
    published = anchor.published_at or "未知"
    lines.append(f"- 发布时间：{published}")
    return "\n".join(lines)


def build_news_anchor_message(anchor: NewsItem, user_message: str) -> str:
    """把新闻锚点拼接到用户消息前面，形成完整的 user 消息。

    结构：
        [新闻锚点]
        - 标题：...
        - 来源：...
        ...
        [用户问题]
        {用户原文}

    不裁剪、不重写 user_message；空消息也保留 ``[用户问题]`` 段以保证锚点边界清晰。
    """
    anchor_block = build_news_anchor_prompt(anchor)
    return f"{anchor_block}\n{USER_QUESTION_HEADER}\n{user_message}"


def build_news_full_context(
    anchor: NewsItem,
    user_message: str,
    analysis: NewsAnalysisResponse | None,
) -> str:
    """拼装完整的新闻研判上下文：锚点 + 证据 + 线索 + 用户问题。

    结构：
        [新闻锚点]
        - 标题：...
        ...
        [证据卡片]
        ...
        [未核实线索]
        ...
        [用户问题]
        {用户原文}

    ``analysis`` 可为 ``None``（生产默认 ``EmptyEvidenceProvider`` 返回空列表
    时也走同一路径，``build_evidence_block`` 内部会输出"暂无证据或线索"占位）。
    调用方在调用本函数前已过滤好"news_analysis_locked + 锚点存在"的判断。

    无论 ``analysis`` 是否为 ``None``，都同时输出 ``[证据卡片]`` 与 ``[未核实线索]``
    两段占位；这样新闻 Agent 不会把"占位"误读为"注入未完成"而反问用户。
    """
    anchor_block = build_news_anchor_prompt(anchor)
    evidence_block = (
        build_evidence_block(analysis) if analysis is not None else build_empty_evidence_block()
    )
    return (
        f"{anchor_block}\n"
        f"{evidence_block}\n"
        f"{USER_QUESTION_HEADER}\n"
        f"{user_message}"
    )
