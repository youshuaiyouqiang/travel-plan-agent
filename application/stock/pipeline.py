"""股票复盘抓取管线门面——供调度器 / admin/refresh 调用。

设计要点（AGENTS.md §3 业务边界 + §8.1 端口先于实现 + §8.3 禁止依赖方向）：
- 构造依赖注入 fetchers 列表（实现 ``domain.stock.pipeline_ports.Fetcher``）
  + cache_repo（实现 ``CacheWritePort``）+ correlation_analyzer
- run_morning / run_close 串行调用各 fetcher，fetcher 内部已封装
  akshare 异常处理（失败 log warning + 返回 0）
- run_correlation 仅周五在收盘管线后链式追加
- 模块级 get/set_default_pipeline 供 scheduler 函数内惰性取用
- application 层不 import infrastructure（§8.3 零容忍）
"""

from __future__ import annotations

import logging
import time

from domain.stock.pipeline_ports import (
    CacheWritePort,
    CorrelationAnalyzer,
    Fetcher,
)
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


# ── DTO ──────────────────────────────────────────────────


class PipelineResult(BaseModel):
    """单次抓取管线的执行结果。"""

    model_config = ConfigDict(extra="forbid")
    phase: str  # morning / close / correlation
    trade_date: str
    written: int  # 写入条数
    errors: list[str] = []
    duration_ms: int = 0


# ── 抓取门面 ──────────────────────────────────────────


class StockPipelineService:
    """股票抓取管线门面——调度器/admin 触发；fetcher 串行编排。"""

    def __init__(
        self,
        *,
        repo: CacheWritePort,
        fetchers: list[Fetcher] | None = None,
        correlation_analyzer: CorrelationAnalyzer | None = None,
    ) -> None:
        """构造管线。

        Args:
            repo: 缓存仓储（实现 CacheWritePort 协议）。
            fetchers: Fetcher 协议实现列表；None 时为空列表。
            correlation_analyzer: 周复盘庄股/抱团分析器；可空。
        """
        self._repo = repo
        self._fetchers: list[Fetcher] = list(fetchers or [])
        self._correlation = correlation_analyzer

    def add_fetcher(self, fetcher: Fetcher) -> None:
        """运行时追加 fetcher（便于 lifespan 内挂接新 fetcher）。"""
        self._fetchers.append(fetcher)

    async def _run_all_fetchers(
        self, trade_date: str, errors: list[str]
    ) -> int:
        """串行调用所有 fetcher；单 fetcher 失败不影响其他。"""
        total_written = 0
        for fetcher in self._fetchers:
            try:
                written = await fetcher.run(
                    trade_date=trade_date, repo=self._repo
                )
                total_written += int(written or 0)
            except Exception as e:  # noqa: BLE001 — 边界 catch-all
                logger.warning(
                    "pipeline fetcher %s failed: %s", fetcher.name, e
                )
                errors.append(f"{fetcher.name}: {e}")
        return total_written

    async def run_morning(self, trade_date: str) -> PipelineResult:
        """早盘管线（11:30 窗口）——串行调用各 fetcher。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            PipelineResult。
        """
        start = time.monotonic()
        errors: list[str] = []
        written = await self._run_all_fetchers(trade_date, errors)
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "pipeline morning: trade_date=%s written=%d duration_ms=%d",
            trade_date,
            written,
            duration_ms,
        )
        return PipelineResult(
            phase="morning",
            trade_date=trade_date,
            written=written,
            errors=errors,
            duration_ms=duration_ms,
        )

    async def run_close(self, trade_date: str) -> PipelineResult:
        """收盘管线（16:30 窗口）——串行调用各 fetcher。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            PipelineResult。
        """
        start = time.monotonic()
        errors: list[str] = []
        written = await self._run_all_fetchers(trade_date, errors)
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "pipeline close: trade_date=%s written=%d duration_ms=%d",
            trade_date,
            written,
            duration_ms,
        )
        return PipelineResult(
            phase="close",
            trade_date=trade_date,
            written=written,
            errors=errors,
            duration_ms=duration_ms,
        )

    async def run_correlation(
        self, end_date: str, days: int = 7
    ) -> PipelineResult:
        """周复盘庄股/抱团分析——仅周五链式触发。

        Args:
            end_date: 截止交易日（YYYYMMDD）。
            days: 回溯天数（默认 7）。

        Returns:
            PipelineResult。
        """
        start = time.monotonic()
        errors: list[str] = []
        written = 0

        if self._correlation is None:
            logger.warning(
                "pipeline correlation: no correlation_analyzer wired; skip"
            )
            errors.append("correlation_analyzer not configured")
        else:
            try:
                await self._correlation.analyze(end_date, days)
                written = 1
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "pipeline correlation: %s failed: %s",
                    self._correlation.name,
                    e,
                )
                errors.append(f"{self._correlation.name}: {e}")

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "pipeline correlation: end_date=%s days=%d written=%d duration_ms=%d",
            end_date,
            days,
            written,
            duration_ms,
        )
        return PipelineResult(
            phase="correlation",
            trade_date=end_date,
            written=written,
            errors=errors,
            duration_ms=duration_ms,
        )


# ── 进程内默认实例注册（接缝 4） ────────────────────────

_DEFAULT_PIPELINE: StockPipelineService | None = None


def set_default_pipeline(pipeline: StockPipelineService | None) -> None:
    """注册/清除进程内默认 pipeline 实例。

    由组合根（app.py）启动时调用；scheduler 函数内惰性取用，
    避免 application 反向 import app.py 造成循环依赖。
    """
    global _DEFAULT_PIPELINE
    _DEFAULT_PIPELINE = pipeline


def get_default_pipeline() -> StockPipelineService | None:
    """取得当前进程默认 pipeline；未注册返回 None。"""
    return _DEFAULT_PIPELINE
