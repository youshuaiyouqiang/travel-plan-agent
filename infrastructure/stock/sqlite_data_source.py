"""SQLite 股票数据源——读侧 StockDataSource 协议实现。

设计要点（AGENTS.md §8.1 端口先于实现 + §4 SQL 安全）：
- 唯一满足 ``domain.stock.ports.StockDataSource`` 协议的 SQLite 读实现
- 复盘链路（review_service / query_service / correlation_service）必须
  通过本数据源读缓存，**不得直连 akshare**（AGENTS.md §3 业务红线）
- 表名通过硬编码字面量（白名单）写入 SQL；用户输入一律 ? 占位符
- 单连接；通过 ``get_connection()`` 取得当前线程连接
- 进程内单例，可由组合根装配
"""

from __future__ import annotations

import json
import logging
import sqlite3

from domain.stock.models import (
    CorrelationResult,
    EmotionIndicators,
    MarketSnapshot,
    ResistantSector,
    SectorDaily,
    SectorDivergence,
    SectorHeatDistribution,
    SectorLeader,
    SectorPerformance,
    SignalStock,
    StockDaily,
    StrongRepairLeader,
    WatchlistStock,
    LimitStock,
)

logger = logging.getLogger(__name__)


# ── 表名白名单（与 cache_repository 对齐） ──────────────
_ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "market_index_daily",
        "stock_daily",
        "limit_stocks_daily",
        "board_ladder_daily",
        "sector_daily",
        "emotion_daily",
        "watchlist_stocks",
        "review_reports",
    }
)


def _validate_table(table: str) -> None:
    """校验表名在白名单内（防御性）。"""
    if table not in _ALLOWED_TABLES:
        raise ValueError(
            f"Refusing to read non-whitelisted table: {table!r}"
        )


class SqliteStockDataSource:
    """SQLite 股票数据源——读侧。

    复盘链路只读缓存（AGENTS.md §3）；不允许发起 akshare 网络请求。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """构造数据源。

        Args:
            conn: 已配置的 sqlite3.Connection。
        """
        self._conn = conn

    # ── market snapshot ─────────────────────────────────────

    async def get_market_snapshot(self, trade_date: str) -> MarketSnapshot:
        """拉取大盘快照（上证/深证/创业板/成交额/连续下跌天数/MA20）。"""
        _validate_table("market_index_daily")
        # 取所有指数；聚合得到 sh / sz / cyb
        rows = self._conn.execute(
            "SELECT index_code, close, pct_chg FROM market_index_daily "
            "WHERE trade_date = ?",
            (trade_date,),
        ).fetchall()
        sh_index: float | None = None
        sz_index: float | None = None
        cyb_index: float | None = None
        for r in rows:
            code = r["index_code"]
            close = r["close"]
            if code in ("000001", "sh000001"):
                sh_index = close
            elif code in ("399001", "sz399001"):
                sz_index = close
            elif code in ("399006", "sz399006"):
                cyb_index = close
        # 成交额 / 量能：来自 emotion_daily（v021 schema 唯一存成交额的表）
        _validate_table("emotion_daily")
        e_row = self._conn.execute(
            "SELECT total_volume, volume_change_pct FROM emotion_daily "
            "WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()
        total_volume = e_row["total_volume"] if e_row else None
        volume_change_pct = e_row["volume_change_pct"] if e_row else None
        # 连续下跌天数 / MA20：未在 schema 内存储，返回占位
        return MarketSnapshot(
            trade_date=trade_date,
            sh_index=sh_index,
            sz_index=sz_index,
            cyb_index=cyb_index,
            total_volume=total_volume,
            volume_change_pct=volume_change_pct,
            consecutive_down_days=0,
            ma20_status=None,
        )

    # ── emotion ────────────────────────────────────────────

    async def get_emotion_indicators(
        self, trade_date: str
    ) -> EmotionIndicators:
        _validate_table("emotion_daily")
        row = self._conn.execute(
            "SELECT * FROM emotion_daily WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()
        if row is None:
            return EmotionIndicators(
                trade_date=trade_date,
                limit_up_count=0,
                limit_down_count=0,
                valid_limit_up_count=0,
                broken_limit_ratio=0.0,
                max_consecutive_boards=0,
                yesterday_limit_up_today_premium=None,
                total_volume=0.0,
                volume_change_pct=None,
                phase=None,
                phase_confidence=None,
                phase_reason=None,
            )
        return self._row_to_emotion(row)

    async def get_emotion_indicators_trend(
        self, end_date: str, days: int
    ) -> list[EmotionIndicators]:
        """拉取最近 days 天的情绪数据，按 trade_date DESC。"""
        _validate_table("emotion_daily")
        bounded_days = max(1, min(int(days), 60))
        rows = self._conn.execute(
            "SELECT * FROM emotion_daily "
            "WHERE trade_date <= ? "
            "ORDER BY trade_date DESC LIMIT ?",
            (end_date, bounded_days),
        ).fetchall()
        return [self._row_to_emotion(r) for r in rows]

    # ── watchlist / sector rotation / signals ──────────────

    async def get_watchlist(self) -> list[WatchlistStock]:
        _validate_table("watchlist_stocks")
        rows = self._conn.execute(
            "SELECT stock_code, stock_name, category, entry_date, entry_price, "
            "status, market_index_snapshot, notes "
            "FROM watchlist_stocks WHERE status = 'active' "
            "ORDER BY category ASC, entry_date DESC"
        ).fetchall()
        return [self._row_to_watchlist(r) for r in rows]

    async def get_stock_daily(
        self, stock_code: str, days: int
    ) -> list[StockDaily]:
        _validate_table("stock_daily")
        bounded_days = max(1, min(int(days), 60))
        rows = self._conn.execute(
            "SELECT trade_date, stock_code, open, close, high, low, volume, pct_chg "
            "FROM stock_daily WHERE stock_code = ? "
            "ORDER BY trade_date DESC LIMIT ?",
            (stock_code, bounded_days),
        ).fetchall()
        return [
            StockDaily(
                trade_date=r["trade_date"],
                stock_code=r["stock_code"],
                open=r["open"],
                close=r["close"],
                high=r["high"],
                low=r["low"],
                volume=r["volume"],
                pct_chg=r["pct_chg"],
            )
            for r in rows
        ]

    async def get_signal_stocks(
        self, trade_date: str
    ) -> list[SignalStock]:
        """新信号股：占位实现（schema 未单独建 signal_stocks 表）→ 返空。"""
        return []

    async def get_sector_rotation(
        self, trade_date: str
    ) -> list[SectorPerformance]:
        _validate_table("sector_daily")
        rows = self._conn.execute(
            "SELECT trade_date, sector_code, sector_name, pct_chg, "
            "leading_stock_codes, limit_up_count "
            "FROM sector_daily WHERE trade_date = ? "
            "ORDER BY pct_chg DESC",
            (trade_date,),
        ).fetchall()
        return [self._row_to_sector_perf(r) for r in rows]

    async def get_sector_heat_distribution(
        self, trade_date: str
    ) -> list[SectorHeatDistribution]:
        """板块涨停时段分布：未在 schema 内实现 → 返空。"""
        return []

    async def get_strong_repair_leaders(self) -> list[StrongRepairLeader]:
        """强修复领涨板块：未在 schema 内实现 → 返空。"""
        return []

    async def get_resistant_sectors(
        self, trade_date: str
    ) -> list[ResistantSector]:
        """抗跌板块：未在 schema 内实现 → 返空。"""
        return []

    async def get_sector_leaders(
        self, sector_name: str
    ) -> list[SectorLeader]:
        """板块龙头：未在 schema 内实现 → 返空（占位）。"""
        return []

    async def get_sector_divergence(
        self, trade_date: str
    ) -> list[SectorDivergence]:
        """板块高潮后分歧：未在 schema 内实现 → 返空。"""
        return []

    async def get_correlation(
        self, end_date: str, days: int
    ) -> CorrelationResult:
        """庄股/抱团识别：未在 schema 内实现 → 返空 result。
        CorrelationService 会判定空 → 409 CORRELATION_NOT_READY。
        """
        return CorrelationResult(end_date=end_date, window_days=days)

    async def get_sector_history(
        self, sector_name: str, days: int
    ) -> list[SectorDaily]:
        """板块多日：sector_name 为空时返全板块。"""
        _validate_table("sector_daily")
        bounded_days = max(1, min(int(days), 60))
        if sector_name:
            rows = self._conn.execute(
                "SELECT trade_date, sector_code, sector_name, pct_chg, "
                "leading_stock_codes, limit_up_count "
                "FROM sector_daily WHERE sector_name = ? "
                "ORDER BY trade_date DESC LIMIT ?",
                (sector_name, bounded_days),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT trade_date, sector_code, sector_name, pct_chg, "
                "leading_stock_codes, limit_up_count "
                "FROM sector_daily "
                "ORDER BY trade_date DESC LIMIT ?",
                (bounded_days,),
            ).fetchall()
        return [
            SectorDaily(
                trade_date=r["trade_date"],
                sector_code=r["sector_code"],
                sector_name=r["sector_name"],
                pct_chg=r["pct_chg"],
                leading_stock_codes=json.loads(
                    r["leading_stock_codes"] or "[]"
                ),
                limit_up_count=r["limit_up_count"],
            )
            for r in rows
        ]

    async def get_limit_stocks(
        self, trade_date: str
    ) -> list[LimitStock]:
        _validate_table("limit_stocks_daily")
        rows = self._conn.execute(
            "SELECT trade_date, stock_code, stock_name, limit_type, "
            "consecutive_boards, first_limit_time, last_limit_time, "
            "open_count, is_valid_limit_up "
            "FROM limit_stocks_daily WHERE trade_date = ?",
            (trade_date,),
        ).fetchall()
        return [
            LimitStock(
                trade_date=r["trade_date"],
                stock_code=r["stock_code"],
                stock_name=r["stock_name"],
                limit_type=r["limit_type"],
                consecutive_boards=r["consecutive_boards"],
                first_limit_time=r["first_limit_time"],
                last_limit_time=r["last_limit_time"],
                open_count=r["open_count"],
                is_valid_limit_up=bool(r["is_valid_limit_up"]),
            )
            for r in rows
        ]

    # Task 10：启动期缓存回填的"是否已有数据"判定
    # 用 ``SELECT 1 ... LIMIT 1`` 比 COUNT(*) 快（命中即停），返回 bool 语义清晰。
    async def has_limit_stocks(self, trade_date: str) -> bool:
        """判定指定交易日的 limit_stocks_daily 表是否有任何行。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            True 当且仅当 limit_stocks_daily 中存在 trade_date 的任意行。
        """
        _validate_table("limit_stocks_daily")
        row = self._conn.execute(
            "SELECT 1 FROM limit_stocks_daily WHERE trade_date = ? LIMIT 1",
            (trade_date,),
        ).fetchone()
        return row is not None

    # Task 13：大盘指数数据回填的"是否已有数据"判定
    async def has_market_index(self, trade_date: str) -> bool:
        """判定指定交易日的 market_index_daily 表是否有任何行。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            True 当且仅当 market_index_daily 中存在 trade_date 的任意行。
        """
        _validate_table("market_index_daily")
        row = self._conn.execute(
            "SELECT 1 FROM market_index_daily WHERE trade_date = ? LIMIT 1",
            (trade_date,),
        ).fetchone()
        return row is not None

    # ── 内部辅助 ────────────────────────────────────────

    @staticmethod
    def _row_to_emotion(row: sqlite3.Row) -> EmotionIndicators:
        return EmotionIndicators(
            trade_date=row["trade_date"],
            limit_up_count=row["limit_up_count"],
            limit_down_count=row["limit_down_count"],
            valid_limit_up_count=row["valid_limit_up_count"],
            broken_limit_ratio=row["broken_limit_ratio"] or 0.0,
            max_consecutive_boards=row["max_consecutive_boards"],
            yesterday_limit_up_today_premium=row[
                "yesterday_limit_up_today_premium"
            ],
            total_volume=row["total_volume"] or 0.0,
            volume_change_pct=row["volume_change_pct"],
            phase=row["phase"],
            phase_confidence=row["phase_confidence"],
            phase_reason=row["phase_reason"],
        )

    @staticmethod
    def _row_to_watchlist(row: sqlite3.Row) -> WatchlistStock:
        return WatchlistStock(
            stock_code=row["stock_code"],
            stock_name=row["stock_name"],
            category=row["category"],
            entry_date=row["entry_date"],
            entry_price=row["entry_price"],
            status=row["status"],
            market_index_snapshot=row["market_index_snapshot"],
            notes=row["notes"],
        )

    @staticmethod
    def _row_to_sector_perf(row: sqlite3.Row) -> SectorPerformance:
        return SectorPerformance(
            trade_date=row["trade_date"],
            sector_code=row["sector_code"],
            sector_name=row["sector_name"],
            pct_chg=row["pct_chg"],
            leading_stock_codes=json.loads(row["leading_stock_codes"] or "[]"),
            limit_up_count=row["limit_up_count"],
        )
