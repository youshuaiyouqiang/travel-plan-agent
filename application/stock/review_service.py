"""股票周期复盘服务：编排 7 步思维链，调用 LLM 产复盘文。

设计要点：
- 构造函数注入 data_source（StockDataSource 端口）+ llm（LLMPort 端口）+
  cache_repo（仓储接口）+ skill_md_path（system prompt 源文件）
- 7 步思维链严格对应 SKILL.md 第 3 章（计划文档 §4）
- LLM 输出校验 9 章节 + 降级策略：
  - 第一次 LLM 输出校验通过 → status="completed"
  - 第一次缺章节 → L2 重试 1 次（追加 hint）
  - 重试仍缺 → status="degraded"，仍存档
  - 数据全空（market/趋势/watchlist 全空）→ status="no_data"，不调 LLM
- 复盘 Service 只通过 StockDataSource 端口读缓存，不直接 import akshare

应用层不 import infrastructure（AGENTS.md §8.3）：cache_repo 接口由
调用方注入；本模块仅依赖 domain 端口与 Pydantic DTO。
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Protocol

from domain.shared.llm.ports import LLMPort
from domain.stock.ports import StockDataSource

logger = logging.getLogger(__name__)


# ── 必含章节清单（与 SKILL.md 第 9 章节对齐；顺序固定） ──
REQUIRED_SECTIONS: tuple[str, ...] = (
    "## 一、周期定位",
    "## 二、大盘与量能",
    "## 三、情绪指标详解",
    "## 四、板块轮动",
    "## 五、观察池复盘",
    "## 六、新信号扫描",
    "## 七、明日条件预判",
    "## 八、风险提示",
    "## 九、方法论说明",
)

# 末尾强制声明（AGENTS.md §3 业务红线）
INVESTMENT_DISCLAIMER = "不构成投资建议"

# LLM 输出 token 上限
_MAX_TOKENS = 4000
_LLM_TEMPERATURE = 0.3


class ReviewValidationError(Exception):
    """复盘文章节校验失败。"""


class CacheRepositoryPort(Protocol):
    """缓存仓储端口——由 application 层定义契约，infrastructure 层实现。

    当前 Task 4 范围仅需 ``save_review_report``。其余方法（watchlist upsert
    等）由后续 Task 补全。
    """

    async def save_review_report(
        self,
        *,
        user_id: str,
        trade_date: str,
        content: str,
        status: str,
        llm_metadata: dict[str, Any] | None = None,
    ) -> str:
        """保存复盘文到 review_reports 表，返回生成的 report_id。"""
        ...


def _review_report_dto() -> Any:
    """延迟导入 ReviewReport DTO 避免循环依赖。"""
    from domain.stock.models import ReviewReport

    return ReviewReport


class StockReviewService:
    """股票周期复盘服务——7 步思维链 + LLM + 章节校验 + 降级。"""

    def __init__(
        self,
        data_source: StockDataSource,
        llm: LLMPort,
        cache_repo: CacheRepositoryPort,
        skill_md_path: Path,
    ) -> None:
        """构造复盘服务。

        Args:
            data_source: 实现 StockDataSource 协议的数据源（只读缓存）。
            llm: 实现 LLMPort 协议的 LLM 客户端。
            cache_repo: 缓存仓储端口（实现方在 infrastructure 层）。
            skill_md_path: SKILL.md 路径，作为 system prompt 全文源。
        """
        self._data = data_source
        self._llm = llm
        self._cache = cache_repo
        self._skill_md_path = skill_md_path

    async def generate_review(
        self, *, user_id: str, trade_date: str
    ) -> Any:
        """生成复盘文。

        编排流程：
        1. 拉市场快照 + 情绪趋势 + 观察池 + 信号
        2. 数据全空 → no_data
        3. 加载 SKILL.md 作 system prompt
        4. 构造 user_prompt
        5. 调 LLM 生成 markdown
        6. 校验 9 章节
        7. 缺章节 → 重试 1 次；仍缺 → degraded
        8. 存档 review_reports
        """
        # ── 1. 数据收集 ──
        market = await self._data.get_market_snapshot(trade_date)
        emotion_trend = await self._data.get_emotion_indicators_trend(
            trade_date, days=10
        )
        watchlist = await self._data.get_watchlist()
        signals = await self._data.get_signal_stocks(trade_date)
        sector_rotation = await self._data.get_sector_rotation(trade_date)

        # ── 2. no_data 判定 ──
        market_empty = (
            market is None
            or (market.sh_index is None and market.sz_index is None)
        )
        if market_empty and not emotion_trend and not watchlist:
            logger.info(
                "review_pipeline no_data: user_id=%s trade_date=%s",
                user_id,
                trade_date,
            )
            return await self._save_report(
                user_id=user_id,
                trade_date=trade_date,
                content=self._build_no_data_content(),
                status="no_data",
                llm_metadata={"reason": "market_and_pool_empty"},
            )

        # ── 3-4. prompt 准备 ──
        system_prompt = self._load_skill_prompt()
        user_prompt = self._build_user_prompt(
            market=market,
            emotion_trend=emotion_trend,
            watchlist=watchlist,
            signals=signals,
            sector_rotation=sector_rotation,
        )
        messages = [{"role": "user", "content": user_prompt}]

        # ── 5. 首次 LLM ──
        markdown = await self._llm.complete(
            system=system_prompt,
            messages=messages,
        )
        if not isinstance(markdown, str):
            markdown = str(markdown)

        # ── 6-7. 章节校验 + 降级 ──
        status = "completed"
        try:
            self._validate_markdown(markdown)
        except ReviewValidationError as e:
            logger.warning(
                "review_validation_failed (will retry): %s", e
            )
            # L2 重试 1 次（追加章节提示）
            hint_messages = messages + [
                {
                    "role": "user",
                    "content": (
                        "上次输出缺失必含章节。请严格按以下 9 个标题产出复盘文，"
                        "且末尾必须含「不构成投资建议」：\n"
                        + "\n".join(REQUIRED_SECTIONS)
                    ),
                }
            ]
            markdown = await self._llm.complete(
                system=system_prompt, messages=hint_messages
            )
            if not isinstance(markdown, str):
                markdown = str(markdown)
            try:
                self._validate_markdown(markdown)
            except ReviewValidationError as e2:
                logger.warning("review_validation_retry_failed: %s", e2)
                status = "degraded"

        # ── 8. 存档 ──
        return await self._save_report(
            user_id=user_id,
            trade_date=trade_date,
            content=markdown,
            status=status,
            llm_metadata={
                "temperature": _LLM_TEMPERATURE,
                "max_tokens": _MAX_TOKENS,
            },
        )

    def _load_skill_prompt(self) -> str:
        """从 skill_md_path 加载 SKILL.md 全文作为 system prompt。"""
        return self._skill_md_path.read_text(encoding="utf-8")

    def _validate_markdown(self, markdown: str) -> None:
        """校验 markdown 含 9 章节 + 投资免责申明；缺则抛 ReviewValidationError。"""
        missing = [s for s in REQUIRED_SECTIONS if s not in markdown]
        if missing:
            raise ReviewValidationError(
                f"missing required sections: {missing}"
            )
        if INVESTMENT_DISCLAIMER not in markdown:
            raise ReviewValidationError(
                f"missing investment disclaimer: {INVESTMENT_DISCLAIMER!r}"
            )

    def _build_user_prompt(
        self,
        *,
        market: Any,
        emotion_trend: list[Any],
        watchlist: list[Any],
        signals: list[Any],
        sector_rotation: list[Any],
    ) -> str:
        """构造 user_prompt——结构化数据 + 多日趋势表格。

        数据缺失字段渲染为空字符串或"暂无数据"占位，避免模型臆测。
        """
        parts: list[str] = [
            "请基于以下数据完成今日 A 股周期复盘，严格按方法论 7 步思维链产出 9 章节复盘文。",
            "",
            "## 大盘快照",
            self._format_market(market),
            "",
            "## 情绪指标趋势（最近 10 日，最新在前）",
            self._format_emotion_trend(emotion_trend),
            "",
            "## 板块轮动",
            self._format_sectors(sector_rotation),
            "",
            "## 观察池（活跃股票）",
            self._format_watchlist(watchlist),
            "",
            "## 今日新信号",
            self._format_signals(signals),
            "",
            "请产出完整 9 章节复盘文，末尾必须含「不构成投资建议」声明。",
        ]
        return "\n".join(parts)

    def _build_no_data_content(self) -> str:
        """no_data 状态下的占位 Markdown——含 9 章节标题 + 数据缺失说明。"""
        lines = [f"# {self._today_str()} A股周期复盘（数据缺失）"]
        section_titles = [
            "周期定位",
            "大盘与量能",
            "情绪指标详解",
            "板块轮动",
            "观察池复盘",
            "新信号扫描",
            "明日条件预判",
            "风险提示",
            "方法论说明",
        ]
        for i, t in enumerate(section_titles, start=1):
            lines.append(f"## {self._cn_num(i)}、{t}")
            lines.append("数据缺失，今日无可用截面/趋势数据，不进行判断。")
            lines.append("")
        lines.append(f"本内容仅为数据缺失占位，{INVESTMENT_DISCLAIMER}。")
        return "\n".join(lines)

    @staticmethod
    def _cn_num(n: int) -> str:
        """1..9 → 一/二/.../九。"""
        mapping = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
        return mapping[n] if 0 <= n <= 9 else str(n)

    @staticmethod
    def _today_str() -> str:
        """占位日期——实际 trade_date 由调用方传入。"""
        return "今日"

    def _format_market(self, market: Any) -> str:
        if market is None:
            return "暂无数据"
        return (
            f"上证 {market.sh_index if market.sh_index is not None else 'N/A'}, "
            f"深证 {market.sz_index if market.sz_index is not None else 'N/A'}, "
            f"创业板 {market.cyb_index if market.cyb_index is not None else 'N/A'}, "
            f"两市成交额 {market.total_volume if market.total_volume is not None else 'N/A'} 亿, "
            f"环比 {market.volume_change_pct if market.volume_change_pct is not None else 'N/A'}%, "
            f"连续下跌 {market.consecutive_down_days} 日, "
            f"MA20 状态 {market.ma20_status or 'N/A'}"
        )

    def _format_emotion_trend(self, rows: list[Any]) -> str:
        if not rows:
            return "暂无数据"
        lines = [
            "| trade_date | 涨停 | 跌停 | 有效涨停 | 炸板率 | 最高连板 |",
            "|---|---|---|---|---|---|",
        ]
        for r in rows:
            lines.append(
                f"| {r.trade_date} | {r.limit_up_count} | {r.limit_down_count} "
                f"| {r.valid_limit_up_count} | {r.broken_limit_ratio:.2%} "
                f"| {r.max_consecutive_boards} |"
            )
        return "\n".join(lines)

    def _format_sectors(self, sectors: list[Any]) -> str:
        if not sectors:
            return "暂无数据"
        return "\n".join(
            f"- {s.sector_name} {s.pct_chg if s.pct_chg is not None else 'N/A'}% "
            f"(涨停 {s.limit_up_count})"
            for s in sectors
        )

    def _format_watchlist(self, watchlist: list[Any]) -> str:
        if not watchlist:
            return "暂无数据"
        return "\n".join(
            f"- {w.stock_code} {w.stock_name} (类别 {w.category}, "
            f"入场 {w.entry_date}, 价格 {w.entry_price})"
            for w in watchlist
        )

    def _format_signals(self, signals: list[Any]) -> str:
        if not signals:
            return "暂无数据"
        return "\n".join(
            f"- {s.stock_code} {s.stock_name} 类型={s.signal_type} "
            f"涨跌幅={s.pct_chg if s.pct_chg is not None else 'N/A'}%"
            for s in signals
        )

    async def _save_report(
        self,
        *,
        user_id: str,
        trade_date: str,
        content: str,
        status: str,
        llm_metadata: dict[str, Any],
    ) -> Any:
        """存档复盘文；返回 ReviewReport DTO（带生成 id）。"""
        from domain.stock.models import ReviewReport

        report_id = uuid.uuid4().hex
        saved_id = await self._cache.save_review_report(
            user_id=user_id,
            trade_date=trade_date,
            content=content,
            status=status,
            llm_metadata=llm_metadata,
        )
        if saved_id:
            report_id = saved_id
        return ReviewReport(
            id=report_id,
            user_id=user_id,
            trade_date=trade_date,
            content=content,
            status=status,
            llm_metadata=str(llm_metadata),
            created_at=self._now_iso(),
        )

    @staticmethod
    def _now_iso() -> str:
        """当前 UTC ISO 时间戳。"""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
