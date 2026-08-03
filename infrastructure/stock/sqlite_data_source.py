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

from domain.stock.emotion_cycles import identify_emotion_cycles
from domain.stock.models import (
    CorrelationResult,
    EmotionCycleSegment,
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


def _resolve_trade_date_with_data(
    conn: sqlite3.Connection, table: str, target_date: str
) -> str | None:
    """非交易日 fallback：返回 <= target_date 且指定表里有数据的最近 trade_date。

    设计要点（Bug③ 修复）：
    - 大盘快照 / 板块轮动接口，调用方传"今天"日期；
      周末/节假日该日期在 market_index_daily / sector_daily 中无数据。
    - 原版 SELECT ... WHERE trade_date = today 直接返空 → 前端所有卡片"—"。
    - 现在 fallback 到 <= today 的最近有数据日期，MarketSnapshot.trade_date
      / SectorPerformance.trade_date 反映**实际**查询的日期，前端可据此
      显示"截至 20260731"。

    边界：
    - forward-only：``WHERE trade_date <= target_date``，绝不回退到未来
      （避免 cache 时间戳错乱时把未来数据当历史展示）
    - 整表为空 → 返 None，调用方保持 target_date 不变（行为与旧版一致）

    Args:
        conn: SQLite 连接。
        table: 目标表名（必须在 _ALLOWED_TABLES 白名单内）。
        target_date: 目标交易日（YYYYMMDD）。

    Returns:
        实际有数据的交易日；无数据返 None。
    """
    _validate_table(table)
    row = conn.execute(
        f"SELECT MAX(trade_date) AS latest FROM {table} "
        f"WHERE trade_date <= ?",
        (target_date,),
    ).fetchone()
    if row is None or row["latest"] is None:
        return None
    return str(row["latest"])


def _compute_top_board_leaders(
    conn: sqlite3.Connection, trade_date: str
) -> list[str]:
    """取 max_consecutive_boards 对应的 stock_code 列表。

    修复：emotion_daily.max_consecutive_boards 只存数字，缺少龙头归属。
    该函数多查一次 limit_stocks_daily（白名单内）给出"龙头列表"，
    供"最高板龙头"前端表。

    Args:
        conn: SQLite 连接（必须能读 limit_stocks_daily）。
        trade_date: 交易日（YYYYMMDD）。

    Returns:
        已排序的 stock_code 列表（空列表 = 该日无涨停股）。
    """
    _validate_table("limit_stocks_daily")
    max_row = conn.execute(
        "SELECT MAX(consecutive_boards) AS m FROM limit_stocks_daily "
        "WHERE trade_date = ?",
        (trade_date,),
    ).fetchone()
    max_boards = max_row["m"] if max_row is not None else None
    if max_boards is None or int(max_boards) <= 0:
        return []
    rows = conn.execute(
        "SELECT stock_code FROM limit_stocks_daily "
        "WHERE trade_date = ? AND consecutive_boards = ? "
        "ORDER BY stock_code",
        (trade_date, int(max_boards)),
    ).fetchall()
    return [r["stock_code"] for r in rows]


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
        """拉取大盘快照（上证/深证/创业板/成交额/连续下跌天数/MA20）。

        非交易日 fallback（Bug③）：当 trade_date 无 market_index_daily 数据时
        （周末/节假日），自动回退到 <= trade_date 的最近有数据交易日。
        MarketSnapshot.trade_date 反映实际查询的日期，前端可据此标注
        "截至 20260731"。
        """
        _validate_table("market_index_daily")
        # Bug③ 修复：非交易日 fallback
        resolved = _resolve_trade_date_with_data(
            self._conn, "market_index_daily", trade_date
        )
        effective_date = resolved if resolved is not None else trade_date
        # 取所有指数；聚合得到 sh / sz / cyb
        rows = self._conn.execute(
            "SELECT index_code, close, pct_chg, volume FROM market_index_daily "
            "WHERE trade_date = ?",
            (effective_date,),
        ).fetchall()
        sh_index: float | None = None
        sz_index: float | None = None
        cyb_index: float | None = None
        sh_volume: float = 0.0  # 修复：原 SELECT 漏了 volume，两市成交额永远 None
        sz_volume: float = 0.0
        for r in rows:
            code = r["index_code"]
            close = r["close"]
            vol = float(r["volume"]) if r["volume"] is not None else 0.0
            if code in ("000001", "sh000001"):
                sh_index = close
            elif code in ("399001", "sz399001"):
                sz_index = close
                sz_volume = vol
            elif code in ("399006", "sz399006"):
                cyb_index = close
                sz_volume += vol
            if code in ("000001", "sh000001"):
                sh_volume = vol
        # 修复：根据 market_index_daily 各指数的 volume 求和得到两市成交额（元）。
        total_volume_from_index: float | None = (
            (sh_volume + sz_volume) if (sh_volume > 0 or sz_volume > 0) else None
        )
        # 成交额 / 量能：emotion_daily.total_volume 仅在 sum==0 时作为 fallback 兜底
        _validate_table("emotion_daily")
        e_row = self._conn.execute(
            "SELECT total_volume, volume_change_pct FROM emotion_daily "
            "WHERE trade_date = ?",
            (effective_date,),
        ).fetchone()
        # 修复：两市成交额优先用 market_index_daily 求和；全为 0 时 fallback emotion_daily
        total_volume: float | None = total_volume_from_index
        if total_volume is None:
            total_volume = e_row["total_volume"] if e_row else None
        volume_change_pct = e_row["volume_change_pct"] if e_row else None
        # 连续下跌天数 / MA20：未在 schema 内存储，返回占位
        return MarketSnapshot(
            trade_date=effective_date,
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
        return self._row_to_emotion(row, self._conn)

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
        return [self._row_to_emotion(r, self._conn) for r in rows]  # noqa: PERF401

    async def get_emotion_cycles(
        self, end_date: str, lookback_days: int = 60
    ) -> list[EmotionCycleSegment]:
        """返回近 N 日的情绪周期段（峰谷检测，客观切分）。

        Task E.10：为 SKILL.md §三第 3 步"与上一轮退潮比"提供客观数据。
        不判定阶段方向——只提供峰/谷/首次修复日 + 涨停数，
        LLM 基于代码提供的周期段数据，对比"当前涨停数 vs 上一轮首次修复涨停数"。

        实现要点：
        - 子查询取最近 N 日（DESC LIMIT），外层按 ASC 重排（算法要求正序）
        - 调 ``domain.stock.emotion_cycles.identify_emotion_cycles`` 做峰谷检测
        - 历史数据不足 (<5 日) 或无峰谷模式时返回空列表

        Args:
            end_date: 截止交易日（YYYYMMDD）。
            lookback_days: 回看天数（默认 60，上限 60 防止过载）。

        Returns:
            EmotionCycleSegment 列表。
        """
        _validate_table("emotion_daily")
        bounded_days = max(5, min(int(lookback_days), 60))
        # 子查询取最近 N 日（DESC LIMIT），外层按 ASC 重排供算法使用
        rows = self._conn.execute(
            "SELECT * FROM ("
            "SELECT * FROM emotion_daily "
            "WHERE trade_date <= ? "
            "ORDER BY trade_date DESC LIMIT ?"
            ") ORDER BY trade_date ASC",
            (end_date, bounded_days),
        ).fetchall()
        history = [self._row_to_emotion(r) for r in rows]
        return identify_emotion_cycles(history)

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
            "SELECT trade_date, stock_code, open, close, high, low, "
            "volume, pct_chg, turnover "
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
                turnover=r["turnover"],
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
        """板块轮动——非交易日 fallback 到最近有数据日期。

        Bug③ 修复：trade_date 无 sector_daily 数据（周末/节假日）→ 回退到
        <= trade_date 的最近有数据交易日。SectorPerformance.trade_date
        反映实际查询日期。
        """
        _validate_table("sector_daily")
        resolved = _resolve_trade_date_with_data(
            self._conn, "sector_daily", trade_date
        )
        effective_date = resolved if resolved is not None else trade_date
        rows = self._conn.execute(
            "SELECT trade_date, sector_code, sector_name, pct_chg, "
            "leading_stock_codes, limit_up_count "
            "FROM sector_daily WHERE trade_date = ? "
            "ORDER BY pct_chg DESC",
            (effective_date,),
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
        self, sector_name: str, days: int, end_date: str
    ) -> list[SectorDaily]:
        """板块多日：sector_name 为空时返全板块。

        Bug 修复：原 SQL ``LIMIT ?`` 限制的是**行数**而非**天数**。
        当 sector_name 为空时，90 个板块 × 1 天 = 90 行，
        ``LIMIT 10`` 只返回最近 1 天的 10 行，无法展示多日轮动。

        修复：先用子查询取 ``<= end_date`` 的最近 N 个**交易日**，
        再关联全板块数据，确保返回 N 天 × 所有板块。
        """
        _validate_table("sector_daily")
        bounded_days = max(1, min(int(days), 60))
        if sector_name:
            rows = self._conn.execute(
                "SELECT trade_date, sector_code, sector_name, pct_chg, "
                "leading_stock_codes, limit_up_count "
                "FROM sector_daily "
                "WHERE sector_name = ? AND trade_date IN ("
                "  SELECT DISTINCT trade_date FROM sector_daily "
                "  WHERE trade_date <= ? ORDER BY trade_date DESC LIMIT ?"
                ") ORDER BY trade_date DESC, sector_code ASC",
                (sector_name, end_date, bounded_days),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT trade_date, sector_code, sector_name, pct_chg, "
                "leading_stock_codes, limit_up_count "
                "FROM sector_daily "
                "WHERE trade_date IN ("
                "  SELECT DISTINCT trade_date FROM sector_daily "
                "  WHERE trade_date <= ? ORDER BY trade_date DESC LIMIT ?"
                ") ORDER BY trade_date DESC, sector_code ASC",
                (end_date, bounded_days),
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

    # Task 12：情绪指标数据回填的"是否已有数据"判定
    async def has_emotion_daily(self, trade_date: str) -> bool:
        """判定指定交易日的 emotion_daily 表是否有任何行。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            True 当且仅当 emotion_daily 中存在 trade_date 的任意行。
        """
        _validate_table("emotion_daily")
        row = self._conn.execute(
            "SELECT 1 FROM emotion_daily WHERE trade_date = ? LIMIT 1",
            (trade_date,),
        ).fetchone()
        return row is not None

    # Task 14：板块日线数据回填的"是否已有数据"判定
    async def has_sector_daily(self, trade_date: str) -> bool:
        """判定指定交易日的 sector_daily 表是否有任何行。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            True 当且仅当 sector_daily 中存在 trade_date 的任意行。
        """
        _validate_table("sector_daily")
        row = self._conn.execute(
            "SELECT 1 FROM sector_daily WHERE trade_date = ? LIMIT 1",
            (trade_date,),
        ).fetchone()
        return row is not None

    # Task 15：个股 K 线数据回填的"是否已有数据"判定
    async def has_stock_daily(self, trade_date: str) -> bool:
        """判定指定交易日的 stock_daily 表是否有任何行。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            True 当且仅当 stock_daily 中存在 trade_date 的任意行。
        """
        _validate_table("stock_daily")
        row = self._conn.execute(
            "SELECT 1 FROM stock_daily WHERE trade_date = ? LIMIT 1",
            (trade_date,),
        ).fetchone()
        return row is not None

    # Task 18：非交易日复盘回退——查询缓存中最近一个有数据的交易日
    async def get_latest_trade_date_with_data(self) -> str | None:
        """取缓存中最近一个有数据的交易日（用于 LLM 非交易日自动回退）。

        实现要点（AGENTS.md §4 SQL 安全）：
        - 表名 hard-coded "market_index_daily"（在 _ALLOWED_TABLES 白名单内）
        - 无用户输入 → 不需要 ? 占位符
        - ``SELECT MAX(trade_date)`` 走 trade_date 索引，O(1) 命中

        选择 market_index_daily 而非 limit_stocks_daily 的原因：
        - 大盘指数每天必有 3 行（上证/深证/创业板），是最可靠的"当天有市"信号
        - limit_stocks_daily 在"无涨停日"为空，emotion_daily 在 fetcher 失败时为空
        - sector_daily / stock_daily 行数不稳定（取决于个股数 / 板块数）

        Returns:
            str（YYYYMMDD）或 None（缓存完全为空——warmup 尚未跑过）。
        """
        _validate_table("market_index_daily")
        row = self._conn.execute(
            "SELECT MAX(trade_date) AS latest FROM market_index_daily"
        ).fetchone()
        if row is None or row["latest"] is None:
            return None
        return str(row["latest"])

    # Task 19：行数对齐判定——limit_stocks_daily 该日行数
    async def count_limit_stocks(self, trade_date: str) -> int:
        """返回指定交易日的 limit_stocks_daily 行数（涨停股数）。

        实现要点（AGENTS.md §4 SQL 安全）：
        - 表名 hard-coded "limit_stocks_daily"（在 _ALLOWED_TABLES 白名单内）
        - trade_date 通过 ? 占位符参数化（bandit B608）
        - ``SELECT COUNT(*)`` 走 trade_date 索引，O(log N) 命中

        与 ``has_limit_stocks`` 的区别：
        - has_* 只查"是否有 1 行"（O(1) LIMIT 1），用于 has_* 5 张表判定的快速短路
        - count_* 查实际行数（O(N) 全扫描，但小表够快），用于行数对齐判定

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            该日 limit_stocks_daily 的行数（≥ 0）；无数据返 0。
        """
        _validate_table("limit_stocks_daily")
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM limit_stocks_daily WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()
        return int(row["c"])

    # Task 19：行数对齐判定——stock_daily 该日行数
    async def count_stock_daily(self, trade_date: str) -> int:
        """返回指定交易日的 stock_daily 行数（已抓取的 K 线股数）。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            该日 stock_daily 的行数（≥ 0）；无数据返 0。
        """
        _validate_table("stock_daily")
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM stock_daily WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()
        return int(row["c"])

    # Task 12：取 trade_date 之前最近一个交易日的 emotion_daily
    async def get_emotion_indicators_before(
        self, trade_date: str
    ) -> EmotionIndicators | None:
        """取 ``trade_date`` 之前最近一个交易日的情绪指标行（用于算 volume_change_pct）。

        Args:
            trade_date: 截止日期（YYYYMMDD，不含本日本身）。

        Returns:
            EmotionIndicators 或 None（无更早数据时）。
        """
        _validate_table("emotion_daily")
        row = self._conn.execute(
            "SELECT * FROM emotion_daily WHERE trade_date < ? "
            "ORDER BY trade_date DESC LIMIT 1",
            (trade_date,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_emotion(row, self._conn)

    # ── 内部辅助 ────────────────────────────────────────

    @classmethod
    def _row_to_emotion(
        cls,
        row: sqlite3.Row,
        conn: sqlite3.Connection | None = None,
    ) -> EmotionIndicators:
        """把 sqlite3.Row 转为 EmotionIndicators DTO（含 v023 新增 18 字段）。

        Task E：v023 新增字段允许 None；total_volume 旧代码用 ``or 0.0``
        兜底（兼容 v021 旧行），新字段保持 None 语义（未计算=未写入）。

        v024 修复：top_board_leaders 列已加入 schema；读路径优先取列值（JSON
        解析），无值时再 fallback 到 limit_stocks_daily 聚合。

        Args:
            row: emotion_daily 表行。
            conn: 可选的 SQLite 连接；若提供且列值为 NULL，fallback 到
                limit_stocks_daily 聚合 top_board_leaders。
        """
        emotion = EmotionIndicators(
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
            # Task E v023 新增字段（6 维度情绪观察框架）
            adv_count=row["adv_count"],
            decl_count=row["decl_count"],
            adv_decl_ratio=row["adv_decl_ratio"],
            breadth_level=row["breadth_level"],
            top20_volume_avg_chg=row["top20_volume_avg_chg"],
            top20_volume_up_count=row["top20_volume_up_count"],
            top20_volume_limit_up_count=row["top20_volume_limit_up_count"],
            strength_level=row["strength_level"],
            market_style=row["market_style"],
            board_break_total_count=row["board_break_total_count"],
            board_break_rebound_count=row["board_break_rebound_count"],
            rebound_success_ratio=row["rebound_success_ratio"],
            top5d_avg_chg=row["top5d_avg_chg"],
            resilience_level=row["resilience_level"],
            authenticity_level=row["authenticity_level"],
            height_level=row["height_level"],
            trend_5d=row["trend_5d"],
            trend_20d=row["trend_20d"],
            # v025 情绪周期字段（NULL 自动转 None）
            board_style_score=row["board_style_score"],
            trend_style_score=row["trend_style_score"],
            rebound_style_score=row["rebound_style_score"],
            emotion_score=row["emotion_score"],
            emotion_phase=row["emotion_phase"],
        )
        if conn is not None:
            # v024 修复：emotion_daily 表已有 top_board_leaders 列；
            # 优先读列值（JSON 数组），无值时再 fallback 到 limit_stocks_daily 聚合。
            stored_leaders_raw = (
                row["top_board_leaders"] if "top_board_leaders" in row.keys() else None
            )
            parsed_leaders: list[str] | None = None
            if stored_leaders_raw:
                try:
                    parsed_leaders = json.loads(stored_leaders_raw)
                except (json.JSONDecodeError, TypeError):
                    parsed_leaders = None
            if parsed_leaders is None:
                parsed_leaders = _compute_top_board_leaders(conn, emotion.trade_date)
            object.__setattr__(emotion, "top_board_leaders", parsed_leaders)
        return emotion

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
