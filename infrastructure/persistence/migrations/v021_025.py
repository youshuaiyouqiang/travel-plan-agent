"""迁移版本 21–25。

当前含 v21（股票复盘 8 张数据表）和 v22（stock_fetch_log 单股抓取日志）。
23–25 预留，待后续 Task 补充。
历史迁移（v1–v20）的 SQL 文本与版本号不得修改。
"""

from __future__ import annotations

import logging
from typing import Any

from infrastructure.persistence.migrations.types import Migration

logger = logging.getLogger(__name__)


def _upgrade_21(conn: Any) -> None:
    """股票周期复盘数据表（8 张）。

    设计要点（与 SKILL.md / 计划文档 §7 Task 1 对齐）：
    - 全部 ``CREATE TABLE IF NOT EXISTS``，保证幂等
    - 复合主键防重复抓取（按 trade_date + 维度）
    - 索引按 trade_date DESC 优化近期查询
    - review_reports.user_id 用于所有权隔离
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_index_daily (
            trade_date TEXT NOT NULL,
            index_code TEXT NOT NULL,
            open REAL, close REAL, high REAL, low REAL,
            volume REAL, pct_chg REAL,
            PRIMARY KEY (trade_date, index_code)
        );
        CREATE INDEX IF NOT EXISTS idx_market_index_date
            ON market_index_daily(trade_date DESC);

        CREATE TABLE IF NOT EXISTS stock_daily (
            trade_date TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            open REAL, close REAL, high REAL, low REAL,
            volume REAL, pct_chg REAL, turnover REAL,
            PRIMARY KEY (trade_date, stock_code)
        );
        CREATE INDEX IF NOT EXISTS idx_stock_daily_code_date
            ON stock_daily(stock_code, trade_date DESC);

        CREATE TABLE IF NOT EXISTS limit_stocks_daily (
            trade_date TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            limit_type TEXT NOT NULL,
            consecutive_boards INTEGER NOT NULL DEFAULT 1,
            first_limit_time TEXT,
            last_limit_time TEXT,
            open_count INTEGER NOT NULL DEFAULT 0,
            is_valid_limit_up INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (trade_date, stock_code)
        );
        CREATE INDEX IF NOT EXISTS idx_limit_stocks_date
            ON limit_stocks_daily(trade_date DESC);

        CREATE TABLE IF NOT EXISTS board_ladder_daily (
            trade_date TEXT NOT NULL,
            boards INTEGER NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            stock_codes TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (trade_date, boards)
        );
        CREATE INDEX IF NOT EXISTS idx_board_ladder_date
            ON board_ladder_daily(trade_date DESC);

        CREATE TABLE IF NOT EXISTS sector_daily (
            trade_date TEXT NOT NULL,
            sector_code TEXT NOT NULL,
            sector_name TEXT NOT NULL,
            pct_chg REAL,
            leading_stock_codes TEXT NOT NULL DEFAULT '[]',
            limit_up_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (trade_date, sector_code)
        );
        CREATE INDEX IF NOT EXISTS idx_sector_daily_date
            ON sector_daily(trade_date DESC);

        CREATE TABLE IF NOT EXISTS emotion_daily (
            trade_date TEXT NOT NULL,
            limit_up_count INTEGER NOT NULL DEFAULT 0,
            limit_down_count INTEGER NOT NULL DEFAULT 0,
            valid_limit_up_count INTEGER NOT NULL DEFAULT 0,
            broken_limit_ratio REAL,
            max_consecutive_boards INTEGER NOT NULL DEFAULT 0,
            yesterday_limit_up_today_premium REAL,
            total_volume REAL,
            volume_change_pct REAL,
            phase TEXT,
            phase_confidence TEXT,
            phase_reason TEXT,
            PRIMARY KEY (trade_date)
        );
        CREATE INDEX IF NOT EXISTS idx_emotion_daily_date
            ON emotion_daily(trade_date DESC);

        CREATE TABLE IF NOT EXISTS watchlist_stocks (
            stock_code TEXT PRIMARY KEY,
            stock_name TEXT NOT NULL,
            category INTEGER NOT NULL,
            entry_date TEXT NOT NULL,
            entry_price REAL,
            status TEXT NOT NULL DEFAULT 'active',
            market_index_snapshot REAL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_watchlist_stocks_status
            ON watchlist_stocks(status);

        CREATE TABLE IF NOT EXISTS review_reports (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed',
            llm_metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_review_reports_user_date
            ON review_reports(user_id, trade_date DESC);
        """
    )
    conn.commit()
    logger.info("Migration 21: created 8 stock review tables and indexes")


def _downgrade_21(conn: Any) -> None:
    """回滚迁移 21 — 按依赖倒序删除 8 张表。

    8 张表之间无外键约束，按任意顺序 DROP 即可；此处按 ``review_reports`` →
    ``watchlist_stocks`` → ``emotion_daily`` → ... → ``market_index_daily``
    倒序删除，便于阅读。
    """
    conn.executescript(
        """
        DROP TABLE IF EXISTS review_reports;
        DROP TABLE IF EXISTS watchlist_stocks;
        DROP TABLE IF EXISTS emotion_daily;
        DROP TABLE IF EXISTS sector_daily;
        DROP TABLE IF EXISTS board_ladder_daily;
        DROP TABLE IF EXISTS limit_stocks_daily;
        DROP TABLE IF EXISTS stock_daily;
        DROP TABLE IF EXISTS market_index_daily;
        """
    )
    conn.commit()
    logger.warning("Migration 21 downgrade: dropped 8 stock review tables")


def _downgrade_22(conn: Any) -> None:
    """回滚迁移 22 — 删除 stock_fetch_log 表。"""
    conn.executescript(
        """
        DROP TABLE IF EXISTS stock_fetch_log;
        """
    )
    conn.commit()
    logger.warning("Migration 22 downgrade: dropped stock_fetch_log")


def _upgrade_22(conn: Any) -> None:
    """单股抓取日志表（stock_fetch_log）。

    用途（Task 20）：
    - 记录每只股每次抓取的状态（success / failed）+ last_attempt_at
    - warmup 重启后：若 log 标记 success 且在 TTL 内（默认 24h）→ 跳过
      重新 akshare 调用，避免对前次成功的股再走一遍失败率高的 akshare
    - 仅用于 stock_daily_fetcher；其他 4 个 fetcher 仍是 per-date 模式
      （has_* + 行数对齐已足够）

    设计要点：
    - 复合主键 (trade_date, stock_code, table_name) 防重复
    - last_attempt_at 索引按 trade_date + 时间优化 TTL 查询
    - status 用 CHECK 约束限定为 success / failed
    - error_message 仅 failed 状态有值（success 时清空）
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS stock_fetch_log (
            trade_date TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            table_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('success', 'failed')),
            last_attempt_at TEXT NOT NULL,
            error_message TEXT,
            PRIMARY KEY (trade_date, stock_code, table_name)
        );
        CREATE INDEX IF NOT EXISTS idx_stock_fetch_log_attempt
            ON stock_fetch_log(trade_date, last_attempt_at DESC);
        """
    )
    conn.commit()
    logger.info("Migration 22: created stock_fetch_log table and index")


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=21,
        description="Stock review: 8 tables (market_index/stock/limit_stocks/board_ladder/sector/emotion/watchlist/review_reports)",
        upgrade=_upgrade_21,
        downgrade=_downgrade_21,
    ),
    Migration(
        version=22,
        description="stock_fetch_log table: per-(date, code, table) fetch status with TTL index",
        upgrade=_upgrade_22,
        downgrade=_downgrade_22,
    ),
)
