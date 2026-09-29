from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import logging
from typing import Any

from api.config import settings
from api.db import get_connection, init_db
from api.realtime_types import RealtimeQuote
from api.realtime_source_mootdx import fetch_realtime_quotes as fetch_mootdx_realtime_quotes
from api.realtime_source_tencent import fetch_realtime_quotes as fetch_tencent_realtime_quotes


logger = logging.getLogger(__name__)
SUPPORTED_REALTIME_SOURCES = {"mootdx", "tencent"}


@dataclass
class RealtimeSnapshot:
    code: str
    trade_date: str
    last_price: float
    open: float | None
    high: float | None
    low: float | None
    pre_close: float | None
    pct_chg: float | None
    vol: float | None
    amount: float | None
    quote_time: str
    source: str
    is_stale: bool
    created_at: str
    updated_at: str


@dataclass
class RealtimeStatus:
    enabled: bool
    active: bool
    source: str
    as_of: str | None
    stale: bool
    display_mode: str


def _today_ui(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return current.strftime("%Y-%m-%d")


def _today_api(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return current.strftime("%Y%m%d")


def is_market_session_time(now: datetime | None = None) -> bool:
    current = now or datetime.now()
    minutes = current.hour * 60 + current.minute
    # 盘中展示口径按 09:30-15:00 全时段处理，午休阶段继续展示上午最后一笔快照。
    return (9 * 60 + 30) <= minutes < (15 * 60)


def _is_open_trade_day(trade_date_ui: str) -> bool:
    trade_date_api = trade_date_ui.replace("-", "")
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT is_open
            FROM trade_calendar
            WHERE trade_date = ?
            """,
            (trade_date_api,),
        ).fetchone()
    return row is not None and int(row["is_open"]) == 1


def should_use_intraday_realtime(selected_trade_date: str, explicit_trade_date: bool, now: datetime | None = None) -> bool:
    if explicit_trade_date:
        return False
    if not settings.realtime_enabled or settings.realtime_source not in SUPPORTED_REALTIME_SOURCES:
        return False
    current = now or datetime.now()
    today_trade_date = _today_ui(current)
    if selected_trade_date != today_trade_date:
        return False
    if not _is_open_trade_day(today_trade_date):
        return False
    return is_market_session_time(current)


def _row_to_snapshot(row: Any) -> RealtimeSnapshot:
    return RealtimeSnapshot(
        code=row["code"],
        trade_date=row["trade_date"],
        last_price=float(row["last_price"]),
        open=float(row["open"]) if row["open"] is not None else None,
        high=float(row["high"]) if row["high"] is not None else None,
        low=float(row["low"]) if row["low"] is not None else None,
        pre_close=float(row["pre_close"]) if row["pre_close"] is not None else None,
        pct_chg=float(row["pct_chg"]) if row["pct_chg"] is not None else None,
        vol=float(row["vol"]) if row["vol"] is not None else None,
        amount=float(row["amount"]) if row["amount"] is not None else None,
        quote_time=row["quote_time"],
        source=row["source"],
        is_stale=bool(row["is_stale"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _safe_parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _snapshot_age_seconds(snapshot: RealtimeSnapshot, now: datetime) -> float:
    quote_time = _safe_parse_datetime(snapshot.quote_time) or _safe_parse_datetime(snapshot.updated_at)
    if quote_time is None:
        return float("inf")
    return max(0.0, (now - quote_time).total_seconds())


def _load_snapshot_map(trade_date_api: str, source: str) -> dict[str, RealtimeSnapshot]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                code,
                trade_date,
                last_price,
                open,
                high,
                low,
                pre_close,
                pct_chg,
                vol,
                amount,
                quote_time,
                source,
                is_stale,
                created_at,
                updated_at
            FROM etf_realtime_snapshot
            WHERE trade_date = ?
              AND source = ?
            ORDER BY code ASC
            """,
            (trade_date_api, source),
        ).fetchall()
    return {row["code"]: _row_to_snapshot(row) for row in rows}


def _upsert_realtime_quotes(quotes: list[RealtimeQuote], now: datetime) -> None:
    if not quotes:
        return

    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    records = [
        {
            "code": quote.code,
            "trade_date": quote.trade_date,
            "last_price": quote.last_price,
            "open": quote.open,
            "high": quote.high,
            "low": quote.low,
            "pre_close": quote.pre_close,
            "pct_chg": quote.pct_chg,
            "vol": quote.vol,
            "amount": quote.amount,
            "quote_time": quote.quote_time,
            "source": quote.source,
            "is_stale": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        for quote in quotes
    ]

    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO etf_realtime_snapshot (
                code,
                trade_date,
                last_price,
                open,
                high,
                low,
                pre_close,
                pct_chg,
                vol,
                amount,
                quote_time,
                source,
                is_stale,
                created_at,
                updated_at
            )
            VALUES (
                :code,
                :trade_date,
                :last_price,
                :open,
                :high,
                :low,
                :pre_close,
                :pct_chg,
                :vol,
                :amount,
                :quote_time,
                :source,
                :is_stale,
                :created_at,
                :updated_at
            )
            ON CONFLICT(code) DO UPDATE SET
                trade_date = excluded.trade_date,
                last_price = excluded.last_price,
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                pre_close = excluded.pre_close,
                pct_chg = excluded.pct_chg,
                vol = excluded.vol,
                amount = excluded.amount,
                quote_time = excluded.quote_time,
                source = excluded.source,
                is_stale = excluded.is_stale,
                updated_at = excluded.updated_at
            """,
            records,
        )


def _fetch_realtime_quotes_by_source(source: str, codes: list[str]) -> list[RealtimeQuote]:
    if source == "mootdx":
        return fetch_mootdx_realtime_quotes(codes)
    if source == "tencent":
        return fetch_tencent_realtime_quotes(codes)
    raise ValueError(f"不支持的实时数据源: {source}")


def get_realtime_dashboard_context(codes: list[str], selected_trade_date: str, explicit_trade_date: bool) -> tuple[dict[str, RealtimeSnapshot], dict[str, Any]]:
    init_db()
    realtime_source = settings.realtime_source if settings.realtime_source in SUPPORTED_REALTIME_SOURCES else "fallback"
    status = RealtimeStatus(
        enabled=settings.realtime_enabled,
        active=False,
        source="fallback",
        as_of=None,
        stale=False,
        display_mode="official_close",
    )
    if not should_use_intraday_realtime(selected_trade_date, explicit_trade_date):
        return {}, asdict(status)

    now = datetime.now()
    trade_date_api = _today_api(now)
    requested_codes = [code.strip() for code in codes if code and code.strip()]
    requested_code_set = set(requested_codes)
    snapshot_map = _load_snapshot_map(trade_date_api, realtime_source)
    snapshot_map = {code: snapshot for code, snapshot in snapshot_map.items() if code in requested_code_set}

    codes_to_refresh = [
        code
        for code in requested_codes
        if code not in snapshot_map
        or _snapshot_age_seconds(snapshot_map[code], now) > settings.realtime_refresh_window_seconds
    ]

    if codes_to_refresh:
        try:
            quotes = _fetch_realtime_quotes_by_source(realtime_source, codes_to_refresh)
            _upsert_realtime_quotes(quotes, now)
        except Exception as exc:
            logger.warning("%s 实时行情刷新失败: %s", realtime_source, exc)

    refreshed_map = _load_snapshot_map(trade_date_api, realtime_source)
    refreshed_map = {code: snapshot for code, snapshot in refreshed_map.items() if code in requested_code_set}

    if not refreshed_map:
        status.stale = bool(snapshot_map)
        status.as_of = max((snapshot.quote_time for snapshot in snapshot_map.values()), default=None)
        return {}, asdict(status)

    as_of_now = datetime.now()
    status.source = realtime_source
    status.as_of = max(snapshot.quote_time for snapshot in refreshed_map.values())
    status.display_mode = "intraday"
    status.active = True
    status.stale = all(
        _snapshot_age_seconds(snapshot, as_of_now) > settings.realtime_stale_threshold_seconds
        for snapshot in refreshed_map.values()
    )
    return refreshed_map, asdict(status)
