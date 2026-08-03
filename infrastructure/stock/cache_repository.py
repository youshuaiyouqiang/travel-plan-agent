"""缓存仓储——所有 SQL 参数化，表名白名单（AGENTS.md §4 安全与数据）。

Task 3 最小实现：仅实现 limit_stocks_daily 表的 upsert/select。
Task 4 扩展：实现 review_reports 表的 save_review_report。
Task 5 扩展：实现 watchlist_stocks 表的 add/remove + review_reports 查询。
Task 20 扩展：实现 stock_fetch_log 表的 record_fetch / is_recently_succeeded。

设计要点：
- 表名全部走 ALLOWED_TABLES 白名单；任何动态表名不在白名单内必须抛 ValueError
- 所有用户输入（trade_date / stock_code / stock_name 等）必须用 ? 占位符参数化
- upsert 用 INSERT OR REPLACE，复合主键 (trade_date, stock_code) 防重复
- 复用 infrastructure.persistence.connection 的 get_connection() 取得当前线程连接
- 公开方法对应 ``application.stock.cache_repository_port.CacheRepositoryPort``
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from typing import Any

from domain.stock.models import (
    BoardLadder,
    EmotionIndicators,
    LimitStock,
    MarketIndexRow,
    ReviewReport,
    SectorDaily,
    StockDaily,
    WatchlistStock,
)

logger = logging.getLogger(__name__)


# ── 表名白名单（AGENTS.md §4：动态表名只能来自硬编码白名单）──
ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "market_index_daily",
        "stock_daily",
        "limit_stocks_daily",
        "board_ladder_daily",
        "sector_daily",
        "emotion_daily",
        "watchlist_stocks",
        "review_reports",
        "stock_fetch_log",  # Task 20：单股抓取日志
    }
)


def _validate_table(table: str) -> None:
    """校验表名在白名单内；不在则抛 ValueError。

    这是 SQL 注入防护的核心：表名虽然不能参数化（SQLite 不支持），但可以
    限制只能从白名单内选取，从源头杜绝拼接用户输入。
    """
    if table not in ALLOWED_TABLES:
        raise ValueError(
            f"Refusing to operate on non-whitelisted table: {table!r}. "
            f"Allowed: {sorted(ALLOWED_TABLES)}"
        )


def _compute_top_board_leaders(
    conn: sqlite3.Connection, trade_date: str
) -> list[str]:
    """取指定交易日 ``max_consecutive_boards`` 对应的全部股票代码。

    修复：``emotion_daily.max_consecutive_boards`` 只存了数字，看不出是哪只股票。
    该函数多查一次 ``limit_stocks_daily`` 给出"龙头列表"，供前端"最高板龙头"表格。

    Args:
        conn: SQLite 连接（必须能读 limit_stocks_daily 白名单表）。
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


def _row_to_emotion_indicators(
    row: sqlite3.Row, conn: sqlite3.Connection | None = None
) -> EmotionIndicators:
    """把 sqlite3.Row 转为 EmotionIndicators DTO（含 v023 新增 18 字段）。

    Task E：v023 新增字段允许 None；用 ``row[key]`` 取值时若列不存在
    会抛 KeyError，但迁移 v023 已确保所有列存在。
    ``or 0`` 仅对 NOT NULL DEFAULT 0 的旧字段使用，新字段保持 None 语义。

    Args:
        row: emotion_daily 表行。
        conn: 可选的 SQLite 连接；若提供，则补充 ``top_board_leaders``
            （从 ``limit_stocks_daily`` 多查一次聚合）。
    """
    base = EmotionIndicators(
        trade_date=row["trade_date"],
        limit_up_count=row["limit_up_count"],
        limit_down_count=row["limit_down_count"],
        valid_limit_up_count=row["valid_limit_up_count"],
        broken_limit_ratio=row["broken_limit_ratio"] or 0.0,
        max_consecutive_boards=row["max_consecutive_boards"],
        yesterday_limit_up_today_premium=row["yesterday_limit_up_today_premium"],
        total_volume=row["total_volume"],
        volume_change_pct=row["volume_change_pct"],
        phase=row["phase"],
        phase_confidence=row["phase_confidence"],
        phase_reason=row["phase_reason"],
        # Task E v023 新增字段
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
    )
    if conn is not None:
        # v024 修复：emotion_daily 表已有 top_board_leaders 列（JSON 字符串数组）；
        # 优先读列值；若列为 NULL 或解析失败，fallback 到聚合查询
        # （兼容历史无 leader 数据的行 + 旧部署）。
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
            parsed_leaders = _compute_top_board_leaders(conn, base.trade_date)
        object.__setattr__(base, "top_board_leaders", parsed_leaders)
    return base


class CacheRepository:
    """缓存仓储——SQLite 写路径的薄包装。

    实例无状态，可单例复用。通过外部注入的 ``conn`` 访问数据库，
    不主动调用 ``get_connection()``，便于测试用临时数据库。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """初始化仓储。

        Args:
            conn: 已配置的 sqlite3.Connection。
        """
        self._conn = conn

    # ── limit_stocks_daily ─────────────────────────────────

    def upsert_limit_stocks(
        self, trade_date: str, stocks: list[LimitStock]
    ) -> None:
        """批量写入涨停股池（先删后插，确保完全覆盖）。

        语义：每次抓取结果代表该日完整股池快照。
        盘中拓取可能包含临时涨停但尾盘未封住的股票，收盘后重新抓取
        必须覆盖而非追加，否则旧数据残留导致涨停数虚高。

        Args:
            trade_date: 交易日期（YYYYMMDD）。
            stocks: LimitStock DTO 列表。

        Raises:
            ValueError: 当 limit_stocks_daily 不在白名单时（防御性校验）。
        """
        _validate_table("limit_stocks_daily")
        # 空列表保护：fetch 返回空结果时不覆盖已有数据。
        # 场景：周末/节假日 akshare 可能返回空，不能因此清空有效数据。
        if not stocks:
            return
        # 先删除该日同类型旧数据，确保新抓取结果完全覆盖。
        # 按 limit_type 分别删除：limit_fetcher 写 "up"，
        # limit_broken_fetcher 写 "broken"，互不影响。
        types_in_batch = {s.limit_type for s in stocks}
        for lt in types_in_batch:
            self._conn.execute(
                "DELETE FROM limit_stocks_daily "
                "WHERE trade_date = ? AND limit_type = ?",
                (trade_date, lt),
            )
        # 表名直接写在 SQL 字符串字面量中（白名单内），全部 ? 占位符
        sql = (
            "INSERT INTO limit_stocks_daily "
            "(trade_date, stock_code, stock_name, limit_type, "
            "consecutive_boards, first_limit_time, last_limit_time, "
            "open_count, is_valid_limit_up) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        for s in stocks:
            self._conn.execute(
                sql,
                (
                    trade_date,
                    s.stock_code,
                    s.stock_name,
                    s.limit_type,
                    s.consecutive_boards,
                    s.first_limit_time,
                    s.last_limit_time,
                    s.open_count,
                    int(s.is_valid_limit_up),
                ),
            )
        self._conn.commit()

    def select_limit_stocks(self, trade_date: str) -> list[LimitStock]:
        """查询某日的涨停股池。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            LimitStock DTO 列表；无数据时为空列表。
        """
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
                trade_date=row["trade_date"],
                stock_code=row["stock_code"],
                stock_name=row["stock_name"],
                limit_type=row["limit_type"],
                consecutive_boards=row["consecutive_boards"],
                first_limit_time=row["first_limit_time"],
                last_limit_time=row["last_limit_time"],
                open_count=row["open_count"],
                is_valid_limit_up=bool(row["is_valid_limit_up"]),
            )
            for row in rows
        ]

    # ── market_index_daily ─────────────────────────────────
    # Task 13：大盘指数 fetcher 写路径

    def upsert_market_index(
        self, trade_date: str, indices: list[MarketIndexRow]
    ) -> None:
        """批量 upsert 大盘指数（上证/深证/创业板）单日行。

        Args:
            trade_date: 交易日期（YYYYMMDD）。
            indices: MarketIndexRow DTO 列表。

        Raises:
            ValueError: 当 market_index_daily 不在白名单时（防御性校验）。
        """
        _validate_table("market_index_daily")
        # 表名直接写在 SQL 字符串字面量中（白名单内），全部 ? 占位符
        sql = (
            "INSERT OR REPLACE INTO market_index_daily "
            "(trade_date, index_code, open, close, high, low, volume, pct_chg) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        for r in indices:
            self._conn.execute(
                sql,
                (
                    trade_date,
                    r.index_code,
                    r.open,
                    r.close,
                    r.high,
                    r.low,
                    r.volume,
                    r.pct_chg,
                ),
            )
        self._conn.commit()

    def select_market_index(self, trade_date: str) -> list[MarketIndexRow]:
        """查询某日的大盘指数行（上证/深证/创业板）。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            MarketIndexRow DTO 列表；无数据时为空列表。
        """
        _validate_table("market_index_daily")
        rows = self._conn.execute(
            "SELECT trade_date, index_code, open, close, high, low, "
            "volume, pct_chg FROM market_index_daily WHERE trade_date = ?",
            (trade_date,),
        ).fetchall()
        return [
            MarketIndexRow(
                trade_date=row["trade_date"],
                index_code=row["index_code"],
                open=row["open"],
                close=row["close"],
                high=row["high"],
                low=row["low"],
                volume=row["volume"],
                pct_chg=row["pct_chg"],
            )
            for row in rows
        ]

    # ── emotion_daily ──────────────────────────────────────
    # Task 12：情绪指标 fetcher 写路径

    def upsert_emotion_daily(
        self, trade_date: str, rows: list[EmotionIndicators]
    ) -> None:
        """批量 upsert 情绪指标单日行。

        Task E 扩展：写入 v023 新增的 18 个 6 维度字段。
        全部新字段允许 None（fetcher 未计算时保持 None）。

        Args:
            trade_date: 交易日期（YYYYMMDD）。
            rows: EmotionIndicators DTO 列表（通常 1 个元素）。

        Raises:
            ValueError: 当 emotion_daily 不在白名单时（防御性校验）。
        """
        _validate_table("emotion_daily")
        # 表名直接写在 SQL 字符串字面量中（白名单内），全部 ? 占位符
        # Task E v023：新增 18 个 6 维度字段（共 30 列 = 12 旧 + 18 新）
        # 占位符按 10 个一组分行书写，便于人工核对数量
        sql = (
            "INSERT OR REPLACE INTO emotion_daily ("
            "trade_date, limit_up_count, limit_down_count, "
            "valid_limit_up_count, broken_limit_ratio, max_consecutive_boards, "
            "yesterday_limit_up_today_premium, total_volume, volume_change_pct, "
            "phase, phase_confidence, phase_reason, "
            # Task E v023 新增字段（6 维度情绪观察框架）
            "adv_count, decl_count, adv_decl_ratio, breadth_level, "
            "top20_volume_avg_chg, top20_volume_up_count, "
            "top20_volume_limit_up_count, strength_level, market_style, "
            "board_break_total_count, board_break_rebound_count, "
            "rebound_success_ratio, top5d_avg_chg, resilience_level, "
            "authenticity_level, height_level, "
            "trend_5d, trend_20d, "
            # v024 修复：最高板龙头 stock_code 列表（JSON 数组）
            "top_board_leaders"
            ") VALUES ("
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "  # 10
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "  # 10
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "  # 10
            "?"                                # top_board_leaders
            ")"
        )
        for r in rows:
            self._conn.execute(
                sql,
                (
                    trade_date,
                    r.limit_up_count,
                    r.limit_down_count,
                    r.valid_limit_up_count,
                    r.broken_limit_ratio,
                    r.max_consecutive_boards,
                    r.yesterday_limit_up_today_premium,
                    r.total_volume,
                    r.volume_change_pct,
                    r.phase,
                    r.phase_confidence,
                    r.phase_reason,
                    # Task E v023 新增字段
                    r.adv_count,
                    r.decl_count,
                    r.adv_decl_ratio,
                    r.breadth_level,
                    r.top20_volume_avg_chg,
                    r.top20_volume_up_count,
                    r.top20_volume_limit_up_count,
                    r.strength_level,
                    r.market_style,
                    r.board_break_total_count,
                    r.board_break_rebound_count,
                    r.rebound_success_ratio,
                    r.top5d_avg_chg,
                    r.resilience_level,
                    r.authenticity_level,
                    r.height_level,
                    r.trend_5d,
                    r.trend_20d,
                    # v024 修复：top_board_leaders 字段持久化（JSON 数组）
                    # 由 _row_to_emotion_indicators 在读取路径补全
                    (
                        json.dumps(r.top_board_leaders, ensure_ascii=False)
                        if r.top_board_leaders is not None
                        else None
                    ),
                ),
            )
        self._conn.commit()

    def select_emotion_daily(
        self, trade_date: str
    ) -> list[EmotionIndicators]:
        """查询某日的情绪指标行。

        Task E 扩展：读取 v023 新增的 18 个 6 维度字段。
        用 ``SELECT *`` 简化列管理（v023 新增 18 列后显式列名冗长）。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            EmotionIndicators DTO 列表；无数据时为空列表。
        """
        _validate_table("emotion_daily")
        rows = self._conn.execute(
            "SELECT * FROM emotion_daily WHERE trade_date = ?",
            (trade_date,),
        ).fetchall()
        return [_row_to_emotion_indicators(row, self._conn) for row in rows]  # noqa: PERF401

    # ── sector_daily ──────────────────────────────────────
    # Task 14：板块日线 fetcher 写路径

    def upsert_sector_daily(
        self, trade_date: str, rows: list[SectorDaily]
    ) -> None:
        """批量 upsert 板块日线（一天多行，每板块一行）。

        Args:
            trade_date: 交易日期（YYYYMMDD）。
            rows: SectorDaily DTO 列表（约 100+ 个行业板块）。

        Raises:
            ValueError: 当 sector_daily 不在白名单时（防御性校验）。
        """
        _validate_table("sector_daily")
        # 表名直接写在 SQL 字符串字面量中（白名单内），全部 ? 占位符
        sql = (
            "INSERT OR REPLACE INTO sector_daily ("
            "trade_date, sector_code, sector_name, pct_chg, "
            "leading_stock_codes, limit_up_count"
            ") VALUES (?, ?, ?, ?, ?, ?)"
        )
        for r in rows:
            self._conn.execute(
                sql,
                (
                    trade_date,
                    r.sector_code,
                    r.sector_name,
                    r.pct_chg,
                    json.dumps(r.leading_stock_codes, ensure_ascii=False),
                    r.limit_up_count,
                ),
            )
        self._conn.commit()

    def select_sector_daily(self, trade_date: str) -> list[SectorDaily]:
        """查询某日的所有板块日线行。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            SectorDaily DTO 列表；无数据时为空列表。
        """
        _validate_table("sector_daily")
        rows = self._conn.execute(
            "SELECT trade_date, sector_code, sector_name, pct_chg, "
            "leading_stock_codes, limit_up_count "
            "FROM sector_daily WHERE trade_date = ? "
            "ORDER BY pct_chg DESC",
            (trade_date,),
        ).fetchall()
        return [
            SectorDaily(
                trade_date=row["trade_date"],
                sector_code=row["sector_code"],
                sector_name=row["sector_name"],
                pct_chg=row["pct_chg"],
                leading_stock_codes=json.loads(row["leading_stock_codes"] or "[]"),
                limit_up_count=row["limit_up_count"],
            )
            for row in rows
        ]

    # ── board_ladder_daily ────────────────────────────────
    # Task A2：连板高度分层 fetcher 写路径
    # 由 limit_stocks_daily 聚合产生，无 akshare 调用
    def upsert_board_ladder(
        self, *, trade_date: str, rows: list[BoardLadder]
    ) -> None:
        """批量 upsert 连板高度分层（一天多行，每高度一行）。

        Args:
            trade_date: 交易日期（YYYYMMDD）。
            rows: BoardLadder DTO 列表（每连板高度一条，约 1-10 条）。

        Raises:
            ValueError: 当 board_ladder_daily 不在白名单时（防御性校验）。
        """
        _validate_table("board_ladder_daily")
        # 表名直接写在 SQL 字符串字面量中（白名单内），全部 ? 占位符
        sql = (
            "INSERT OR REPLACE INTO board_ladder_daily ("
            "trade_date, boards, count, stock_codes"
            ") VALUES (?, ?, ?, ?)"
        )
        for r in rows:
            self._conn.execute(
                sql,
                (
                    trade_date,
                    r.boards,
                    r.count,
                    json.dumps(r.stock_codes, ensure_ascii=False),
                ),
            )
        self._conn.commit()

    def select_board_ladder(self, trade_date: str) -> list[BoardLadder]:
        """查询某日的连板高度分层。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            BoardLadder DTO 列表，按 boards 升序排列；无数据时为空列表。
        """
        _validate_table("board_ladder_daily")
        rows = self._conn.execute(
            "SELECT trade_date, boards, count, stock_codes "
            "FROM board_ladder_daily WHERE trade_date = ? "
            "ORDER BY boards ASC",
            (trade_date,),
        ).fetchall()
        return [
            BoardLadder(
                trade_date=row["trade_date"],
                boards=row["boards"],
                count=row["count"],
                stock_codes=json.loads(row["stock_codes"] or "[]"),
            )
            for row in rows
        ]

    # ── stock_daily ───────────────────────────────────────
    # Task 15：个股 K 线 fetcher 写路径

    def upsert_stock_daily(
        self, trade_date: str, rows: list[StockDaily]
    ) -> None:
        """批量 upsert 个股 K 线（一天多行，每只股一行）。

        Args:
            trade_date: 交易日期（YYYYMMDD）。rows 中 trade_date 必须与之对齐。
            rows: StockDaily DTO 列表（每只股一行）。

        Raises:
            ValueError: 当 stock_daily 不在白名单时（防御性校验）。
        """
        _validate_table("stock_daily")
        sql = (
            "INSERT OR REPLACE INTO stock_daily ("
            "trade_date, stock_code, open, close, high, low, "
            "volume, pct_chg, turnover"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        for r in rows:
            self._conn.execute(
                sql,
                (
                    trade_date,
                    r.stock_code,
                    r.open,
                    r.close,
                    r.high,
                    r.low,
                    r.volume,
                    r.pct_chg,
                    r.turnover,
                ),
            )
        self._conn.commit()

    def select_stock_daily(self, trade_date: str) -> list[StockDaily]:
        """查询某日所有个股 K 线行。

        Args:
            trade_date: 交易日期（YYYYMMDD）。

        Returns:
            StockDaily DTO 列表；无数据时为空列表。
        """
        _validate_table("stock_daily")
        rows = self._conn.execute(
            "SELECT trade_date, stock_code, open, close, high, low, "
            "volume, pct_chg, turnover "
            "FROM stock_daily WHERE trade_date = ?",
            (trade_date,),
        ).fetchall()
        return [
            StockDaily(
                trade_date=row["trade_date"],
                stock_code=row["stock_code"],
                open=row["open"],
                close=row["close"],
                high=row["high"],
                low=row["low"],
                volume=row["volume"],
                pct_chg=row["pct_chg"],
                turnover=row["turnover"],
            )
            for row in rows
        ]

    # ── review_reports ─────────────────────────────────────

    async def save_review_report(
        self,
        *,
        user_id: str,
        trade_date: str,
        content: str,
        status: str,
        llm_metadata: dict[str, Any] | None = None,
    ) -> str:
        """保存复盘文到 review_reports 表，返回生成的 report_id。

        Args:
            user_id: 用户 ID（所有权隔离用，AGENTS.md §4）。
            trade_date: 交易日期。
            content: 复盘文 Markdown 全文。
            status: completed / degraded / no_data。
            llm_metadata: 元数据 dict（会序列化为 JSON 字符串）。

        Returns:
            新生成的 report_id（32 字符 hex）。

        Raises:
            ValueError: 当 review_reports 不在白名单时。
        """
        _validate_table("review_reports")
        report_id = uuid.uuid4().hex
        self._conn.execute(
            "INSERT INTO review_reports "
            "(id, user_id, trade_date, content, status, llm_metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                report_id,
                user_id,
                trade_date,
                content,
                status,
                json.dumps(llm_metadata or {}, ensure_ascii=False),
                self._now_iso(),
            ),
        )
        self._conn.commit()
        return report_id

    async def select_review_report(
        self, *, report_id: str, user_id: str
    ) -> ReviewReport | None:
        """按 (report_id, user_id) 查询复盘文。

        Args:
            report_id: 复盘文 ID。
            user_id: 用户 ID（所有权过滤）。

        Returns:
            ReviewReport DTO；不存在或所有权不匹配返回 None。
        """
        _validate_table("review_reports")
        row = self._conn.execute(
            "SELECT id, user_id, trade_date, content, status, llm_metadata, created_at "
            "FROM review_reports WHERE id = ? AND user_id = ?",
            (report_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_review_report(row)

    async def select_review_reports(
        self, *, user_id: str, limit: int
    ) -> list[ReviewReport]:
        """列出某 user 的复盘文（按 trade_date DESC, created_at DESC）。

        Args:
            user_id: 用户 ID（所有权过滤）。
            limit: 返回上限。

        Returns:
            ReviewReport DTO 列表；无数据时为空列表。
        """
        _validate_table("review_reports")
        bounded_limit = max(1, min(int(limit), 100))
        rows = self._conn.execute(
            "SELECT id, user_id, trade_date, content, status, llm_metadata, created_at "
            "FROM review_reports WHERE user_id = ? "
            "ORDER BY trade_date DESC, created_at DESC LIMIT ?",
            (user_id, bounded_limit),
        ).fetchall()
        return [self._row_to_review_report(r) for r in rows]

    @staticmethod
    def _row_to_review_report(row: Any) -> ReviewReport:
        """sqlite3.Row → ReviewReport DTO。"""
        llm_metadata_raw = row["llm_metadata"]
        if llm_metadata_raw is None:
            llm_metadata_str = "{}"
        else:
            llm_metadata_str = str(llm_metadata_raw)
        return ReviewReport(
            id=row["id"],
            user_id=row["user_id"],
            trade_date=row["trade_date"],
            content=row["content"],
            status=row["status"],
            llm_metadata=llm_metadata_str,
            created_at=row["created_at"],
        )

    # ── watchlist_stocks ────────────────────────────────────

    async def add_watchlist_stock(self, *, stock: Any) -> None:
        """upsert 一只股票到 watchlist_stocks 表。

        Args:
            stock: WatchlistStock DTO（任意带同名属性的对象，运行时 duck-type）。

        Raises:
            ValueError: 当 watchlist_stocks 不在白名单时。
        """
        _validate_table("watchlist_stocks")
        now = self._now_iso()
        self._conn.execute(
            "INSERT INTO watchlist_stocks "
            "(stock_code, stock_name, category, entry_date, entry_price, "
            "status, market_index_snapshot, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(stock_code) DO UPDATE SET "
            "stock_name = excluded.stock_name, "
            "category = excluded.category, "
            "entry_date = excluded.entry_date, "
            "entry_price = excluded.entry_price, "
            "status = excluded.status, "
            "market_index_snapshot = excluded.market_index_snapshot, "
            "notes = excluded.notes, "
            "updated_at = excluded.updated_at",
            (
                stock.stock_code,
                stock.stock_name,
                stock.category,
                stock.entry_date,
                stock.entry_price,
                stock.status,
                stock.market_index_snapshot,
                stock.notes,
                now,
                now,
            ),
        )
        self._conn.commit()

    async def remove_watchlist_stock(self, *, stock_code: str) -> int:
        """从 watchlist_stocks 表删除指定 stock_code。

        Args:
            stock_code: 股票代码。

        Returns:
            受影响行数（0/1）。
        """
        _validate_table("watchlist_stocks")
        cur = self._conn.execute(
            "DELETE FROM watchlist_stocks WHERE stock_code = ?",
            (stock_code,),
        )
        self._conn.commit()
        return cur.rowcount

    def select_watchlist(
        self, *, status: str = "active"
    ) -> list[WatchlistStock]:
        """查询观察池（同步，便于同步 fetcher 调用）。

        Args:
            status: 过滤状态，默认 active（排除 removed）。

        Returns:
            WatchlistStock DTO 列表。
        """
        _validate_table("watchlist_stocks")
        rows = self._conn.execute(
            "SELECT stock_code, stock_name, category, entry_date, entry_price, "
            "status, market_index_snapshot, notes "
            "FROM watchlist_stocks WHERE status = ? "
            "ORDER BY category ASC, entry_date DESC",
            (status,),
        ).fetchall()
        return [
            WatchlistStock(
                stock_code=r["stock_code"],
                stock_name=r["stock_name"],
                category=r["category"],
                entry_date=r["entry_date"],
                entry_price=r["entry_price"],
                status=r["status"],
                market_index_snapshot=r["market_index_snapshot"],
                notes=r["notes"],
            )
            for r in rows
        ]

    @staticmethod
    def _now_iso() -> str:
        """当前 UTC ISO 时间戳。"""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    # ── stock_fetch_log（Task 20：单股抓取日志） ─────────

    def record_fetch(
        self,
        *,
        trade_date: str,
        stock_code: str,
        table_name: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """记录一次抓取结果（成功或失败），upsert 语义。

        Args:
            trade_date: 交易日期（YYYYMMDD）。
            stock_code: 股票代码。
            table_name: 数据表名（当前仅 'stock_daily'）。
            status: 'success' 或 'failed'（与表 CHECK 约束对齐）。
            error_message: 错误详情（status='success' 时清空为 None）。

        Raises:
            ValueError: 当 stock_fetch_log 不在白名单时。
        """
        _validate_table("stock_fetch_log")
        # success 时强制清空 error_message，避免旧错误误导后续判定
        cleaned_error: str | None = None if status == "success" else error_message
        self._conn.execute(
            "INSERT INTO stock_fetch_log "
            "(trade_date, stock_code, table_name, status, last_attempt_at, error_message) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(trade_date, stock_code, table_name) DO UPDATE SET "
            "status = excluded.status, "
            "last_attempt_at = excluded.last_attempt_at, "
            "error_message = excluded.error_message",
            (
                trade_date,
                stock_code,
                table_name,
                status,
                self._now_iso(),
                cleaned_error,
            ),
        )
        self._conn.commit()

    def is_recently_succeeded(
        self,
        *,
        trade_date: str,
        stock_code: str,
        table_name: str,
        within_seconds: int,
    ) -> bool:
        """查询 (date, code, table) 是否在 TTL 内 status='success'。

        判定规则：
        - 无 log 行 → False（必须抓取）
        - status='failed' → False（即使在 TTL 内也允许重试）
        - status='success' 且 last_attempt_at 在 TTL 内 → True（跳过）
        - status='success' 但 last_attempt_at 超过 TTL → False（重抓）

        Args:
            trade_date: 交易日期（YYYYMMDD）。
            stock_code: 股票代码。
            table_name: 数据表名。
            within_seconds: TTL 窗口（秒）；负数视为 0（永不过期）。

        Returns:
            True = 应跳过抓取；False = 需重新抓取。
        """
        _validate_table("stock_fetch_log")
        from datetime import datetime, timedelta, timezone

        # TTL 边界：now - within_seconds 之后才算"在 TTL 内"
        ttl_boundary = (
            datetime.now(timezone.utc) - timedelta(seconds=max(0, within_seconds))
        ).isoformat()
        row = self._conn.execute(
            "SELECT status, last_attempt_at FROM stock_fetch_log "
            "WHERE trade_date = ? AND stock_code = ? AND table_name = ?",
            (trade_date, stock_code, table_name),
        ).fetchone()
        if row is None:
            return False
        if row["status"] != "success":
            return False
        # last_attempt_at 是 ISO8601 字符串，比较字典序即可（UTC ISO 可字典序比时间）
        return row["last_attempt_at"] >= ttl_boundary
