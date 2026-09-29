from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from api.config import settings


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS etf_pool (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ts_code TEXT NOT NULL UNIQUE,
    full_code TEXT NOT NULL UNIQUE,
    group_name TEXT NOT NULL,
    market TEXT NOT NULL,
    is_visible INTEGER NOT NULL DEFAULT 1,
    entry_type TEXT NOT NULL DEFAULT 'default'
);

CREATE TABLE IF NOT EXISTS trade_calendar (
    trade_date TEXT PRIMARY KEY,
    is_open INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS etf_daily_bar (
    trade_date TEXT NOT NULL,
    code TEXT NOT NULL,
    ts_code TEXT NOT NULL,
    full_code TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    pre_close REAL,
    change REAL,
    pct_chg REAL,
    adj_factor REAL,
    vol REAL,
    amount REAL,
    PRIMARY KEY (trade_date, code)
);

CREATE TABLE IF NOT EXISTS etf_adjustment_state (
    code TEXT PRIMARY KEY,
    qfq_base_factor REAL NOT NULL,
    latest_trade_date TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- (ETF 成分股与股票研究相关表已移除)

CREATE TABLE IF NOT EXISTS etf_realtime_snapshot (
    code TEXT PRIMARY KEY,
    trade_date TEXT NOT NULL,
    last_price REAL,
    open REAL,
    high REAL,
    low REAL,
    pre_close REAL,
    pct_chg REAL,
    vol REAL,
    amount REAL,
    quote_time TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'tencent',
    is_stale INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS etl_job_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    run_time TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    message TEXT
);

-- (股票研究相关索引已移除)

"""

SQLITE_BUSY_TIMEOUT_MS = 30_000
_INIT_DB_LOCK = Lock()
_INITIALIZED_DATABASE_PATH: str | None = None


def _ensure_etf_pool_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(etf_pool)").fetchall()
    }
    if "is_visible" not in columns:
        connection.execute(
            "ALTER TABLE etf_pool ADD COLUMN is_visible INTEGER NOT NULL DEFAULT 1"
        )
    if "entry_type" not in columns:
        connection.execute(
            "ALTER TABLE etf_pool ADD COLUMN entry_type TEXT NOT NULL DEFAULT 'default'"
        )


def _ensure_etf_daily_bar_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(etf_daily_bar)").fetchall()
    }
    if "adj_factor" not in columns:
        connection.execute(
            "ALTER TABLE etf_daily_bar ADD COLUMN adj_factor REAL"
        )


def _ensure_realtime_snapshot_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(etf_realtime_snapshot)").fetchall()
    }
    if columns and "source" not in columns:
        connection.execute(
            "ALTER TABLE etf_realtime_snapshot ADD COLUMN source TEXT NOT NULL DEFAULT 'tencent'"
        )
    if columns and "is_stale" not in columns:
        connection.execute(
            "ALTER TABLE etf_realtime_snapshot ADD COLUMN is_stale INTEGER NOT NULL DEFAULT 0"
        )


def ensure_parent_directory() -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.exports_dir.mkdir(parents=True, exist_ok=True)


def _configure_connection(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("PRAGMA foreign_keys = ON")


@contextmanager
def get_connection():
    ensure_parent_directory()
    connection = sqlite3.connect(settings.database_path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    _configure_connection(connection)
    try:
        yield connection
        if connection.in_transaction:
            connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def init_db(force: bool = False) -> None:
    global _INITIALIZED_DATABASE_PATH

    database_path = str(settings.database_path.resolve())
    if not force and _INITIALIZED_DATABASE_PATH == database_path:
        return

    with _INIT_DB_LOCK:
        if not force and _INITIALIZED_DATABASE_PATH == database_path:
            return

        with get_connection() as connection:
            connection.executescript(SCHEMA_SQL)
            _ensure_etf_pool_columns(connection)
            _ensure_etf_daily_bar_columns(connection)
            _ensure_realtime_snapshot_columns(connection)

        _INITIALIZED_DATABASE_PATH = database_path
