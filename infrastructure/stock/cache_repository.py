"""缓存仓储——所有 SQL 参数化，表名白名单（AGENTS.md §4 安全与数据）。

Task 3 最小实现：仅实现 limit_stocks_daily 表的 upsert/select。
其余 7 张表的方法在后续 Task 补全——本模块先建好 ALLOWED_TABLES 白名单
和 connection 注入基座，确保 SQL 注入防护覆盖全模块。

设计要点：
- 表名全部走 ALLOWED_TABLES 白名单；任何动态表名不在白名单内必须抛 ValueError
- 所有用户输入（trade_date / stock_code / stock_name 等）必须用 ? 占位符参数化
- upsert 用 INSERT OR REPLACE，复合主键 (trade_date, stock_code) 防重复
- 复用 infrastructure.persistence.connection 的 get_connection() 取得当前线程连接
"""

from __future__ import annotations

import logging
import sqlite3

from domain.stock.models import LimitStock

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
        """批量 upsert 涨停股池。

        Args:
            trade_date: 交易日期（YYYYMMDD）。
            stocks: LimitStock DTO 列表。

        Raises:
            ValueError: 当 limit_stocks_daily 不在白名单时（防御性校验）。
        """
        _validate_table("limit_stocks_daily")
        # 表名直接写在 SQL 字符串字面量中（白名单内），全部 ? 占位符
        sql = (
            "INSERT OR REPLACE INTO limit_stocks_daily "
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
